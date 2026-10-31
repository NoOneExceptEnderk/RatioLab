# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Live catalog coverage and mechanically distinct help conventions."""
import unittest
from parameter_help import lookup, coverage_rows, COMMON, OPTIONS, OPTION_LABELS, CHECK_LABELS
from geometry import FAMILIES, VARIANTS


class ParameterHelpTests(unittest.TestCase):
    def test_live_family_variant_matrix_has_no_missing_controls(self):
        rows = coverage_rows()
        self.assertEqual({r['family'] for r in rows}, set(FAMILIES))
        self.assertEqual(len(rows), sum(len(VARIANTS.get(f, {None: None})) for f in FAMILIES))
        for row in rows:
            with self.subTest(family=row['family'], variant=row['variant']):
                self.assertFalse(row['missing'])
                for key in row['parameters'] + row['options']:
                    help = lookup(row['family'], key)
                    self.assertTrue(help.title and help.meaning and help.effect and help.dimension)
        self.assertTrue(set(OPTION_LABELS.values()) <= COMMON.keys() | OPTIONS.keys())
        self.assertTrue(set(CHECK_LABELS.values()) <= OPTIONS.keys())

    def test_distinct_module_pressure_width_and_bore_conventions(self):
        self.assertIn('normal', lookup('helical', 'module').meaning)
        self.assertIn('axial', lookup('worm', 'module').meaning.lower())
        self.assertIn('axial', lookup('worm', 'pressure').meaning)
        self.assertIn('outer', lookup('differential', 'module').meaning)
        self.assertIn('generator', lookup('differential', 'width').meaning)
        self.assertIn('wheel', lookup('worm', 'width').meaning)
        self.assertIn('eccentric', lookup('cycloidal', 'bore').meaning)
        self.assertIn('wave generator', lookup('harmonic', 'bore').meaning)
        self.assertIn('perimeter', lookup('harmonic', 'wave_factor').effect)

    def test_differential_configuration_and_no_universal_ratio_figure(self):
        for config in ('wrist', 'classic'):
            for key in ('input_rpm', 'input_b_rpm', 'output_difference_rpm'):
                self.assertEqual(lookup('differential', key, {'configuration': config}).diagram, 'differential_motion')
        self.assertIn('carrier', lookup('differential', 'input_rpm', {'configuration': 'classic'}).meaning)
        self.assertIn('both', lookup('differential', 'flange_radius', {'configuration': 'classic'}).effect)

    def test_drive_connections_distinguish_pairs_and_triples(self):
        self.assertIn('two meshing', lookup('worm', 'io_scheme').meaning)
        self.assertIn('remaining member is fixed', lookup('planetary', 'io_scheme').meaning)
        self.assertIn('physical eccentric shaft', lookup('cycloidal', 'input_shaft').meaning)

    def test_wolfrom_has_compound_layers_ring_output_and_signed_sun_help(self):
        for key in ('sun', 'planet', 'planet2', 'output_ring', 'planets', 'width', 'width2', 'layer_gap', 'input_rpm', 'io_scheme'):
            self.assertEqual(lookup('wolfrom', key).diagram, 'wolfrom', key)
        self.assertIn('derived', lookup('wolfrom', 'module').effect)
        self.assertIn('second rim', lookup('wolfrom', 'width2').effect)
        self.assertIn('free common carrier', lookup('wolfrom', 'width2').effect)
        self.assertIn('+Z', lookup('wolfrom', 'input_rpm').meaning)
        self.assertIn('zero', lookup('wolfrom', 'input_rpm').effect)
        self.assertIn('not established', lookup('wolfrom', 'io_scheme').effect)

    def test_unknown_keys_are_explicit_gaps(self):
        with self.assertRaises(KeyError):
            lookup('spur', 'unknown_future_parameter')

    def test_optional_worm_friction_has_specific_model_help_and_worm_only_coverage(self):
        help = lookup('worm', 'worm_static_friction')
        self.assertEqual(help.diagram, 'text')
        for phrase in ('dimensionless', 'Missing means unknown', 'explicit 0'):
            self.assertIn(phrase, help.meaning)
        for phrase in ('Apply commits', 'Clear removes', 'does not clear', 'cos(αn) tan(γ)',
                       'axial pressure angle', 'static contact model', 'not a brake'):
            self.assertIn(phrase, help.effect)
        for row in coverage_rows():
            self.assertEqual('worm_static_friction' in row['parameters'], row['family'] == 'worm')


if __name__ == '__main__':
    unittest.main()
