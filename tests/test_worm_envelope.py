# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Independent contact normals and literal moving triangulated-solid slices.

The collision oracle never evaluates the envelope equation: it intersects the
actual triangle strips with a plane and performs ordinary polygon containment.
"""
from bisect import bisect_right
import json
from math import pi,sin,cos,tan,atan,atan2,hypot,sqrt,radians,degrees
import unittest

from geometry import generate,contains,profile_sections
from motion import build_plan,transform
from solid_geometry import point,signature
from worm_geometry import WormSurface,WheelSection,CHORD
from test_geometry import distance


def inverse(matrix,p):
    q=[p[i]-matrix[12+i] for i in range(3)]
    return tuple(sum(matrix[4*i+j]*q[j] for j in range(3)) for i in range(3))


class SlicedSolid:
    """An independent exact planar intersection of the shared triangle strips."""
    def __init__(self,part):
        self.part=part
        self.levels=profile_sections(part)
        self.zs=[x[0] for x in self.levels]
        self.radius=max(hypot(*q) for _,_,loop in self.levels for q in loop)
    def penetration(self,world):
        p=self.part
        if p.axis_x:x,y,z=-world[2]+p.z,world[1],world[0]+p.width/2
        else:x,y,z=world[0]-p.center[0],world[1]-p.center[1],world[2]-p.z
        if not self.zs[0]<z<self.zs[-1] or hypot(x,y)>self.radius:return 0.
        i=min(len(self.zs)-2,bisect_right(self.zs,z)-1)
        lo,_,a=self.levels[i];hi,_,b=self.levels[i+1]
        t=(z-lo)/(hi-lo)
        mix=lambda u,v:((1-t)*u[0]+t*v[0],(1-t)*u[1]+t*v[1])
        outline=[]
        for j in range(len(a)):
            k=(j+1)%len(a)
            outline.append(mix(a[j],b[j]))
            outline.append(mix(a[k],b[j]) if p.alternate_diagonal else mix(a[j],b[k]))
        if not contains(outline,(x,y)):return 0.
        if any(contains(h,(x,y)) for h in p.holes):return 0.
        return distance((x,y),outline)


def surface_samples(part):
    """Vertices and triangle centroids distributed over the real side strips."""
    levels=profile_sections(part)
    samples=[]
    step=max(1,(len(levels)-1)//7)
    for i in range(0,len(levels)-1,step):
        lo,angle,a=levels[i];hi,_,b=levels[i+1]
        for j in range(0,len(a),max(1,len(a)//100)):
            k=(j+1)%len(a)
            v=[point(part,a[j],lo,0),point(part,a[k],lo,0),point(part,b[j] if part.alternate_diagonal else b[k],hi,0)]
            samples.append(v[0])
            samples.append(tuple(sum(q[d] for q in v)/3 for d in range(3)))
    return samples


class WormEnvelopeTests(unittest.TestCase):
    def test_khk_axial_module_benchmark_and_nominal_pitch(self):
        # KHK Table4.23: mx=3, z1=2, z2=30, d1=44, alpha_n=20deg.
        gamma=atan(6/44)
        ax=degrees(atan(tan(radians(20))/cos(gamma)))
        d=generate('worm',dict(module=3,starts=2,teeth=30,diameter=44,pressure=ax))
        self.assertAlmostEqual(d.analysis['lead_angle_deg'],7.765166018425334)
        self.assertAlmostEqual(d.analysis['center_distance_mm'],67)
        self.assertAlmostEqual(d.analysis['normal_pressure_deg'],20)
        self.assertEqual(d.analysis['wheel_geometry']['reference_wheel_radius_mm'],45)
        self.assertAlmostEqual(d.analysis['lead_mm'],6*pi)

    def test_physical_common_normal_forward_inverse_and_za_base_circle(self):
        for variant in ('za','zi'):
            for hand in (-1,1):
                d=generate('worm',dict(variant=variant,worm_hand=hand,backlash=0))
                s=WormSurface(d.values)
                mu=hand*d.values['starts']/d.values['teeth']
                for height in (-3.71,0,2.39):
                    for side in (-1,1):
                        section=WheelSection(s,height)
                        for fraction in (.13,.47,.81):
                            r=section.starts[side]+(section.flank_ends[side]-section.starts[side])*fraction
                            q,original,n,phi=s.contact(r,height,side)
                            chi=mu*phi
                            X=q[0]*cos(chi)-q[1]*sin(chi)
                            Y=q[0]*sin(chi)+q[1]*cos(chi)-s.a
                            self.assertAlmostEqual(Y,original[1],places=10)
                            self.assertAlmostEqual(X,original[0]-hand*s.k*phi,places=10)
                            # Literal angular velocities about world axes; no
                            # equivalent-translation equation is used here.
                            velocity=(mu*(Y+s.a),-height-mu*X,Y)
                            self.assertAlmostEqual(sum(a*b for a,b in zip(n,velocity)),0,places=10)
                            # Inverse physical screw rotation must land exactly
                            # on a flank of the original, zero-backlash screw.
                            y=Y*cos(phi)+height*sin(phi);z=-Y*sin(phi)+height*cos(phi)
                            theta=(atan2(y,-z)-hand*(X+s.length/2)/s.k+pi/s.starts)%(2*pi/s.starts)-pi/s.starts
                            self.assertAlmostEqual(abs(theta),s.half_angle(hypot(y,z)),places=10)
                            if variant=='za' and height==0:
                                # Independent planar involute benchmark: each
                                # normal is tangent to the wheel's base circle.
                                base=abs(X*n[1]-(Y+s.a)*n[0])/hypot(n[0],n[1])
                                self.assertAlmostEqual(base,s.R*cos(s.alpha),places=9)

    def test_undercut_root_transition_and_roundtrip(self):
        for variant in ('za','zi'):
            d=generate('worm',dict(variant=variant,teeth=12,pressure=25,width=1))
            self.assertTrue(d.analysis['wheel_geometry']['undercut_trimmed'])
            s=WormSurface(d.values)
            for height in (-.5,0,.5):
                section=WheelSection(s,height)
                for side in (-1,1):
                    a,b=section.flank(side,1),section.fillet(side,0)
                    self.assertLess(hypot(a[0]-b[0],a[1]-b[1]),1e-7)
            self.assertGreater(signature(d.parts[1])['volume_mm3'],0)
            self.assertEqual(generate('worm',json.loads(json.dumps(d.values))).parts,d.parts)
        with self.assertRaisesRegex(ValueError,'Wheel too wide'):
            generate('worm',dict(width=30))

    def test_literal_mesh_moving_clearance_both_hands_variants_and_parameter_cases(self):
        cases=({},dict(starts=4,width=6),dict(diameter=30,teeth=40,width=8),
               dict(module=1,diameter=14,length=12,width=6,journal_diameter=8,bore=2),
               dict(teeth=12,pressure=25,width=1))
        for variant in ('za','zi'):
            for hand in (-1,1):
                for values in cases:
                    with self.subTest(variant=variant,hand=hand,values=values):
                        d=generate('worm',dict(variant=variant,worm_hand=hand,**values))
                        solids=[SlicedSolid(p) for p in d.parts[:2]]
                        samples=[surface_samples(p) for p in d.parts[:2]]
                        plan=build_plan(d)
                        maximum=0.;queries=0
                        # Unaligned phases include a full revolution and
                        # reverse motion, not merely tooth-index snapshots.
                        for phase in (0,.173,.719,1.337,2.581,4.913,6.283185307179586,-.491):
                            matrices=[plan.matrix(i,phase) for i in (0,1)]
                            for source,target in ((0,1),(1,0)):
                                for p in samples[source]:
                                    q=inverse(matrices[target],transform(matrices[source],p))
                                    maximum=max(maximum,solids[target].penetration(q));queries+=1
                        self.assertGreater(queries,1000)
                        self.assertLessEqual(maximum,.01,'Strict common interior on literal shared mesh')

    def test_collision_oracle_detects_deliberately_wrong_wheel_phase(self):
        d=generate('worm')
        solid=SlicedSolid(d.parts[0])
        phi=.173;chi=phi*d.values['starts']/d.values['teeth']+.4*2*pi/d.values['teeth']
        worst=0.
        for p in surface_samples(d.parts[1]):
            x,y,z=p;x-=d.parts[1].center[0];y-=d.parts[1].center[1]
            X=x*cos(chi)-y*sin(chi);Y=x*sin(chi)+y*cos(chi)+d.parts[1].center[1]
            q=(X,Y*cos(phi)+z*sin(phi),-Y*sin(phi)+z*cos(phi))
            worst=max(worst,solid.penetration(q))
        self.assertGreater(worst,.05)


if __name__=='__main__':unittest.main()
