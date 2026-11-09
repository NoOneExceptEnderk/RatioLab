# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Finished tip geometry, independent involute normals, assemblies and targets."""
import json
from math import cos, sin, pi, hypot, isclose, radians, tan, atan
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

from geometry import generate, gear_part, get_specs, validate
from precise_numbers import from_text
from rust_geometry import call
from solid_geometry import signature
from tooth_tips import members, key, parameters

ROOT = Path(__file__).resolve().parents[1]


class ToothTipTests(unittest.TestCase):
    def test_zero_treatments_preserve_native_profile_and_metadata_exactly(self):
        for internal in (False,True):
            args=dict(z=66 if internal else 24,mt=2,internal=internal)
            original=call('involute_profile',args)
            same=call('involute_profile',dict(args,topping_mm=0,semitopping_mm=0,semitopping_angle_deg=65))
            self.assertEqual(original,same)

    def test_topping_has_opposite_radial_signs_and_preserves_roots(self):
        for internal in (False,True):
            a=gear_part('gear',66 if internal else 24,2,20,.15,10,internal=internal)
            b=gear_part('gear',66 if internal else 24,2,20,.15,10,internal=internal,topping_mm=.15)
            ma=a.profile_metadata['tooth_profile'];mb=b.profile_metadata['tooth_profile']
            self.assertAlmostEqual(mb['tip_radius_mm']-ma['tip_radius_mm'],.15 if internal else -.15)
            self.assertAlmostEqual(mb['root_radius_mm'],ma['root_radius_mm'])
            self.assertLess(signature(b)['volume_mm3'],signature(a)['volume_mm3'])

    def test_generated_semitopping_common_normals_and_join_independent_of_sampling(self):
        for internal in (False,True):
            for beta in (0,30,-30):
                cb=cos(radians(beta));rp=(66 if internal else 24)/cb
                at=atan(tan(radians(20))/cb)
                args=dict(z=66 if internal else 24,mt=2/cb,depth=2,pressure=at*180/__import__('math').pi,
                          normal_pressure=20,topping_mm=.1,semitopping_mm=.2,semitopping_angle_deg=50)
                q=call('internal_half' if internal else 'external_half',args)
                curves=q['metadata']['sampling_curves'];semi=curves[0] if internal else curves[-1]
                main=curves[1]
                join=semi['end'] if internal else semi['start']
                point=lambda c,t:call('curve_point',dict(curve=c,t=t))
                self.assertLess(hypot(*(a-b for a,b in zip(point(semi,join),point(main,join)))),1e-10)
                # For an involute, the distance from the origin to every normal
                # is its base radius. Compute normals by finite differences,
                # independently of the constructor's involute-angle formula.
                expected_base=rp*cos(atan(tan(radians(50))/cb))
                for fraction in (.15,.5,.85):
                    t=semi['start']+(semi['end']-semi['start'])*fraction
                    p=point(semi,t);lo=point(semi,t-1e-5);hi=point(semi,t+1e-5)
                    dx,dy=hi[0]-lo[0],hi[1]-lo[1]
                    distance=abs(p[0]*dx+p[1]*dy)/hypot(dx,dy)
                    self.assertAlmostEqual(distance,expected_base,delta=2e-7)
                meta=q['metadata'];self.assertFalse(meta['tooth_thickness']['tip']['on_usable_involute'])
                self.assertGreater(meta['tooth_thickness']['tip']['generated_transverse_chord_mm'],0)

    def test_independent_solid_rack_sweep_generates_the_semitopped_flank(self):
        # Translate/rotate a solid two-slope cutter through 8001 independent
        # poses. Query material membership, without using a meshing equation
        # or the profile constructor's involute expression.
        for beta in (0,30,-30):
            cb=cos(radians(beta));rp=24/cb
            q=call('external_half',dict(z=24,mt=2/cb,depth=2,pressure=atan(tan(radians(20))/cb)*180/pi,
                normal_pressure=20,topping_mm=.1,semitopping_mm=.2,semitopping_angle_deg=50))
            c=q['metadata']['sampling_curves'][-1]
            k1=pi/2+.15*cb/4
            k2=pi/2+rp*cb*(pi/48-c['half'])
            poses=[(-.7+1.4*j/8000) for j in range(8001)]
            rotations=[(cos(t),sin(t),rp*t) for t in poses]
            def penetration(p):
                rotation=pi/2-pi/24
                x=p[0]*cos(rotation)-p[1]*sin(rotation)
                y=p[0]*sin(rotation)+p[1]*cos(rotation)
                best=-1e9
                for cp,sp,feed in rotations:
                    u=(x*cp-y*sp+feed)*cb;v=x*sp+y*cp-rp
                    if v < -2.5:continue
                    u=abs((u+pi)%(2*pi)-pi)
                    best=max(best,max(k1+v*tan(radians(20)),k2+v*tan(radians(50)))-u)
                return best
            for fraction in (.2,.7):
                r=c['start']+(c['end']-c['start'])*fraction
                p=call('curve_point',dict(curve=c,t=r))
                self.assertAlmostEqual(penetration(p),0,delta=3e-5)
                def turn(delta):return [p[0]*cos(delta)-p[1]*sin(delta),p[0]*sin(delta)+p[1]*cos(delta)]
                self.assertLess(penetration(turn(-.00005)),-1e-4)
                self.assertGreater(penetration(turn(.00005)),1e-4)

    def test_member_and_stage_controls_only_change_the_requested_teeth(self):
        cases=[('parallel','spur','pinion'),('parallel','three_stage_helical','wheel2'),
               ('internal','helical','ring'),('planetary','two_stage_double','sun2'),
               ('wolfrom','double','planet2'),('rack','double','pinion')]
        for family,variant,role in cases:
            with self.subTest(family=family,variant=variant,role=role):
                base=generate(family,dict(variant=variant))
                edited=generate(family,dict(base.values,**{key(role,'topping_mm'):.03,key(role,'semitopping_mm'):.05}))
                changed=[b.name for a,b in zip(base.parts,edited.parts) if (a.outer,a.holes,a.stations)!=(b.outer,b.holes,b.stations)]
                self.assertTrue(changed)
                for a,b in zip(base.parts,edited.parts):
                    treatment=b.profile_metadata.get('tooth_profile',{}).get('tip_treatment')
                    if treatment:self.assertIn(b.name,changed)
                    else:self.assertEqual((a.outer,a.holes,a.stations),(b.outer,b.holes,b.stations),b.name)
                self.assertEqual(base.analysis.get('signed_ratio'),edited.analysis.get('signed_ratio'))

    def test_contact_uses_the_remaining_primary_flanks(self):
        for family,role in [('parallel','pinion'),('internal','ring'),('planetary','planet'),('wolfrom','planet2')]:
            base=generate(family)
            modified=generate(family,dict(base.values,**{key(role,'semitopping_mm'):.08}))
            a=base.analysis['meshes'];b=modified.analysis['meshes']
            self.assertTrue(any(y['profile_contact_transverse']<x['profile_contact_transverse']-1e-8 for x,y in zip(a,b)))
            for x,y in zip(a,b):
                self.assertEqual(x['working_pair_backlash_mm'],y['working_pair_backlash_mm'])
                self.assertGreater(y['profile_contact_total'],1)
            if family!='parallel':
                for mesh in b:
                    if mesh['internal'] and ('tip_treatment' in mesh['gear1'] or 'tip_treatment' in mesh['gear2']):
                        self.assertIn('tip-treated',mesh['internal_pair_construction']['verification']['source'])

    def test_intentional_head_restriction_does_not_invent_a_root_warning(self):
        d=generate('parallel',dict(pinion=30,wheel=60,pinion_semitopping_mm=.1))
        q=d.analysis['meshes'][0]
        self.assertFalse(q['nominal_contact_within_usable_involutes'])
        self.assertFalse(any('Non-involute root contact' in w for w in q['warnings']))
        from engineering import report_text
        report=report_text(d)
        self.assertTrue('Generated thickness unavailable' not in report)
        self.assertIn('Finished tip widths include semitopping;',report)

    def test_inactive_stage_drafts_follow_existing_variant_normalization(self):
        v=generate('parallel',dict(variant='three_stage_helical',wheel3_semitopping_mm=.05)).values
        single=generate('parallel',dict(v,variant='helical'))
        self.assertEqual(single.values['variant'],'helical')
        self.assertNotIn('wheel3_semitopping_mm',single.values)

    def test_rack_straight_ramps_height_contact_and_travel(self):
        for variant in ('spur','helical','double'):
            base=generate('rack',dict(variant=variant))
            d=generate('rack',dict(base.values,rack_topping_mm=.12,rack_semitopping_mm=.16,pinion_semitopping_mm=.1))
            q=d.analysis['rack'];r=q['rack_tip_treatment']
            self.assertAlmostEqual(r['finished_tip_height_mm'],1.88)
            self.assertAlmostEqual(r['active_tip_height_mm'],1.72)
            self.assertLess(q['nominal_contact_transverse'],base.analysis['rack']['nominal_contact_transverse'])
            self.assertEqual(q['travel_limits_mm'],base.analysis['rack']['travel_limits_mm'])
            self.assertLess(signature(d.parts[1])['volume_mm3'],signature(base.parts[1])['volume_mm3'])

    def test_invalid_treatments_and_unsupported_families_fail_explicitly(self):
        for patch in [dict(topping_mm=-.1),dict(topping_mm=2),dict(semitopping_mm=2),
                      dict(semitopping_mm=.2,semitopping_angle_deg=19),
                      dict(semitopping_mm=.9,semitopping_angle_deg=80),dict(semitopping_mm=float('nan'))]:
            with self.subTest(patch=patch),self.assertRaises(ValueError):generate('spur',patch)
        for family in ('cycloidal','worm','harmonic','bevel','face','hypoid','differential'):
            with self.subTest(family=family),self.assertRaisesRegex(ValueError,'Unsupported tooth-tip'):
                generate(family,dict(topping_mm=.1))
        with self.assertRaisesRegex(ValueError,'contact ratio'):
            generate('parallel',dict(pinion_topping_mm=1.5,wheel_topping_mm=1.5))

    def test_exact_sources_round_trip_and_analytic_topping_dimension(self):
        d=generate('spur',dict(topping_mm=from_text('0.15000000000000000001'),semitopping_mm=from_text('.20')))
        self.assertEqual(d.parts[0].profile_metadata['analytic_values']['tip_radius_mm'],'25.84999999999999999999')
        reopened=generate('spur',json.loads(json.dumps(d.values)))
        self.assertEqual(d.parts[0].outer,reopened.parts[0].outer)
        self.assertEqual(d.values,reopened.values)
        staged=generate('parallel',dict(variant='two_stage',wheel2_topping_mm=from_text('0.05000000000000000001')))
        wheel=next(p for p in staged.parts if p.name=='S2_Wheel')
        self.assertEqual(wheel.profile_metadata['analytic_values']['tip_radius_mm'],'81.94999999999999999999')

    def test_active_schema_has_independent_controls_for_all_members(self):
        from parameter_help import lookup
        for family,variant in [('spur',None),('parallel','three_stage_double'),('planetary','two_stage'),('internal','double'),('wolfrom','helical'),('rack','spur')]:
            fields={s[0] for s in get_specs(family,variant)}
            for role,_ in members(family,variant):
                for suffix in ('topping_mm','semitopping_mm','semitopping_angle_deg'):
                    name=key(role,suffix);self.assertIn(name,fields)
                    self.assertTrue(lookup(family,name,dict(variant=variant)).meaning)

    def test_native_wasm_profiles_and_rack_constructions_agree(self):
        requests=[dict(operation=op,parameters=args) for op,args in [
            ('involute_profile',dict(z=24,mt=2,topping_mm='.10000000000000000001',semitopping_mm=.2)),
            ('internal_half',dict(z=66,mt=2,topping_mm=.1,semitopping_mm=.2)),
            ('engineering_mesh',dict(z1=20,z2=60,m=2,tooth_tips1=dict(semitopping_mm=.15))),
            ('construction_rack',dict(values=validate('rack',dict(variant='helical',pinion_topping_mm=.1,rack_semitopping_mm=.15))))]]
        native=[call(q['operation'],q['parameters']) for q in requests]
        node=os.environ.get('RATIOLAB_NODE')
        self.assertTrue(node,'Actual Wasm execution is required')
        with TemporaryDirectory() as folder:
            path=Path(folder)/'requests.json';path.write_text(json.dumps(requests))
            result=subprocess.run([node,str(ROOT/'tests/rust_wasm_protocol.mjs'),str(ROOT),str(path)],capture_output=True,text=True,check=True,timeout=90)
        wasm=json.loads(result.stdout)
        def compare(a,b):
            if isinstance(a,float):self.assertTrue(isclose(a,b,abs_tol=1e-8,rel_tol=1e-12),(a,b))
            elif isinstance(a,dict):
                self.assertEqual(set(a),set(b))
                for k in a:compare(a[k],b[k])
            elif isinstance(a,list):
                self.assertEqual(len(a),len(b))
                for x,y in zip(a,b):compare(x,y)
            else:self.assertEqual(a,b)
        for a,b in zip(native,wasm):
            self.assertTrue(b['ok'],b);compare(a,b['result'])


if __name__=='__main__':unittest.main()
