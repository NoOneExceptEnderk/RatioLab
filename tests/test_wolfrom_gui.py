# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Display-backed Wolfrom document, motion and real export acceptance."""
from copy import deepcopy
import json
from math import pi
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, Gio, GLib
import app as module
from geometry import generate
from gui_workflow import CATALOG
from interference import expected_interface
from motion import build_plan


def pump_until(predicate, timeout=25):
    deadline = time.monotonic() + timeout
    context = GLib.MainContext.default()
    while time.monotonic() < deadline:
        while context.pending() and time.monotonic() < deadline:
            context.iteration(False)
        if predicate():
            return
        time.sleep(.005)
    raise AssertionError('Timed out waiting for the Wolfrom GUI')


def widgets(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from widgets(child)
        child = child.get_next_sibling()


class WolfromGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            raise unittest.SkipTest('GTK display required')
        cls.temporary = TemporaryDirectory(prefix='ratiolab-wolfrom-gui-')
        cls.root = Path(cls.temporary.name)
        cls.environment = patch.dict(os.environ, dict(
            XDG_CONFIG_HOME=str(cls.root/'config'), XDG_DATA_HOME=str(cls.root/'data'),
            APPDATA=str(cls.root/'roaming'), LOCALAPPDATA=str(cls.root/'local')))
        cls.environment.start()
        cls.app = module.ReducerApp()
        cls.app.set_application_id(f'local.solidcraft.reducers.wolfromtests.p{os.getpid()}')
        cls.app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        cls.app.register(None)
        cls.app.activate()
        pump_until(lambda: cls.app.canvas.gl is not None or cls.app.canvas.failure)
        if cls.app.canvas.failure:
            raise AssertionError(cls.app.canvas.failure)

    @classmethod
    def tearDownClass(cls):
        for window in cls.app.get_windows():
            window.destroy()
        cls.environment.stop()
        cls.temporary.cleanup()

    def setUp(self):
        a = self.app
        a.canvas.set_motion_playing(False)
        a.load_config_data(dict(format='solidcraft-riduttori/1', family='wolfrom',
                                parameters=generate('wolfrom').values))
        a.output_dir = self.root/self._testMethodName
        a.output_dir.mkdir(exist_ok=True)
        pump_until(lambda: not a.pending and a.canvas.get_mapped())
        self.assertEqual(a.design.family, 'wolfrom')

    def commit_rpm(self, text):
        self.app.motion_speed_text.set_text(text)
        self.app.motion_speed_text.emit('activate')

    def matrices(self):
        c = self.app.canvas
        return [c.motion_plan.matrix(i, c.motion_phase) for i in range(len(c.design.parts))]

    def assert_matrices(self, expected):
        for actual, wanted in zip(self.matrices(), expected):
            for a, b in zip(actual, wanted):
                self.assertAlmostEqual(a, b, places=9)

    def test_catalog_fixed_roles_derived_dimensions_and_member_rates(self):
        a = self.app
        self.assertEqual(CATALOG['wolfrom'][0], 'Wolfrom / 3K reducer')
        self.assertEqual(a.io_role_selectors, {})
        self.assertEqual(a.io_mode_buttons, {})
        self.assertEqual(a.io_selectors, {})
        self.assertFalse(any(isinstance(w, Gtk.DropDown) for w in widgets(a.io_box)))
        self.assertEqual(a.option_values['io_scheme'], 'sun_output_ring')
        self.assertEqual(a.geometry_derived['planets'].get_text(), '162')
        self.assertAlmostEqual(float(a.geometry_derived['module2'].get_text()), a.design.analysis['wolfrom']['module2_mm'], places=12)
        self.assertIn(repr(a.design.analysis['wolfrom']['module2_mm']), a.geometry_derived['module2'].get_tooltip_text())
        self.assertNotIn('module2', a.inputs)
        self.assertNotIn('fixed_ring', a.inputs)
        result = a.io_results[0][1].get_text()
        for text in ('Sun input: +600', 'Common carrier: +60', 'Compound spin: -75', 'Output ring: +1', '+Z'):
            self.assertIn(text, result)
        self.assertIn('−100,000 to +100,000', a.motion_speed.get_tooltip_text())
        self.assertIn('+Z', a.motion_speed.get_tooltip_text())
        self.assertTrue(a.export_menu.get_sensitive())
        self.assertTrue(a.canvas.motion_valid)
        self.assertTrue(a.motion_play.get_sensitive())
        self.assertEqual(len(a.document.states), 1)
        self.assertFalse(a.document.dirty)

    def test_reverse_and_zero_rates_reuse_scene_and_gpu_preserving_continuity(self):
        a, c = self.app, self.app.canvas
        scene, parts = c.scene, a.design.parts
        oracle = build_plan(a.design)
        with patch('preview3d.GLib.get_monotonic_time', return_value=1000000) as clock:
            c.set_motion_playing(True)
            c.on_motion_tick(c, SimpleNamespace(get_frame_time=lambda: 1100000))
            # 600 rpm for 0.1 s is one input revolution.
            expected = [oracle.matrix(i, 2*pi) for i in range(len(parts))]
            self.assert_matrices(expected)
            clock.return_value = 1100000
            with patch('app.generate', wraps=module.generate) as generation, \
                 patch.object(c.gl, 'BufferData', wraps=c.gl.BufferData) as upload:
                self.commit_rpm('-00600.00000')
                self.assert_matrices(expected)
                c.on_motion_tick(c, SimpleNamespace(get_frame_time=lambda: 1150000))
                self.assert_matrices([oracle.matrix(i, pi) for i in range(len(parts))])
                clock.return_value = 1150000
                self.commit_rpm('0.0000')
                stopped = self.matrices()
                c.on_motion_tick(c, SimpleNamespace(get_frame_time=lambda: 1800000))
                self.assert_matrices(stopped)
                self.assertEqual((generation.call_count, upload.call_count), (0, 0))
            self.assertIs(c.scene, scene)
            self.assertTrue(all(new.outer is old.outer for new, old in zip(a.design.parts, parts)))
            self.assertTrue(all(rate == 0 for rate in a.design.analysis['kinematics']['rates_rpm'].values()))
            self.assertEqual(a.motion_speed_text.get_text(), '0')
            self.assertTrue(c.motion_playing)
        c.set_motion_playing(False)

    def test_exact_parameters_save_roundtrip_and_raw_recovery(self):
        a = self.app
        raw = {'width2': '006.125000000', 'layer_gap': '002.5000', 'input_torque': '001.234567891234'}
        for key, text in raw.items():
            a.inputs[key].set_text(text)
        self.commit_rpm('-00600.00000')
        self.assertTrue(a.refresh())
        for key, text in raw.items():
            self.assertEqual(a.inputs[key].get_text(), text)
        expected = deepcopy(a.design.values)
        a.project_changed()
        recovered = a.project_store.read_recovery(a.project_store.session, a.families)
        self.assertEqual(recovered.current['raw']['wolfrom']['width2'], raw['width2'])
        a.restore_project_snapshot(recovered.current)
        for key, text in raw.items():
            self.assertEqual(a.inputs[key].get_text(), text)
        self.assertEqual(a.motion_speed_text.get_text(), '-00600.00000')
        self.assertEqual(a.config()['parameters'], expected)
        path = a.output_dir/'precise.json'
        self.assertTrue(a.save_project(path=path))
        saved = json.loads(path.read_text())
        self.assertEqual(saved['parameters'], expected)
        a.load_config_data(saved, path)
        self.assertEqual(a.design.values, expected)
        self.assertFalse(a.document.dirty)
        self.assertTrue(a.export_menu.get_sensitive())

    def test_singular_profile_and_phase_drafts_keep_accepted_design_and_repair(self):
        a = self.app
        for key, text, original in (('planet2', '060', '059'), ('pressure', '14.5000', '20.0000'), ('planets', '04', '03')):
            with self.subTest(key=key):
                a.inputs['width2'].set_text('006.0000')
                self.assertTrue(a.refresh())
                accepted, scene = a.design, a.canvas.scene
                accepted_values = deepcopy(accepted.values)
                a.inputs[key].set_text(text)
                self.assertFalse(a.refresh())
                self.assertIs(a.design, accepted)
                self.assertIs(a.canvas.design, accepted)
                self.assertIs(a.canvas.scene, scene)
                self.assertEqual(accepted.values, accepted_values)
                self.assertEqual(a.inputs[key].get_text(), text)
                self.assertEqual(a.inputs['width2'].get_text(), '006.0000')
                self.assertFalse(a.export_menu.get_sensitive())
                self.assertFalse(a.motion_play.get_sensitive())
                self.assertFalse(a.canvas.motion_valid)
                self.assertIn('Last valid model', a.empty.get_text())
                a.project_changed()
                recovery = a.project_store.read_recovery(a.project_store.session, a.families)
                self.assertEqual(recovery.current['raw']['wolfrom'][key], text)
                with self.assertRaises(ValueError):
                    a.config()
                with patch.object(a, 'background') as background:
                    a.export_step()
                    a.export_stl()
                    a.export_profiles()
                    a.export()
                    background.assert_not_called()
                a.inputs[key].set_text(original)
                self.assertTrue(a.refresh())
                self.assertEqual(a.inputs[key].get_text(), original)
                self.assertEqual(a.inputs['width2'].get_text(), '006.0000')
                self.assertTrue(a.export_menu.get_sensitive())
                self.assertTrue(a.canvas.motion_valid)

    def test_invalid_project_load_preserves_current_document_and_drafts(self):
        a = self.app
        a.inputs['layer_gap'].set_text('002.5000')
        self.assertTrue(a.refresh())
        a.project_changed()
        current, document, design = a.project_snapshot(), a.document, a.design
        states, token = deepcopy(document.states), document.token
        with self.assertRaises(ValueError):
            a.load_config_data(dict(format='solidcraft-riduttori/1', family='wolfrom', parameters=dict(a.design.values, planet2=60)))
        self.assertIs(a.design, design)
        self.assertIs(a.document, document)
        self.assertEqual(a.project_snapshot(), current)
        self.assertEqual(a.document.states, states)
        self.assertEqual(a.document.token, token)
        self.assertTrue(a.export_menu.get_sensitive())

    def test_undo_redo_invalid_draft_recovery_and_real_exports(self):
        a = self.app
        a.inputs['width2'].set_text('007.25000')
        self.assertTrue(a.refresh())
        a.project_changed()
        a.document.barrier()
        a.inputs['planet2'].set_text('060')
        self.assertFalse(a.refresh())
        a.project_changed()
        a.undo_project()
        self.assertTrue(a.canvas.motion_valid)
        self.assertEqual(a.inputs['width2'].get_text(), '007.25000')
        self.assertEqual(a.design.values['planet2'], 59)
        a.redo_project()
        self.assertFalse(a.canvas.motion_valid)
        self.assertEqual(a.inputs['planet2'].get_text(), '060')
        a.inputs['planet2'].set_text('059')
        self.assertTrue(a.refresh())
        self.assertTrue(a.export_menu.get_sensitive())
        with patch.object(module, 'Client', side_effect=AssertionError('Standalone export connected to CAD')):
            for action in (a.export_step, a.export_stl, a.export_profiles, a.export):
                action()
                pump_until(lambda: not a.busy)
        steps = list(a.output_dir.glob('*.step-export'))
        profiles = list(a.output_dir.glob('*.profiles-export'))
        self.assertEqual(len(steps), 1)
        self.assertEqual(len(list((steps[0]/'step-parts').glob('*.step'))), 18)
        self.assertTrue((steps[0]/'assembly.step').is_file())
        self.assertEqual(len(profiles), 1)
        self.assertEqual(len(json.loads((profiles[0]/'profiles.json').read_text())['components']), 18)
        self.assertTrue(list(a.output_dir.glob('*.stl')))
        package = next(a.output_dir.glob('*.package'))
        self.assertTrue(json.loads((package/'manifest.json').read_text())['complete'])
        self.assertTrue((package/'preview.png').read_bytes().startswith(b'\x89PNG\r\n\x1a\n'))
        self.assertTrue((package/'assembly.step').is_file())
        self.assertTrue(a.export_menu.get_sensitive())

    def test_expected_interface_labels_only_actual_meshes_and_rigid_groups(self):
        d = self.app.design
        indices = {p.name: i for i, p in enumerate(d.parts)}
        label = lambda a, b: expected_interface(d, indices[a], indices[b])
        self.assertIn('Wolfrom mesh', label('Sun_input', 'Compound_1_rim1'))
        self.assertIn('Wolfrom mesh', label('Ring_output', 'Compound_1_rim2'))
        self.assertEqual(label('Ring_output', 'Compound_1_rim1'), '')
        self.assertIn('Same rigid Wolfrom body', label('Compound_1_rim1', 'Compound_1_rim2'))
        self.assertEqual(label('Compound_1_rim1', 'Compound_2_rim1'), '')


if __name__ == '__main__':
    unittest.main()
