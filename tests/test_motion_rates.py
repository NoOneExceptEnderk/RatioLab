# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Operating-rate changes preserve physical angles and generated metadata."""
import unittest
from copy import deepcopy
from math import pi
from geometry import FAMILIES, generate
from motion import build_plan, update_operating_rates


class MotionRateTests(unittest.TestCase):
    def assert_pose(self, actual, expected, count, phase, expected_phase):
        for index in range(count):
            for method in ('matrix', 'deformation', 'warp'):
                a = getattr(actual, method)(index, phase)
                b = getattr(expected, method)(index, expected_phase)
                if a is None or b is None:
                    self.assertIs(a, b)
                else:
                    self.assertEqual(len(a), len(b))
                    for x, y in zip(a, b):
                        self.assertAlmostEqual(x, y, places=8)

    def test_metadata_matches_regeneration_and_shares_only_geometry(self):
        cases = [(f, {}) for f in FAMILIES]
        cases += [('planetary', {'variant': 'two_stage_double', 'io_scheme': 'ring_carrier_sun', 'io_scheme2': 'sun_ring_carrier'}),
                  ('cycloidal', {'variant': 'dual', 'io_scheme': 'ring_eccentric_output'}),
                  ('harmonic', {'io_scheme': 'flex_wave_circular'}),
                  ('worm', {'io_scheme': 'reverse'}),
                  ('parallel', {'io_scheme': 'reverse'}),
                  ('internal', {'io_scheme': 'reverse'}),
                  ('differential', {'configuration': 'classic', 'output_difference_rpm': 40})]
        for family, extra in cases:
            with self.subTest(family=family, extra=extra):
                original = generate(family, dict(extra, input_rpm=0))
                original_analysis = deepcopy(original.analysis)
                for speed in (321.125, 0):
                    values = dict(original.values, input_rpm=speed)
                    actual = update_operating_rates(original, values)
                    expected = generate(family, values)
                    for attr in ('values', 'analysis', 'metrics', 'notes', 'requirements'):
                        self.assertEqual(getattr(actual, attr), getattr(expected, attr), attr)
                    self.assertEqual([p.port for p in actual.parts], [p.port for p in expected.parts])
                    for a, b in zip(actual.parts, original.parts):
                        self.assertIs(a.outer, b.outer)
                        self.assertIs(a.mesh, b.mesh)
                        self.assertIsNot(a.port, b.port)
                    self.assertEqual(original.values['input_rpm'], 0)
                    self.assertEqual(original.analysis, original_analysis)

    def test_single_input_angles_orbits_and_flex_integrate_speed_ramp(self):
        ramp = ((60, .13), (173.125, .07), (0, .31), (7.5, .19), (100000, .001), (0, .17), (33, .21))
        total_angle = sum(speed*seconds*2*pi/60 for speed, seconds in ramp)
        for family in FAMILIES:
            if family == 'differential':
                continue
            with self.subTest(family=family):
                d = generate(family, {'input_rpm': 60})
                oracle = build_plan(d)
                plan = build_plan(d)
                # Finite travel needs shorter durations, not reduced RPM or
                # relaxed limits. Leave room before the positive stroke end.
                time_scale = (min(1., .8*oracle.phase_limits[1]/total_angle)
                              if oracle.phase_limits is not None else 1.)
                phase = angle = 0
                for speed, seconds in ramp:
                    seconds *= time_scale
                    before = plan
                    new = update_operating_rates(d, dict(d.values, input_rpm=speed))
                    plan = build_plan(new, plan, phase)
                    self.assert_pose(plan, before, len(d.parts), phase, phase)
                    phase += (plan.reference_rpm if speed else 0)*seconds*2*pi/60
                    angle += speed*seconds*2*pi/60
                    self.assert_pose(plan, oracle, len(d.parts), phase, angle)
                    d = new

    def test_finite_rack_speed_changes_preserve_both_stroke_ends(self):
        for variant in ('spur', 'helical', 'double'):
            with self.subTest(variant=variant):
                d = generate('rack', dict(variant=variant, input_rpm=60))
                oracle = plan = build_plan(d)
                low, high = d.analysis['rack']['pinion_angle_limits_rad']
                travel_low, travel_high = d.analysis['rack']['travel_limits_mm']
                phase = angle = 0.
                for speed, target in ((100000, high), (0, high), (-173.125, low), (0, low), (33, 0.)):
                    with self.subTest(speed=speed, target=target):
                        new = update_operating_rates(d, dict(d.values, input_rpm=speed))
                        previous = plan
                        plan = build_plan(new, previous, phase)
                        self.assert_pose(plan, previous, len(d.parts), phase, phase)
                        seconds = (target-angle)*60/(speed*2*pi) if speed else .31
                        self.assertGreater(seconds, 0.)
                        phase += (plan.reference_rpm if speed else 0)*seconds*2*pi/60
                        angle += speed*seconds*2*pi/60
                        self.assertAlmostEqual(angle, target, places=12)
                        self.assert_pose(plan, oracle, len(d.parts), phase, angle)
                        if speed:
                            # A reversed plan traverses the same physical
                            # stroke with its endpoints in the opposite order.
                            ends = sorted(plan.matrix(1, bound)[12] for bound in plan.phase_limits)
                            self.assertAlmostEqual(ends[0], travel_low, places=10)
                            self.assertAlmostEqual(ends[1], travel_high, places=10)
                            for outside in (plan.phase_limits[0]-.01, plan.phase_limits[1]+.01):
                                with self.assertRaisesRegex(ValueError, 'finite working stroke'):
                                    plan.matrix(1, outside)
                        else:
                            self.assertEqual(plan.matrix(1, phase), plan.matrix(1, phase+3))
                        d = new

    def test_differential_independent_inputs_reversal_and_stationary_members(self):
        for configuration, second in (('wrist', 'input_b_rpm'), ('classic', 'output_difference_rpm')):
            with self.subTest(configuration=configuration):
                d = generate('differential', dict(configuration=configuration, input_rpm=0, **{second: 0}))
                plan = build_plan(d)
                phase = total = a_integral = b_integral = 0
                for a, b, seconds in ((12, -12, .12), (-7, 13, .07), (0, 0, .3), (21, 21, .13), (-5, 0, .11)):
                    new = update_operating_rates(d, dict(d.values, input_rpm=a, **{second: b}))
                    previous = plan
                    plan = build_plan(new, plan, phase)
                    self.assert_pose(plan, previous, len(d.parts), phase, phase)
                    phase += (plan.reference_rpm if a or b else 0)*seconds*2*pi/60
                    total += seconds
                    a_integral += a*seconds
                    b_integral += b*seconds
                    average = generate('differential', dict(d.values, input_rpm=a_integral/total, **{second: b_integral/total}))
                    oracle = build_plan(average)
                    self.assert_pose(plan, oracle, len(d.parts), phase, oracle.reference_rpm*total*2*pi/60)
                    d = new

    def test_rate_update_rejects_geometry_and_invalid_or_unsupported_speed_ranges(self):
        d = generate('differential')
        with self.assertRaises(ValueError):
            update_operating_rates(d, dict(d.values, module=3))
        for field, values in (('input_rpm', (-100001, 100001, float('nan'), float('inf'), True)),
                              ('input_b_rpm', (-100001, 100001, float('nan'), float('inf'))),
                              ('output_difference_rpm', (-200001, 200001, float('nan'), float('inf')))):
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    update_operating_rates(d, dict(d.values, **{field: value}))
        d = generate('spur')
        with self.assertRaises(ValueError):
            update_operating_rates(d, dict(d.values, input_rpm=-1))


if __name__ == '__main__':
    unittest.main()
