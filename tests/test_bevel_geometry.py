# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Independent spherical equations and actual moving shared-surface checks."""
from dataclasses import replace
from math import acos, atan2, cos, sin, sqrt, pi, hypot, log, tan, radians
import unittest

from bevel_geometry import parameters, spherical_involute, section, engagement, PROFILE_TOLERANCE
from geometry import generate
from solid_geometry import faces, signature
from stl_export import triangles
from collision_geometry import Surface, relation, cross, dot
from motion import build_plan, transform, rotation


def rx(p, a):
    return p[0], cos(a)*p[1]-sin(a)*p[2], sin(a)*p[1]+cos(a)*p[2]


def rz(p, a):
    return cos(a)*p[0]-sin(a)*p[1], sin(a)*p[0]+cos(a)*p[1], p[2]


def frame_a(p):
    return p[2], p[0], p[1]


def norm(v):
    return sqrt(dot(v, v))


def normal(q, theta, distance, side, phase):
    dr = tuple((x-y)/.0002 for x,y in zip(q.point(theta,distance+.0001,side,phase),q.point(theta,distance-.0001,side,phase)))
    dt = tuple((x-y)/.0000004 for x,y in zip(q.point(theta+.0000002,distance,side,phase),q.point(theta-.0000002,distance,side,phase)))
    n = cross(dr, dt)
    return tuple(x/norm(n) for x in n)


def contacts(a, b):
    """Solve Wang Eq22 independently, without a runtime contact solver."""
    for R in (.86*a.outer_distance, .94*a.outer_distance, a.outer_distance):
        for sign in (-1, 1):
            for fraction in (.1,.3,.5,.7,.9):
                theta=max(a.root,a.base)+(a.tip-max(a.root,a.base))*fraction
                phase=pi/2-pi/a.teeth
                p=frame_a(a.point(theta,R,sign,phase))
                n=frame_a(normal(a,theta,R,sign,phase))
                def residual(rot):
                    return dot(rx(n,rot),cross((1,0,a.teeth/b.teeth),rx(p,rot)))
                c=(residual(0)+residual(pi))/2
                aa=residual(0)-c;bb=residual(pi/2)-c
                amplitude=hypot(aa,bb)
                if abs(c)>amplitude:continue
                offset=atan2(bb,aa);arc=acos(max(-1,min(1,-c/amplitude)))
                for rot in (offset+arc,offset-arc):
                    mate=rz(rx(p,rot),a.teeth/b.teeth*rot)
                    th=atan2(hypot(mate[0],mate[1]),mate[2])
                    if not max(b.root,b.base)+1e-6<th<b.tip-1e-6:continue
                    angle=atan2(mate[1],mate[0])-b.k*log(R/b.outer_distance)
                    angle=(angle+pi/b.teeth)%(2*pi/b.teeth)-pi/b.teeth
                    mate_sign=1 if angle>=0 else -1
                    angular_error=abs(abs(angle)-b.half_angle(th))*R*sin(th)
                    # Remove tooth indexing before comparing the other normal.
                    centre=atan2(mate[1],mate[0])-b.k*log(R/b.outer_distance)-mate_sign*b.half_angle(th)
                    other_normal=normal(b,th,R,mate_sign,centre)
                    first_normal=rz(rx(n,rot),a.teeth/b.teeth*rot)
                    yield angular_error, abs(dot(first_normal,other_normal)), abs(residual(rot))


