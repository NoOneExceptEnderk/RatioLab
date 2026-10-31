# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
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

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load('bundle_builder_test', ROOT/'scripts/build-bundle.py')
support = load('bundle_support_test', ROOT/'packaging/bundle_support.py')
gui_check = load('bundle_gui_check_test', ROOT/'scripts/check-installed-gui.py')


class WorkspaceRuntimeTests(unittest.TestCase):
    def test_gui_self_test_uses_only_the_workspace_for_rendering(self):
        from geometry import FAMILIES
        from ratiolab_checks import self_test
        runtime = {'gtk': 'fixture'}
        def workspace(config, output, runtime):
            self.assertEqual(config['family'], 'helical')
            self.assertTrue(output.is_dir())
            runtime.update(opengl_version=45, graphics_api='OpenGL',
                           graphics_renderer='fixture', preview='rendered',
                           framebuffer_has_geometry=True)
            return list(FAMILIES)
        with patch('ratiolab_cli.diagnose', return_value=runtime) as diagnose, \
                patch('ratiolab_checks._workspace_check', side_effect=workspace) as check:
            result = self_test(gui=True)
        diagnose.assert_called_once_with(gui=False)
        check.assert_called_once()
        self.assertIs(check.call_args.kwargs['runtime'], runtime)
        self.assertEqual(result['preview_families'], list(FAMILIES))
        self.assertEqual(len(result['features']), 6)
        self.assertTrue(all(value == 'passed' for value in result['features'].values()))
        self.assertEqual(result['preview'], 'rendered')
        self.assertTrue(result['framebuffer_has_geometry'])

    def canvas(self, version=45, use_es=False):
        canvas = unittest.mock.Mock(failure=None, use_es=use_es)
        canvas.get_error.return_value = None
        canvas.gl.GetError.return_value = 0
        canvas.gl.lib.epoxy_gl_version.return_value = version
        return canvas

    def test_runtime_metadata_comes_from_the_current_workspace_context(self):
        from ratiolab_checks import _canvas_runtime
        for version, use_es, api in ((33, False, 'OpenGL'), (30, True, 'OpenGL ES')):
            with self.subTest(api=api):
                canvas = self.canvas(version, use_es)
                def get_string(name):
                    canvas.make_current.assert_called_once()
                    self.assertEqual(name, 0x1F01)
                    return b'Actual workspace renderer'
                with patch('gl_loader.bind_function', return_value=get_string):
                    result = _canvas_runtime(canvas)
                self.assertEqual(result, dict(opengl_version=version, graphics_api=api,
                                              graphics_renderer='Actual workspace renderer'))

    def test_workspace_runtime_rejects_insufficient_gl_versions(self):
        from ratiolab_checks import _canvas_runtime
        for version, use_es in ((32, False), (29, True)):
            with self.subTest(version=version), self.assertRaisesRegex(RuntimeError, 'or newer is required'):
                _canvas_runtime(self.canvas(version, use_es))

    def test_workspace_runtime_preserves_context_and_gl_error_checks(self):
        from ratiolab_checks import _canvas_runtime
        for failure in ('renderer', 'context', 'missing GL', 'GL error'):
            canvas = self.canvas()
            if failure == 'renderer':
                canvas.failure = 'Renderer failure'
            elif failure == 'context':
                canvas.get_error.return_value = 'Context failure'
            elif failure == 'missing GL':
                canvas.gl = None
            else:
                canvas.gl.GetError.return_value = 0x0502
            with self.subTest(failure=failure), self.assertRaises(RuntimeError):
                _canvas_runtime(canvas)
            canvas.make_current.assert_called_once()


