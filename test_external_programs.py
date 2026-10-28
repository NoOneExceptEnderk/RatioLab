"""System programs must not inherit the frozen application's private GTK ABI."""
from contextlib import ExitStack
import ctypes
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import external_programs as external


class ChildEnvironmentTests(unittest.TestCase):
    def frozen(self, stack, root, platform='linux', original=None):
        stack.enter_context(patch.object(sys, 'frozen', True, create=True))
        stack.enter_context(patch.object(sys, '_MEIPASS', str(root), create=True))
        stack.enter_context(patch.object(sys, 'platform', platform))
        stack.enter_context(patch.object(sys, '_ratiolab_original_environment', original or {}, create=True))

    def test_source_launch_copies_environment_without_modifying_it(self):
        dirty = {'PATH': '/user/bin', 'LD_LIBRARY_PATH': '/user/lib', 'GI_TYPELIB_PATH': '/user/typelibs'}
        with patch.object(sys, 'frozen', False, create=True):
            clean = external.child_environment(dirty)
        self.assertEqual(clean, dirty)
        self.assertIsNot(clean, dirty)

    def test_linux_restores_original_libraries_and_path_only_in_child(self):
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary)/'_internal'
            self.frozen(stack, root)
            dirty = {'LD_LIBRARY_PATH': str(root)+':/user/lib', 'LD_LIBRARY_PATH_ORIG': '/user/lib',
                     'PATH': str(root)+':/usr/bin', 'PATH_ORIG': '/custom/bin:'+str(root)+':/usr/bin'}
            before = dirty.copy()
            clean = external.child_environment(dirty)
            self.assertEqual(clean['LD_LIBRARY_PATH'], '/user/lib')
            self.assertEqual(clean['PATH'], '/custom/bin:/usr/bin')
            self.assertEqual(clean['LD_LIBRARY_PATH_ORIG'], '/user/lib')
            self.assertEqual(clean['PATH_ORIG'], before['PATH_ORIG'])
            self.assertEqual(dirty, before)

    def test_runtime_hook_variables_restore_user_values_and_remove_generated_cache(self):
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary)/'_internal'
            self.frozen(stack, root, original={'GI_TYPELIB_PATH': '/user/typelibs',
                'FONTCONFIG_FILE': '/user/fonts.conf', 'GDK_PIXBUF_MODULE_FILE': None,
                'XDG_DATA_DIRS': None, 'PATH': '/user/bin:/usr/bin'})
            clean = external.child_environment({'LD_LIBRARY_PATH': str(root),
                'GI_TYPELIB_PATH': str(root/'gi_typelibs'), 'FONTCONFIG_FILE': str(root/'fonts.conf'),
                'GDK_PIXBUF_MODULE_FILE': '/tmp/generated-cache', 'XDG_DATA_DIRS': str(root/'share'),
                'PATH': str(root)})
            self.assertNotIn('LD_LIBRARY_PATH', clean)
            self.assertEqual(clean['GI_TYPELIB_PATH'], '/user/typelibs')
            self.assertEqual(clean['FONTCONFIG_FILE'], '/user/fonts.conf')
            self.assertNotIn('GDK_PIXBUF_MODULE_FILE', clean)
            self.assertNotIn('XDG_DATA_DIRS', clean)
            self.assertEqual(clean['PATH'], '/user/bin:/usr/bin')

    def test_macos_filters_frameworks_and_resources_but_keeps_system_paths(self):
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            contents = Path(temporary)/'RatioLab.app/Contents'
            self.frozen(stack, contents/'Frameworks', platform='darwin')
            clean = external.child_environment({'DYLD_LIBRARY_PATH':
                f'{contents}/Frameworks:/user/lib:{contents}/Resources', 'PATH': '/usr/bin'})
            self.assertEqual(clean['DYLD_LIBRARY_PATH'], '/user/lib')

    def test_windows_filters_semicolon_paths(self):
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary)/'_internal'
            self.frozen(stack, root, platform='win32')
            clean = external.child_environment({'PATH': f'{root};/system/bin;{root}/gi',
                                                'PYGI_DLL_PATH': str(root)})
            self.assertEqual(clean['PATH'], '/system/bin')
            self.assertNotIn('PYGI_DLL_PATH', clean)

    def test_gio_launch_context_changes_only_child_environment(self):
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary)/'_internal'
            self.frozen(stack, root, original={'GI_TYPELIB_PATH': None})
            stack.enter_context(patch.dict(os.environ, {'LD_LIBRARY_PATH': str(root),
                'LD_LIBRARY_PATH_ORIG': '/user/lib', 'GI_TYPELIB_PATH': str(root/'gi_typelibs'),
                'PATH': '/usr/bin'}, clear=True))
            before = dict(os.environ)
            context = Mock()
            self.assertIs(external.configure_launch_context(context), context)
            context.setenv.assert_called_once_with('LD_LIBRARY_PATH', '/user/lib')
            context.unsetenv.assert_called_once_with('GI_TYPELIB_PATH')
            self.assertEqual(dict(os.environ), before)


