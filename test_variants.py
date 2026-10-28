"""Verifiche dimensionali e cinematiche delle nuove varianti."""
import unittest
from math import pi, hypot, radians, cos, sin
from geometry import *
from test_geometry import inside, distance

class VariantTests(unittest.TestCase):

    def test_every_variant_and_legacy_configs(self):
        for f in VARIANTS:
            for v in VARIANTS[f]:
                with self.subTest(family=f, variant=v):
                    d = generate(f, {'variant': v})
                    self.assertEqual(d.values['variant'], v)
                    if f in ('planetary', 'cycloidal', 'parallel', 'internal'):
                        self.assertTrue(any((p.role == 'support' for p in d.parts)))
                    if f in ('planetary', 'cycloidal'):
                        self.assertTrue(any((p.role == 'housing' for p in d.parts)))
        self.assertEqual(generate('planetary', {'sun': 18}).values['variant'], 'spur')

    def test_two_stage_separation_and_ratio(self):
        d = generate('planetary', {'variant': 'two_stage', 'sun2': 24})
        gears = [p for p in d.parts if p.role == 'gear']
        self.assertEqual(len(gears), 10)
        one = [p for p in gears if p.name.startswith('S1_')]
        two = [p for p in gears if p.name.startswith('S2_')]
        self.assertGreater(min((p.z for p in two)), max((p.z + p.width for p in one)))
        self.assertIn('14:1', d.metrics[0])
        connector = next((p for p in d.parts if 'Coupling_interstage' in p.name))
        self.assertGreater(connector.z + connector.width, min((p.z for p in two)))

    def test_helical_hands_and_contact_at_heights(self):
        d = generate('planetary', {'variant': 'helical'})
        gears = [p for p in d.parts if p.role == 'gear']
        sun = gears[0]
        planets = gears[1:-1]
        ring = gears[-1]
        self.assertGreater(sun.twist, 0)
        self.assertTrue(all((p.twist < 0 for p in planets)))
        self.assertLess(ring.twist, 0)
        for h in (0, 0.37, 1):
            outer = transformed(sun.outer, angle=radians(sun.twist * h))
            inner = transformed(ring.holes[0], angle=radians(ring.twist * h))
            for p in planets:
                points = transformed(p.outer, p.center, radians(p.twist * h))
                self.assertFalse(any((inside(pt, outer) for pt in points)))
                self.assertTrue(all((inside(pt, inner) for pt in points)))

    def test_planetary_motion_sampled(self):
        d = generate('planetary')
        gears = [p for p in d.parts if p.role == 'gear']
        sun = gears[0]
        p = gears[1]
        ring = gears[-1]
        zs, zp = (d.values['sun'], d.values['planet'])
        ratio = 1 + (zs + 2 * zp) / zs
        for theta in (0, 0.37, 1.1, 2.4, 3.7, 5.3):
            carrier = theta / ratio
            spin = carrier + zs / zp * (carrier - theta)
            pts = transformed(p.outer, transformed([p.center], angle=carrier)[0], spin)
            sung = transformed(sun.outer, angle=theta)
            self.assertFalse(any((inside(pt, sung) for pt in pts)))
            self.assertTrue(all((inside(pt, ring.holes[0]) for pt in pts)))

    def test_dual_cycloid_phasing_and_common_pins(self):
        d = generate('cycloidal', {'variant': 'dual'})
        discs = [p for p in d.parts if p.name.startswith('Disc_cycloidal')]
        self.assertEqual(len(discs), 2)
        self.assertGreater(discs[1].z, discs[0].width)
        n, R, e, r = (16, 40, 1.2, 3)
        for phase in (0, 0.6, 2.1, 4.5):
            out = -phase / (n - 1)
            for j, disc in enumerate(discs):
                center = polar(e, phase + j * pi)
                base = cycloid(n, R, e, r, 0.1, samples=4096)
                profile = transformed(base, angle=-j * pi / (n - 1))
                for k in range(n):
                    pin = polar(R, TAU * k / n)
                    local = transformed([(pin[0] - center[0], pin[1] - center[1])], angle=-out)[0]
                    self.assertGreaterEqual(distance(local, profile), r + 0.095)
                for k in range(d.values['output_count']):
                    hole = transformed([polar(22, TAU * k / 6)], center, out)[0]
                    pin = transformed([polar(22, TAU * k / 6)], angle=out)[0]
                    self.assertAlmostEqual(hypot(hole[0] - pin[0], hole[1] - pin[1]), e)

    def test_double_one_step_solid_and_no_boolean_union(self):
        for gap in (0, 1, 2):
            d = generate('double', {'gap': gap})
            cmd = d.commands()
            solids = [c for c in cmd if c['command'] in ('solid.loft', 'solid.sweep', 'solid.extrude', 'file.insert_step')]
            self.assertEqual(len(solids), 1)
            self.assertEqual(solids[0]['command'], 'file.insert_step')
            self.assertFalse(any((c['command'] == 'solid.combine' for c in cmd)))

    def test_invalid_mounting_and_eccentric_bore(self):
        for family, values in [('planetary', {'variant': 'two_stage', 'sun2': 19}), ('cycloidal', {'variant': 'dual', 'input_shaft': 12}), ('double', {'bore': 42, 'helix': 0})]:
            with self.subTest(family=family), self.assertRaises(ValueError):
                generate(family, values)
if __name__ == '__main__':
    unittest.main(verbosity=2)
