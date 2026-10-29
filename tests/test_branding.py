# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Native application identity, resource lookup and launcher compatibility."""
import ctypes
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import app_paths
import install_desktop

ROOT = Path(__file__).resolve().parents[1]


class ApplicationIdentityTests(unittest.TestCase):
    def test_source_registration_dry_run_resolves_actual_icon_without_writing(self):
        with tempfile.TemporaryDirectory() as temporary, \
                patch.dict(os.environ, {'XDG_DATA_HOME': temporary}), \
                patch.object(install_desktop.sys, 'platform', 'linux'), \
                patch.object(install_desktop, 'desktop_directory', return_value=None), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            install_desktop.main(['--dry-run'])
            text = output.getvalue()
            self.assertIn(str(Path(temporary)/'applications'/f'{app_paths.APP_ID}.desktop'), text)
            self.assertIn(str(ROOT/'src/app.py'), text)
            icon_line = next(line for line in text.splitlines() if line.startswith('Icon='))
            self.assertTrue(Path(icon_line.removeprefix('Icon=')).is_file())
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_windows_identity_matches_installer_shortcuts_before_gui(self):
        identify = Mock(return_value=0)
        shell = Mock(SetCurrentProcessExplicitAppUserModelID=identify)
        with patch.object(app_paths.sys, 'platform', 'win32'), \
                patch.object(ctypes, 'WinDLL', return_value=shell, create=True) as load:
            app_paths.prepare_application_identity()
        load.assert_called_once_with('shell32')
        identify.assert_called_once_with(app_paths.APP_ID)
        self.assertEqual(identify.argtypes, [ctypes.c_wchar_p])
        self.assertIs(identify.restype, ctypes.c_long)
        shortcuts = (ROOT/'scripts/package-windows.iss').read_text()
        self.assertEqual(shortcuts.count(f'AppUserModelID: "{app_paths.APP_ID}"'), 2)

    def test_non_windows_does_not_access_shell_and_failure_does_not_block_gui(self):
        with patch.object(app_paths.sys, 'platform', 'linux'), \
                patch.object(ctypes, 'WinDLL', create=True) as load:
            app_paths.prepare_application_identity()
            load.assert_not_called()
        for result in (-2147467259, OSError('shell unavailable')):
            identify = Mock(return_value=result) if isinstance(result, int) else Mock(side_effect=result)
            with patch.object(app_paths.sys, 'platform', 'win32'), \
                    patch.object(ctypes, 'WinDLL', return_value=Mock(SetCurrentProcessExplicitAppUserModelID=identify), create=True), \
                    self.assertLogs('app_paths', level='WARNING') as logs:
                app_paths.prepare_application_identity()
            self.assertIn('taskbar identity', logs.output[0])

    def test_launchers_match_canonical_window_identity_for_each_layout(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            source = folder/'source with spaces'
            (source/'src').mkdir(parents=True)
            (source/'launch.sh').touch()
            cases = [(source/'src', False, 'app.py'),
                     (folder/'site-packages', False, '"-m" "ratiolab_cli"'),
                     (folder/'_internal', True, 'Exec="/native path/RatioLab"')]
            for module_root, frozen, command in cases:
                with self.subTest(layout=module_root), \
                        patch.object(install_desktop, 'ROOT', module_root), \
                        patch.object(install_desktop.sys, 'frozen', frozen, create=True), \
                        patch.object(install_desktop.sys, 'executable', '/native path/RatioLab'):
                    app_id, contents = install_desktop.launcher()
                self.assertEqual(app_id, app_paths.APP_ID)
                self.assertIn(f'StartupWMClass={app_id}\n', contents)
                self.assertIn(command, contents)
                self.assertIn(f'Icon={app_paths.resource_path("branding/ratiolab-icon.png")}\n', contents)

    def test_approved_artwork_and_native_icon_resources_are_preserved(self):
        provenance = json.loads((ROOT/'packaging/icons/source.json').read_text())
        source = app_paths.resource_path('branding/ratiolab-icon.png')
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), provenance['sha256'])
        self.assertTrue(app_paths.resource_path('icons/hicolor/index.theme').is_file())
        for size in (128, 256):
            png = app_paths.resource_path(f'icons/hicolor/{size}x{size}/apps/{app_paths.APP_ID}.png').read_bytes()
            self.assertEqual(png[:8], b'\x89PNG\r\n\x1a\n')
            self.assertEqual(int.from_bytes(png[16:20], 'big'), size)
            self.assertEqual(int.from_bytes(png[20:24], 'big'), size)


class WindowBrandingTests(unittest.TestCase):
    def test_realized_workspace_provides_native_window_icons(self):
        app_paths.prepare_native_runtime()
        import gi
        gi.require_version('Gtk', '4.0')
        from gi.repository import Gtk, Gdk, Gio, GLib
        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            self.skipTest('GTK display required')
        import app
        with tempfile.TemporaryDirectory() as temporary, \
                patch.dict(os.environ, dict(XDG_CONFIG_HOME=temporary+'/config', XDG_DATA_HOME=temporary+'/data',
                                            APPDATA=temporary+'/roaming', LOCALAPPDATA=temporary+'/local')), \
                patch.object(app, 'BASE', Path(temporary)), \
                patch.object(app, 'GENERATED', Path(temporary)/'exports'):
            application = app.ReducerApp()
            application.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
            application.register(None)
            try:
                application.activate()
                self.assertEqual(application.get_application_id(), app_paths.APP_ID)
                self.assertEqual(GLib.get_prgname(), app_paths.APP_ID)
                self.assertEqual(application.win.get_icon_name(), app_paths.APP_ID)
                self.assertTrue(application.win.get_realized())
                theme = Gtk.IconTheme.get_for_display(application.win.get_display())
                self.assertIn(128, theme.get_icon_sizes(app_paths.APP_ID))
                for size in (128, 256):
                    paintable = theme.lookup_icon(app_paths.APP_ID, None, size, 1, Gtk.TextDirection.NONE, 0)
                    icon = Path(paintable.get_file().get_path())
                    self.assertEqual(icon, app_paths.resource_path(f'icons/hicolor/{size}x{size}/apps/{app_paths.APP_ID}.png'))
                    texture = Gdk.Texture.new_from_filename(str(icon))
                    self.assertEqual((texture.get_width(), texture.get_height()), (size, size))
            finally:
                for window in application.get_windows():
                    window.destroy()


if __name__ == '__main__':
    unittest.main()
