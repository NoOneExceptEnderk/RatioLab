# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Construction ownership, failure recovery and complete native/Wasm packets.

Independent tooth/velocity/swept-envelope oracles remain in the existing bevel,
hypoid, face and herringbone suites; these tests cover the new port boundaries.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from geometry import Design,generate,validate,part_from_kernel
from precise_numbers import transport
from rust_geometry import call,call_geometry,_buffer_result

ROOT=Path(__file__).resolve().parents[1]
CASES=[('bevel',dict(variant=v,**({'spiral_hand':h} if v!='straight' else {})))
       for v in ('straight','spiral','zerol') for h in ((1,) if v=='straight' else (-1,1))]
CASES += [('hypoid',dict(offset=e)) for e in (-2,0,2)]
CASES += [('face',dict(variant=v,**p)) for v,p in [
    ('spur',{}),('helical',dict(helix=15,offset=5)),('helical',dict(helix=-15,offset=-5)),
    ('double_helical',dict(double_style='joined',helix=15)),
    ('double_helical',dict(double_style='joined',helix=-15,offset=5)),
    ('double_helical',dict(double_style='separated',helix=15)),
    ('double_helical',dict(double_style='separated',helix=-15,offset=-5)),
    ('double_helical',dict(double_style='joined',helix=0)),('spur',dict(bore=0,output_bore=0))]]
OPS={'bevel':'construction_bevel_pair','hypoid':'construction_hypoid','face':'construction_face'}


