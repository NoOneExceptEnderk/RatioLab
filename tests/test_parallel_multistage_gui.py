# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Real GTK/OpenGL acceptance for multistage controls and rejected layouts."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk, Gdk, Gio, GLib
import app as module
from geometry import generate


def wait_until(predicate, timeout=25):
    deadline=time.monotonic()+timeout
    context=GLib.MainContext.default()
    while time.monotonic()<deadline:
        if predicate():return
        # A running frame clock can keep the queue ready indefinitely. Observe
        # completion after each dispatch and yield CPU to the export worker.
        context.iteration(False)
        time.sleep(.005)
    raise AssertionError('Multistage GTK acceptance timed out')


class ParallelMultistageGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            raise unittest.SkipTest('GTK display required')
        cls.temporary=TemporaryDirectory(prefix='ratiolab-parallel-gui-')
        cls.root=Path(cls.temporary.name)
        cls.environment=patch.dict(os.environ,dict(XDG_CONFIG_HOME=str(cls.root/'config'),
            XDG_DATA_HOME=str(cls.root/'data'),APPDATA=str(cls.root/'roaming'),LOCALAPPDATA=str(cls.root/'local')))
        cls.environment.start()
        cls.app=module.ReducerApp()
        cls.app.set_application_id(f'local.solidcraft.reducers.paralleltests.p{os.getpid()}')
        cls.app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        cls.app.register(None)
        cls.app.activate()
        wait_until(lambda:cls.app.canvas.gl is not None or cls.app.canvas.failure)
        if cls.app.canvas.failure:raise AssertionError(cls.app.canvas.failure)

    @classmethod
    def tearDownClass(cls):
        cls.app.canvas.set_motion_playing(False)
        for window in cls.app.get_windows():window.destroy()
        cls.environment.stop()
        cls.temporary.cleanup()

    def setUp(self):
        a=self.app
        a.canvas.set_motion_playing(False)
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='parallel',
                                parameters=generate('parallel',dict(variant='two_stage')).values))
        a.output_dir=self.root/self._testMethodName
        a.output_dir.mkdir(exist_ok=True)
        wait_until(lambda:not a.pending and a.canvas.get_mapped())

    def test_separate_stage_and_tooth_controls_preserve_canonical_projects(self):
        a=self.app
        self.assertTrue(a.stage_box.get_visible())
        self.assertEqual(a.stage_selector.get_selected(),1)
        self.assertEqual(a.variant_selector.get_model().get_n_items(),3)
        self.assertEqual(a.variant_selector.get_selected_item().get_string(),'Spur')
        a.inputs['module2'].set_text('2.1234567890123')
        a.stage_selector.set_selected(2)
        self.assertEqual(a.design.values['variant'],'three_stage')
        self.assertEqual(a.collect_fields()['variant'],'three_stage')
        self.assertEqual(a.design.values['module2'],2.1234567890123)
        self.assertIn('pinion3',a.inputs)
        saved=a.config()
        self.assertNotIn('stage_count',saved['parameters'])
        self.assertNotIn('tooth_type',saved['parameters'])
        a.load_config_data(saved)
        self.assertEqual(a.config(),saved)
        self.assertEqual(a.stage_selector.get_selected(),2)
        a.stage_selector.set_selected(0)
        self.assertEqual(a.design.values['variant'],'spur')
        self.assertEqual(a.variant_selector.get_model().get_n_items(),3)
        a.variant_selector.set_selected(1)
        self.assertEqual(a.design.values['variant'],'helical')
        self.assertEqual(a.stage_selector.get_model().get_n_items(),3)
        a.variant_selector.set_selected(0)
        self.assertEqual(a.stage_selector.get_model().get_n_items(),3)
        a.stage_selector.set_selected(1)
        self.assertEqual(a.design.values['variant'],'two_stage')
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='internal',parameters=generate('internal',{}).values))
        self.assertFalse(a.stage_box.get_visible())
        self.assertFalse(a.stage_notice.get_visible())

    def test_helical_stage_tooth_choices_precise_angles_and_reverse_rpm(self):
        a=self.app
        a.variant_selector.set_selected(1)
        wait_until(lambda:not a.pending)
        self.assertEqual(a.design.values['variant'],'two_stage_helical')
        self.assertIn('helix2',a.inputs)
        self.assertEqual(a.input_geometry_groups['helix2'],'stage2')
        a.inputs['helix2'].set_text('-23.1234567890123')
        self.assertTrue(a.refresh())
        a.stage_selector.set_selected(2)
        wait_until(lambda:not a.pending)
        self.assertEqual(a.design.values['variant'],'three_stage_helical')
        self.assertEqual(a.design.values['helix2'],-23.1234567890123)
        self.assertIn('helix3',a.inputs)
        saved=a.config();a.load_config_data(saved)
        self.assertEqual(a.config(),saved)
        parts=list(a.design.parts)
        a.motion_speed_text.set_text('-31.1234567890123')
        a.motion_speed_text.emit('activate')
        wait_until(lambda:not a.pending)
        self.assertEqual(a.design.values['input_rpm'],-31.1234567890123)
        self.assertTrue(all(p.outer is q.outer for p,q in zip(parts,a.design.parts)))
        self.assertAlmostEqual(a.design.analysis['output']['rpm'],-31.1234567890123/-36)
        # The existing single-stage family accepts nonnegative RPM only.
        a.motion_speed_text.set_text('31.1234567890123')
        a.motion_speed_text.emit('activate')
        wait_until(lambda:not a.pending)
        a.stage_selector.set_selected(0)
        wait_until(lambda:not a.pending)
        self.assertEqual(a.design.values['variant'],'helical')

    def test_double_joined_separated_each_stage_groove_and_real_gl_capture(self):
        a=self.app
        a.rebuild_options({'variant':'three_stage_double','double_style':'separated'})
        wait_until(lambda:not a.pending)
        for key in ('helix','helix2','helix3','gap','gap2','gap3'):self.assertIn(key,a.inputs)
        a.inputs['gap2'].set_text('2.1234567890123')
        self.assertTrue(a.refresh())
        a.rebuild_options({'double_style':'joined'})
        wait_until(lambda:not a.pending)
        for key in ('gap','gap2','gap3'):
            self.assertNotIn(key,a.inputs)
            self.assertEqual(a.design.values[key],0)
        a.rebuild_options({'double_style':'separated'})
        wait_until(lambda:not a.pending)
        self.assertEqual(a.inputs['gap2'].get_text(),'2.1234567890123')
        self.assertEqual(a.design.values['gap2'],2.1234567890123)
        a.rebuild_options({'double_style':'joined'})
        a.inputs['layout_angle2'].set_text('60')
        a.inputs['layout_angle3'].set_text('-45')
        self.assertTrue(a.refresh())
        saved=a.config();a.load_config_data(saved)
        self.assertEqual(a.config(),saved)
        self.assertTrue(a.export_menu.get_sensitive())
        result=[]
        a.canvas.capture_png(lambda data,error:result.append((data,error)))
        wait_until(lambda:bool(result))
        self.assertIsNone(result[0][1]);self.assertTrue(result[0][0].startswith(b'\x89PNG'))
        evidence=os.environ.get('RATIOLAB_MULTISTAGE_EVIDENCE')
        if evidence:
            target=Path(evidence);target.mkdir(parents=True,exist_ok=True)
            (target/'native-three-stage-double.png').write_bytes(result[0][0])
            (target/'native-double-design.json').write_text(json.dumps(dict(values=a.design.values,analysis=a.design.analysis),indent=2))

    def test_stage_selection_builds_fields_and_signed_turns_on_assembly_page(self):
        a=self.app
        self.assertEqual(a.design.analysis['signed_ratio'],12)
        from result_controls import items
        self.assertEqual(items(a.design)[2],('Stage distances','80 / 100','mm','Stage 1 / 2'))
        self.assertIn('pinion2',a.inputs)
        self.assertNotIn('pinion3',a.inputs)
        self.assertEqual(a.input_pages['layout_angle2'],'assembly')
        self.assertEqual(a.input_geometry_groups['module2'],'stage2')
        def descendants(widget):
            yield widget
            child=widget.get_first_child()
            while child:
                yield from descendants(child)
                child=child.get_next_sibling()
        labels=[w.get_label() for w in descendants(a.sections['geometry'][1]) if isinstance(w,Gtk.Button)]
        extra=a.extra_geometry_expander.get_child()
        self.assertTrue(any(isinstance(w,Gtk.Button) and w.get_label()=='Restore model defaults' for w in descendants(extra)), labels)
        a.rebuild_options({'variant':'three_stage'})
        wait_until(lambda:not a.pending)
        self.assertIn('pinion3',a.inputs)
        self.assertIn('layout_angle3',a.inputs)
        self.assertEqual(a.design.analysis['signed_ratio'],-36)
        self.assertEqual(a.design.values['module3'],2.5)
        self.assertTrue(a.export_menu.get_sensitive())

    def test_precise_fold_save_recovery_and_invalid_layout_undo(self):
        a=self.app
        raw='73.1234567890123'
        a.inputs['layout_angle2'].set_text(raw)
        self.assertTrue(a.refresh())
        a.project_changed()
        path=a.output_dir/'folded.json'
        self.assertTrue(a.save_project(path=path))
        self.assertEqual(json.loads(path.read_text())['parameters']['layout_angle2'],73.1234567890123)
        accepted=a.canvas.design
        a.inputs['width2'].set_text('010.000000')
        a.inputs['layout_angle2'].set_text('180')
        self.assertFalse(a.refresh())
        a.project_changed()
        self.assertTrue(a.canvas.design is accepted, 'Rejected fold replaced the accepted preview')
        self.assertFalse(a.export_menu.get_sensitive())
        self.assertEqual(a.inputs['width2'].get_text(),'010.000000')
        self.assertEqual(a.inputs['layout_angle2'].get_text(),'180')
        recovery=a.project_store.read_recovery(a.project_store.session,a.families)
        self.assertEqual(recovery.current['raw']['parallel']['layout_angle2'],'180')
        a.undo_project()
        wait_until(lambda:not a.pending)
        self.assertTrue(a.canvas.motion_valid)
        self.assertEqual(a.inputs['layout_angle2'].get_text(),raw)
        a.redo_project()
        wait_until(lambda:not a.pending)
        self.assertFalse(a.export_menu.get_sensitive())

    def test_rate_only_updates_retain_gpu_geometry_and_compound_speeds(self):
        a=self.app
        a.inputs['layout_angle2'].set_text('90')
        self.assertTrue(a.refresh())
        parts=list(a.design.parts)
        a.motion_speed_text.set_text('-31.1234567890123')
        a.motion_speed_text.emit('activate')
        wait_until(lambda:not a.pending)
        self.assertEqual(a.design.values['input_rpm'],-31.1234567890123)
        self.assertEqual(a.design.analysis['kinematics']['shaft_rates_rpm'],[-31.1234567890123,10.374485596337433,-2.593621399084358])
        self.assertTrue(all(old.outer is new.outer for old,new in zip(parts,a.design.parts)))
        self.assertEqual(a.motion_speed_text.get_text(),'-31.1234567890123')

    def test_real_standalone_exports_contain_all_parts(self):
        a=self.app
        a.rebuild_options({'variant':'three_stage'})
        a.inputs['layout_angle2'].set_text('60')
        a.inputs['layout_angle3'].set_text('-45')
        self.assertTrue(a.refresh())
        with patch.object(module,'Client',side_effect=AssertionError('Standalone export connected to CAD')):
            for action in (a.export_step,a.export_stl,a.export_profiles,a.export):
                action()
                wait_until(lambda:not a.busy)
        step=next(a.output_dir.glob('*.step-export'))
        self.assertEqual(len(list((step/'step-parts').glob('*.step'))),12)
        package=next(a.output_dir.glob('*.package'))
        self.assertTrue(json.loads((package/'manifest.json').read_text())['complete'])
        self.assertTrue((package/'preview.png').read_bytes().startswith(b'\x89PNG'))
        evidence=os.environ.get('RATIOLAB_MULTISTAGE_EVIDENCE')
        if evidence:
            import shutil
            target=Path(evidence)
            target.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(package/'preview.png',target/'native-three-stage-preview.png')
            (target/'native-design.json').write_text(json.dumps(dict(values=a.design.values,analysis=a.design.analysis),indent=2))


if __name__=='__main__':unittest.main()
