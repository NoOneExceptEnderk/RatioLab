# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Actual GTK key-map edits, history capture, focus isolation and persistence."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk
import app_paths
import keyboard_shortcuts as keys
import test_workspace_theme_preferences as fixtures
from test_interference_gui import pump, wait_until


class ShortcutGuiTests(unittest.TestCase):
    setUpClass = fixtures.WorkspaceThemePreferencesTests.__dict__['setUpClass']
    setUp = fixtures.WorkspaceThemePreferencesTests.setUp
    close_apps = fixtures.WorkspaceThemePreferencesTests.close_apps
    launch = fixtures.WorkspaceThemePreferencesTests.launch

    def test_capture_suspends_commands_and_applies_new_binding_with_restart(self):
        app_paths.save_preferences(custom={'keep': 7})
        app = self.launch()
        app.settings.present()
        panel = app.settings
        before = deepcopy(app.project_snapshot())
        panel.edit_shortcut('save')
        recorder = panel.capture
        self.assertTrue(app.keyboard.recording)
        self.assertEqual(app.get_accels_for_action('app.save'), [])
        recorder.key_pressed(None, Gdk.KEY_s, 0, Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK)
        recorder.apply_button.emit('clicked')
        self.assertIsNone(panel.capture)
        self.assertFalse(app.keyboard.recording)
        self.assertEqual(app.get_accels_for_action('app.save'), ['<Control><Alt>s'])
        self.assertEqual(app.project_snapshot(), before)
        self.assertFalse(app.document.dirty)
        environment = dict(os.environ)
        root = Path(__file__).resolve().parents[1]
        environment['PYTHONPATH'] = os.pathsep.join((str(root/'src'), str(root/'tests')))
        # A fresh process exercises the actual on-disk preference boundary.
        restarted = subprocess.run([sys.executable, '-W', 'ignore::DeprecationWarning', '-c', '''
import json
import app
from gi.repository import Gio
from test_interference_gui import wait_until
a=app.ReducerApp()
a.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
a.register(None);a.activate()
assert wait_until(lambda:a.canvas.gl is not None or a.canvas.failure is not None)
assert a.canvas.failure is None and a.canvas.get_error() is None
print(json.dumps(a.get_accels_for_action('app.save')))
for window in a.get_windows():window.destroy()
'''], env=environment, capture_output=True, text=True, timeout=30)
        self.assertEqual(restarted.returncode, 0, restarted.stderr)
        self.assertEqual(json.loads(restarted.stdout.strip().splitlines()[-1]), ['<Control><Alt>s'])
        self.assertEqual(app_paths.load_preferences()['custom'], {'keep': 7})

    def test_conflicting_capture_cancel_clear_reset_and_parent_cleanup(self):
        app = self.launch()
        app.settings.present()
        panel = app.settings
        before = deepcopy(app.keyboard.config)
        panel.edit_shortcut('save')
        recorder = panel.capture
        recorder.key_pressed(None, Gdk.KEY_z, 0, Gdk.ModifierType.CONTROL_MASK)
        recorder.apply_button.emit('clicked')
        self.assertTrue(recorder.error.get_visible())
        self.assertEqual(app.keyboard.config, before)
        recorder.key_pressed(None, Gdk.KEY_Escape, 0, Gdk.ModifierType(0))
        self.assertIsNone(panel.capture)
        self.assertEqual(app.get_accels_for_action('app.save'), ['<Control>s'])
        panel.edit_shortcut('save')
        panel.capture.apply([])
        self.assertEqual(app.get_accels_for_action('app.save'), [])
        panel.reset_shortcut('save')
        self.assertEqual(app.get_accels_for_action('app.save'), ['<Control>s'])
        panel.edit_shortcut('save')
        app.win.destroy()
        self.assertFalse(app.keyboard.recording)
        self.assertIsNone(panel.capture)
        self.assertFalse(app.keyboard.listeners)

    def test_cad_view_sequences_do_not_intercept_parameter_typing_or_old_cube_keys(self):
        app = self.launch()
        keyboard = app.keyboard
        before = deepcopy(app.project_snapshot())
        keyboard.select_preset('freecad')
        app.inputs['module'].grab_focus()
        self.assertFalse(keyboard._key_pressed(None, Gdk.KEY_v, 0, Gdk.ModifierType(0)))
        self.assertFalse(keyboard.pending)
        app.canvas.grab_focus()
        # Leaving a numeric field may finish its pre-existing refresh; compare
        # the accepted scene after that transition, before any view shortcut.
        self.assertTrue(wait_until(lambda: not app.pending and not app._geometry_waiting))
        scene = app.canvas.scene
        app.canvas.zoom = 2
        yaw, tilt = app.canvas.yaw, app.canvas.tilt
        self.assertTrue(keyboard._key_pressed(None, Gdk.KEY_v, 0, Gdk.ModifierType(0)))
        self.assertEqual(app.canvas.zoom, 2)
        self.assertTrue(keyboard._key_pressed(None, Gdk.KEY_f, 0, Gdk.ModifierType(0)))
        self.assertEqual(app.canvas.zoom, 1)
        self.assertEqual((app.canvas.yaw, app.canvas.tilt), (yaw, tilt))
        self.assertFalse(keyboard.pending)
        keyboard.view_key(Gdk.KEY_v, Gdk.ModifierType(0))
        pump(1.3)
        self.assertFalse(keyboard.pending)
        self.assertFalse(keyboard.view_key(Gdk.KEY_f, Gdk.ModifierType(0)))
        self.assertFalse(app.navigation_cube.key(None, Gdk.KEY_Home, 0, Gdk.ModifierType(0)))
        self.assertTrue(app.navigation_cube.key(None, Gdk.KEY_2, 0, Gdk.ModifierType(0)))
        self.assertTrue(wait_until(lambda: (app.canvas.yaw, app.canvas.tilt) == (0., 0.)))
        self.assertEqual((app.canvas.yaw, app.canvas.tilt), (0., 0.))
        keyboard.view_key(Gdk.KEY_v, Gdk.ModifierType(0))
        app.inputs['module'].grab_focus()
        self.assertFalse(keyboard.pending)
        self.assertEqual(app.project_snapshot(), before)
        self.assertFalse(app.document.dirty)
        self.assertIs(app.canvas.scene, scene)

    def test_dynamic_history_bindings_keep_project_undo_and_remove_old_trigger(self):
        app = self.launch()
        app.keyboard.assign('undo', ['<Control><Alt>z'])
        self.assertEqual(app.get_accels_for_action('app.undo'), ['<Control><Alt>z'])
        triggers = [shortcut.get_trigger().to_string() for shortcut in app.history_shortcuts]
        self.assertNotIn('<Control>z', triggers)
        self.assertIn('<Control><Alt>z', triggers)
        app.inputs['module'].grab_focus()
        app.inputs['module'].set_text('2.25')
        self.assertTrue(app.document.dirty)
        app.history_shortcuts[0].get_action().activate(Gtk.ShortcutActionFlags.EXCLUSIVE, app.inputs['module'], None)
        self.assertFalse(app.document.dirty)
        app.keyboard.select_preset('solidcraft')
        self.assertEqual(app.get_accels_for_action('app.redo'), ['<Control>y'])
        self.assertEqual(len(app.history_shortcuts), 2)

    def test_sequence_recording_autorepeat_and_failed_preference_write(self):
        app = self.launch()
        app.settings.present()
        app.keyboard.select_preset('freecad')
        app.settings.edit_shortcut('view-fit')
        recorder = app.settings.capture
        recorder.key_pressed(None, Gdk.KEY_v, 0, Gdk.ModifierType(0))
        recorder.key_pressed(None, Gdk.KEY_v, 0, Gdk.ModifierType(0))
        self.assertEqual(recorder.pending, ['v'])
        self.assertFalse(recorder.apply_button.get_sensitive())
        recorder.key_released(None, Gdk.KEY_v)
        recorder.key_pressed(None, Gdk.KEY_f, 0, Gdk.ModifierType(0))
        self.assertTrue(recorder.apply_button.get_sensitive())
        with patch.object(app_paths, 'save_preferences', side_effect=OSError('read-only profile')):
            recorder.apply_button.emit('clicked')
        self.assertTrue(app.settings.error.get_visible())
        self.assertEqual(app.keyboard.config['bindings']['view-fit'], ['v f'])
        self.assertFalse(app.keyboard.recording)
        self.assertFalse(app.document.dirty)


if __name__ == '__main__':unittest.main()
