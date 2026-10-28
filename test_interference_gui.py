# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Real GTK/GL worker, revision invalidation and temporary inspection views."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk,Gio,GLib
import app as module
from geometry import generate
from interference import Settings


def pump(duration=.04):
    until=time.monotonic()+duration;context=GLib.MainContext.default()
    while time.monotonic()<until:
        while context.pending():context.iteration(False)
        time.sleep(.002)


def wait_until(predicate,seconds=10):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        pump(.03)
        if predicate():return True
    return False


class InterferenceGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check() or Gdk.Display.get_default() is None:raise unittest.SkipTest('GTK display required')
        cls.temp=TemporaryDirectory(prefix='ratiolab-interference-gui-');root=Path(cls.temp.name)
        cls.env=patch.dict(os.environ,dict(XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'),APPDATA=str(root/'roaming'),LOCALAPPDATA=str(root/'local')));cls.env.start()
        cls.app=module.ReducerApp();cls.app.set_application_id(f'local.solidcraft.reducers.interferencetests.p{os.getpid()}');cls.app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        cls.app.register(None);cls.app.activate();pump(.15)

    @classmethod
    def tearDownClass(cls):
        for w in cls.app.get_windows():w.destroy()
        pump();cls.env.stop();cls.temp.cleanup()

    def setUp(self):
        a=self.app;a.interference.invalidate();a.load_config_data(dict(format='solidcraft-riduttori/1',family='parallel',parameters=generate('parallel',{'input_rpm':0}).values))
        a.interference.open();pump();self.c=a.interference
        if self.c.thread:self.c.thread.join(2)

    def run_check(self,settings=None):
        self.c.start(settings or Settings(step_degrees=180,max_seconds=20))
        self.assertTrue(wait_until(lambda:self.c.cancel is None,25));self.assertIsNotNone(self.c.result)
        return self.c.result

    def test_real_result_selection_gl_and_restore_preserve_document_exports(self):
        a=self.app;c=self.c;before=a.config();token=a.document.token;states=len(a.document.states)
        a.view_options['exploded'].set_active(True);a.view_options['section'].set_active(True)
        r=self.run_check();self.assertTrue(r.coverage_complete);self.assertTrue(r.rows)
        c.list.select_row(c.list.get_row_at_index(0));pump(.1)
        self.assertIsNotNone(a.canvas.inspection_phase);self.assertEqual(len(a.canvas.inspection_indices),2)
        self.assertFalse(a.canvas.exploded);self.assertFalse(a.canvas.section);self.assertTrue(a.canvas.show_support)
        self.assertIsNone(a.canvas.failure);self.assertIsNotNone(a.canvas.gl)
        self.assertEqual(a.config(),before);self.assertEqual(a.document.token,token);self.assertEqual(len(a.document.states),states)
        captured=[];a.canvas.capture_png(lambda data,error:captured.append((data,error)))
        self.assertTrue(captured);self.assertIsNone(captured[0][1]);self.assertTrue(captured[0][0].startswith(b'\x89PNG'))
        if os.environ.get('RATIOLAB_INTERFERENCE_ARTIFACT'):Path(os.environ['RATIOLAB_INTERFERENCE_ARTIFACT']).write_bytes(captured[0][0])
        c.restore_view();self.assertIsNone(a.canvas.inspection_phase);self.assertTrue(a.canvas.exploded);self.assertTrue(a.canvas.section)
        a.view_options['exploded'].set_active(False);a.view_options['section'].set_active(False)

    def test_edit_invalidates_before_debounce_and_invalid_text_blocks(self):
        a=self.app;c=self.c;self.run_check();c.list.select_row(c.list.get_row_at_index(0));pump()
        a.inputs['module'].set_text('-')
        self.assertIsNone(c.result);self.assertIsNone(a.canvas.inspection_phase)
        self.assertIn('changed',c.summary.get_text())
        pump(.15);self.assertIsNone(a.design);c.start();self.assertIsNone(c.result);self.assertIn('Invalid',c.summary.get_text())

    def test_identical_replacement_and_late_callback_rejected(self):
        a=self.app;c=self.c;self.run_check();old=c.result;serial=c.serial;oldtoken=a.document.token;obj=a.config()
        a.load_config_data(obj);self.assertNotEqual(a.document.token[0],oldtoken[0]);self.assertIsNone(c.result)
        c.finished(serial,old,None);self.assertIsNone(c.result)
        self.assertEqual(c.list.get_first_child(),None)

    def test_cancel_real_worker_retains_explicit_partial_report(self):
        a=self.app;c=self.c
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='planetary',parameters=generate('planetary').values))
        c.start(Settings(step_degrees=.1,max_seconds=20));self.assertIsNotNone(c.cancel);pump(.05);c.stop()
        self.assertTrue(wait_until(lambda:c.cancel is None,5));self.assertIsNotNone(c.result)
        self.assertFalse(c.result.coverage_complete);self.assertTrue(c.result.cancelled);self.assertIn('INCOMPLETE',c.summary.get_text())

    def test_edit_during_worker_and_close_reject_late_results(self):
        a=self.app;c=self.c
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='planetary',parameters=generate('planetary').values))
        c.start(Settings(step_degrees=.1,max_seconds=20));serial=c.serial
        a.inputs['module'].set_text('2.5');self.assertIsNone(c.result);pump(.3)
        self.assertTrue(wait_until(lambda:not c.thread.is_alive(),5));self.assertIsNone(c.result);self.assertGreater(c.serial,serial)
        c.open();c.start(Settings(step_degrees=.1,max_seconds=20));c.window.close();pump(.2)
        self.assertTrue(wait_until(lambda:not c.thread.is_alive(),5));self.assertIsNone(c.window)
        # Closed analysis window can receive a cancelled partial report, but cannot
        # leave an inspection pose active or affect document/export data.
        self.assertIsNone(a.canvas.inspection_phase)

    def test_refresh_same_revision_does_not_create_false_undo_or_invalidate(self):
        a=self.app;c=self.c;r=self.run_check();token=a.document.token
        a.refresh();a.project_changed();self.assertEqual(a.document.token,token);self.assertIs(c.result,r)
        a.save_project(path=Path(self.temp.name)/'check.json');self.assertIs(c.result,r);self.assertFalse(a.document.dirty)

if __name__=='__main__':unittest.main()
