# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Real native popup placement, model replacement and search selection."""
import unittest
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk
import gui_workflow
import test_workspace_theme_preferences as fixtures
from model_catalog_ui import Catalog


class NativeChoiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.WorkspaceThemePreferencesTests.setUpClass()

    setUp = fixtures.WorkspaceThemePreferencesTests.setUp
    close_apps = fixtures.WorkspaceThemePreferencesTests.close_apps
    launch = fixtures.WorkspaceThemePreferencesTests.launch

    def popup(self, dropdown):
        popup = next(w for w in gui_workflow._descendants(dropdown)
                     if isinstance(w, Gtk.Popover))
        dropdown.get_first_child().set_active(True)
        fixtures.pump(.15)
        self.assertTrue(popup.get_mapped())
        return popup

    def test_catalog_list_is_below_and_browsing_does_not_edit_document(self):
        app = self.launch()
        picker = Catalog(app)
        app.model_catalog = picker
        picker.window.present()
        fixtures.pump(.15)
        token = app.document.token
        dropdown = picker.selectors[0]
        for _ in range(2):
            popup = self.popup(dropdown)
            _, field = dropdown.compute_bounds(picker.window)
            _, content = popup.get_first_child().compute_bounds(picker.window)
            self.assertGreaterEqual(content.get_y(), field.get_y() + field.get_height())
            self.assertLess(content.get_y() + content.get_height(), picker.window.get_height())
            self.assertFalse(popup.get_has_arrow())
            self.assertFalse(any(isinstance(w, Gtk.Button) and w.get_visible()
                                 for w in gui_workflow._descendants(popup)))
            popup.popdown()
            fixtures.pump(.05)
        self.assertEqual(app.document.token, token)
        picker.window.close()

    def test_search_keeps_canonical_indices_after_model_replacement(self):
        app = self.launch()
        window = Gtk.Window(application=app, transient_for=app.win, modal=True,
                            default_width=400, default_height=420, css_classes=['reducers'])
        self.addCleanup(window.destroy)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        dropdown = gui_workflow.searchable_dropdown(['old'])
        box.append(dropdown)
        window.set_child(box)
        window.present()
        self.assertTrue(fixtures.wait_until(lambda: dropdown.get_mapped()))
        choices = ['Alpha', 'Beta', 'Gamma', 'Tamil தமிழ்', '中文'] + [f'Choice {n}' for n in range(35)]
        dropdown.set_model(Gtk.StringList.new(choices))
        dropdown.set_selected(3)
        fixtures.pump(.1)
        popup = self.popup(dropdown)
        search = next(w for w in gui_workflow._descendants(popup)
                      if isinstance(w, Gtk.SearchEntry))
        search.set_text('Choice 34')
        fixtures.pump(.3)
        listing = next(w for w in gui_workflow._descendants(popup)
                       if isinstance(w, Gtk.ListView))
        self.assertEqual(listing.get_model().get_n_items(), 1)
        listing.emit('activate', 0)
        fixtures.pump(.1)
        self.assertEqual(dropdown.get_selected(), choices.index('Choice 34'))
        self.assertEqual(dropdown.get_selected_item().get_string(), 'Choice 34')
        search.set_text('')
        popup = self.popup(dropdown)
        scroller = next(w for w in gui_workflow._descendants(popup)
                        if isinstance(w, Gtk.ScrolledWindow))
        self.assertGreater(scroller.get_vadjustment().get_upper(),
                           scroller.get_vadjustment().get_page_size())
        popup.popdown()
