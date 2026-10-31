# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Independent nominal benchmarks and polygon/axial failure-path regressions."""
import json
import math
import unittest
from unittest.mock import patch

from geometry import generate, involute, transformed, profile_sections, section_holes
from internal_mesh import (plan_planetary_internal_pair, verify_internal_polygon_pair,
                           polygon_pose_clearance, validate_axial_pair, _plan)
from engineering import mesh, report_text


def square(r):
    return [(-r,-r),(r,-r),(r,r),(-r,r)]


def segment_min_radius(a,b):
    dx=b[0]-a[0];dy=b[1]-a[1];den=dx*dx+dy*dy
    t=max(0,min(1,-(a[0]*dx+a[1]*dy)/den)) if den else 0
    return math.hypot(a[0]+t*dx,a[1]+t*dy)


def independent_clear(planet,ring):
    """Independent spatial-grid proper crossings and ray containment.

    Supplemental dense sweep only, never the continuous certificate.
    """
    cell=3.; grid={}
    def cells(a,b):
        for x in range(math.floor(min(a[0],b[0])/cell),math.floor(max(a[0],b[0])/cell)+1):
            for y in range(math.floor(min(a[1],b[1])/cell),math.floor(max(a[1],b[1])/cell)+1):yield x,y
    edges=list(zip(ring,ring[1:]+ring[:1]))
    for i,(a,b) in enumerate(edges):
        for key in cells(a,b):grid.setdefault(key,[]).append(i)
    def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    for a,b in zip(planet,planet[1:]+planet[:1]):
        nearby=set(i for key in cells(a,b) for i in grid.get(key,[]))
        for i in nearby:
            c,d=edges[i]
            if cross(a,b,c)*cross(a,b,d)<0 and cross(c,d,a)*cross(c,d,b)<0:return False
    x,y=planet[0];count=0
    for a,b in edges:
        if (a[1]>y)!=(b[1]>y) and a[0]+(y-a[1])*(b[0]-a[0])/(b[1]-a[1])>x:count+=1
    return bool(count%2)


