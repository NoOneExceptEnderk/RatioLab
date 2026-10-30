# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Independent force-sign oracle, shared backend gate and atomic API checks."""
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backdrivability import BackdrivabilityError, evaluate
from geometry import defaults, generate, validate
from ratiolab_agent import AgentError, AgentService


class BackdrivabilityTests(unittest.TestCase):
    def test_independent_khk_reference_normal_to_axial_conversion(self):
        # KHK Table 4.23: mx=3, starts=2, d1=44, normal pressure=20 deg.
        # Independent critical coefficient from the right triangle of lead and
        # circumference, without the evaluator's atan/tan evaluation path.
        lead_ratio = 6 / 44
        alpha_x = math.degrees(math.atan(math.tan(math.radians(20)) * math.sqrt(1 + lead_ratio**2)))
        values = validate('worm', dict(module=3, starts=2, diameter=44, pressure=alpha_x,
                                       width=8, worm_static_friction=.1))
        q = evaluate('worm', values)
        self.assertAlmostEqual(q['lead_angle_deg'], 7.765166018425333, places=10)
        self.assertAlmostEqual(q['normal_pressure_angle_deg'], 20, places=12)
        self.assertAlmostEqual(q['critical_static_friction'], .12813990283444206, places=12)
        self.assertEqual(q['status'], 'potentially_backdrivable')

    def test_force_sign_oracle_both_variants_hands_starts_and_threshold(self):
        for variant in ('za', 'zi'):
            for hand in (-1, 1):
                for starts in (1, 4):
                    values = validate('worm', dict(variant=variant, worm_hand=hand, starts=starts))
                    t = values['module'] * starts / values['diameter']
                    normal_tangent = math.tan(math.radians(values['pressure'])) / math.sqrt(1+t*t)
                    critical = t / math.sqrt(1+normal_tangent**2)
                    for mu, allowed in ((0, True), (critical*.5, True), (critical*1.001, False), (1e300, False)):
                        gamma = math.atan(t)
                        alpha = math.atan(normal_tangent)
                        force_ratio = math.cos(alpha)*math.sin(gamma) - mu*math.cos(gamma)
                        self.assertEqual(force_ratio > 0, allowed)
                        q = evaluate('worm', dict(values, io_scheme='reverse', worm_static_friction=mu))
                        self.assertEqual(q['allowed'], allowed)
                    limit = evaluate('worm', values)['critical_static_friction']
                    with self.assertRaises(BackdrivabilityError):
                        validate('worm', dict(values, io_scheme='reverse', worm_static_friction=limit))
                    validate('worm', dict(values, io_scheme='reverse', worm_static_friction=math.nextafter(limit, 0)))
                    with self.assertRaises(BackdrivabilityError):
                        validate('worm', dict(values, io_scheme='reverse', worm_static_friction=math.nextafter(limit, math.inf)))

    def test_missing_zero_forward_and_motor_sign_are_distinct(self):
        for rpm in (0, 30):
            for hand in (-1, 1):
                values = dict(input_rpm=rpm, worm_hand=hand)
                unknown = generate('worm', dict(values, io_scheme='reverse'))
                self.assertEqual(unknown.analysis['backdrivability']['status'], 'indeterminate')
                self.assertIn('static tooth friction is missing', '\n'.join(unknown.notes))
                zero = generate('worm', dict(values, io_scheme='reverse', worm_static_friction=0))
                self.assertEqual(zero.analysis['backdrivability']['status'], 'potentially_backdrivable')
                forward = generate('worm', dict(values, worm_static_friction=.5))
                q = forward.analysis['backdrivability']
                self.assertEqual(q['status'], 'not_backdrivable')
                self.assertTrue(q['allowed'])
                with self.assertRaises(BackdrivabilityError):
                    generate('worm', dict(values, io_scheme='reverse', worm_static_friction=.5))

    def test_policy_is_invariant_to_speed_sign_and_normal_speed_domain_remains(self):
        physical = validate('worm', dict(worm_static_friction=.2))
        for rpm in (-30, 0, 30):
            self.assertTrue(evaluate('worm', dict(physical, input_rpm=rpm))['allowed'])
            self.assertFalse(evaluate('worm', dict(physical, io_scheme='reverse', input_rpm=rpm))['allowed'])
        # The current general operating-data domain disallows negative worm RPM;
        # that ordinary numeric limit is distinct from reverse-member refusal.
        for scheme in ('forward', 'reverse'):
            with self.assertRaises(ValueError) as caught:
                generate('worm', dict(input_rpm=-30, io_scheme=scheme, worm_static_friction=0))
            self.assertNotIsInstance(caught.exception, BackdrivabilityError)
            self.assertIn('Input speed', str(caught.exception))

    def test_invalid_physical_values_cannot_disappear_or_select_other_family(self):
        for bad in (True, False, '0.1', '', None, -1, float('nan'), float('inf'), -float('inf'), 10**1000):
            for scheme in ('forward', 'reverse'):
                with self.subTest(value=repr(bad)[:30], scheme=scheme), self.assertRaises(ValueError):
                    validate('worm', dict(io_scheme=scheme, worm_static_friction=bad))
        with self.assertRaises(ValueError):
            validate('spur', dict(worm_static_friction=.1))

    def test_no_harmonic_family_ban_or_invented_friction(self):
        for scheme in ('wave_flex_circular', 'wave_circular_flex', 'flex_wave_circular',
                       'circular_wave_flex', 'flex_circular_wave', 'circular_flex_wave'):
            d = generate('harmonic', dict(io_scheme=scheme))
            q = d.analysis['backdrivability']
            self.assertTrue(q['allowed'])
            self.assertEqual(q['status'], 'not_evaluated' if scheme.startswith('wave_') else 'indeterminate')
            if q['reverse_requested']:
                self.assertIn('breakaway torque', q['message'])

    def test_api_update_open_and_metadata_roundtrip_are_atomic(self):
        with TemporaryDirectory() as folder:
            service = AgentService(folder)
            self.addCleanup(service.close)
            discovery = service.discover('worm')
            self.assertIn('worm_static_friction', discovery['options'])
            json.dumps(discovery, allow_nan=False)
            project = service.project_create('worm', dict(worm_static_friction=.2))
            ref = dict(handle=project['handle'], revision=project['revision'])
            original = service.projects[project['handle']].design
            for changes in (dict(io_scheme='reverse'), dict(worm_static_friction=10**1000),
                            dict(worm_static_friction=None), dict(worm_static_friction='0')):
                with self.assertRaises(AgentError):
                    service.project_update(**ref, parameters=changes)
                self.assertEqual(service.project_list()['projects'], [project])
                self.assertIs(service.projects[project['handle']].design, original)
            path = Path(folder)/'forbidden.json'
            path.write_text(json.dumps(dict(format='solidcraft-riduttori/1', family='worm',
                                            parameters=dict(io_scheme='reverse', worm_static_friction=.2))))
            with self.assertRaises(AgentError):
                service.project_open(path.name)
            self.assertEqual(service.project_list()['projects'], [project])
            path.write_text(json.dumps(dict(format='solidcraft-riduttori/1', family='worm',
                                            parameters=dict(io_scheme='reverse'))))
            legacy = service.project_open(path.name)
            d = service.projects[legacy['handle']].design
            self.assertEqual(d.analysis['backdrivability']['status'], 'indeterminate')
            valid = service.project_create('worm', dict(io_scheme='reverse', worm_static_friction=0))
            service.project_save(valid['handle'], valid['revision'], 'zero.json')
            reopened = service.project_open('zero.json')
            self.assertEqual(reopened['parameters']['worm_static_friction'], 0)
            self.assertEqual(service.projects[reopened['handle']].design.analysis['backdrivability']['status'], 'potentially_backdrivable')


if __name__ == '__main__':
    unittest.main()