class BevelGeometryTests(unittest.TestCase):
    def test_spherical_polar_formula_matches_primary_cartesian_equation_one(self):
        # Dong2025 Section2 Eq1, evaluated directly from the generating
        # spherical involute parameter t, independently of angular inversion.
        for z,o in ((24,24),(24,48),(18,30),(17,25),(60,16)):
            q=parameters(z,o,2,20,0)
            for fraction in (.05,.25,.6,1):
                theta=q.base+(q.tip-q.base)*fraction
                t=acos(cos(theta)/cos(q.base));psi=t/sin(q.base)
                x=sin(q.base)*cos(t)*cos(psi)+sin(t)*sin(psi)
                y=sin(q.base)*cos(t)*sin(psi)-sin(t)*cos(psi)
                zz=cos(q.base)*cos(t)
                self.assertAlmostEqual(hypot(hypot(x,y),zz),1,places=13)
                self.assertAlmostEqual(atan2(y,x),spherical_involute(theta,q.base),places=13)
                self.assertAlmostEqual(atan2(hypot(x,y),zz),theta,places=13)
            for hand in (-1,1):
                spiral=parameters(z,o,2,20,.15,45,hand)
                heel=q.outer_distance*cos(q.delta)
                for theta in (max(q.base,q.root)+.001,q.delta,q.tip):
                    xy=spiral.section_point(theta,heel)
                    actualR=hypot(hypot(*xy),heel)
                    azimuth=atan2(xy[1],xy[0])
                    expected=spiral.k*log(actualR/q.outer_distance)+spiral.half_angle(theta)
                    self.assertAlmostEqual(azimuth,expected,places=12)
                # A naive section-wide twist would incorrectly be zero here.
                correction=spiral.k*log(cos(q.delta)/cos(q.tip))
                self.assertGreater(abs(correction),.001)

    def test_common_normal_position_and_velocity_for_both_flanks_ratios_and_hands(self):
        for z,o in ((24,24),(24,48),(18,30),(17,25)):
            for beta in (0,25,45):
                for hand in (-1,1):
                    a=parameters(z,o,2,20,0,beta,hand)
                    b=parameters(o,z,2,20,0,beta,-hand)
                    results=list(contacts(a,b))
                    with self.subTest(z=z,o=o,beta=beta,hand=hand):
                        self.assertGreaterEqual(len(results),12)
                        self.assertLess(max(x[0] for x in results),2e-7)
                        self.assertLess(max(abs(1-x[1]) for x in results),2e-8)
                        self.assertLess(max(x[2] for x in results),2e-12)
                    if beta:
                        wrong=list(contacts(a,replace(b,k=-b.k)))
                        self.assertGreater(max(x[0] for x in wrong),.1)

    def test_nonworking_roots_clear_mate_tips_and_unsupported_flanks_are_refused(self):
        for z,o in ((16,16),(16,60),(60,16),(17,25),(24,48)):
            for pressure in (14.5,20,30):
                a=parameters(z,o,2,pressure,.15)
                b=parameters(o,z,2,pressure,.15)
                self.assertLess(a.root+b.tip,pi/2)
                self.assertLess(b.root+a.tip,pi/2)
                self.assertGreater(a.half_angle(a.tip),0)
                self.assertLess(a.half_angle(a.root),pi/z)
        # The old 60/16 blank's cone occupied the mating tooth-tip cone.
        old_root=atan2(60-2.5,16)
        self.assertGreater(old_root+parameters(16,60,2,20).tip,pi/2)
        self.assertLess(parameters(60,16,2,20).root,old_root)
        with self.assertRaisesRegex(ValueError,'below-base'):
            parameters(16,16,2,1)
        with self.assertRaisesRegex(ValueError,'below its base'):
            spherical_involute(.1,.2)

    def test_both_cap_intervals_have_complete_engagement_or_explicitly_refuse_real_phase_gaps(self):
        for z,o,width,beta in ((24,24,8,0),(24,48,4,0),(16,60,8,35),(60,16,8,35)):
            a=parameters(z,o,2,20,0,beta,1);b=parameters(o,z,2,20,0,beta,-1)
            info=engagement(a,b,width)
            self.assertGreater(info['contact_phase_span_teeth'],1)
            dense=[[],[]];outer=a.outer_distance;inner=outer-width
            # Independently scan the unit-sphere action circle and recover
            # gear angles literally from the profile, rather than s/sin(db).
            for j in range(10001):
                s=-.35+.7*j/10000
                x=cos(a.delta)*cos(s)-sin(radians(20))*sin(a.delta)*sin(s)
                y=-cos(radians(20))*sin(s)
                zz=sin(a.delta)*cos(s)+sin(radians(20))*cos(a.delta)*sin(s)
                theta=atan2(hypot(y,zz),x);mate_theta=atan2(hypot(x,y),zz)
                if not max(a.base,a.root)<=theta<=a.tip or not max(b.base,b.root)<=mate_theta<=b.tip:continue
                lo=max(inner*cos(a.delta)/x,inner*cos(b.delta)/zz)
                hi=min(outer*cos(a.delta)/x,outer*cos(b.delta)/zz)
                if lo>hi:continue
                for sign,values in zip((-1,1),dense):
                    for R in (lo,hi):
                        values.append(atan2(zz,y)-a.half_angle(theta)-sign*a.k*log(R/outer))
            spans=[(max(values)-min(values))/(2*pi/z) for values in dense]
            for actual,expected in zip(spans,info['flank_contact_phase_spans_teeth']):
                self.assertAlmostEqual(actual,expected,delta=.0015)
            # Swapping the member names preserves the complete pair's minimum.
            self.assertAlmostEqual(info['contact_phase_span_teeth'],engagement(b,a,width)['contact_phase_span_teeth'],places=12)
        benchmark=engagement(parameters(24,24,2,20),parameters(24,24,2,20),8)
        self.assertAlmostEqual(benchmark['contact_phase_span_teeth'],1.1920246968825747,places=12)
        # Narrow 16/60 had looked collision-free yet failed continuous tooth
        # availability. Exact extrema establish a real missing phase interval.
        for beta in (0,35,45):
            a=parameters(16,60,2,20,0,beta,1);b=parameters(60,16,2,20,0,beta,-1)
            self.assertLess(engagement(a,b,4)['contact_phase_span_teeth'],1)
            with self.assertRaisesRegex(ValueError,'gap in ideal tooth engagement'):
                generate('differential',dict(side_teeth=16,output_teeth=60,width=4,variant='spiral',spiral_angle=beta))
        with self.assertRaisesRegex(ValueError,'gap in ideal tooth engagement'):
            generate('differential',dict(module=6,width=2))

    def test_refined_section_flanks_and_planar_caps_share_closed_geometry(self):
        for hand in (-1,1):
            d=generate('differential',dict(variant='spiral',spiral_angle=45,spiral_hand=hand,side_teeth=17,output_teeth=25,width=4))
            for p in d.parts[:3]:
                self.assertGreater(signature(p)['volume_mm3'],0)
                self.assertTrue(all(s['holes']==p.holes for s in p.stations))
                for face in faces(p):
                    if len(face[0])>3:
                        # Every cap remains in a single actual world plane.
                        axis=p.frame[3];levels={round(dot(axis,x),10) for loop in face for x in loop}
                        self.assertEqual(len(levels),1)
                q=parameters(17 if p is not d.parts[2] else 25,25 if p is not d.parts[2] else 17,2,20,.15,45,hand if p is not d.parts[2] else -hand)
                z=p.z+p.width
                coarse=section(q,z)
                fine=section(q,z,tolerance=PROFILE_TOLERANCE/8)
                # Independent point-to-polyline oracle on a refined profile.
                for point in fine[::3]:
                    radius=hypot(*point)
                    # Restrict candidates by radius to keep the oracle small.
                    best=float('inf')
                    for a,b in zip(coarse,coarse[1:]+coarse[:1]):
                        if min(hypot(*a),hypot(*b))-1>radius or max(hypot(*a),hypot(*b))+1<radius:continue
                        dx,dy=b[0]-a[0],b[1]-a[1];den=dx*dx+dy*dy
                        f=max(0,min(1,((point[0]-a[0])*dx+(point[1]-a[1])*dy)/den)) if den else 0
                        best=min(best,hypot(point[0]-a[0]-f*dx,point[1]-a[1]-f*dy))
                    self.assertLessEqual(best,PROFILE_TOLERANCE*1.05)

    def test_actual_shared_mesh_moves_clear_in_wrist_and_classic_with_collision_negative_control(self):
        cases=(dict(),dict(configuration='classic',side_teeth=17,output_teeth=25,variant='spiral',spiral_angle=45,spiral_hand=-1,input_rpm=0,output_difference_rpm=24),
               dict(side_teeth=24,output_teeth=48,variant='spiral',spiral_angle=35,spiral_hand=1))
        for values in cases:
            d=generate('differential',dict(width=4,**values));plan=build_plan(d)
            meshes=[list(triangles(p)) for p in d.parts[:3]]
            for fraction in (0,.31,.73):
                phase=2*pi/d.values['side_teeth']*fraction
                surfaces=[Surface([tuple(transform(plan.matrix(i,phase),p) for p in t) for t in mesh]) for i,mesh in enumerate(meshes)]
                for i in (0,1):
                    result=relation(surfaces[i],surfaces[2],1e-6)
                    self.assertEqual(result['kind'],'Separated',(values,fraction,i,result))
                    self.assertGreater(result['distance'],.01)
                    # relation() tests containment in BOTH directions.
            if not values:
                a=Surface(meshes[0]);shift=rotation(pi/d.values['output_teeth'])
                bad=Surface([tuple(transform(shift,p) for p in t) for t in meshes[2]])
                self.assertEqual(relation(a,bad,1e-6)['kind'],'Intersection')

    def test_zero_backlash_spiral_faceting_stays_in_the_normal_checker_boundary_band(self):
        d=generate('differential',dict(width=4,variant='spiral',spiral_angle=45,backlash=0))
        meshes=[list(triangles(p)) for p in d.parts[:3]];plan=build_plan(d)
        for fraction in (0,.17,.53):
            phase=2*pi/24*fraction
            surfaces=[Surface([tuple(transform(plan.matrix(i,phase),p) for p in t) for t in mesh]) for i,mesh in enumerate(meshes)]
            for i in (0,1):
                self.assertEqual(relation(surfaces[i],surfaces[2],.01)['kind'],'Boundary contact / unresolved')


if __name__=='__main__':unittest.main()