class PairedConstructionTests(unittest.TestCase):
    def test_independent_benchmarks_and_full_roll_residuals(self):
        cases=[(18,54,0,53.01446721217457,.4927663939127136,1.2930583571881276),
               (24,72,0,70.74589711271742,.6270514436412924,1.4702851818196647),
               (18,54,20,56.30574894907068,.579925382314,1.264683475216311),
               (18,54,25,58.33486127927015,.623773172352,1.2374137057161156)]
        for zp,zr,beta,tip,ha,epsilon in cases:
            for sign in (1,-1):
                with self.subTest(zp=zp,beta=beta*sign):
                    p=plan_planetary_internal_pair(zp,zr,2,beta=beta*sign)
                    self.assertAlmostEqual(p['ring_tip_radius_mm'],tip,places=10)
                    self.assertAlmostEqual(p['ring_addendum_coefficient'],ha,places=10)
                    self.assertAlmostEqual(p['contact_transverse'],epsilon,places=10)
                    mt=2/math.cos(math.radians(beta));at=math.atan(math.tan(math.radians(20))/math.cos(math.radians(beta)))
                    rp=mt*zp/2;rr=mt*zr/2;a=rr-rp;bp=rp*math.cos(at);br=rr*math.cos(at)
                    lo=math.sqrt(tip*tip-br*br)-a*math.sin(at)
                    hi=math.sqrt((rp+2)**2-bp*bp)
                    self.assertGreaterEqual(lo-math.sqrt(p['planet_involute_start_radius_mm']**2-bp*bp),0)
                    self.assertGreaterEqual(math.sqrt(p['ring_join_radius_mm']**2-br*br)-hi-a*math.sin(at),0)
                    self.assertAlmostEqual((hi-lo)/(math.pi*mt*math.cos(at)),epsilon)
                    self.assertEqual(p['verification']['status'],'clear')

    def test_module_scale_backlash_and_nonidentical_counts(self):
        a=plan_planetary_internal_pair(18,54,2)
        b=plan_planetary_internal_pair(18,54,4,backlash=.3)
        self.assertAlmostEqual(a['contact_transverse'],b['contact_transverse'])
        self.assertAlmostEqual(a['ring_tip_radius_mm']*2,b['ring_tip_radius_mm'])
        self.assertEqual(plan_planetary_internal_pair(18,60,2)['verification']['status'],'clear')
        self.assertEqual(plan_planetary_internal_pair(18,54,2,backlash=.25)['verification']['status'],'clear')
        for kwargs in [dict(mn=.2),dict(zp=8,zr=24),dict(mn=2,profile_chord_threshold_mm=.01)]:
            args=dict(zp=18,zr=54,mn=2);args.update(kwargs)
            with self.assertRaises(ValueError):plan_planetary_internal_pair(**args)

    def test_reduced_blend_bracket_is_tangent_and_radially_monotone(self):
        from tooth_profiles import internal_half
        calls=[]
        def sample(fn,a,b):
            points=[fn(a+(b-a)*i/128) for i in range(129)]
            calls.append((fn,a,b,points));return points
        _,info=internal_half(54,2,20,.15,2,.4927663939127136,1.25,sample,56.4)
        self.assertTrue(info['blend_radius_adapted'])
        self.assertAlmostEqual(info['involute_end_radius_mm'],56.4,places=9)
        f,a,b,flank=calls[0];g,c,d,blend=calls[1]
        radii=[math.hypot(*p) for p in blend]
        self.assertTrue(all(r>=q-1e-10 for q,r in zip(radii,radii[1:])))
        self.assertGreaterEqual(min(segment_min_radius(p,q) for p,q in zip(blend,blend[1:])),56.4-1e-9)
        eps=1e-7;v=[x-y for x,y in zip(f(b),f(b-eps))];w=[x-y for x,y in zip(g(c+eps),g(c))]
        cosine=sum(x*y for x,y in zip(v,w))/(math.hypot(*v)*math.hypot(*w))
        self.assertGreater(cosine,1-1e-7)
        with self.assertRaises(ValueError):internal_half(54,2,20,.15,2,.5,1.25,sample,56.5)

    def test_actual_contour_metadata_and_unchanged_external_gears(self):
        d=generate('planetary');p=d.analysis['meshes'][1]['internal_pair_construction']
        planet=next(q for q in d.parts if q.name=='S1_Planet_1');ring=next(q for q in d.parts if q.name=='S1_Ring')
        radii=[segment_min_radius(a,b) for a,b in zip(ring.holes[0],ring.holes[0][1:]+ring.holes[0][:1])]
        self.assertGreaterEqual(min(radii),p['ring_tip_radius_mm']-1e-9)
        self.assertAlmostEqual(max(math.hypot(*q) for q in planet.outer),p['planet_tip_radius_mm'])
        info=ring.profile_metadata['tooth_profile'];q=d.analysis['meshes'][1]
        self.assertEqual(info['construction_version'],'planetary_paired_involute_v1')
        self.assertEqual(info['tooth_thickness'],q['gear2']['tooth_thickness'])
        self.assertAlmostEqual(info['tip_radius_mm'],q['gear2']['tip_radius'])
        legacy=involute(18,2)
        self.assertEqual(planet.outer,transformed(legacy,angle=math.pi/18+math.pi))
        text=report_text(d)
        self.assertIn('tip relief 1.014467',text)
        self.assertIn('excludes analytic curve sampling error',text)

    def test_dense_independent_actual_pair_and_bad_phase(self):
        for zp in (18,24):
            p=plan_planetary_internal_pair(zp,3*zp,2)
            planet=involute(zp,2);ring=involute(3*zp,2,internal=True,ha=p['ring_addendum_coefficient'],minimum_join_radius_mm=p['minimum_join_radius_mm'])
            phaseP=math.pi/zp+math.pi;phaseR=(zp*phaseP-math.pi)/(3*zp)
            for i in range(97):
                phi=2*math.pi/zp*i/96
                pts=transformed(planet,(p['center_distance_mm'],0),phaseP+phi)
                void=transformed(ring,angle=phaseR+phi/3)
                self.assertTrue(independent_clear(pts,void),(zp,i))
            bad=verify_internal_polygon_pair(planet,ring,phaseP+math.pi/zp,phaseR,zp,3*zp,p['center_distance_mm'])
            self.assertEqual(bad['status'],'collision')

    def test_all_variants_both_hands_and_axial_subset_law(self):
        for variant in ('spur','helical','double','two_stage','two_stage_double'):
            for sign in (1,-1):
                d=generate('planetary',dict(variant=variant,helix=25*sign))
                for stage in range(1,3 if 'two_stage' in variant else 2):
                    p=next(q for q in d.parts if q.name==f'S{stage}_Planet_1')
                    r=next(q for q in d.parts if q.name==f'S{stage}_Ring')
                    q=d.analysis['meshes'][2*stage-1]
                    self.assertEqual(q['internal_pair_construction']['verification']['status'],'clear')
                    self.assertIsNone(validate_axial_pair(p,r,q['z1'],q['z2']))
                    for fraction in (0,.031,.18,.43,.5,.57,.91,1):
                        z=p.width*fraction; h=(p.width-p.gap)/2
                        axial=min(z,p.width-z,h) if p.double else z
                        self.assertAlmostEqual(r.twist*axial/r.width,q['z1']/q['z2']*p.twist*axial/p.width)
                    for z,_,outer in profile_sections(r):
                        self.assertTrue(all(math.hypot(*a)>=math.hypot(*b)-1e-9 for a,b in zip(section_holes(r,z,outer)[0],r.holes[0])))
                    p.twist+=1
                    self.assertIn('phases',validate_axial_pair(p,r,q['z1'],q['z2']))

    def test_deformed_axial_core_does_not_pass_vertex_radius_shortcut(self):
        d=generate('planetary',dict(variant='double'))
        planet=next(q for q in d.parts if q.name=='S1_Planet_1')
        ring=next(q for q in d.parts if q.name=='S1_Ring')
        malformed=transformed(planet.outer,angle=.1)
        original=profile_sections
        with patch('geometry.profile_sections',side_effect=lambda p:[(0,0,p.outer),(p.width/2,0,malformed)] if p is planet else original(p)):
            self.assertIn('core',validate_axial_pair(planet,ring,18,54))

    def test_unresolved_stage_and_legacy_parameters_remain_visible(self):
        original=plan_planetary_internal_pair
        def bad_second(zp,zr,*args,**kwargs):
            p=original(zp,zr,*args,**kwargs)
            if zp==24:p['verification'].update(status='unresolved',failure_reason='test second-stage budget',certified_separation_lower_bound_mm=None)
            return p
        with patch('internal_mesh.plan_planetary_internal_pair',side_effect=bad_second):
            d=generate('planetary',dict(variant='two_stage',sun2=24,planet2=24))
        self.assertEqual(d.analysis['meshes'][1]['internal_pair_construction']['verification']['status'],'clear')
        self.assertIn('second-stage budget',d.analysis['meshes'][3]['warnings'][0])
        d=generate('planetary',dict(backlash=0,input_rpm=123.456))
        self.assertTrue(any('clearance unresolved' in n for n in d.notes))
        supplied=json.loads(json.dumps(d.values));again=generate('planetary',supplied)
        self.assertEqual(again.values,supplied)
        self.assertEqual((again.values['sun'],again.values['planet'],again.values['input_rpm']),(18,18,123.456))
        fixed=generate('internal');self.assertNotIn('construction_version',fixed.parts[1].profile_metadata.get('tooth_profile',{}))
        self.assertTrue(any('pinion-cutter' in n for n in fixed.notes))
        self.assertTrue(any('Internal involute interference' in n for n in mesh(18,54,2,internal=True,strict=False)['warnings']))

    def test_operational_budget_keeps_small_backlash_visibly_unresolved(self):
        d=generate('planetary',dict(backlash=.01))
        q=d.analysis['meshes'][1];check=q['internal_pair_construction']['verification']
        self.assertEqual(check['status'],'unresolved')
        self.assertEqual(check['budget'],1024)
        self.assertLessEqual(check['evaluated_intervals'],1024)
        self.assertTrue(any('budget exhausted' in warning for warning in q['warnings']))

    def test_cache_detached_and_operating_data_not_geometry_key(self):
        _plan.cache_clear();a=generate('planetary');misses=_plan.cache_info().misses
        b=generate('planetary',dict(input_rpm=30,width=14,input_torque=4))
        self.assertEqual(_plan.cache_info().misses,misses)
        p=plan_planetary_internal_pair(18,54,2);p['verification']['status']='bad'
        self.assertEqual(plan_planetary_internal_pair(18,54,2)['verification']['status'],'clear')
        self.assertEqual(a.analysis['meshes'][1]['contact_transverse'],b.analysis['meshes'][1]['contact_transverse'])
        with self.assertRaisesRegex(ValueError,'construction inputs'):
            mesh(24,72,2,internal=True,backlash=.15,internal_plan=plan_planetary_internal_pair(18,54,2))


