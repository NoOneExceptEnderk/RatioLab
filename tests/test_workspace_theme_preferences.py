# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Display-backed theme persistence, preview rendering and document isolation."""
from collections import Counter
from copy import deepcopy
from io import BytesIO
import os
import json
from pathlib import Path
import sys
import subprocess
from tempfile import TemporaryDirectory
import unittest
import uuid
from unittest.mock import patch

import cairo
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, Gio
import app as module
import app_paths
from geometry import generate
import stl_export
from test_interference_gui import pump, wait_until


class WorkspaceThemePreferencesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            raise unittest.SkipTest('GTK display required')

    def setUp(self):
        self.temp = TemporaryDirectory(prefix='ratiolab-theme-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        env = patch.dict(os.environ, dict(XDG_CONFIG_HOME=str(self.root/'config'),
                         XDG_DATA_HOME=str(self.root/'data'), APPDATA=str(self.root/'roaming'),
                         LOCALAPPDATA=str(self.root/'local'), RATIOLAB_UPDATE_CHECK='0'))
        env.start()
        self.addCleanup(env.stop)
        self.apps = []
        self.addCleanup(self.close_apps)

    def close_apps(self):
        for app in self.apps:
            for window in app.get_windows():
                window.destroy()
            Gtk.StyleContext.remove_provider_for_display(Gdk.Display.get_default(), app.workspace_style)
        pump()

    def launch(self):
        app = module.ReducerApp()
        app.set_application_id(f'local.ratiolab.themetests.p{os.getpid()}.n{uuid.uuid4().hex}')
        app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        app.register(None)
        app.activate()
        self.apps.append(app)
        self.assertTrue(wait_until(lambda: app.canvas.gl is not None or app.canvas.failure is not None))
        self.assertIsNone(app.canvas.failure)
        self.assertIsNone(app.canvas.get_error())
        return app

    def test_theme_switch_changes_theme_directly_without_editing_project(self):
        app=self.launch()
        before=deepcopy(app.project_snapshot())
        design=app.design
        self.assertFalse(app.theme_switch.get_active())
        self.assertIsNone(app.theme_switch.get_parent())
        self.assertFalse(hasattr(app,'theme_popover'))
        for active, theme in ((True,'light'), (False,'dark'), (True,'light')):
            app.theme_switch.set_active(active);pump(.1)
            self.assertEqual(app.workspace_theme,theme)
            self.assertEqual(app.canvas.theme,theme)
            self.assertEqual(app_paths.load_preferences()['theme'],theme)
            self.assertIs(app.design,design)
            self.assertEqual(app.project_snapshot(),before)
        app.language.change('it');pump(.1)
        self.assertIs(app.appearance_button, app.settings_button)
        app.theme_switch.set_active(False);pump(.1)
        self.assertEqual(app.workspace_theme,'dark')
        self.assertFalse(app.theme_switch.get_mapped())

    def test_missing_or_invalid_preference_keeps_existing_dark_default(self):
        app = self.launch()
        self.assertEqual(app.workspace_theme, 'dark')
        self.assertEqual(app.theme_selector.get_selected(), 0)
        self.assertFalse((app_paths.config_dir()/app_paths.PREFERENCES_FILENAME).exists())
        # JSON objects/arrays and unknown strings are also safe to ignore.
        for invalid in ({'name': 'light'}, ['light'], 'unknown', None):
            app_paths.save_preferences(theme=invalid)
            restarted = self.launch()
            self.assertEqual(restarted.workspace_theme, 'dark')
            self.assertEqual(restarted.canvas.theme, 'dark')

    def test_change_persists_and_restart_preserves_unrelated_preferences(self):
        app_paths.save_preferences(output_dir=str(self.root/'exports'), custom={'keep': 7})
        app = self.launch()
        app.theme_selector.set_selected(1)
        self.assertEqual(app_paths.load_preferences()['theme'], 'light')
        app_paths.save_preferences(recent=['example.json'])
        restarted = self.launch()
        self.assertEqual(restarted.workspace_theme, 'light')
        self.assertEqual(restarted.canvas.theme, 'light')
        self.assertEqual(restarted.theme_selector.get_selected(), 1)
        self.assertEqual(restarted.output_dir, self.root/'exports')
        self.assertEqual(app_paths.load_preferences()['custom'], {'keep': 7})
        self.assertEqual(app_paths.load_preferences()['recent'], ['example.json'])
        repository = Path(__file__).resolve().parents[1]
        child_environment = os.environ.copy()
        child_paths = [str(repository/'src'), str(repository/'tests')]
        if child_environment.get('PYTHONPATH'):
            child_paths.append(child_environment['PYTHONPATH'])
        child_environment['PYTHONPATH'] = os.pathsep.join(child_paths)
        result = subprocess.run([sys.executable, '-W', 'ignore::DeprecationWarning', '-c', '''
import json
import app
from gi.repository import Gio
from test_interference_gui import pump
a=app.ReducerApp()
a.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
a.register(None)
a.activate()
pump(.15)
print(json.dumps(dict(theme=a.workspace_theme, preview=a.canvas.theme,
                     selected=a.theme_selector.get_selected())))
for w in a.get_windows():w.destroy()
'''], env=child_environment, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout.strip().splitlines()[-1]),
                         dict(theme='light', preview='light', selected=1))

    def test_live_theme_and_scaling_keep_geometry_document_selection_and_stl(self):
        app = self.launch()
        app.load_config_data(dict(format='solidcraft-riduttori/1', family='spur',
                                  parameters=generate('spur').values))
        app.components.select((0,))
        canvas = app.canvas
        config, states = deepcopy(app.config()), deepcopy(app.document.states)
        token, dirty, scene, design = app.document.token, app.document.dirty, canvas.scene, app.design
        vertices = scene.vertices.tobytes()
        # Palette changes and native font allocation complete on a mapped frame.
        # Read the baseline after paint rather than during initial realization.
        painted=[];clock=app.win.get_frame_clock()
        handler=clock.connect('after-paint',lambda *_:painted.append(True))
        try:
            app.win.queue_draw()
            self.assertTrue(wait_until(lambda:bool(painted) and app.project_title.get_mapped(),3))
        finally:
            clock.disconnect(handler)
        base_font_size = app.project_title.get_pango_context().get_font_description().get_size()
        before = stl_export.write_stl(self.root/'before.stl', design.parts).read_bytes()
        for theme in (1, 0, 1):
            app.theme_selector.set_selected(theme)
            for scale in (2, 1, 0):
                app.text_size.set_selected(scale)
                expected = (38, 56, 70) if theme else (233, 238, 244)
                expected_scale = (1, 1.25, 1.5)[scale]
                def displayed_style_ready():
                    color=app.project_title.get_style_context().get_color()
                    font_size=app.project_title.get_pango_context().get_font_description().get_size()
                    return (app.project_title.get_mapped()
                        and all(abs(actual-value/255)<=.01
                            for actual,value in zip((color.red,color.green,color.blue),expected))
                        and abs(font_size/base_font_size-expected_scale)<=.02)
                ready=wait_until(displayed_style_ready,3)
                color = app.project_title.get_style_context().get_color()
                self.assertTrue(ready,
                    f'Native style did not settle: theme={theme}, scale={scale}, '
                    f'mapped={app.project_title.get_mapped()}, '
                    f'actual_rgb={(color.red,color.green,color.blue)}, '
                    f'font_scale={app.project_title.get_pango_context().get_font_description().get_size()/base_font_size}')
                for actual, value in zip((color.red, color.green, color.blue), expected):
                    self.assertAlmostEqual(actual, value/255, delta=.01,
                        msg=f'theme={theme}, scale={scale}, app_theme={app.workspace_theme}, '
                            f'selected={app.theme_selector.get_selected()}, canvas_theme={canvas.theme}, '
                            f'actual_rgb={(color.red,color.green,color.blue)}, '
                            f'palette_lookup={app.project_title.get_style_context().lookup_color("rl_text")}')
                font_size = app.project_title.get_pango_context().get_font_description().get_size()
                self.assertAlmostEqual(font_size/base_font_size, (1, 1.25, 1.5)[scale], delta=.02)
                self.assertEqual(canvas.theme, ('dark', 'light')[theme])
                self.assertIs(canvas.scene, scene)
                self.assertIs(app.design, design)
                self.assertEqual(canvas.selected_indices, (0,))
        self.assertEqual(app.config(), config)
        self.assertEqual(app.document.token, token)
        self.assertEqual(app.document.states, states)
        self.assertEqual(app.document.dirty, dirty)
        self.assertEqual(scene.vertices.tobytes(), vertices)
        after = stl_export.write_stl(self.root/'after.stl', app.design.parts).read_bytes()
        self.assertEqual(before, after)

    def test_real_gl_framebuffers_follow_each_palette(self):
        app = self.launch()
        for selected in (1, 0):
            app.theme_selector.set_selected(selected)
            captured = []
            app.canvas.capture_png(lambda data, error: captured.append((data, error)))
            self.assertEqual(len(captured), 1)
            png, error = captured[0]
            self.assertIsNone(error)
            surface = cairo.ImageSurface.create_from_png(BytesIO(png))
            data = bytes(surface.get_data())
            counts = Counter(data[i:i+4] for i in range(0, len(data), 4))
            rgb = tuple(round(x*255) for x in app.canvas.palette['background'])
            pixel = bytes((rgb[2], rgb[1], rgb[0], 255) if sys.byteorder == 'little' else (255, *rgb))
            self.assertGreater(counts[pixel], surface.get_width()*surface.get_height()*.1)
            self.assertGreater(len(counts), 12, 'Preview contains rendered geometry and grid')

    def test_save_failure_keeps_session_theme_and_displays_error(self):
        app = self.launch()
        with patch.object(app_paths, 'save_preferences', side_effect=OSError('read-only profile')):
            app.theme_selector.set_selected(1)
        self.assertEqual(app.workspace_theme, 'light')
        self.assertEqual(app.canvas.theme, 'light')
        self.assertTrue(app.theme_error.get_visible())
        app.theme_selector.set_selected(0)
        self.assertFalse(app.theme_error.get_visible())
        self.assertEqual(app_paths.load_preferences()['theme'], 'dark')


if __name__ == '__main__':
    unittest.main()
