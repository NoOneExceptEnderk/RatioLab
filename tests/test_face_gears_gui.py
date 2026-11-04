# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Actual GTK/OpenGL face selection, project edits and standalone export."""
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


class FaceGearGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check() or Gdk.Display.get_default() is None:raise unittest.SkipTest('GTK display required')
        cls.temporary=TemporaryDirectory(prefix='ratiolab-face-gui-');cls.root=Path(cls.temporary.name)
        cls.environment=patch.dict(os.environ,dict(XDG_CONFIG_HOME=str(cls.root/'config'),XDG_DATA_HOME=str(cls.root/'data'),
            APPDATA=str(cls.root/'roaming'),LOCALAPPDATA=str(cls.root/'local')))
        cls.environment.start();cls.app=module.ReducerApp()
        cls.app.set_application_id(f'local.ratiolab.facetests.p{os.getpid()}')
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
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='face',parameters=generate('face').values))
        a.output_dir=self.root/self._testMethodName;a.output_dir.mkdir()
        wait_until(lambda:not a.pending and a.canvas.get_mapped())

    def test_select_family_ports_result_cards_and_precise_save(self):
        a=self.app
        self.assertEqual(a.selector.get_selected_item().get_string(),'Face gear pair')
        self.assertEqual(a.design.values['variant'],'spur')
        self.assertFalse(a.stage_box.get_visible())
        self.assertEqual(len(a.design.parts),2)
        self.assertTrue(a.canvas.motion_plan.supported)
        a.canvas.set_motion_playing(True)
        self.assertTrue(a.canvas.motion_playing)
        before=a.canvas.motion_phase
        wait_until(lambda:a.canvas.motion_phase!=before)
        a.canvas.set_motion_playing(False)
        self.assertIn('output_bore',a.inputs)
        from result_controls import items
        self.assertEqual(items(a.design)[2][0],'Tooth-band width')
        a.inputs['radial_setting'].set_text('4.1234567890123');self.assertTrue(a.refresh())
        a.io_mode_buttons['reverse'].set_active(True)
        self.assertEqual(a.design.analysis['signed_ratio'],1/3)
        self.assertEqual(a.design.values['radial_setting'],4.1234567890123)
        path=a.output_dir/'face.config.json';self.assertTrue(a.save_project(path=path))
        config=json.loads(path.read_text());a.load_config_data(config)
        self.assertEqual(a.config(),config)
        self.assertEqual(a.design.parts[0].port['role'],'output')

    def test_invalid_draft_undo_and_speed_only_gpu_retention(self):
        a=self.app
        a.inputs['radial_setting'].set_text('4.1234567890123');self.assertTrue(a.refresh());a.project_changed()
        a.document.barrier()
        accepted=a.canvas.design
        a.inputs['radial_setting'].set_text('30');self.assertFalse(a.refresh());a.project_changed()
        self.assertIs(a.canvas.design,accepted)
        self.assertFalse(a.export_menu.get_sensitive())
        a.undo_project();wait_until(lambda:not a.pending)
        self.assertTrue(a.export_menu.get_sensitive())
        self.assertEqual(a.design.values['radial_setting'],4.1234567890123)
        parts=list(a.design.parts)
        a.motion_speed_text.set_text('-31.1234567890123');a.motion_speed_text.emit('activate')
        wait_until(lambda:not a.pending)
        self.assertAlmostEqual(a.design.parts[1].port['rpm'],-31.1234567890123/3)
        self.assertTrue(all(x.outer is y.outer for x,y in zip(parts,a.design.parts)))

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
        evidence=os.environ.get('RATIOLAB_FACE_EVIDENCE')
        if evidence:
            import shutil
            target=Path(evidence);target.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(package/'preview.png',target/'native-face-preview.png')

    def test_all_tooth_types_play_and_keep_precise_signed_helix(self):
        a=self.app
        for index,variant in enumerate(('spur','helical','double_helical')):
            a.variant_selector.set_selected(index);wait_until(lambda:not a.pending)
            self.assertEqual(a.design.values['variant'],variant)
            self.assertEqual('helix' in a.inputs,variant!='spur')
            self.assertEqual('gap' in a.inputs,variant=='double_helical' and a.design.values.get('double_style')=='separated')
            a.canvas.set_motion_playing(True);before=a.canvas.motion_phase
            wait_until(lambda:a.canvas.motion_phase!=before);a.canvas.set_motion_playing(False)
            if variant!='spur':
                a.inputs['helix'].set_text('-15.1234567890123');self.assertTrue(a.refresh())
                self.assertEqual(a.design.values['helix'],-15.1234567890123)
            if variant=='double_helical':self.assertEqual(len(a.design.analysis['face_gear']['band_axial_intervals_mm']),2)

    def test_offset_axes_all_types_precise_save_reverse_and_invalid_undo(self):
        a=self.app
        for index in range(3):
            a.variant_selector.set_selected(index);wait_until(lambda:not a.pending)
            for offset in ('-5.1234567890123','5.1234567890123'):
                a.inputs['offset'].set_text(offset);self.assertTrue(a.refresh())
                self.assertEqual(a.design.values['offset'],float(offset))
                self.assertEqual(a.design.parts[0].frame[0][1],float(offset))
                self.assertIsNone(a.design.analysis['face_gear']['axis_intersection_mm'])
                a.canvas.set_motion_playing(True);before=a.canvas.motion_phase
                wait_until(lambda:a.canvas.motion_phase!=before);a.canvas.set_motion_playing(False)
        from result_controls import items
        self.assertEqual(items(a.design)[2][0],'Shaft offset')
        a.io_mode_buttons['reverse'].set_active(True)
        self.assertEqual(a.design.parts[0].port['role'],'output')
        path=a.output_dir/'offset.config.json';self.assertTrue(a.save_project(path=path))
        a.load_config_data(json.loads(path.read_text()))
        self.assertEqual(a.design.values['offset'],5.1234567890123)
        a.project_changed();a.document.barrier();accepted=a.canvas.design
        a.inputs['offset'].set_text('50');self.assertFalse(a.refresh());a.project_changed()
        self.assertIs(a.canvas.design,accepted);self.assertFalse(a.export_menu.get_sensitive())
        a.undo_project();wait_until(lambda:not a.pending)
        self.assertTrue(a.export_menu.get_sensitive());self.assertEqual(a.design.values['offset'],5.1234567890123)

    def test_joined_separated_selector_precise_groove_history_and_legacy_project(self):
        a=self.app;a.variant_selector.set_selected(2);wait_until(lambda:not a.pending)
        self.assertEqual(a.design.values['double_style'],'joined');self.assertNotIn('gap',a.inputs)
        self.assertEqual(a.design.analysis['face_gear']['tooth_band_count'],1)
        a.face_style_selector.set_selected(1);wait_until(lambda:not a.pending)
        self.assertEqual(a.design.values['double_style'],'separated');self.assertIn('gap',a.inputs)
        a.inputs['gap'].set_text('2.1234567890123');self.assertTrue(a.refresh());a.project_changed();a.document.barrier()
        a.face_style_selector.set_selected(0);wait_until(lambda:not a.pending)
        self.assertEqual(a.design.values['gap'],0);self.assertNotIn('gap',a.inputs)
        a.undo_project();wait_until(lambda:not a.pending)
        self.assertEqual(a.design.values['double_style'],'separated')
        self.assertEqual(a.design.values['gap'],2.1234567890123)
        a.face_style_selector.set_selected(0);wait_until(lambda:not a.pending)
        a.face_style_selector.set_selected(1);wait_until(lambda:not a.pending)
        self.assertEqual(a.design.values['gap'],2.1234567890123)
        old=dict(a.config());old['parameters']=dict(old['parameters']);old['parameters'].pop('double_style')
        a.load_config_data(old);wait_until(lambda:not a.pending)
        self.assertEqual(a.design.values['double_style'],'separated')

    def test_joined_actual_opengl_closeup_and_export(self):
        from dataclasses import replace
        from math import pi
        a=self.app;a.variant_selector.set_selected(2);wait_until(lambda:not a.pending)
        self.assertEqual(a.design.values['double_style'],'joined')
        a.canvas.set_motion_playing(True);before=a.canvas.motion_phase
        wait_until(lambda:a.canvas.motion_phase!=before);a.canvas.set_motion_playing(False)
        a.canvas.motion_phase=0;a.canvas.motion_last=None
        with patch.object(module,'Client',side_effect=AssertionError('Standalone export connected to CAD')):
            a.export_step();wait_until(lambda:not a.busy)
        step=next(a.output_dir.glob('*.step-export'))
        self.assertEqual(len(list((step/'step-parts').glob('*.step'))),2)
        evidence=os.environ.get('RATIOLAB_FACE_EVIDENCE')
        if evidence:
            target=Path(evidence);target.mkdir(parents=True,exist_ok=True)
            def capture(name):
                result=[];a.canvas.capture_png(lambda data,error:result.append((data,error)))
                wait_until(lambda:bool(result));self.assertIsNone(result[0][1]);(target/name).write_bytes(result[0][0])
            capture('joined-overview.png')
            # Display-only close-up of the actual shared solid; no altered teeth.
            original=a.canvas.scene;camera=(a.canvas.yaw,a.canvas.tilt,a.canvas.zoom)
            a.canvas.scene=replace(original,center=(82.6,0,24.5),radius=12)
            a.canvas.yaw=-pi/2;a.canvas.tilt=-.6;a.canvas.zoom=1;a.canvas.isolated_indices=(1,)
            capture('joined-wheel-closeup.png')
            a.canvas.scene=original;a.canvas.yaw,a.canvas.tilt,a.canvas.zoom=camera;a.canvas.isolated_indices=None
            a.canvas.queue_render()



if __name__=='__main__':unittest.main()
