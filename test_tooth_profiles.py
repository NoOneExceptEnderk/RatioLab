# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Numerical oracles independent of the envelope construction.

The rack oracle time-steps a solid cutter in the blank frame and queries its
interior. It never calls rack_point or the analytic meshing equation.
"""
import json
import unittest
from math import sin, cos, tan, atan2, hypot, pi, radians, sqrt
from geometry import gear_part, generate, sample_curve, profile_sections
from tooth_profiles import rack_parameters, external_half, internal_half
from wave_geometry import map_point, unmap_point
from special_drives import ellipse_axes
from solid_geometry import signature


def swept_depth(point,z,mt,mn,alpha,backlash,shift,hf=1.25,poses=6001):
    """Maximum cutter penetration at a blank point, in normal rack mm.

    Direct solid membership uses horizontal slices of the rounded trapezoid.
    Distances here are signed slice margins, not Euclidean surface distances.
    """
    an=radians(alpha);cb=mn/mt;rp=z*mt/2
    land=pi*mn/4+backlash*cb/4-hf*mn*tan(an)
    rho=min(.3*mn,(land-.025*mn)*cos(an)/(1-sin(an)))
    uc=land-rho*(1-sin(an))/cos(an);vc=-hf*mn+rho+shift*mn
    rotation=pi/2-pi/z;x,y=point
    x,y=x*cos(rotation)-y*sin(rotation),x*sin(rotation)+y*cos(rotation)
    best=-1e9
    for j in range(poses):
        span=max(4*pi/z,.75)
        phi=-span+2*span*j/(poses-1)
        u=(x*cos(phi)-y*sin(phi)+rp*phi)*cb
        v=x*sin(phi)+y*cos(phi)-rp
        u=abs((u+pi*mn/2)%(pi*mn)-pi*mn/2)
        if v<vc-rho:margin=v-(vc-rho)
        elif v<vc-rho*sin(an):
            margin=min(v-(vc-rho),uc+sqrt(max(0,rho*rho-(v-vc)**2))-u)
        else:margin=pi*mn/4+backlash*cb/4+(v-shift*mn)*tan(an)-u
        best=max(best,margin)
    return best


class GeneratedProfileTests(unittest.TestCase):
    def test_rack_solid_sweep_independently_bounds_generated_flanks(self):
        for z,x,beta in [(8,0,0),(12,-.3,0),(24,.4,0),(12,-.25,30),(24,.5,-35)]:
            with self.subTest(z=z,x=x,beta=beta):
                mn=2;mt=mn/cos(radians(beta));at=__import__('math').degrees(__import__('math').atan(tan(radians(20))/cos(radians(beta))))
                flank,meta=external_half(z,mt,at,.15,mn,x,20,1,1.25,sample_curve)
                # The solid cutter must approach every generated root/flank.
                # Pose discretization is independent and deliberately finer
                # than the profile chord threshold.
                for p in flank[::max(1,len(flank)//8)]:
                    depth=swept_depth(p,z,mt,mn,20,.15,x)
                    self.assertLess(depth,.004)
                    self.assertGreater(depth,-.004)
                self.assertTrue(meta['generated'])

    def test_undercut_trim_shift_helix_and_impossible_tool(self):
        for z,x,trim in [(8,0,True),(12,-.5,True),(12,.5,False),(24,0,False)]:
            p=gear_part('Gear',z,2,20,.15,8,shift=x)
            meta=p.profile_metadata['tooth_profile'];self.assertEqual(meta['undercut_trimmed'],trim)
            self.assertGreater(signature(p)['volume_mm3'],0)
        tool=rack_parameters(24,2/cos(radians(35)),__import__('math').degrees(__import__('math').atan(tan(radians(20))/cos(radians(35)))),depth=2,normal_pressure=20)
        self.assertAlmostEqual(tool['cos_beta'],cos(radians(35)))
        # A normal circle becomes an ellipse, rather than a transverse circle.
        self.assertGreater(tool['tip_radius']/tool['cos_beta'],tool['tip_radius'])
        with self.assertRaisesRegex(ValueError,'Impossible rack'):
            gear_part('Gear',24,2,60,0,8,hf=1.6)
        with self.assertRaises(ValueError):gear_part('Gear',8,2,20,.15,8,shift=1)

    def test_internal_blend_is_tangent_and_removes_radial_corner(self):
        for z,beta in [(54,0),(66,25),(54,-35)]:
            mn=2;mt=mn/cos(radians(beta));at=__import__('math').degrees(__import__('math').atan(tan(radians(20))/cos(radians(beta))))
            flank,meta=internal_half(z,mt,at,.15,mn,1,1.25,sample_curve)
            self.assertFalse(meta['generated']);rho=meta['blend_radius_mm'];root=meta['root_radius_mm']
            end=flank[-1];center=((root-rho)*end[0]/root,(root-rho)*end[1]/root)
            # Fit the circle independently from the last three sampled points.
            a,b,c=flank[-3:];det=2*(a[0]*(b[1]-c[1])+b[0]*(c[1]-a[1])+c[0]*(a[1]-b[1]))
            ux=((a[0]**2+a[1]**2)*(b[1]-c[1])+(b[0]**2+b[1]**2)*(c[1]-a[1])+(c[0]**2+c[1]**2)*(a[1]-b[1]))/det
            uy=((a[0]**2+a[1]**2)*(c[0]-b[0])+(b[0]**2+b[1]**2)*(a[0]-c[0])+(c[0]**2+c[1]**2)*(b[0]-a[0]))/det
            self.assertAlmostEqual(hypot(a[0]-ux,a[1]-uy),rho,places=7)
            self.assertLess(hypot(ux-center[0],uy-center[1]),1e-7)
            p=gear_part('Ring',z,2,20,.15,8,helix=beta,internal=True)
            self.assertGreater(signature(p)['volume_mm3'],0)
        regression=generate('internal',dict(variant='helical',wheel=36,pinion=20,module=2,pressure=30,helix=-35))
        ring=next(p for p in regression.parts if p.internal)
        meta=ring.profile_metadata['tooth_profile'];self.assertTrue(meta['blend_radius_adapted'])
        self.assertGreater(meta['blend_radius_mm'],0)
        self.assertLess(meta['blend_radius_mm'],meta['nominal_blend_radius_mm'])
        self.assertGreater(signature(ring)['volume_mm3'],0)
        with self.assertRaises(ValueError):gear_part('Ring',16,2,20,.15,8,internal=True)

    def test_wave_equal_arc_pitch_normal_orientation_and_inverse(self):
        for z,factor in [(30,1.5),(60,1),(160,.5)]:
            rp=z;a,b=ellipse_axes(rp,2*factor)
            # Independent dense polyline arc measurement between tooth centres.
            segments=[]
            for k in range(z):
                points=[map_point(2*pi*(k+j/512)/z,0,1,a,b,rp) for j in range(513)]
                segments.append(sum(hypot(v[0]-u[0],v[1]-u[1]) for u,v in zip(points,points[1:])))
            self.assertLess(max(segments)-min(segments),1e-6)
            self.assertAlmostEqual(sum(segments),2*pi*rp,delta=2e-5)
            for u in (.1,1.2,3.8):
                p=map_point(u,0,1,a,b,rp);q=map_point(u,1,1,a,b,rp)
                self.assertAlmostEqual((q[0]-p[0])*p[1]/(b*b)-(q[1]-p[1])*p[0]/(a*a),0,places=8)
                for weight in (0,.3,1):
                    point=map_point(u,-3,weight,a,b,rp)
                    material=unmap_point(*point,weight,a,b,rp)
                    for fa,wa in [(0,0),(.4,1.5),(-1,3)]:
                        mapped=map_point(*material,a,b,rp,fa,wa)
                        expected=map_point(u,-3,weight,a,b,rp,fa,wa)
                        self.assertLess(hypot(mapped[0]-expected[0],mapped[1]-expected[1]),1e-7)

    def test_wave_shoulder_has_exact_shared_vertices_not_micro_edges(self):
        for variant in ('cup','flat_cup','hat'):
            p=generate('harmonic',dict(variant=variant,cup_length=8,width=5)).parts[0]
            for lower,upper in zip(p.stations,p.stations[1:]):
                if lower['z']!=upper['z']:continue
                for a,b in zip(lower['outer'],upper['outer']):
                    distance=hypot(a[0]-b[0],a[1]-b[1])
                    self.assertTrue(distance==0 or distance>1e-7,(variant,distance))
            self.assertGreater(signature(p)['volume_mm3'],0)

    def test_worm_throat_cylinder_and_export_metadata_roundtrip(self):
        for hand in (-1,1):
            d=generate('worm',dict(worm_hand=hand));wheel=d.parts[1]
            meta=d.analysis['wheel_geometry'];r=meta['radius_mm']
            self.assertEqual(d.analysis['signed_ratio'],hand*d.values['teeth']/d.values['starts'])
            self.assertEqual(wheel.port['rpm'],d.values['input_rpm']/d.analysis['signed_ratio'])
            middle=wheel.stations[len(wheel.stations)//2]['outer']
            for s in wheel.stations:
                h=s['z']-wheel.width/2
                # Independent cylinder relation, not sagitta reconstruction.
                for p,q in zip(s['outer'][::17],middle[::17]):
                    dr=hypot(*p)-hypot(*q)
                    self.assertAlmostEqual((r-dr)**2+h*h,r*r,places=7)
            self.assertGreater(signature(wheel)['volume_mm3'],0)
            restored=generate(d.family,json.loads(json.dumps(d.values)))
            self.assertEqual(restored.parts,d.parts)
        right=generate('worm').parts[1];left=generate('worm',dict(worm_hand=-1)).parts[1]
        self.assertAlmostEqual(signature(left)['volume_mm3'],signature(right)['volume_mm3'],places=7)
        for f in ('spur','internal','helical','double','harmonic'):
            d=generate(f);self.assertTrue(d.analysis['tooth_profiles'])
            self.assertEqual(generate(f,json.loads(json.dumps(d.values))).parts,d.parts)
        with self.assertRaisesRegex(ValueError,'Wheel too wide'):generate('worm',{'width':30})

if __name__=='__main__':unittest.main(verbosity=2)
