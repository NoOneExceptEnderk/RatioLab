# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Shaped attachment bores follow the physical shaft and the shared solid."""
import json
import unittest

from geometry import generate, circle_info
from geometry_quality import project, representation
from parameter_errors import ParameterError
from shaft_connections import targets, profile_key
from solid_geometry import rings, signature


class ShaftConnectionTests(unittest.TestCase):
    def test_rotary_models_generate_real_closed_shaped_bores(self):
        cases = [
            ('planetary', {'variant': 'two_stage_double'}),
            ('parallel', {'variant': 'three_stage_double', 'io_scheme': 'reverse'}),
            ('internal', {'io_scheme': 'reverse'}),
            ('worm', {}),
            ('harmonic', {}),
            ('differential', {}),
            ('wolfrom', {'module': 1, 'bore': 6}),
            ('bevel', {}),
            ('hypoid', {}),
            ('face', {}),
        ]
        for family, settings in cases:
            base = generate(family, settings)
            ports = targets(family, base.values)
            self.assertTrue(ports)
            for profile in ('d_shaft', 'keyed_shaft'):
                with self.subTest(family=family, profile=profile):
                    params = {**settings, **{profile_key(port): profile for port in ports}}
                    design = generate(family, params)
                    records = design.analysis['shaft_connections']
                    self.assertEqual({row['port'] for row in records}, set(ports))
                    parts = {part.name: part for part in design.parts}
                    for record in records:
                        part = parts[record['part']]
                        self.assertIsNone(circle_info(part.holes[0]))
                        self.assertGreater(signature(part)['volume_mm3'], 0)
                        self.assertFalse(set(ports[record['port']][1]) & parts.keys())
                    self.assertEqual(design.analysis.get('signed_ratio'), base.analysis.get('signed_ratio'))

    def test_double_helix_d_flat_stays_axial_at_export_precision(self):
        design = generate('planetary', {'variant': 'double', 'input_shaft_profile': 'd_shaft',
                                        'input_connection_clocking': 30}, quality={'export_mm': .005})
        design = representation(design, 'export')
        sun = next(part for part in design.parts if part.name == 'S1_Sun')
        levels = rings(sun)
        self.assertGreater(len(levels), 4)
        first_bore = [point[:2] for point in levels[0][1]]
        for level in levels[1:]:
            self.assertEqual([point[:2] for point in level[1]], first_bore)
        self.assertNotEqual([point[:2] for point in levels[2][0]], [point[:2] for point in levels[0][0]])
        saved = json.loads(json.dumps(project(design)))
        restored = generate(saved['family'], saved['parameters'], quality=saved['quality'])
        self.assertEqual(restored.analysis['shaft_connections'], design.analysis['shaft_connections'])

    def test_ring_output_and_impossible_flat_are_rejected(self):
        with self.assertRaisesRegex(ParameterError, 'no supported shaft bore'):
            generate('wolfrom', {'output_shaft_profile': 'd_shaft'})
        with self.assertRaisesRegex(ParameterError, 'D-flat depth'):
            generate('parallel', {'input_shaft_profile': 'd_shaft', 'input_connection_flat': 3})
