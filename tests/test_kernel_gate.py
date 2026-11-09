# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""The CI entrypoint rejects missing targets, test errors and skipped coverage."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class KernelGateTests(unittest.TestCase):
    def execute(self,source,**overrides):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);(folder/'gate_fixture.py').write_text(source)
            report=folder/'result.json'
            env=dict(os.environ,PYTHONPATH=str(folder)+os.pathsep+os.environ.get('PYTHONPATH',''))
            env.update(overrides)
            child=subprocess.run([sys.executable,str(ROOT/'scripts/check-rust-engine.py'),
                '--tests','gate_fixture','--report',str(report)],env=env,capture_output=True,text=True,timeout=60)
            return child,json.loads(report.read_text())

    def test_skips_are_failed_required_coverage(self):
        child,report=self.execute("import unittest\n@unittest.skip('deliberately unavailable')\nclass Coverage(unittest.TestCase):\n def test_required(self): pass\n")
        self.assertEqual(child.returncode,1);self.assertFalse(report['successful'])
        self.assertEqual(len(report['skips']),1)
        self.assertEqual(report['preflight']['native'],True);self.assertEqual(report['preflight']['wasm'],True)

    def test_test_errors_and_missing_wasm_runtime_are_fatal(self):
        child,report=self.execute("import unittest\nclass Coverage(unittest.TestCase):\n def test_required(self): raise RuntimeError('real fixture error')\n")
        self.assertEqual(child.returncode,1);self.assertEqual(report['errors'],1)
        child,report=self.execute('',RATIOLAB_NODE='/missing-required-ratiolab-node')
        self.assertEqual(child.returncode,1);self.assertFalse(report['successful'])
        self.assertIsNone(report['preflight']);self.assertIn('FileNotFoundError',report['error'])

    def test_real_kernel_subset_records_actual_executed_coverage(self):
        child,report=self.execute("import unittest\nfrom rust_geometry import call\nclass Coverage(unittest.TestCase):\n def test_actual(self):\n  self.assertEqual(call('cylindrical_dimensions',dict(teeth=24,module='2.00000000000000000001'))['values']['pitch_radius_mm'],'24.00000000000000000012')\n")
        self.assertEqual(child.returncode,0,child.stderr);self.assertTrue(report['successful'])
        self.assertEqual(report['tests'],1);self.assertEqual(report['skips'],[])
