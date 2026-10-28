# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Regressioni per adattatori fisici, ruoli e collegamenti fra stadi."""
import unittest, json
from math import hypot
from geometry import generate, VARIANTS
from kinematics import TRIPLES, PAIRS, options, default
from solid_geometry import signature
from bom import part_info, build

class MountingTests(unittest.TestCase):

    def test_three_member_alternatives_have_connected_closed_interfaces(self):
        for f in TRIPLES:
            for scheme in options(f):
                if scheme == default(f):
                    continue
                with self.subTest(family=f, scheme=scheme):
                    d = generate(f, {'io_scheme': scheme})
                    records = d.analysis['mount_interfaces']
                    self.assertEqual(len(records), 3)
                    self.assertEqual({r['role'] for r in records}, {'input', 'output', 'fixed'})
                    byname = {p.name: p for p in d.parts}
                    for r in records:
                        self.assertIn(r['anchor'], set(byname))
                        for n in r['parts']:
                            p = byname[n]
                            self.assertGreater(signature(p)['volume_mm3'], 0)
                            self.assertEqual(p.port['role'], r['role'])
                            self.assertEqual(p.port['rpm'], d.analysis['kinematics']['stage_results'][0]['rates_rpm'][r['member']])
                        if r['role'] == 'fixed':
                            self.assertEqual(byname[r['parts'][-1]].port['rpm'], 0)

    def test_swap_changes_real_mounting_patterns_and_bom(self):
        a = generate('planetary', {'io_scheme': 'ring_carrier_sun'})
        b = generate('planetary', {'io_scheme': 'carrier_ring_sun'})
        for member in ('ring', 'carrier'):
            pa = next((p for p in a.parts if p.name == f'S1_Attachment_{member}_Flange'))
            pb = next((p for p in b.parts if p.name == pa.name))
            self.assertNotEqual(len(pa.holes), len(pb.holes))
            self.assertNotEqual(part_info(pa)['code'], part_info(pb)['code'])
        self.assertFalse(any(('Retainer_ring' in p.name or 'TieRod_ring' in p.name for p in a.parts)))

    def test_all_planetary_interstage_connections(self):
        for s1 in options('planetary'):
            for s2 in options('planetary'):
                if s1 == s2 == default('planetary'):
                    continue
                d = generate('planetary', {'variant': 'two_stage_double', 'io_scheme': s1, 'io_scheme2': s2})
                link = d.analysis['interstage_mounting']
                self.assertEqual(link['from_member'], s1.split('_')[1])
                self.assertEqual(link['to_member'], s2.split('_')[0])
                bridge = next((p for p in d.parts if p.name == link['bridge']))
                self.assertGreater(signature(bridge)['volume_mm3'], 0)
                q1, q2 = d.analysis['kinematics']['stage_results']
                self.assertAlmostEqual(bridge.port['rpm'], q2['rates_rpm'][q2['input']])
                gears1 = [p for p in d.parts if p.role == 'gear' and p.name.startswith('S1_')]
                gears2 = [p for p in d.parts if p.role == 'gear' and p.name.startswith('S2_')]
                self.assertGreater(bridge.z, max((p.z + p.width for p in gears1)))
                self.assertLess(bridge.z + bridge.width, min((p.z for p in gears2)))

    def test_reverse_axes_and_differential_ports(self):
        for f in [f for f in PAIRS if f not in TRIPLES] + []:
            scheme = next((s for s in options(f) if s != default(f)))
            d = generate(f, {'io_scheme': scheme})
            records = d.analysis['mount_interfaces']
            self.assertTrue(records)
            self.assertEqual({r['role'] for r in records}, {'input', 'output'})
            names = {p.name for p in d.parts}
            for r in records:
                self.assertIn(r['anchor'], names)
                for name in r['parts']:
                    self.assertGreater(signature(next((p for p in d.parts if p.name == name)))['volume_mm3'], 0)
            cfg = json.loads(json.dumps(d.values))
            self.assertEqual(generate(f, cfg).analysis['mount_interfaces'], records)
        d = generate('worm', {'io_scheme': 'reverse'})
        a = next((r for r in d.analysis['mount_interfaces'] if r['member'] == 'A'))
        b = next((r for r in d.analysis['mount_interfaces'] if r['member'] == 'B'))
        self.assertEqual(a['axis'], (1, 0, 0))
        self.assertEqual(b['axis'], (0, 0, 1))

    def test_harmonic_flex_attachment_is_at_base(self):
        for variant in VARIANTS['harmonic']:
            d = generate('harmonic', {'variant': variant, 'io_scheme': 'flex_circular_wave'})
            flex = d.parts[0]
            a = next((r for r in d.analysis['mount_interfaces'] if r['member'] == 'flex'))
            self.assertEqual(a['contact_z_mm'], flex.z)
            self.assertLess(a['terminal_z_mm'], flex.z)

    def test_cycloidal_catalog_not_reused_for_moving_housing(self):
        with self.assertRaises(ValueError):
            generate('cycloidal', {'io_scheme': 'ring_output_eccentric', 'bearing_mode': 'shaft'})
if __name__ == '__main__':
    unittest.main()
