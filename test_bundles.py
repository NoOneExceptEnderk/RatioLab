"""Bundle integrity and bootstrap tests; real native builds have separate smoke tests."""
import importlib.util
import io
import json
import os
from pathlib import Path
import plistlib
import runpy
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load('bundle_builder_test', ROOT/'scripts/build-bundle.py')
support = load('bundle_support_test', ROOT/'packaging/bundle_support.py')


class BundleIntegrityTests(unittest.TestCase):
    def test_macos_minimum_uses_native_load_commands_and_normalizes_versions(self):
        with tempfile.TemporaryDirectory() as temporary:
            app = Path(temporary)/'RatioLab.app'
            native = app/'Contents/Frameworks/libsample.dylib'
            native.parent.mkdir(parents=True)
            native.write_bytes(b'\xfe\xed\xfa\xcf' + b'unit test header')
            plist = app/'Contents/Info.plist'
            plist.write_bytes(plistlib.dumps({'LSMinimumSystemVersion': '14.0'}))
            commands = 'cmd LC_ID_DYLIB\n version 900.0.0\ncmd LC_BUILD_VERSION\n minos 15.0.0\n'
            with patch.object(builder.subprocess, 'check_output', return_value=commands):
                with self.assertRaisesRegex(RuntimeError, 'requires macOS 15.0.0'):
                    builder.minimum_macos(app)
                plist.write_bytes(plistlib.dumps({'LSMinimumSystemVersion': '15.0'}))
                self.assertEqual(builder.minimum_macos(app), '15.0')

    def test_inventory_detects_mutation_and_external_links(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)/'app'
            root.mkdir()
            data = root/'runtime.dat'
            data.write_bytes(b'original')
            original = builder.inventory(root)
            data.write_bytes(b'changed')
            self.assertNotEqual(builder.inventory(root), original)
            if os.name != 'nt':
                (root/'external').symlink_to(Path(temporary)/'elsewhere')
                with self.assertRaisesRegex(RuntimeError, 'External symlink'):
                    builder.inventory(root)

    def test_inventory_rejects_personal_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            (Path(temporary)/'preferenze-ui.json').write_text('{}')
            with self.assertRaisesRegex(RuntimeError, 'Personal data'):
                builder.inventory(temporary)

    def test_smoke_environment_cannot_find_developer_python_gtk(self):
        dirty = dict(PATH='/developer/msys2/bin', PYTHONPATH='/checkout',
                     PYTHONHOME='/python', GI_TYPELIB_PATH='/developer/gtk',
                     PYGI_DLL_PATH='/developer/dlls', LD_LIBRARY_PATH='/developer/libs',
                     DYLD_LIBRARY_PATH='/developer/Homebrew')
        with patch.dict(os.environ, dirty):
            clean = builder.sanitized_environment(Path('/bundle'))
        for name in dirty:
            if name == 'PATH':
                self.assertNotIn('developer', clean[name])
            else:
                self.assertNotIn(name, clean)


class BootstrapTests(unittest.TestCase):
    def test_runtime_hook_uses_bundle_paths_only(self):
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(sys, 'frozen', True, create=True), \
                patch.object(sys, '_MEIPASS', temporary, create=True), \
                patch.object(sys, '_ratiolab_original_environment', {}, create=True), \
                patch.object(sys, 'platform', 'linux'), patch.dict(os.environ, {}, clear=True):
            runpy.run_path(str(ROOT/'packaging/runtime.py'))
            for key in ('GI_TYPELIB_PATH', 'GSETTINGS_SCHEMA_DIR', 'FONTCONFIG_FILE', 'GIO_MODULE_DIR'):
                self.assertTrue(Path(os.environ[key]).is_relative_to(temporary))

    def test_windowed_entrypoint_writes_requested_report_and_exitcode(self):
        entry = load('bundle_entrypoint_test', ROOT/'packaging/entrypoint.py')
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary)/'report with spaces Ω.json'
            def run(args):
                self.assertEqual(args, ['--self-test'])
                print(json.dumps({'self_test': 'passed'}))
                return 0
            with patch('ratiolab_cli.main', side_effect=run), \
                    patch.object(sys, 'argv', ['RatioLab.exe', '--self-test', '--report', str(report)]), \
                    patch.object(sys, 'stdout', None), patch.object(sys, 'stderr', None):
                self.assertEqual(entry.main(), 0)
            self.assertEqual(json.loads(report.read_text())['self_test'], 'passed')