class PolygonVerificationTests(unittest.TestCase):
    def test_segment_crossing_in_concavity_and_containment(self):
        ring=[(-3,-3),(3,-3),(3,3),(1,3),(1,-1),(-1,-1),(-1,3),(-3,3)]
        bridge=[(-2,1),(2,1),(2,2),(-2,2)]
        self.assertEqual(polygon_pose_clearance(bridge,ring)[0],'collision')
        self.assertEqual(polygon_pose_clearance(transformed(square(.1),(10,0)),square(3))[0],'collision')
        self.assertEqual(polygon_pose_clearance(square(.1),square(3))[0],'clear')

    def test_intermediate_collision_missed_by_endpoints(self):
        planet=square(.1);ring=[(-3,-1),(3,-1),(3,1),(-3,1)]
        for phase in (0,math.pi,2*math.pi):
            self.assertEqual(polygon_pose_clearance(transformed(planet,(2*math.cos(phase),2*math.sin(phase))),ring)[0],'clear')
        check=verify_internal_polygon_pair(planet,ring,0,0,1,1,2)
        self.assertEqual(check['status'],'collision')
        self.assertIn('witness',check)

    def test_touch_tiny_backlash_budget_and_depth_never_clear(self):
        for kwargs in (dict(budget=0),dict(max_depth=0),dict(backlash_mm=0),dict(backlash_mm=1e-10)):
            check=verify_internal_polygon_pair(square(.1),square(5),0,0,1,1,2,**kwargs)
            self.assertEqual(check['status'],'unresolved')
            self.assertIsNone(check['certified_separation_lower_bound_mm'])
        self.assertEqual(verify_internal_polygon_pair(square(1),square(1),0,0,1,1)['status'],'unresolved')
        for kwargs in (dict(zp=0),dict(zr=0),dict(phaseP=float('nan')),dict(max_depth=-1),dict(budget=float('inf')),dict(budget=4097)):
            args=dict(phaseP=0,phaseR=0,zp=1,zr=1);args.update(kwargs)
            with self.assertRaises(ValueError):verify_internal_polygon_pair(square(.1),square(3),**args)

    def test_motion_bound_and_full_period_both_directions(self):
        clear=verify_internal_polygon_pair(square(.1),square(10),0,0,1,1,2,max_depth=0)
        self.assertEqual(clear['status'],'clear')
        self.assertGreater(clear['certified_separation_lower_bound_mm'],0)
        for angle in (0,-.37,2*math.pi):
            check=verify_internal_polygon_pair(square(.1),square(5),angle,angle,1,1,2)
            self.assertEqual(check['status'],'clear')
            self.assertEqual(check['phase_period_rad'],2*math.pi)
        self.assertEqual(verify_internal_polygon_pair(square(.1),square(5),0,0,1,1,2,max_depth=0)['status'],'unresolved')


if __name__=='__main__':unittest.main()
