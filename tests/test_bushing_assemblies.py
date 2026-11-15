# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Seated bushing geometry, kinematic parentage and stored project options."""
from contextlib import ExitStack
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from bom import build
from collision_geometry import Surface, relation
from geometry import circle_info, generate
from motion import build_plan, update_operating_rates
from selected_export import export


CASES = (
    ('planetary', {'variant': 'two_stage_double', 'planet_bushing': 'GSM-0608-04'},
     'S2_Planet_1_bushing', 'S2_Planet_1', 6),
    ('differential', {'configuration': 'classic', 'spider_bushing': 'GSM-0608-04',
                      'output_difference_rpm': 36},
     'Bushing_spider', 'Bevel_spider', 1),
    ('wolfrom', {'variant': 'double', 'compound_bushing': 'GSM-0304-05'},
     'Compound_1_bushing_1', 'Compound_1_rim1', 6),
    ('cycloidal', {'variant': 'dual', 'eccentric_bushing': 'GSM-1012-06', 'output_pin_sleeve': 'sleeved'},
     'Bushing_disc_eccentric_2', 'Disc_cycloidal_2', 2),
    ('parallel', {'variant': 'two_stage', 'shaft_bushing': 'GSM-0810-05'},
     'Bushing_shaft_upper', 'BushingBlock_upper', 2),
    ('worm', {'worm_bushing': 'GSM-1214-06'},
     'Bushing_shaft_upper', 'BushingBlock_upper', 2),
)


class BushingAssemblyTests(unittest.TestCase):
    def test_catalog_sleeves_are_seated_and_follow_the_intended_moving_part(self):
        for family, values, sleeve, seat, count in CASES:
            with self.subTest(family=family):
                d = generate(family, values)
                parts = {p.name: p for p in d.parts}
                fitted, receiving = parts[sleeve], parts[seat]
                self.assertAlmostEqual(circle_info(fitted.outer)[2], circle_info(receiving.holes[0])[2])
                self.assertGreaterEqual(fitted.z, receiving.z)
                self.assertLessEqual(fitted.z+fitted.width, receiving.z+receiving.width+1e-9)
                plan = build_plan(d)
                i, j = (d.parts.index(p) for p in (fitted, receiving))
                with ExitStack() as stack:
                    a, b = Surface.from_part(fitted), Surface.from_part(receiving)
                    stack.callback(a.close)
                    stack.callback(b.close)
                    for phase in (0, .37, 1.2):
                        self.assertEqual(plan.matrix(i,phase), plan.matrix(j,phase))
                        ap, bp = a.posed(plan.matrix(i,phase)), b.posed(plan.matrix(j,phase))
                        stack.callback(ap.close)
                        stack.callback(bp.close)
                        self.assertIn(relation(ap, bp, .002)['kind'], ('Boundary contact / unresolved', 'Separated'))
                rows = build(d)['rows']
                row = next(r for r in rows if r['code'] == fitted.procurement['code'])
                self.assertEqual((row['category'], row['quantity']), ('PURCHASE', count))
                restored = generate(family, json.loads(json.dumps(d.values)))
                self.assertEqual(build(restored)['rows'], rows)
                with TemporaryDirectory() as folder:
                    for kind in ('step', 'stl'):
                        output = Path(folder) / kind
                        export(d, [i], kind, output)
                        manifest = json.loads((output/'manifest.json').read_text())
                        self.assertTrue(any(f['path'].endswith('.'+kind) for f in manifest['files']))

    def test_cycloidal_output_sleeves_preserve_contact_and_shrink_only_the_core(self):
        standard = generate('cycloidal', {'variant': 'dual'})
        sleeved = generate('cycloidal', {'variant': 'dual', 'output_pin_sleeve': 'sleeved'})
        p = {p.name: p for p in sleeved.parts}
        original = {p.name: p for p in standard.parts}
        self.assertEqual(p['Disc_cycloidal_2'].holes, original['Disc_cycloidal_2'].holes)
        self.assertEqual(p['Pin_output_sleeve_1'].outer, original['Pin_output_1'].outer)
        self.assertEqual(p['Pin_output_sleeve_1'].holes[0], p['Pin_output_1'].outer)
        self.assertAlmostEqual(circle_info(p['Flange_output'].holes[1])[2], 1.5)
        row = next(r for r in build(sleeved)['rows'] if r['description'] == 'Cycloidal output pin sleeve')
        self.assertEqual((row['category'], row['quantity']), ('MANUFACTURE', 6))

    def test_multistage_speed_edit_keeps_bushing_blocks_fixed(self):
        d = generate('parallel', {'variant': 'two_stage', 'shaft_bushing': 'GSM-0810-05'})
        changed = update_operating_rates(d, dict(d.values, input_rpm=730))
        self.assertIsNotNone(changed)
        i = next(i for i,p in enumerate(d.parts) if p.name == 'BushingBlock_upper')
        self.assertEqual(build_plan(changed).matrix(i, .5), build_plan(d).matrix(i, 0))

    def test_incompatible_catalog_or_missing_journal_is_reported(self):
        with self.assertRaisesRegex(ValueError, 'journal diameter to 12'):
            generate('worm', {'worm_bushing': 'GSM-1214-06', 'journal_diameter': 10})
        with self.assertRaisesRegex(ValueError, 'available seat'):
            generate('worm', {'worm_bushing': 'GSM-1214-06', 'journal_length': 0})
        with self.assertRaisesRegex(ValueError, 'eccentric seat diameter to 10'):
            generate('cycloidal', {'eccentric_bushing': 'GSM-0810-05'})
        with self.assertRaisesRegex(ValueError, 'available seat'):
            generate('planetary', {'planet_bushing': 'GSM-0608-04', 'width': 3})