class NativeNoticesTests(unittest.TestCase):
    def test_typelib_without_active_analysis_stays_unmapped_without_querying_gi(self):
        # Provide only a fake config module: neither PyInstaller nor GI needs to
        # be installed, and querying GI before checking workpath would fail.
        package = ModuleType('PyInstaller')
        package.__path__ = []
        config = ModuleType('PyInstaller.config')
        for configuration in ({}, {'workpath': ''}, {'workpath': None}):
            config.CONF = configuration
            with self.subTest(configuration=configuration), patch.dict(sys.modules, {
                    'PyInstaller': package, 'PyInstaller.config': config,
                    'PyInstaller.compat': None, 'PyInstaller.utils.hooks.gi': None}):
                self.assertIsNone(support._typelib_build_inputs('Gtk', '4.0'))
                with patch.object(support.sys, 'platform', 'darwin'):
                    self.assertIsNone(support.derived_typelib_component(
                        'gi_typelibs/Gtk-4.0.typelib', '/untrusted/Gtk-4.0.typelib'))
        with patch.dict(sys.modules, {'PyInstaller': None, 'PyInstaller.config': None}):
            self.assertIsNone(support._typelib_build_inputs('Gtk', '4.0'))

    def test_darwin_recompiled_typelib_requires_exact_source_recipe_and_owner(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prefix = root/'native'
            original = prefix/'lib/girepository-1.0/Gtk-4.0.typelib'
            original.parent.mkdir(parents=True)
            original.write_bytes(b'original typelib fixture')
            gir = prefix/'share/gir-1.0/Gtk-4.0.gir'
            gir.parent.mkdir(parents=True)
            gir.write_text('<namespace name="Gtk" version="4.0"\n'
                           ' shared-library="/opt/homebrew/lib/libgtk-4.1.dylib,libdep.dylib">\n</namespace>\n')
            work = root/'pyinstaller'
            work.mkdir()
            generated = work/'Gtk-4.0.typelib'
            generated.write_bytes(b'relocated typelib fixture')
            generated_gir = work/'Gtk-4.0.gir'
            rewritten = '<namespace name="Gtk" version="4.0"\n' \
                        ' shared-library="@loader_path/libgtk-4.1.dylib,@loader_path/libdep.dylib">\n</namespace>\n'
            generated_gir.write_text(rewritten)
            component = dict(name='gtk4', version='4.22.4', provider='Homebrew')
            with patch.object(support.sys, 'platform', 'darwin'), \
                    patch.object(support, '_typelib_build_inputs',
                                 return_value=(original, prefix/'python/Versions/3.14', work)), \
                    patch.object(support, 'component_for_binary',
                                 side_effect=lambda path: component if Path(path) in (original, gir) else None):
                owner, derived = support.derived_typelib_component('gi_typelibs/Gtk-4.0.typelib', generated)
                self.assertEqual(owner, component)
                self.assertEqual(derived['from'], 'share/gir-1.0/Gtk-4.0.gir')
                self.assertEqual(len(derived['source_sha256']), 64)
                # An identically named file outside Analysis.workpath is not trusted.
                self.assertIsNone(support.derived_typelib_component('gi_typelibs/Gtk-4.0.typelib', original))
                generated_gir.write_text(rewritten.replace('libdep.dylib', 'unrelated.dylib'))
                self.assertIsNone(support.derived_typelib_component('gi_typelibs/Gtk-4.0.typelib', generated))
                generated_gir.write_text(rewritten)
                with patch.object(support, 'component_for_binary', return_value=None):
                    self.assertIsNone(support.derived_typelib_component('gi_typelibs/Gtk-4.0.typelib', generated))
                with patch.object(support, 'component_for_binary', side_effect=[
                        component, dict(component, name='another-owner')]):
                    self.assertIsNone(support.derived_typelib_component('gi_typelibs/Gtk-4.0.typelib', generated))

    def test_generated_icon_cache_uses_only_its_adjacent_theme_owner(self):
        with tempfile.TemporaryDirectory() as temporary:
            theme = Path(temporary)/'share/icons/Adwaita'
            theme.mkdir(parents=True)
            definition = theme/'index.theme'
            definition.write_text('[Icon Theme]\nName=Adwaita\n')
            cache = theme/'icon-theme.cache'
            cache.write_bytes(b'generated cache fixture')
            license_file = Path(temporary)/'LICENSE'
            license_file.write_text('License test fixture')
            component = dict(name='adwaita-icon-theme', version='1', provider='dpkg',
                             source='https://example.invalid/upstream', license_declarations=['example'],
                             _licenses=[license_file])
            with patch.object(support, 'component_for_binary',
                              side_effect=lambda source: component if Path(source) == definition else None), \
                    patch.object(support, 'pip_component', return_value=component):
                staging = Path(temporary)/'notices'
                support.write_notices([], staging, datas=[
                    ('share/icons/Adwaita/icon-theme.cache', str(cache), 'DATA')])
            report = json.loads((staging/'components.json').read_text())
            self.assertTrue(report['complete'])
            resource = next(item for item in report['components'] if item.get('derived_resources'))
            self.assertEqual(resource['derived_resources']['share/icons/Adwaita/icon-theme.cache']['from'],
                             'share/icons/Adwaita/index.theme')

    def test_usrmerge_alias_is_attributed_to_the_actual_package(self):
        def command(args):
            if args[:2] == ['dpkg-query', '-S']:
                return 'libsample:amd64: /lib/x86_64-linux-gnu/libsample.so.1' if args[-1].startswith('/lib/') else ''
            return '1.2\nhttps://example.invalid/upstream\nlibsample\n1.2'
        with patch.object(support, 'command', side_effect=command), patch.object(support, '_packages', {}):
            component = support.linux_component(Path('/usr/lib/x86_64-linux-gnu/libsample.so.1'))
        self.assertEqual(component['name'], 'libsample:amd64')

    def test_common_license_text_is_not_just_a_reference(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)/'copyright'
            source.write_text('See /usr/share/common-licenses/LGPL-2.1 for the full license.')
            common = Path('/usr/share/common-licenses/LGPL-2.1')
            if not common.is_file():
                self.skipTest('Debian common licenses required')
            self.assertIn(common, support.referenced_common_licenses([source]))

    def test_missing_attribution_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(support, 'component_for_binary', return_value=None), \
                patch.object(support, 'pip_component', return_value=dict(name='builder', version='1', provider='PyPI',
                           source='https://example.invalid', license_declarations=['example'], _licenses=[])):
            with self.assertRaisesRegex(RuntimeError, 'Native notices incomplete'):
                support.write_notices([('unknown.so', '/unknown', 'BINARY')], Path(temporary))
            report = json.loads((Path(temporary)/'components.json').read_text())
            self.assertFalse(report['complete'])
            self.assertIn('unknown.so', report['unmapped_native_files'])

    def test_icons_and_typelibs_require_attribution_too(self):
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(support, 'component_for_binary', return_value=None), \
                patch.object(support, 'pip_component', return_value=dict(name='builder', version='1', provider='PyPI',
                           source='https://example.invalid', license_declarations=['example'], _licenses=[])):
            with self.assertRaisesRegex(RuntimeError, 'Native notices incomplete'):
                support.write_notices([], Path(temporary), datas=[
                    ('share/icons/Adwaita/index.theme', '/usr/share/icons/Adwaita/index.theme', 'DATA'),
                    ('gi_typelibs/Gtk-4.0.typelib', '/usr/lib/girepository-1.0/Gtk-4.0.typelib', 'DATA')])
            report = json.loads((Path(temporary)/'components.json').read_text())
            self.assertEqual(report['unmapped_native_files'], [
                'gi_typelibs/Gtk-4.0.typelib', 'share/icons/Adwaita/index.theme'])

    def test_msys2_spdx_labels_find_common_license_directory_names(self):
        with tempfile.TemporaryDirectory() as temporary:
            common = Path(temporary)
            (common/'GPL2').mkdir()
            (common/'LGPL2.1').mkdir()
            (common/'GPL2/license.txt').write_text('GPL test fixture')
            (common/'LGPL2.1/license.txt').write_text('LGPL test fixture')
            def command(args):
                if args[:2] == ['pacman', '-Qoq']:
                    return 'sample'
                if args[:2] == ['pacman', '-Qi']:
                    return 'Version : 1.2\nLicenses : GPL-2.0-or-later LGPL-2.1-only'
                return ''
            with patch.object(support, 'command', side_effect=command), \
                    patch.object(support, 'native_windows_path', return_value=common), \
                    patch.object(support, '_packages', {}):
                component = support.windows_component(Path('sample.dll'))
            self.assertEqual(set(component['_licenses']), set(common.rglob('license.txt')))


if __name__ == '__main__':
    unittest.main(verbosity=2)
