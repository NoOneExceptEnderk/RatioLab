# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Thickness benchmarks and checks against the constructed flank endpoints."""
import json
import math
import tempfile
import unittest
from pathlib import Path

from bom import export
from engineering import gear_dimensions, mesh, report_text
from geometry import generate, sample_curve
from tooth_profiles import external_half, internal_half


class ToothThicknessTests(unittest.TestCase):
    @staticmethod
    def thickness(z, m, x=0, backlash=.15):
        return external_half(z, m, 20, backlash, m, x, 20, 1, 1.25, sample_curve)[1]['tooth_thickness']

    def test_reference_benchmark_preserves_nominal_compatibility(self):
        g = gear_dimensions(24, 2, backlash=.15)
        t = self.thickness(24, 2)
        self.assertAlmostEqual(g['normal_thickness'], 3.141592653589793)
        self.assertAlmostEqual(g['reference_normal_thickness_with_allowance_mm'], 3.066592653589793)
        self.assertAlmostEqual(t['reference']['nominal_transverse_arc_mm'], math.pi)
        self.assertAlmostEqual(t['reference']['generated_transverse_arc_mm'], 3.066592653589793)
        self.assertAlmostEqual(t['per_gear_reference_reduction_transverse_mm'], .075)
        self.assertAlmostEqual(t['pair_backlash_transverse_mm'], .15)
        # Regression value; the endpoint geometry is compared separately below.
        self.assertAlmostEqual(t['tip']['generated_transverse_chord_mm'], 1.3496992720611687)
        for location in ('reference', 'tip'):
            q = self.thickness(24, 2, backlash=0)[location]
            self.assertAlmostEqual(q['nominal_transverse_arc_mm'], q['generated_transverse_arc_mm'])

    def test_tip_chords_match_flank_endpoints_external_internal_both_hands(self):
        for internal, z in ((False, 24), (True, 72)):
            for beta in (0, -30, 30):
                with self.subTest(internal=internal, beta=beta):
                    mn = 2
                    mt = mn / math.cos(math.radians(beta))
                    at = math.degrees(math.atan(math.tan(math.radians(20)) * mt / mn))
                    if internal:
                        flank, p = internal_half(z, mt, at, .15, mn, 1, 1.25, sample_curve)
                        tip_point = flank[0]
                    else:
                        flank, p = external_half(z, mt, at, .15, mn, .3, 20, 1, 1.25, sample_curve)
                        tip_point = flank[-1]
                    t = p['tooth_thickness']
                    tip = t['tip']
                    self.assertAlmostEqual(tip['generated_transverse_chord_mm'], 2 * tip_point[1])
                    self.assertAlmostEqual(tip['generated_transverse_arc_mm'], 2 * math.hypot(*tip_point) * math.atan2(tip_point[1], tip_point[0]))
                    # The local tip helix differs from the reference helix.
                    rp = mt * z / 2
                    beta_tip = math.atan(math.hypot(*tip_point) / rp * math.tan(math.radians(beta)))
                    self.assertAlmostEqual(tip['generated_normal_arc_mm'], tip['generated_transverse_arc_mm'] * math.cos(beta_tip))
                    self.assertAlmostEqual(t['reference']['generated_normal_arc_mm'], t['reference']['nominal_normal_arc_mm'] - .075 * math.cos(math.radians(beta)))

    def test_internal_dimensions_and_flank_sign_are_distinct(self):
        q = mesh(24, 72, 2, internal=True, backlash=.15)
        g = q['gear2']
        self.assertTrue(g['internal'])
        self.assertEqual(g['tip_radius'], 70)
        self.assertEqual(g['root_radius'], 74.5)
        t = g['tooth_thickness']
        self.assertTrue(t['internal'])
        self.assertLess(t['tip']['generated_transverse_arc_mm'], t['reference']['generated_transverse_arc_mm'])

    def test_trimmed_reference_and_very_thin_tip_are_geometric_results(self):
        # A three-tooth rack envelope has no usable involute at reference R.
        q = self.thickness(3, 2)['reference']
        self.assertFalse(q['on_usable_involute'])
        self.assertIsNone(q['generated_transverse_arc_mm'])
        # A positive, extremely thin tip remains quantified, not strength rated.
        t = self.thickness(8, 2, x=.5)
        self.assertAlmostEqual(t['tip']['generated_transverse_chord_mm'], .048756675296995955)
        self.assertAlmostEqual(t['tip_chord_over_normal_module'], .024378337648497978)
        with self.assertRaisesRegex(ValueError, 'Pointed or overlapping'):
            self.thickness(8, 2, x=1)
        a = self.thickness(24, 2)
        b = self.thickness(24, 6, backlash=.45)
        self.assertAlmostEqual(a['tip_chord_over_normal_module'], b['tip_chord_over_normal_module'])
        self.assertAlmostEqual(3*a['tip']['generated_transverse_chord_mm'], b['tip']['generated_transverse_chord_mm'])

    def test_report_and_export_expose_nominal_and_constructed_results(self):
        d = generate('spur', {'teeth': 24, 'module': 2, 'backlash': .15})
        text = report_text(d)
        self.assertIn('nominal transverse arc 3.141593 mm', text)
        self.assertIn('Generated transverse arc 3.066593 mm', text)
        self.assertIn('no minimum safe thickness or structural capacity calculated', text)
        self.assertTrue(any('tip chord' in m for m in d.metrics))
        with tempfile.TemporaryDirectory() as folder:
            stem = Path(folder) / 'thickness'
            export(d, stem)
            analysis = json.loads(stem.with_suffix('.calculations.json').read_text())
            self.assertAlmostEqual(analysis['tooth_profiles'][0]['tooth_thickness']['reference']['generated_normal_arc_mm'], math.pi-.075)
            self.assertIn('Generated transverse arc 3.066593 mm', stem.with_suffix('.calculations.txt').read_text())

    def test_special_families_have_no_cylindrical_thickness_results(self):
        for family in ('worm', 'harmonic', 'cycloidal', 'differential'):
            with self.subTest(family=family):
                d = generate(family)
                self.assertFalse(any('reference tooth arc' in m or 'tip chord' in m for m in d.metrics))
                self.assertNotIn('Tip transverse chord / normal module:', report_text(d))


if __name__ == '__main__':
    unittest.main()