class GuiEventLoopTests(unittest.TestCase):
    def frame_fixture(self, width=640):
        clock = unittest.mock.Mock()
        frame = [10]
        clock.get_frame_counter.side_effect = lambda: frame[0]
        callbacks = []
        clock.connect.side_effect = lambda signal, callback: callbacks.append((signal, callback)) or 7
        canvas = unittest.mock.Mock(gl=object(), dirty=False)
        canvas.get_frame_clock.return_value = clock
        canvas.get_mapped.return_value = True
        canvas.get_width.return_value = width
        canvas.get_height.return_value = 480
        context = unittest.mock.Mock()
        def dispatch(blocking):
            self.assertFalse(blocking)
            self.assertEqual(callbacks[0][0], 'after-paint')
            canvas.queue_render.assert_called_once()
            if context.iteration.call_count > 1:
                frame[0] += 1
            callbacks[0][1](clock)
        context.iteration.side_effect = dispatch
        return canvas, context, clock

    def test_capture_barrier_waits_for_a_new_completed_frame(self):
        from ratiolab_checks import _wait_for_frame
        canvas, context, clock = self.frame_fixture()
        with patch('ratiolab_checks.time.sleep'):
            _wait_for_frame(canvas, context)
        self.assertEqual(context.iteration.call_count, 2)
        clock.disconnect.assert_called_once_with(7)

    def test_capture_barrier_rejects_zero_size_and_disconnects_on_timeout(self):
        from ratiolab_checks import _wait_for_frame
        canvas, context, clock = self.frame_fixture(width=0)
        with patch('ratiolab_checks.time.monotonic', side_effect=[0, .05, .15, .25, .35]), \
                patch('ratiolab_checks.time.sleep'), self.assertRaisesRegex(RuntimeError, 'Timed out'):
            _wait_for_frame(canvas, context, timeout=.3)
        self.assertEqual(context.iteration.call_count, 3)
        clock.disconnect.assert_called_once_with(7)

    def test_capture_barrier_requires_a_frame_clock(self):
        from ratiolab_checks import _wait_for_frame
        canvas = unittest.mock.Mock()
        canvas.get_frame_clock.return_value = None
        with self.assertRaisesRegex(RuntimeError, 'no frame clock'):
            _wait_for_frame(canvas, unittest.mock.Mock())
        canvas.queue_render.assert_not_called()

    def test_continuously_ready_events_do_not_starve_the_condition(self):
        from ratiolab_checks import _wait_for_context
        context = unittest.mock.Mock()
        context.pending.return_value = True
        dispatched = []
        def dispatch(blocking):
            self.assertFalse(blocking)
            dispatched.append(None)
            if len(dispatched) > 10:
                self.fail('The event queue was drained without checking readiness')
        context.iteration.side_effect = dispatch
        with patch('ratiolab_checks.time.sleep'):
            _wait_for_context(context, lambda: len(dispatched) >= 3)
        self.assertEqual(len(dispatched), 3)

    def test_continuously_ready_events_still_observe_the_deadline(self):
        from ratiolab_checks import _wait_for_context
        context = unittest.mock.Mock()
        context.pending.return_value = True
        def dispatch(blocking):
            self.assertFalse(blocking)
            if context.iteration.call_count > 10:
                self.fail('The event queue prevented the deadline from being checked')
        context.iteration.side_effect = dispatch
        with patch('ratiolab_checks.time.monotonic', side_effect=[0, .05, .15, .25, .35]), \
                patch('ratiolab_checks.time.sleep'), \
                self.assertRaisesRegex(RuntimeError, 'Timed out checking the installed workspace'):
            _wait_for_context(context, lambda: False, timeout=.3)
        self.assertEqual(context.iteration.call_count, 3)


class NativeGuiChecksTests(unittest.TestCase):
    def test_current_catalog_passes_and_missing_duplicate_or_substituted_families_fail(self):
        from geometry import FAMILIES
        self.assertEqual(gui_check.EXPECTED_FAMILIES,set(FAMILIES))
        ids=list(FAMILIES)
        variants=[(ids,True),(list(reversed(ids)),True),(ids[:-1],False),
                  (ids[:-1]+[ids[0]],False),(ids[:-1]+['unknown'],False)]
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)
            def run(command,**kwargs):
                Path(command[-1]).write_text(json.dumps(dict(bundled=True,preview='rendered')))
                return type('Result',(),{'returncode':0})()
            for families,valid in variants:
                def workspace(command,report):
                    report.write_text(json.dumps(dict(self_test='passed',workspace_export='passed',
                        features={str(k):'passed' for k in range(6)},preview_families=families)))
                with self.subTest(families=families),patch.object(gui_check.subprocess,'run',side_effect=run), \
                        patch.object(gui_check,'_run_workspace',side_effect=workspace),patch('builtins.print'):
                    if valid:
                        gui_check.check(Path('RatioLab.exe'),folder)
                        self.assertEqual(json.loads((folder/'gui-result.json').read_text())['gui'],'passed')
                    else:
                        with self.assertRaisesRegex(RuntimeError,'workspace/features'):gui_check.check(Path('RatioLab.exe'),folder)

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
                report.write_text(json.dumps({'bundled': True, 'preview': 'rendered'}), encoding='utf-8')
                return type('Result', (), {'returncode': 0})()
            def workspace(command, report):
                self.assertIn('--self-test-gui', command)
                report.write_text(json.dumps({'self_test': 'passed', 'workspace_export': 'passed'}), encoding='utf-8')
            with patch.object(gui_check.subprocess, 'run', side_effect=run), \
                    patch.object(gui_check, '_run_workspace', side_effect=workspace) as work, \
                    self.assertRaises(RuntimeError):
                gui_check.check(Path('RatioLab.exe'), folder)
            work.assert_called_once()


