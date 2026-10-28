# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Verifiche geometriche; non sostituiscono una verifica meccanica del riduttore."""
import unittest
import json
from math import hypot, pi, sin, cos, tan, radians
from geometry import *

def inside(p, poly):
    x, y = p
    hit = False
    for a, b in zip(poly, poly[1:] + poly[:1]):
        if (a[1] > y) != (b[1] > y) and x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]:
            hit = not hit
    return hit

def distance(p, poly):
    best = float('inf')
    for a, b in zip(poly, poly[1:] + poly[:1]):
        vx, vy = (b[0] - a[0], b[1] - a[1])
        den = vx * vx + vy * vy
        t = max(0, min(1, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / den)) if den else 0
        best = min(best, hypot(p[0] - a[0] - t * vx, p[1] - a[1] - t * vy))
    return best

class GeometryTests(unittest.TestCase):

    def test_all_defaults(self):
        for family in FAMILIES:
            with self.subTest(family=family):
                d = generate(family)
                self.assertTrue(d.parts)
                json.dumps(d.commands(), allow_nan=False)
                for p in d.parts:
                    self.assertGreater(len(p.outer), 3)
                    self.assertTrue(all((isfinite(x) and isfinite(y) for x, y in p.outer)))

    def test_involute_radii_and_helix(self):
        d = generate('spur')
        rs = [hypot(x, y) for x, y in d.parts[0].outer]
        self.assertAlmostEqual(max(rs), 26, places=6)
        self.assertAlmostEqual(min(rs), 21.5, places=6)
        d = generate('helical')
        rp = 2 * 24 / (2 * cos(radians(20)))
        self.assertAlmostEqual(d.parts[0].twist, 180 / pi * 10 * tan(radians(20)) / rp)

    def test_planet_assembly_and_clearance(self):
        d = generate('planetary')
        gears = [p for p in d.parts if p.role == 'gear']
        self.assertEqual(len(gears), 5)
        sun = gears[0]
        ring = gears[-1]
        hole = ring.holes[0]
        for p in gears[1:-1]:
            outer = transformed(p.outer, p.center)
            self.assertFalse(any((inside(pt, sun.outer) for pt in outer)), 'Satellite interferisce con sun')
            self.assertTrue(all((inside(pt, hole) for pt in outer)), 'Satellite interferisce con ring')
        with self.assertRaises(ValueError):
            generate('planetary', {'planets': 5})

    def test_cycloidal_contact_through_revolution(self):
        n, R, e, r = (16, 40, 1.2, 3)
        clear = 0.1
        poly = cycloid(n, R, e, r, clear, samples=8192)
        for phase in (0, 0.3, 1.2, 2.7, 5.1):
            for j in range(n):
                x = R * cos(TAU * j / n) - e * cos(phase)
                y = R * sin(TAU * j / n) - e * sin(phase)
                pt = transformed([(x, y)], angle=phase / (n - 1))[0]
                self.assertFalse(inside(pt, poly))
                self.assertAlmostEqual(distance(pt, poly), r + clear, delta=0.003)

    def test_reject_invalid_configurations(self):
        cases = [('spur', {'teeth': 24.2}), ('spur', {'module': float('nan')}), ('spur', {'bore': 80}), ('cycloidal', {'eccentric': 5}), ('cycloidal', {'output_radius': 35}), ('double', {'gap': 10}), ('harmonic', {'teeth': 61}), ('worm', {'length': 80, 'module': 0.1})]
        for f, p in cases:
            with self.subTest(f=f, p=p), self.assertRaises(ValueError):
                generate(f, p)

    def test_native_circles_and_unique_groups(self):
        d = generate('spur')
        cmds = d.commands()
        self.assertEqual(len([c for c in cmds if c['command'] == 'sketch.circle.center']), 1)
        self.assertNotEqual(d.token, generate('spur').token)
        self.assertFalse(any((c['command'] == 'file.new' for c in cmds)))
if __name__ == '__main__':
    unittest.main(verbosity=2)
