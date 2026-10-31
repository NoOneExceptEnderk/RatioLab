# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Camera commands in the actual browser app and renderer modules."""
import os
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CameraControlsTests(unittest.TestCase):
    def test_fit_and_keyboard_orbit_keep_named_view_controls_consistent(self):
        node = os.environ.get('RATIOLAB_TEST_NODE') or shutil.which('node') or shutil.which('nodejs')
        if not node:
            self.skipTest('Node.js is required for the JS camera regression')
        result = subprocess.run([node, '--experimental-vm-modules', str(ROOT/'tests/webapp_camera_controls.mjs')],
                                cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout+'\n'+result.stderr)
        self.assertIn('Camera Fit, keyboard orbit and named-view state checks passed.', result.stdout)


if __name__ == '__main__':
    unittest.main()
