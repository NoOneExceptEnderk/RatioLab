# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Wolfrom browser boundary parity and transactional document regressions."""
from array import array
from copy import deepcopy
from io import BytesIO
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'webapp'))
import engine_bridge as web
import geometry
import motion
import stl_export
import cad_export
import profile_export
import bom
import engineering


class WolfromWebTests(unittest.TestCase):
    def source(self, **parameters):
        self.engine = web.Engine()
        return self.engine.call('generate', dict(family='wolfrom', parameters=parameters))

    def exported(self, kind, **extra):
        result = self.engine.call('export', dict(design_id=self.engine.design_id, kind=kind, **extra))
        return self.engine.buffers[result['buffer']]

    def test_signed_native_mesh_motion_and_all_eighteen_part_metadata(self):
        for p2, ratio in [(59, 600), (61, -600)]:
            with self.subTest(planet2=p2):
                result = self.source(planet2=p2)
                native = geometry.generate('wolfrom', dict(planet2=p2))
                self.assertEqual(len(result['parts']), 18)
                self.assertEqual(result['analysis'], native.analysis)
                self.assertEqual(result['values'], native.values)
                self.assertEqual(result['analysis']['wolfrom']['signed_ratio'], ratio)
                plan = motion.build_plan(native)
                for record, part in zip(result['parts'], native.parts):
                    self.assertEqual(record['port'], part.port)
                    self.assertEqual(record['profile_geometry'], part.profile_metadata)
                    self.assertEqual(record['manufacturing'], part.manufacturing)
                    triangles = list(stl_export.triangles(part))
                    expected = array('f', (x for triangle in triangles for vertex in triangle for x in vertex))
                    packed = array('f'); packed.frombytes(self.engine.buffers[record['mesh']['positions']])
                    self.assertEqual(packed, expected)
                    self.assertEqual(len(self.engine.buffers[record['mesh']['normals']]), len(expected)*4)
                posed = self.engine.call('pose', dict(design_id=result['design_id'], phases=[-.75, 0, 1.25]))
                for phase, frame in zip([-.75, 0, 1.25], posed['frames']):
                    self.assertEqual([row['matrix'] for row in frame['parts']], [plan.matrix(i, phase) for i in range(18)])

    def test_signed_zero_rates_reuse_meshes_and_preserve_all_coordinate_phases(self):
        self.source()
        for rpm in (-600, 0, 600):
            before, plan, phase = self.engine.design, self.engine.plan, 1.2345
            old_matrices = [plan.matrix(i, phase) for i in range(18)]
            expected = geometry.generate('wolfrom', dict(before.values, input_rpm=rpm))
            with patch.object(geometry, 'generate', side_effect=AssertionError('regeneration')), \
                    patch.object(stl_export, 'triangles', side_effect=AssertionError('mesh work')):
                result = self.engine.call('rates', dict(design_id=self.engine.design_id, rpm_patch=dict(input_rpm=rpm), phase=phase))
            self.assertEqual(self.engine.buffers, [])
            self.assertNotIn('parts', result)
            self.assertEqual(result['analysis'], expected.analysis)
            self.assertEqual(result['values']['input_rpm'], rpm)
            self.assertEqual(result['analysis']['kinematics']['rates_rpm'], dict(sun=rpm, carrier=rpm/10, planet=-rpm/8, output=rpm/600, ring=0))
            for i, (new, old) in enumerate(zip(self.engine.design.parts, before.parts)):
                self.assertIs(new.outer, old.outer)
                self.assertIs(new.mesh, old.mesh)
                for a, b in zip(self.engine.plan.matrix(i, phase), old_matrices[i]):
                    self.assertAlmostEqual(a, b, places=11)

    def test_rejected_live_import_and_packing_preserve_accepted_source_and_queries(self):
        accepted = self.source()
        query = self.engine.remember('fixture', {'exact': .5921052631578947}, 'accepted query')
        self.engine.surfaces[0] = ('retained facet cache',)
        state = dict(self.engine.__dict__, buffers=list(self.engine.buffers), surfaces=dict(self.engine.surfaces))
        bad = [dict(planet2=60), dict(planets=4), dict(module=-1), dict(variant='helical')]
        bad += [{key: 0} for key in ('helix', 'double_style', 'profile_shift', 'module2', 'fixed_ring', 'one_rim')]
        for values in bad:
            for method in ('generate', 'import_project'):
                with self.subTest(method=method, values=values):
                    args = dict(family='wolfrom', parameters=values) if method == 'generate' else dict(project=dict(format=web.PROJECT_FORMAT, family='wolfrom', parameters=values))
                    with self.assertRaises(ValueError): self.engine.call(method, args)
                    self.assertEqual(self.engine.__dict__, state)
                    self.assertIs(self.engine.design, state['design'])
                    self.assertIs(self.engine.plan, state['plan'])
        with patch.object(self.engine, 'pack_design', side_effect=ValueError('transport budget')):
            with self.assertRaisesRegex(ValueError, 'transport budget'):
                self.engine.call('generate', dict(family='wolfrom', parameters={}))
        self.assertEqual(self.engine.__dict__, state)
        self.assertEqual(self.engine.call('project', dict(design_id=accepted['design_id']))['project']['family'], 'wolfrom')
        self.assertEqual(self.engine.query, query)
        with patch.object(web, '_engine', self.engine):
            failed = json.loads(web.dispatch('generate', json.dumps(dict(family='wolfrom', parameters=dict(planet2=60)))))
        self.assertFalse(failed['ok'])
        self.assertNotIn('result', failed)
        self.assertIs(self.engine.design, state['design'])
        self.assertIs(self.engine.plan, state['plan'])
        self.assertEqual(self.engine.design_id, accepted['design_id'])
        self.assertEqual(self.engine.query, query)

    def test_precise_project_and_every_export_keep_native_geometry_and_metadata(self):
        result = self.source(module=.5000000001234567, width2=6.1234567890123, input_rpm=-600.123456789123)
        native = deepcopy(self.engine.design)
        project = json.loads(self.exported('project'))
        self.assertEqual(project['parameters'], native.values)
        imported = self.engine.call('import_project', dict(project=dict(project, parameters=dict(project['parameters'], future={'ignored': True}))))
        self.assertEqual(imported['ignored_parameters'], ['future'])
        self.assertEqual(imported['values'], result['values'])
        self.assertEqual(self.engine.design.parts, native.parts)
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            stl_export.export(native, folder/'model')
            cad_export.write_files(native, folder)
            profile_export.write_files(native, folder)
            bom.export(native, folder/'model')
            for kind, names in [('stl', ['model.stl']), ('step', ['assembly.step', 'step-info.json']),
                                ('svg', ['profiles.json']), ('dxf', ['profiles.json']), ('bom', ['model.bom.json', 'model.bom.csv'])]:
                with self.subTest(kind=kind), ZipFile(BytesIO(self.exported(kind))) as output:
                    self.assertEqual(json.loads(output.read('model.config.json')), project)
                    for name in names: self.assertEqual(output.read(name), (folder/name).read_bytes())
                    if kind in ('svg', 'dxf'):
                        for name in output.namelist():
                            if name.endswith('.'+kind): self.assertEqual(output.read(name), (folder/name).read_bytes())
            with ZipFile(BytesIO(self.exported('report'))) as output:
                self.assertEqual(json.loads(output.read('model.calculations.json')), native.analysis)
                self.assertEqual(output.read('model.calculations.txt').decode(), engineering.report_text(native))
            png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aLuUAAAAASUVORK5CYII=')
            with ZipFile(BytesIO(self.exported('package', preview_png=list(png)))) as output:
                self.assertEqual(output.read('preview.png'), png)
                self.assertTrue(json.loads(output.read('manifest.json'))['complete'])
                self.assertEqual(json.loads(output.read('model.config.json')), project)
                self.assertEqual(json.loads(output.read('model.calculations.json')), native.analysis)

    def test_actual_browser_fields_fixed_connections_stale_drafts_and_history(self):
        node = os.environ.get('RATIOLAB_TEST_NODE') or shutil.which('node') or shutil.which('nodejs')
        if not node: self.skipTest('Node.js is required for JS state regressions')
        result = self.source()
        result.pop('parts')
        fixture = dict(schema=web.schema('wolfrom'), previous_schema=web.schema('parallel'), design=result)
        process = subprocess.run([node, '--experimental-vm-modules', str(ROOT/'tests/webapp_wolfrom_state.mjs')],
                                 cwd=ROOT, input=json.dumps(fixture), capture_output=True, text=True, timeout=30)
        self.assertEqual(process.returncode, 0, process.stdout+'\n'+process.stderr)
        self.assertIn('Wolfrom browser state checks passed', process.stdout)


if __name__ == '__main__':
    unittest.main()
