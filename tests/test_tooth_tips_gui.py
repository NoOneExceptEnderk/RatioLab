# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Actual GTK/OpenGL tip controls, exact project history and real exports."""
from pathlib import Path
import json
import unittest
import cad_export
import stl_export
from geometry import generate
import test_workspace_theme_preferences as fixtures
from test_interference_gui import wait_until


class ToothTipGuiTests(unittest.TestCase):
    setUpClass = fixtures.WorkspaceThemePreferencesTests.__dict__['setUpClass']
    setUp = fixtures.WorkspaceThemePreferencesTests.setUp
    close_apps = fixtures.WorkspaceThemePreferencesTests.close_apps
    launch = fixtures.WorkspaceThemePreferencesTests.launch

    def load(self,app,family,values=None,path=None):
        app.canvas.set_motion_playing(False)
        d=generate(family,values)
        app.load_config_data(dict(format='solidcraft-riduttori/1',family=family,parameters=d.values),path)
        self.assertTrue(wait_until(lambda:not app.pending and app.canvas.get_mapped()))
        return d

    def test_controls_refresh_geometry_undo_redo_and_actual_gl_frame(self):
        a=self.launch();self.load(a,'spur')
        group=a.geometry_group_boxes['tooth_tips_']
        self.assertFalse(group._section.get_expanded())
        group._section.set_expanded(True)
        original=list(a.design.parts[0].outer)
        a.inputs['semitopping_mm'].set_text('0.2')
        self.assertTrue(a.refresh());a.project_changed()
        self.assertTrue(wait_until(lambda:not a.pending))
        self.assertNotEqual(a.design.parts[0].outer,original)
        self.assertAlmostEqual(a.design.parts[0].profile_metadata['tooth_profile']['tip_treatment']['semitopping_mm'],.2)
        a.undo_project();self.assertTrue(wait_until(lambda:not a.pending))
        self.assertEqual(a.design.parts[0].outer,original)
        a.redo_project();self.assertTrue(wait_until(lambda:not a.pending))
        self.assertNotEqual(a.design.parts[0].outer,original)
        captured=[];a.canvas.capture_png(lambda data,error:captured.append((data,error)))
        self.assertTrue(wait_until(lambda:bool(captured)))
        self.assertIsNone(captured[0][1]);self.assertTrue(captured[0][0].startswith(b'\x89PNG'))

    def test_precise_project_save_reopen_and_invalid_draft_keeps_preview(self):
        a=self.launch();path=self.root/'tips.json';self.load(a,'spur',path=path)
        a.inputs['topping_mm'].set_text('0.15000000000000000001')
        a.inputs['semitopping_mm'].set_text('.20')
        self.assertTrue(a.save_project())
        saved=json.loads(path.read_text());before=a.design.parts[0].outer
        self.assertIn('_decimal_inputs',saved['parameters'])
        a.load_config_data(saved,path)
        self.assertTrue(wait_until(lambda:not a.pending))
        self.assertEqual(a.design.parts[0].outer,before)
        self.assertEqual(a.design.parts[0].profile_metadata['analytic_values']['tip_radius_mm'],'25.84999999999999999999')
        accepted=a.canvas.design
        a.inputs['semitopping_mm'].set_text('4')
        self.assertFalse(a.refresh())
        self.assertIs(a.canvas.design,accepted)
        self.assertFalse(a.export_menu.get_sensitive())

    def test_stage_and_rack_fields_reach_real_exports(self):
        a=self.launch()
        self.load(a,'parallel',dict(variant='two_stage_helical',wheel2_topping_mm=.03,wheel2_semitopping_mm=.05))
        self.assertIn('wheel2_semitopping_mm',a.inputs)
        self.assertEqual(a.input_geometry_groups['wheel2_semitopping_mm'],'tooth_tips_wheel2')
        self.assertIn('tip_treatment',next(p for p in a.design.parts if p.name=='S2_Wheel').profile_metadata['tooth_profile'])
        self.load(a,'rack',dict(variant='double',pinion_semitopping_mm=.1,rack_semitopping_mm=.15))
        self.assertIn('rack_semitopping_mm',a.inputs)
        stl=stl_export.write_stl(self.root/'rack.stl',a.design.parts)
        step=self.root/'rack.step'
        cad_export.write(step,a.design.parts)
        self.assertGreater(stl.stat().st_size,1000)
        self.assertEqual(Path(step).read_text().count('FACETED_BREP('),len(a.design.parts))
        self.assertTrue(a.export_menu.get_sensitive())


if __name__=='__main__':unittest.main()
