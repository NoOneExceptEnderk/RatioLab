# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Independent span benchmark, jaw geometry and supported-domain regressions."""
import json
import math
import tempfile
import unittest
from pathlib import Path

from bom import export
from engineering import mesh, report_text
from gear_measurement import wildhaber_span
from geometry import generate
from tooth_profiles import external_half, internal_half


def external(z=24, m=3, x=.4, backlash=0, ha=1, hf=1.25):
    return external_half(z, m, 20, backlash, m, x, 20, ha, hf,
                         lambda fn, a, b: [fn(a), fn(b)])[1]['measurement_geometry']


class WildhaberTests(unittest.TestCase):
    def test_khk_table_5_10_and_allowance_scaling(self):
        # KHK Technical Data section 5.2 Table 5.10: m3,z24,x.4,20deg,k4.
        zero = wildhaber_span(external())
        w4 = next(q['span_mm'] for q in zero['usable_spans'] if q['k'] == 4)
        self.assertAlmostEqual(w4, 32.82662724866363)
        self.assertEqual([q['k'] for q in zero['usable_spans']], [2, 3, 4, 5])
        reduced = wildhaber_span(external(backlash=.15))
        scaled = wildhaber_span(external(m=9, backlash=.45))
        self.assertEqual([q['k'] for q in reduced['usable_spans']], [q['k'] for q in scaled['usable_spans']])
        for a, b, c in zip(zero['usable_spans'], reduced['usable_spans'], scaled['usable_spans']):
            self.assertAlmostEqual(a['span_mm']-b['span_mm'], .075*math.cos(math.radians(20)))
            self.assertAlmostEqual(c['span_mm'], 3*b['span_mm'])
            self.assertAlmostEqual(c['contact_radius_mm'], 3*b['contact_radius_mm'])

    def test_jaws_are_tangent_to_actual_opposing_flanks(self):
        # Reconstruct opposing teeth from the independent involute polar curve;
        # finite differences verify tangent jaw direction, not merely A.9 again.
        for z, x in ((3, 0), (8, .4), (24, .4), (80, -.1)):
            g = external(z=z, x=x, backlash=.15)
            rb, rp = g['base_radius_mm'], g['reference_radius_mm']
            at = math.acos(rb/rp)
            for q in wildhaber_span(g)['usable_spans']:
                k, r = q['k'], q['contact_radius_mm']
                def point(radius, side):
                    a = math.acos(rb/radius)
                    angle = (k-1)*math.pi/z+g['reference_half_angle_rad']+math.tan(at)-at-(math.tan(a)-a)
                    return radius*math.cos(angle), side*radius*math.sin(angle)
                upper, lower = point(r, 1), point(r, -1)
                self.assertAlmostEqual(upper[1]-lower[1], q['span_mm'])
                self.assertAlmostEqual(upper[0], lower[0])
                step = r*1e-5
                self.assertAlmostEqual((point(r+step, 1)[1]-point(r-step, 1)[1])/(2*step), 0, places=7)
                self.assertGreaterEqual(r, g['involute_start_radius_mm']-1e-9)
                self.assertLessEqual(r, g['involute_end_radius_mm']+1e-9)

    def test_enumeration_excludes_fillet_tip_reverse_and_no_integer_solution(self):
        g = external()
        result = wildhaber_span(g)
        valid = [q['k'] for q in result['usable_spans']]
        # Exhaust independently for every possible positive integer k.
        for k in range(1, g['teeth']+1):
            roll = (k-1)*math.pi/g['teeth']+g['reference_half_angle_rad']+math.tan(g['transverse_pressure_angle_rad'])-g['transverse_pressure_angle_rad']
            radius = g['base_radius_mm']*math.sqrt(1+roll**2)
            expected = roll > 0 and g['involute_start_radius_mm'] <= radius <= g['involute_end_radius_mm']
            self.assertEqual(k in valid, expected)
        # A valid short-tooth generated profile may have no integer span.
        no_k = wildhaber_span(external(z=8, m=2, x=0, backlash=.15, ha=.2, hf=.2))
        self.assertTrue(no_k['supported'])
        self.assertEqual(no_k['status'], 'no_usable_span')
        self.assertIsNone(no_k['recommended_k'])
        self.assertEqual(no_k['usable_spans'], [])
        # Negative roll must never be accepted by the squared radius alone.
        g['reference_half_angle_rad'] = -math.tan(g['transverse_pressure_angle_rad'])+g['transverse_pressure_angle_rad']-.05
        self.assertNotIn(1, [q['k'] for q in wildhaber_span(g)['usable_spans']])

    def test_internal_helical_and_special_domains_are_explicit(self):
        invalid = external()
        invalid['helix_angle_abs_deg'] = math.nan
        with self.assertRaisesRegex(ValueError, 'helix angle'):
            wildhaber_span(invalid)
        _, p = internal_half(72, 2, 20, .15, 2, 1, 1.25, lambda fn, a, b: [fn(a), fn(b)])
        self.assertFalse(wildhaber_span(p['measurement_geometry'])['supported'])
        for family in ('helical', 'double'):
            d = generate(family)
            self.assertFalse(d.analysis['gear']['wildhaber_span']['supported'])
            self.assertIn('Helical flat-jaw', report_text(d))
        for family in ('worm', 'harmonic', 'cycloidal', 'differential'):
            d = generate(family)
            self.assertNotIn('Wildhaber', report_text(d))
            self.assertTrue(all('wildhaber_span' not in p for p in d.analysis.get('tooth_profiles', [])))

    def test_real_analysis_report_and_exports_list_each_usable_k(self):
        d = generate('spur', {'module': 3, 'teeth': 24, 'profile_shift': .4, 'backlash': 0})
        span = d.analysis['gear']['wildhaber_span']
        self.assertEqual(span, d.analysis['tooth_profiles'][0]['wildhaber_span'])
        text = report_text(d)
        self.assertIn('k=4: W_k 32.826627 mm', text)
        self.assertIn('choose any usable k', text)
        self.assertTrue(any('Wildhaber W' in m for m in d.metrics))
        for member in ('gear1', 'gear2'):
            self.assertEqual(mesh(24, 36, 2)[member]['wildhaber_span']['status'], 'ok')
        with tempfile.TemporaryDirectory() as directory:
            stem = Path(directory)/'span'
            export(d, stem)
            analysis = json.loads(stem.with_suffix('.calculations.json').read_text())
            self.assertEqual(analysis['tooth_profiles'][0]['wildhaber_span'], span)
            self.assertIn('k=4: W_k 32.826627 mm', stem.with_suffix('.calculations.txt').read_text())


if __name__ == '__main__':
    unittest.main()
