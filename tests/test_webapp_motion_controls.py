# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Display cadence and input bursts against the actual browser app module."""
import os
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]

class WebMotionControlsTests(unittest.TestCase):
    def test_motion_cadence_and_latest_input_without_worker_backlogs(self):
        node = os.environ.get('RATIOLAB_TEST_NODE') or shutil.which('node') or shutil.which('nodejs')
        if not node:
            self.skipTest('Node.js is required for browser motion checks')
        result = subprocess.run([node, '--experimental-vm-modules', str(ROOT/'tests/webapp_motion_controls.mjs')],
                                cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout+'\n'+result.stderr)
        self.assertIn('latest scrub checks passed', result.stdout)
