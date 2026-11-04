# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Retiring one native workspace must release its display and event resources."""
import unittest
from unittest.mock import patch
from gi.repository import Gtk
import test_workspace_theme_preferences as fixtures
from test_workspace_theme_preferences import wait_until


class WorkspaceLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.WorkspaceThemePreferencesTests.setUpClass()

    setUp = fixtures.WorkspaceThemePreferencesTests.setUp
    close_apps = fixtures.WorkspaceThemePreferencesTests.close_apps
    launch = fixtures.WorkspaceThemePreferencesTests.launch

    def test_destroy_releases_style_worker_and_ticks_without_stopping_other_workspace(self):
        first = self.launch()
        first.canvas.set_motion_playing(True)
        self.assertTrue(wait_until(lambda: first.canvas.motion_phase > 0))
        second = self.launch()
        second.canvas.set_motion_playing(True)
        self.assertTrue(wait_until(lambda: second.canvas.motion_phase > 0))
        original = Gtk.StyleContext.remove_provider_for_display
        with patch.object(Gtk.StyleContext, 'remove_provider_for_display', wraps=original) as remove:
            first.win.destroy()
            self.assertEqual(first.canvas.motion_tick, 0)
            self.assertIsNone(first.canvas.gl)
            self.assertTrue(first.geometry_worker.closed)
            self.assertIsNone(first.language.timer)
            providers = [call.args[1] for call in remove.call_args_list]
            self.assertIn(first.workspace_style, providers)
            self.assertNotIn(second.workspace_style, providers)
            phase = second.canvas.motion_phase
            self.assertTrue(wait_until(lambda: second.canvas.motion_phase > phase))
            second.win.destroy()
            providers = [call.args[1] for call in remove.call_args_list]
            self.assertIn(second.workspace_style, providers)
