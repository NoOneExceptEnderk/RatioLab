# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Assembly, torque indexing and printable solids for the bolted eccentric shaft."""
import json
import unittest
from math import hypot, pi, cos, sin
from geometry import generate, circle_info, contains
from printed_shaft import PRESET
from solid_geometry import signature
from bom import build
from motion import build_plan, transform
import test_stl_export

class PrintedShaftTests(unittest.TestCase):

    def design(self, variant='dual', **values):
        return generate('cycloidal', dict(variant=variant, eccentric_design='fdm_bolted', **values))

    def test_bolted_stack_is_closed_and_stl_keeps_the_real_holes(self):
        checker = test_stl_export.StlExportTests()
        for variant in ('single', 'dual'):
            d = self.design(variant)
            selected = [p for p in d.parts if p.name.startswith(('Eccentric_', 'Bearing_eccentric_'))]
            self.assertEqual(len([p for p in selected if p.name.startswith('Eccentric_printed_')]), 2 if variant == 'single' else 3)
            for p in selected:
                with self.subTest(variant=variant, part=p.name):
                    self.assertGreater(signature(p)['volume_mm3'], 0)
                    checker.assert_solid(p)
            for name in d.analysis['printed_eccentric_shaft']['printed_parts']:
                p = next((p for p in d.parts if p.name == name))
                for station in p.stations:
                    for hole in station['holes']:
                        x, y, r = circle_info(hole)
                        self.assertFalse(contains(station['outer'], (x, y)) and (not any((contains(h, (x, y)) for h in station['holes']))))

    def test_two_axial_bolts_align_through_every_part_and_index_phase(self):
        d = self.design()
        data = d.analysis['printed_eccentric_shaft']
        centers = data['bolt_centers_mm']
        self.assertEqual(len(centers), 2)
        self.assertGreater(hypot(centers[0][0] - centers[1][0], centers[0][1] - centers[1][1]), 8)
        self.assertGreater(abs(hypot(*centers[0]) - hypot(*centers[1])), d.values['print_hole_clearance'])
        for name in data['printed_parts']:
            p = next((p for p in d.parts if p.name == name))
            for s in p.stations:
                for h, expected in zip(s['holes'], centers):
                    x, y, r = circle_info(h)
                    self.assertAlmostEqual(x, expected[0])
                    self.assertAlmostEqual(y, expected[1])
                    self.assertGreaterEqual(r * 2, data['bolt_hole_diameter_mm'] - 1e-07)
        plan = build_plan(d)
        for phase in (0, pi / 3, pi, 5 * pi / 3):
            for j, center in enumerate(centers, 1):
                i = next((i for i, p in enumerate(d.parts) if p.name == f'Eccentric_tie_bolt_{j}'))
                base = next((i for i, p in enumerate(d.parts) if p.name == 'Eccentric_printed_base'))
                self.assertEqual(transform(plan.matrix(i, phase), (*center, 0)), transform(plan.matrix(base, phase), (*center, 0)))

    def test_bearings_can_slide_on_and_have_axial_shoulders_and_retainer(self):
        for variant in ('single', 'dual'):
            d = self.design(variant)
            data = d.analysis['printed_eccentric_shaft']
            bearings = [p for p in d.parts if p.name.startswith('Bearing_eccentric_')]
            self.assertEqual(len(bearings), 1 if variant == 'single' else 2)
            self.assertLess(data['cap_top_mm'], data['disc_stack_top_mm'])
            for j, bearing in enumerate(bearings):
                self.assertAlmostEqual(bearing.width, 7)
                self.assertEqual(bearing.center, (d.values['eccentric'] * (-1 if j else 1), 0))
                host = next((p for p in d.parts if p.name == ('Eccentric_printed_base' if j == 0 else 'Eccentric_printed_stage_2')))
                top = host.stations[-1]
                x, y, r = circle_info(top['outer'])
                self.assertAlmostEqual(2 * r, 19.85)
                self.assertAlmostEqual(bearing.z + bearing.width - host.z - host.width, 0.12)
                self.assertGreater(20 - 2 * r, 0)
                self.assertGreater(d.values['bore'] - 32, 0)
                shoulder = next((s for s in host.stations if abs(host.z + s['z'] - bearing.z) < 1e-07))
                self.assertGreater(circle_info(shoulder['outer'])[2] * 2, 22)
            cap = next((p for p in d.parts if p.name == 'Eccentric_printed_cap'))
            self.assertAlmostEqual(cap.z, bearings[-1].z + 7)

    def test_purchased_hardware_and_full_nut_engagement(self):
        for variant, L in [('single', 30), ('dual', 45)]:
            d = self.design(variant)
            rows = build(d)['rows']

            def quantity(code):
                return sum((r['quantity'] for r in rows if r['code'] == code and r['category'] == 'PURCHASE'))
            self.assertEqual(quantity(f'ISO4762-M3x{L}'), 2)
            self.assertEqual(quantity('ISO4032-M3'), 2)
            self.assertEqual(quantity('ISO7089-M3'), 4)
            self.assertEqual(quantity('NSK 6804'), 1 if variant == 'single' else 2)
            for j in (1, 2):
                bolt = next((p for p in d.parts if p.name == f'Eccentric_tie_bolt_{j}'))
                nut = next((p for p in d.parts if p.name == f'Eccentric_tie_nut_{j}'))
                self.assertLessEqual(bolt.z, nut.z - 1)
                self.assertGreater(bolt.z + bolt.width, nut.z + nut.width)

    def test_invalid_walls_and_incompatible_schemes_are_rejected(self):
        cases = [{'input_shaft': 12}, {'input_shaft': 20}, {'print_bolt_pitch': 6}, {'width': 12}, {'eccentric': 3}, {'print_min_wall': 2}, {'io_scheme': 'ring_output_eccentric'}, {'bearing_mode': 'gear'}, {'hardware_mode': 'standard'}, {'eccentric_design': 'unknown'}]
        for values in cases:
            with self.subTest(values=values):
                args = dict(variant='dual', eccentric_design='fdm_bolted')
                args.update(values)
                with self.assertRaises(ValueError):
                    generate('cycloidal', args)

    def test_legacy_and_json_roundtrip_preserves_fixed_hardware(self):
        legacy = generate('cycloidal', {'variant': 'dual'})
        self.assertEqual(legacy.values['eccentric_design'], 'standard')
        self.assertTrue(any((p.name == 'Shaft_input' for p in legacy.parts)))
        self.assertFalse(any((p.name.startswith('Eccentric_printed_') for p in legacy.parts)))
        d = self.design()
        again = generate('cycloidal', json.loads(json.dumps(d.values)))
        self.assertEqual(d.values, again.values)
        self.assertEqual(build(d)['rows'], build(again)['rows'])

    def test_housing_output_keeps_the_two_bolt_input_and_fixes_the_pin_carrier(self):
        for variant in ('single', 'dual'):
            standard = self.design(variant)
            d = self.design(variant, io_scheme='eccentric_ring_output')
            self.assertEqual(d.analysis['signed_ratio'], 16)
            self.assertEqual(d.analysis['kinematics']['stage_results'][0]['rates_rpm'], {'eccentric': 1500, 'ring': 93.75, 'output': 0})
            self.assertTrue(any((p.name == 'Cover_input' for p in d.parts)))
            self.assertFalse(any((p.name == 'Attachment_eccentric_Hub' for p in d.parts)))
            printed = d.analysis['printed_eccentric_shaft']['printed_parts']
            for name in printed + ['Eccentric_tie_bolt_1', 'Eccentric_tie_bolt_2']:
                old = next((p for p in standard.parts if p.name == name))
                new = next((p for p in d.parts if p.name == name))
                self.assertEqual(signature(old), signature(new))
                self.assertEqual(new.port['member'], 'eccentric')
                self.assertEqual(new.port['role'], 'input')
            names = {p.name for p in d.parts}
            for r in d.analysis['mount_interfaces']:
                self.assertIn(r['anchor'], names)
                for name in r['parts']:
                    self.assertIn(name, names)
                    part = next((p for p in d.parts if p.name == name))
                    self.assertEqual(part.port['role'], r['role'])
            for p in d.parts:
                if p.name.startswith(('Pin_output_', 'Flange_pincarrier', 'Shaft_pincarrier')):
                    self.assertEqual(p.port['role'], 'fixed')
                    self.assertEqual(p.port['rpm'], 0)
            plan = build_plan(d)
            phase = pi / 2
            ring_i = next((i for i, p in enumerate(d.parts) if p.name == 'Housing_tubular'))
            x, y, z = transform(plan.matrix(ring_i, phase), (40, 0, 0))
            self.assertAlmostEqual(x, 40 * cos(phase / 16))
            self.assertAlmostEqual(y, 40 * sin(phase / 16))
            fixed_i = next((i for i, p in enumerate(d.parts) if p.name == 'Shaft_pincarrier'))
            self.assertEqual(transform(plan.matrix(fixed_i, phase), (3, 2, 5)), (3, 2, 5))

    def test_housing_output_interfaces_are_watertight_and_clear_of_the_fixed_shaft(self):
        for variant in ('single', 'dual'):
            d = self.design(variant, io_scheme='eccentric_ring_output')
            byname = {p.name: p for p in d.parts}
            shaft = byname['Shaft_pincarrier']
            rings = [byname['Attachment_ring_Hub'], byname['Attachment_ring_Flange']]
            frame = byname['Attachment_output_Frame_flange']
            cover = byname['Cover_output']
            self.assertAlmostEqual(rings[0].z, cover.z + cover.width)
            self.assertAlmostEqual(rings[1].z, rings[0].z + rings[0].width)
            self.assertGreater(frame.z, rings[1].z + rings[1].width)
            self.assertAlmostEqual(shaft.z + shaft.width, frame.z)
            for p in rings:
                self.assertGreater(circle_info(p.holes[0])[2], circle_info(shaft.outer)[2] + d.values['assembly_clearance'])
            self.assertEqual(len(rings[1].holes) - 1, 6)
            self.assertEqual(len(frame.holes), 8)
            for p in d.parts:
                if p.name.startswith(('Eccentric_', 'Disc_cycloidal', 'Pin_output_', 'Roller_ring_')):
                    self.assertLessEqual(p.z + p.width, rings[0].z + 1e-07)
            checker = test_stl_export.StlExportTests()
            for p in rings + [frame, shaft]:
                checker.assert_solid(p)
            again = generate('cycloidal', json.loads(json.dumps(d.values)))
            self.assertEqual(again.analysis['mount_interfaces'], d.analysis['mount_interfaces'])
            self.assertEqual(build(again)['rows'], build(d)['rows'])
if __name__ == '__main__':
    unittest.main()
