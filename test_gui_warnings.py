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

    def test_concept_notice_remains_visible(self):
        for family in ('harmonic', 'worm'):
            with self.subTest(family=family):
                label = self.label_for(generate(family))
                label.set_visible.assert_called_once_with(True)
                label.set_text.assert_called_once_with(
                    'Concept model · profiles are not conjugate')


if __name__ == '__main__':
    unittest.main()
