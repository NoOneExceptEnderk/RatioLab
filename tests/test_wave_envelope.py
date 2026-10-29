# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Literal off-grid moving polygon checks, engagement and negative controls."""
from math import pi,sin,cos,atan2,hypot,floor
import json
import unittest
from geometry import generate,gear_part
from wave_geometry import map_point
from motion import build_plan
from solid_geometry import signature


def ring_ray(hole,zc,theta):
    # Direct line/ray intersection on the actual generated polygon. No swept
    # envelope routines, interpolation of radial ordinates or meshing equations.
    n=len(hole)//zc;pitch=2*pi/zc;step=pitch/n
    t=(theta+pitch/2)%pitch-pitch/2;j=min(n-1,floor((t+pitch/2)/step))
    p=hole[j]
    if j+1<n:q=hole[j+1]
    else:q=(hole[0][0]*cos(pitch)-hole[0][1]*sin(pitch),hole[0][0]*sin(pitch)+hole[0][1]*cos(pitch))
    dx,dy=q[0]-p[0],q[1]-p[1]
    radius=(p[0]*q[1]-p[1]*q[0])/(cos(t)*dy-sin(t)*dx)
    norm=hypot(dx,dy);nx,ny=dy/norm,-dx/norm;angle=theta-t
    return radius,(nx*cos(angle)-ny*sin(angle),nx*sin(angle)+ny*cos(angle))


class WaveEnvelopeTests(unittest.TestCase):
    def test_housing_output_kinematics_shared_profile_and_roundtrip(self):
        reference=None
        for variant in ('cup','flat_cup','hat'):
            for output in ('flex','circular'):
                d=generate('harmonic',dict(variant=variant,harmonic_output=output,input_rpm=13.2))
                k=d.analysis['kinematics']['stage_results'][0]['rates_rpm'];z=d.values['teeth']
                self.assertAlmostEqual(2*k['wave']+z*k['flex']-(z+2)*k['circular'],0)
                self.assertTrue(d.analysis['wave_mapping']['conjugate'])
                self.assertFalse(d.analysis['wave_mapping']['elastic_solution'])
                ring=d.parts[1]
                self.assertEqual(len(ring.holes[0]),128*(z+2))
                if reference is None:reference=ring.holes[0]
                self.assertEqual(reference,ring.holes[0])
                for p in d.parts:self.assertGreater(signature(p)['volume_mm3'],0)
                self.assertEqual(generate('harmonic',json.loads(json.dumps(d.values))).parts,d.parts)

    def test_literal_polygon_sweeps_all_branches_corners_and_both_outputs(self):
        for z,factor in ((30,.5),(30,1),(30,1.5),(60,.5),(60,1),(60,1.5),(100,.5),(100,1),(100,1.5)):
            for output in ('flex','circular'):
                with self.subTest(z=z,factor=factor,output=output):
                    d=generate('harmonic',dict(teeth=z,wave_factor=factor,harmonic_output=output))
                    a,b=d.analysis['pitch_ellipse_semiaxes_mm'];rp=d.values['module']*z/2
                    refs=d.parts[0].stations[-1]['material_outer'];hole=d.parts[1].holes[0]
                    rates=d.analysis['kinematics']['stage_results'][0]['rates_rpm']
                    ref=abs(d.values['input_rpm']) or 1;wf=rates['flex']/ref;we=rates['wave']/ref;wc=rates['circular']/ref
                    maximum=-1e9
                    for phase in [pi*(k+.317)/13 for k in range(13)]+[-.713,0,2*pi]:
                        points=[map_point(*p,a,b,rp,wf*phase,we*phase) for p in refs]
                        c,s=cos(-wc*phase),sin(-wc*phase)
                        points=[(x*c-y*s,x*s+y*c) for x,y in points]
                        for p,q in zip(points,points[1:]+points[:1]):
                            for f in (0,.25,.5,.75):
                                x=p[0]+f*(q[0]-p[0]);y=p[1]+f*(q[1]-p[1])
                                radius,_=ring_ray(hole,z+2,atan2(y,x))
                                maximum=max(maximum,hypot(x,y)-radius)
                    self.assertLess(maximum,.004,'Literal moving mesh intrudes beyond the numerical envelope threshold')

    def test_zero_backlash_useful_flank_engagement_and_wrong_phase_control(self):
        for z,factor in ((30,.5),(30,1.5),(60,1),(100,.5),(100,1.5)):
            d=generate('harmonic',dict(teeth=z,wave_factor=factor,backlash=0))
            a,b=d.analysis['pitch_ellipse_semiaxes_mm'];rp=z;hole=d.parts[1].holes[0]
            original=gear_part('independent reference',z,2,20,0,10).outer
            material=[]
            for p,q in zip(original,original[1:]+original[:1]):
                if abs(hypot(*p)-hypot(*q))<1e-6:continue  # exclude radial tip/root lands
                for j in range(5):
                    x=p[0]+(q[0]-p[0])*j/5;y=p[1]+(q[1]-p[1])*j/5
                    material.append((atan2(y,x),hypot(x,y)-rp))
            wrong=0.
            for phase in [pi*(k+.31)/11 for k in range(11)]:
                closest=100.
                for u,offset in material:
                    if not -.5<offset<2.000001:continue
                    p=map_point(u,offset,1,a,b,rp,-2/z*phase,phase)
                    r=hypot(*p);radius,n=ring_ray(hole,z+2,atan2(p[1],p[0]))
                    gap=(radius-r)*abs((p[0]*n[0]+p[1]*n[1])/r)
                    moment=abs(p[0]*n[1]-p[1]*n[0])/r
                    h=1e-5;q=map_point(u,offset,1,a,b,rp,-2/z*(phase+h),phase+h)
                    velocity=((q[0]-p[0])/h,(q[1]-p[1])/h)
                    fraction=abs(velocity[0]*n[0]+velocity[1]*n[1])/max(hypot(*velocity),1e-8)
                    if moment>.2 and fraction<.1:closest=min(closest,gap)
                    shifted,_=ring_ray(hole,z+2,atan2(p[1],p[0])+.4*2*pi/(z+2))
                    wrong=max(wrong,r-shifted)
                self.assertLess(closest,.004,'No useful flank contact within the sampled numerical envelope precision')
            self.assertGreater(wrong,.05,'Negative control did not expose the wrong ring phase')

    def test_reference_backlash_is_separate_from_numerical_enclosure(self):
        zero=generate('harmonic',dict(backlash=0));working=generate('harmonic',dict(backlash=.3))
        az=[hypot(*p) for p in zero.parts[1].holes[0][:128]]
        aw=[hypot(*p) for p in working.parts[1].holes[0][:128]]
        self.assertGreater(max(y-x for x,y in zip(az,aw)),.05)
        # Conservative discretisation relief changes with the generating
        # reference; compare physical widening outside that reported band.
        numeric=sum(d.analysis['wave_mapping']['ring_envelope']['numerical_enclosure_relief_mm'] for d in (zero,working))+.002
        self.assertGreaterEqual(min(y-x for x,y in zip(az,aw)),-numeric)
        for d in (zero,working):
            q=d.analysis['wave_mapping'];e=q['ring_envelope']
            self.assertEqual(q['reference_pair_backlash_mm'],d.values['backlash'])
            self.assertLessEqual(e['measured_refinement_change_mm'],e['convergence_threshold_mm'])
            self.assertGreaterEqual(e['numerical_enclosure_relief_mm'],0)


if __name__=='__main__':unittest.main()
