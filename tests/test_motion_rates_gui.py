# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Display-backed RPM controls, clock integration and document regression checks."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import time
import unittest
from unittest.mock import patch
from math import pi
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, Gio, GLib
import app as module
import preview3d
from geometry import generate
from motion import build_plan, IDENTITY
from motion_controls import scale_rpm


def pump(seconds=.04):
    until = time.monotonic()+seconds
    context = GLib.MainContext.default()
    while time.monotonic() < until:
        while context.pending() and time.monotonic() < until:
            context.iteration(False)
        time.sleep(.002)


class MotionRateGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            raise unittest.SkipTest('GTK display required')
        cls.temp = TemporaryDirectory(prefix='ratiolab-motion-rate-tests-')
        cls.root = Path(cls.temp.name)
        cls.env = patch.dict(os.environ, dict(XDG_CONFIG_HOME=str(cls.root/'config'),
                                             XDG_DATA_HOME=str(cls.root/'data')))
        cls.env.start()
        cls.app = module.ReducerApp()
        cls.app.set_application_id(f'local.solidcraft.reducers.motionratetests.p{os.getpid()}')
        cls.app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        cls.app.register(None)
        cls.app.activate()
        pump(.2)
        assert cls.app.canvas.gl is not None and cls.app.canvas.failure is None

    @classmethod
    def tearDownClass(cls):
        for window in cls.app.get_windows():
            window.destroy()
        cls.env.stop()
        cls.temp.cleanup()

    def setUp(self):
        self.app.canvas.reset_motion()
        self.load('planetary', input_rpm=60)

    def load(self, family, **values):
        self.app.load_config_data(dict(format='solidcraft-riduttori/1', family=family,
                                       parameters=generate(family, values).values))
        pump(.03)

    def commit(self, value):
        self.app.motion_speed_text.set_text(str(value))
        self.app.motion_speed_text.emit('activate')

    def assert_nominal_angle(self, oracle, angle):
        c = self.app.canvas
        for i in range(len(c.design.parts)):
            for x, y in zip(c.motion_plan.matrix(i, c.motion_phase), oracle.matrix(i, angle)):
                self.assertAlmostEqual(x, y, places=8)

    def test_controlled_clock_old_and_new_rates_zero_and_stale_frame(self):
        a, c = self.app, self.app.canvas
        oracle = build_plan(a.design)
        mesh = c.scene
        with patch('preview3d.GLib.get_monotonic_time', return_value=1000000) as clock:
            c.set_motion_playing(True)
            c.on_motion_tick(c, SimpleNamespace(get_frame_time=lambda: 1250000))
            self.assert_nominal_angle(oracle, pi/2)
            clock.return_value = 1500000
            self.commit(120)
            self.assert_nominal_angle(oracle, pi)
            # An already queued older frame cannot rewind the event clock.
            c.on_motion_tick(c, SimpleNamespace(get_frame_time=lambda: 1400000))
            self.assert_nominal_angle(oracle, pi)
            c.on_motion_tick(c, SimpleNamespace(get_frame_time=lambda: 2000000))
            self.assert_nominal_angle(oracle, 3*pi)
            clock.return_value = 2250000
            self.commit(0)
            self.assert_nominal_angle(oracle, 4*pi)
            c.on_motion_tick(c, SimpleNamespace(get_frame_time=lambda: 3000000))
            self.assert_nominal_angle(oracle, 4*pi)
            clock.return_value = 3500000
            self.commit(90)
            c.on_motion_tick(c, SimpleNamespace(get_frame_time=lambda: 4000000))
            self.assert_nominal_angle(oracle, 5.5*pi)
            self.assertTrue(c.motion_playing)
            self.assertIs(c.scene, mesh)
        c.set_motion_playing(False)
        phase = c.motion_phase
        self.commit(18)
        self.assertFalse(c.motion_playing)
        self.assertEqual(c.motion_phase, phase)

    def test_slider_burst_reuses_mesh_buffers_and_bounds_recovery(self):
        a, c = self.app, self.app.canvas
        mesh = c.scene
        states = len(a.document.states)
        revision = a.document.revision
        c.set_motion_playing(True)
        pump(.05)
        with patch('app.generate', wraps=module.generate) as generation, \
             patch('preview3d.build_scene', wraps=preview3d.build_scene) as scene, \
             patch.object(c.gl, 'BufferData', wraps=c.gl.BufferData) as upload, \
             patch.object(a.project_store, 'checkpoint', wraps=a.project_store.checkpoint) as saves:
            a.begin_motion_rate_drag()
            for value in range(61, 91):
                a.motion_speed.set_value(scale_rpm(value))
            a.end_motion_rate_drag()
            pump(.3)
            self.assertEqual((generation.call_count, scene.call_count, upload.call_count), (0, 0, 0))
            self.assertLessEqual(saves.call_count, 2)
        self.assertIs(c.scene, mesh)
        self.assertTrue(c.motion_playing)
        self.assertGreaterEqual(a.document.revision-revision, 30)
        self.assertEqual(len(a.document.states), states+1)
        self.assertEqual(a.design.values['input_rpm'], 90)
        c.set_motion_playing(False)
        a.undo_project()
        self.assertEqual(a.motion_rpm, 60)
        a.redo_project()
        self.assertEqual(a.motion_rpm, 90)

    def test_drag_group_survives_slow_changes_and_ends_before_next_edit(self):
        a = self.app
        count = len(a.document.states)
        a.begin_motion_rate_drag()
        for value in (75, 60, 120):
            a.motion_speed.set_value(scale_rpm(value))
            pump(.75)
        a.end_motion_rate_drag()
        self.assertEqual(len(a.document.states), count+1)
        a.motion_speed.set_value(scale_rpm(150))
        self.assertEqual(len(a.document.states), count+2)
        a.undo_project()
        self.assertEqual(a.motion_rpm, 120)
        a.undo_project()
        self.assertEqual(a.motion_rpm, 60)

    def test_closing_speed_popover_ends_the_drag_history_group(self):
        a = self.app
        count = len(a.document.states)
        a.begin_motion_rate_drag()
        a.motion_speed.set_value(scale_rpm(80))
        a.motion_button.get_popover().emit('closed')
        a.motion_speed.set_value(scale_rpm(90))
        self.assertEqual(len(a.document.states), count+2)
        a.undo_project()
        self.assertEqual(a.motion_rpm, 80)
        a.undo_project()
        self.assertEqual(a.motion_rpm, 60)

    def test_save_interrupts_drag_and_preserves_saved_undo_position(self):
        a = self.app
        a.begin_motion_rate_drag()
        a.motion_speed.set_value(scale_rpm(75))
        a.save_project(path=self.root/'rpm-drag-save.json')
        self.assertFalse(a.document.dirty)
        a.motion_speed.set_value(scale_rpm(90))
        a.undo_project()
        self.assertEqual(a.motion_rpm, 75)
        self.assertFalse(a.document.dirty)

    def test_numeric_draft_keeps_committed_rate_through_refresh_and_invalid_commit(self):
        a, c = self.app, self.app.canvas
        c.set_motion_playing(True)
        for draft in ('-', '2.', '1e-', 'invalid', '00123,45000'):
            a.motion_speed_text.set_text(draft)
            self.assertTrue(a.refresh())
            self.assertEqual(a.design.values['input_rpm'], 60)
            self.assertEqual(a.motion_rpm, 60)
            self.assertEqual(a.motion_speed_text.get_text(), draft)
            self.assertTrue(c.motion_playing)
        self.commit('invalid')
        self.assertTrue(a.motion_input_invalid)
        self.assertTrue(c.motion_playing)
        self.assertEqual(a.motion_rpm, 60)
        self.commit('00123,45000')
        self.assertEqual(a.motion_rpm, 123.45)
        self.assertEqual(a.motion_speed_text.get_text(), '123.45')
        self.assertTrue(c.motion_playing)

    def test_save_confirms_valid_focused_draft_and_blocks_invalid_draft(self):
        a, c = self.app, self.app.canvas
        path = self.root/'rpm-focused-save.json'
        path.unlink(missing_ok=True)
        c.set_motion_playing(True)
        a.motion_speed_text.grab_focus()
        a.motion_speed_text.set_text('incomplete')
        a.save_project(path=path)
        self.assertFalse(path.exists())
        self.assertTrue(a.document.dirty)
        self.assertTrue(c.motion_playing)
        self.assertEqual(a.motion_rpm, 60)
        a.motion_speed_text.set_text('00123,45000')
        a.save_project(path=path)
        self.assertEqual(json.loads(path.read_text())['parameters']['input_rpm'], 123.45)
        self.assertFalse(a.document.dirty)
        self.assertTrue(c.motion_playing)

    def test_complete_draft_history_rebuild_and_recovery_keep_committed_speed(self):
        a = self.app
        a.motion_speed_text.set_text('00123,45678912345000')
        for snapshot in (a.project_snapshot(), a.document.current):
            self.assertEqual(snapshot['values']['planetary']['input_rpm'], 60)
            self.assertEqual(snapshot['raw']['planetary']['input_rpm'], '00123,45678912345000')
        a.make_fields()
        self.assertEqual(a.motion_rpm, 60)
        self.assertEqual(a.design.values['input_rpm'], 60)
        self.assertEqual(a.motion_speed_text.get_text(), '00123,45678912345000')
        a.undo_project()
        self.assertEqual(a.motion_rpm, 60)
        a.redo_project()
        self.assertEqual(a.motion_rpm, 60)
        self.assertEqual(a.motion_speed_text.get_text(), '00123,45678912345000')
        recovered = a.project_store.read_recovery(a.project_store.session, a.families)
        a.restore_project_snapshot(recovered.current)
        self.assertEqual(a.motion_rpm, 60)
        self.assertEqual(a.design.values['input_rpm'], 60)
        self.assertEqual(a.motion_speed_text.get_text(), '00123,45678912345000')
        a.motion_speed_text.emit('activate')
        self.assertEqual(a.motion_rpm, 123.45678912345)
        self.assertEqual(a.design.values['input_rpm'], 123.45678912345)

    def test_inspection_uses_nominal_plan_and_reset_clears_live_offsets(self):
        a, c = self.app, self.app.canvas
        for family in ('planetary', 'cycloidal', 'harmonic', 'differential'):
            with self.subTest(family=family):
                self.load(family, input_rpm=60)
                c.motion_enabled = True
                c.motion_phase = .8
                self.commit(0)
                live = c.motion_plan
                c.show_inspection(.37, (0, 1))
                nominal = build_plan(a.design)
                for i in range(len(a.design.parts)):
                    self.assertEqual(c.motion_plan.matrix(i, .37), nominal.matrix(i, .37))
                    self.assertEqual(c.motion_plan.deformation(i, .37), nominal.deformation(i, .37))
                c.clear_inspection()
                self.assertIs(c.motion_plan, live)
                c.reset_motion()
                self.assertFalse(c.motion_playing)
                self.assertFalse(c.motion_enabled)
                self.assertEqual(c.motion_phase, 0)
                for i in range(len(a.design.parts)):
                    self.assertEqual(c.motion_plan.matrix(i, 0), IDENTITY)


if __name__ == '__main__':
    unittest.main()
