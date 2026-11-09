# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Real GTK/GL camera-handler and combined keyboard/mouse preference checks."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk
import app_paths
from mouse_navigation import PROFILES
import test_workspace_theme_preferences as fixtures
from test_interference_gui import pump, wait_until


class Gesture:
    def __init__(self, button, state=0):self.button=button;self.state=state
    def get_current_button(self):return self.button
    def get_current_event_state(self):return self.state
    def set_state(self, state):self.denied=state


class PointerEvent:
    def __init__(self, kind, x, y, state=0, button=0):self.kind=kind;self.x=x;self.y=y;self.state=state;self.button=button
    def get_event_type(self):return self.kind
    def get_position(self):return True,self.x,self.y
    def get_modifier_state(self):return self.state
    def get_button(self):return self.button


class MouseNavigationGuiTests(unittest.TestCase):
    setUpClass = fixtures.WorkspaceThemePreferencesTests.__dict__['setUpClass']
    setUp = fixtures.WorkspaceThemePreferencesTests.setUp
    close_apps = fixtures.WorkspaceThemePreferencesTests.close_apps
    launch = fixtures.WorkspaceThemePreferencesTests.launch

    def test_preset_applies_mouse_and_keys_together_and_allows_independent_mouse(self):
        app=self.launch();app.settings.present();panel=app.settings
        before=deepcopy(app.project_snapshot());app.canvas.zoom_speed=2
        panel.mouse['zoom_speed'].set_selected(2);panel.invert_zoom.set_active(True)
        for profile in PROFILES:
            panel.preset.set_selected(panel.preset_codes.index(profile));panel.preset_apply.emit('clicked')
            self.assertEqual(app.canvas.mouse_navigation, profile)
            self.assertEqual(app.workspace_preferences['mouse_navigation'], profile)
            self.assertEqual(panel.mouse_codes[panel.mouse_navigation.get_selected()], profile)
            self.assertEqual(app_paths.load_preferences()['mouse_navigation'], profile)
            self.assertEqual(app.canvas.zoom_speed, 2);self.assertTrue(app.canvas.invert_zoom)
        key_map=deepcopy(app.keyboard.config)
        panel.mouse_navigation.set_selected(panel.mouse_codes.index('fusion'))
        self.assertEqual(app.keyboard.config, key_map)
        self.assertEqual(app.canvas.mouse_navigation, 'fusion')
        self.assertEqual(app.project_snapshot(), before);self.assertFalse(app.document.dirty)

    def test_handlers_change_only_the_requested_camera_quantity_and_rebase_modifiers(self):
        app=self.launch();canvas=app.canvas
        self.assertTrue(wait_until(lambda:not app.pending))
        before=deepcopy(app.project_snapshot());scene=canvas.scene
        for profile,button,state,kind in [('ratiolab',1,0,'orbit'),('ratiolab',3,0,'pan'),
            ('fusion',2,0,'pan'),('fusion',2,Gdk.ModifierType.SHIFT_MASK,'orbit'),
            ('solidworks',2,0,'orbit'),('solidworks',2,Gdk.ModifierType.CONTROL_MASK,'pan'),
            ('solidworks',2,Gdk.ModifierType.SHIFT_MASK,'zoom'),('solidcraft',3,0,'orbit')]:
            app.keyboard.select_mouse_profile(profile);canvas.view('iso')
            old=(canvas.yaw,canvas.tilt,canvas.pan_offset,canvas.zoom)
            gesture=Gesture(button,state);canvas.drag_begin(gesture,0,0);canvas.drag_update(gesture,45,-30)
            self.assertEqual(canvas.drag_kind,kind)
            self.assertEqual((canvas.yaw,canvas.tilt)==old[:2],kind!='orbit')
            self.assertEqual(canvas.pan_offset==old[2],kind!='pan')
            self.assertEqual(canvas.zoom==old[3],kind!='zoom')
            canvas.drag_end(gesture)
        app.keyboard.select_mouse_profile('fusion');gesture=Gesture(2)
        canvas.drag_begin(gesture,0,0);canvas.drag_update(gesture,20,10)
        old=(canvas.yaw,canvas.tilt,canvas.pan_offset)
        gesture.state=Gdk.ModifierType.SHIFT_MASK;canvas.drag_update(gesture,20,10)
        self.assertEqual((canvas.yaw,canvas.tilt,canvas.pan_offset),old)
        canvas.drag_update(gesture,40,25);self.assertNotEqual((canvas.yaw,canvas.tilt),old[:2])
        self.assertEqual(canvas.pan_offset,old[2])
        self.assertEqual(app.project_snapshot(),before);self.assertIs(canvas.scene,scene)

    def test_freecad_chord_survives_secondary_buttons_and_does_not_select(self):
        app=self.launch();canvas=app.canvas;app.keyboard.select_mouse_profile('freecad')
        class Controller:
            def get_current_event(self):return PointerEvent(Gdk.EventType.MOTION_NOTIFY,100,100)
        self.assertFalse(canvas.freecad_pointer_event(Controller(),None))
        def event(kind,x,y,state=0,button=0):
            self.assertFalse(canvas.freecad_pointer_event(None,PointerEvent(kind,x,y,state,button)))
        down,up,motion=Gdk.EventType.BUTTON_PRESS,Gdk.EventType.BUTTON_RELEASE,Gdk.EventType.MOTION_NOTIFY
        b1,b2,b3=Gdk.ModifierType.BUTTON1_MASK,Gdk.ModifierType.BUTTON2_MASK,Gdk.ModifierType.BUTTON3_MASK
        for second,mask in [(1,b1),(3,b3)]:
            canvas.view('iso');old=(canvas.yaw,canvas.tilt,canvas.pan_offset)
            event(down,100,100,0,2);event(down,100,100,b2,second)
            event(motion,140,120,b2|mask)
            self.assertNotEqual((canvas.yaw,canvas.tilt),old[:2]);self.assertEqual(canvas.pan_offset,old[2])
            if second==3:
                event(up,140,120,b2|mask,2);yaw=canvas.yaw
                event(motion,155,120,b3);self.assertNotEqual(canvas.yaw,yaw)
                event(up,155,120,b3,3)
            else:event(up,140,120,b2|mask,1);event(up,140,120,b2,2)
            selected=canvas.selected_indices
            canvas.component_click(Gesture(1),1,100,100)
            self.assertEqual(canvas.selected_indices,selected)
            self.assertIsNone(canvas._freecad_origin)
        event(down,100,100,0,1);self.assertFalse(canvas._navigation_click)
        event(up,100,100,b1,1)

    def test_wheel_pan_override_saved_profile_and_failed_write_keep_session_usable(self):
        app_paths.save_preferences(mouse_navigation='solidworks', custom={'keep':7})
        app=self.launch();canvas=app.canvas;self.assertEqual(canvas.mouse_navigation,'solidworks')
        for profile in PROFILES:
            app.keyboard.select_mouse_profile(profile);canvas.zoom=1
            canvas.scroll(None,0,1);self.assertLess(canvas.zoom,1)
        canvas.pan_mode=True;gesture=Gesture(1);canvas.drag_begin(gesture,0,0)
        self.assertEqual(canvas.drag_kind,'pan');canvas.drag_end(gesture)
        app.settings.present()
        with patch.object(app_paths,'save_preferences',side_effect=OSError('read-only')):
            app.keyboard.select_preset('solidcraft')
        self.assertEqual(canvas.mouse_navigation,'solidcraft')
        self.assertEqual(app.keyboard.config['preset'],'solidcraft')
        self.assertTrue(app.settings.error.get_visible())
        self.assertEqual(app_paths.load_preferences()['custom'],{'keep':7})


if __name__=='__main__':unittest.main()
