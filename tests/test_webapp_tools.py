# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Run actual JS controllers under state/DOM doubles; no browser claim."""
import os
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ToolsTests(unittest.TestCase):
    def test_analysis_ownership_precision_apply_and_candidate_resource_lifecycle(self):
        node = os.environ.get('RATIOLAB_TEST_NODE') or shutil.which('node') or shutil.which('nodejs')
        if not node:
            self.skipTest('Node.js is required for the JS state regression')
        result = subprocess.run([node, '--experimental-vm-modules', str(ROOT/'tests/webapp_tools_state.mjs')],
                                cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout+'\n'+result.stderr)
        self.assertIn('inverse-camera checks passed', result.stdout)


if __name__ == '__main__':
    unittest.main()
