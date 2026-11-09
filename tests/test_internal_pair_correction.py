# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Independent form-domain, conservative sampling and full-cycle regressions."""
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import unittest
from tempfile import TemporaryDirectory

from cylindrical_validation import audit_design, audit_pair
from engineering import mesh
from geometry import generate
from internal_mesh import plan_fixed_internal_pair, validate_axial_pair
from rust_geometry import call
from test_geometry import distance
from test_planetary_internal_contact import contains_independent

ROOT=Path(__file__).resolve().parents[1]


def clipped_trace(loop, radius, outer):
    """Split existing straight edges at a circle without changing their shape.

    Unlike the production verifier this uses a direct line/circle quadratic.
    The selected segments are the literal sampled root trace, not a new fit.
    """
    points=[]
    for p,q in zip(loop,loop[1:]+loop[:1]):
        dx,dy=q[0]-p[0],q[1]-p[1]
        a=dx*dx+dy*dy;b=2*(p[0]*dx+p[1]*dy);c=p[0]*p[0]+p[1]*p[1]-radius*radius
        cuts=[0.]
        discriminant=b*b-4*a*c
        if discriminant>0 and a:
            cuts.extend(t for t in ((-b-math.sqrt(discriminant))/(2*a),(-b+math.sqrt(discriminant))/(2*a)) if 1e-10<t<1-1e-10)
        points.extend((p[0]+t*dx,p[1]+t*dy) for t in sorted(set(cuts)))
    selected=[]
    for i,(p,q) in enumerate(zip(points,points[1:]+points[:1])):
        inside=math.hypot((p[0]+q[0])/2,(p[1]+q[1])/2)<radius
        if inside != outer:selected.append(i)
    return points,selected


