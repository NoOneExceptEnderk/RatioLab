# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
import unittest, json
from itertools import product
from geometry import generate, VARIANTS
from kinematics import options, coefficients, solve
from bom import build, as_text

class KinematicTests(unittest.TestCase):

    def test_six_schemes_satisfy_equation_and_inverse(self):
        for family in ('planetary', 'cycloidal', 'harmonic'):
            opts = options(family)
            self.assertEqual(len(opts), 6)
            for scheme in opts:
                with self.subTest(family=family, scheme=scheme):
                    d = generate(family, {'io_scheme': scheme, 'input_rpm': 1200})
                    q = d.analysis['kinematics']['stage_results'][0]
                    self.assertAlmostEqual(sum((q['coefficients'][m] * q['rates_rpm'][m] for m in q['coefficients'])), 0, places=7)
                    a, b, c = scheme.split('_')
                    reverse = generate(family, {'io_scheme': '_'.join((b, a, c))})
                    self.assertAlmostEqual(d.analysis['signed_ratio'] * reverse.analysis['signed_ratio'], 1)
                    self.assertEqual(q['rates_rpm'][c], 0)
                    self.assertTrue(any((p.port for p in d.parts)))

    def test_independent_planetary_stages_all_variants(self):
        for variant in VARIANTS['planetary']:
            for scheme in options('planetary'):
                d = generate('planetary', {'variant': variant, 'io_scheme': scheme, 'io_scheme2': 'ring_sun_carrier'})
                stages = d.analysis['kinematics']['stage_results']
                expected = 1
                for q in stages:
                    expected *= q['signed_ratio']
                self.assertAlmostEqual(d.analysis['signed_ratio'], expected)
                if 'two_stage' in variant:
                    self.assertEqual(len(stages), 2)
                    self.assertAlmostEqual(stages[1]['rates_rpm'][stages[1]['input']], stages[0]['rates_rpm'][stages[0]['output']])
                self.assertEqual(d.values['variant'], variant)

    def test_alternate_planetary_releases_ring(self):
        d = generate('planetary', {'io_scheme': 'ring_carrier_sun'})
        self.assertFalse(any((any((k in p.name for k in ('TieRod_ring', 'Retainer_ring', 'Shaft_input', 'Coupling_interstage'))) for p in d.parts)))
        ring = next((p for p in d.parts if p.name == 'S1_Ring'))
        self.assertTrue(ring.stations)
        self.assertEqual(ring.port['role'], 'input')
        self.assertEqual(len(ring.holes), 1)
        self.assertTrue(any((p.name == 'S1_Attachment_ring_Hub' and p.holes for p in d.parts)))

    def test_cycloidal_industrial_known_cases(self):
        for variant in ('single', 'dual'):
            self.assertEqual(generate('cycloidal', {'variant': variant}).analysis['signed_ratio'], -15)
            self.assertEqual(generate('cycloidal', {'variant': variant, 'io_scheme': 'eccentric_ring_output'}).analysis['signed_ratio'], 16)
            self.assertAlmostEqual(generate('cycloidal', {'variant': variant, 'io_scheme': 'output_ring_eccentric'}).analysis['signed_ratio'], 16 / 15)

    def test_harmonic_legacy_and_priority(self):
        a = generate('harmonic', {'harmonic_output': 'circular'})
        self.assertEqual(a.values['io_scheme'], 'wave_circular_flex')
        self.assertEqual(a.analysis['signed_ratio'], 31)
        b = generate('harmonic', {'harmonic_output': 'circular', 'io_scheme': 'wave_flex_circular'})
        self.assertEqual(b.analysis['signed_ratio'], -30)

    def test_reverse_pairs_and_no_stale_forces(self):
        for family in ('parallel', 'internal', 'worm'):
            a = generate(family)
            b = generate(family, {'io_scheme': 'reverse'})
            self.assertAlmostEqual(a.analysis['signed_ratio'] * b.analysis['signed_ratio'], 1)
            self.assertTrue(any((p.port.get('role') == 'input' for p in b.parts)))
            self.assertTrue(any((p.port.get('role') == 'output' for p in b.parts)))
            for q in b.analysis.get('meshes', []):
                self.assertNotIn('forces', q)
        self.assertTrue(any(('backdrivability' in n for n in generate('worm', {'io_scheme': 'reverse'}).notes)))

    def test_roundtrip_bom_and_ports(self):
        d = generate('planetary', {'variant': 'two_stage_double', 'io_scheme': 'sun_ring_carrier', 'io_scheme2': 'carrier_sun_ring'})
        restored = generate(d.family, json.loads(json.dumps(d.values)))
        self.assertEqual(restored.values, d.values)
        b = build(d)
        self.assertTrue(b['ports'])
        self.assertIn('INPUTS / OUTPUTS', as_text(b))
        self.assertEqual(b['analysis']['kinematics'], d.analysis['kinematics'])
        self.assertTrue(any((c['params'].get('values', {}).get('local.solidcraft.kinematic_port') for c in d.commands())))
        self.assertTrue(any((c['params'].get('properties', {}).get('Kinematic role') == 'Fixed' for c in d.commands())))

    def test_unknown_schemes_rejected(self):
        with self.assertRaises(ValueError):
            generate('planetary', {'io_scheme': 'ring_carrier_sun', 'hardware_mode': 'standard'})
        d = generate('planetary', {'bearing_mode': 'shaft', 'io_scheme2': 'ring_sun_carrier'})
        self.assertNotIn('io_scheme2', d.values)
        for family, values in [('planetary', {'io_scheme': 'foo'}), ('planetary', {'variant': 'two_stage', 'io_scheme2': 'foo'}), ('spur', {'io_scheme': 'forward'}), ('harmonic', {'harmonic_output': 'foo'})]:
            with self.subTest(family=family), self.assertRaises(ValueError):
                generate(family, values)
if __name__ == '__main__':
    unittest.main()
