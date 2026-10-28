"""Bundle integrity and bootstrap tests; real native builds have separate smoke tests."""
import importlib.util
import hashlib
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
gui_check = load('bundle_gui_check_test', ROOT/'scripts/check-installed-gui.py')


class NativeGuiChecksTests(unittest.TestCase):
    def probe(self, folder, message, code, require=False):
        def run(*args, **kwargs):
            (folder/'gui-diagnostic.json').write_text(message, encoding='utf-8')
            return type('Result', (), {'returncode': code})()
        with patch.object(gui_check.subprocess, 'run', side_effect=run), patch('builtins.print'):
            return gui_check.check(Path('RatioLab.exe'), folder, require)

    def test_explicit_display_absence_is_recorded_without_claiming_a_gui_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            message = 'RatioLab runtime check failed: A graphical desktop session is required for --diagnose-gui'
            self.probe(folder, message, 1)
            self.assertEqual(json.loads((folder/'gui-result.json').read_text())['gui'], 'unavailable_on_runner')
            with self.assertRaises(RuntimeError):
                self.probe(folder, message, 1, require=True)

    def test_application_errors_and_crashes_cannot_be_treated_as_missing_gpu(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            for message, code in (('The OpenGL preview produced a blank framebuffer', 1),
                                  ('shader compilation failed', 1),
                                  ('gdk-gl-error-quark: No GL implementation is available', -11)):
                with self.subTest(message=message), self.assertRaises(RuntimeError):
                    self.probe(folder, message, code)

    def test_renderer_success_requires_complete_workspace_and_feature_proof(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            def run(command, **kwargs):
                report = Path(command[-1])
                value = {'bundled': True, 'preview': 'rendered'} if '--diagnose-gui' in command else {'self_test': 'passed', 'workspace_export': 'passed'}
                report.write_text(json.dumps(value), encoding='utf-8')
                return type('Result', (), {'returncode': 0})()
            with patch.object(gui_check.subprocess, 'run', side_effect=run), self.assertRaises(RuntimeError):
                gui_check.check(Path('RatioLab.exe'), folder)


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
    def test_vendored_msys2_notices_match_exact_versions_declarations_and_hashes(self):
        registry = json.loads((support._msys_notice_root/'registry.json').read_text(encoding='utf-8'))
        self.assertEqual({record['name'].removeprefix('mingw-w64-ucrt-x86_64-') for record in registry['components']},
                         {'gobject-introspection-runtime', 'gst-plugins-bad-libs', 'gst-plugins-base',
                          'gstreamer', 'python-gobject'})
        for record in registry['components']:
            with self.subTest(package=record['name']):
                component = dict(name=record['name'], version=record['version'],
                                 license_declarations=record['license_declarations'])
                paths = support.vendored_windows_notices(component)
                self.assertGreater(len(paths), 0)
                for entry, path in zip(record['license_files'], paths):
                    self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), entry['sha256'])
                    self.assertIn(Path(entry['original_path']).name, ('COPYING', 'COPYING.GPL', 'COPYING.LGPL'))
                    self.assertFalse({'tests', 'docs', 'sys'} & set(Path(entry['original_path']).parts))
                source_info = (support._msys_notice_root/record['source_info']).read_bytes()
                self.assertEqual(hashlib.sha256(source_info).hexdigest(), record['source_info_sha256'])
                self.assertEqual(component['notice_provenance']['source_sha256'], record['source_sha256'])
                # Pacman may retain or omit the MSYS2-specific spdx: marker.
                plain = dict(component, license_declarations=[label.removeprefix('spdx:')
                                                             for label in record['license_declarations']])
                self.assertEqual(support.vendored_windows_notices(plain), paths)
                self.assertEqual(support.vendored_windows_notices(dict(component, version='unverified')), [])
                self.assertEqual(support.vendored_windows_notices(dict(component,
                                 license_declarations=['spdx:MIT'])), [])

    def test_vendored_msys2_notices_fail_on_modified_missing_or_escaping_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            notice = root/'COPYING.txt'
            notice.write_bytes(b'Original upstream notice fixture')
            record = dict(name='sample', version='1', license_declarations=['spdx:LGPL-2.1-or-later'],
                          license_files=[dict(path='COPYING.txt', sha256=hashlib.sha256(notice.read_bytes()).hexdigest())])
            registry = dict(format='ratiolab-msys2-source-notices/1', components=[record])
            (root/'registry.json').write_text(json.dumps(registry))
            component = dict(name='sample', version='1', license_declarations=['spdx:LGPL-2.1-or-later'])
            with patch.object(support, '_msys_notice_root', root):
                notice.write_bytes(b'Modified notice')
                with self.assertRaisesRegex(RuntimeError, 'checksum mismatch'):
                    support.vendored_windows_notices(component)
                notice.unlink()
                with self.assertRaisesRegex(RuntimeError, 'checksum mismatch'):
                    support.vendored_windows_notices(component)
                record['license_files'][0]['path'] = '../outside.txt'
                (root/'registry.json').write_text(json.dumps(registry))
                with self.assertRaisesRegex(RuntimeError, 'Unsafe path'):
                    support.vendored_windows_notices(component)

    def test_all_five_missing_msys2_notices_produce_complete_offline_inventory(self):
        registry = json.loads((support._msys_notice_root/'registry.json').read_text(encoding='utf-8'))
        records = [dict(name=record['name'], version=record['version'], provider='MSYS2 UCRT64',
                        source='https://packages.msys2.org/packages/'+record['name'],
                        license_declarations=record['license_declarations'], _licenses=[])
                   for record in registry['components']]
        builder = dict(name='builder', version='1', provider='PyPI', source='https://example.invalid',
                       license_declarations=['fixture'],
                       _licenses=[ROOT/'packaging/fonts/LICENSE-DejaVu.txt'])
        binaries = [(f'component{index}.dll', f'/fixture/{index}', 'BINARY') for index in range(5)]
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(support, 'component_for_binary', side_effect=records), \
                patch.object(support, 'pip_component', return_value=builder), \
                patch.object(support.urllib.request, 'urlopen', side_effect=AssertionError('No build-time download')):
            support.write_notices(binaries, temporary)
            report = json.loads((Path(temporary)/'components.json').read_text())
            self.assertTrue(report['complete'])
            msys = [item for item in report['components'] if item['provider'] == 'MSYS2 UCRT64']
            self.assertEqual(len(msys), 5)
            for item in msys:
                self.assertTrue(item['notices_present'])
                self.assertEqual(len(item['notice_provenance']['source_recipe_sha256']), 64)
                for path in item['license_files']:
                    self.assertTrue((Path(temporary)/path).is_file())

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
            root = Path(temporary)
            common = root/'usr/share/licenses/common'
            common.mkdir(parents=True)
            (common/'GPL2').mkdir()
            (common/'LGPL2.1').mkdir()
            (common/'GPL2/license.txt').write_text('GPL test fixture')
            (common/'LGPL2.1/license.txt').write_text('LGPL test fixture')
            def command(args):
                if args == ['cygpath', '-w', '/']:
                    return str(root)
                if args == ['pacman', '-Ql']:
                    return ('sample /ucrt64/bin/sample.dll\n'
                            'licenses /usr/share/licenses/common/GPL2/license.txt\n'
                            'licenses /usr/share/licenses/common/LGPL2.1/license.txt')
                if args[:2] == ['pacman', '-Qi']:
                    return 'Version : 1.2\nLicenses : spdx:GPL-2.0-or-later spdx:LGPL-2.1-only'
                raise AssertionError(f'Unexpected command: {args}')
            with patch.object(support, 'command', side_effect=command), \
                    patch.object(support, '_windows_files', None), \
                    patch.object(support, '_packages', {}):
                component = support.windows_component(root/'ucrt64/bin/sample.dll')
            self.assertEqual(set(component['_licenses']), set(common.rglob('license.txt')))

    def test_msys2_many_files_share_one_exact_index_and_one_metadata_query(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)/'MSYS2 with spaces Ω'
            license_file = root/'ucrt64/share/licenses/sample/LICENSE'
            license_file.parent.mkdir(parents=True)
            license_file.write_text('Native package license fixture')
            listing = '\n'.join(f'sample /ucrt64/bin/item{index}.dll' for index in range(200))
            listing += ('\nsample /ucrt64/share/licenses/sample/LICENSE\n'
                        'sample /ucrt64/bin/ambiguous.dll\nother /ucrt64/bin/AMBIGUOUS.dll\n'
                        'sample /ucrt64/bin/\nother /ucrt64/bin/')
            def command(args):
                if args == ['cygpath', '-w', '/']:
                    return str(root)
                if args == ['pacman', '-Ql']:
                    return listing
                if args == ['pacman', '-Qi', 'sample']:
                    return 'Version : 1.2\nLicenses : MIT\nURL : https://example.invalid/sample'
                raise AssertionError(f'Unexpected command: {args}')
            with patch.object(support, 'command', side_effect=command) as commands, \
                    patch.object(support, '_windows_files', None), \
                    patch.object(support, '_packages', {}):
                for index in range(200):
                    component = support.windows_component(root/f'ucrt64/bin/item{index}.dll')
                    self.assertEqual(component['name'], 'sample')
                    self.assertEqual(component['version'], '1.2')
                    self.assertEqual(component['_licenses'], [license_file])
                self.assertEqual(support.windows_component(root/'ucrt64/bin/ITEM3.DLL')['name'], 'sample')
                for unknown in (root/'ucrt64/bin/not-owned.dll', root/'ucrt64/bin/ambiguous.dll',
                                root/'ucrt64/bin', root.parent/'outside.dll', Path('relative.dll'),
                                root/'ucrt64/bin/../bin/item3.dll'):
                    self.assertIsNone(support.windows_component(unknown))
            self.assertEqual([call.args[0] for call in commands.call_args_list], [
                ['cygpath', '-w', '/'], ['pacman', '-Ql'], ['pacman', '-Qi', 'sample']])

    def test_msys2_index_rejects_relative_and_escaping_database_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            for spelling in ('relative.dll', '/ucrt64/../../outside.dll', '//server/share/file.dll',
                             '/ucrt64/bin/C:/escape.dll', '/ucrt64\\bin\\escape.dll'):
                def command(args):
                    return temporary if args[0] == 'cygpath' else 'sample '+spelling
                with self.subTest(spelling=spelling), \
                        patch.object(support, 'command', side_effect=command), \
                        patch.object(support, '_windows_files', None):
                    with self.assertRaisesRegex(RuntimeError, 'Unsafe path'):
                        support._windows_inventory()
            with patch.object(support, 'command', return_value='relative-root'), \
                    patch.object(support, '_windows_files', None):
                with self.assertRaisesRegex(RuntimeError, 'absolute native'):
                    support._windows_inventory()

    def test_msys2_index_resolves_internal_symlinks_and_rejects_external_targets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = (Path(temporary)/'msys2').resolve()
            alias, target = root/'ucrt64/alias', root/'ucrt64/real'
            escape, outside = root/'ucrt64/escape', root.parent/'outside'
            actual_resolve = Path.resolve
            def resolve(path, *args, **kwargs):
                if path.is_relative_to(alias):
                    return target/path.relative_to(alias)
                if path.is_relative_to(escape):
                    return outside/path.relative_to(escape)
                return actual_resolve(path, *args, **kwargs)
            def command(args):
                if args == ['cygpath', '-w', '/']:
                    return str(root)
                if args == ['pacman', '-Ql']:
                    return 'sample /ucrt64/alias/owned.dll\nsample /ucrt64/escape/private.dll'
                if args == ['pacman', '-Qi', 'sample']:
                    return 'Version : 1.2\nLicenses : MIT'
                raise AssertionError(f'Unexpected command: {args}')
            # Simulated filesystem resolutions avoid needing Windows symlink
            # privileges while exercising the same Path.resolve interface.
            with patch.object(Path, 'resolve', resolve), \
                    patch.object(support, 'command', side_effect=command), \
                    patch.object(support, '_windows_files', None), \
                    patch.object(support, '_packages', {}):
                self.assertEqual(support.windows_component(target/'owned.dll')['name'], 'sample')
                self.assertEqual(support.windows_component(alias/'owned.dll')['name'], 'sample')
                self.assertIsNone(support.windows_component(escape/'private.dll'))
                self.assertIsNone(support.windows_component(outside/'private.dll'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
