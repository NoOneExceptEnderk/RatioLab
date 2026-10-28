# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Kinematic pose checks independent of the rendering buffers."""
import unittest, json
from math import pi, cos, sin, isfinite, hypot
from geometry import generate, FAMILIES
from motion import build_plan, rotation, transform, IDENTITY
from kinematics import options, TRIPLES
from solid_geometry import signature

class MotionTests(unittest.TestCase):

    def close(self, a, b):
        for x, y in zip(a, b):
            self.assertAlmostEqual(x, y, places=8)

    def test_rotation_pivot_and_rigidity(self):
        m = rotation(pi / 2, pivot=(2, 3, 0))
        self.close(transform(m, (3, 3, 7)), (2, 4, 7))
        self.close(transform(m, (2, 3, 0)), (2, 3, 0))
        self.close(transform(rotation(pi / 2, (1, 0, 0)), (0, 1, 0)), (0, 0, 1))

    def test_supported_plans_are_finite_at_every_part_and_start_at_reference(self):
        for family in FAMILIES:
            d = generate(family)
            p = build_plan(d)
            self.assertTrue(p.supported, family)
            for i, part in enumerate(d.parts):
                self.close(p.matrix(i, 0), IDENTITY)
                for phase in (0.2, 1.4, 5.3):
                    self.assertTrue(all((isfinite(x) for x in p.matrix(i, phase))), (family, part.name))
                    if p.warp(i, phase):
                        self.assertTrue(all((isfinite(x) for x in p.warp(i, phase))))

    def test_planetary_spin_is_not_just_carrier_orbit(self):
        d = generate('planetary')
        p = build_plan(d)
        i = next((i for i, x in enumerate(d.parts) if x.name == 'S1_Planet_1'))
        part = d.parts[i]
        r = hypot(*part.center)
        phase = pi / 2
        C = transform(p.matrix(i, phase), (*part.center, 0))
        self.close(C, (r * cos(pi / 8), r * sin(pi / 8), 0))
        tip = transform(p.matrix(i, phase), (part.center[0] + 1, part.center[1], 0))
        self.close(tuple((tip[k] - C[k] for k in range(3))), (cos(-pi / 4), sin(-pi / 4), 0))

    def test_all_fixed_ports_stay_still_and_two_stages_follow_their_own_speed(self):
        for f in ('planetary', 'cycloidal', 'harmonic'):
            for scheme in options(f):
                d = generate(f, {'io_scheme': scheme})
                p = build_plan(d)
                for i, part in enumerate(d.parts):
                    if part.port.get('role') == 'fixed':
                        self.close(p.matrix(i, 1.2), IDENTITY)
        d = generate('planetary', {'variant': 'two_stage_double', 'io_scheme': 'ring_carrier_sun', 'io_scheme2': 'sun_ring_carrier'})
        p = build_plan(d)
        for stage in (1, 2):
            q = d.analysis['kinematics']['stage_results'][stage - 1]
            i = next((i for i, x in enumerate(d.parts) if x.name == f'S{stage}_Sun'))
            self.close(transform(p.matrix(i, 1), (1, 0, 0)), (cos(q['rates_rpm']['sun'] / p.reference_rpm), sin(q['rates_rpm']['sun'] / p.reference_rpm), 0))

    def test_cycloidal_disc_orbits_without_being_rigidly_welded_to_cam(self):
        d = generate('cycloidal')
        p = build_plan(d)
        i = next((i for i, x in enumerate(d.parts) if x.name == 'Disc_cycloidal_1'))
        part = d.parts[i]
        phase = pi / 2
        e = d.values['eccentric']
        c = transform(p.matrix(i, phase), (*part.center, 0))
        self.close(c, (0, e, 0))
        tip = transform(p.matrix(i, phase), (part.center[0] + 1, 0, 0))
        a = -phase / (d.values['pins'] - 1)
        self.close(tuple((tip[k] - c[k] for k in range(3))), (cos(a), sin(a), 0))

    def test_animation_does_not_change_design_parameters_or_export_geometry(self):
        d = generate('planetary', {'variant': 'double', 'io_scheme': 'ring_carrier_sun'})
        before = json.dumps(d.commands(), sort_keys=True)
        volumes = [signature(x)['volume_mm3'] for x in d.parts]
        p = build_plan(d)
        for phase in (1, 2, 3):
            for i in range(len(d.parts)):
                p.matrix(i, phase)
        self.assertEqual(before, json.dumps(d.commands(), sort_keys=True))
        self.assertEqual(volumes, [signature(x)['volume_mm3'] for x in d.parts])
if __name__ == '__main__':
    unittest.main()
