# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Native GTK lifecycle checks; all network, package and launch operations injected."""
import json
import itertools
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk, Gdk
import update_ui
import updates
from project_ui import ProjectActions
from project_document import Document
from test_update_ui import pump
from test_updates import release, asset


_app_ids=itertools.count()


class ProjectApp(ProjectActions, Gtk.Application):
    """Real document protection/save/finish logic with a small native window."""
    def __init__(self,folder):
        super().__init__(application_id=f'local.ratiolab.updateflow.p{os.getpid()}.t{next(_app_ids)}',flags=0)
        self.register(None)
        self.win=Gtk.ApplicationWindow(application=self)
        self.win.set_child(Gtk.Label(label='Temporary update-flow test document'))
        self.header=Gtk.HeaderBar();self.win.set_titlebar(self.header)
        self.win.connect('close-request',self.close_project)
        self.project_alive=True;self.project_dialog=None;self.busy=False;self.messages=[]
        self.document=Document({'edit':0},folder/'project.json')
        self.document.record({'edit':1})
        self.project_store=SimpleNamespace(session=folder/'recovery.json')
        self.project_store.session.write_text('temporary recovery')
        self.quit_calls=0;self.settled=0;self.close_calls=0
        self.win.present()
        self.win.connect('unrealize',lambda *_:setattr(self,'project_alive',False))
    def settle_project(self):self.settled+=1
    def project_changed(self):pass
    def status_text(self,message):self.messages.append(message)
    def config(self):return {'saved':self.document.current}
    def update_document(self):pass
    def remember_project(self,path):pass
    def quit(self):self.quit_calls+=1
    def finish_close_project(self,before_close=None):
        self.close_calls+=1
        return super().finish_close_project(before_close=before_close)


class FakeDownload:
    def __init__(self):self.cleaned=0
    def cleanup(self):self.cleaned+=1


class FakePrepared:
    def __init__(self,installation,folder,fail=False):
        self.installation=installation;self.directory=folder;self.package=folder/'package.run'
        self.action_label='Close, install and restart' if installation.requires_exit else 'Open package installer'
        self.command='';self.log_path=folder/'install.log';self.result_path=folder/'result.json'
        self.launched=0;self.cancelled=0;self.fail=fail
        self.helper_status='ready'
    def status(self):return self.helper_status
    def launch(self):
        if self.fail:raise OSError('injected launch failure')
        self.launched+=1
    def cancel(self):self.cancelled+=1


class UpdateFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            raise unittest.SkipTest('A native GTK display is required')

    def setUp(self):
        self.temp=TemporaryDirectory();self.folder=Path(self.temp.name)
        self.config=patch.object(update_ui.app_paths,'config_dir',return_value=self.folder);self.config.start()
        self.env=patch.dict(os.environ,{'RATIOLAB_UPDATE_CHECK':'1'});self.env.start()
        self.app=ProjectApp(self.folder);self.controllers=[];self.opened=[];self.thread_ids=[]
        self.installation=SimpleNamespace(can_install=True,requires_exit=True,package_format='.run',
            explanation='Temporary marked test bundle.',selection_target=lambda:dict(system='linux',machine='x86_64',package_format='.run'))
        major,minor,patch_number=updates.Version(update_ui.RELEASE_VERSION).core
        self.release_version=f'{major}.{minor}.{patch_number+1}'
        tag='v'+self.release_version
        self.record=release(tag,assets=[asset(f'RatioLab-{self.release_version}-linux-x86_64.run',tag),asset('SHA256SUMS',tag)])
        self.record['assets'][0]['size']=10
        self.verified=FakeDownload();self.prepared=FakePrepared(self.installation,self.folder)
        self.main_thread=threading.get_ident()

    def tearDown(self):
        for controller in self.controllers:controller.close()
        if self.app.project_dialog:self.app.project_dialog.destroy();self.app.project_dialog=None
        for window in list(self.app.get_windows()):window.destroy()
        self.config.stop();self.env.stop();self.temp.cleanup()

    def controller(self,fetch=None,download=None,prepare=None,detect=None):
        def do_download(*args,**kwargs):
            self.thread_ids.append(threading.get_ident());kwargs['progress'](5,10);return self.verified
        def do_prepare(*args,**kwargs):
            self.thread_ids.append(threading.get_ident());return self.prepared
        def do_detect():
            self.thread_ids.append(threading.get_ident());return self.installation
        controller=update_ui.Controller(self.app,self.app.header,fetch=fetch or (lambda:[self.record]),
            launch=self.opened.append,detect=detect or do_detect,download=download or do_download,
            prepare=prepare or do_prepare,cache=self.folder/'cache')
        self.controllers.append(controller);return controller

    def ready(self,controller):
        controller.show(manual=True);pump(lambda:not controller.inflight)
        self.assertTrue(controller._eligible())
        self.assertEqual(self.opened,[])

    def start_update(self,controller):
        self.ready(controller);controller.begin_download()
        pump(lambda:not controller.worker_running)

    def test_manual_checks_with_automatic_off_persist_fresh_skip_and_disabled(self):
        controller=self.controller();controller.set_automatic(False);controller.start()
        self.assertFalse(controller.inflight);self.assertEqual(controller.timer,0)
        self.assertFalse(updates.Preferences(self.folder/'updates.json').automatic)
        self.ready(controller);controller.preferences.skip(controller.release);controller.refresh()
        self.assertFalse(controller.button.get_visible())
        controller.show(manual=True);pump(lambda:not controller.inflight)
        self.assertEqual(controller.displayed_release.version,self.release_version)
        self.assertFalse(controller.button.get_visible());self.assertEqual(controller.timer,0)
        controller.fetch=lambda:[];controller.check_button.emit('clicked');pump(lambda:not controller.inflight)
        self.assertIn('up to date',controller.status_label.get_text())
        self.assertIsNone(controller.displayed_release)
        with patch.dict(os.environ,{'RATIOLAB_UPDATE_CHECK':'0'}):
            called=[];controller.fetch=lambda:called.append(True)
            controller.show(manual=True)
            self.assertIn('disabled by',controller.status_label.get_text());self.assertEqual(called,[])
            self.assertFalse(controller.check_button.get_sensitive())

    def test_network_manual_retry_rate_limit_no_duplicate_checks(self):
        gate=threading.Event();entered=threading.Event();calls=[]
        def failing():entered.set();gate.wait(2);calls.append(True);raise OSError('fixture offline')
        controller=self.controller(fetch=failing);controller.show(manual=True)
        self.assertTrue(entered.wait(2));controller.check(manual=True);self.assertTrue(controller.inflight)
        gate.set();pump(lambda:not controller.inflight)
        self.assertEqual(calls,[True]);self.assertIn('fixture offline',controller.status_label.get_text())
        self.assertEqual(controller.preferences.state['backoff_reason'],'network')
        controller.fetch=lambda:[];controller.check(manual=True);pump(lambda:not controller.inflight)
        self.assertIn('up to date',controller.status)
        def limited():raise updates.RetryAfter(3600)
        controller.fetch=limited;controller.check(manual=True);pump(lambda:not controller.inflight)
        self.assertIn('GitHub has limited',controller.status_label.get_text())
        controller.fetch=lambda:self.fail('Rate-limited manual retry performed network request')
        controller.check(manual=True);self.assertFalse(controller.inflight)
        self.assertIn('temporarily limited',controller.status_label.get_text())

    def test_download_cancel_visible_progress_late_worker_cleanup_no_duplicate(self):
        gate=threading.Event();entered=threading.Event()
        def download(*args,**kwargs):
            kwargs['progress'](5,10);entered.set();gate.wait(2);return self.verified
        controller=self.controller(download=download);self.ready(controller);controller.begin_download()
        self.assertTrue(entered.wait(2));pump(lambda:controller.progress_bar.get_fraction()==.5)
        cancel=controller.job_box.get_last_child();self.assertEqual(cancel.get_label(),'Cancel');cancel.emit('clicked')
        controller.begin_download();self.assertTrue(controller.worker_running)
        gate.set();pump(lambda:not controller.worker_running)
        self.assertEqual(self.verified.cleaned,1);self.assertEqual(self.prepared.launched,0)
        self.assertIsNone(controller.prepared);self.assertEqual(self.app.quit_calls,0)

    def test_closed_window_late_preparation_disarms_and_cleans_download(self):
        gate=threading.Event();entered=threading.Event()
        def prepare(*args,**kwargs):entered.set();gate.wait(2);return self.prepared
        controller=self.controller(prepare=prepare);self.ready(controller);controller.begin_download()
        self.assertTrue(entered.wait(2));controller.window.destroy();gate.set()
        pump(lambda:not controller.worker_running)
        self.assertGreater(self.prepared.cancelled,0);self.assertEqual(self.verified.cleaned,1)
        self.assertEqual(self.prepared.launched,0);self.assertEqual(self.app.quit_calls,0)

    def test_release_replacement_invalidates_late_preparation(self):
        gate=threading.Event();entered=threading.Event()
        def prepare(*args,**kwargs):entered.set();gate.wait(2);return self.prepared
        controller=self.controller(prepare=prepare);self.ready(controller);controller.begin_download()
        major,minor,patch_number=updates.Version(self.release_version).core
        replacement_version=f'{major}.{minor}.{patch_number+1}'
        self.assertTrue(entered.wait(2));controller.fetch=lambda:[release('v'+replacement_version)]
        controller.check(manual=True);pump(lambda:not controller.inflight)
        gate.set();pump(lambda:not controller.worker_running)
        self.assertEqual(controller.release.version,replacement_version);self.assertGreater(self.prepared.cancelled,0)
        self.assertEqual(self.prepared.launched,0)

    def test_document_cancel_and_stale_answer_never_arm(self):
        for stale in (False,True):
            controller=self.controller();self.start_update(controller)
            self.assertIsNotNone(self.app.project_dialog)
            if stale:self.app.document.record({'edit':self.app.document.revision+2})
            self.app.project_dialog.response(Gtk.ResponseType.REJECT if stale else Gtk.ResponseType.CANCEL)
            self.assertEqual(self.prepared.launched,0);self.assertGreater(self.prepared.cancelled,0)
            self.assertTrue(self.app.win.get_visible());self.assertEqual(self.app.quit_calls,0)
            self.assertIsNone(controller.prepared);controller.close()

    def test_failed_save_keeps_app_open_and_disarms(self):
        controller=self.controller();self.start_update(controller)
        with patch('project_ui.atomic_json',side_effect=OSError('fixture save failure')):
            self.app.project_dialog.response(Gtk.ResponseType.ACCEPT)
        self.assertEqual(self.prepared.launched,0);self.assertGreater(self.prepared.cancelled,0)
        self.assertTrue(self.app.win.get_visible());self.assertEqual(self.app.close_calls,0)
        self.assertIn('fixture save failure',self.app.messages[-1])

    def test_accepted_save_closes_once_and_arms_once_after_save(self):
        controller=self.controller();self.start_update(controller)
        self.assertEqual(self.prepared.launched,0)
        extra=Gtk.ApplicationWindow(application=self.app);extra.present()
        self.app.project_dialog.response(Gtk.ResponseType.ACCEPT)
        self.assertEqual(self.prepared.launched,1);self.assertEqual(self.prepared.cancelled,0)
        self.assertEqual(self.app.close_calls,1);self.assertEqual(self.app.quit_calls,1)
        self.assertFalse(self.app.win.get_visible());self.assertFalse(extra.get_visible())
        self.assertTrue(self.app.document.path.is_file());self.assertFalse(self.app.project_store.session.exists())
        self.assertTrue(all(thread!=self.main_thread for thread in self.thread_ids))

    def test_accepted_discard_closes_once_without_writing_project(self):
        controller=self.controller();self.start_update(controller)
        self.app.project_dialog.response(Gtk.ResponseType.REJECT)
        self.assertEqual(self.prepared.launched,1);self.assertEqual(self.app.close_calls,1)
        self.assertEqual(self.app.quit_calls,1);self.assertFalse(self.app.document.path.exists())

    def test_launch_failure_keeps_app_usable_and_requires_fresh_package(self):
        self.prepared.fail=True;controller=self.controller();self.start_update(controller)
        self.app.project_dialog.response(Gtk.ResponseType.REJECT)
        self.assertTrue(self.app.win.get_visible());self.assertFalse(self.app.closing_project)
        self.assertEqual(self.app.quit_calls,0);self.assertIsNone(controller.prepared)
        self.assertIn('injected launch failure',controller.job_status)

    def test_nonexit_system_package_opens_without_save_prompt(self):
        self.installation.requires_exit=False;self.prepared.command="sudo apt install '/tmp/verified fixture.deb'"
        controller=self.controller();self.start_update(controller)
        self.assertEqual(self.prepared.launched,1);self.assertIsNone(self.app.project_dialog)
        self.assertTrue(self.app.win.get_visible());self.assertEqual(self.app.quit_calls,0)
        self.assertFalse(controller.install_button.get_sensitive())
        labels=[];child=controller.job_box.get_first_child()
        while child:
            if isinstance(child,Gtk.Label):labels.append(child.get_text());self.assertTrue(child.get_selectable())
            child=child.get_next_sibling()
        self.assertIn(self.prepared.command,' '.join(labels))

    def test_manual_installation_never_downloads_or_prepares(self):
        self.installation.can_install=False
        controller=self.controller(download=lambda *a,**k:self.fail('Manual installation downloaded'))
        controller.show(manual=True);pump(lambda:not controller.inflight)
        self.assertFalse(controller._eligible());controller.begin_download()
        self.assertFalse(controller.worker_running);self.assertEqual(self.prepared.launched,0)

    def test_checkbox_save_failure_restores_visible_choice_and_reports_error(self):
        controller=self.controller();controller.show()
        with patch('project_document.atomic_json',side_effect=OSError('read only fixture')):
            controller.automatic_button.set_active(False)
        self.assertTrue(controller.preferences.automatic)
        self.assertTrue(controller.automatic_button.get_active())
        self.assertIn('could not be saved',controller.status_label.get_text())

    def test_missing_guard_or_busy_app_refuses_handoff(self):
        self.app.protect_document=None
        controller=self.controller();self.start_update(controller)
        self.assertEqual(self.prepared.launched,0);self.assertGreater(self.prepared.cancelled,0)
        self.assertIn('safely close',controller.job_status)
        self.assertTrue(self.app.win.get_visible())

    def test_recovery_failure_prevents_arm_and_keeps_project(self):
        controller=self.controller();self.start_update(controller)
        self.app.project_store.session.unlink();self.app.project_store.session.mkdir()
        self.app.project_dialog.response(Gtk.ResponseType.REJECT)
        self.assertEqual(self.prepared.launched,0);self.assertGreater(self.prepared.cancelled,0)
        self.assertTrue(self.app.win.get_visible());self.assertEqual(self.app.quit_calls,0)
        self.assertIn('Could not clear session recovery',self.app.messages[-1])

    def test_cancellation_while_guard_open_invalidates_accepted_reply(self):
        controller=self.controller();self.start_update(controller)
        dialog=self.app.project_dialog;controller.cancel_download()
        dialog.response(Gtk.ResponseType.REJECT)
        self.assertEqual(self.prepared.launched,0);self.assertEqual(self.app.quit_calls,0)
        self.assertTrue(self.app.win.get_visible())

    def test_helper_expiry_while_guard_open_disarms_and_rejects_late_discard(self):
        controller=self.controller();self.start_update(controller)
        dialog=self.app.project_dialog;self.prepared.helper_status='expired'
        pump(lambda:controller.prepared is None)
        self.assertIn('expired',controller.job_status)
        dialog.response(Gtk.ResponseType.REJECT)
        self.assertEqual(self.prepared.launched,0);self.assertEqual(self.app.quit_calls,0)

    def test_system_opener_status_waits_for_completion_and_exposes_failure(self):
        self.installation.requires_exit=False
        controller=self.controller();self.start_update(controller)
        self.assertIn('Opening the verified',controller.job_status)
        self.prepared.helper_status='checksum-mismatch'
        pump(lambda:controller.prepared is None)
        self.assertIn('checksum-mismatch',controller.job_status)
        self.assertIn(str(self.prepared.result_path),controller.job_status)
        self.assertTrue(self.app.win.get_visible())

    def test_system_opener_reports_opened_only_after_terminal_status(self):
        self.installation.requires_exit=False
        controller=self.controller();self.start_update(controller)
        self.assertIn('Opening the verified',controller.job_status)
        self.prepared.helper_status='opened';pump(lambda:controller.prepared is None)
        self.assertIn('Package opened.',controller.job_status)
        self.assertIsNone(controller.install_button)

    def test_browser_fallback_uses_external_program_launcher(self):
        controller=self.controller();controller.launch=controller._launch
        with patch.object(update_ui.external_programs,'launch_uri',return_value=True) as launch:
            self.assertTrue(controller._launch(updates.RELEASES_URL))
        self.assertEqual(launch.call_args.args[0],updates.RELEASES_URL)

    def test_clean_document_arms_and_closes_without_save_prompt(self):
        self.app.document.mark_saved(self.folder/'existing.json')
        controller=self.controller();self.start_update(controller)
        self.assertIsNone(self.app.project_dialog);self.assertEqual(self.prepared.launched,1)
        self.assertEqual(self.app.close_calls,1);self.assertEqual(self.app.quit_calls,1)

    def test_failed_window_close_disarms_and_leaves_retry_visible(self):
        controller=self.controller();self.start_update(controller)
        with patch.object(self.app.win,'close',side_effect=OSError('fixture close failure')):
            self.app.project_dialog.response(Gtk.ResponseType.REJECT)
        self.assertEqual(self.prepared.launched,1);self.assertGreater(self.prepared.cancelled,0)
        self.assertTrue(self.app.win.get_visible());self.assertEqual(self.app.quit_calls,0)
        self.assertIn('fixture close failure',controller.job_status)
        self.assertFalse(self.app.closing_project)

    def test_cancelled_save_chooser_disarms_without_closing(self):
        self.app.document.path=None;self.app.family='parallel';self.app.output_dir=self.folder
        controller=self.controller();self.start_update(controller)
        # Keep the native chooser's async desktop portal out of a synthetic
        # response test; the real save/cancel callback and GTK object are used.
        with patch.object(Gtk.FileChooserNative,'show',lambda widget:None):
            self.app.project_dialog.response(Gtk.ResponseType.ACCEPT)
        chooser=self.app.project_dialog
        self.assertIsInstance(chooser,Gtk.FileChooserNative)
        chooser.emit('response',Gtk.ResponseType.CANCEL)
        self.assertGreater(self.prepared.cancelled,0);self.assertEqual(self.prepared.launched,0)
        self.assertEqual(self.app.quit_calls,0);self.assertTrue(self.app.win.get_visible())


if __name__=='__main__':unittest.main()
