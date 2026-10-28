# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Keep native timeout diagnostics separate from the application's JSON report."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location(
    'gui_runner_test', Path(__file__).parent/'scripts/check-installed-gui.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class NativeGuiRunnerTests(unittest.TestCase):
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
