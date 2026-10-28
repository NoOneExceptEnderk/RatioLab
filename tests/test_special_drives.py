# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Verifiche delle costruzioni a doppia elica, ZA/ZI e involucri strain wave."""
import math, unittest
from geometry import *
from special_drives import za_profile, ellipse_axes
from solid_geometry import signature
from bom import part_info
from test_geometry import distance

class SpecialDrivesTests(unittest.TestCase):

    def test_double_styles_and_configuration_migration(self):
        self.assertEqual(generate('double').values['variant'], 'joined')
        self.assertEqual(generate('double', {'gap': 0}).values['variant'], 'joined')
        self.assertEqual(generate('double', {'gap': 1}).values['variant'], 'separated')
        for f, var in [('double', 'joined'), ('planetary', 'double'), ('parallel', 'double'), ('internal', 'double')]:
            d = generate(f, dict(variant=var, double_style='joined'))
            self.assertEqual(d.values['gap'], 0)
            for p in d.parts:
                if p.double:
                    self.assertGreater(signature(p)['volume_mm3'], 0)
            separated = generate(f, dict(variant='separated' if f == 'double' else var, double_style='separated', gap=1))
            self.assertEqual(separated.values['gap'], 1)
        with self.assertRaises(ValueError):
            generate('double', {'variant': 'separated', 'gap': 0})

    def test_joined_midsection_is_toothed_and_separated_has_recess(self):
        for style in ('joined', 'separated'):
            p = generate('double', {'variant': style}).parts[0]
            sections = profile_sections(p)
            near = min(sections, key=lambda s: abs(s[0] - p.width / 2))
            span = max((hypot(*q) for q in near[2])) - min((hypot(*q) for q in near[2]))
            self.assertGreater(span, 1) if style == 'joined' else self.assertLess(span, 0.01)

    def test_za_axial_straight_flanks_and_tooth_thickness(self):
        m = 2
        starts = 2
        k = m * starts / 2
        rp = 10
        alpha = 20
        j = 0.15
        profile = za_profile(starts, m, 20, alpha, j)
        half = lambda r: pi / (2 * starts) - (r - rp) * tan(radians(alpha)) / k - j / (4 * k)
        for r in (8, 9, 10, 11, 12):
            self.assertLess(distance(polar(r, half(r)), profile), 0.016)
        thickness = 2 * k * half(rp)
        self.assertAlmostEqual(thickness, pi * m / 2 - j / 2)
        x1 = -k * half(9)
        x2 = -k * half(11)
        self.assertAlmostEqual((x2 - x1) / 2, tan(radians(alpha)))

    def test_worm_hands_journals_distinct_profiles_and_detail_limit(self):
        za = generate('worm', {'variant': 'za'})
        zi = generate('worm', {'variant': 'zi'})
        self.assertNotEqual(za.parts[0].outer, zi.parts[0].outer)
        self.assertNotEqual(part_info(za.parts[0])['code'], part_info(zi.parts[0])['code'])
        for variant in ('za', 'zi'):
            p = generate('worm', {'variant': variant, 'length': 12}).parts[0]
            self.assertEqual(p.width, 28)
            self.assertGreater(signature(p)['volume_mm3'], 0)
            left = generate('worm', {'variant': variant, 'length': 12, 'worm_hand': -1}).parts[0]
            self.assertAlmostEqual(signature(p)['volume_mm3'], signature(left)['volume_mm3'], places=6)
            self.assertNotEqual(part_info(p)['code'], part_info(left)['code'])
        long = generate('worm', {'length': 50, 'starts': 2})
        self.assertGreater(long.analysis['thread_turns'], 3)
        with self.assertRaises(ValueError):
            generate('worm', {'length': 80, 'module': 0.1})
        with self.assertRaises(ValueError):
            generate('worm', {'journal_diameter': 16})

    def test_wave_pitch_perimeter_and_continuous_flexspline_variants(self):
        lengths = {}
        for variant in ('cup', 'flat_cup', 'hat'):
            d = generate('harmonic', {'variant': variant})
            p = d.parts[0]
            self.assertTrue(p.stations)
            self.assertGreater(signature(p)['volume_mm3'], 0)
            self.assertEqual(len([q for q in d.parts if q.name.startswith('Flexspline')]), 1)
            a, b = d.analysis['pitch_ellipse_semiaxes_mm']
            perimeter = sum((math.hypot(a * math.sin(TAU * (j + 0.5) / 4096), b * math.cos(TAU * (j + 0.5) / 4096)) for j in range(4096))) * TAU / 4096
            self.assertAlmostEqual(perimeter, d.analysis['reference_pitch_perimeter_mm'], places=7)
            lengths[variant] = p.width
            self.assertTrue(any((q.name == 'Bearing_wave_envelope' for q in d.parts)))
        self.assertLess(lengths['flat_cup'], lengths['cup'])

    def test_harmonic_layout_ratios_clearances_and_bom(self):
        for teeth in (60, 100):
            a = generate('harmonic', {'teeth': teeth})
            b = generate('harmonic', {'teeth': teeth, 'harmonic_output': 'circular'})
            self.assertEqual(a.analysis['signed_ratio'], -teeth / 2)
            self.assertEqual(b.analysis['signed_ratio'], (teeth + 2) / 2)
        d = generate('harmonic')
        flex, ring, bearing, cam = d.parts
        flexinner = flex.stations[-1]['holes'][0]
        for f, q, c in zip(flexinner, bearing.outer, cam.outer):
            self.assertAlmostEqual(hypot(*f) - hypot(*q), d.values['wave_clearance'])
            self.assertAlmostEqual(hypot(*q) - hypot(*c), d.values['bearing_thickness'] + d.values['wave_clearance'])
        a = generate('harmonic', {'variant': 'hat', 'flange_width': 6}).parts[0]
        b = generate('harmonic', {'variant': 'hat', 'flange_width': 20}).parts[0]
        self.assertNotEqual(part_info(a)['code'], part_info(b)['code'])
        self.assertIn('155.000', part_info(b)['dimensions'])
        for values in ({'diaphragm': 10, 'cup_length': 8}, {'bore': 100, 'teeth': 30}, {'harmonic_output': 'invalid'}):
            with self.assertRaises(ValueError):
                generate('harmonic', values)
if __name__ == '__main__':
    unittest.main()
