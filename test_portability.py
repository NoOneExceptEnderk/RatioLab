"""Portable paths and GL dispatch; no display or live CAD required."""
import ctypes as C
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import app_paths
import gl_loader
import connection


class UserPathsTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        environment = patch.dict(os.environ, {'XDG_CONFIG_HOME': str(self.root/'config'),
                                              'XDG_DATA_HOME': str(self.root/'data'),
                                              'APPDATA': str(self.root/'roaming'),
                                              'LOCALAPPDATA': str(self.root/'local')})
        environment.start()
        self.addCleanup(environment.stop)
        # macOS uses ~/Library rather than XDG/AppData. Isolate home on every
        # host so preferences from one test cannot affect a later test or user.
        home = patch.object(Path, 'home', return_value=self.root)
        home.start()
        self.addCleanup(home.stop)

    def test_platform_directories(self):
        for platform, config, data in [
            ('linux', self.root/'config/ratiolab', self.root/'data/ratiolab'),
            ('win32', self.root/'roaming/RatioLab', self.root/'local/RatioLab'),
            ('darwin', self.root/'Library/Application Support/RatioLab', self.root/'Library/Application Support/RatioLab'),
        ]:
            with self.subTest(platform=platform), patch('app_paths.sys.platform', platform), patch.object(Path, 'home', return_value=self.root):
                self.assertEqual(app_paths.config_dir(), config)
                self.assertEqual(app_paths.data_dir(), data)

    @patch('app_paths.sys.platform', 'linux')
    def test_relative_xdg_is_ignored(self):
        with patch.dict(os.environ, {'XDG_CONFIG_HOME': 'relative'}), patch.object(Path, 'home', return_value=self.root):
            self.assertEqual(app_paths.config_dir(), self.root/'.config/ratiolab')

    def test_legacy_preferences_are_read_and_migrated_without_writing_source(self):
        legacy = self.root/'source'
        legacy.mkdir()
        original = json.dumps({'output_dir': str(self.root/'old exports'), 'mode': 'legacy'})
        (legacy/'preferenze-ui.json').write_text(original)
        for platform in ('linux', 'win32', 'darwin'):
            with self.subTest(platform=platform), patch('app_paths.sys.platform', platform):
                self.assertTrue(app_paths.config_dir().is_relative_to(self.root))
                self.assertEqual(app_paths.saved_output_dir(legacy), self.root/'old exports')
                app_paths.save_preferences(legacy_root=legacy, output_dir=str(self.root/'new exports'))
                self.assertEqual(app_paths.saved_output_dir(legacy), self.root/'new exports')
                self.assertNotIn('mode', app_paths.load_preferences())
                self.assertEqual((legacy/'preferenze-ui.json').read_text(), original)

    def test_invalid_preferences_and_failed_atomic_replace(self):
        app_paths.save_preferences(output_dir='relative')
        self.assertEqual(app_paths.saved_output_dir(), app_paths.default_output_dir())
        target = app_paths.config_dir()/'preferenze-ui.json'
        previous = target.read_bytes()
        with patch('app_paths.os.replace', side_effect=OSError('read only')):
            with self.assertRaises(OSError):
                app_paths.save_preferences(output_dir=str(self.root/'cannot save'))
        self.assertEqual(target.read_bytes(), previous)
        self.assertEqual(list(target.parent.glob('.preferences-*')), [])
        target.write_text('[]')
        self.assertEqual(app_paths.load_preferences(), {})

    def test_resources_independent_of_cwd_and_reject_escape(self):
        current = Path.cwd()
        try:
            os.chdir(self.root)
            self.assertTrue(app_paths.resource_path('branding/ratiolab-icon.png').is_file())
            self.assertIsInstance(json.loads(app_paths.resource_path('catalogo-cuscinetti.json').read_text()), (dict,list))
            for path in ('../preferenze-ui.json', str(self.root/'absolute')):
                with self.assertRaises(ValueError):
                    app_paths.resource_path(path)
        finally:
            os.chdir(current)

    def test_asset_default_is_user_data(self):
        from geometry import generate
        design = generate('helical')
        self.assertEqual(design.asset_folder(), app_paths.default_output_dir()/'solidi'/design.token)

    @patch('connection.sys.platform', 'win32')
    def test_nonlinux_cad_requires_explicit_control_location(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(connection.ControlError, 'SOLIDCRAFT_CONTROL_DIR'):
                connection.control_directory()

    @patch('connection.sys.platform', 'win32')
    def test_missing_cad_control_configuration_never_launches(self):
        with patch.dict(os.environ, {'SOLIDCRAFT_EXECUTABLE': 'configured.exe'}, clear=True), \
                patch('connection.subprocess.Popen') as launch:
            with self.assertRaisesRegex(connection.ControlConfigurationError, 'SOLIDCRAFT_CONTROL_DIR'):
                connection.connect_or_launch(self.root)
            launch.assert_not_called()

    @patch('connection.Client')
    @patch('connection.sys.platform', 'darwin')
    def test_nonlinux_cad_never_guesses_an_appimage(self, client):
        client.return_value.__enter__.side_effect = connection.ControlError('offline')
        with patch.dict(os.environ, {}, clear=True), patch('connection.subprocess.Popen') as launch:
            with self.assertRaisesRegex(connection.ControlError, 'No SolidCraft executable'):
                connection.connect_or_launch(self.root)
            launch.assert_not_called()

    def test_configured_cad_launch_on_windows_and_macos_keeps_paths_intact(self):
        executable = self.root/'CAD with spaces'/'SolidCraft.exe'
        executable.parent.mkdir()
        executable.touch()
        control = self.root/'control tokens'
        control.mkdir()
        for platform in ('win32', 'darwin'):
            with self.subTest(platform=platform), patch('connection.sys.platform', platform), \
                    patch.dict(os.environ, {'SOLIDCRAFT_EXECUTABLE': str(executable),
                                            'SOLIDCRAFT_CONTROL_DIR': str(control)}), \
                    patch('connection.Client') as client, \
                    patch('connection.APPIMAGE') as appimage, \
                    patch('connection.time.sleep'), \
                    patch('connection.subprocess.Popen') as launch:
                self.assertEqual(connection.control_directory(), control)
                client.return_value.__enter__.side_effect = [connection.ControlError('offline'), Mock()]
                launch.return_value.poll.return_value = None
                self.assertIn('launched and connected', connection.connect_or_launch(self.root/'logs'))
                self.assertEqual(launch.call_args.args[0], [str(executable), '--control', '7878'])
                self.assertEqual(launch.call_args.kwargs['start_new_session'], platform != 'win32')
                appimage.is_file.assert_not_called()
                self.assertEqual(client.return_value.__enter__.call_count, 2)


class DispatchTests(unittest.TestCase):
    def test_old_gtk_fails_before_ui_setup(self):
        gtk = SimpleNamespace(check_version=lambda *args: 'GTK version too old')
        with self.assertRaisesRegex(RuntimeError, 'GTK 4.12'):
            app_paths.require_gtk_version(gtk)

    def test_real_export_is_read_as_pointer_data(self):
        library = gl_loader.load_epoxy()
        function = gl_loader.bind_function(library, 'BufferData', None, [C.c_uint, C.c_ssize_t, C.c_void_p, C.c_uint])
        address = C.c_void_p.in_dll(library, 'epoxy_glBufferData').value
        self.assertEqual(C.cast(function, C.c_void_p).value, address)
        self.assertIs(function._library, library)
        self.assertEqual(function.argtypes[1], C.c_ssize_t)
        self.assertEqual(function.argtypes[2], C.c_void_p)

    def test_pointer_round_trip_is_not_truncated(self):
        factory = C.WINFUNCTYPE if os.name == 'nt' else C.CFUNCTYPE
        callback = factory(C.c_int, C.c_int)(lambda value: value+4)
        pointer_type = C.c_void_p
        address = C.cast(callback, pointer_type).value
        class Pointer:
            def __new__(cls, value):
                return pointer_type(value)
            @staticmethod
            def in_dll(library, symbol):
                return SimpleNamespace(value=address)
        with patch('gl_loader.C.c_void_p', Pointer):
            function = gl_loader.bind_function(object(), 'Test', C.c_int, [C.c_int])
            self.assertEqual(function(38), 42)

    def test_missing_and_invalid_dispatch_pointers_fail(self):
        library = gl_loader.load_epoxy()
        with self.assertRaisesRegex(RuntimeError, 'unavailable'):
            gl_loader.bind_function(library, 'NotAnOpenGLFunction', None, [])
        real_pointer = C.c_void_p
        for value in (None, 0, 1, 2, 3, real_pointer(-1).value):
            class Pointer:
                def __new__(cls, value):
                    return real_pointer(value)
                @staticmethod
                def in_dll(library, symbol):
                    return SimpleNamespace(value=value)
            with self.subTest(value=value), patch('gl_loader.C.c_void_p', Pointer):
                with self.assertRaisesRegex(RuntimeError, 'invalid'):
                    gl_loader.bind_function(library, 'Test', None, [])


class DiagnosticGuiTests(unittest.TestCase):
    def test_diagnostic_observes_completed_render_and_nonblank_pixels(self):
        app_paths.prepare_native_runtime()
        import gi
        gi.require_version('Gtk', '4.0')
        from gi.repository import Gtk, Gdk
        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            self.skipTest('GTK display required')
        from ratiolab_cli import diagnose
        result = diagnose(gui=True)
        self.assertEqual(result['preview'], 'rendered')
        self.assertTrue(result['framebuffer_has_geometry'])
        self.assertGreaterEqual(result['opengl_version'], 33)


if __name__ == '__main__':
    unittest.main(verbosity=2)