class RustNewFamiliesTests(unittest.TestCase):
    def test_builders_do_not_execute_python_generator_or_station_math(self):
        import bevel_pair,hypoid_geometry,face_geometry,rack_geometry
        for family,values in CASES:
            with self.subTest(family=family,values=values):
                d=Design(family,validate(family,values))
                with (patch.object(bevel_pair,'dimensions',side_effect=AssertionError('Python dimensions')),
                     patch.object(bevel_pair,'curved_section',side_effect=AssertionError('Python curved section')),
                     patch.object(hypoid_geometry.Generator,'__init__',side_effect=AssertionError('Python hypoid generator')),
                     patch.object(face_geometry.Generator,'__init__',side_effect=AssertionError('Python face generator')),
                     patch.object(rack_geometry,'_stations',side_effect=AssertionError('Python stations'))):
                    {'bevel':bevel_pair,'hypoid':hypoid_geometry,'face':face_geometry}[family].build(d)
                self.assertEqual(len(d.parts),2)
                self.assertTrue(d.analysis)

    def test_new_constructions_keep_circle_provenance_and_owned_meshes(self):
        for family in OPS:
            first=generate(family);second=generate(family)
            for old,new in zip(first.parts,second.parts):
                self.assertEqual(old,new)
                for hole in new.holes:
                    self.assertTrue(hole.intact())
                if old.mesh:
                    self.assertIsNot(old.mesh,new.mesh)
                    saved=old.mesh[0][0][0];new.mesh[0][0][0]=(999,999,999)
                    self.assertEqual(old.mesh[0][0][0],saved)
                if old.stations:
                    self.assertIsNot(old.stations,new.stations)
                    saved=old.stations[0]['outer'][0];new.stations[0]['outer'][0]=(999,999)
                    self.assertEqual(old.stations[0]['outer'][0],saved)

    def test_source_decimal_precision_survives_face_pinion_construction(self):
        d=generate('face',dict(module=2,_decimal_inputs={'module':'2.00000000000000000001'}))
        self.assertEqual(d.parts[0].profile_metadata['analytic_values']['pitch_radius_mm'],
                         '24.00000000000000000012')
        self.assertTrue(d.parts[0].profile_metadata['analytic_precision']['agreement'])

    def test_face_pinion_retains_shared_shoulder_and_side_triangle_refinement(self):
        from face_geometry import Generator
        from rack_geometry import _stations
        for beta,offset in ((15,0),(-15,0),(15,5),(-15,-5),(0,0)):
            values=validate('face',dict(variant='double_helical',double_style='separated',helix=beta,offset=offset))
            expected,_=_stations(Generator(values).pinion)
            actual=call_geometry('construction_face',dict(values=values))['parts'][0]['stations']
            with self.subTest(beta=beta,offset=offset):
                self.assertEqual(len(actual),len(expected))
                for a,b in zip(actual,expected):
                    self.assertEqual(a['z'],b['z']);self.assertEqual(a['holes'],b['holes'])
                    self.assertEqual(len(a['outer']),len(b['outer']))
                    for p,q in zip(a['outer'],b['outer']):
                        for x,y in zip(p,q):self.assertAlmostEqual(x,y,delta=1e-11)

    def test_raw_constructor_parts_are_real_solids_in_the_native_protocol(self):
        from solid_geometry import signature
        values=validate('face',dict(variant='double_helical'))
        result=call_geometry('construction_face',dict(values=values))
        wire=result['parts'][1]
        direct=call('solid_signature',dict(part=wire))
        adapted=signature(part_from_kernel(wire['name'],wire))
        self.assertEqual(direct,adapted)
        # A flat record must never be silently treated as the wheel's circle
        # extruded through its width; malformed/ambiguous forms are errors.
        for points in ([[0,0,0]],[[0,0]]*3):
            with self.assertRaises(ValueError):call('solid_signature',dict(part=dict(wire,mesh_triangle_points=points)))
        with self.assertRaisesRegex(ValueError,'ambiguous'):
            call('solid_signature',dict(part=dict(wire,mesh=[[[[0,0,0],[1,0,0],[0,1,0]]]])))

    def test_cancellation_inside_each_constructor_preserves_exception_and_retries(self):
        class Stopped(Exception):pass
        for family,params in [('bevel',dict(variant='zerol',trace_radius=51)),
                              ('hypoid',dict(offset=-1.9)),
                              ('face',dict(variant='double_helical',offset=1.1))]:
            values=validate(family,params)
            checks=[]
            def check():
                checks.append(True)
                if len(checks)>75:raise Stopped('constructor deadline')
            with self.subTest(family=family),self.assertRaisesRegex(Stopped,'constructor deadline'):
                call_geometry(OPS[family],dict(values=values),check=check)
            self.assertGreater(len(checks),75)
            result=call_geometry(OPS[family],dict(values=values))
            self.assertEqual(len(result['parts']),2)
            self.assertEqual(result,call_geometry(OPS[family],dict(values=values)))

    def test_native_domain_checks_refuse_invalid_inputs_and_unresolved_enclosures(self):
        for family in OPS:
            values=validate(family,{})
            for change in (dict(module=-1),dict(width=0),dict(pinion=20.5),dict(wheel=100000),dict(bore=-1)):
                with self.subTest(family=family,change=change),self.assertRaises(ValueError):
                    call_geometry(OPS[family],dict(values=dict(values,**change)))
        from hypoid_geometry import Interval,Jet
        for operation in (lambda:Interval(-1,1).sqrt(),lambda:Interval(1)/Interval(-1,1),
                          lambda:Interval(1,2).acos(),lambda:Jet(Interval(-1,1)).sqrt()):
            with self.assertRaises(ValueError):operation()
        with self.assertRaisesRegex(RuntimeError,'triangle count'):
            part_from_kernel('bad',dict(outer=[(0,0),(1,0),(0,1)],holes=[],mesh_triangle_points=[[0,0,0]]))
        values=validate('hypoid',{})
        with self.assertRaisesRegex(ValueError,'variant'):
            call_geometry(OPS['hypoid'],dict(values=dict(values,variant='translated')))
        values=validate('face',dict(variant='double_helical'))
        with self.assertRaisesRegex(ValueError,'style'):
            call_geometry(OPS['face'],dict(values=dict(values,double_style='unknown')))
        values=validate('face',{})
        with self.assertRaisesRegex(ValueError,'budget'):
            call('face_generator',dict(action='mesh',values=values,hs=[22.7,26.5],grids=[[76+i/16 for i in range(129)]],segments=64))

    def test_native_and_wasm_compare_all_new_family_coordinates_and_metadata(self):
        node=os.environ.get('RATIOLAB_NODE') or shutil.which('node')
        if not node:self.skipTest('Node.js required for actual WebAssembly execution')
        with TemporaryDirectory() as temporary:
            folder=Path(temporary);manifest=[]
            cases=CASES+[('face',dict(module=2,_decimal_inputs={'module':'2.00000000000000000001'}))]
            for i,(family,params) in enumerate(cases):
                values=validate(family,params);parameters=dict(values=values)
                path=folder/f'{i}.bin';path.write_bytes(_buffer_result(OPS[family],parameters))
                manifest.append(dict(key=f'{family}-{i}',native=str(path),request=dict(protocol=1,operation=OPS[family],parameters=transport(parameters))))
            path=folder/'requests.json';path.write_text(json.dumps(manifest))
            completed=subprocess.run([node,str(ROOT/'tests/rust_new_families_wasm.mjs'),str(ROOT),str(path)],
                                     text=True,capture_output=True,check=True,timeout=120)
        result=json.loads(completed.stdout)
        self.assertEqual(result['models'],len(cases));self.assertGreater(result['coordinates'],3000000)
        self.assertLess(result['maxDelta'],1e-9)
        print('COMPLETE_NEW_FAMILIES_WASM',json.dumps(result),flush=True)


if __name__=='__main__':unittest.main()
