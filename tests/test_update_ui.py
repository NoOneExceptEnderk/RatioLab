# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Display-backed GTK tests with injected releases: never uses real network/browser."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest.mock import patch
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk,GLib
import update_ui
from test_updates import release as release_record,asset as release_asset


def release(tag='v0.1.2',**extra):
    return release_record(tag,**extra)


def asset(name,tag='v0.1.2'):
    return release_asset(name,tag)


def pump(until=lambda:False,timeout=2):
    end=time.monotonic()+timeout
    context=GLib.MainContext.default()
    while time.monotonic()<end:
        while context.pending():context.iteration(False)
        if until():return
        time.sleep(.005)
    if not until():raise AssertionError('GTK update callback did not complete')


class UpdateUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check() or Gdk.Display.get_default() is None:raise unittest.SkipTest('GTK display required')
        cls.application=Gtk.Application(application_id=f'local.solidcraft.reducers.updates.p{os.getpid()}')
        cls.application.register(None)

    def setUp(self):
        self.directory=TemporaryDirectory()
        # Exercise a fixed stable installation even after future release bumps.
        select_release=update_ui.updates.select_release
        def select_stable(records,**target):
            options=dict(current='0.1.1',channel='stable');options.update(target)
            return select_release(records,**options)
        self.selector=patch.object(update_ui.updates,'select_release',side_effect=select_stable)
        self.selector.start()
        self.env=patch.dict(os.environ,{'RATIOLAB_UPDATE_CHECK':'1'});self.env.start()
        self.config=patch.object(update_ui.app_paths,'config_dir',return_value=Path(self.directory.name));self.config.start()
        self.application.win=Gtk.ApplicationWindow(application=self.application)
        self.header=Gtk.HeaderBar();self.application.win.set_titlebar(self.header)
        self.opened=[];self.controllers=[]

    def tearDown(self):
        for controller in self.controllers:controller.close()
        self.application.win.destroy();self.config.stop();self.env.stop();self.selector.stop();self.directory.cleanup()

    def controller(self,fetch):
        controller=update_ui.Controller(self.application,self.header,fetch=fetch,launch=self.opened.append)
        self.controllers.append(controller);return controller

    def test_new_release_badge_only_then_click_notes_without_browser(self):
        controller=self.controller(lambda:[release(assets=[asset('RatioLab-0.1.2-linux-x86_64.run')])])
        self.assertFalse(controller.button.get_visible());controller.start()
        pump(lambda:not controller.inflight)
        self.assertEqual(controller.badge_label.get_text(),'Update to 0.1.2')
        self.assertTrue(controller.button.get_visible());self.assertIsNone(controller.window)
        controller.button.emit('clicked');self.assertIsNotNone(controller.window)
        self.assertEqual(self.opened,[])
        box=controller.window.get_child();row=box.get_last_child().get_prev_sibling().get_prev_sibling()
        row.get_first_child().emit('clicked')
        self.assertEqual(self.opened,[controller.release.download])
        controller._hide('skip');self.assertFalse(controller.button.get_visible())
        controller.release=update_ui.updates.select_release([release('v0.1.3')]);controller.refresh()
        self.assertTrue(controller.button.get_visible())
        controller._hide('remind');self.assertFalse(controller.button.get_visible())

    def test_equal_older_offline_and_disabled_stay_hidden(self):
        for records in [[release('v0.1.1')],[release('v0.1.0')],[]]:
            controller=self.controller(lambda r=records:r);controller.start();pump(lambda:not controller.inflight)
            self.assertFalse(controller.button.get_visible());self.assertIsNone(controller.window)
            controller.close()
        def offline():raise OSError('offline')
        controller=self.controller(offline);controller.start();pump(lambda:not controller.inflight)
        self.assertFalse(controller.button.get_visible());self.assertGreater(controller.timer,0)
        self.assertGreater(controller.preferences.state['next_allowed'],time.time())
        called=[]
        with patch.dict(os.environ,{'RATIOLAB_UPDATE_CHECK':'0'}):
            other=self.controller(lambda:called.append(True));other.start();self.assertEqual(called,[])

    def test_late_callback_after_close_never_updates_widgets_or_opens_window(self):
        gate=threading.Event();finished=threading.Event()
        def delayed():gate.wait(2);finished.set();return [release()]
        controller=self.controller(delayed);controller.start()
        controller.close();gate.set();self.assertTrue(finished.wait(2))
        sentinel=[];GLib.idle_add(lambda:(sentinel.append(True),False)[1]);pump(lambda:bool(sentinel))
        self.assertFalse(controller.button.get_visible());self.assertIsNone(controller.window)
        self.assertEqual(controller.timer,0)

    def test_backoff_persists_and_local_changelog_available_without_update(self):
        controller=self.controller(lambda:[])
        controller.preferences.state['next_allowed']=time.time()+7200
        controller.start();self.assertFalse(controller.inflight);self.assertGreater(controller.timer,0)
        controller.show();self.assertIsNotNone(controller.window)
        self.assertFalse(controller.button.get_visible());self.assertEqual(self.opened,[])

    def test_open_window_keeps_its_release_actions_and_badge_rebuilds_new_notes(self):
        controller=self.controller(lambda:[])
        controller.release=update_ui.updates.select_release([release()]);controller.refresh();controller.show()
        old=controller.window;shown=controller.release
        controller.release=update_ui.updates.select_release([release('v0.1.3',body='New v4 notes')]);controller.refresh()
        controller._hide('skip',shown,old)
        self.assertTrue(controller.button.get_visible());self.assertEqual(controller.preferences.state['skip'],shown.version)
        controller.show();self.assertEqual(controller.displayed_release.version,'0.1.3')
        previous=controller.window
        controller.release=update_ui.updates.select_release([release('v0.1.4')]);controller.refresh()
        controller.button.emit('clicked')
        self.assertIsNot(controller.window,previous);self.assertEqual(controller.displayed_release.version,'0.1.4')

    def test_browser_failure_is_inline_with_copyable_url(self):
        controller=self.controller(lambda:[])
        controller.release=update_ui.updates.select_release([release()]);controller.show()
        def failed(_):raise OSError('No handler')
        controller.launch=failed
        box=controller.window.get_child();error=box.get_last_child().get_prev_sibling();row=error.get_prev_sibling()
        row.get_first_child().emit('clicked')
        self.assertTrue(error.get_visible());self.assertTrue(error.get_selectable())
        self.assertIn(controller.release.download,error.get_text());self.assertIn('No handler',error.get_text())


if __name__=='__main__':unittest.main()
