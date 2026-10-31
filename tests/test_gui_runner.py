# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Keep native timeout diagnostics separate from the application's JSON report."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location(
    'gui_runner_test', Path(__file__).resolve().parents[1]/'scripts/check-installed-gui.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class NativeGuiRunnerTests(unittest.TestCase):
    def test_failed_probe_retains_capability_reason_from_separate_diagnostic_log(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            reason = 'RatioLab runtime check failed: A graphical desktop session is required for --diagnose-gui'
            def probe(command, **kwargs):
                report = Path(command[-1])
                report.write_text('', encoding='utf-8')
                report.with_suffix('.stderr.log').write_text(reason, encoding='utf-8')
                return subprocess.CompletedProcess(command, 1)
            with patch.object(runner.subprocess, 'run', side_effect=probe), patch('builtins.print'):
                runner.check(Path('RatioLab'), folder)
                result = json.loads((folder/'gui-result.json').read_text())
                self.assertEqual(result['gui'], 'unavailable_on_runner')
                self.assertIn(reason, result['reason'])
                with self.assertRaisesRegex(RuntimeError, 'Installed GUI diagnostic failed'):
                    runner.check(Path('RatioLab'), folder, require=True)

    def test_application_error_in_diagnostic_log_cannot_be_treated_as_capability_absence(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            def probe(command, **kwargs):
                report = Path(command[-1])
                report.write_text('', encoding='utf-8')
                report.with_suffix('.stderr.log').write_text('shader compilation failed', encoding='utf-8')
                return subprocess.CompletedProcess(command, 1)
            with patch.object(runner.subprocess, 'run', side_effect=probe), \
                    self.assertRaisesRegex(RuntimeError, 'shader compilation failed'):
                runner.check(Path('RatioLab'), folder)

    def test_failed_new_probe_cannot_reuse_a_stale_capability_reason(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            report = folder/'gui-diagnostic.json'
            report.with_suffix('.stderr.log').write_text(
                'gdk-gl-error-quark: No GL implementation is available', encoding='utf-8')
            def probe(command, **kwargs):
                Path(command[-1]).write_text('unexpected loader failure', encoding='utf-8')
                return subprocess.CompletedProcess(command, 1)
            with patch.object(runner.subprocess, 'run', side_effect=probe), \
                    self.assertRaisesRegex(RuntimeError, 'unexpected loader failure'):
                runner.check(Path('RatioLab'), folder)

    def test_mixed_application_output_cannot_be_downgraded_by_a_capability_phrase(self):
        reason = 'RatioLab runtime check failed: gdk-gl-error-quark: No GL implementation is available (0)'
        cases = (
            (json.dumps({'bundled': True, 'preview': 'rendered'}), reason),
            ('', 'Traceback (most recent call last):\nRuntimeError: unexpected callback\n'+reason),
            ('', reason+'\nadditional application failure'),
        )
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            for output, diagnostic in cases:
                def probe(command, **kwargs):
                    report = Path(command[-1])
                    report.write_text(output, encoding='utf-8')
                    report.with_suffix('.stderr.log').write_text(diagnostic, encoding='utf-8')
                    return subprocess.CompletedProcess(command, 1)
                with self.subTest(output=output, diagnostic=diagnostic), \
                        patch.object(runner.subprocess, 'run', side_effect=probe), \
                        self.assertRaisesRegex(RuntimeError, 'Installed GUI diagnostic failed'):
                    runner.check(Path('RatioLab'), folder)
            # A sole actual GLib capability error retains its optional status.
            def probe(command, **kwargs):
                report = Path(command[-1])
                report.write_text('', encoding='utf-8')
                report.with_suffix('.stderr.log').write_text(reason, encoding='utf-8')
                return subprocess.CompletedProcess(command, 1)
            with patch.object(runner.subprocess, 'run', side_effect=probe), patch('builtins.print'):
                runner.check(Path('RatioLab'), folder)
            self.assertEqual(json.loads((folder/'gui-result.json').read_text())['gui'], 'unavailable_on_runner')

    def test_success_and_application_exit_keep_the_original_result(self):
        process = Mock()
        with patch.object(runner.subprocess, 'Popen', return_value=process):
            process.wait.return_value = 0
            runner._run_workspace(['app'], Path('report.json'))
            process.wait.assert_called_once_with(timeout=180)
            process.kill.assert_not_called()
            process.wait.return_value = 7
            with self.assertRaises(subprocess.CalledProcessError) as raised:
                runner._run_workspace(['app'], Path('report.json'))
            self.assertEqual(raised.exception.returncode, 7)

    def test_macos_timeout_samples_the_live_process_and_preserves_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary)/'gui-workspace.json'
            report.write_text('{}', encoding='utf-8')
            process = Mock(pid=123)
            timeout = subprocess.TimeoutExpired(['app'], 180)
            process.wait.side_effect = [timeout, -9]
            def sample(command, **kwargs):
                process.kill.assert_not_called()
                self.assertEqual(command[:3], ['/usr/bin/sample', '123', '1'])
                self.assertEqual(kwargs['timeout'], 10)
                Path(command[-1]).write_text('native stack', encoding='utf-8')
                return subprocess.CompletedProcess(command, 0, stdout='sample collected')
            with patch.object(runner.sys, 'platform', 'darwin'), \
                    patch.object(runner.subprocess, 'Popen', return_value=process), \
                    patch.object(runner.subprocess, 'run', side_effect=sample), \
                    self.assertRaises(subprocess.TimeoutExpired) as raised:
                runner._run_workspace(['app'], report)
            self.assertIs(raised.exception, timeout)
            process.kill.assert_called_once()
            self.assertEqual(report.read_text(encoding='utf-8'), '{}')
            self.assertEqual(report.with_suffix('.sample.txt').read_text(), 'native stack')

    def test_failed_sampling_still_kills_and_reports_the_workspace_timeout(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary)/'report.json'
            for failure in (OSError('sample unavailable'),
                            subprocess.TimeoutExpired(['sample'], 10)):
                process = Mock(pid=123)
                timeout = subprocess.TimeoutExpired(['app'], 180)
                process.wait.side_effect = [timeout, -9]
                with self.subTest(failure=type(failure).__name__), \
                        patch.object(runner.sys, 'platform', 'darwin'), \
                        patch.object(runner.subprocess, 'Popen', return_value=process), \
                        patch.object(runner.subprocess, 'run', side_effect=failure), \
                        self.assertRaises(subprocess.TimeoutExpired) as raised:
                    runner._run_workspace(['app'], report)
                self.assertIs(raised.exception, timeout)
                process.kill.assert_called_once()
                self.assertTrue(report.with_suffix('.sample.log').is_file())

    def test_other_platforms_keep_the_same_timeout_without_macos_tools(self):
        process = Mock()
        process.wait.side_effect = [subprocess.TimeoutExpired(['app'], 180), -9]
        with patch.object(runner.sys, 'platform', 'win32'), \
                patch.object(runner.subprocess, 'Popen', return_value=process), \
                patch.object(runner.subprocess, 'run') as sample, \
                self.assertRaises(subprocess.TimeoutExpired):
            runner._run_workspace(['app'], Path('report.json'))
        sample.assert_not_called()
        process.kill.assert_called_once()


if __name__ == '__main__':
    unittest.main()
