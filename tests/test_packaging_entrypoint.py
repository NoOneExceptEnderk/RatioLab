# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Machine reports retain warnings and failures without mixing them into JSON."""
import builtins
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import warnings


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('packaging_entrypoint_test', ROOT/'packaging/entrypoint.py')
entrypoint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entrypoint)


class PackagingEntrypointTests(unittest.TestCase):
    def test_explicit_report_separates_runtime_warning_and_stderr_from_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary)/'GUI report Ω.json'
            payload = {'self_test': 'passed', 'preview_families': ['spur']}
            original_hook = sys.excepthook
            def run(args):
                self.assertEqual(args, ['--self-test-gui'])
                warnings.warn('g_value_get_double binding warning', RuntimeWarning)
                print('additional diagnostic', file=sys.stderr)
                print(json.dumps(payload))
                return 0
            with patch.dict(sys.modules, {'ratiolab_cli': SimpleNamespace(main=run)}), \
                    patch.object(sys, 'argv', ['RatioLab', '--self-test-gui', '--report', str(report)]), \
                    patch.object(sys, 'stdout', None), patch.object(sys, 'stderr', None), \
                    warnings.catch_warnings():
                warnings.simplefilter('always')
                self.assertEqual(entrypoint.main(), 0)
            self.assertIs(sys.excepthook, original_hook)
            self.assertEqual(json.loads(report.read_text(encoding='utf-8')), payload)
            diagnostic = report.with_suffix('.stderr.log').read_text(encoding='utf-8')
            self.assertIn('RuntimeWarning: g_value_get_double binding warning', diagnostic)
            self.assertIn('additional diagnostic', diagnostic)
            self.assertNotIn('preview_families', diagnostic)

    def test_cli_import_warnings_are_captured_after_streams_are_separated(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary)/'report.json'
            original_import = builtins.__import__
            def run(args):
                print('{"self_test": "passed"}')
                return 0
            def importing(name, globals=None, locals=None, fromlist=(), level=0):
                if name == 'ratiolab_cli':
                    warnings.warn('binding import warning', RuntimeWarning)
                    return SimpleNamespace(main=run)
                return original_import(name, globals, locals, fromlist, level)
            with patch.object(sys, 'argv', ['RatioLab', '--self-test', '--report', str(report)]), \
                    patch('builtins.__import__', side_effect=importing), warnings.catch_warnings():
                warnings.simplefilter('always')
                self.assertEqual(entrypoint.main(), 0)
            self.assertEqual(json.loads(report.read_text())['self_test'], 'passed')
            self.assertIn('binding import warning', report.with_suffix('.stderr.log').read_text())

    def test_unexpected_exception_remains_a_failure_with_a_diagnostic_traceback(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary)/'report.json'
            original_hook = sys.excepthook
            def run(args):
                raise RuntimeError('workspace failed')
            with patch.dict(sys.modules, {'ratiolab_cli': SimpleNamespace(main=run)}), \
                    patch.object(sys, 'argv', ['RatioLab', '--self-test-gui', '--report', str(report)]):
                self.assertEqual(entrypoint.main(), 1)
            self.assertIs(sys.excepthook, original_hook)
            self.assertEqual(report.read_text(), '')
            diagnostic = report.with_suffix('.stderr.log').read_text()
            self.assertIn('Traceback (most recent call last)', diagnostic)
            self.assertIn('RuntimeError: workspace failed', diagnostic)

    def test_unhandled_callback_exception_cannot_pass_with_successful_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary)/'report.json'
            original_hook = sys.excepthook
            def run(args):
                try:
                    raise RuntimeError('unhandled GTK callback failure')
                except RuntimeError as error:
                    sys.excepthook(type(error), error, error.__traceback__)
                print('{"self_test": "passed"}')
                return 0
            with patch.dict(sys.modules, {'ratiolab_cli': SimpleNamespace(main=run)}), \
                    patch.object(sys, 'argv', ['RatioLab', '--self-test-gui', '--report', str(report)]):
                self.assertEqual(entrypoint.main(), 1)
            self.assertIs(sys.excepthook, original_hook)
            self.assertEqual(json.loads(report.read_text())['self_test'], 'passed')
            diagnostic = report.with_suffix('.stderr.log').read_text()
            self.assertIn('Traceback (most recent call last)', diagnostic)
            self.assertIn('unhandled GTK callback failure', diagnostic)

    def test_system_exit_restores_original_exception_hook(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary)/'report.json'
            original_hook = sys.excepthook
            for code in (0, 7):
                def run(args):
                    raise SystemExit(code)
                with self.subTest(code=code), \
                        patch.dict(sys.modules, {'ratiolab_cli': SimpleNamespace(main=run)}), \
                        patch.object(sys, 'argv', ['RatioLab', '--diagnose-gui', '--report', str(report)]), \
                        self.assertRaises(SystemExit) as raised:
                    entrypoint.main()
                self.assertEqual(raised.exception.code, code)
                self.assertIs(sys.excepthook, original_hook)

    def test_cli_failure_keeps_its_exit_code_and_error_message(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary)/'report.json'
            def run(args):
                print('RatioLab runtime check failed: no display', file=sys.stderr)
                return 3
            with patch.dict(sys.modules, {'ratiolab_cli': SimpleNamespace(main=run)}), \
                    patch.object(sys, 'argv', ['RatioLab', '--diagnose-gui', '--report', str(report)]):
                self.assertEqual(entrypoint.main(), 3)
            self.assertEqual(report.read_text(), '')
            self.assertIn('no display', report.with_suffix('.stderr.log').read_text())

    def test_windowed_gui_keeps_combined_append_only_normal_logging(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            log = folder/'logs/ratiolab.log'
            log.parent.mkdir()
            log.write_text('previous launch\n')
            def run(args):
                self.assertEqual(args, [])
                print('GUI output')
                print('GUI diagnostic', file=sys.stderr)
                return 0
            with patch.dict(sys.modules, {'ratiolab_cli': SimpleNamespace(main=run),
                                          'app_paths': SimpleNamespace(data_dir=lambda: folder)}), \
                    patch.object(sys, 'argv', ['RatioLab']), \
                    patch.object(sys, 'stdout', None), patch.object(sys, 'stderr', None):
                self.assertEqual(entrypoint.main(), 0)
            self.assertEqual(log.read_text(), 'previous launch\nGUI output\nGUI diagnostic\n')
            self.assertFalse(log.with_suffix('.stderr.log').exists())

    def test_mcp_streams_remain_unredirected(self):
        output, diagnostic = io.StringIO(), io.StringIO()
        def run(args):
            self.assertEqual(args, ['--mcp', '--workspace', '/agent'])
            print('{"jsonrpc": "2.0"}')
            print('agent diagnostic', file=sys.stderr)
            return 0
        with patch.dict(sys.modules, {'ratiolab_cli': SimpleNamespace(main=run)}), \
                patch.object(sys, 'argv', ['RatioLab', '--mcp', '--workspace', '/agent']), \
                patch.object(sys, 'stdin', io.StringIO()), patch.object(sys, 'stdout', output), \
                patch.object(sys, 'stderr', diagnostic):
            self.assertEqual(entrypoint.main(), 0)
        self.assertEqual(json.loads(output.getvalue()), {'jsonrpc': '2.0'})
        self.assertEqual(diagnostic.getvalue(), 'agent diagnostic\n')


if __name__ == '__main__':
    unittest.main()
