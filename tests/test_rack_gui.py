# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Actual GTK/OpenGL rack selection, project edits and standalone export."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk,Gio
import app as module
from geometry import generate
from test_parallel_multistage_gui import wait_until


class RackGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check() or Gdk.Display.get_default() is None:raise unittest.SkipTest('GTK display required')
        cls.temporary=TemporaryDirectory(prefix='ratiolab-rack-gui-');cls.root=Path(cls.temporary.name)
        cls.environment=patch.dict(os.environ,dict(XDG_CONFIG_HOME=str(cls.root/'config'),XDG_DATA_HOME=str(cls.root/'data'),
            APPDATA=str(cls.root/'roaming'),LOCALAPPDATA=str(cls.root/'local')))
        cls.environment.start();cls.app=module.ReducerApp()
        cls.app.set_application_id(f'local.ratiolab.racktests.p{os.getpid()}')
        cls.app.set_flags(Gio.ApplicationFlags.NON_UNIQUE);cls.app.register(None);cls.app.activate()
        wait_until(lambda:cls.app.canvas.gl is not None or cls.app.canvas.failure)
        if cls.app.canvas.failure:raise AssertionError(cls.app.canvas.failure)

    @classmethod
    def tearDownClass(cls):
        cls.app.canvas.set_motion_playing(False)
        for window in cls.app.get_windows():window.destroy()
        cls.environment.stop();cls.temporary.cleanup()

    def setUp(self):
        a=self.app;a.canvas.set_motion_playing(False)
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='rack',parameters=generate('rack').values))
        a.output_dir=self.root/self._testMethodName;a.output_dir.mkdir()
        wait_until(lambda:not a.pending and a.canvas.get_mapped())

    def test_selection_types_exact_project_and_play_to_end_then_reverse(self):
        a=self.app
        self.assertEqual(a.selector.get_selected_item().get_string(),'Rack and pinion')
        self.assertFalse(a.stage_box.get_visible())
        self.assertEqual(len(a.design.parts),2)
        from result_controls import items
        self.assertEqual(items(a.design)[0][0],'Travel per revolution')
        for index,variant in enumerate(('spur','helical','double')):
            a.variant_selector.set_selected(index);wait_until(lambda:not a.pending)
            self.assertEqual(a.design.values['variant'],variant)
            self.assertEqual('helix' in a.inputs,variant!='spur')
            a.canvas.set_motion_playing(True)
            before=a.canvas.motion_phase;wait_until(lambda:a.canvas.motion_phase!=before)
            # The first rendered frame may arrive after the finite stroke has
            # already completed. Both a real frame and this explicit advance
            # must stop at the same physical endpoint; a stopped clock is None.
            if a.canvas.motion_playing:
                a.canvas.advance_motion(a.canvas.motion_last+100)
            self.assertFalse(a.canvas.motion_playing)
            self.assertAlmostEqual(a.canvas.motion_phase,a.canvas.motion_plan.phase_limits[1])
            old=a.canvas.motion_plan.matrix(1,a.canvas.motion_phase)
            a.motion_speed_text.set_text('-12');a.motion_speed_text.emit('activate')
            wait_until(lambda:not a.pending)
            for x,y in zip(old,a.canvas.motion_plan.matrix(1,a.canvas.motion_phase)):self.assertAlmostEqual(x,y,places=10)
            a.canvas.set_motion_playing(True)
            a.canvas.advance_motion(a.canvas.motion_last+.05)
            self.assertLess(a.canvas.motion_plan.matrix(1,a.canvas.motion_phase)[12],old[12])
            a.canvas.set_motion_playing(False)
            a.canvas.reset_motion()
            a.motion_speed_text.set_text('12');a.motion_speed_text.emit('activate')
            wait_until(lambda:not a.pending)
        a.rebuild_options({'double_style':'joined'});wait_until(lambda:not a.pending)
        self.assertNotIn('gap',a.inputs);self.assertEqual(a.design.values['gap'],0)
        a.rebuild_options({'double_style':'separated'});wait_until(lambda:not a.pending)
        self.assertIn('gap',a.inputs)
        a.inputs['base'].set_text('6.1234567890123');self.assertTrue(a.refresh())
        path=a.output_dir/'rack.config.json';self.assertTrue(a.save_project(path=path))
        config=json.loads(path.read_text());a.load_config_data(config)
        self.assertEqual(a.config(),config);self.assertEqual(a.design.values['base'],6.1234567890123)

    def test_invalid_draft_undo_and_rpm_surface_retention(self):
        a=self.app
        a.inputs['base'].set_text('7.1234567890123');self.assertTrue(a.refresh());a.project_changed();a.document.barrier()
        accepted=a.canvas.design
        a.inputs['pinion'].set_text('12');self.assertFalse(a.refresh());a.project_changed()
        self.assertIs(a.canvas.design,accepted);self.assertFalse(a.export_menu.get_sensitive())
        a.undo_project();wait_until(lambda:not a.pending)
        self.assertTrue(a.export_menu.get_sensitive());self.assertEqual(a.design.values['base'],7.1234567890123)
        parts=list(a.design.parts)
        a.motion_speed_text.set_text('-31.1234567890123');a.motion_speed_text.emit('activate')
        wait_until(lambda:not a.pending)
        self.assertLess(a.design.analysis['linear_output']['velocity_mm_s'],0)
        self.assertTrue(all(x.stations is y.stations for x,y in zip(parts,a.design.parts)))

    def test_real_standalone_step_and_package_keep_two_parts(self):
        a=self.app
        with patch.object(module,'Client',side_effect=AssertionError('Standalone export connected to CAD')):
            for index in range(3):
                a.variant_selector.set_selected(index);wait_until(lambda:not a.pending)
                a.export_step();wait_until(lambda:not a.busy)
            a.export();wait_until(lambda:not a.busy)
        step=next(a.output_dir.glob('*.step-export'))
        self.assertEqual(len(list((step/'step-parts').glob('*.step'))),2)
        package=next(a.output_dir.glob('*.package'))
        self.assertTrue(json.loads((package/'manifest.json').read_text())['complete'])
        self.assertTrue((package/'preview.png').read_bytes().startswith(b'\x89PNG'))
        evidence=os.environ.get('RATIOLAB_RACK_EVIDENCE')
        if evidence:
            import shutil
            target=Path(evidence);target.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(package/'preview.png',target/'native-rack-preview.png')



if __name__=='__main__':unittest.main()
