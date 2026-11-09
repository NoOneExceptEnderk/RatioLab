# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Twentieth-place inputs must reach Rust and survive save/history/recovery."""
from copy import deepcopy
from decimal import Decimal, localcontext
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from precise_numbers import from_text,attach,PreciseFloat,SOURCE_KEY
from geometry import generate,validate
from engineering import gear_dimensions
from project_document import Document,atomic_json,validate_snapshot
from motion import same_geometry


class PreciseInputTests(unittest.TestCase):
    def test_twentieth_place_reaches_both_analytic_and_constructed_part_records(self):
        d=generate('spur',dict(module=from_text('2.00000000000000000001')))
        self.assertEqual(d.values[SOURCE_KEY]['module'],'2.00000000000000000001')
        for record in (d.analysis['gear']['analytic_values'],d.parts[0].profile_metadata['analytic_values']):
            self.assertEqual(record['pitch_radius_mm'],'24.00000000000000000012')
        restored=generate('spur',json.loads(json.dumps(d.values)))
        self.assertEqual(restored.analysis,d.analysis)
        self.assertEqual(restored.parts[0].outer,d.parts[0].outer)

    def test_derived_arithmetic_is_re_evaluated_in_rust_without_float_rounding(self):
        module=from_text('2.00000000000000000001')
        derived=module*3/7
        self.assertIsInstance(derived,PreciseFloat)
        g=gear_dimensions(24,derived)
        with localcontext() as context:
            context.prec=100
            expected=format(Decimal('2.00000000000000000001')*3/7*12,'.20f')
        self.assertEqual(g['analytic_values']['pitch_radius_mm'],expected)
        negative=gear_dimensions(24,module,x=-from_text('.10000000000000000001'))
        self.assertTrue(negative['analytic_values']['normal_reference_arc_mm'])
        cancelled=(module+20000000000000000)-20000000000000000
        self.assertEqual(float(cancelled),2.)
        # A valid expression must survive cancellation at presentation precision,
        # not be rejected as a contradictory hand-edited project source.
        restored=generate('spur',dict(module=cancelled))
        self.assertEqual(restored.analysis['gear']['analytic_values']['pitch_radius_mm'],
                         '24.00000000000000000012')

    def test_strict_integer_bounds_and_contradictory_sources_are_refused(self):
        with self.assertRaisesRegex(ValueError,'integer'):
            validate('spur',dict(teeth=from_text('24.00000000000000000001')))
        with self.assertRaisesRegex(ValueError,'bounds'):
            validate('spur',dict(module=from_text('10.00000000000000000001')))
        with self.assertRaisesRegex(ValueError,'does not match'):
            validate('spur',dict(module=2,_decimal_inputs={'module':'5'}))

    def test_history_and_json_keep_changes_beyond_binary64_and_undo_them(self):
        values=validate('spur',dict(module=from_text('2.00000000000000000001')))
        first=dict(family='spur',values={'spur':values},raw={'spur':{'module':'2.00000000000000000001'}})
        second=deepcopy(first)
        attach(second['values']['spur'],'module',from_text('2.00000000000000000002'))
        second['raw']['spur']['module']='2.00000000000000000002'
        document=Document(first)
        self.assertTrue(document.record(second,'module'))
        self.assertTrue(document.dirty)
        self.assertEqual(document.undo()["values"]['spur'][SOURCE_KEY]['module'],'2.00000000000000000001')
        document.redo()
        with TemporaryDirectory() as temporary:
            path=Path(temporary)/'precise.json';atomic_json(path,document.current)
            saved=json.loads(path.read_text())
            validate_snapshot(saved,{'spur'})
            self.assertEqual(saved['values']['spur'][SOURCE_KEY]['module'],'2.00000000000000000002')

    def test_speed_edits_keep_precise_geometry_and_geometry_edits_invalidate_it(self):
        d=generate('spur',dict(module=from_text('2.00000000000000000001')))
        values=deepcopy(d.values);attach(values,'input_rpm',from_text('1500.00000000000000000001'))
        self.assertTrue(same_geometry(d,'spur',values))
        attach(values,'module',from_text('2.00000000000000000002'))
        self.assertFalse(same_geometry(d,'spur',values))
