# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Functional BOM rows must describe the actual generated construction."""
import unittest

import bom
from geometry import FAMILIES, generate


class BomViewTests(unittest.TestCase):
    def test_all_families_use_current_source_indices(self):
        for family in FAMILIES:
            with self.subTest(family=family):
                design = generate(family)
                report = bom.presentation(design)
                self.assertEqual(report['family'], family)
                self.assertTrue(report['rows'])
                context = set(report['context_indices'])
                self.assertTrue(context <= set(range(len(design.parts))))
                counted = set()
                for row in report['rows']:
                    indices = set(row['indices'])
                    self.assertTrue(indices and indices <= context)
                    self.assertEqual(len(indices), len(row['indices']))
                    if row['status'] == 'interface':
                        self.assertIsNone(row['quantity'])
                        self.assertTrue(row['cad'])
                        continue
                    self.assertFalse(counted & indices)
                    self.assertEqual(row['quantity'], len(indices))
                    if row['status'] == 'buy':
                        self.assertTrue(row['code'])
                        self.assertTrue(all(bom.part_info(design.parts[i])['code'] == row['code']
                                            for i in indices))
                    counted.update(indices)
                purchased = {i for i, part in enumerate(design.parts) if part.procurement or part.catalog_code}
                self.assertTrue(purchased <= counted)

    def test_bushed_cycloidal_counts_and_integral_ring(self):
        for variant, expected in [('single', 16), ('dual', 32)]:
            with self.subTest(variant=variant):
                design = generate('cycloidal', {'variant': variant, 'ring_roller_bearing': 'GSM-0304-05'})
                rows = {row['kind']: row for row in bom.presentation(design)['rows']}
                self.assertEqual(rows['ring_bushing']['quantity'], expected)
                self.assertEqual(rows['ring_shell']['quantity'], expected)
                self.assertEqual(rows['ring_pin']['quantity'], 16)
                self.assertEqual(rows['ring_bushing']['code'], 'igus GSM-0304-05')
                self.assertEqual(rows['ring_shell']['status'], 'make')
                self.assertTrue(all(design.parts[i].name.startswith('Pin_ring_')
                                    for i in rows['ring_pin']['indices']))
        ring_output = generate('cycloidal', {'variant': 'dual', 'io_scheme': 'eccentric_ring_output',
                                             'ring_roller_bearing': 'GSM-0304-05'})
        rows = bom.presentation(ring_output)['rows']
        self.assertFalse(any(row['kind'] in ('ring_pin', 'ring_bushing', 'ring_shell') for row in rows))
        support = next(row for row in rows if row['label'] == 'Annular ring support')
        self.assertIsNone(support['quantity'])
        self.assertEqual([ring_output.parts[i].name for i in support['indices']], ['Ring_pin_carrier'])

    def test_distinct_stage_sizes_and_unresolved_rack_interfaces(self):
        design = generate('planetary', {'variant': 'two_stage', 'width2': 12,
                                         'planet_bushing': 'GSM-0608-04'})
        rows = bom.presentation(design)['rows']
        pins = [row for row in rows if row['kind'] == 'planet_pin']
        self.assertEqual(sorted(row['quantity'] for row in pins), [3, 3])
        self.assertNotEqual(pins[0]['dimensions'], pins[1]['dimensions'])
        rack = bom.presentation(generate('rack'))['rows']
        self.assertTrue(all(row['status'] == 'interface' and row['quantity'] is None for row in rack))
        self.assertTrue(any(row['label'] == 'Linear guide and travel stops' for row in rack))