class WindowsDllDirectoryTests(unittest.TestCase):
    def test_directory_is_reset_and_restored_even_when_spawn_raises(self):
        previous = 'C:\\RatioLab with spaces\\_internal'
        def get_directory(length, buffer):
            if buffer is not None:
                buffer.value = previous
                return len(previous)
            return len(previous)+1
        kernel = SimpleNamespace(GetDllDirectoryW=Mock(side_effect=get_directory),
                                 SetDllDirectoryW=Mock(return_value=1))
        with patch.object(sys, 'platform', 'win32'), \
                patch.object(sys, 'frozen', True, create=True), \
                patch.object(external, '_kernel32', return_value=kernel):
            for failure in (False, True):
                with self.subTest(failure=failure):
                    kernel.SetDllDirectoryW.reset_mock()
                    try:
                        with external.system_library_search():
                            kernel.SetDllDirectoryW.assert_called_once_with(None)
                            if failure:
                                raise OSError('spawn failed')
                    except OSError as error:
                        self.assertTrue(failure)
                        self.assertEqual(str(error), 'spawn failed')
                    self.assertEqual([call.args[0] for call in kernel.SetDllDirectoryW.call_args_list],
                                     [None, previous])

    def test_kernel32_declarations_use_pointer_sized_wide_string_parameters(self):
        kernel = SimpleNamespace(GetDllDirectoryW=Mock(), SetDllDirectoryW=Mock())
        with patch.object(ctypes, 'WinDLL', return_value=kernel, create=True) as dll:
            self.assertIs(external._kernel32(), kernel)
        dll.assert_called_once_with('kernel32', use_last_error=True)
        self.assertEqual(kernel.GetDllDirectoryW.argtypes, [ctypes.c_ulong, ctypes.c_wchar_p])
        self.assertEqual(kernel.SetDllDirectoryW.argtypes, [ctypes.c_wchar_p])


class IntegrationTests(unittest.TestCase):
    def test_cad_spawn_uses_clean_child_environment_and_scoped_dll_search(self):
        import connection
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary)/'CAD with spaces.exe'
            executable.touch()
            guard = Mock()
            guard.__enter__ = Mock()
            guard.__exit__ = Mock(return_value=False)
            with patch.dict(os.environ, {'SOLIDCRAFT_EXECUTABLE': str(executable)}), \
                    patch.object(connection, 'Client') as client, \
                    patch.object(connection.subprocess, 'Popen') as launch, \
                    patch.object(connection.time, 'sleep'), \
                    patch.object(connection, 'child_environment', return_value={'PATH': '/system/bin'}), \
                    patch.object(connection, 'system_library_search', return_value=guard):
                client.return_value.__enter__.side_effect = [connection.ControlError('offline'), Mock()]
                launch.return_value.poll.return_value = None
                connection.connect_or_launch(Path(temporary)/'logs')
            self.assertEqual(launch.call_args.kwargs['env'], {'PATH': '/system/bin'})
            guard.__enter__.assert_called_once()
            guard.__exit__.assert_called_once()

    def test_folder_launch_uses_gio_context_and_scoped_library_search(self):
        import gui_workflow
        with tempfile.TemporaryDirectory() as temporary:
            app = SimpleNamespace(output_dir=Path(temporary)/'exports with spaces Ω', win=Mock(), status_text=Mock())
            context = app.win.get_display.return_value.get_app_launch_context.return_value
            with patch.object(sys, 'frozen', False, create=True), \
                    patch.object(external, 'configure_launch_context', return_value=context) as configure, \
                    patch.object(external, 'system_library_search') as guard, \
                    patch.object(gui_workflow.Gio.AppInfo, 'launch_default_for_uri') as launch:
                gui_workflow.open_output(app)
            configure.assert_called_once_with(context)
            launch.assert_called_once_with(app.output_dir.as_uri(), context)
            guard.return_value.__enter__.assert_called_once()
            guard.return_value.__exit__.assert_called_once()
            app.status_text.assert_not_called()

    def test_frozen_linux_folder_opener_uses_system_environment_and_unicode_path(self):
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(sys, 'platform', 'linux'), \
                patch.object(sys, 'frozen', True, create=True), \
                patch.object(external, 'child_environment', return_value={'PATH': '/system/bin'}) as clean, \
                patch.object(external.shutil, 'which', return_value='/system/bin/xdg-open') as which, \
                patch.object(external.subprocess, 'Popen') as launch:
            folder = Path(temporary)/'exports with spaces Ω'
            external.open_folder(folder, Mock())
            clean.assert_called_once()
            which.assert_called_once_with('xdg-open', path='/system/bin')
            self.assertEqual(launch.call_args.args[0], ['/system/bin/xdg-open', folder.as_uri()])
            self.assertEqual(launch.call_args.kwargs['env'], {'PATH': '/system/bin'})
            self.assertTrue(launch.call_args.kwargs['start_new_session'])

    def test_frozen_linux_link_is_a_single_argument_without_shell_expansion(self):
        uri = 'https://example.invalid/datasheet?bearing=608&text=$(literal)'
        with patch.object(sys, 'platform', 'linux'), \
                patch.object(sys, 'frozen', True, create=True), \
                patch.object(external, 'child_environment', return_value={'PATH': '/system/bin'}), \
                patch.object(external.shutil, 'which', return_value='/system/bin/xdg-open'), \
                patch.object(external.subprocess, 'Popen') as launch:
            external.launch_uri(uri, Mock())
        self.assertEqual(launch.call_args.args[0], ['/system/bin/xdg-open', uri])
        self.assertNotIn('shell', launch.call_args.kwargs)

    def test_link_button_suppresses_default_handler_even_if_launch_fails(self):
        import gui_workflow
        app = SimpleNamespace(win=Mock(), status_text=Mock())
        with patch.object(external, 'launch_uri', side_effect=OSError('handler unavailable')) as launch:
            self.assertTrue(gui_workflow.open_link(app, 'https://example.invalid/datasheet'))
        launch.assert_called_once_with('https://example.invalid/datasheet',
                                     app.win.get_display.return_value.get_app_launch_context.return_value)
        app.status_text.assert_called_once_with('Could not open the link: handler unavailable')


if __name__ == '__main__':
    unittest.main(verbosity=2)
