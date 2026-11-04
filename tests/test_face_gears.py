# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Independent involute, world-frame normal/roll, sampled solids and integration."""
from math import pi,sin,cos,tan,atan,sqrt,hypot
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sys
import unittest
from geometry import generate,validate,get_specs
from face_geometry import Generator,REFINEMENT
from motion import build_plan,update_operating_rates,transform,rotation
from collision_geometry import Surface,relation,cross,dot
from solid_geometry import signature
from stl_export import triangles


def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def norm(p):return sqrt(dot(p,p))
def unit(p):return tuple(x/norm(p) for x in p)
def rx(p,a):return p[0],p[1]*cos(a)-p[2]*sin(a),p[1]*sin(a)+p[2]*cos(a)
def rz(p,a):return p[0]*cos(a)-p[1]*sin(a),p[0]*sin(a)+p[1]*cos(a),p[2]


class FaceGearTests(unittest.TestCase):
    def test_exact_pitch_benchmark_and_orthogonal_intersecting_axes(self):
        g=Generator(validate('face',dict(backlash=0)))
        for side in (-1,1):
            R,theta,z,r,phase,y=g.contact(72,24,side,0)
            for a,b in zip((R,theta,z,r,phase,y),(72,side*pi/144,24,24,-side*pi/48,0)):
                self.assertAlmostEqual(a,b,places=12)
            self.assertLess(norm(sub(rz(g.point(72,24,side,0),g.g*phase),(72,0,24))),1e-11)
        d=generate('face');plan=build_plan(d)
        self.assertEqual(d.parts[0].frame[0],(0,0,48))
        self.assertEqual(d.parts[0].frame[-1],(1,0,0))
        self.assertEqual(d.analysis['signed_ratio'],3)
        self.assertEqual(d.parts[1].port['rpm'],500)
        self.assertTrue(plan.supported)

    def test_independent_involute_normals_positions_and_literal_velocity(self):
        cases=[(v,b,e) for v,b in (('spur',0),('helical',15),('helical',-15),('double_helical',15),('double_helical',-15)) for e in (-5,0,5)]
        for variant,beta,offset in cases:
            g=Generator(validate('face',dict(variant=variant,double_style='separated',helix=beta,backlash=0,offset=offset)))
            for lo,hi,k in g.bands:
                for side in (-1,1):
                    # Build the involute independently of face.contact/F.
                    def master(r,x):
                        t=sqrt((r/g.rb)**2-1)
                        half=pi/(2*g.v['pinion'])+tan(g.alpha)-g.alpha-t+atan(t)
                        angle=-pi/2+side*half+g.twist(x)
                        return x,r*cos(angle),r*sin(angle)
                    for fraction in (.1,.35,.65):
                        x=(lo+hi)/2;h=g.low+(g.high-g.low)*fraction
                        R,angle,z,r,phase,y=g.contact(x,h,side,k)
                        if r>g.rp+g.m:continue
                        q=master(r,x)
                        n=unit(cross(sub(master(r+1e-5,x),master(r-1e-5,x)),sub(master(r,x+1e-5),master(r,x-1e-5))))
                        def residual(roll,wrong=False):
                            p=rx(q,roll);P=(p[0],p[1]+offset,p[2]+g.height)
                            v=sub(cross((1,0,0),p),cross((0,0,-g.g if wrong else g.g),P))
                            return dot(rx(n,roll),v)
                        # Separate roll solve using the literal full-world condition.
                        a,b=phase-.02,phase+.02
                        self.assertLess(residual(a)*residual(b),0)
                        for _ in range(42):
                            mid=(a+b)/2
                            if residual(a)*residual(mid)<=0:b=mid
                            else:a=mid
                        self.assertAlmostEqual((a+b)/2,phase,delta=2e-8)
                        p=rx(q,phase);world=(p[0],p[1]+offset,p[2]+g.height)
                        self.assertLess(norm(sub(rz(g.point(x,h,side,k),g.g*phase),world)),2e-8)
                        dx=sub(g.point(x+1e-5,h,side,k),g.point(x-1e-5,h,side,k))
                        dh=sub(g.point(x,h+1e-5,side,k),g.point(x,h-1e-5,side,k))
                        face_n=rz(unit(cross(dx,dh)),g.g*phase)
                        self.assertAlmostEqual(abs(dot(face_n,rx(n,phase))),1,delta=2e-8)
                        self.assertLess(abs(residual(phase)),1e-7)
                        self.assertGreater(abs(residual(phase,True)),.1)

    def test_interval_implicit_derivatives_and_finite_refinement_oracles(self):
        g=Generator(validate('face',dict(variant='helical',offset=-5)))
        self.assertGreater(g.engagement['phase_span_lower_bound_teeth'],1)
        for lo,hi,k in g.bands:
            for side in (-1,1):
                x=(lo+hi)/2;h=(g.low+g.high)/2
                row=g._cell(x-.001,x+.001,h-.001,h+.001,side,k)
                for direction,index in (('x',5),('h',4)):
                    dx=1e-5 if direction=='x' else 0;dh=1e-5 if direction=='h' else 0
                    derivative=(g.contact(x+dx,h+dh,side,k)[1]-g.contact(x-dx,h-dh,side,k)[1])/2e-5
                    self.assertLess(row[index].lo,derivative);self.assertGreater(row[index].hi,derivative)
        hs,grids,segments=g.grids()
        for xs,band in zip(grids,g.bands):
            for x in (xs[0],xs[len(xs)//2],xs[-1]):
                for a,b in zip(hs,hs[1:]):
                    for side in (-1,1):
                        p=g.point(x,a,side,band[2]);q=g.point(x,b,side,band[2])
                        for f in (.19,.61,.91):
                            actual=g.point(x,a+(b-a)*f,side,band[2])
                            self.assertLess(norm(tuple(actual[i]-p[i]-(q[i]-p[i])*f for i in range(3))),REFINEMENT*1.03)

    def test_actual_shared_solids_multiple_poses_and_wrong_phase_controls(self):
        cases=[('spur',0,24,72),('helical',15,24,72),('helical',-15,24,72),
               ('double_helical',15,24,72),('double_helical',-15,24,72),('spur',0,25,75)]
        for variant,beta,z,w in cases:
            d=generate('face',dict(variant=variant,double_style='separated',helix=beta,pinion=z,wheel=w));plan=build_plan(d)
            for p in d.parts:self.assertGreater(signature(p)['volume_mm3'],0)
            self.assertTrue(all(len(face)==1 and len(face[0])==3 for face in d.parts[1].mesh))
            meshes=[list(triangles(p)) for p in d.parts]
            for fraction in (0,.31,.73):
                phase=2*pi/z*fraction
                surfaces=[Surface([tuple(transform(plan.matrix(i,phase),v) for v in t) for t in mesh]) for i,mesh in enumerate(meshes)]
                self.assertEqual(relation(*surfaces,1e-6)['kind'],'Separated',(variant,beta,z,fraction))
            wrong=Surface([tuple(transform(rotation(pi/w),v) for v in t) for t in meshes[1]])
            self.assertEqual(relation(Surface(meshes[0]),wrong,1e-6)['kind'],'Intersection')

    def test_zero_helix_limit_bores_and_relief_bands(self):
        d=generate('face');zero=generate('face',dict(variant='helical',helix=0))
        self.assertEqual(d.parts,zero.parts)
        double=generate('face',dict(variant='double_helical',double_style='separated'))
        bands=double.analysis['face_gear']['band_axial_intervals_mm']
        self.assertEqual(len(bands),2);self.assertGreater(bands[1][0]-bands[0][1],4)
        for station in double.parts[0].stations:self.assertEqual(station['holes'],double.parts[0].holes)
        solid=generate('face',dict(bore=0,output_bore=0))
        for p in solid.parts:self.assertGreater(signature(p)['volume_mm3'],0)

    def test_invalid_geometry_and_variant_specific_specs(self):
        for variant in ('spur','helical','double_helical'):
            keys={s[0] for s in get_specs('face',variant,'separated')}
            self.assertEqual('helix' in keys,variant!='spur');self.assertEqual('gap' in keys,variant=='double_helical')
        for values in (dict(pinion=80,wheel=72),dict(bore=100),dict(radial_setting=40),dict(face_addendum=1),
                       dict(variant='double_helical',gap=1),dict(variant='double_helical',gap=8),
                       dict(variant='joined'),dict(bearing_mode='gear'),dict(hardware_mode='standard')):
            with self.subTest(values=values),self.assertRaises(ValueError):generate('face',values)

    def test_reverse_zero_signed_rpm_exact_projects_and_worker(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'webapp'));import engine_bridge as web
        for scheme in ('forward','reverse'):
            d=generate('face',dict(variant='helical',helix=-15.1234567890123,io_scheme=scheme))
            self.assertEqual(d.parts,generate('face',json.loads(json.dumps(d.values))).parts)
            plan=build_plan(d)
            for rpm in (-31.1234567890123,0,125):
                other=update_operating_rates(d,dict(d.values,input_rpm=rpm));updated=build_plan(other,plan,.7)
                self.assertAlmostEqual(other.parts[1].port['rpm']/other.parts[0].port['rpm'] if rpm else 1/3,1/3)
                for i in (0,1):
                    self.assertIs(d.parts[i].mesh,other.parts[i].mesh);self.assertIs(d.parts[i].stations,other.parts[i].stations)
                    for a,b in zip(plan.matrix(i,.7),updated.matrix(i,.7)):self.assertAlmostEqual(a,b,places=12)
                d,plan=other,updated
            result=web.Engine().call('generate',dict(family='face',parameters=d.values))
            self.assertEqual(result['analysis'],d.analysis);self.assertTrue(result['motion']['supported'])

    def test_canonical_exports_and_finite_search(self):
        import cad_export,stl_export,profile_export
        from combination_search import search,Settings
        for variant in ('spur','helical','double_helical'):
            d=generate('face',dict(variant=variant))
            with TemporaryDirectory() as td:
                _,parts=cad_export.export(d,Path(td)/'step');self.assertEqual(len(parts),2)
                stl_export.export(d,Path(td)/'stl');profile_export.export(d,Path(td)/'profiles')
                self.assertEqual(len(list(Path(td).rglob('*.stl'))),3)
                records=json.loads(next(Path(td).rglob('profiles.json')).read_text())
                # The freeform face wheel is not misrepresented as an extrudible 2D gear.
                self.assertIn('mesh without parametric planar sections',json.dumps(records))
        d=generate('face');result=search('face',d.values,{'wheel':(72,75)},Settings(target=3,tolerance_percent=0,max_seconds=30))
        self.assertTrue(result.complete,result.text());self.assertEqual(len(result.proposals),1)
        self.assertEqual(result.proposals[0].values['wheel'],72)


if __name__=='__main__':unittest.main()
