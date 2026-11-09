# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Public mouse-map contracts and safe preference defaults, without GTK."""
import unittest
import app_paths
from mouse_navigation import LEFT, MIDDLE, RIGHT, PROFILES, drag_mode


class MouseProfileTests(unittest.TestCase):
    def test_ratiolab_keeps_original_buttons(self):
        self.assertEqual(drag_mode('ratiolab', LEFT), 'orbit')
        self.assertEqual(drag_mode('ratiolab', RIGHT), 'pan')
        self.assertIsNone(drag_mode('ratiolab', MIDDLE))

    def test_fusion_inventor_and_solidcraft_main_gestures(self):
        for profile in ('fusion', 'inventor', 'solidcraft'):
            self.assertEqual(drag_mode(profile, MIDDLE), 'pan')
            self.assertEqual(drag_mode(profile, MIDDLE, shift=True), 'orbit')
        self.assertEqual(drag_mode('solidcraft', RIGHT), 'orbit')
        self.assertEqual(drag_mode('inventor', MIDDLE, control=True), 'pan')
        self.assertIsNone(drag_mode('fusion', LEFT))

    def test_solidworks_modifiers_have_distinct_camera_operations(self):
        self.assertEqual(drag_mode('solidworks', MIDDLE), 'orbit')
        self.assertEqual(drag_mode('solidworks', MIDDLE, control=True), 'pan')
        self.assertEqual(drag_mode('solidworks', MIDDLE, shift=True), 'zoom')
        self.assertIsNone(drag_mode('solidworks', MIDDLE, shift=True, control=True))

    def test_freecad_combines_buttons_and_pan_tool_remains_an_explicit_override(self):
        self.assertEqual(drag_mode('freecad', MIDDLE), 'pan')
        self.assertEqual(drag_mode('freecad', MIDDLE | LEFT), 'orbit')
        self.assertEqual(drag_mode('freecad', MIDDLE | RIGHT), 'orbit')
        for profile in PROFILES:
            self.assertEqual(drag_mode(profile, LEFT, pan_mode=True), 'pan')

    def test_preferences_validate_profile_without_mutating_other_values(self):
        for profile in PROFILES:
            self.assertEqual(app_paths.ui_preferences({'mouse_navigation': profile})['mouse_navigation'], profile)
        for invalid in ([], {}, None, True, 'unknown'):
            data={'mouse_navigation': invalid, 'zoom_speed': 2, 'invert_zoom': True}
            result=app_paths.ui_preferences(data)
            self.assertEqual(result['mouse_navigation'], 'ratiolab')
            self.assertEqual(result['zoom_speed'], 2)
            self.assertTrue(result['invert_zoom'])
            self.assertEqual(data['mouse_navigation'], invalid)


if __name__ == '__main__':unittest.main()
