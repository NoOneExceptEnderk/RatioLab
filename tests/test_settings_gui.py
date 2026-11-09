# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Actual GTK/OpenGL preference changes must leave the current project intact."""
from copy import deepcopy
from math import isclose
import unittest
from unittest.mock import patch
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk
import app_paths
import test_workspace_theme_preferences as fixtures
from test_interference_gui import pump


class SettingsTests(unittest.TestCase):
    setUpClass = fixtures.WorkspaceThemePreferencesTests.__dict__['setUpClass']
    setUp = fixtures.WorkspaceThemePreferencesTests.setUp
    close_apps = fixtures.WorkspaceThemePreferencesTests.close_apps
    launch = fixtures.WorkspaceThemePreferencesTests.launch

    def test_single_dialog_close_reopen_and_parent_lifecycle(self):
        app = self.launch()
        app.settings_button.emit('clicked')
        pump(.1)
        panel = app.settings
        dialog = panel.dialog
        self.assertIsNotNone(dialog)
        self.assertTrue(dialog.get_modal())
        self.assertIs(dialog.get_transient_for(), app.win)
        app.lookup_action('settings').activate(None)
        self.assertIs(panel.dialog, dialog)
        self.assertEqual(app.get_accels_for_action('app.settings'), ['<Control>comma'])
        for name in ('controls', 'general', 'appearance'):
            panel.tabs[name].set_active(True)
            pump(.03)
            self.assertEqual(panel.stack.get_visible_child_name(), name)
            self.assertTrue(panel.pages[name].get_mapped())
        self.assertTrue(panel._key_pressed(None, Gdk.KEY_Escape, 0, Gdk.ModifierType(0)))
        self.assertIsNone(panel.dialog)
        self.assertFalse(panel.handlers)
        app.theme_switch.set_active(True)
        panel.present()
        self.assertEqual(panel.theme.get_selected(), 1)
        app.win.destroy()
        self.assertIsNone(panel.dialog)
        self.assertFalse(panel.handlers)

    def test_live_preferences_preserve_document_and_change_actual_navigation(self):
        app = self.launch()
        panel = app.settings
        panel.present()
        before = deepcopy(app.project_snapshot())
        states = deepcopy(app.document.states)
        token = app.document.token
        design, scene = app.design, app.canvas.scene
        panel.theme.set_selected(1)
        self.assertTrue(app.theme_switch.get_active())
        self.assertEqual(app.canvas.theme, 'light')
        app.theme_switch.set_active(False)
        self.assertEqual(panel.theme.get_selected(), 0)
        panel.text_size.set_selected(1)
        panel.mouse['zoom_speed'].set_selected(2)
        panel.mouse['rotation_speed'].set_selected(0)
        panel.invert_zoom.set_active(True)
        panel.hover_help.set_active(False)
        self.assertEqual(app.workspace_preferences['text_scale'], 1.25)
        self.assertEqual(app.canvas.zoom_speed, 2)
        self.assertEqual(app.canvas.rotation_speed, .5)
        self.assertTrue(app.canvas.invert_zoom)
        self.assertFalse(app.workspace_preferences['hover_help'])
        canvas = app.canvas
        zoom = canvas.zoom
        canvas.scroll(None, 0, 1)
        self.assertTrue(isclose(canvas.zoom, zoom*1.12**2))
        yaw = canvas.yaw
        canvas.drag_begin(None, 0, 0)
        canvas.drag_update(None, 10, 0)
        self.assertTrue(isclose(canvas.yaw, yaw+10*.008*.5))
        yaw = canvas.yaw
        app.navigation_cube.begin(None, 50, 50)
        app.navigation_cube.drag(None, 10, 0)
        self.assertTrue(isclose(canvas.yaw, yaw+10*.008*.5))
        self.assertEqual(app.project_snapshot(), before)
        self.assertEqual(app.document.states, states)
        self.assertEqual(app.document.token, token)
        self.assertFalse(app.document.dirty)
        self.assertIs(app.design, design)
        self.assertIs(canvas.scene, scene)
        saved = app_paths.load_preferences()
        for key in ('theme', 'text_scale', 'zoom_speed', 'rotation_speed', 'invert_zoom', 'hover_help'):
            self.assertEqual(saved[key], app.workspace_preferences[key])

    def test_restart_preserves_preferences_and_unrelated_profile_data(self):
        app_paths.save_preferences(custom={'keep': 7}, recent=['example.json'],
                                   output_dir=str(self.root/'exports'))
        app = self.launch()
        app.settings.present()
        panel = app.settings
        panel.theme.set_selected(1)
        panel.text_size.set_selected(2)
        panel.mouse['zoom_speed'].set_selected(0)
        panel.mouse['rotation_speed'].set_selected(2)
        panel.invert_zoom.set_active(True)
        panel.hover_help.set_active(False)
        panel.language.set_selected(panel.language_codes.index('it'))
        panel.dialog.close()
        self.assertIsNone(panel.dialog)
        app.win.destroy()
        restarted = self.launch()
        restarted.settings.present()
        panel = restarted.settings
        self.assertEqual(panel.theme.get_selected(), 1)
        self.assertEqual(panel.text_size.get_selected(), 2)
        self.assertEqual(panel.mouse['zoom_speed'].get_selected(), 0)
        self.assertEqual(panel.mouse['rotation_speed'].get_selected(), 2)
        self.assertTrue(panel.invert_zoom.get_active())
        self.assertFalse(panel.hover_help.get_active())
        self.assertEqual(restarted.language.language, 'it')
        self.assertAlmostEqual(restarted.win.get_pango_context().get_font_description().get_size()/1024, 21)
        self.assertEqual(restarted.output_dir, self.root/'exports')
        self.assertEqual(app_paths.load_preferences()['custom'], {'keep': 7})
        self.assertEqual(app_paths.load_preferences()['recent'], ['example.json'])

    def test_language_sync_and_failed_writes_keep_session_usable(self):
        app = self.launch()
        app.settings.present()
        panel = app.settings
        app.language.change('it')
        self.assertEqual(panel.language.get_selected(), panel.language_codes.index('it'))
        self.assertEqual(panel.tabs['appearance'].get_label(), 'Aspetto')
        self.assertEqual(panel.dialog.get_title(), 'Impostazioni')
        with patch.object(app_paths, 'save_preferences', side_effect=OSError('read-only profile')):
            panel.mouse['zoom_speed'].set_selected(2)
            self.assertTrue(panel.error.get_visible())
            self.assertEqual(app.canvas.zoom_speed, 2)
            panel.text_size.set_selected(1)
            self.assertTrue(panel.error.get_visible())
            panel.language.set_selected(panel.language_codes.index('fr'))
            self.assertEqual(app.language.language, 'fr')
            self.assertTrue(panel.error.get_visible())
        panel.language.set_selected(panel.language_codes.index('en'))
        # A different preference's successful save cannot hide the pending error.
        self.assertTrue(panel.error.get_visible())
        panel.mouse['zoom_speed'].set_selected(1)
        self.assertFalse(panel.error.get_visible())


if __name__ == '__main__':
    unittest.main()
