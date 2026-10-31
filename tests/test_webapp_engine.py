# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Native engine parity; these tests do not establish WebAssembly compatibility."""
from array import array
from io import BytesIO
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
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


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = web.Engine()

    def generate(self, family='spur', parameters=None):
        return self.engine.call('generate', dict(family=family, parameters=parameters or {}))

    def test_catalog_exposes_all_numeric_fields_variants_options_and_help(self):
        result = self.engine.call('catalog', {})
        self.assertEqual([r['key'] for r in result['families']], list(geometry.FAMILIES))
        for row in result['families']:
            family = row['key']
            options = {p['key']: p for p in row['options']}
            self.assertIn('bearing_mode', options)
            self.assertIn('hardware_mode', options)
            if family in geometry.VARIANTS:
                self.assertEqual([p['value'] for p in options['variant']['choices']], list(geometry.VARIANTS[family]))
            for variant in geometry.VARIANTS.get(family, {None: None}):
                schema = self.engine.call('schema', dict(family=family, parameters=dict(variant=variant) if variant else {}))
                fields = {p['key']: p for p in schema['fields']}
                self.assertEqual(set(fields), {p[0] for p in geometry.get_specs(family, variant)})
                for field in fields.values():
                    self.assertIsInstance(field['help'], dict, (family, field['key']))
                    self.assertTrue(field['help']['meaning'])
        differential = next(p for p in result['families'] if p['key'] == 'differential')
        self.assertTrue({'configuration', 'ratio_mode', 'carrier_style', 'output_interface'} <= {p['key'] for p in differential['options']})

    def test_all_ten_family_default_meshes_use_actual_shared_triangles(self):
        # Independently re-triangulate source geometry and compare every vertex's
        # float32 transport and every double-precision bound, not a canned model.
        for family in geometry.FAMILIES:
            with self.subTest(family=family):
                result = self.generate(family)
                native = geometry.generate(family, {})
                self.assertEqual(result['values'], native.values)
                self.assertEqual(result['analysis'], native.analysis)
                self.assertEqual([p['name'] for p in result['parts']], [p.name for p in native.parts])
                triangle_count = 0
                for record, part in zip(result['parts'], native.parts):
                    triangles = list(stl_export.triangles(part))
                    triangle_count += len(triangles)
                    expected = [coordinate for triangle in triangles for point in triangle for coordinate in point]
                    self.assertEqual(self.engine.buffers[record['mesh']['positions']], web.float_bytes(expected))
                    self.assertEqual(record['mesh']['vertex_count'], len(triangles)*3)
                    for axis in range(3):
                        self.assertEqual(record['bounds_mm']['minimum'][axis], min(expected[axis::3]))
                        self.assertEqual(record['bounds_mm']['maximum'][axis], max(expected[axis::3]))
                    normals = array('f'); normals.frombytes(self.engine.buffers[record['mesh']['normals']])
                    for i in range(0, len(normals), 3):
                        self.assertAlmostEqual(sum(n*n for n in normals[i:i+3]), 1, places=5)
                    if part.name.startswith('Flexspline'):
                        self.assertIn('material', record['mesh'])
                        self.assertEqual(len(self.engine.buffers[record['mesh']['material']]), len(expected)*4)
                self.assertEqual(result['triangle_count'], triangle_count)
                self.assertEqual(result['motion']['supported'], True)
                self.assertEqual(len(self.engine.buffers), sum(3 if 'material' in p['mesh'] else 2 for p in result['parts']))

    def test_pose_uses_canonical_differential_and_flex_deformation(self):
        for family, values in [('differential', dict(input_rpm=23, input_b_rpm=-7)), ('harmonic', {})]:
            result = self.generate(family, values)
            native = motion.build_plan(geometry.generate(family, values))
            poses = self.engine.call('pose', dict(design_id=result['design_id'], phases=[0, 1.25, -2]))
            for frame in poses['frames']:
                for part in frame['parts']:
                    i, phase = part['index'], frame['phase']
                    self.assertEqual(part['matrix'], native.matrix(i, phase))
                    self.assertEqual(part['deformation'], native.deformation(i, phase))
            self.assertEqual(self.engine.buffers, [])

    def test_only_active_design_is_kept_and_bad_generation_invalidates_it(self):
        result = self.generate()
        previous_id = result['design_id']
        with self.assertRaises(ValueError):
            self.generate('spur', dict(module=-2))
        self.assertIsNone(self.engine.design)
        with self.assertRaises(web.BridgeError) as context:
            self.engine.call('project', dict(design_id=previous_id))
        self.assertEqual(context.exception.code, 'stale_design')
        result = self.generate('helical')
        self.assertGreater(result['design_id'], previous_id)
        self.assertEqual(len(self.engine.buffers), 2)

    def test_bad_parameters_are_rejected_without_coercing_typed_values(self):
        for values in [dict(teeth=True), dict(module='2'), dict(bearing_mode=1), dict(hardware_keys='yes'), dict(foo=1), dict(module=float('nan'))]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.engine.call('validate', dict(family='spur', parameters=values))

    def exported(self, kind, indices=None, **extra):
        args = dict(design_id=self.engine.design_id, kind=kind, **extra)
        if indices is not None: args['indices'] = indices
        result = self.engine.call('export', args)
        data = self.engine.buffers[result['buffer']]
        self.assertEqual(result['bytes'], len(data))
        return result, data

    def test_desktop_project_round_trip_preserves_normalized_exact_values(self):
        generated = self.generate('helical', dict(module=2.1234567890123, teeth=22))
        _, data = self.exported('project')
        project = json.loads(data)
        self.assertEqual(project['format'], 'solidcraft-riduttori/1')
        self.assertEqual(project['parameters'], generated['values'])
        imported = self.engine.call('import_project', dict(project=project))
        self.assertEqual(imported['values'], generated['values'])
        self.assertEqual(project['parameters']['module'], 2.1234567890123)
        project['selected_export'] = {}
        with self.assertRaises(web.BridgeError): self.engine.call('import_project', dict(project=project))

    def test_stl_and_selected_parts_match_native_binary_geometry(self):
        self.generate('parallel')
        native = geometry.generate('parallel', {})
        result, data = self.exported('stl', indices=[1])
        self.assertFalse(result['scope']['complete_assembly'])
        with ZipFile(BytesIO(data)) as archive, tempfile.TemporaryDirectory() as temporary:
            expected = Path(temporary)/'expected.stl'
            stl_export.write_stl(expected, [native.parts[1]])
            self.assertEqual(archive.read('model.stl'), expected.read_bytes())
            self.assertEqual(json.loads(archive.read('selection.json'))['source_indices'], [2])
            self.assertEqual(len([p for p in archive.namelist() if p.endswith('.stl')]), 2)
            raw = archive.read('model.stl')
            self.assertEqual(len(raw), 84+50*struct.unpack('<I', raw[80:84])[0])

    def test_step_svg_dxf_bom_and_report_reuse_canonical_exporters(self):
        self.generate()
        native = geometry.generate('spur', {})
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            cad_export.write_files(native, folder)
            profile_export.write_files(native, folder)
            bom.export(native, folder/'model')
            for kind, names in [('step', ['assembly.step', 'step-info.json']), ('svg', ['profiles.json']), ('dxf', ['profiles.json']),
                                ('bom', ['model.bom.json', 'model.bom.csv', 'model.bom.txt'])]:
                _, data = self.exported(kind)
                with ZipFile(BytesIO(data)) as archive:
                    for name in names: self.assertEqual(archive.read(name), (folder/name).read_bytes())
                    if kind in ('svg', 'dxf'):
                        profile = next(p for p in archive.namelist() if p.endswith('.'+kind))
                        self.assertEqual(archive.read(profile), (folder/profile).read_bytes())
            _, data = self.exported('report')
            with ZipFile(BytesIO(data)) as archive:
                self.assertEqual(archive.read('model.calculations.txt').decode(), engineering.report_text(native))
                self.assertEqual(json.loads(archive.read('model.calculations.json')), native.analysis)

    def test_complete_package_requires_png_and_keeps_portable_source_references(self):
        self.generate('helical')
        with self.assertRaises(web.BridgeError): self.exported('package')
        # Actual 1x1 PNG test fixture; no screenshot is fabricated in production.
        import base64
        png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aLuUAAAAASUVORK5CYII=')
        _, data = self.exported('package', preview_png=list(png))
        with ZipFile(BytesIO(data)) as archive:
            self.assertEqual(archive.read('preview.png'), png)
            self.assertTrue(json.loads(archive.read('manifest.json'))['complete'])
            commands = json.loads(archive.read('model.script.json'))['commands']
            paths = [p['params']['path'] for p in commands if p['command']=='file.insert_step']
            self.assertTrue(paths)
            self.assertTrue(all(p.startswith('assets/') and p in archive.namelist() for p in paths))

    def test_binary_preview_does_not_expand_into_rpc_json(self):
        response = json.loads(web.dispatch('generate', json.dumps(dict(family='spur', parameters={}))))
        design_id = response['result']['design_id']
        import base64
        png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aLuUAAAAASUVORK5CYII=')
        # Keep a valid PNG, adding a legal tEXt chunk larger than the 1 MiB
        # control-JSON cap. Binary transport must accept it without JSON expansion.
        import zlib
        text = b'Comment\0'+b'x'*(web.MAX_INPUT_BYTES+1)
        chunk = struct.pack('>I', len(text))+b'tEXt'+text+struct.pack('>I', zlib.crc32(b'tEXt'+text))
        png = png[:-12]+chunk+png[-12:]
        self.assertGreater(len(png), web.MAX_INPUT_BYTES)
        response = json.loads(web.dispatch('export', json.dumps(dict(design_id=design_id, kind='package')), memoryview(png)))
        self.assertTrue(response['ok'], response)
        with ZipFile(BytesIO(web.buffer(response['result']['buffer']))) as archive:
            self.assertEqual(archive.read('preview.png'), png)
        web.clear_buffers()
        response = json.loads(web.dispatch('export', json.dumps(dict(design_id=design_id, kind='package')), memoryview(b'x'*16777217)))
        self.assertFalse(response['ok'])
        self.assertIn('16 MiB', response['error']['message'])
        self.assertEqual(web._engine.buffers, [])

    def test_rpc_returns_structured_errors_and_bounded_buffers(self):
        response = json.loads(web.dispatch('generate', json.dumps(dict(family='spur', parameters={}))))
        self.assertTrue(response['ok'])
        self.assertEqual(response['buffer_count'], 2)
        self.assertIsInstance(web.buffer(0), bytes)
        error = json.loads(web.dispatch('generate', json.dumps(dict(family='spur', parameters=dict(module=-1)))))
        self.assertFalse(error['ok'])
        self.assertEqual(error['error']['code'], 'invalid_parameters')
        self.assertEqual(web._engine.buffers, [])
        self.assertEqual(json.loads(web.dispatch('unknown', '{}'))['error']['code'], 'unknown_method')


if __name__ == '__main__': unittest.main()
