"""Installer lifecycle and frozen paths; runtime bundles have separate real GL tests."""
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

import app_paths
import gl_loader
import install_desktop

ROOT = Path(__file__).resolve().parent


class GtkAssetsTests(unittest.TestCase):
    def test_gtk_bundle_excludes_icons_from_other_installed_applications(self):
        info = SimpleNamespace(available=True, version='4.0',
                               collect_typelib_data=lambda: ([], [], []))
        files = {
            ('icons', 'Adwaita'): [('/native/share/icons/Adwaita/dialog-error.svg', 'share/icons/Adwaita')],
            ('icons', 'hicolor'): [('/native/share/icons/hicolor/index.theme', 'share/icons/hicolor'),
                                   ('/native/share/icons/hicolor/icon-theme.cache', 'share/icons/hicolor'),
                                   ('/native/share/icons/hicolor/48x48/apps/google-chrome.png', 'share/icons/hicolor/48x48/apps')],
            ('glib-2.0', 'schemas'): [('/native/org.gtk.gtk4.Settings.gschema.xml', 'share/glib-2.0/schemas')],
        }
        gi = ModuleType('PyInstaller.utils.hooks.gi')
        gi.GiModuleInfo = lambda *args, **kwargs: info
        gi.collect_glib_share_files = lambda *args: files[args]
        with patch.dict(sys.modules, {'PyInstaller.utils.hooks.gi': gi}):
            hook = runpy.run_path(str(ROOT/'packaging/hooks/hook-gi.repository.Gtk.py'))['hook']
            api = Mock()
            hook(api)
        sources = [source for source, _ in api.add_datas.call_args.args[0]]
        self.assertTrue(any(source.endswith('dialog-error.svg') for source in sources))
        self.assertTrue(any(source.endswith('index.theme') for source in sources))
        self.assertFalse(any('google-chrome' in source or source.endswith('icon-theme.cache') for source in sources))


class FrozenPathsTests(unittest.TestCase):
    def test_bundle_never_searches_host_epoxy(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(sys, 'frozen', True, create=True), \
                patch.object(sys, '_MEIPASS', folder, create=True), \
                patch('gl_loader.ctypes.util.find_library', side_effect=AssertionError('host lookup')):
            candidates = list(gl_loader.library_candidates())
            self.assertTrue(candidates)
            self.assertTrue(all(Path(item).is_relative_to(folder) for item in candidates))

    def test_frozen_windows_dll_path_replaces_developer_runtime(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(sys, 'frozen', True, create=True), \
                patch.object(sys, '_MEIPASS', folder, create=True), patch.object(sys, 'platform', 'win32'), \
                patch.object(app_paths, '_dll_directories', []), \
                patch.dict(os.environ, {'PYGI_DLL_PATH': '/old/msys2/path'}), \
                patch.object(os, 'add_dll_directory', create=True) as add:
            app_paths.prepare_native_runtime()
            self.assertEqual(os.environ['PYGI_DLL_PATH'], folder)
            add.assert_called_once_with(folder)
            app_paths.prepare_native_runtime()
            add.assert_called_once()

    def test_frozen_launcher_runs_the_executable_without_python_flags(self):
        executable = '/tmp/RatioLab space/RatioLab'
        with patch.object(sys, 'frozen', True, create=True), patch.object(sys, 'executable', executable):
            _, text = install_desktop.launcher()
        self.assertIn('Exec="'+executable+'"\n', text)
        self.assertNotIn('-m', text)


@unittest.skipUnless(sys.platform.startswith('linux'), 'Linux installer lifecycle')
class LinuxInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='ratiolab installer tests ')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.package = self.root/'download'
        self.payload = self.package/'RatioLab'
        self.payload.mkdir(parents=True)
        self.destination = self.root/'installed app Ω'
        self.environment = os.environ | {'HOME': str(self.root/'home'),
                                         'XDG_DATA_HOME': str(self.root/'data'),
                                         'XDG_CONFIG_HOME': str(self.root/'config')}
        shutil.copy2(ROOT/'scripts/install-bundle-linux.sh', self.package/'install.sh')
        shutil.copy2(ROOT/'scripts/uninstall-bundle-linux.sh', self.package/'uninstall.sh')
        # A controlled command fixture tests installer rollback/destruction
        # independently of the real GTK/Python payload and its display tests.
        executable = self.payload/'RatioLab'
        executable.write_text('''#!/bin/sh
case "$1" in
  --self-test) test ! -f "$(dirname -- "$0")/fail-check" ;;
  --install-desktop)
    mkdir -p "$XDG_DATA_HOME/applications"
    printf 'Exec="%s"\\n' "$0" > "$XDG_DATA_HOME/applications/local.solidcraft.reducers.desktop" ;;
  *) exit 2 ;;
esac
''')
        executable.chmod(0o755)

    def install(self):
        paths = sorted(str(path.relative_to(self.payload)) for path in self.payload.rglob('*') if path.is_file())
        (self.package/'installed-files.txt').write_text('\n'.join(paths)+'\n')
        return subprocess.run(['sh', str(self.package/'install.sh'), '--yes', '--destination', str(self.destination)],
                              env=self.environment, capture_output=True, text=True)

    def test_install_update_and_uninstall_keep_projects_and_preferences(self):
        projects = self.root/'data/ratiolab/exports/project.stl'
        prefs = self.root/'config/ratiolab/preferenze-ui.json'
        for path in (projects, prefs):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('keep me')
        (self.payload/'version').write_text('one')
        first = self.install()
        self.assertEqual(first.returncode, 0, first.stderr)
        (self.payload/'version').write_text('two')
        second = self.install()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual((self.destination/'version').read_text(), 'two')
        removed = subprocess.run(['sh', str(self.destination/'uninstall.sh')], env=self.environment,
                                 capture_output=True, text=True)
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertFalse(self.destination.exists())
        self.assertFalse((self.root/'data/applications/local.solidcraft.reducers.desktop').exists())
        for path in (projects, prefs):
            self.assertEqual(path.read_text(), 'keep me')

    def test_unrelated_destination_is_never_overwritten(self):
        self.destination.mkdir()
        sentinel = self.destination/'personal-file'
        sentinel.write_text('keep me')
        (self.destination/'.ratiolab-installation').write_text('another application')
        self.assertNotEqual(self.install().returncode, 0)
        self.assertEqual(sentinel.read_text(), 'keep me')

    def test_failed_runtime_check_preserves_previous_installation(self):
        (self.payload/'version').write_text('working')
        self.assertEqual(self.install().returncode, 0)
        (self.payload/'version').write_text('broken')
        (self.payload/'fail-check').touch()
        self.assertNotEqual(self.install().returncode, 0)
        self.assertEqual((self.destination/'version').read_text(), 'working')
        self.assertEqual(list(self.root.glob('.ratiolab-install.*')), [])

    def test_projects_inside_application_folder_survive_update_and_removal(self):
        self.assertEqual(self.install().returncode, 0)
        project = self.destination/'my projects'/'keep.stl'
        project.parent.mkdir()
        project.write_text('personal project')
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(project.read_text(), 'personal project')
        removed = subprocess.run(['sh', str(self.destination/'uninstall.sh')], env=self.environment,
                                 capture_output=True, text=True)
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertFalse((self.destination/'RatioLab').exists())
        self.assertEqual(project.read_text(), 'personal project')


if __name__ == '__main__':
    unittest.main(verbosity=2)
