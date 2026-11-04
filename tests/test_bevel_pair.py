# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Independent cone/rolling benchmarks and moving shared surfaces."""
from math import pi, cos, sin, sqrt
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sys
import unittest

from geometry import generate, validate
from motion import build_plan, update_operating_rates, transform, rotation, part_axis
from solid_geometry import signature
from bevel_pair import dimensions
from collision_geometry import Surface, relation
from stl_export import triangles
from combination_search import estimated_ratio, search, Settings, variables
from test_bevel_geometry import contacts


class BevelPairTests(unittest.TestCase):
    def test_khk_reference_pitch_cones_and_independent_rolling(self):
        for io,ratio,speeds in [('forward',-2,[1500,-750]),('reverse',-.5,[-3000,1500])]:
            d=generate('bevel',dict(module=3,pinion=20,wheel=40,width=15,io_scheme=io))
            q=d.analysis['bevel_pair']
            self.assertAlmostEqual(q['pitch_cone_distance_mm'],sqrt(4500),places=12)
            self.assertAlmostEqual(q['pinion_pitch_angle_deg'],26.56505117707799,places=12)
            self.assertAlmostEqual(q['wheel_pitch_angle_deg'],63.43494882292201,places=12)
            self.assertEqual(q['outer_pitch_diameters_mm'],[60,120])
            self.assertEqual(d.analysis['signed_ratio'],ratio)
            self.assertEqual(estimated_ratio('bevel',d.values),ratio)
            self.assertEqual([p.port['rpm'] for p in d.parts],speeds)
            self.assertEqual(20*speeds[0]+40*speeds[1],0)
            self.assertEqual(d.analysis['output']['rpm'],speeds[1 if io=='forward' else 0])
            self.assertEqual([part_axis(p)[1] for p in d.parts],[(1,0,0),(0,0,1)])
        equal=generate('bevel',dict(pinion=24,wheel=24))
        self.assertEqual(equal.analysis['signed_ratio'],-1)
        self.assertEqual(equal.analysis['bevel_pair']['pinion_pitch_angle_deg'],45)

    def test_no_carrier_or_invented_hardware_and_physical_bores_persist_on_swap(self):
        d=generate('bevel',dict(bore=5,output_bore=9))
        reverse=generate('bevel',dict(bore=5,output_bore=9,io_scheme='reverse'))
        self.assertEqual([p.name for p in d.parts],['Bevel_pinion','Bevel_wheel'])
        self.assertEqual([signature(p) for p in d.parts],[signature(p) for p in reverse.parts])
        self.assertEqual([p.port['role'] for p in reverse.parts],['output','input'])
        for p,bore in zip(d.parts,[5,9]):
            for station in p.stations:
                self.assertTrue(all(abs(sqrt(x*x+y*y)-bore/2)<1e-12 for x,y in station['holes'][0]))
        self.assertTrue(all(not p.holes for p in generate('bevel',dict(bore=0,output_bore=0)).parts))
        for key,value in [('bearing_mode','shaft'),('hardware_mode','standard')]:
            with self.assertRaises(ValueError):generate('bevel',{key:value})

    def test_invalid_width_bore_engagement_and_tooth_inputs_refused(self):
        for values in [dict(width=25),dict(bore=100),dict(output_bore=100),dict(backlash=1,module=.5,width=2),
                       dict(pressure=30,pinion=24,wheel=24),dict(pinion=20.5),dict(variant='hypoid')]:
            with self.subTest(values=values),self.assertRaises(ValueError):validate('bevel',values)

    def test_independent_contact_normals_on_both_flanks(self):
        for z,w in [(20,40),(24,24),(21,41),(40,20)]:
            v=validate('bevel',dict(pinion=z,wheel=w,backlash=0))
            a,b,_=dimensions(v)
            results=list(contacts(a,b))
            self.assertGreater(len(results),10)
            self.assertLess(max(q[0] for q in results),2e-7)
            self.assertLess(max(abs(1-q[1]) for q in results),2e-8)
            self.assertLess(max(q[2] for q in results),2e-12)

    def test_shared_mesh_at_independent_cycle_poses_and_wrong_phase_negative_control(self):
        for z,w in [(20,40),(21,41),(24,24)]:
            d=generate('bevel',dict(pinion=z,wheel=w))
            meshes=[list(triangles(p)) for p in d.parts];plan=build_plan(d)
            self.assertTrue(plan.supported)
            self.assertEqual(plan.rates,{0:(1.0,),1:(-z/w,)})
            for fraction in (0,.31,.73):
                phase=2*pi/z*fraction
                surfaces=[Surface([tuple(transform(plan.matrix(i,phase),p) for p in t) for t in mesh]) for i,mesh in enumerate(meshes)]
                result=relation(*surfaces,1e-6)
                self.assertEqual(result['kind'],'Separated',(z,w,fraction,result))
            bad=rotation(pi/w)
            shifted=Surface([tuple(transform(bad,p) for p in t) for t in meshes[1]])
            self.assertEqual(relation(Surface(meshes[0]),shifted,1e-6)['kind'],'Intersection')

    def test_speed_changes_retain_surface_buffers_and_pose_continuity(self):
        d=generate('bevel');plan=build_plan(d)
        self.assertTrue(plan.supported)
        self.assertNotEqual(plan.matrix(0,.731),plan.matrix(0,0))
        self.assertAlmostEqual(transform(plan.matrix(0,.731),(0,1,0))[1],cos(.731),places=12)
        self.assertAlmostEqual(transform(plan.matrix(1,.731),(1,0,0))[1],sin(-.731/2),places=12)
        for rpm in (-37.1234567890123,0,1500):
            changed=update_operating_rates(d,dict(d.values,input_rpm=rpm))
            updated=build_plan(changed,plan,.731)
            self.assertTrue(all(a.outer is b.outer and a.stations is b.stations for a,b in zip(d.parts,changed.parts)))
            self.assertEqual(changed.parts[1].port['rpm'],-rpm/2)
            for index in range(2):
                for a,b in zip(plan.matrix(index,.731),updated.matrix(index,.731)):self.assertAlmostEqual(a,b,places=12)
            if rpm==0:
                self.assertEqual(updated.matrix(0,.731),updated.matrix(0,2))
            d,plan=changed,updated

    def test_finite_search_validates_real_bevel_candidates(self):
        d=generate('bevel')
        self.assertIn('wheel',{v[0] for v in variables('bevel',d.values)})
        result=search('bevel',d.values,{'wheel':[40,48]},Settings(target=2,tolerance_percent=0,max_seconds=30))
        self.assertEqual(len(result.proposals),1)
        self.assertEqual(result.proposals[0].values['wheel'],40)

    def test_canonical_exports_and_roundtrip(self):
        import cad_export,stl_export,profile_export,bom
        d=generate('bevel',dict(bore=5.1234567890123))
        with TemporaryDirectory() as td:
            cad_export.export(d,Path(td)/'cad')
            stl_export.export(d,Path(td)/'mesh')
            profile_export.export(d,Path(td)/'profiles')
            bom.export(d,Path(td)/'reports')
            for suffix in ('.step','.stl','.svg','.dxf','.bom.json','.calculations.json'):
                self.assertTrue(any(p.stat().st_size>100 for p in Path(td).rglob('*'+suffix)),suffix)
        copied=generate('bevel',json.loads(json.dumps(d.values)))
        self.assertEqual(copied.values,d.values)
        self.assertEqual([signature(p) for p in copied.parts],[signature(p) for p in d.parts])

    def test_browser_schema_and_worker_match_native_without_gui(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'webapp'))
        import engine_bridge as web
        s=web.schema('bevel')
        self.assertFalse(s['bearing_supported']);self.assertFalse(s['hardware_supported'])
        self.assertTrue(all(f['help'] for f in s['fields']))
        self.assertEqual(next(f for f in s['fields'] if f['key']=='input_rpm')['minimum'],-100000)
        engine=web.Engine();result=engine.call('generate',dict(family='bevel',parameters=dict(io_scheme='reverse')))
        self.assertEqual(result['analysis']['signed_ratio'],-.5)
        self.assertEqual(len(result['parts']),2)
        self.assertGreater(result['triangle_count'],0)
        with self.assertRaises(ValueError):engine.call('generate',dict(family='bevel',parameters=dict(width=25)))
        self.assertIsNone(engine.design)


if __name__=='__main__':unittest.main()