class FixedInternalCorrectionTests(unittest.TestCase):
    def test_full_nominal_contact_and_ring_tip_are_preserved(self):
        for zp,zr in ((22,66),(24,72),(30,90)):
            for beta in (0,25,-25):
                plan=plan_fixed_internal_pair(zp,zr,2,beta=beta)
                self.assertTrue(plan['nominal_contact_preserved'])
                self.assertEqual(plan['ring_tip_relief_mm'],0)
                self.assertEqual(plan['ring_addendum_coefficient'],1)
                self.assertAlmostEqual(plan['contact_transverse'],plan['baseline_nominal_contact_transverse'],delta=1e-12)
                self.assertGreaterEqual(plan['contact_transverse'],plan['baseline_usable_contact_transverse'])
                self.assertGreater(plan['pinion_roll_margin_mm'],0)
                self.assertFalse(plan['pinion_profile']['undercut_trimmed'])

    def test_normal_rack_form_diameter_independent_of_cartesian_envelope(self):
        # ISO21771 7.6, Eq128/130, evaluated through the actual normal tip
        # and the helical transverse pressure angle, not a circular replacement.
        for module in (.3,2,7.5):
            for beta in (0,25,-25,60):
                p=plan_fixed_internal_pair(22,66,module,beta=beta)
                tool=p['pinion_profile']['tool'];an=math.radians(20)
                at=math.atan(math.tan(an)/math.cos(math.radians(beta)))
                rp=module*22/(2*math.cos(math.radians(beta)));rb=rp*math.cos(at)
                rho=tool['tip_radius']
                signed_roll=rp*math.sin(at)-(1.25*module-rho*(1-math.sin(an)))/math.sin(at)
                self.assertGreater(signed_roll,0)
                self.assertAlmostEqual(math.hypot(rb,signed_roll),p['pinion_profile']['involute_start_radius_mm'],delta=2e-11)
                if p['pinion_rack_tip_radius_mm'] is not None:
                    lo,hi=p['feasible_nonundercut_normal_rack_radius_interval_mm']
                    self.assertGreater(rho,lo);self.assertLess(rho,hi)

    def test_infeasible_tool_uses_declared_minimal_line_of_action_relief(self):
        # A low-level limiting construction outside the UI's >=12 tooth range.
        p=plan_fixed_internal_pair(10,100,2,alpha_n=27.5)
        self.assertFalse(p['nominal_contact_preserved'])
        self.assertIsNone(p['pinion_rack_tip_radius_mm'])
        self.assertGreater(p['ring_tip_relief_mm'],0)
        old=p['baseline_usable_contact_transverse']
        self.assertGreaterEqual(p['contact_transverse'],.999*old-1e-12)
        at=math.radians(27.5);br=100*math.cos(at)
        radial=math.hypot(br,p['center_distance_mm']*math.sin(at)+p['actual_pinion_roll_min_mm'])
        self.assertAlmostEqual(p['ring_tip_radius_mm'],radial,delta=1e-11)
        self.assertLess(p['ring_tip_radius_mm'],p['center_distance_mm']+p['pinion_profile']['involute_start_radius_mm'])
        report=mesh(10,100,2,pressure=27.5,internal=True,backlash=.15,internal_plan=p)
        self.assertAlmostEqual(float(report['gear2']['analytic_values']['tip_radius_mm']),p['ring_tip_radius_mm'],delta=1e-11)

    def test_zero_backlash_is_not_misreported_as_strict_source_clearance(self):
        q=audit_design(generate('internal',dict(backlash=0)))
        self.assertEqual(q['coverage']['status'],'covered')
        self.assertEqual(q['status'],'unresolved')
        self.assertFalse(q['covered_checks_passed'])
        self.assertEqual(q['neutral_clearance']['status'],'unresolved')
        self.assertNotIn('collision',[r['status'] for r in q['operating_root_clearance']])

    def test_exact_decimal_tool_cache_does_not_collapse_distinct_sources(self):
        results=[]
        for rho in ('0.20000000000000000001','0.20000000000000000002'):
            q=call('cylindrical_dimensions',dict(teeth=22,module='2.00000000000000000001',rack_tip_radius_mm=rho))
            self.assertEqual(q['values']['generating_rack_normal_tip_radius_mm'],rho)
            self.assertEqual(q['values']['pitch_radius_mm'],'22.00000000000000000011')
            self.assertTrue(q['precision']['agreement']);results.append(q['values'])
        self.assertNotEqual(results[0]['generating_rack_normal_tip_radius_mm'],results[1]['generating_rack_normal_tip_radius_mm'])
        for rho in (0,-.1,100):
            with self.assertRaises(ValueError):call('cylindrical_dimensions',dict(teeth=22,module=2,rack_tip_radius_mm=rho))

    def test_corrected_source_curves_clear_both_operating_flanks(self):
        for params in ({},{'pinion':24,'wheel':72},{'pinion':30,'wheel':90},
                       {'variant':'helical','helix':25},{'variant':'helical','helix':-25},
                       {'variant':'double','helix':25,'gap':0},{'variant':'double','helix':-25,'gap':2}):
            d=generate('internal',params);q=audit_design(d)
            self.assertEqual(q['status'],'passed_with_limits',params)
            self.assertTrue(q['covered_checks_passed'])
            self.assertTrue(q['mesh']['nominal_contact_within_usable_involutes'])
            self.assertTrue(all(c['status']=='clear' for c in q['operating_root_clearance']))
            self.assertIn('full loaded tip/flank interference and elastic contact',q['unqualified'])

    def test_literal_sampled_root_traces_clear_for_both_hands_and_sides(self):
        for beta in (0,25,-25):
            d=generate('internal',dict(variant='spur' if beta==0 else 'helical',helix=beta))
            p,r=d.parts[:2];m=d.analysis['meshes'][0];plan=m['internal_pair_construction']
            for member,part,radius in ((1,p,plan['pinion_profile']['involute_start_radius_mm']),
                                       (2,r,plan['ring_join_radius_mm'])):
                loop=p.outer if member==1 else r.holes[0]
                points,indices=clipped_trace(loop,radius,member==2)
                self.assertTrue(indices)
                for side in (-1,1):
                    play=m['working_pair_backlash_mm']/(2*m['gear2']['pitch_radius'])
                    q=call('internal_verify_trace',dict(planet_loop=points if member==1 else p.outer,
                        ring_void=points if member==2 else r.holes[0],segments=indices,root_member=member,
                        zp=m['z1'],zr=m['z2'],phaseP=0,phaseR=side*play,
                        center_distance_mm=m['center_distance_mm'],budget=16384,numeric_guard_mm=1e-8))
                    self.assertEqual(q['status'],'clear',(beta,member,side,q))

    def test_old_independent_intrusion_witness_is_no_longer_pinion_material(self):
        d=generate('internal',dict(pinion=30,wheel=90));p=d.parts[0]
        x,y=87.8732594334011-60,4.908137959274496
        phi=.031088677301148993
        local=(x*math.cos(phi)+y*math.sin(phi),-x*math.sin(phi)+y*math.cos(phi))
        self.assertFalse(contains_independent(local,p.outer))
        # The unpaired reference remains an executable negative control.
        unpaired=audit_pair(30,90,2,internal=True)
        self.assertFalse(unpaired['covered_checks_passed'])

    def test_conservative_root_and_ring_flank_sampling_respects_bounds(self):
        d=generate('internal');p,r=d.parts[:2];plan=d.analysis['meshes'][0]['internal_pair_construction']
        mt=p.profile_metadata['analytic_values']['transverse_module_mm']
        pinion=call('external_half',dict(z=22,mt=mt,depth=2,normal_pressure=20,pressure=20,backlash=.15,
                    rack_tip_radius_mm=plan['pinion_rack_tip_radius_mm'],safe_pair_sampling=True))
        root=pinion['metadata']['sampling_curves'][0];bound=pinion['metadata']['root_chord_bound_mm']
        self.assertGreater(bound,0);self.assertLessEqual(bound,.01)
        for i in range(1,100):
            t=root['start']+(root['end']-root['start'])*i/100
            point=call('curve_point',dict(curve=root,t=t));gap=distance(point,p.outer)
            self.assertLessEqual(gap,bound+1e-10)
            self.assertFalse(contains_independent(point,p.outer) and gap>1e-9)
        meta=call('internal_half',dict(z=66,mt=mt,depth=2,pressure=20,backlash=.15,safe_pair_sampling=True))['metadata']
        flank=meta['sampling_curves'][0];bound=meta['flank_chord_bound_mm']
        self.assertGreater(bound,0);self.assertLessEqual(bound,.01)
        phase=math.pi/66
        for i in range(1,100):
            radius=flank['start']+(flank['end']-flank['start'])*i/100
            q=call('curve_point',dict(curve=flank,t=radius))
            point=(q[0]*math.cos(phase)-q[1]*math.sin(phase),q[0]*math.sin(phase)+q[1]*math.cos(phase))
            gap=distance(point,r.holes[0]);self.assertLessEqual(gap,bound+1e-10)
            self.assertTrue(contains_independent(point,r.holes[0]) or gap<1e-9)

    def test_cache_detached_and_quality_speed_do_not_change_source_construction(self):
        p=plan_fixed_internal_pair(22,66,2);p['pinion_profile']['tool']['tip_radius']=100
        self.assertLess(plan_fixed_internal_pair(22,66,2)['pinion_profile']['tool']['tip_radius'],1)
        a=generate('internal',quality=dict(preview_mm=.1,export_mm=.005))
        b=generate('internal',dict(input_rpm=0),quality=dict(preview_mm=.005,export_mm=.000001))
        self.assertEqual(a.parts[0].outer,b.parts[0].outer);self.assertEqual(a.parts[1].holes,b.parts[1].holes)
        self.assertEqual(a.analysis['meshes'][0]['internal_pair_construction'],b.analysis['meshes'][0]['internal_pair_construction'])

    def test_native_and_wasm_use_the_same_root_construction(self):
        node=os.environ.get('RATIOLAB_NODE') or shutil.which('node')
        if not node:self.skipTest('Node.js required for actual Wasm execution')
        requests=[dict(operation='internal_fixed_plan',parameters=dict(zp=22,zr=66,mn=2,beta=b)) for b in (0,25,-25)]
        native=[call(q['operation'],q['parameters']) for q in requests]
        with TemporaryDirectory() as folder:
            source=Path(folder)/'requests.json';source.write_text(json.dumps(requests))
            run=subprocess.run([node,str(ROOT/'tests/rust_wasm_protocol.mjs'),str(ROOT),str(source)],capture_output=True,text=True,check=True,timeout=60)
            wasm=json.loads(run.stdout)
        for a,b in zip(native,wasm):
            self.assertTrue(b['ok'],b);b=b['result']
            self.assertEqual(a['construction_version'],b['construction_version'])
            self.assertEqual(a['nominal_contact_preserved'],b['nominal_contact_preserved'])
            self.assertAlmostEqual(a['pinion_rack_tip_radius_mm'],b['pinion_rack_tip_radius_mm'],delta=1e-12)
            self.assertAlmostEqual(a['contact_transverse'],b['contact_transverse'],delta=1e-12)


if __name__=='__main__':unittest.main()
