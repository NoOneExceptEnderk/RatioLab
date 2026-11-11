# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Actual GTK focus commits, persistent tooth sessions and animated views."""
from copy import deepcopy
import unittest
from gi.repository import Gtk
import test_tooth_tip_preview_gui as fixtures
from test_interference_gui import pump,wait_until


class QolGuiTests(unittest.TestCase):
    setUpClass=fixtures.ToothTipPreviewGuiTests.__dict__['setUpClass']
    setUp=fixtures.ToothTipPreviewGuiTests.setUp
    close_apps=fixtures.ToothTipPreviewGuiTests.close_apps
    launch=fixtures.ToothTipPreviewGuiTests.launch
    load=fixtures.ToothTipPreviewGuiTests.load
    ready=fixtures.ToothTipPreviewGuiTests.ready

    def settled(self,a):
        self.assertTrue(wait_until(lambda:not a.pending and not a._geometry_waiting and not a.empty_fields.waiting and not a.canvas.camera_transition))

    def commit_empty(self,a,key):
        w=a.inputs[key];w.grab_focus();w.set_text('');w.emit('activate')
        self.assertTrue(wait_until(lambda:bool(w.get_text().strip()) and not a.pending and not a.empty_fields.waiting))
        return w.get_text()

    def test_empty_zero_minimum_and_model_dependent_minimum_save_and_history(self):
        a=self.launch();self.load(a,'spur')
        self.assertEqual(float(self.commit_empty(a,'backlash')),0)
        self.assertEqual(float(self.commit_empty(a,'teeth')),8)
        # Restore the usual tooth count; module minimum depends on the real bore.
        self.load(a,'spur')
        before=deepcopy(a.design.values)
        self.assertEqual(float(self.commit_empty(a,'module')),.302326)
        self.assertEqual(a.design.values['bore'],before['bore'])
        self.assertEqual(a.config()['parameters']['module'],.302326)
        a.undo_project();self.settled(a);self.assertEqual(a.design.values['module'],2)
        a.redo_project();self.settled(a);self.assertEqual(a.design.values['module'],.302326)

    def test_focus_loss_commit_and_field_switch_keep_manual_tooth_camera(self):
        a=self.launch();self.load(a,'spur')
        a.geometry_group_boxes['tooth_tips_']._section.set_expanded(True)
        a.inputs['topping_mm'].grab_focus();self.ready(a)
        self.assertTrue(a.tooth_tips.reset_camera.get_visible())
        c=a.canvas;c.yaw=.25;c.tilt=-.55;c.roll=.1;c.zoom=1.8;c.pan_offset=(.5,.75,1.)
        state=c.camera_state()
        for key,text in (('semitopping_mm','.2'),('semitopping_angle_deg','50'),('topping_mm','.1')):
            a.inputs[key].grab_focus();pump(.1)
            self.assertEqual(c.camera_state(),state)
            a.inputs[key].set_text(text);self.ready(a)
            for p,q in zip(c.camera_state()[:4],state[:4]):self.assertAlmostEqual(p,q)
            self.assertEqual(c.camera_center,state[4])
        a.inputs['topping_mm'].set_text('');c.grab_focus()
        self.assertTrue(wait_until(lambda:a.inputs['topping_mm'].get_text()=='0' and not a.pending and not a.empty_fields.waiting))
        self.ready(a);self.assertIsNotNone(c.tooth_detail)
        self.assertEqual(c.camera_center,state[4])
        # SpinButton commits its adjustment on focus loss even if the typed
        # text already produced a preview. Reset must accept that first click.
        angle=a.inputs['semitopping_angle_deg']
        angle.grab_focus();angle.set_text('51');self.ready(a)
        a.tooth_tips.reset_camera.grab_focus();pump(.01)
        self.assertTrue(a.tooth_tips.reset_camera.get_sensitive())
        a.tooth_tips.reset_camera.emit('clicked')
        self.assertIsNotNone(c.camera_transition)
        self.settled(a)
        self.assertAlmostEqual(c.tilt,0);self.assertAlmostEqual(c.yaw,0);self.assertAlmostEqual(c.roll,0)
        self.assertEqual(c.zoom,1)
        a.select_view('iso');self.settled(a)
        self.assertFalse(a.tooth_tips.reset_camera.get_visible())

    def test_camera_has_intermediate_frames_and_gesture_interrupts(self):
        a=self.launch();self.load(a,'spur');c=a.canvas;self.settled(a)
        initial=c.camera_state();c.orient((0,0,1))
        self.assertIsNotNone(c.camera_transition);self.assertEqual(c.camera_state(),initial)
        pump(.1);self.assertNotEqual(c.camera_state(),initial);self.assertNotEqual(c.tilt,0)
        self.settled(a);self.assertEqual((c.yaw,c.tilt,c.roll),(0.,0.,0.))
        c.orient((1,0,0));pump(.08)
        c._anchor_drag('orbit',0,0);self.assertIsNone(c.camera_transition)
        c._move_drag(20,10);state=c.camera_state();pump(.5)
        self.assertEqual(c.camera_state(),state)
        c.view('iso');self.assertIsNotNone(c.camera_transition);self.settled(a)

    def test_new_edit_or_document_rejects_delayed_minimum(self):
        from threading import Event
        from unittest.mock import patch
        import empty_fields
        started,release=Event(),Event();original=empty_fields.minimum
        def hold(*args,**kwargs):
            started.set();release.wait(5);return original(*args,**kwargs)
        a=self.launch();self.load(a,'spur')
        try:
            with patch.object(empty_fields,'minimum',side_effect=hold):
                a.inputs['module'].set_text('');a.inputs['module'].emit('activate')
                self.assertTrue(wait_until(started.is_set))
                a.inputs['module'].set_text('3.00000000000000000001')
                release.set()
                self.assertTrue(wait_until(lambda:a.empty_fields.worker.thread is None and not a.pending))
                self.assertEqual(a.inputs['module'].get_text(),'3.00000000000000000001')
                self.assertEqual(a.config()['parameters']['_decimal_inputs']['module'],'3.00000000000000000001')
        finally:release.set()

    def test_back_during_numeric_search_does_not_reopen_the_tooth_session(self):
        from threading import Event
        from unittest.mock import patch
        import empty_fields
        started,release=Event(),Event();original=empty_fields.minimum
        def hold(*args,**kwargs):
            started.set();release.wait(5);return original(*args,**kwargs)
        a=self.launch();self.load(a,'spur',dict(topping_mm=.2))
        a.geometry_group_boxes['tooth_tips_']._section.set_expanded(True)
        a.inputs['topping_mm'].grab_focus();self.ready(a)
        try:
            with patch.object(empty_fields,'minimum',side_effect=hold):
                a.inputs['topping_mm'].set_text('');a.inputs['topping_mm'].emit('activate')
                self.assertTrue(wait_until(started.is_set))
                a.select_view('iso');release.set()
                self.assertTrue(wait_until(lambda:a.inputs['topping_mm'].get_text()=='0' and not a.empty_fields.waiting))
                self.settled(a)
                self.assertIsNone(a.canvas.tooth_detail)
                self.assertIsNone(a.tooth_tips.field)
                self.assertFalse(a.tooth_tips.reset_camera.get_visible())
        finally:release.set()
