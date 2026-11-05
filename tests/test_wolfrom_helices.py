# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Normal-system dimensions, full axial mesh phases and shared export surfaces."""
from copy import deepcopy
from math import cos, sin, tan, radians, pi, remainder, hypot
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from geometry import generate, get_specs, profile_sections, VARIANTS
from internal_mesh import validate_axial_pair
from motion import build_plan, update_operating_rates
import cad_export
import stl_export


CASES = ({'variant':'helical'},
         {'variant':'double','double_style':'joined'},
         {'variant':'double','double_style':'separated','gap':1.25})


def section_angle(part, z):
    sections = profile_sections(part)
    for a, b in zip(sections, sections[1:]):
        if a[0]-1e-12 <= z <= b[0]+1e-12:
            return radians(a[1]+(b[1]-a[1])*(z-a[0])/(b[0]-a[0]))
    raise AssertionError(z)


class WolfromHelixTests(unittest.TestCase):
    def test_normal_dimensions_contact_overlap_and_both_hands(self):
        # Independently evaluated normal-system 18/72/162 and 59/135 benchmark.
        for options in CASES:
            for beta in (20, -20, 0, 35):
                with self.subTest(options=options,beta=beta):
                    d = generate('wolfrom',dict(options,helix=beta,width2=8))
                    v, q = d.values, d.analysis['wolfrom']
                    a = 22.5/cos(radians(beta))
                    self.assertAlmostEqual(q['center_distance_mm'],a,places=12)
                    self.assertAlmostEqual(q['module2_mm'],45/76,places=14)
                    self.assertEqual(q['fixed_ring_teeth'],162)
                    self.assertEqual(d.analysis['signed_ratio'],600)
                    self.assertAlmostEqual(hypot(*d.parts[3].center),a,places=12)
                    for pair, width, module in zip(d.analysis['meshes'],(6,6,8),(.5,.5,45/76)):
                        self.assertAlmostEqual(pair['center_distance_mm'],a,places=12)
                        active = (width-v['gap'])/2 if v['variant']=='double' else width
                        self.assertAlmostEqual(pair['contact_overlap'],active*abs(sin(radians(beta)))/(pi*module))
                        self.assertGreaterEqual(pair['profile_contact_total'],1)
                    self.assertEqual([p['verification']['status'] for p in q['internal_pair_plans']],['clear','clear'])
                    self.assertEqual(d.parts[0].double,v['variant']=='double')
                    self.assertAlmostEqual(d.parts[0].twist,6*tan(radians(beta))/(.5*18/(2*cos(radians(beta))))*180/pi)
                    for part in d.parts[1:]:
                        if 'tooth_profile' in part.profile_metadata:
                            self.assertLessEqual(part.twist*beta,0)

    def test_three_mesh_congruences_at_every_axial_station_and_moving_phase(self):
        for options in CASES:
            for beta in (-23, 20):
                d = generate('wolfrom',dict(options,helix=beta,width2=8))
                sun, fixed, output = d.parts[:3]
                q = d.analysis['wolfrom']['assembly']
                r = d.analysis['kinematics']['rates_rpm']
                for item in q['compounds']:
                    p1 = next(p for p in d.parts if p.name==f"Compound_{item['index']}_rim1")
                    p2 = next(p for p in d.parts if p.name==f"Compound_{item['index']}_rim2")
                    for planet, ring, zp, zr in ((p1,fixed,72,162),(p2,output,59,135)):
                        self.assertIsNone(validate_axial_pair(planet,ring,zp,zr))
                        levels = {z for part in (planet,ring) for z,_,_ in profile_sections(part)}
                        for z in levels:
                            self.assertAlmostEqual(zp*section_angle(planet,z)-zr*section_angle(ring,z),0,places=11)
                    # Construction datums plus the actual emitted section sweep.
                    levels = {z for part in (sun,p1,fixed) for z,_,_ in profile_sections(part)}
                    for z in levels:
                        for t in (-.37,0,.51):
                            theta = item['theta_rad']+r['carrier']*t
                            ps = r['sun']*t+section_angle(sun,z)
                            pp = item['planet_phase_rad']+r['planet']*t+section_angle(p1,z)
                            pf = q['fixed_ring_phase_rad']+section_angle(fixed,z)
                            for residual in (18*ps+72*pp-90*theta-73*pi,
                                             72*pp-162*pf+90*theta-pi):
                                self.assertAlmostEqual(remainder(residual,2*pi),0,places=9)
                    for z,_,_ in profile_sections(p2):
                        for t in (-.37,0,.51):
                            theta = item['theta_rad']+r['carrier']*t
                            pp = item['planet2_phase_rad']+r['planet']*t+section_angle(p2,z)
                            po = q['output_ring_phase_rad']+r['output']*t+section_angle(output,z)
                            self.assertAlmostEqual(remainder(59*pp-135*po+76*theta-pi,2*pi),0,places=9)
                    self.assertAlmostEqual(p2.profile_metadata['wolfrom']['body_phase_rad']-p1.profile_metadata['wolfrom']['body_phase_rad'],q['common_clocking_rad'])

    def test_variants_roundtrip_rates_and_actual_solid_exports(self):
        self.assertEqual(list(VARIANTS['wolfrom']),['spur','helical','double'])
        self.assertNotIn('helix',{s[0] for s in get_specs('wolfrom','spur')})
        self.assertNotIn('gap',{s[0] for s in get_specs('wolfrom','double','joined')})
        for options in CASES:
            d = generate('wolfrom',options)
            from solid_geometry import signature
            for part in d.parts:
                self.assertGreater(signature(part)['volume_mm3'],0)
            restored = generate('wolfrom',json.loads(json.dumps(d.values)))
            self.assertEqual(restored.parts,d.parts)
            original = deepcopy(d.values)
            for rpm in (-600,0,600):
                plan = build_plan(d)
                before = [plan.matrix(i,.123) for i in range(len(d.parts))]
                changed = update_operating_rates(d,dict(d.values,input_rpm=rpm))
                changed_plan = build_plan(changed,plan,.123)
                self.assertEqual(changed.analysis['kinematics']['rates_rpm']['output'],rpm/600)
                for old, new in zip(before,[changed_plan.matrix(i,.123) for i in range(len(d.parts))]):
                    for a,b in zip(old,new):self.assertAlmostEqual(a,b,places=11)
                self.assertIs(changed.parts[0].outer,d.parts[0].outer)
            self.assertEqual(original,d.values)
            # Exercise external and internal teeth, including the real groove void.
            subset = deepcopy(d); subset.parts = subset.parts[:2]
            with TemporaryDirectory() as temporary:
                path = Path(temporary)
                cad_export.write_files(subset,path)
                self.assertIn('END-ISO-10303-21;', (path/'assembly.step').read_text())
                for part in subset.parts:
                    triangles = list(stl_export.triangles(part))
                    self.assertGreater(len(triangles),100)
                    self.assertTrue(all(len(t)==3 for t in triangles))

    def test_invalid_helix_groove_and_axial_law_rejected(self):
        for options in ({'variant':'helical','helix':36},
                        {'variant':'double','gap':5},
                        {'variant':'double','gap':4,'width2':4},
                        {'variant':'double','double_style':'separated','gap':0},
                        {'variant':'double','double_style':'invalid'}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                generate('wolfrom',options)
        d = generate('wolfrom',{'variant':'helical'})
        planet, ring = d.parts[3], deepcopy(d.parts[1])
        ring.twist *= -1
        self.assertIn('phases',validate_axial_pair(planet,ring,72,162))


if __name__ == '__main__':
    unittest.main()
