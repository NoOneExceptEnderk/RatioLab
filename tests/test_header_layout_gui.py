# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Native title bar and File menu must retain project and preference state."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk, Gdk, Gio
import app as app_module
from theme_preferences import BASE_PALETTES
from ui_language import translate
from updates import select_release
import test_workspace_theme_preferences as fixtures
from test_interference_gui import pump,wait_until
from test_updates import release


class HeaderLayoutTests(unittest.TestCase):
    setUpClass = fixtures.WorkspaceThemePreferencesTests.__dict__['setUpClass']
    setUp = fixtures.WorkspaceThemePreferencesTests.setUp
    close_apps = fixtures.WorkspaceThemePreferencesTests.close_apps
    launch = fixtures.WorkspaceThemePreferencesTests.launch

    def ready(self):
        a=self.launch()
        self.assertTrue(wait_until(lambda:not a.pending and not a._geometry_waiting and not a.busy))
        return a

    @staticmethod
    def root_child(widget,parent):
        while widget.get_parent() is not parent:widget=widget.get_parent()
        return widget

    def assert_brand_before_file(self,a):
        ok,brand=a.header_brand.compute_bounds(a.header_start);self.assertTrue(ok)
        ok,file_menu=a.file_menu.compute_bounds(a.header_start);self.assertTrue(ok)
        self.assertAlmostEqual(brand.get_x(),0,delta=1)
        self.assertLessEqual(brand.get_x()+brand.get_width(),file_menu.get_x())

    def test_brand_before_file_and_theme_edited_only_in_settings(self):
        a=self.ready();toolbar=a.secondary_toolbar
        self.assertIs(a.file_menu,a.project_menu)
        self.assertEqual(a.file_menu.get_label(),'File')
        self.assertIsInstance(a.file_menu.get_popover(),Gtk.PopoverMenu)
        self.assertFalse(a.file_menu.get_popover().get_has_arrow())
        self.assert_brand_before_file(a)
        self.assertIs(self.root_child(a.undo_button,toolbar),toolbar.get_first_child())
        controls=[a.undo_button,a.redo_button,a.family_chip,a.language_menu,a.settings_button]
        xs=[]
        for widget in controls:
            ok,bounds=widget.compute_bounds(toolbar);self.assertTrue(ok);xs.append(bounds.get_x())
        self.assertEqual(xs,sorted(xs))
        for widget in (a.file_menu,a.cad_split,a.export_menu):
            ok,bounds=widget.compute_bounds(a.win);self.assertTrue(ok)
            ok,bar=toolbar.compute_bounds(a.win);self.assertTrue(ok)
            self.assertLess(bounds.get_y(),bar.get_y())
        for widget,icon in [(a.undo_button,'undo'),(a.redo_button,'redo'),
                            (a.cad_action,'cad-link'),(a.export_menu,'download'),
                            (a.language_menu,'globe'),(a.settings_button,'settings')]:
            self.assertEqual(widget.workspace_icon.glyph_name,icon)
        self.assertIsNone(a.theme_switch.get_parent());self.assertIsNone(a.theme_switch.get_root())
        self.assertFalse(a.theme_switch.get_mapped())
        before=deepcopy(a.project_snapshot());token=a.document.token
        a.settings_button.emit('clicked');pump(.1)
        a.settings.theme.set_selected(1)
        self.assertEqual(a.workspace_theme,'light');self.assertEqual(a.canvas.theme,'light')
        a.settings.dialog.close()
        self.assertEqual(a.project_snapshot(),before);self.assertEqual(a.document.token,token)

    def test_native_file_actions_busy_state_shortcuts_and_existing_popovers(self):
        calls=[]
        def save(app,*_):calls.append(app)
        with patch.object(app_module.ReducerApp,'save_dialog',save):a=self.ready()
        popup=a.file_menu.get_popover();model=popup.get_menu_model();commands=[]
        for i in range(model.get_n_items()):
            section=model.get_item_link(i,Gio.MENU_LINK_SECTION);self.assertIsNotNone(section)
            for j in range(section.get_n_items()):
                commands.append(section.get_item_attribute_value(j,Gio.MENU_ATTRIBUTE_ACTION,None).get_string())
        self.assertEqual(commands,['app.new','app.open','app.recent','app.save','app.save-as',
                                   'app.reset-defaults','app.undo-reset','app.updates'])
        self.assertEqual(a.get_accels_for_action('app.save'),a.keyboard.config['bindings']['save'])
        a.file_menu.popup();self.assertTrue(wait_until(popup.get_mapped))
        a.lookup_action('save').activate(None);self.assertEqual(calls,[a]);popup.popdown()
        button=a.file_command_buttons['save'];button.set_sensitive(False)
        self.assertFalse(a.lookup_action('save').get_enabled())
        a.lookup_action('save').activate(None);self.assertEqual(calls,[a])
        button.set_sensitive(True);self.assertTrue(a.lookup_action('save').get_enabled())
        self.assertFalse(a.lookup_action('undo-reset').get_enabled())
        a.undo_reset.set_visible(True);self.assertTrue(a.lookup_action('undo-reset').get_enabled())
        a.undo_reset.set_visible(False);self.assertFalse(a.lookup_action('undo-reset').get_enabled())
        a.export_menu.popup();self.assertTrue(wait_until(a.export_menu.get_popover().get_mapped))
        a.export_menu.popdown();pump(.05)
        a.cad_menu.popup();self.assertTrue(wait_until(a.cad_menu.get_popover().get_mapped))
        self.assertEqual(a.cad_stack.get_visible_child_name(),'compact');a.cad_menu.popdown()

    def test_translated_header_and_native_menu_with_large_text_and_long_name(self):
        a=self.ready();before=deepcopy(a.project_snapshot());scene=a.canvas.scene;token=a.document.token
        a.project_title.set_text('A very long project filename that should ellipsize without moving RatioLab')
        for language in ('en','it','fr','ta'):
            a.language.change(language)
            for mode in (0,1):
                a.theme_selector.set_selected(mode)
                for scale in (0,1,2):
                    a.text_size.set_selected(scale);pump(.14)
                    self.assert_brand_before_file(a)
                    self.assertEqual(a.file_menu.get_label(),translate('File',language))
                    for widget in (a.file_menu,a.header_brand,a.project_title,a.undo_button,a.redo_button,
                                   a.family_chip,a.language_menu,a.settings_button,a.cad_split,a.export_menu):
                        self.assertTrue(widget.get_mapped())
                        ok,b=widget.compute_bounds(a.win);self.assertTrue(ok)
                        self.assertGreaterEqual(b.get_x(),0)
                        self.assertLessEqual(b.get_x()+b.get_width(),a.win.get_width()+1)
                    a.file_menu.popup();self.assertTrue(wait_until(a.file_menu.get_popover().get_mapped))
                    a.file_menu.popdown();pump(.03)
                    self.assertFalse(a.theme_switch.get_mapped())
        self.assertEqual(a.project_snapshot(),before);self.assertIs(a.canvas.scene,scene)
        self.assertEqual(a.document.token,token)

    def test_update_button_in_workspace_opens_existing_release_window(self):
        a=self.ready();controller=a.updates;button=controller.button
        self.assertFalse(button.get_mapped())
        a.win.set_default_size(1366,768)
        a.language.change('it')
        a.text_size.set_selected(2)
        controller.release=select_release([release('v0.2.5')], current='0.2.4', channel='stable')
        controller.refresh()
        self.assertTrue(wait_until(button.get_mapped))
        self.assertTrue(wait_until(lambda:controller.badge_label.get_text()=='Aggiorna a 0.2.5'))
        self.assertIsNone(controller.window)
        for mode, theme in enumerate(('dark', 'light')):
            a.theme_selector.set_selected(mode);pump(.15)
            expected=Gdk.RGBA();self.assertTrue(expected.parse(BASE_PALETTES[theme]['on_accent']))
            color=controller.badge_label.get_style_context().get_color()
            for channel in ('red', 'green', 'blue'):
                self.assertAlmostEqual(getattr(color,channel),getattr(expected,channel),delta=.01)
        self.assertIs(button.get_next_sibling(),a.cad_split)
        self.assertEqual(button.workspace_icon.glyph_name,'download')
        self.assertTrue(button.workspace_icon.get_mapped())
        self.assertEqual(button.workspace_icon.get_width(),button.workspace_icon.get_height())
        self.assert_brand_before_file(a)
        ok,badge=button.compute_bounds(a.win);self.assertTrue(ok)
        ok,brand=a.header_brand.compute_bounds(a.win);self.assertTrue(ok)
        self.assertLessEqual(brand.get_x()+brand.get_width(),badge.get_x())
        button.emit('clicked')
        self.assertTrue(wait_until(controller.window.get_mapped))
        self.assertIs(controller.window.get_transient_for(),a.win)
        self.assertEqual(controller.displayed_release.version,'0.2.5')


if __name__=='__main__':unittest.main()
