# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Direct drive cards retain physical controls, project history and catalog drafts."""
from copy import deepcopy
import unittest
import test_workspace_theme_preferences as fixtures
from test_workspace_theme_preferences import pump, wait_until
from geometry import generate
from kinematics import TRIPLES, options
from model_catalog_ui import Catalog
from gui_workflow import _descendants


class DirectSidebarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.WorkspaceThemePreferencesTests.setUpClass()

    setUp=fixtures.WorkspaceThemePreferencesTests.setUp
    close_apps=fixtures.WorkspaceThemePreferencesTests.close_apps
    launch=fixtures.WorkspaceThemePreferencesTests.launch

    def load(self,app,family,**parameters):
        design=generate(family,parameters)
        app.load_config_data(dict(format='solidcraft-riduttori/1',family=family,parameters=design.values))
        self.assertTrue(wait_until(lambda:app.design and app.design.family==family and not app.pending and not app._geometry_waiting))

    def test_launch_and_reactivation_open_workspace_without_catalog(self):
        app=self.launch()
        self.assertIsNone(getattr(app,'model_catalog',None))
        self.assertEqual(app.get_windows(),[app.win])
        before=deepcopy(app.project_snapshot())
        from model_catalog_ui import show
        show(app);pump(.05)
        picker=app.model_catalog
        self.assertTrue(picker.window.get_visible())
        picker.choose('planetary','two_stage')
        app.activate();pump(.05)
        self.assertIsNone(app.model_catalog)
        self.assertFalse(picker.window.get_visible())
        self.assertEqual(app.project_snapshot(),before)

    def test_card_selection_uses_real_motion_and_undo_preserves_exact_fields(self):
        app=self.launch();self.load(app,'parallel')
        app.inputs['module'].set_text('2.000000000012345')
        app.inputs['module'].emit('activate')
        self.assertTrue(wait_until(lambda:not app.pending and not app._geometry_waiting))
        snapshot=deepcopy(app.project_snapshot())
        self.assertEqual(set(app.io_mode_buttons),{'forward','reverse'})
        self.assertTrue(all(b.has_css_class('drive-member-card') for b in app.io_mode_buttons.values()))
        app.io_mode_buttons['reverse'].set_active(True)
        self.assertTrue(wait_until(lambda:app.design.values['io_scheme']=='reverse' and not app.pending and not app._geometry_waiting))
        self.assertAlmostEqual(app.design.analysis['output']['rpm'],-4500)
        self.assertEqual(app.inputs['module'].get_text(),'2.000000000012345')
        app.undo_project();pump(.1)
        self.assertEqual(app.project_snapshot(),snapshot)
        self.assertTrue(app.io_mode_buttons['forward'].get_active())

    def test_three_member_selectors_retain_all_six_permutations_and_both_stages(self):
        app=self.launch()
        for family in TRIPLES:
            self.load(app,family)
            self.assertEqual(len(options(family)),6)
            roles=app.io_role_selectors['io_scheme']
            self.assertEqual(roles['input'].get_model().get_n_items(),3)
            self.assertEqual(roles['output'].get_model().get_n_items(),2)
            self.assertFalse(any(w.has_css_class('drive-member-card') for w in _descendants(app.io_box)))
        self.load(app,'planetary',variant='two_stage')
        self.assertEqual(set(app.io_role_selectors),{'io_scheme','io_scheme2'})
        before=app.read_values()['io_scheme']
        app.io_role_selectors['io_scheme2']['input'].set_selected(1)
        pump(.1)
        self.assertEqual(app.read_values()['io_scheme'],before)
        self.assertNotEqual(app.read_values()['io_scheme2'],before)

    def test_illustrated_catalog_is_transactional_and_header_tracks_variants(self):
        app=self.launch();self.load(app,'parallel')
        before=deepcopy(app.project_snapshot())
        picker=Catalog(app);app.model_catalog=picker
        picker.choose('parallel','three_stage_helical')
        picker.window.close();pump(.05)
        self.assertEqual(app.project_snapshot(),before)
        picker=Catalog(app);app.model_catalog=picker
        picker.choose('parallel','three_stage_helical');picker.commit();pump(.1)
        self.assertFalse(app.variant_box.get_visible())
        self.assertIn('3 stages',app.catalog_summary.get_text())
        self.assertIn('Helical',app.catalog_summary.get_text())
        self.assertIsNotNone(app.catalog_picture.get_paintable())
        app.undo_project();pump(.1)
        self.assertEqual(app.project_snapshot(),before)
        self.assertIn('1 stage',app.catalog_summary.get_text())

    def test_fixed_and_differential_topologies_are_not_binary_cards(self):
        app=self.launch()
        for family in ('wolfrom','differential'):
            self.load(app,family)
            self.assertFalse(any(w.has_css_class('drive-member-card') for w in _descendants(app.io_box)))
        self.assertEqual(set(app.io_mode_buttons),{'tilt','spin','combined'})