class BundleIntegrityTests(unittest.TestCase):
    def test_native_bundle_requires_all_plain_fusion_addin_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)/'RatioLab'
            runtime = bundle/'_internal'
            runtime.mkdir(parents=True)
            for name in ('RatioLab.exe', 'RatioLab-MCP.exe'):
                (bundle/name).write_bytes(b'fixture')
            for name in ('gi_typelibs/Gtk-4.0.typelib', 'gi_typelibs/Gdk-4.0.typelib',
                         'share/glib-2.0/schemas/gschemas.compiled',
                         'ratiolab_resources/branding/ratiolab-icon.png',
                         'ratiolab_resources/icons/hicolor/index.theme',
                         'ratiolab_resources/icons/hicolor/128x128/apps/local.solidcraft.reducers.png',
                         'ratiolab_resources/icons/hicolor/256x256/apps/local.solidcraft.reducers.png',
                         'ratiolab_resources/bearing-catalog.json',
                         'ratiolab_resources/hardware-catalog.json',
                         'ratiolab_resources/INSTALL.md', 'ratiolab_resources/MCP.md',
                         'ratiolab_resources/CHANGELOG.md', 'ratiolab_resources/version.json',
                         'etc/fonts/fonts.conf', 'share/fonts/DejaVuSans.ttf',
                         'notices/THIRD-PARTY-NOTICES.txt',
                         'libepoxy-fixture.dll', 'libEGL.dll', 'libGLESv2.dll'):
                target = runtime/name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b'fixture')
            for name in ('LICENSE', 'COPYRIGHT'):
                (runtime/'ratiolab_resources'/name).write_bytes((ROOT/name).read_bytes())
            (runtime/'notices/components.json').write_text(
                json.dumps(dict(complete=True, components=[])), encoding='utf-8')
            source = ROOT/'src/ratiolab_resources/fusion_addin/RatioLabBridge'
            addin = runtime/'ratiolab_resources/fusion_addin/RatioLabBridge'
            addin.mkdir(parents=True)
            names = ('RatioLabBridge.py', 'RatioLabBridge.manifest', 'bridge_server.py', 'fusion_import.py')
            for name in names:
                (addin/name).write_bytes((source/name).read_bytes())
            self.assertEqual(builder.verify_bundle(bundle, run=False, check_manifest=False)['structure'], 'passed')
            # Failure diagnostics must survive the temporary report's cleanup.
            reports = []
            def failed_self_test(command, **kwargs):
                report = Path(command[-1])
                reports.append(report)
                report.write_text('{"self_test": "passed"}', encoding='utf-8')
                report.with_suffix('.stderr.log').write_text(
                    'RuntimeError: unhandled workspace callback', encoding='utf-8')
                return builder.subprocess.CompletedProcess(command, 1, stdout='', stderr='native diagnostic')
            with patch.object(builder.subprocess, 'run', side_effect=failed_self_test), \
                    self.assertRaisesRegex(RuntimeError, 'unhandled workspace callback') as raised:
                builder.verify_bundle(bundle, check_manifest=False)
            self.assertIn('native diagnostic', str(raised.exception))
            self.assertFalse(reports[0].parent.exists())
            for name in names:
                with self.subTest(name=name):
                    target = addin/name
                    target.unlink()
                    with self.assertRaisesRegex(RuntimeError, 'Bundle runtime data missing:.*'+name.replace('.', r'\.')):
                        builder.verify_bundle(bundle, run=False, check_manifest=False)
                    target.write_bytes((source/name).read_bytes())

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
            for name in ('ui-preferences.json', 'preferenze-ui.json', 'updates.json'):
                path = Path(temporary)/name
                path.write_text('{}')
                with self.assertRaisesRegex(RuntimeError, 'Personal data'):
                    builder.inventory(temporary)
                path.unlink()

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
    def test_agent_command_dispatches_before_any_gtk_runtime_setup(self):
        import ratiolab_cli
        module = ModuleType('ratiolab_mcp')
        calls = []
        module.main = lambda args: calls.append(args) or 0
        with patch.dict(sys.modules, {'ratiolab_mcp': module}), \
                patch.object(ratiolab_cli, 'prepare_native_runtime') as prepare:
            self.assertEqual(ratiolab_cli.main(['--mcp', '--workspace', '/agent workspace']), 0)
        prepare.assert_not_called()
        self.assertEqual(calls, [['--workspace', '/agent workspace']])

    def test_frozen_agent_stream_is_never_redirected_to_a_log_or_report(self):
        entry = load('bundle_entrypoint_agent_test', ROOT/'packaging/entrypoint.py')
        output = io.StringIO()
        with patch('ratiolab_cli.main', side_effect=lambda args: print('{"jsonrpc":"2.0"}') or 0), \
                patch.object(sys, 'argv', ['RatioLab', '--mcp', '--workspace', '/agent']), \
                patch.object(sys, 'stdin', io.StringIO()), patch.object(sys, 'stdout', output):
            self.assertEqual(entry.main(), 0)
        self.assertEqual(json.loads(output.getvalue()), {'jsonrpc': '2.0'})

    def test_windowed_windows_agent_launch_without_streams_fails_immediately(self):
        entry = load('bundle_entrypoint_agent_no_console_test', ROOT/'packaging/entrypoint.py')
        with patch.object(sys, 'argv', ['RatioLab.exe', '--mcp', '--workspace', '/agent']), \
                patch.object(sys, 'stdin', None), patch.object(sys, 'stdout', None), \
                patch.object(sys, 'stderr', None), patch('ratiolab_cli.main') as run:
            self.assertEqual(entry.main(), 2)
        run.assert_not_called()

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
                          'gstreamer', 'python-gobject', 'angleproject'})
        for record in registry['components']:
            with self.subTest(package=record['name']):
                component = dict(name=record['name'], version=record['version'],
                                 license_declarations=record['license_declarations'])
                paths = support.vendored_windows_notices(component)
                self.assertGreater(len(paths), 0)
                for entry, path in zip(record['license_files'], paths):
                    self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), entry['sha256'])
                    if record.get('source_method') == 'pinned-git-files':
                        self.assertEqual(len(entry['source_commit']), 40)
                        self.assertEqual(len(entry['source_blob_sha1']), 40)
                        self.assertEqual(len(entry['source_original_sha256']), 64)
                        self.assertIn(entry['source_commit'], entry['source_original'])
                        start, end = entry['selection_bytes']
                        self.assertGreater(end, start)
                        self.assertEqual(end-start, len(path.read_bytes()))
                    else:
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
                   for record in registry['components'] if not record.get('required_supplement')]
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

    def test_angle_adds_static_notices_to_installed_license_and_keeps_git_provenance(self):
        verifier = load('angle_notices_verifier', support._msys_notice_root/'verify_angle.py')
        record = verifier.verify_local()
        self.assertTrue(record['required_supplement'])
        self.assertEqual(record['version'], '2.1.r25748.890b5d8f-6')
        self.assertEqual(len(record['license_files']), 18)
        names = {entry['original_path'] for entry in record['license_files']}
        self.assertIn('vulkan-loader/loader/cJSON.c', names)
        self.assertIn('vulkan-loader/loader/loader_json.c', names)
        self.assertIn('vulkan-loader/loader/dirent_on_windows.c', names)
        self.assertIn('vulkan-loader/loader/dirent_on_windows.h', names)
        self.assertFalse(any(any(word in name.lower() for word in
                                ('swiftshader', 'rapidjson', 'ceval', '/volk/', 'astc', 'abseil'))
                             for name in names))
        component = dict(name=record['name'], version=record['version'], provider='MSYS2 UCRT64',
                         source='https://packages.msys2.org/packages/'+record['name'],
                         license_declarations=record['license_declarations'],
                         _licenses=[support._msys_notice_root/record['license_files'][0]['path']])
        builder_notice = dict(name='builder', version='1', provider='PyPI', source='https://example.invalid',
                              license_declarations=['fixture'], _licenses=[ROOT/'packaging/fonts/LICENSE-DejaVu.txt'])
        binaries = [(name, '/fixture/'+name, 'BINARY') for name in ('libEGL.dll', 'libGLESv2.dll')]
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(support, 'component_for_binary', return_value=component), \
                patch.object(support, 'pip_component', return_value=builder_notice), \
                patch.object(support.urllib.request, 'urlopen', side_effect=AssertionError('Offline build')):
            support.write_notices(binaries, temporary)
            report = json.loads((Path(temporary)/'components.json').read_text())
            self.assertTrue(report['complete'])
            angle, = [item for item in report['components'] if item['name'] == record['name']]
            self.assertEqual(angle['bundled_files'], ['libEGL.dll', 'libGLESv2.dll'])
            self.assertEqual(len(angle['license_files']), 19)  # Installed root plus all 18 supplements.
            provenance = angle['notice_provenance']
            self.assertIsNone(provenance['source_sha256'])
            self.assertEqual(provenance['source_commit'], record['source_commit'])
            self.assertEqual(provenance['original_files'][8]['source_blob_sha1'],
                             record['license_files'][8]['source_blob_sha1'])
            self.assertEqual(provenance['original_files'][8]['selection_bytes'],
                             record['license_files'][8]['selection_bytes'])

    def test_angle_unknown_version_or_license_is_rejected_despite_installed_root_license(self):
        registry = json.loads((support._msys_notice_root/'registry.json').read_text(encoding='utf-8'))
        record, = [item for item in registry['components'] if item.get('required_supplement')]
        builder_notice = dict(name='builder', version='1', provider='PyPI', source='https://example.invalid',
                              license_declarations=['fixture'], _licenses=[ROOT/'packaging/fonts/LICENSE-DejaVu.txt'])
        for version, declarations in [('unverified', record['license_declarations']),
                                      (record['version'], ['spdx:MIT'])]:
            component = dict(name=record['name'], version=version, provider='MSYS2 UCRT64',
                             source='https://packages.msys2.org', license_declarations=declarations,
                             _licenses=[support._msys_notice_root/record['license_files'][0]['path']])
            with self.subTest(version=version, declarations=declarations), \
                    tempfile.TemporaryDirectory() as temporary, \
                    patch.object(support, 'component_for_binary', return_value=component), \
                    patch.object(support, 'pip_component', return_value=builder_notice):
                with self.assertRaisesRegex(RuntimeError, 'Required ANGLE source notices are not verified'):
                    support.write_notices([('libEGL.dll', '/fixture/libEGL.dll', 'BINARY')], temporary)

    def test_angle_git_verifier_rejects_changed_original_blob_and_notice_range(self):
        verifier = load('angle_git_bytes_verifier', support._msys_notice_root/'verify_angle.py')
        original = b'header\n/* Original copyright and permission notice. */\nimplementation\n'
        start, end = original.index(b'/*'), original.index(b'*/')+2
        notice = original[start:end]
        entry = dict(original_path='fixture/source.c', selection_bytes=[start, end],
                     source_original_sha256=hashlib.sha256(original).hexdigest(),
                     source_blob_sha1=hashlib.sha1(b'blob '+str(len(original)).encode()+b'\0'+original).hexdigest(),
                     sha256=hashlib.sha256(notice).hexdigest())
        self.assertEqual(verifier.verify_source_bytes(entry, original), notice)
        for modified, data, error in [
                (entry, original+b'changed', 'Original source SHA-256'),
                (dict(entry, source_blob_sha1='0'*40), original, 'Git blob'),
                (dict(entry, selection_bytes=[-1, end]), original, 'byte range'),
                (dict(entry, selection_bytes=[start, len(original)+1]), original, 'byte range'),
                (dict(entry, selection_bytes=[start, end-1]), original, 'Notice SHA-256')]:
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                verifier.verify_source_bytes(modified, data)

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
