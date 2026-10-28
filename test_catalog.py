# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
import json, tempfile, unittest
from pathlib import Path
from math import hypot, radians
from geometry import generate, profile_sections, section_holes, transformed, circle_info, material_point, contains
from catalog import BEARINGS
from bom import build, export
from test_geometry import inside

class CatalogTests(unittest.TestCase):

    def test_desktop_catalog_keeps_only_requested_transmissions(self):
        from geometry import FAMILIES, VARIANTS
        self.assertEqual(len(FAMILIES), 9)
        for family in ('internal', 'parallel', 'planetary', 'cycloidal', 'harmonic', 'worm'):
            self.assertIn(family, FAMILIES)
        self.assertEqual(set(VARIANTS['parallel']), {'spur', 'helical', 'double'})
        self.assertEqual(set(VARIANTS['internal']), {'spur', 'helical', 'double'})

    def test_linked_catalog_dimensions_and_roundtrip(self):
        for code, b in BEARINGS.items():
            for mode in ('gear', 'shaft'):
                with self.subTest(code=code, mode=mode):
                    d = generate('spur', {'bearing_mode': mode, 'bearing': code, 'module': 3})
                    self.assertEqual(d.values['bore'], b.D if mode == 'gear' else b.d)
                    bought = [p for p in d.parts if p.catalog_code]
                    self.assertEqual(len(bought), 1 if mode == 'gear' else 2)
                    for p in bought:
                        self.assertEqual(p.width, b.B)
                        self.assertAlmostEqual(circle_info(p.outer)[2] * 2, b.D)
                    again = generate(d.family, json.loads(json.dumps(d.values)))
                    self.assertEqual(build(d)['rows'], build(again)['rows'])

    def test_fits_are_diametric_and_nominal_resets(self):
        d = generate('double', {'bearing_mode': 'gear', 'bearing': '626', 'fit': 'custom', 'seat_allowance': 0.12, 'shaft_allowance': -0.04})
        self.assertAlmostEqual(d.values['bore'], 19.12)
        shaft = next((p for p in d.parts if p.name == 'Shaft_per_bearing'))
        self.assertAlmostEqual(circle_info(shaft.outer)[2] * 2, 5.96)
        self.assertEqual(generate('double', dict(d.values, fit='nominal')).values['bore'], 19)

    def test_assembly_quantities_and_partial_bom(self):
        for family, values, count in [('planetary', {'variant': 'two_stage_double'}, 6), ('cycloidal', {'variant': 'dual'}, 2)]:
            d = generate(family, dict(values, bearing_mode='gear'))
            rows = build(d)['rows']
            buy = [r for r in rows if r['category'] == 'PURCHASE']
            self.assertEqual(len(buy), 1)
            self.assertEqual(buy[0]['quantity'], count)
            self.assertTrue(any((r['category'] == 'TO BE DEFINED' for r in rows)))
            self.assertEqual(sum((r['quantity'] for r in rows)), len(d.parts))

    def test_planet_pins_enlarge_carriers_when_needed(self):
        d = generate('planetary', {'bearing_mode': 'gear', 'bearing': '6001'})
        for p in d.parts:
            if '_PlanetCarrier_' in p.name or '_Flange_output' in p.name:
                radius = circle_info(p.outer)[2]
                for h in p.holes[1:]:
                    x, y, r = circle_info(h)
                    self.assertGreater(radius, hypot(x, y) + r + 0.7)

    def test_exports_and_native_metadata(self):
        d = generate('planetary', {'bearing_mode': 'shaft'})
        with tempfile.TemporaryDirectory() as folder:
            stem = Path(folder) / 'sample'
            export(d, stem)
            self.assertEqual(json.loads(Path(str(stem) + '.bom.json').read_text())['family'], 'planetary')
            self.assertIn('PURCHASE', Path(str(stem) + '.bom.txt').read_text())
            self.assertIn('NSK 626', Path(str(stem) + '.bom.csv').read_text(encoding='utf-8-sig'))
        metadata = [c['params'] for c in d.commands() if c['command'] == 'component.metadata.set']
        self.assertEqual(len(metadata), len(d.parts) + 1)
        self.assertEqual(sum((m.get('part_number') == 'NSK 626' for m in metadata)), 3)

    def test_double_planetary_contact_and_one_import_per_gear(self):
        for variant in ('double', 'two_stage_double'):
            d = generate('planetary', {'variant': variant})
            gears = [p for p in d.parts if p.double]
            self.assertEqual(len(gears), 5 if variant == 'double' else 10)
            self.assertEqual(sum((c['command'] == 'file.insert_step' for c in d.commands())), len(gears))
            sun, planet, ring = (gears[0], gears[1], gears[4])
            for z, angle, outer in profile_sections(sun):
                sa = transformed(outer, angle=radians(angle))
                pa = angle * planet.twist / sun.twist
                ra = angle * ring.twist / sun.twist
                pp = transformed(next((o for zz, aa, o in profile_sections(planet) if abs(zz - z) < 1e-06)), planet.center, radians(pa))
                ri = transformed(section_holes(ring, z)[0], angle=radians(ra))
                self.assertFalse(any((inside(q, sa) for q in pp)))
                self.assertTrue(all((inside(q, ri) for q in pp)))
            mid = (ring.width - ring.gap) / 2
            self.assertGreater(min((hypot(x, y) for x, y in section_holes(ring, mid)[0])), max((hypot(x, y) for x, y in ring.holes[0])))

    def test_region_picks_exclude_every_hole(self):
        for family in ('spur', 'helical', 'double', 'planetary', 'cycloidal', 'harmonic', 'worm'):
            d = generate(family)
            for p in d.parts:
                for z, angle, outer in profile_sections(p):
                    holes = section_holes(p, z, outer)
                    q = material_point(outer, holes)
                    self.assertTrue(contains(outer, q))
                    self.assertFalse(any((contains(h, q) for h in holes)))
            for command in d.commands():
                if command['command'] in ('solid.extrude', 'solid.sweep'):
                    self.assertIn('profiles', command['params'])
                if command['command'] == 'solid.loft':
                    self.assertTrue(all(('profiles' in section for section in command['params']['sections'])))

    def test_invalid_catalog_combinations_rejected(self):
        for f, v in [('spur', {'bearing_mode': 'gear', 'bearing': '6201', 'module': 0.5}), ('cycloidal', {'bearing_mode': 'gear', 'bearing': '624'}), ('planetary', {'variant': 'double', 'gap': 10}), ('worm', {'bearing_mode': 'gear'}), ('planetary', {'variant': 'double', 'helix': 0, 'bore': 29.7})]:
            with self.subTest(f=f), self.assertRaises(ValueError):
                generate(f, v)
if __name__ == '__main__':
    unittest.main()
