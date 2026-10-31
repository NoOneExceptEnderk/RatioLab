# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""The release MCP gate must exercise real Wolfrom subprocesses in both eras."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('wolfrom_mcp_verifier', ROOT/'scripts/check-installed-mcp.py')
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class WolfromSubprocessTests(unittest.TestCase):
    def test_current_source_passes_the_complete_installed_mcp_gate(self):
        # Use the same external process/stdio/file checks as frozen bundles.
        # An absolute source path remains valid after the verifier changes cwd.
        environment = dict(os.environ, PYTHONPATH=str(ROOT/'src'))
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary)/'mcp.json'
            result = verifier.check(sys.executable, report, module=True, environment=environment)
            self.assertEqual(json.loads(report.read_text(encoding='utf-8')), result)
        self.assertEqual(result['mcp'], 'passed')
        self.assertFalse(result['display_required'])
        self.assertEqual([row['protocol'] for row in result['protocols']], [verifier.MODERN, verifier.LEGACY])
        for proof in result['protocols']:
            with self.subTest(protocol=proof['protocol']):
                self.assertEqual(proof['families'], 11)
                self.assertEqual(proof['wolfrom']['components'], 18)
                self.assertEqual(proof['wolfrom']['signed_ratio'], 600)
                self.assertEqual(proof['wolfrom']['singular_preservation'], 'passed')
                self.assertEqual(proof['wolfrom']['save_open'], 'passed')
                self.assertEqual(len(proof['wolfrom']['stl_sha256']), 7)
                # Legacy gates must keep protecting the existing parallel flow.
                self.assertEqual(proof['stale_revision'], 'rejected')
                self.assertEqual(proof['path_escape'], 'rejected')
                self.assertEqual(proof['step_subset'], 'passed')


if __name__ == '__main__':
    unittest.main()
