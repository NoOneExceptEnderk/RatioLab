# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Actual native theme edits must preserve model data, history and GL rendering."""
from collections import Counter
from copy import deepcopy
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import cairo
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio
import app_paths
import theme_preferences as themes
import test_workspace_theme_preferences as fixtures
from test_interference_gui import pump, wait_until


class CustomThemeGuiTests(unittest.TestCase):
    setUpClass = fixtures.WorkspaceThemePreferencesTests.__dict__['setUpClass']
    setUp = fixtures.WorkspaceThemePreferencesTests.setUp
    close_apps = fixtures.WorkspaceThemePreferencesTests.close_apps
    launch = fixtures.WorkspaceThemePreferencesTests.launch

    def open_editor(self):
        app = self.launch();app.settings.present();pump(.1)
        self.assertTrue(wait_until(lambda:not app.pending and not app._geometry_waiting))
        return app, app.settings.theme_editor

    def test_color_controls_change_actual_css_and_gl_without_editing_the_document(self):
        app, editor = self.open_editor()
        before = deepcopy(app.project_snapshot());states = deepcopy(app.document.states)
        token, design, scene = app.document.token, app.design, app.canvas.scene
        editor.cards['nord'].set_active(True)
        entry = editor.entries['colors', 'accent'];entry.set_text('#BC6512');entry.emit('activate')
        entry = editor.entries['viewport', 'background'];entry.set_text('#123456');entry.emit('activate')
        self.assertEqual(themes.palette('dark', editor.config)['accent'], '#bc6512')
        self.assertEqual(app.canvas.palette['background'], themes.rgb('#123456'))
        self.assertTrue(wait_until(lambda:app.project_title.get_style_context().lookup_color('rl_accent')[1].red > .7))
        color = app.project_title.get_style_context().lookup_color('rl_accent')[1]
        self.assertAlmostEqual(color.red, 188/255, delta=.01)
        captured=[];app.canvas.capture_png(lambda data,error:captured.append((data,error)))
        self.assertEqual(len(captured),1);self.assertIsNone(captured[0][1])
        surface=cairo.ImageSurface.create_from_png(BytesIO(captured[0][0]));raw=bytes(surface.get_data())
        counts=Counter(raw[i:i+4] for i in range(0,len(raw),4))
        pixel=bytes((86,52,18,255) if sys.byteorder=='little' else (255,18,52,86))
        self.assertGreater(counts[pixel],surface.get_width()*surface.get_height()*.1)
        self.assertGreater(len(counts),12)
        self.assertEqual(app.project_snapshot(),before);self.assertEqual(app.document.states,states)
        self.assertEqual(app.document.token,token);self.assertIs(app.design,design);self.assertIs(app.canvas.scene,scene)

    def test_switching_presets_modes_and_reset_keeps_each_customization(self):
        app, editor = self.open_editor()
        editor.set_color('colors','accent','#123456')
        editor.cards['warm'].set_active(True);editor.set_color('colors','accent','#765432')
        app.theme_switch.set_active(True);editor.cards['slate'].set_active(True)
        editor.set_color('viewport','background','#faf0dd')
        app.theme_switch.set_active(False)
        self.assertTrue(editor.cards['warm'].get_active())
        self.assertEqual(editor.entries['colors','accent'].get_text(),'#765432')
        editor.cards['ratiolab'].set_active(True)
        self.assertEqual(themes.palette('dark',editor.config)['accent'],'#123456')
        editor.reset_colors()
        self.assertEqual(themes.palette('dark',editor.config),themes.BASE_PALETTES['dark'])
        app.theme_switch.set_active(True)
        self.assertEqual(app.canvas.palette['background'],themes.rgb('#faf0dd'))

    def test_file_roundtrip_invalid_import_and_invalid_hex_are_atomic(self):
        app, editor = self.open_editor()
        editor.cards['nord'].set_active(True);editor.set_color('colors','text','#eaf0ff')
        path=self.root/'theme.json';editor.save_file(path)
        document=json.loads(path.read_text());self.assertEqual(document['format'],'ratiolab-theme/1')
        editor.cards['warm'].set_active(True);editor.load_file(path)
        self.assertTrue(editor.cards['custom'].get_active())
        self.assertEqual(themes.palette(editor.mode,editor.config),document['colors'])
        original=deepcopy(editor.config);project=deepcopy(app.project_snapshot())
        bad=self.root/'invalid.json';bad.write_text('{"format":"project/1"}')
        with self.assertRaises(ValueError):editor.load_file(bad)
        self.assertEqual(editor.config,original)
        entry=editor.entries['colors','accent'];entry.set_text('invalid');entry.emit('activate')
        self.assertTrue(editor.error.get_visible());self.assertTrue(entry.has_css_class('error'))
        self.assertEqual(editor.config,original);self.assertEqual(app.project_snapshot(),project)
        editor.set_color('colors','accent','#c34283');editor.reset_colors()
        self.assertEqual(themes.palette(editor.mode,editor.config),document['colors'])

    def test_fresh_process_restores_theme_without_losing_unrelated_preferences(self):
        app_paths.save_preferences(custom={'keep':7},recent=['keep.json'])
        app, editor = self.open_editor();editor.cards['nord'].set_active(True)
        editor.set_color('colors','accent','#bb7733');editor.set_color('viewport','selection','#ef2468')
        editor.app.theme_switch.set_active(True);editor.cards['warm'].set_active(True)
        editor.set_color('colors','accent','#224488')
        expected=editor.config
        env=dict(os.environ);root=Path(__file__).resolve().parents[1]
        env['PYTHONPATH']=os.pathsep.join((str(root/'src'),str(root/'tests')))
        code='''import json
import app, theme_preferences as t
from gi.repository import Gio
from test_interference_gui import wait_until
a=app.ReducerApp();a.set_flags(Gio.ApplicationFlags.NON_UNIQUE);a.register(None);a.activate()
assert wait_until(lambda:a.canvas.gl is not None or a.canvas.failure)
assert a.canvas.failure is None
print(json.dumps(dict(theme=a.workspace_theme,config=a.workspace_preferences['theme_customizations'],palette=t.palette(a.workspace_theme,a.workspace_preferences['theme_customizations']))))
for w in a.get_windows():w.destroy()
'''
        result=subprocess.run([sys.executable,'-W','ignore::DeprecationWarning','-c',code],env=env,capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        restored=json.loads(result.stdout.strip().splitlines()[-1]);self.assertEqual(restored['theme'],'light')
        self.assertEqual(restored['config'],expected);self.assertEqual(restored['palette']['accent'],'#224488')
        self.assertEqual(app_paths.load_preferences()['custom'],{'keep':7})
        self.assertEqual(app_paths.load_preferences()['recent'],['keep.json'])

    def test_failed_preference_write_keeps_session_and_dialog_retirement_cleans_file_picker(self):
        app, editor = self.open_editor();before=deepcopy(app.project_snapshot())
        with patch.object(app_paths,'save_preferences',side_effect=OSError('read-only')):
            editor.cards['nord'].set_active(True);editor.set_color('colors','accent','#ccaa33')
        self.assertTrue(app.settings.error.get_visible())
        self.assertEqual(themes.palette('dark',editor.config)['accent'],'#ccaa33')
        self.assertEqual(app.project_snapshot(),before)
        self.assertEqual(app.settings.tabs['appearance'].get_parent().get_orientation(),Gtk.Orientation.VERTICAL)
        editor.choose_file(False);self.assertIsNotNone(editor.file_dialog)
        app.settings.dialog.close();pump(.05)
        self.assertFalse(editor.active);self.assertIsNone(editor.file_dialog)
        self.assertIsNone(app.settings.dialog);self.assertFalse(app.settings.handlers)

    def test_embedded_file_selection_imports_and_parent_destroy_retires_pending_chooser(self):
        app, editor = self.open_editor()
        config = themes.defaults();config['active']['light'] = 'warm'
        path = self.root/'import-theme.json'
        path.write_text(json.dumps(themes.export_theme('light', config)))
        editor.choose_file(False)
        chooser = editor.file_dialog
        chooser.set_file(Gio.File.new_for_path(str(path)))
        self.assertTrue(wait_until(lambda:chooser.get_file() is not None
            and chooser.get_file().get_path() == str(path)))
        editor.accept_file(False)
        self.assertIsNone(editor.file_dialog)
        self.assertEqual(app.workspace_theme, 'light')
        self.assertEqual(editor.config['active']['light'], 'custom')
        editor.choose_file(True)
        chooser = editor.file_dialog
        # GTK restores its initial folder asynchronously after mapping. Navigate
        # only once that restoration is complete, as a user opening it would.
        self.assertTrue(wait_until(lambda:chooser.get_current_folder() is not None))
        chooser.set_current_folder(Gio.File.new_for_path(str(self.root)))
        self.assertTrue(wait_until(lambda:chooser.get_current_folder() is not None
            and chooser.get_current_folder().get_path() == str(self.root)))
        chooser.set_current_name('export-theme.json')
        exported = self.root/'export-theme.json'
        self.assertTrue(wait_until(lambda:chooser.get_file() is not None
            and chooser.get_file().get_path() == str(exported)))
        editor.accept_file(True)
        self.assertEqual(json.loads(exported.read_text())['colors'], themes.palette('light', editor.config))
        editor.choose_file(True)
        self.assertIsNotNone(editor.file_dialog)
        app.win.destroy();pump(.1)
        self.assertFalse(editor.active);self.assertIsNone(editor.file_dialog)

    def test_native_color_palette_closes_with_settings_without_an_orphan_or_document_edit(self):
        app, editor = self.open_editor()
        before = deepcopy(app.project_snapshot())
        editor.expanders['colors'].set_expanded(True)
        self.assertTrue(editor.pickers['colors', 'accent'].activate())
        self.assertTrue(wait_until(lambda:any(w.get_mapped() and w.get_transient_for() is app.settings.dialog
                                             for w in Gtk.Window.list_toplevels())))
        app.settings.dialog.close();pump(.15)
        self.assertFalse(editor.active)
        self.assertFalse(any(w.get_mapped() and w is not app.win for w in Gtk.Window.list_toplevels()))
        self.assertEqual(app.project_snapshot(), before)
        editor.close();pump(.05)
        self.assertTrue(app.win.get_mapped())


if __name__=='__main__':unittest.main()
