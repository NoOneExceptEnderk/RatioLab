# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Real GL catalog/export coverage, including compositor-suspended workspaces."""
import os
import unittest
from unittest.mock import patch
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk
from geometry import FAMILIES
from ratiolab_checks import self_test


class WorkspaceFrameGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            raise unittest.SkipTest('GTK display required')

    def test_every_family_renders_a_new_checked_frame_and_workspace_exports(self):
        with patch.object(os,'environ',dict(os.environ,RATIOLAB_UPDATE_CHECK='0')):
            result=self_test(gui=True)
        self.assertEqual(result['self_test'],'passed')
        self.assertEqual(result['preview_families'],list(FAMILIES))
        self.assertEqual(result['workspace_export'],'passed')
        self.assertTrue(result['framebuffer_has_geometry'])
        checks={row['phase'].removeprefix('family:'):row for row in result['preview_frame_checks']
                if row['phase'].startswith('family:')}
        self.assertEqual(set(checks),set(FAMILIES))
        for family,proof in checks.items():
            with self.subTest(family=family):
                self.assertIn(proof['mode'],('gtk-frame','suspended-capture'))
                self.assertGreater(proof['png_bytes'],8)
                self.assertGreater(proof['width'],0);self.assertGreater(proof['height'],0)
                self.assertGreater(proof['render_after'],proof['render_before'])


if __name__=='__main__':unittest.main()
