# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Browser preference persistence without a browser or native GUI dependency."""
import os
from pathlib import Path
import shutil
import subprocess
import unittest


class BrowserPreferencesTests(unittest.TestCase):
    def test_shared_interface_languages_preserve_engineering_values(self):
        self.run_script('webapp_ui_language.mjs')

    def test_preferences_validate_and_preserve_projects_when_storage_fails(self):
        self.run_script('webapp_preferences.mjs')

    def run_script(self, filename):
        node = os.environ.get('RATIOLAB_TEST_NODE') or shutil.which('node') or shutil.which('nodejs')
        if not node:
            self.skipTest('Node.js is required for the JS preferences regression')
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([node, '--experimental-vm-modules', str(root/'tests'/filename)],
                                cwd=root, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout+'\n'+result.stderr)


if __name__ == '__main__':
    unittest.main()
