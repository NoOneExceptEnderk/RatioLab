# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Warning decisions can be checked without creating widgets or opening CAD."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from engineering import geometry_warnings
from geometry import generate
from gui_workflow import update_geometry_warning


class GeometryWarningTests(unittest.TestCase):
    def label_for(self, design):
        app = SimpleNamespace(study=Mock())
        update_geometry_warning(app, design)
        return app.study

    def test_single_gear_undercut_is_visible_and_matches_report(self):
        for family in ('spur', 'helical', 'double'):
            with self.subTest(family=family):
                design = generate(family, {'teeth': 12, 'bore': 0})
                warning, = geometry_warnings(design)
                self.assertIn('undercut', warning)
                self.assertIn(warning, design.notes)
                label = self.label_for(design)
                label.set_visible.assert_called_once_with(True)
                self.assertIn(warning, label.set_text.call_args.args[0])

    def test_profile_shift_clears_undercut_and_hides_old_warning(self):
        app = SimpleNamespace(study=Mock())
        update_geometry_warning(app, generate('spur', {'teeth': 12, 'bore': 0}))
        corrected = generate('spur', {'teeth': 12, 'bore': 0, 'profile_shift': 0.4})
        self.assertEqual(geometry_warnings(corrected), [])
        update_geometry_warning(app, corrected)
        app.study.set_visible.assert_called_with(False)
        app.study.set_text.assert_called_with('')

    def test_internal_interference_is_visible(self):
        design = generate('planetary')
        self.assertTrue(any('Internal involute interference' in w
                            for w in geometry_warnings(design)))
        label = self.label_for(design)
        label.set_visible.assert_called_once_with(True)
        self.assertIn('Internal involute interference', label.set_text.call_args.args[0])

    def test_generated_profiles_clear_both_construction_notices(self):
        for family in ('worm', 'differential', 'harmonic'):
            with self.subTest(family=family):
                app = SimpleNamespace(study=Mock(), family_hint=Mock(),
                                      warning_bar=Mock(), warning_details=Mock())
                update_geometry_warning(app, generate(family))
                app.study.set_visible.assert_called_once_with(False)
                app.study.set_text.assert_called_once_with('')
                app.family_hint.set_visible.assert_called_once_with(False)
                app.warning_bar.set_visible.assert_called_once_with(False)

    def test_missing_verification_is_not_silently_accepted(self):
        for family in ('harmonic', 'worm', 'differential'):
            with self.subTest(family=family):
                design = SimpleNamespace(family=family, analysis={})
                # This checks the display decision independently of generation.
                from unittest.mock import patch
                with patch('engineering.geometry_warnings', return_value=[]):
                    label = self.label_for(design)
                label.set_visible.assert_called_once_with(True)
                self.assertIn('not been verified', label.set_text.call_args.args[0])

    def test_real_warning_takes_priority_over_construction_notice(self):
        from unittest.mock import patch
        design = SimpleNamespace(family='worm', analysis={})
        with patch('engineering.geometry_warnings', return_value=['Insufficient clearance']):
            label = self.label_for(design)
        self.assertIn('Insufficient clearance', label.set_text.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
