# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Display-backed refusal transactions, distinct from incomplete numeric drafts."""
import copy
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, Gio, GLib
import app as module
from geometry import generate
from backdrivability import BackdrivabilityError


def pump(duration=.04):
    until = time.monotonic()+duration
    context = GLib.MainContext.default()
    while time.monotonic() < until:
        while context.pending() and time.monotonic() < until:
            context.iteration(False)
        time.sleep(.002)


class BackdrivabilityGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            raise unittest.SkipTest('GTK display required')
        cls.temp = TemporaryDirectory(prefix='ratiolab-backdrivability-tests-')
        cls.root = Path(cls.temp.name)
        cls.env = patch.dict(os.environ, dict(XDG_CONFIG_HOME=str(cls.root/'config'),
                                             XDG_DATA_HOME=str(cls.root/'data')))
        cls.env.start()
        cls.app = module.ReducerApp()
        cls.app.set_application_id(f'local.solidcraft.reducers.backdrivetests.p{os.getpid()}')
        cls.app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        cls.app.register(None)
        cls.app.activate()
        pump(.15)
        assert cls.app.canvas.gl is not None and cls.app.canvas.failure is None

    @classmethod
    def tearDownClass(cls):
        for window in cls.app.get_windows():
            window.destroy()
        cls.env.stop()
        cls.temp.cleanup()

    def setUp(self):
        self.load(worm_static_friction=.2)

    def load(self, **parameters):
        self.app.load_config_data(dict(format='solidcraft-riduttori/1', family='worm',
                                       parameters=generate('worm', parameters).values))
        pump(.03)

    def state(self):
        a = self.app
        return (a.design, a.canvas.scene, a.document.token, copy.deepcopy(a.document.states),
                copy.deepcopy(a.document.clean), a.document.index, a.canvas.motion_phase,
                a.canvas.motion_plan, a.components.selected, a.canvas.selected_indices)

    def assert_preserved(self, before, *, equivalent_rate_copy=False):
        a = self.app
        if equivalent_rate_copy:
            self.assertEqual(a.design.values, before[0].values)
            self.assertEqual(a.design.analysis, before[0].analysis)
        else:
            self.assertTrue(a.design is before[0], 'Last evaluated design object changed')
        self.assertTrue(a.canvas.scene is before[1], 'Last scene object changed')
        self.assertEqual(a.document.token, before[2])
        self.assertEqual(a.document.states, before[3])
        self.assertEqual(a.document.clean, before[4])
        self.assertEqual(a.document.index, before[5])
        self.assertEqual(a.canvas.motion_phase, before[6])
        if equivalent_rate_copy:
            for index in range(len(a.design.parts)):
                self.assertEqual(a.canvas.motion_plan.matrix(index, before[6]), before[7].matrix(index, before[6]))
        else:
            self.assertTrue(a.canvas.motion_plan is before[7])
        self.assertEqual(a.components.selected, before[8])
        self.assertEqual(a.canvas.selected_indices, before[9])

    def test_forbidden_member_selection_restores_selector_and_document(self):
        a = self.app
        a.components.select((0,), sync=False)
        a.canvas.motion_phase = .37
        before = self.state()
        a.io_mode_buttons['reverse'].set_active(True)
        self.assert_preserved(before)
        self.assertTrue(a.io_mode_buttons['forward'].get_active())
        self.assertFalse(a.io_mode_buttons['reverse'].get_active())
        self.assertIn('limiting value', a.io_policy_error.get_text())
        self.assertTrue(a.io_policy_error.get_visible())
        self.assertTrue(a.export_menu.get_sensitive())

    def test_coefficient_apply_invalid_and_forbidden_preserve_valid_reverse(self):
        self.load(io_scheme='reverse', worm_static_friction=.01)
        a = self.app
        before = self.state()
        for coefficient in ('0.2', 'nan', 'inf', '-1', 'unknown'):
            a.io_friction_entry.set_text(coefficient)
            a.io_friction_apply.emit('clicked')
            self.assert_preserved(before)
            self.assertEqual(a.option_values['worm_static_friction'], .01)
            self.assertTrue(a.io_policy_error.get_visible())

    def test_geometric_edit_crossing_limit_is_refused_before_history(self):
        self.load(io_scheme='reverse', worm_static_friction=.05)
        a = self.app
        before = self.state()
        a.inputs['diameter'].set_text('60')
        self.assert_preserved(before)
        self.assertEqual(float(a.inputs['diameter'].get_text()), 20)
        self.assertIn('limiting value', a.io_policy_error.get_text())
        self.assertTrue(a.refresh())
        self.assertEqual(a.design.values['diameter'], 20)

    def test_rejected_dimension_restores_prior_exact_raw_snapshot(self):
        self.load(io_scheme='reverse', worm_static_friction=.05)
        a = self.app
        a.inputs['diameter'].set_text('20.000')
        a.refresh()
        a.project_changed()
        snapshot = a.project_snapshot()
        before = self.state()
        a.inputs['diameter'].set_text('60')
        self.assert_preserved(before)
        self.assertEqual(a.inputs['diameter'].get_text(), '20.000')
        self.assertEqual(a.project_snapshot(), snapshot)

    def test_unrelated_incomplete_draft_cannot_hide_forbidden_member_request(self):
        a = self.app
        # Preserve a pre-existing incomplete field without running its pending
        # ordinary-error refresh: the new member attempt must not replace it.
        a.inputs['width'].set_text('-')
        before = self.state()
        raw = copy.deepcopy(a.raw_edits)
        a.io_mode_buttons['reverse'].set_active(True)
        self.assert_preserved(before)
        self.assertEqual(a.inputs['width'].get_text(), '-')
        self.assertEqual(a.raw_edits, raw)
        self.assertTrue(a.io_mode_buttons['forward'].get_active())
        self.assertIn('limiting value', a.io_policy_error.get_text())

    def test_programmatic_batch_restores_physical_evidence_preserves_other_drafts(self):
        a = self.app
        before = self.state()
        a.building = True
        a.inputs['module'].set_text('1')
        a.inputs['diameter'].set_text('60')
        a.inputs['width'].set_text('-')
        a.option_values.update(io_scheme='reverse', worm_static_friction=.3)
        a.raw_edits['worm']['width'] = '-'
        a.building = False
        self.assertFalse(a.refresh())
        self.assert_preserved(before)
        self.assertEqual(float(a.inputs['module'].get_text()), 2)
        self.assertEqual(float(a.inputs['diameter'].get_text()), 20)
        self.assertEqual(a.inputs['width'].get_text(), '-')
        self.assertEqual(a.raw_edits['worm']['width'], '-')
        self.assertEqual(a.option_values['worm_static_friction'], .2)
        self.assertEqual(a.option_values['io_scheme'], 'forward')

    def test_unapplied_coefficient_and_unchanged_numeric_text_survive_batch_refusal(self):
        self.load(io_scheme='reverse', worm_static_friction=.05)
        a = self.app
        before = self.state()
        a.io_friction_entry.set_text('0.04')
        a.building = True
        a.inputs['module'].set_text('2.000')
        a.inputs['diameter'].set_text('60')
        a.building = False
        self.assertFalse(a.refresh())
        self.assert_preserved(before)
        self.assertEqual(a.io_friction_entry.get_text(), '0.04')
        self.assertEqual(a.inputs['module'].get_text(), '2.000')
        self.assertEqual(float(a.inputs['diameter'].get_text()), 20)
        self.assertEqual(a.option_values['worm_static_friction'], .05)

    def test_slider_with_pending_forbidden_physical_batch_restores_whole_snapshot(self):
        from motion_controls import scale_rpm
        self.load(io_scheme='reverse', worm_static_friction=.05)
        a = self.app
        snapshot = a.project_snapshot()
        before = self.state()
        a.building = True
        a.inputs['diameter'].set_text('60')
        a.building = False
        import preview3d
        with patch('app.generate', wraps=module.generate) as generation, \
             patch('preview3d.build_scene', wraps=preview3d.build_scene) as scene, \
             patch.object(a.canvas.gl, 'BufferData', wraps=a.canvas.gl.BufferData) as upload:
            a.motion_speed.set_value(scale_rpm(123))
            self.assertEqual(generation.call_count, 0)
            self.assertEqual(scene.call_count, 0)
            self.assertEqual(upload.call_count, 0)
        self.assert_preserved(before, equivalent_rate_copy=True)
        self.assertEqual(a.motion_rpm, 1500)
        self.assertEqual(float(a.motion_speed_text.get_text()), 1500)
        self.assertEqual(a.project_snapshot(), snapshot)

    def test_persistent_empty_physical_field_retains_normal_invalid_draft_workflow(self):
        a = self.app
        a.inputs['diameter'].set_text('')
        # Allow normal deferred replay and auto-refresh to run even when a
        # layout/render callback consumes the former fixed pump duration.
        deadline = time.monotonic()+2
        context = GLib.MainContext.default()
        while not (a.document.current.get('raw', {}).get('worm', {}).get('diameter') == ''
                   and a.design is None
                   and 'Complete the numeric value' in a.parameter_error.get_text()):
            if time.monotonic() >= deadline:
                break
            if context.pending():
                context.iteration(False)
            else:
                time.sleep(.002)
        self.assertEqual(a.document.current['raw']['worm']['diameter'], '')
        self.assertTrue(a.design is None, 'Empty physical input retained a valid design')
        self.assertIn('Complete the numeric value', a.parameter_error.get_text())

    def test_empty_physical_edit_is_recorded_before_continuously_ready_layout_work(self):
        a = self.app
        # GTK layout/redraw work has higher priority than ordinary idle work.
        # Keep such work ready deterministically instead of depending on how
        # quickly this machine paints a frame during a fixed-duration pump.
        ready = GLib.idle_add(lambda: GLib.SOURCE_CONTINUE,
                              priority=GLib.PRIORITY_HIGH_IDLE)
        try:
            a.inputs['diameter'].set_text('')
            context = GLib.MainContext.default()
            for _ in range(16):
                context.iteration(False)
            self.assertEqual(a.document.current['raw']['worm']['diameter'], '')
            self.assertFalse(a.refresh())
            self.assertIsNone(a.design)
        finally:
            GLib.source_remove(ready)

    def test_empty_replacement_valid_value_never_records_intermediate_empty(self):
        a = self.app
        a.inputs['diameter'].set_text('25')
        pump(.15)
        self.assertEqual(a.design.values['diameter'], 25)
        for state in a.document.states:
            self.assertNotEqual(state.get('raw', {}).get('worm', {}).get('diameter'), '')

    def test_empty_replay_is_stale_after_rebuild_or_family_replacement(self):
        a = self.app
        a.inputs['diameter'].set_text('')
        a.make_fields()
        token = a.document.token
        pump(.1)
        self.assertIsNotNone(a.design)
        self.assertEqual(a.document.token, token)
        a.inputs['diameter'].set_text('')
        a.load_config_data(dict(format='solidcraft-riduttori/1', family='spur', parameters={}))
        token = a.document.token
        pump(.1)
        self.assertEqual(a.design.family, 'spur')
        self.assertEqual(a.document.token, token)

    def test_existing_incomplete_rpm_draft_survives_physical_refusal(self):
        self.load(io_scheme='reverse', worm_static_friction=.05)
        a = self.app
        a.motion_speed_text.set_text('-')
        a.motion_speed_text.emit('activate')
        snapshot = a.project_snapshot()
        before = self.state()
        a.building = True
        a.inputs['diameter'].set_text('60')
        a.building = False
        self.assertFalse(a.refresh())
        self.assert_preserved(before)
        self.assertEqual(a.motion_speed_text.get_text(), '-')
        self.assertTrue(a.motion_input_invalid)
        self.assertEqual(a.project_snapshot(), snapshot)

    def test_typing_rpm_cannot_record_pending_forbidden_physical_batch(self):
        from geometry import validate
        self.load(io_scheme='reverse', worm_static_friction=.05)
        a = self.app
        a.building = True
        a.inputs['diameter'].set_text('60')
        a.building = False
        a.motion_speed_text.set_text('123')
        a.motion_speed_text.emit('activate')
        # The physical request is refused first. The subsequent completed RPM
        # edit is an independent valid operating-rate change on the restored pair.
        self.assertEqual(a.design.values['diameter'], 20)
        self.assertEqual(a.design.values['input_rpm'], 123)
        self.assertEqual(a.motion_rpm, 123)
        self.assertEqual(a.document.current['values']['worm']['input_rpm'], 123)
        for state in a.document.states:
            validate('worm', state['values']['worm'])

    def test_invalid_config_is_rejected_before_project_replacement(self):
        a = self.app
        before = self.state()
        with self.assertRaises(BackdrivabilityError):
            a.load_config_data(dict(format='solidcraft-riduttori/1', family='worm',
                                    parameters=dict(io_scheme='reverse', worm_static_friction=.2)))
        self.assert_preserved(before)

    def test_explicit_clear_is_indeterminate_and_saved_as_unknown(self):
        a = self.app
        a.io_friction_clear.emit('clicked')
        self.assertNotIn('worm_static_friction', a.config()['parameters'])
        a.io_mode_buttons['reverse'].set_active(True)
        self.assertEqual(a.design.analysis['backdrivability']['status'], 'indeterminate')
        self.assertIn('ideal kinematics only', a.io_policy_note.get_text())
        self.assertNotIn('worm_static_friction', a.option_values)


if __name__ == '__main__':
    unittest.main()
