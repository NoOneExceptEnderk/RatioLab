# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Desktop project compatibility and actual browser document action state."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'webapp'))
import engine_bridge as web
import geometry
from test_project_scope import LEGACY


class ProjectTests(unittest.TestCase):
    def project(self, family='helical', **values):
        return dict(format=web.PROJECT_FORMAT, family=family, parameters=values)

    def test_legacy_projects_keep_native_geometry_precision_and_roundtrip_all_families(self):
        for family in geometry.FAMILIES:
            with self.subTest(family=family):
                exact = dict(input_rpm=1234.123456789123)
                if 'module' in geometry.defaults(family):
                    exact['module'] = 2.123456789123
                native = geometry.generate(family, exact)
                old = self.project(family, **dict(native.values, **LEGACY, production='old', future_setting={'ignored': True}))
                engine = web.Engine()
                result = engine.call('import_project', dict(project=json.loads(json.dumps(old))))
                self.assertEqual(engine.design.parts, native.parts)
                self.assertEqual(result['values'], native.values)
                self.assertEqual(result['ignored_parameters'], sorted([*LEGACY, 'production', 'future_setting']))
                for key, value in exact.items():
                    self.assertEqual(result['values'][key], value)
                exported = engine.call('export', dict(design_id=result['design_id'], kind='project'))
                saved = json.loads(engine.buffers[exported['buffer']])
                self.assertEqual(saved, self.project(family, **native.values))
                restored = engine.call('import_project', dict(project=saved))
                self.assertEqual(restored['values'], native.values)
                self.assertEqual(restored['ignored_parameters'], [])

    def test_import_keeps_nondefault_variant_specific_fields_and_options(self):
        cases = [
            ('planetary', dict(variant='two_stage_double', double_style='separated', sun2=20, planet2=16, width2=12.123456789123)),
            ('cycloidal', dict(variant='dual', eccentric_design='fdm_bolted', io_scheme='eccentric_output_ring')),
            ('differential', dict(configuration='classic', variant='spiral', output_difference_rpm=31.1234567890123)),
            ('harmonic', dict(variant='hat', harmonic_output='circular')),
        ]
        for family, values in cases:
            with self.subTest(family=family):
                native = geometry.generate(family, values)
                engine = web.Engine()
                result = engine.call('import_project', dict(project=self.project(family, **dict(values, **LEGACY))))
                self.assertEqual(result['values'], native.values)
                self.assertEqual(engine.design.parts, native.parts)

    def test_known_invalid_values_stay_errors_and_live_unknown_keys_stay_strict(self):
        for values in [dict(module='2'), dict(module=True), dict(module=-1), dict(module=float('nan')),
                       dict(variant='removed'), dict(hardware_bolts='yes'), dict(hardware_mode='removed')]:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    web.Engine().call('import_project', dict(project=self.project('parallel', **dict(values, **LEGACY))))
        for method in ['generate', 'validate']:
            with self.subTest(method=method):
                with self.assertRaisesRegex(web.BridgeError, 'Unknown parameter: material'):
                    web.Engine().call(method, dict(family='helical', parameters=dict(material='obsolete')))
        for parameters in [None, [], 'wrong', {1: 2}]:
            with self.subTest(parameters=parameters):
                project = self.project(); project['parameters'] = parameters
                with self.assertRaisesRegex(web.BridgeError, 'object with string keys'):
                    web.Engine().call('import_project', dict(project=project))
        project = self.project(); project['selected_export'] = {}
        with self.assertRaisesRegex(web.BridgeError, 'complete'):
            web.Engine().call('import_project', dict(project=project))

    def test_document_actions_confirm_exact_rates_and_reject_async_stale_snapshots(self):
        node = os.environ.get('RATIOLAB_TEST_NODE') or shutil.which('node') or shutil.which('nodejs')
        if not node:
            self.skipTest('Node.js is required for the JS state regression')
        fixture = dict(schema=web.schema('parallel'), values=geometry.generate('parallel').values)
        result = subprocess.run([node, '--experimental-vm-modules', str(ROOT/'tests/webapp_document_actions.mjs')],
                                cwd=ROOT, input=json.dumps(fixture), capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout+'\n'+result.stderr)
        self.assertIn('document action checks passed', result.stdout)


if __name__ == '__main__':
    unittest.main()
