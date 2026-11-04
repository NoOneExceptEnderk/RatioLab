# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Rack equations, independent common normals and actual finite moving solids."""
from math import pi,sin,cos,tan,atan,sqrt,radians,hypot
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sys
import unittest
from geometry import generate,validate,get_specs
from rack_geometry import dimensions
from motion import build_plan,update_operating_rates,transform,translation
from solid_geometry import signature
from collision_geometry import Surface,relation,cross,dot
from stl_export import triangles


def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def norm(a):return sqrt(dot(a,a))
def unit(a):return tuple(x/norm(a) for x in a)
def rz(a,t):return (a[0]*cos(t)-a[1]*sin(t),a[0]*sin(t)+a[1]*cos(t),a[2])


class RackGeometryTests(unittest.TestCase):
    def test_khk_table_413_benchmark_and_spur_equation_42(self):
        beta=10+57/60+49/3600
        d=generate('rack',dict(variant='helical',module=2.5,pinion=20,rack_teeth=40,helix=beta,base=24.375))
        q=d.analysis['rack']
        self.assertAlmostEqual(2*q['pitch_radius_mm'],50.92956,delta=.00001)
        self.assertAlmostEqual(q['transverse_pressure_deg'],20.34160,delta=.00001)
        self.assertAlmostEqual(q['travel_per_revolution_mm'],160,delta=.0001)
        self.assertAlmostEqual(q['pitch_radius_mm']+27.5,52.965,delta=.0005)
        d=generate('rack');q=d.analysis['rack']
        self.assertAlmostEqual(q['travel_per_revolution_mm'],48*pi,places=12)
        self.assertAlmostEqual(d.analysis['linear_output']['velocity_mm_s'],48*pi*12/60,places=12)
        self.assertNotIn('signed_ratio',d.analysis);self.assertNotIn('rpm',d.parts[1].port)

    def test_literal_world_common_normals_and_rack_flanks(self):
        # Independent analytic involute, numerical surface normals, numerical
        # world-velocity root solve; no runtime contact solver or rack outline.
        for variant,beta in (('spur',0),('helical',20),('helical',-20),('double',25),('double',-25)):
            d=generate('rack',dict(variant=variant,helix=beta,backlash=0,rack_teeth=25 if variant=='spur' else 24))
            v=d.values;q=d.analysis['rack'];r=q['pitch_radius_mm'];rb=r*cos(radians(q['transverse_pressure_deg']))
            at=radians(q['transverse_pressure_deg']);pitch=q['transverse_pitch_mm'];half=pi/(2*v['pinion'])
            phase=-pi/2+(pi/v['pinion'] if v['rack_teeth']%2 else 0)
            def inv(R):t=sqrt((R/rb)**2-1);return t-atan(t)
            def shear(z):return tan(radians(beta))*(min(z,v['width']-z) if variant=='double' else z)
            for side in (-1,1):
                def point(R,z):
                    a=phase+shear(z)/r+side*(half+inv(r)-inv(R))
                    return R*cos(a),R*sin(a),z
                for z in (.2*v['width'],.8*v['width']):
                    for R in (r-.3*v['module'],r,r+.7*v['module']):
                        p=point(R,z)
                        nn=unit(cross(sub(point(R+1e-5,z),point(R-1e-5,z)),sub(point(R,z+1e-5),point(R,z-1e-5))))
                        def residual(t):
                            a=rz(p,t);n=rz(nn,t)
                            return dot(n,sub(cross((0,0,1),a),(r,0,0)))
                        roots=[];lo=-pi;fl=residual(lo)
                        for j in range(1,65):
                            hi=-pi+2*pi*j/64;fh=residual(hi)
                            if fl*fh<0:
                                a,b=lo,hi
                                for _ in range(45):
                                    mid=(a+b)/2
                                    if residual(a)*residual(mid)<=0:b=mid
                                    else:a=mid
                                t=(a+b)/2;body=rz(p,t);P=(body[0],body[1]+r,z)
                                if -1.25*v['module']<P[1]<v['module']:roots.append((t,P))
                            lo=hi;fl=fh
                        self.assertEqual(len(roots),1)
                        t,P=roots[0];x=P[0]-r*t-shear(z)+(v['rack_teeth']-1)/2*pitch
                        x=(x+pitch/2)%pitch-pitch/2
                        expected=pitch/4-P[1]*tan(at)
                        self.assertAlmostEqual(abs(x),expected,delta=2e-7)
                        slope=tan(radians(beta))*(-1 if variant=='double' and z>v['width']/2 else 1)
                        rack_normal=unit((1,(1 if x>0 else -1)*tan(at),-slope))
                        self.assertAlmostEqual(abs(dot(rz(nn,t),rack_normal)),1,delta=2e-9)

    def test_closed_shared_solids_moving_meshes_and_wrong_direction_control(self):
        cases=[('spur',0,None),('helical',20,None),('helical',-20,None),('double',20,'joined'),('double',20,'separated'),('double',-20,'separated'),('spur',0,'odd')]
        for variant,beta,style in cases:
            d=generate('rack',dict(variant=variant,helix=beta,**(dict(pinion=25,rack_teeth=25) if style=='odd' else {'double_style':style} if style else {})))
            plan=build_plan(d);meshes=[list(triangles(p)) for p in d.parts]
            for p in d.parts:self.assertGreater(signature(p)['volume_mm3'],0)
            for fraction in (0,.31,.73):
                phase=2*pi/d.values['pinion']*fraction
                surfaces=[Surface([tuple(transform(plan.matrix(i,phase),v) for v in t) for t in mesh]) for i,mesh in enumerate(meshes)]
                self.assertEqual(relation(*surfaces,1e-6)['kind'],'Separated',(variant,beta,style,fraction))
            phase=pi/(2*d.values['pinion'])
            pin=Surface([tuple(transform(plan.matrix(0,phase),v) for v in t) for t in meshes[0]])
            wrong=Surface([tuple(transform(translation(-d.analysis['rack']['pitch_radius_mm']*phase),v) for v in t) for t in meshes[1]])
            self.assertEqual(relation(pin,wrong,1e-6)['kind'],'Intersection')

    def test_zero_helix_limit_cylindrical_bores_and_fixed_rack_ends(self):
        spur=generate('rack');zero=generate('rack',dict(variant='helical',helix=0))
        self.assertEqual(spur.parts,zero.parts)
        for variant in ('helical','double'):
            d=generate('rack',dict(variant=variant));p,rack=d.parts
            for s in p.stations:self.assertEqual(s['holes'],p.holes)
            ends={(s['outer'][0],s['outer'][1]) for s in rack.stations}
            self.assertEqual(len(ends),1)
        joined=generate('rack',dict(variant='double',helix=0,double_style='joined'))
        for a,b in zip(spur.parts,joined.parts):self.assertAlmostEqual(signature(a)['volume_mm3'],signature(b)['volume_mm3'],delta=1e-7)

    def test_finite_limits_stationary_signed_speed_and_continuous_rate_edits(self):
        from interference import period
        d=generate('rack');plan=build_plan(d);self.assertIsNone(period(plan));phase=.47
        for rpm in (0,-31.1234567890123,12):
            updated=update_operating_rates(d,dict(d.values,input_rpm=rpm));other=build_plan(updated,plan,phase)
            for i in (0,1):
                for a,b in zip(plan.matrix(i,phase),other.matrix(i,phase)):self.assertAlmostEqual(a,b,places=12)
                self.assertIs(d.parts[i].stations,updated.parts[i].stations)
            self.assertAlmostEqual(updated.analysis['linear_output']['velocity_mm_s'],2*pi*24*rpm/60,places=10)
            if rpm:
                for bound in other.phase_limits:self.assertLessEqual(abs(other.matrix(1,bound)[12]),d.analysis['rack']['travel_limits_mm'][1]+1e-10)
                with self.assertRaisesRegex(ValueError,'stroke'):other.matrix(1,other.phase_limits[1]+.1)
            else:self.assertEqual(other.matrix(1,phase),other.matrix(1,phase+3))
            d,plan=updated,other

    def test_invalid_geometry_and_active_specs(self):
        for variant in ('spur','helical','double'):
            fields={s[0] for s in get_specs('rack',variant)}
            self.assertEqual('helix' in fields,variant!='spur');self.assertEqual('gap' in fields,variant=='double')
        for values in (dict(pinion=12),dict(bore=100),dict(rack_teeth=8,variant='helical',helix=35,width=60),dict(module=.5,backlash=1),
                       dict(variant='double',gap=10),dict(rack_teeth=12.5),dict(base=0),dict(io_scheme='reverse'),dict(hardware_mode='standard')):
            with self.subTest(values=values),self.assertRaises(ValueError):generate('rack',values)

    def test_interference_samples_the_bounded_stroke_without_a_fake_period(self):
        from interference import analyze,Settings
        d=generate('rack');plan=build_plan(d)
        result=analyze(d,Settings(step_degrees=180,max_poses=10,max_seconds=30),plan=plan)
        self.assertIsNone(result.period_turns);self.assertTrue(result.coverage_complete,result.text())
        self.assertIn('nonperiodic',result.period_basis)
        self.assertAlmostEqual(result.requested_end_degrees,plan.phase_limits[1]*180/pi)
        self.assertAlmostEqual(result.sampled_end_degrees,result.requested_end_degrees)
        self.assertTrue(result.rows);self.assertTrue(all(row['kind']=='Separated' for row in result.rows))

    def test_projects_worker_and_canonical_exports(self):
        import cad_export,stl_export,profile_export
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'webapp'));import engine_bridge as web
        for variant in ('spur','helical','double'):
            d=generate('rack',dict(variant=variant,base=6.1234567890123))
            self.assertEqual(d.parts,generate('rack',json.loads(json.dumps(d.values))).parts)
            e=web.Engine();result=e.call('generate',dict(family='rack',parameters=d.values))
            self.assertEqual(result['analysis'],d.analysis);self.assertIsNotNone(result['motion']['phase_limits'])
            with TemporaryDirectory() as td:
                _,parts=cad_export.export(d,Path(td)/'step');self.assertEqual(len(parts),2)
                stl_export.export(d,Path(td)/'stl');profile_export.export(d,Path(td)/'profiles')
                self.assertEqual(len(list(Path(td).rglob('*.stl'))),3)
                self.assertTrue(any(Path(td).rglob('*.dxf')))


if __name__=='__main__':unittest.main()
