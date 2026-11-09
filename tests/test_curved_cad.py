# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Continuous source checks and the opt-in CAD prototype's export boundaries."""
from collections import Counter
from copy import deepcopy
import importlib.util
import json
from math import hypot
import os
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from geometry import Design, generate
from rust_geometry import call
import cad_export
import curved_cad

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('independent_cad_verifier', ROOT/'scripts/verify-curved-cad.py')
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)


class CurvedCadTests(unittest.TestCase):
    def test_spur_curves_follow_independent_rolling_rack_and_polar_involute(self):
        cases = [({}, .001), (dict(teeth=12,module=1.5,bore=2), .0001),
            (dict(teeth=37,module=.7,bore=2,profile_shift=.2,backlash=.02), .0001),
            (dict(teeth=30), .000001)]
        for parameters,tolerance in cases:
            with self.subTest(parameters=parameters,tolerance=tolerance):
                _,info = curved_cad.document(generate('spur',parameters),tolerance_mm=tolerance)
                profile=info['profile']; sources=profile['reference_sources']; curves=profile['curves']
                self.assertLess(profile['curve_interpolation_bound_mm']+profile['resolution_guard_mm'],tolerance)
                for row in curves:
                    for i in range(17):
                        u=i/16
                        actual=reference.expected(row,u,sources)
                        theoretical=reference.expected(row,u,sources,True)
                        deviation=hypot(actual[0]-theoretical[0],actual[1]-theoretical[1])
                        self.assertLessEqual(deviation,row['interpolation_bound_mm']+row['join_displacement_mm']+4*profile['resolution_guard_mm'])
                for previous,current in zip(curves[-1:]+curves[:-1],curves):
                    end=previous['controls'][-1] if previous['kind']=='cubic' else previous['endpoints'][-1]
                    start=current['controls'][0] if current['kind']=='cubic' else current['endpoints'][0]
                    self.assertEqual(end,start)

    def test_spline_faces_share_watertight_edges_without_refitting_pieces(self):
        text,info=curved_cad.document(generate('spur'))
        self.assertNotIn('FACETED_BREP',text)
        self.assertIn('SURFACE_OF_LINEAR_EXTRUSION',text)
        self.assertIn('B_SPLINE_CURVE_WITH_KNOTS',text)
        self.assertEqual(len(info['patches']),7*24)
        self.assertEqual(text.count('ADVANCED_FACE('),7*24+3)
        self.assertLess(len(info['patches']),len(info['profile']['curves']))
        entities=dict(re.findall(r'^#(\d+)=(.*);$',text,re.M))
        edges={key for key,value in entities.items() if value.startswith('EDGE_CURVE(')}
        counts=Counter()
        for value in entities.values():
            match=re.fullmatch(r"ORIENTED_EDGE\('',\*,\*,#(\d+),(\.[TF]\.)\)",value)
            if match:counts[match.groups()]+=1
        for edge in edges:
            self.assertEqual(counts[edge,'.T.'],1,edge)
            self.assertEqual(counts[edge,'.F.'],1,edge)

    def test_quality_operating_state_and_ordinary_exports_are_preserved(self):
        design=generate('spur',quality=dict(preview_mm=.1,export_mm=.005))
        before=deepcopy(design)
        baseline=cad_export.document(design.parts)
        _,info=curved_cad.document(design,tolerance_mm=.0001)
        self.assertEqual(design,before)
        self.assertEqual(cad_export.document(design.parts),baseline)
        self.assertEqual(info['profile']['requested_curve_mm'],.0001)
        self.assertIn('not performed',info['reader_verification'])
        self.assertFalse(info['profile']['ordinary_sampled_geometry_changed'])

    def test_unsupported_or_modified_parts_are_rejected_instead_of_fitted(self):
        for design in (Design('helical',{}),Design('internal',{}),Design('spur',{},parts=[])):
            with self.assertRaisesRegex(ValueError,'prototype'):curved_cad.document(design)
        for field,value in [('twist',.1),('frame',((0,0,0),(1,0,0),(0,1,0),(0,0,1))),
                            ('mesh',[[[0,0,0],[1,0,0],[0,1,0]]]),('width',11)]:
            design=generate('spur');setattr(design.parts[0],field,value)
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'unchanged'):
                curved_cad.document(design)
        design=generate('spur');design.parts[0].outer[0]=(123.,45.)
        with self.assertRaisesRegex(ValueError,'unchanged'):curved_cad.document(design)
        design=generate('spur');design.parts[0].holes[0]=list(design.parts[0].holes[0])
        with self.assertRaisesRegex(ValueError,'intact concentric'):curved_cad.document(design)
        design=generate('spur');design.parts[0].holes[0].radius=2.
        with self.assertRaisesRegex(ValueError,'intact concentric'):curved_cad.document(design)

    def test_finer_request_refines_curves_without_a_micrometre_floor(self):
        counts=[]
        for tolerance in (.02,.0001,.000001):
            _,info=curved_cad.document(generate('spur'),tolerance_mm=tolerance)
            counts.append(len(info['profile']['curves']))
            self.assertEqual(len(info['patches']),168)
            self.assertLess(info['profile']['curve_interpolation_bound_mm'],tolerance)
        self.assertLess(counts[0],counts[1]);self.assertLess(counts[1],counts[2])
        for tolerance in (0,-.1,float('nan'),float('inf'),True,1e-30):
            with self.subTest(tolerance=tolerance),self.assertRaises(ValueError):
                curved_cad.document(generate('spur'),tolerance_mm=tolerance)

    def test_unachievable_budget_and_cancellation_are_errors(self):
        with self.assertRaisesRegex(ValueError,'budget'):
            call('cad_spur_curves',dict(z=200,mt=2,tolerance_mm=5e-10))
        class Stopped(Exception):pass
        visits=[]
        def check():
            visits.append(True)
            if len(visits)>5:raise Stopped('cancelled CAD fit')
        with self.assertRaisesRegex(Stopped,'cancelled CAD fit'):
            call('cad_spur_curves',dict(z=24,mt=2,tolerance_mm=1e-6),check=check)
        self.assertGreater(len(call('cad_spur_curves',dict(z=24,mt=2))['curves']),0)

    def test_export_preserves_precise_sources_and_cleans_up_failed_publication(self):
        design=generate('spur',dict(module=2,_decimal_inputs={'module':'2.00000000000000000001'}),
            quality=dict(preview_mm=.1,export_mm=.0001))
        with TemporaryDirectory() as temporary:
            output=Path(temporary)/'curved'
            curved_cad.export(design,output)
            config=json.loads((output/'project.config.json').read_text())
            self.assertEqual(config['parameters']['_decimal_inputs']['module'],'2.00000000000000000001')
            self.assertEqual(config['quality'],design.quality)
            repeated=Path(temporary)/'repeated'
            subprocess.run([os.sys.executable,str(ROOT/'scripts/prototype-curved-cad.py'),str(repeated),
                '--project',str(output/'project.config.json'),'--tolerance-mm','.001'],
                cwd=ROOT,capture_output=True,text=True,check=True,timeout=30)
            self.assertEqual(json.loads((repeated/'project.config.json').read_text()),config)
            original=(output/'gear.step').read_bytes()
            with self.assertRaises(FileExistsError):curved_cad.export(design,output)
            self.assertEqual((output/'gear.step').read_bytes(),original)
            failed=Path(temporary)/'failed'
            with patch('curved_cad.write_text',side_effect=OSError('disk failure')):
                with self.assertRaisesRegex(OSError,'disk failure'):curved_cad.export(design,failed)
            self.assertFalse(failed.exists())
            self.assertEqual(sorted(p.name for p in Path(temporary).iterdir()),['curved','repeated'])

    def test_native_and_wasm_curves_share_the_same_contract(self):
        node=os.environ.get('RATIOLAB_NODE') or shutil.which('node')
        if not node:self.skipTest('Node is required to execute the shared Wasm kernel.')
        requests=[dict(operation='cad_spur_curves',parameters=dict(z=z,mt=2,tolerance_mm=t))
            for z,t in ((24,.001),(12,.0001),(30,.000001))]
        with TemporaryDirectory() as temporary:
            path=Path(temporary)/'requests.json';path.write_text(json.dumps(requests))
            completed=subprocess.run([node,str(ROOT/'tests/rust_wasm_protocol.mjs'),str(ROOT),str(path)],
                capture_output=True,text=True,check=True,timeout=60)
            wasm=json.loads(completed.stdout)
        def compare(a,b):
            if isinstance(a,float):self.assertAlmostEqual(a,b,delta=max(1e-10,abs(a)*1e-12))
            elif isinstance(a,dict):
                self.assertEqual(set(a),set(b))
                for key in a:compare(a[key],b[key])
            elif isinstance(a,list):
                self.assertEqual(len(a),len(b))
                for x,y in zip(a,b):compare(x,y)
            else:self.assertEqual(a,b)
        for request,answer in zip(requests,wasm):
            self.assertTrue(answer['ok'],answer)
            compare(call(request['operation'],request['parameters']),answer['result'])

    def test_cli_rejects_incomplete_projects_instead_of_exporting_defaults(self):
        cases=[None,dict(family='spur',parameters={}),
            dict(format='solidcraft-riduttori/1',family='spur'),
            dict(format='solidcraft-riduttori/1',family='spur',parameters=[])]
        with TemporaryDirectory() as temporary:
            folder=Path(temporary)
            for index,config in enumerate(cases):
                source=folder/f'{index}.config.json';source.write_text(json.dumps(config))
                target=folder/f'export-{index}'
                result=subprocess.run([os.sys.executable,str(ROOT/'scripts/prototype-curved-cad.py'),
                    str(target),'--project',str(source)],cwd=ROOT,capture_output=True,text=True,timeout=30)
                self.assertEqual(result.returncode,2,result.stderr)
                self.assertFalse(target.exists())


if __name__=='__main__':unittest.main()
