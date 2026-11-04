# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Offset face-gear frames, asymmetric flanks and actual moving shared solids."""
from math import pi,sqrt,atan2,hypot
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sys
import unittest
from geometry import generate,validate
from face_geometry import Generator
from motion import build_plan,transform,rotation,update_operating_rates
from collision_geometry import Surface,relation
from solid_geometry import signature
from stl_export import triangles


class FaceOffsetTests(unittest.TestCase):
    def test_exact_offset_pitch_benchmark_shortest_distance_and_zero_limit(self):
        for offset in (-10,10):
            g=Generator(validate('face',dict(offset=offset,backlash=0,width=3)))
            for side in (-1,1):
                r,a,z,p,phase,y=g.contact(72,24,side,0)
                for actual,expected in zip((r,a,z,p,phase,y),(sqrt(5284),atan2(offset,72)+side*pi/144,24,24,-side*pi/48,0)):
                    self.assertAlmostEqual(actual,expected,places=12)
            d=generate('face',dict(offset=offset,width=3));q=d.analysis['face_gear']
            self.assertEqual(q['shaft_angle_deg'],90)
            self.assertIsNone(q['axis_intersection_mm'])
            self.assertEqual(q['shortest_axis_distance_mm'],10)
            self.assertEqual(d.parts[0].frame[0],(0,offset,48))
            self.assertEqual(d.analysis['signed_ratio'],3)
        # Explicit zero and old projects without this field share exact solids.
        for variant in ('spur','helical','double_helical'):
            a=generate('face',dict(variant=variant));b=generate('face',dict(variant=variant,offset=0))
            self.assertEqual(a.parts,b.parts)
            legacy=dict(a.values);del legacy['offset']
            self.assertEqual(a.parts,generate('face',legacy).parts)
            self.assertEqual(a.analysis['face_gear']['axis_intersection_mm'],[0,0,2*Generator(a.values).rp])

    def test_signed_offsets_actual_solids_poses_and_wrong_phase_controls(self):
        for variant in ('spur','helical','double_helical'):
            for offset in (-5,5):
                d=generate('face',dict(variant=variant,offset=offset));plan=build_plan(d)
                meshes=[list(triangles(p)) for p in d.parts]
                for p in d.parts:self.assertGreater(signature(p)['volume_mm3'],0)
                for fraction in (0,.31,.73):
                    phase=2*pi/24*fraction
                    ss=[Surface([tuple(transform(plan.matrix(i,phase),v) for v in t) for t in mesh]) for i,mesh in enumerate(meshes)]
                    self.assertEqual(relation(*ss,1e-6)['kind'],'Separated',(variant,offset,fraction))
                wrong=Surface([tuple(transform(rotation(pi/72),v) for v in t) for t in meshes[1]])
                self.assertEqual(relation(Surface(meshes[0]),wrong,1e-6)['kind'],'Intersection')
                # Moving only the pinion cannot reuse the zero-offset face wheel.
                old=generate('face',dict(variant=variant))
                changed=max(abs(a-b) for f,h in zip(d.parts[1].mesh,old.parts[1].mesh) for p,q in zip(f[0],h[0]) for a,b in zip(p,q))
                self.assertGreater(changed,.1)

    def test_equal_radius_width_bound_independent_inverse_and_invalid_limits(self):
        for offset in (-5,5):
            g=Generator(validate('face',dict(variant='helical',offset=offset)))
            cert=g.certificates[0]
            self.assertGreater(cert['radial_derivative_lower'],0)
            for h in (g.low,(g.low+g.high)/2,g.high):
                for f in (.2,.5,.8):
                    x=g.x0+(g.x1-g.x0)*f;R=g.contact(x,h,1,g.k)[0]
                    a,b=g.x0,g.x1
                    for _ in range(48):
                        mid=(a+b)/2
                        if g.contact(mid,h,-1,g.k)[0]<R:a=mid
                        else:b=mid
                    other=(a+b)/2
                    self.assertAlmostEqual(g.contact(other,h,-1,g.k)[0],R,places=9)
                    gap=g.contact(x,h,1,g.k)[1]-g.contact(other,h,-1,g.k)[1]
                    self.assertGreater(gap,0);self.assertLess(gap,2*pi/72)
                    if h==g.low or h==g.high:continue
                    for side in (-1,1):
                        target=g.contact(x,h,side,g.k)[0];angles=[]
                        for hh in (h-1e-5,h+1e-5):
                            a,b=g.x0,g.x1
                            for _ in range(48):
                                mid=(a+b)/2
                                if g.contact(mid,hh,side,g.k)[0]<target:a=mid
                                else:b=mid
                            angles.append(g.contact((a+b)/2,hh,side,g.k)[1])
                        derivative=(angles[1]-angles[0])/2e-5
                        row=g._cell(x-.001,x+.001,h-.001,h+.001,side,g.k)
                        self.assertLess(row[6].lo,derivative);self.assertGreater(row[6].hi,derivative)
                        self.assertLess(side*derivative,0)
        for values in (dict(offset=36),dict(offset=-36),dict(variant='helical',offset=10),dict(variant='double_helical',offset=20)):
            with self.subTest(values=values),self.assertRaises(ValueError):generate('face',values)

    def test_precise_offset_projects_reverse_zero_rpm_worker_and_exports(self):
        import cad_export,stl_export
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'webapp'));import engine_bridge
        for scheme in ('forward','reverse'):
            d=generate('face',dict(variant='helical',offset=-5.1234567890123,io_scheme=scheme))
            plan=build_plan(d)
            self.assertEqual(d.parts,generate('face',json.loads(json.dumps(d.values))).parts)
            for rpm in (-31.1234567890123,0,125):
                other=update_operating_rates(d,dict(d.values,input_rpm=rpm));updated=build_plan(other,plan,.9)
                for i in (0,1):
                    self.assertIs(other.parts[i].mesh,d.parts[i].mesh)
                    for a,b in zip(plan.matrix(i,.9),updated.matrix(i,.9)):self.assertAlmostEqual(a,b,places=12)
                self.assertAlmostEqual(other.parts[1].port['rpm'],other.parts[0].port['rpm']/3)
            result=engine_bridge.Engine().call('generate',dict(family='face',parameters=d.values))
            self.assertEqual(result['analysis'],d.analysis)
            self.assertEqual(result['analysis']['face_gear']['shaft_offset_mm'],-5.1234567890123)
        for variant in ('spur','helical','double_helical'):
            d=generate('face',dict(variant=variant,offset=5))
            with TemporaryDirectory() as td:
                _,parts=cad_export.export(d,Path(td)/'step');self.assertEqual(len(parts),2)
                stl_export.export(d,Path(td)/'stl')
                self.assertEqual(len(list(Path(td).rglob('*.stl'))),3)


if __name__=='__main__':unittest.main()
