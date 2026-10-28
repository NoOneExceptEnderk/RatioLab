# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Controlli della geometria 3D relative to quote, twist e assi del CAD."""
import unittest
from math import hypot, isfinite
from geometry import generate, Part
from preview3d import build_scene, point


class FramebufferTests(unittest.TestCase):
    def test_rgba_capture_keeps_color_and_vertical_orientation_in_cairo(self):
        import sys
        from unittest.mock import patch
        from preview3d import framebuffer_argb32
        # GL bottom row red/green; top row blue/white.
        pixels=bytes((255,0,0,255,0,255,0,255,0,0,255,255,255,255,255,255))
        for endian in ('little','big'):
            with self.subTest(endian=endian), patch.object(sys,'byteorder',endian):
                raw=framebuffer_argb32(pixels,2,2)
                words=[int.from_bytes(raw[i:i+4],endian) for i in range(0,16,4)]
                self.assertEqual(words,[0xff0000ff,0xffffffff,0xffff0000,0xff00ff00])

class PreviewTests(unittest.TestCase):

    def test_spur_thickness_and_bounding(self):
        scene = build_scene(generate('spur', {'width': 17}))
        self.assertEqual(scene.bounds[0][2], 0)
        self.assertEqual(scene.bounds[1][2], 17)
        self.assertAlmostEqual(scene.center[2], 8.5)
        start, count = scene.parts[0].side
        for i in range(start * 6, (start + count) * 6, 6):
            p = scene.vertices[i:i + 3]
            self.assertLessEqual(sum(((p[j] - scene.center[j]) ** 2 for j in range(3))), scene.radius ** 2 + 0.001)

    def test_screw_axis_is_x(self):
        p = Part('screw', [(2, 0), (0, 2), (-2, 0), (0, -2)], width=24, axis_x=True)
        self.assertEqual(point(p, (2, 0), 0, 0), (-12, 0, -2))
        self.assertEqual(point(p, (2, 0), 24, 0), (12, 0, -2))

    def test_double_is_one_continuous_closed_surface(self):
        design = generate('double', {'width': 12, 'gap': 2})
        scene = build_scene(design)
        self.assertEqual(len(scene.parts), 1)
        self.assertEqual(len(scene.parts[0].caps), 2)
        from geometry import profile_sections
        sections = profile_sections(design.parts[0])
        self.assertEqual(sections[0][0], 0)
        self.assertEqual(sections[-1][0], 12)
        groove = [(z, outline) for z, angle, outline in sections if outline is not design.parts[0].outer]
        self.assertEqual([z for z, outline in groove], [5, 7])
        self.assertTrue(all((min((hypot(x, y) for x, y in outline)) > 3 for z, outline in groove)))

    def test_finite_scene_for_every_family(self):
        for family in ('spur', 'helical', 'double', 'planetary', 'cycloidal', 'harmonic', 'worm'):
            with self.subTest(family=family):
                s = build_scene(generate(family))
                self.assertTrue(all((isfinite(v) for v in s.vertices)))
                for p in s.parts:
                    for cap in p.caps:
                        self.assertEqual(cap.plane[1], 6)
if __name__ == '__main__':
    unittest.main(verbosity=2)
