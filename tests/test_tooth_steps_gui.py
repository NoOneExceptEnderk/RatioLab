# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Independent tooth UI increments preserve model data and exact numeric edits."""
from copy import deepcopy
from math import isclose
from unittest.mock import patch
import unittest
from gi.repository import Gtk
import app_paths
import test_tooth_tips_gui as fixtures
from test_interference_gui import pump,wait_until


class ToothStepGuiTests(unittest.TestCase):
    setUpClass=fixtures.ToothTipGuiTests.__dict__['setUpClass']
    setUp=fixtures.ToothTipGuiTests.setUp
    close_apps=fixtures.ToothTipGuiTests.close_apps
    launch=fixtures.ToothTipGuiTests.launch
    load=fixtures.ToothTipGuiTests.load

    def step(self,a,key,value):
        entry=a.tooth_tips.step_inputs[key]
        entry.set_text(value);entry.emit('activate')
        return entry

    def test_independent_steps_change_real_plus_minus_without_editing_the_model(self):
        a=self.launch();self.load(a,'spur',dict(topping_mm=.1,semitopping_mm=.1))
        before=deepcopy(a.project_snapshot());token=a.document.token;design=a.design;scene=a.canvas.scene
        self.step(a,'topping_mm','0,025');self.step(a,'semitopping_angle_deg','0.5')
        self.assertEqual(a.inputs['topping_mm'].get_increments(),(.025,.25))
        self.assertEqual(a.inputs['semitopping_mm'].get_increments(),(.01,.1))
        self.assertEqual(a.inputs['semitopping_angle_deg'].get_increments(),(.5,5))
        self.assertEqual(a.project_snapshot(),before);self.assertEqual(a.document.token,token)
        self.assertIs(a.design,design);self.assertIs(a.canvas.scene,scene)
        for direction,expected in ((Gtk.SpinType.STEP_FORWARD,.125),(Gtk.SpinType.STEP_BACKWARD,.1)):
            a.inputs['topping_mm'].spin(direction,0)
            self.assertTrue(wait_until(lambda:not a.pending and a.design is not None and isclose(a.design.values['topping_mm'],expected)))
            self.assertEqual(a.design.values['semitopping_mm'],.1)
            self.assertEqual(a.design.values['semitopping_angle_deg'],45)
        a.inputs['semitopping_angle_deg'].spin(Gtk.SpinType.STEP_FORWARD,0)
        self.assertTrue(wait_until(lambda:not a.pending and a.design is not None and a.design.values['semitopping_angle_deg']==45.5))

    def test_invalid_steps_retain_last_increment_and_do_not_block_export(self):
        a=self.launch();self.load(a,'spur');self.step(a,'topping_mm','0.005')
        before=deepcopy(a.project_snapshot());token=a.document.token
        for invalid in ('','0','-1','nan','inf','101','not a number'):
            entry=self.step(a,'topping_mm',invalid)
            self.assertTrue(entry.has_css_class('field-error'),invalid)
            self.assertEqual(a.inputs['topping_mm'].get_increments(),(.005,.05))
            self.assertEqual(a.project_snapshot(),before);self.assertEqual(a.document.token,token)
            self.assertTrue(a.export_menu.get_sensitive())
        entry=self.step(a,'topping_mm','0.000000123456789')
        self.assertFalse(entry.has_css_class('field-error'))
        self.assertEqual(a.inputs['topping_mm'].get_adjustment().get_step_increment(),.000000123456789)

    def test_steps_survive_rebuild_and_restart_independently_for_each_member(self):
        a=self.launch();self.load(a,'spur');self.step(a,'topping_mm','0.0123456789')
        self.load(a,'parallel');self.step(a,'pinion_topping_mm','0.05')
        self.assertEqual(a.inputs['wheel_topping_mm'].get_adjustment().get_step_increment(),.01)
        self.load(a,'spur')
        self.assertEqual(a.inputs['topping_mm'].get_adjustment().get_step_increment(),.0123456789)
        self.assertEqual(float(a.tooth_tips.step_inputs['topping_mm'].get_text()),.0123456789)
        preferences=app_paths.load_preferences();self.assertNotIn('tooth_tip_steps',a.config()['parameters'])
        restored=self.launch();self.load(restored,'parallel')
        self.assertEqual(restored.inputs['pinion_topping_mm'].get_adjustment().get_step_increment(),.05)
        self.assertEqual(restored.inputs['wheel_topping_mm'].get_adjustment().get_step_increment(),.01)
        self.assertEqual(restored.workspace_preferences['tooth_tip_steps'],preferences['tooth_tip_steps'])

    def test_step_preferences_reject_invalid_saved_values(self):
        raw={'spur:topping_mm':.005,'spur:semitopping_mm':True,'spur:semitopping_angle_deg':float('nan'),
             'parallel:pinion_topping_mm':float('inf'),'spur:module':.1,'unknown:topping_mm':.1,
             'spur:wheel_topping_mm':-1,'spur:huge_topping_mm':10**1000}
        self.assertEqual(app_paths.ui_preferences({'tooth_tip_steps':raw})['tooth_tip_steps'],{'spur:topping_mm':.005})

    def test_small_ui_step_does_not_change_the_compatible_minimum_search(self):
        import empty_fields
        a=self.launch();self.load(a,'spur',dict(semitopping_mm=.2))
        self.step(a,'semitopping_angle_deg','0.000001')
        spin=a.inputs['semitopping_angle_deg']
        with patch.object(empty_fields,'minimum',wraps=empty_fields.minimum) as search:
            spin.set_text('');spin.emit('activate')
            self.assertTrue(wait_until(lambda:not a.empty_fields.waiting and not a.pending
                and a.design is not None and a.design.values['semitopping_angle_deg']==20.000001))
        self.assertEqual(search.call_args.args[3][2],1)
        self.assertEqual(spin.get_adjustment().get_step_increment(),.000001)


if __name__=='__main__':unittest.main()
