# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Global preference validation, persistence and real desktop application."""
from copy import deepcopy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid
import app_paths


class PreferenceValidationTests(unittest.TestCase):
    def test_invalid_types_and_unknown_values_keep_defaults(self):
        for value in (None, [], 'bad', dict(theme=[], text_scale=True, hover_help=1,
                      zoom_speed=float('inf'), rotation_speed=0, invert_zoom='yes')):
            self.assertEqual(app_paths.ui_preferences(value), app_paths.UI_DEFAULTS)
        self.assertEqual(app_paths.ui_preferences(dict(text_scale=1.5, zoom_speed=.5,
                         rotation_speed=2, hover_help=False, invert_zoom=True, theme='light', language='en')),
                         dict(text_scale=1.5, zoom_speed=.5, rotation_speed=2,
                              hover_help=False, invert_zoom=True, theme='light', language='en'))

    def test_atomic_preferences_preserve_output_and_unknown_keys(self):
        with TemporaryDirectory() as folder, patch.dict(os.environ, XDG_CONFIG_HOME=folder,
                     APPDATA=folder), patch.object(app_paths.sys, 'platform', 'linux'):
            app_paths.save_preferences(output_dir=folder, custom={'keep': 7})
            app_paths.save_preferences(text_scale=1.25, hover_help=False)
            saved = app_paths.load_preferences()
            self.assertEqual(saved['output_dir'], folder)
            self.assertEqual(saved['custom'], {'keep': 7})
            self.assertEqual(saved['text_scale'], 1.25)
            self.assertFalse(saved['hover_help'])


class DesktopLanguageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import gi
        gi.require_version('Gtk', '4.0')
        from gi.repository import Gtk, Gdk
        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            raise unittest.SkipTest('GTK display required')

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.environment = patch.dict(os.environ, XDG_CONFIG_HOME=str(root/'config'),
            XDG_DATA_HOME=str(root/'data'), APPDATA=str(root/'config'),
            LOCALAPPDATA=str(root/'data'), RATIOLAB_UPDATE_CHECK='0')
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.apps = []
        self.addCleanup(self.close_apps)

    def close_apps(self):
        from gi.repository import Gtk, Gdk
        from test_interference_gui import pump, wait_until
        for app in self.apps:
            for window in app.get_windows():
                window.destroy()
            Gtk.StyleContext.remove_provider_for_display(Gdk.Display.get_default(), app.workspace_style)
        pump()

    def launch(self):
        import app as module
        from gi.repository import Gio
        from test_interference_gui import wait_until
        app = module.ReducerApp()
        app.set_application_id('local.ratiolab.settings.n'+uuid.uuid4().hex)
        app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        app.register(None)
        app.activate()
        self.apps.append(app)
        self.assertTrue(wait_until(lambda: app.canvas.gl is not None or app.canvas.failure, 10))
        self.assertIsNone(app.canvas.failure)
        self.assertTrue(wait_until(lambda: app.design is not None and not app.busy and not app.pending, 10))
        return app

    def test_languages_theme_restart_preserve_model_and_raw_precision(self):
        from test_interference_gui import pump, wait_until
        from ui_language import catalog, translate
        app_paths.save_preferences(custom={'keep': 9})
        a = self.launch()
        precise = a.inputs['module']
        precise.set_text('2.000000000012345')
        raw = precise.get_text()
        self.assertTrue(wait_until(lambda: not a.pending and not a._geometry_waiting and a.design.values['module'] == float(raw)))
        original = (deepcopy(a.config()), a.document.token, a.document.dirty,
                    deepcopy(a.document.states), a.design, a.canvas.scene,
                    a.canvas.scene.vertices.tobytes())
        family_index, variant_index = a.selector.get_selected(), a.variant_selector.get_selected()
        for code in catalog()['languages']:
            a.language.change(code)
            pump(.18)
            label = a.model_dimensions_heading.get_label()
            self.assertEqual(label, translate('Family', code))
            self.assertEqual(a.selector.get_selected(), family_index)
            self.assertEqual(a.variant_selector.get_selected(), variant_index)
            self.assertEqual(precise.get_text(), raw)
            self.assertEqual(a.config(), original[0])
            self.assertEqual(a.document.token, original[1])
            self.assertEqual(a.document.dirty, original[2])
            self.assertEqual(a.document.states, original[3])
            self.assertIs(a.design, original[4])
            self.assertIs(a.canvas.scene, original[5])
            self.assertEqual(a.canvas.scene.vertices.tobytes(), original[6])
        a.language.change('it')
        a.theme_selector.set_selected(1)
        self.assertEqual(app_paths.load_preferences()['custom'], {'keep':9})
        b = self.launch()
        self.assertEqual(b.language.language, 'it')
        self.assertEqual(b.model_dimensions_heading.get_label(), 'Famiglia')
        self.assertEqual(b.workspace_theme, 'light')
        self.assertFalse(hasattr(b, 'settings_button'))

    def test_closing_transient_popup_keeps_dynamic_label_translation_running(self):
        from gi.repository import Gtk, GLib
        from test_interference_gui import pump
        a = self.launch()
        popup = Gtk.Popover()
        popup.set_parent(a.language_menu)
        label = Gtk.Label(label='Tools')
        popup.set_child(label)
        label.connect('notify::label', lambda *_: popup.unparent() if popup.get_parent() else None)
        a.language.change('it')
        pump(.2)
        self.assertIsNotNone(GLib.MainContext.default().find_source_by_id(a.language.timer))
        a.make_fields()
        pump(.2)
        self.assertEqual(a.model_dimensions_heading.get_label(),'Famiglia')
        self.assertIsNotNone(GLib.MainContext.default().find_source_by_id(a.language.timer))

    def test_language_save_failure_keeps_session(self):
        a = self.launch()
        with patch.object(app_paths, 'save_preferences', side_effect=OSError('read-only')):
            a.language.change('it')
        self.assertEqual(a.language.language,'it')
        self.assertTrue(a.language.error.get_visible())
        a.language.change('en')
        self.assertFalse(a.language.error.get_visible())


if __name__ == '__main__':
    unittest.main()
