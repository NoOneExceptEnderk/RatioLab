# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
import unittest, json, tempfile
from pathlib import Path
from math import hypot
from geometry import generate, circle_info, contains
from solid_geometry import signature, section_loops
from bom import build, export
from hardware_catalog import INTERNAL, EXTERNAL, FASTENERS

class HardwareTests(unittest.TestCase):

    def test_four_categories_and_real_quantities(self):
        d = generate('double', {'hardware_mode': 'standard', 'bearing_mode': 'shaft'})
        rows = build(d)['rows']
        codes = {r['code']: r['quantity'] for r in rows}
        self.assertEqual(sum((n for k, n in codes.items() if k.startswith('ISO 4762'))), 4)
        self.assertEqual(codes['ISO 4032 M3'], 4)
        self.assertEqual(codes['ISO 7089 3'], 8)
        self.assertEqual(codes['EXT0060'], 2)
        self.assertEqual(codes['DIN472-019'], 4)
        self.assertEqual(sum((n for k, n in codes.items() if k.startswith('DIN 6885'))), 1)
        self.assertEqual(sum((n for k, n in codes.items() if k.startswith('K1151.'))), 2)
        self.assertEqual(sum((r['quantity'] for r in rows)), len(d.parts))

    def test_key_is_in_shaft_and_hub_cavities(self):
        d = generate('spur', {'hardware_mode': 'standard', 'hardware_bolts': False})
        gear = d.parts[0]
        shaft = next((p for p in d.parts if p.name == 'Shaft_standard'))
        slot = next((o for o in shaft.machining if o['type'] == 'keyway_shaft'))
        active = next((s for s in shaft.stations if abs(s['z'] - slot['z0']) < 1e-07 and (not contains(s['outer'], (2.9, 0)))))
        self.assertFalse(contains(active['outer'], (2.9, 0)))
        self.assertTrue(contains(gear.stations[0]['holes'][0], (3.8, 0)))
        key = next((p for p in d.parts if 'Key' in p.name))
        self.assertAlmostEqual(min((x for x, y in key.outer)), 1.8)
        self.assertAlmostEqual(max((x for x, y in key.outer)), 3.8)
        self.assertLess(key.width, gear.width)

    def test_groove_dimensions_and_edge_margins(self):
        d = generate('planetary', {'variant': 'double', 'bearing_mode': 'gear', 'hardware_mode': 'standard'})
        for p in d.parts:
            for op in p.machining:
                if op['type'] == 'groove_internal':
                    spec = INTERNAL[19]
                    self.assertAlmostEqual(op['diameter'], spec['groove'])
                    self.assertAlmostEqual(op['z1'] - op['z0'], spec['m'])
                    self.assertGreaterEqual(op['z0'], spec['edge'] - 1e-06)
                    self.assertGreaterEqual(p.width - op['z1'], spec['edge'] - 1e-06)
                    self.assertTrue(any((abs(circle_info(s['holes'][0])[2] * 2 - spec['groove']) < 1e-06 for s in p.stations)))
                elif op['type'] == 'groove_external':
                    self.assertAlmostEqual(op['diameter'], EXTERNAL[6]['groove'])

    def test_modified_solids_are_closed_and_shared(self):
        for f, v in [('double', {'bearing_mode': 'shaft'}), ('planetary', {'variant': 'two_stage_double', 'bearing_mode': 'gear'}), ('cycloidal', {'variant': 'dual', 'bearing_mode': 'gear'})]:
            d = generate(f, dict(v, hardware_mode='standard'))
            for p in d.parts:
                if p.stations:
                    with self.subTest(family=f, part=p.name):
                        self.assertGreater(signature(p)['volume_mm3'], 0)

    def test_bolt_holes_match_screw_positions_and_length(self):
        d = generate('cycloidal', {'hardware_mode': 'standard', 'bearing_mode': 'gear'})
        screws = [p for p in d.parts if p.procurement.get('standard') == 'ISO 4762']
        self.assertEqual(len(screws), 4)
        covers = [p for p in d.parts if p.name in ('Cover_input', 'Cover_output')]
        f = FASTENERS['M3']
        for screw in screws:
            for cover in covers:
                holes = [circle_info(h) for h in cover.holes]
                self.assertTrue(any((h and hypot(h[0] - screw.center[0], h[1] - screw.center[1]) < 1e-06 and (abs(2 * h[2] - f['clearance']) < 1e-06) for h in holes)))
            self.assertLess(screw.z, min((p.z for p in covers)) - f['washer_t'] - f['nut'])

    def test_large_shims_clear_internal_circlip_planes(self):
        d = generate('double', {'hardware_mode': 'standard', 'bearing_mode': 'shaft'})
        shims = [p for p in d.parts if p.procurement.get('standard') == 'DIN 988']
        rings = [p for p in d.parts if p.procurement.get('standard') == 'DIN 472']
        for shim in shims:
            for ring in rings:
                if shim.center == ring.center:
                    self.assertGreaterEqual(max(shim.z, ring.z) - min(shim.z + shim.width, ring.z + ring.width), -1e-07)
        self.assertEqual(sum((p.name.startswith('Spacer_retainer_') for p in d.parts)), 2)

    def test_independent_choices_do_not_add_unrequested_parts(self):
        none = {k: False for k in ('hardware_retaining', 'hardware_keys', 'hardware_bolts', 'hardware_shims')}
        d = generate('spur', dict(none, hardware_mode='standard'))
        self.assertEqual(len(d.parts), 1)
        bolts = generate('spur', dict(none, hardware_mode='standard', hardware_bolts=True))
        self.assertEqual(len(bolts.parts), 1)
        self.assertTrue(any(('Fasteners:' in r for r in bolts.requirements)))
        for size in ('M3', 'M4', 'M5', 'M6'):
            d = generate('spur', dict(none, hardware_mode='standard', bearing_mode='shaft', hardware_bolts=True, hardware_screw=size))
            self.assertEqual(sum((p.procurement.get('standard') == 'ISO 4762' for p in d.parts)), 4)
            self.assertFalse(any((p.procurement.get('standard') in ('DIN 471', 'DIN 472', 'DIN 6885-1 B') for p in d.parts)))

    def test_options_roundtrip_exports_and_safe_omissions(self):
        d = generate('spur', {'hardware_mode': 'standard', 'bearing_mode': 'gear'})
        self.assertFalse(any((p.procurement.get('standard') == 'DIN 6885-1 B' for p in d.parts)))
        self.assertTrue(any(('not fixed' in row for row in d.requirements)))
        again = generate(d.family, json.loads(json.dumps(d.values)))
        self.assertEqual(build(d)['rows'], build(again)['rows'])
        with tempfile.TemporaryDirectory() as folder:
            stem = Path(folder) / 'hardware'
            export(d, stem)
            self.assertTrue(Path(str(stem) + '.machining.json').exists())
            self.assertIn('DIN472-019', Path(str(stem) + '.bom.csv').read_text(encoding='utf-8-sig'))
        legacy = generate('spur')
        self.assertEqual(len(legacy.parts), 1)
        with self.assertRaises(ValueError):
            generate('spur', {'hardware_mode': 'standard', 'hardware_keys': 'true'})
if __name__ == '__main__':
    unittest.main()
