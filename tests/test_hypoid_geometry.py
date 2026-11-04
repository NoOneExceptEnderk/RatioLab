# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Independent world-frame envelope, normal, mesh and integration checks."""
import json
from math import sin, cos, pi, hypot
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest

from geometry import generate, validate, get_specs
from hypoid_geometry import Generator, Interval, REFINEMENT
from collision_geometry import cross, dot, Surface, relation
from motion import build_plan, transform, rotation, update_operating_rates
from stl_export import triangles
from solid_geometry import signature
from test_bevel_geometry import rz, rx, frame_a, normal, norm


def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def unit(p):return tuple(x/norm(p) for x in p)
def world(g,theta,x,side):
    p=g.point(theta,x,side);phase=g.at_x(theta,x,side)[3]
    p=frame_a(rz(p,g.ratio*phase))
    return (p[0],p[1]+g.offset,p[2]),phase


class HypoidTests(unittest.TestCase):
    def test_independent_full_transform_benchmark_and_offset_velocity_term(self):
        g=Generator(validate('hypoid',dict(backlash=0)))
        theta=1.096180105067607;x=36.42229123600033;side=1
        radius,azimuth,R,phase=g.at_x(theta,x,side)
        for actual,expected in zip((R,phase,radius,azimuth),
                (41.00992390887163,.07897272747143103,18.741417383703183,1.728877382724876)):
            self.assertAlmostEqual(actual,expected,places=11)
        q=g.cutter;point=q.point(theta,R,side,0);n=normal(q,theta,R,side,0)
        # Solve literal world n dot (omega_w x P - omega_p x (P-Op))
        # using a finite-difference master normal and numerical bisection.
        def residual(angle,offset=2):
            p=rz(point,angle);nn=rz(n,angle)
            v=sub(cross((0,0,1),p),cross((g.ratio,0,0),sub(p,(0,offset,0))))
            return dot(nn,v)
        lo,hi=0,.2
        self.assertLess(residual(lo)*residual(hi),0)
        for _ in range(50):
            mid=(lo+hi)/2
            if residual(lo)*residual(mid)<=0:hi=mid
            else:lo=mid
        self.assertAlmostEqual((lo+hi)/2,phase,delta=2e-9)
        self.assertGreater(abs(residual(phase,0)),.1)
        expected=rz(point,phase);actual,_=world(g,theta,x,side)
        self.assertLess(norm(sub(actual,expected)),1e-11)

    def test_generated_normals_common_position_and_sliding_both_flanks_and_signs(self):
        for counts in ((20,40),(21,41)):
            for offset in (-2,0,2):
                g=Generator(validate('hypoid',dict(pinion=counts[0],wheel=counts[1],offset=offset,backlash=0)))
                for side in (-1,1):
                    for fraction in (.13,.47,.83):
                        theta=g.top+(g.cutter.tip-g.top)*fraction;x=(g.toe+g.heel)/2
                        p,phase=world(g,theta,x,side);R=g.at_x(theta,x,side)[2]
                        self.assertLess(norm(sub(p,rz(g.cutter.point(theta,R,side,0),phase))),2e-11)
                        dt=sub(g.point(theta+1e-6,x,side),g.point(theta-1e-6,x,side))
                        dx=sub(g.point(theta,x+1e-4,side),g.point(theta,x-1e-4,side))
                        nn=frame_a(rz(unit(cross(dt,dx)),g.ratio*phase))
                        n=rz(normal(g.cutter,theta,R,side,0),phase)
                        self.assertAlmostEqual(abs(dot(nn,n)),1,delta=2e-9)
                        v=sub(cross((0,0,1),p),cross((g.ratio,0,0),sub(p,(0,offset,0))))
                        self.assertLess(abs(dot(n,v)),1e-7)
                        if offset:self.assertGreater(norm(v),.01)

    def test_interval_derivatives_connected_track_and_offset_mirror(self):
        positive=Generator(validate('hypoid',{}));negative=Generator(validate('hypoid',dict(offset=-2)))
        self.assertLess(positive.regularity['radial_derivative_upper_mm_per_rad'],0)
        self.assertGreater(positive.engagement['phase_span_lower_bound_teeth'],1)
        for side in (-1,1):
            for fraction in (.17,.51,.87):
                theta=positive.top+(positive.cutter.tip-positive.top)*fraction;x=(positive.toe+positive.heel)/2
                r,_=positive._jet(theta-1e-5,theta+1e-5,side,Interval(x-.01,x+.01))
                derivative=(positive.at_x(theta+1e-7,x,side)[0]-positive.at_x(theta-1e-7,x,side)[0])/2e-7
                self.assertLess(r.d.lo,derivative);self.assertGreater(r.d.hi,derivative)
                a=positive.point(theta,x,side);b=negative.point(theta,x,-side)
                for actual,expected in zip(b,(-a[0],a[1],a[2])):self.assertAlmostEqual(actual,expected,places=10)
        zero=Generator(validate('hypoid',dict(offset=0)))
        self.assertNotAlmostEqual(positive.at_x(positive.cutter.delta,positive.heel,1)[0],zero.at_x(zero.cutter.delta,zero.heel,1)[0])

    def test_actual_shared_meshes_at_several_rolls_and_wrong_phase_control(self):
        for offset,z,w in ((-2,20,40),(0,20,40),(2,20,40),(2,21,41)):
            d=generate('hypoid',dict(offset=offset,pinion=z,wheel=w));plan=build_plan(d)
            self.assertTrue(plan.supported);meshes=[list(triangles(p)) for p in d.parts]
            for fraction in (0,.27,.63):
                surfaces=[Surface([tuple(transform(plan.matrix(i,2*pi/z*fraction),v) for v in t) for t in mesh]) for i,mesh in enumerate(meshes)]
                self.assertEqual(relation(*surfaces,1e-6)['kind'],'Separated',(offset,z,w,fraction))
            shifted=Surface([tuple(transform(rotation(pi/w),v) for v in t) for t in meshes[1]])
            self.assertEqual(relation(Surface(meshes[0]),shifted,1e-6)['kind'],'Intersection')
            for p in d.parts:
                self.assertGreater(signature(p)['volume_mm3'],0)
                self.assertTrue(all(station['holes']==p.holes for station in p.stations))

    def test_finite_refinement_independent_probes_and_ordered_simple_tooth(self):
        g=Generator(validate('hypoid',{}));angles,xs=g.grids()
        for x in (xs[0],(xs[0]+xs[-1])/2,xs[-1]):
            for lo,hi in zip(angles,angles[1:]):
                for side in (-1,1):
                    a=g.point(lo,x,side);b=g.point(hi,x,side)
                    for f in (.19,.41,.69,.91):
                        p=g.point(lo+(hi-lo)*f,x,side)
                        self.assertLess(hypot(*(p[k]-a[k]-(b[k]-a[k])*f for k in (0,1))),REFINEMENT*1.01)
            # Literal nonadjacent segment test over one tooth and its neighbor.
            contour=g.outline(x,angles);n=len(contour)//g.v['pinion'];points=contour[:2*n+1]
            def orient(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
            for i,(a,b) in enumerate(zip(points,points[1:])):
                for c,d in zip(points[i+2:],points[i+3:]):
                    self.assertFalse(orient(a,b,c)*orient(a,b,d)<-1e-16 and orient(c,d,a)*orient(c,d,b)<-1e-16)

    def test_limits_reject_instead_of_clamping(self):
        for fields in (dict(offset=4),dict(width=25),dict(bore=100),dict(output_bore=100),
                       dict(spiral_angle=0),dict(pressure=30),dict(variant='translated'),dict(offset=float('nan')),
                       dict(bearing_mode='gear'),dict(hardware_mode='standard')):
            with self.subTest(fields=fields),self.assertRaises(ValueError):generate('hypoid',fields)
        fields={s[0] for s in get_specs('hypoid')}
        self.assertIn('offset',fields);self.assertNotIn('spiral_hand',fields)

    def test_finite_search_keeps_offset_and_checks_generated_candidates(self):
        from combination_search import search,Settings
        d=generate('hypoid',dict(offset=-1.1234567890123))
        result=search('hypoid',d.values,{'wheel':(40,44)},Settings(target=2,tolerance_percent=0,max_seconds=30))
        self.assertTrue(result.complete,result.text());self.assertEqual(len(result.proposals),1)
        proposal=result.proposals[0]
        self.assertEqual(proposal.values['wheel'],40)
        self.assertEqual(proposal.values['offset'],d.values['offset'])
        self.assertEqual(proposal.ratio,generate('hypoid',proposal.values).analysis['signed_ratio'])

    def test_projects_worker_reverse_rates_and_standalone_exports(self):
        import cad_export,stl_export,profile_export
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'webapp'))
        import engine_bridge as web
        d=generate('hypoid',dict(offset=-1.1234567890123,io_scheme='reverse'))
        restored=generate('hypoid',json.loads(json.dumps(d.values)))
        self.assertEqual(d.parts,restored.parts);self.assertEqual(d.analysis['signed_ratio'],-.5)
        plan=build_plan(d)
        for rpm in (-37.1234567890123,0,123):
            changed=update_operating_rates(d,dict(d.values,input_rpm=rpm));updated=build_plan(changed,plan,.7)
            self.assertEqual(changed.parts[0].port['rpm'],-2*rpm)
            self.assertIs(changed.parts[0].stations,d.parts[0].stations)
            for i in (0,1):
                for a,b in zip(plan.matrix(i,.7),updated.matrix(i,.7)):self.assertAlmostEqual(a,b,places=12)
            d,plan=changed,updated
        engine=web.Engine();result=engine.call('generate',dict(family='hypoid',parameters=d.values))
        self.assertEqual(result['analysis'],d.analysis);self.assertTrue(result['motion']['supported'])
        self.assertIn('offset',{f['key'] for f in web.schema('hypoid',d.values)['fields']})
        with TemporaryDirectory() as td:
            _,info=cad_export.export(d,Path(td)/'step');self.assertEqual(len(info),2)
            stl_export.export(d,Path(td)/'stl');profile_export.export(d,Path(td)/'profiles')
            # Two individual blanks plus the normal combined assembly STL.
            self.assertEqual(len(list(Path(td).rglob('*.stl'))),3)
            self.assertTrue(any(Path(td).rglob('*.dxf')))


if __name__=='__main__':unittest.main()
