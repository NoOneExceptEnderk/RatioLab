# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Display-backed native navigation without editing the document or mechanism."""
from copy import deepcopy
from gi.repository import Gdk
import unittest
import test_workspace_theme_preferences as fixtures
from test_interference_gui import pump
from component_geometry import project


class NavigationCubeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures.WorkspaceThemePreferencesTests.setUpClass()

    def setUp(self):
        self.fixture=fixtures.WorkspaceThemePreferencesTests('test_theme_switch_changes_theme_directly_without_editing_project')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)

    def launch(self):return self.fixture.launch()

    def test_right_drag_pan_picking_and_display_preserve_document(self):
        app=self.launch();c=app.canvas;before=deepcopy(app.project_snapshot())
        app.components.open();c.view('top');pump()
        class Gesture:
            def get_current_button(self):return 3
            def get_current_event_state(self):return Gdk.ModifierType(0)
        c.drag_begin(Gesture(),0,0);c.drag_update(Gesture(),45,25);pump()
        self.assertEqual((c.yaw,c.tilt),(0.,0.))
        self.assertNotEqual(c.pan_offset,(0.,0.,0.))
        xy=project((10,0,10),c.camera_center,c.scene.radius,c.zoom,c.yaw,c.tilt,c.get_width(),c.get_height())
        c.emit('component-click',*xy,False);self.assertEqual(app.components.selected,(0,))
        for direction in ((1,0,0),(0,0,-1),(1,-1,1)):
            c.orient(direction);pump();self.assertIsNone(c.failure)
        c.view('iso');self.assertEqual(c.pan_offset,(0.,0.,0.))
        app.view_menu.set_active(True);pump();self.assertTrue(app.view_panel.get_visible())
        self.assertEqual((app.navigation_cube.get_width(),app.navigation_cube.get_height()),(116,116))
        app.view_options['section'].set_active(True);app.explode_slider.set_value(.5);pump()
        self.assertTrue(c.section);self.assertEqual(c.exploded,.5)
        app.view_menu.set_active(False);app.pan_button.set_active(True);self.assertTrue(c.pan_mode)
        self.assertEqual(app.project_snapshot(),before)
