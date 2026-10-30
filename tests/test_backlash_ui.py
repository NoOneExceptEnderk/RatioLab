# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Display-backed proposal/history and asynchronous stale callback checks."""
from copy import deepcopy
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import time
import unittest
from unittest.mock import patch
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk, Gdk, Gio, GLib
import app as module
import backlash_solver
from geometry import generate
from interference import Analysis


def pump(duration=.08):
    end=time.monotonic()+duration
    context=GLib.MainContext.default()
    while time.monotonic()<end:
        while context.pending():context.iteration(False)
        time.sleep(.003)


def wait_for(predicate,seconds=15):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:pump(.02)
    if not predicate():raise AssertionError('Timed out waiting for worker/GTK callback')


def checked(*args,**kwargs):
    return Analysis(dict(step_degrees=180,tolerance_mm=.01,max_poses=721,max_seconds=30,
                         max_parts=128,max_triangles=300000),coverage_complete=True,
                    planned_poses=7,completed_poses=7)


class BacklashUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            raise unittest.SkipTest('GTK display required')
        cls.folder=TemporaryDirectory();root=Path(cls.folder.name)
        cls.environment=patch.dict(os.environ,dict(XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'),APPDATA=str(root/'roaming'),LOCALAPPDATA=str(root/'local')))
        cls.environment.start()
        cls.original_base,cls.original_generated=module.BASE,module.GENERATED
        module.BASE=root;module.GENERATED=root/'exports'
        cls.app=module.ReducerApp()
        cls.app.set_application_id(f'local.solidcraft.reducers.backlashtests.p{os.getpid()}')
        cls.app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        cls.app.register(None);cls.app.activate();pump(.15)

    @classmethod
    def tearDownClass(cls):
        for window in cls.app.get_windows():window.destroy()
        module.BASE,module.GENERATED=cls.original_base,cls.original_generated
        cls.environment.stop();cls.folder.cleanup()

    def setUp(self):
        a=self.app
        a.load_config_data({'format':'solidcraft-riduttori/1','family':'parallel','parameters':generate('parallel').values})
        pump()
        a.backlash.button.emit('clicked');pump()
        self.c=a.backlash
        self.analysis=patch('backlash_solver.analyze',side_effect=checked)
        self.analysis.start()

    def tearDown(self):
        self.c.stop()
        if self.c.thread:wait_for(lambda:not self.c.thread.is_alive())
        if self.c.window:self.c.window.close()
        if self.app.gear_measurement.window:self.app.gear_measurement.window.close()
        pump(.03)
        self.analysis.stop()

    def calculate(self,target='.372826053062876'):
        self.c.target.set_text(target)
        self.assertTrue(self.c.start())
        wait_for(lambda:self.c.result is not None or self.c.cancel is None)
        self.assertIsNotNone(self.c.result,self.text())
        self.assertTrue(self.c.result.applicable,self.c.result.reason)

    def text(self):
        b=self.c.report.get_buffer()
        return b.get_text(b.get_start_iter(),b.get_end_iter(),True)

    def test_preview_is_readonly_preserves_main_canvas_and_exports(self):
        a,c=self.app,self.c
        self.assertIs(a.tools.controllers['backlash'],c)
        a.canvas.motion_phase=2.3
        a.canvas.show_inspection(.7,(0,1))
        before=(a.canvas.inspection_phase,a.canvas.inspection_indices,a.canvas.motion_phase,a.canvas.motion_enabled)
        snapshot=a.project_snapshot();token=a.document.token;states=len(a.document.states)
        self.calculate()
        self.assertTrue(c.window.get_visible());self.assertIs(c.preview.design,c.result.design)
        self.assertEqual(a.project_snapshot(),snapshot)
        self.assertEqual(a.document.token,token);self.assertEqual(len(a.document.states),states)
        self.assertIsNot(a.canvas.design,c.preview.design)
        self.assertEqual(before,(a.canvas.inspection_phase,a.canvas.inspection_indices,a.canvas.motion_phase,a.canvas.motion_enabled))
        self.assertIn('change +0.3',self.text());self.assertTrue(c.export())
        self.assertTrue(list(a.output_dir.glob('backlash-proposal-*/backlash.json')))
        c.stop()
        self.assertIsNone(c.preview.design);self.assertFalse(c.apply_button.get_sensitive())
        self.assertEqual(before,(a.canvas.inspection_phase,a.canvas.inspection_indices,a.canvas.motion_phase,a.canvas.motion_enabled))
        self.assertEqual(a.project_snapshot(),snapshot)
        a.canvas.set_motion_playing(True)
        self.assertTrue(a.canvas.motion_playing)
        self.calculate()
        self.assertTrue(a.canvas.motion_playing)
        c.stop();self.assertTrue(a.canvas.motion_playing)
        a.canvas.set_motion_playing(False)

    def test_intentional_apply_one_undo_other_drafts_and_rebound_tools(self):
        a,c=self.app,self.c
        a.values['spur']=generate('spur',{'module':3}).values
        a.raw_edits['spur']={'module':'3.000'}
        a.document.record(a.project_snapshot());a.document.barrier()
        a.document.mark_saved(Path(self.folder.name)/'existing-project.json')
        snapshot=deepcopy(a.project_snapshot());identity=a.document.identity;path=a.document.path;clean=deepcopy(a.document.clean)
        index=a.document.index
        self.calculate()
        self.assertEqual(a.document.index,index)
        self.assertTrue(c.apply())
        self.assertEqual(a.document.identity,identity);self.assertEqual(a.document.path,path)
        self.assertEqual(a.document.clean,clean);self.assertTrue(a.document.dirty)
        self.assertEqual(a.document.index,index+1)
        self.assertEqual(a.values['spur'],snapshot['values']['spur'])
        self.assertEqual(a.raw_edits['spur'],snapshot['raw']['spur'])
        self.assertAlmostEqual(a.design.values['center_extra'],.3,places=11)
        self.assertFalse(c.apply_button.get_sensitive());self.assertFalse(c.apply())
        self.assertEqual(c.result.application,'applied');self.assertEqual(c.result.applied_revision,a.document.token)
        self.assertTrue(c.export())
        self.assertTrue(a.components.current())
        a.gear_measurement.open();pump()
        self.assertTrue(a.gear_measurement.current())
        a.gear_measurement.calculate()
        self.assertIsNotNone(a.gear_measurement.result)
        applied=deepcopy(a.project_snapshot())
        a.undo_project();pump()
        self.assertEqual(a.project_snapshot(),snapshot)
        self.assertIsNone(c.result);self.assertIsNone(c.preview.design)
        a.redo_project();pump()
        self.assertEqual(a.project_snapshot(),applied)
        self.assertIsNone(c.result)

    def test_raw_edits_replacement_normalization_and_unreachable(self):
        a,c=self.app,self.c
        self.calculate()
        serial=c.serial;old=c.result
        a.inputs['module'].set_text('-');a.project_changed(('parallel','module'))
        self.assertIsNone(c.result);self.assertIsNone(c.preview.design)
        self.assertFalse(c.apply());self.assertFalse(c.export())
        c.finished(serial,old,None);self.assertIsNone(c.result)
        a.load_config_data({'format':'solidcraft-riduttori/1','family':'parallel','parameters':generate('parallel',{'variant':'double','gap':0}).values})
        pump()
        self.assertEqual(a.design.values['gap'],0)
        self.calculate('.4')
        self.assertEqual(c.result.values['gap'],0)
        revision=c.revision
        a.load_config_data({'format':'solidcraft-riduttori/1','family':'parallel','parameters':generate('parallel',{'variant':'double','gap':0}).values})
        pump()
        self.assertNotEqual(a.document.token,revision);self.assertIsNone(c.result)
        c.target.set_text('.1');c.start();wait_for(lambda:c.cancel is None)
        self.assertIn('below the reachable',self.text());self.assertFalse(c.apply_button.get_sensitive())
        c.target.set_text('nan');c.start();wait_for(lambda:c.cancel is None)
        self.assertIn('finite',self.text())

    def test_cancel_target_edit_and_close_reject_delayed_workers(self):
        a,c=self.app,self.c
        # Simulates one non-preemptible generator returning after cancellation.
        result=backlash_solver.solve(a.design,.372826053062876)
        for action in ('cancel','target','close','new'):
            with self.subTest(action=action):
                if not c.window:c.open();pump()
                entered,release=Event(),Event()
                def slow(*args,**kwargs):
                    entered.set();release.wait(5);return deepcopy(result)
                with patch('backlash_ui.solve',side_effect=slow):
                    c.target.set_text('.372826053062876');self.assertTrue(c.start())
                    wait_for(entered.is_set)
                    if action=='cancel':c.stop()
                    elif action=='target':c.target.set_text('.5')
                    elif action=='close':c.window.close()
                    else:
                        a.load_config_data({'format':'solidcraft-riduttori/1','family':'parallel','parameters':generate('parallel').values})
                    release.set();wait_for(lambda:not c.thread.is_alive());pump(.05)
                self.assertIsNone(c.result)
                if c.window:
                    self.assertIsNone(c.preview.design)
                    self.assertFalse(c.apply_button.get_sensitive())

    def test_failed_revalidation_and_unsupported_family(self):
        a,c=self.app,self.c
        self.calculate();snapshot=a.project_snapshot();revision=a.document.token
        with patch('backlash_ui.revalidate',side_effect=ValueError('Revalidation test')):
            self.assertFalse(c.apply())
        self.assertEqual(a.project_snapshot(),snapshot);self.assertEqual(a.document.token,revision)
        self.assertIsNone(c.result)
        a.load_config_data({'format':'solidcraft-riduttori/1','family':'internal','parameters':generate('internal').values})
        pump()
        self.assertFalse(c.run_button.get_sensitive())
        self.assertFalse(c.start());self.assertIsNone(c.result)
