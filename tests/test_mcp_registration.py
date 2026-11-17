# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Direct registration preserves unrelated client settings and launch arguments."""
import json
from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import mcp_registration as registration

LAUNCH = {'command': '/opt/Ratio Lab/RatioLab-MCP', 'args': ['--workspace', '/tmp/Project Ω']}


class RegistrationTests(unittest.TestCase):
    def test_opencode_native_jsonc_keeps_comments_and_existing_servers(self):
        original = '''{
  // Keep the provider settings.
  "model": "provider/model//suffix",
  "mcp": {
    "timeout": {"startup": 30000},
    "servers": {
      // Existing server
      "other": {"type": "remote", "url": "https://example.com/mcp"},
    },
  },
}
'''
        updated = registration.merge_configuration(original, 'opencode', LAUNCH)
        self.assertIn('// Keep the provider settings.', updated)
        self.assertIn('"model": "provider/model//suffix"', updated)
        self.assertIn('// Existing server\n      "other":', updated)
        data = json.loads(registration._mask_jsonc(updated))
        servers = data['mcp']['servers']
        self.assertEqual(servers['other']['url'], 'https://example.com/mcp')
        self.assertEqual(servers['ratiolab']['command'], [LAUNCH['command'], *LAUNCH['args']])
        self.assertEqual(registration.merge_configuration(updated, 'opencode', LAUNCH), updated)

    def test_copilot_update_changes_only_launch_parameters(self):
        original = '{"mcpServers":{"ratiolab":{"command":"old","args":[],"tools":["ratiolab.discover"],"env":{"KEY":"value"}}}}\n'
        update = registration.merge_configuration(original, 'copilot', LAUNCH)
        registered = json.loads(update)['mcpServers']['ratiolab']
        self.assertEqual(registered, {**LAUNCH, 'type': 'stdio', 'tools': ['ratiolab.discover'],
                                      'env': {'KEY': 'value'}})

    def test_does_not_overwrite_conflicting_or_invalid_configuration(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)/'config.json'
            for data in ('{"mcpServers":{"ratiolab":{"url":"https://example.com"}}}',
                         '{"mcpServers":{},"mcpServers":{}}', '{"mcpServers":[]}', '{"mcpServers":'):
                with self.subTest(data=data):
                    path.write_text(data, encoding='utf-8')
                    with patch.object(registration, 'config_path', return_value=path):
                        with self.assertRaises(ValueError):
                            registration.register('cursor', LAUNCH)
                    self.assertEqual(path.read_text(encoding='utf-8'), data)

    def test_creates_and_reuses_continue_project_entry(self):
        with TemporaryDirectory() as directory:
            project = Path(directory)
            registration.register('continue', LAUNCH, project=project)
            path = project/'.continue/mcpServers/ratiolab.json'
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')), {'mcpServers': {'ratiolab': LAUNCH}})
            timestamp = path.stat().st_mtime_ns
            registration.register('continue', LAUNCH, project=project)
            self.assertEqual(path.stat().st_mtime_ns, timestamp)

    def test_uses_native_codex_cli_with_separate_arguments(self):
        with patch.object(registration.shutil, 'which', return_value='/bin/codex'), \
                patch.object(registration.subprocess, 'run') as run:
            run.side_effect = [CompletedProcess([], 0, stdout=b'[]'),
                               CompletedProcess([], 0, stdout=b'')]
            registration.register('codex', {**LAUNCH, 'env': {'PYTHONPATH': '/my source/src'}})
            self.assertEqual(run.call_args.args[0],
                             ['/bin/codex', 'mcp', 'add', 'ratiolab', '--env', 'PYTHONPATH=/my source/src',
                              '--', LAUNCH['command'], *LAUNCH['args']])

    def test_leaves_customized_codex_entry_intact(self):
        entry = {'enabled': True, 'transport': {'type': 'stdio'}, 'tool_timeout_sec': 10}
        with patch.object(registration.shutil, 'which', return_value='/bin/codex'), \
                patch.object(registration.subprocess, 'run') as run:
            run.side_effect = [CompletedProcess([], 0, stdout=b'[{"name":"ratiolab"}]'),
                               CompletedProcess([], 0, stdout=json.dumps(entry).encode())]
            with self.assertRaises(registration.RegistrationError):
                registration.register('codex', LAUNCH)
            self.assertEqual(run.call_count, 2)
