# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Real-display help behavior; use a temporary app profile, never user projects."""
import os
import copy
import time
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, Gio, GLib
from parameter_help_ui import HOVER_DELAY_MS, LEAVE_DELAY_MS


def pump(seconds=.08):
    context=GLib.MainContext.default()
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        while context.pending():context.iteration(False)
        time.sleep(.004)


class ParameterHelpGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            raise unittest.SkipTest('A working local GTK display is required')
        cls.temp=TemporaryDirectory(prefix='ratiolab-help-gui-')
        cls.env=patch.dict(os.environ, {'XDG_CONFIG_HOME': cls.temp.name, 'XDG_DATA_HOME': cls.temp.name, 'APPDATA': cls.temp.name, 'LOCALAPPDATA': cls.temp.name})
        cls.env.start()
        from app import ReducerApp
        cls.app=ReducerApp()
        cls.app.set_application_id('local.ratiolab.parameterhelp.p'+str(os.getpid()))
        cls.app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        cls.app.register(None);cls.app.activate();pump(.4)
        if not cls.app.canvas.gl or cls.app.canvas.failure:
            raise RuntimeError('Actual OpenGL preview initialization failed: '+str(cls.app.canvas.failure))

    @classmethod
    def tearDownClass(cls):
        cls.app.parameter_help.close()
        for window in cls.app.get_windows():window.destroy()
        cls.env.stop();cls.temp.cleanup()

    def tearDown(self):
        self.app.parameter_help.close()
        self.app.text_size.set_selected(0)

    def test_delayed_hover_preserves_pending_input_and_focus(self):
        a=self.app;owner=a.parameter_help;b=owner.bindings['module']
        b.control.grab_focus();b.control.set_text('1e-')
        focus=b.control.get_root().get_focus()
        owner.enter(b);pump(.1)
        self.assertIsNone(owner.popover)
        pump(HOVER_DELAY_MS/1000+.08)
        self.assertTrue(owner.popover.get_mapped())
        self.assertEqual(b.control.get_root().get_focus(),focus)
        self.assertEqual(b.control.get_text(),'1e-')
        owner.leave();pump(LEAVE_DELAY_MS/1000+.05)
        self.assertIsNone(owner.popover)
        b.control.set_text('2');b.control.update()

    def test_keyboard_clickable_info_escape_and_rebuild(self):
        a=self.app;owner=a.parameter_help;b=owner.bindings['module']
        b.button.emit('clicked');pump()
        self.assertTrue(owner.popover.get_mapped())
        self.assertTrue(b.key_pressed(None,Gdk.KEY_Escape,0,0))
        self.assertIsNone(owner.popover)
        self.assertTrue(b.key_pressed(None,Gdk.KEY_F1,0,0));pump()
        a.rebuild_options({'variant':'helical'});pump()
        self.assertIsNone(owner.popover)
        self.assertIn('variant', owner.bindings)
        self.assertIn('input_rpm', owner.bindings)
        self.assertTrue(set(a.inputs) <= set(owner.bindings))

    def test_help_tracks_actual_allocation_and_text_scale(self):
        a=self.app;b=a.parameter_help.bindings['module']
        b.open();pump();popup=a.parameter_help.popover
        initial=popup.get_width()
        a.text_size.set_selected(2);pump(.2)
        root=b.label.get_root()
        self.assertGreater(popup.get_width(),initial)
        self.assertLess(popup.get_width(),root.get_width())
        self.assertLessEqual(popup.get_height(),root.get_height())
        surface=popup.get_surface()
        if isinstance(surface,Gdk.Popup):
            self.assertGreaterEqual(surface.get_position_x(),0)
            self.assertGreaterEqual(surface.get_position_y(),0)
            self.assertLessEqual(surface.get_position_x()+surface.get_width(),root.get_width())
            self.assertLessEqual(surface.get_position_y()+surface.get_height(),root.get_height())

    def test_value_badge_never_commits_or_hides_a_numeric_draft(self):
        a=self.app;owner=a.parameter_help;b=owner.bindings['module']
        b.control.grab_focus();b.control.set_text('1e-')
        focus=a.win.get_focus();snapshot=a.project_snapshot()
        owner.open(b);pump()
        self.assertEqual(owner.value_label.get_text(),'Editing value')
        self.assertEqual(b.control.get_text(),'1e-')
        self.assertEqual(a.win.get_focus(),focus)
        self.assertEqual(a.project_snapshot(),snapshot)
        b.control.set_text('2.125');pump()
        self.assertEqual(owner.value_label.get_text(),'2.125 mm')
        owner.close();b.control.set_text('2');b.control.update()

    def test_guide_pinning_keeps_hover_help_open(self):
        owner=self.app.parameter_help;b=owner.bindings['module']
        owner.open(b);pump()
        self.assertIs(owner.body.get_first_child(),owner.diagram_expander)
        self.assertIs(owner.diagram_expander.get_child(),owner.drawing)
        self.assertFalse(owner.diagram_expander.get_expanded())
        self.assertFalse(owner.drawing.get_visible())
        self.assertFalse(owner.pinned)
        self.assertTrue(owner.details.get_visible())
        owner.pin.set_active(True);owner.leave()
        pump(LEAVE_DELAY_MS/1000+.05)
        self.assertTrue(owner.popover.get_mapped())
        self.assertIn('Esc',owner.footer_hint.get_text())
        owner.pin.set_active(False)
        self.assertFalse(owner.pinned)
        self.assertIn('F1',owner.footer_hint.get_text())

    def test_compact_diagram_expands_and_really_shrinks_without_project_changes(self):
        a=self.app;owner=a.parameter_help
        before=copy.deepcopy((a.project_snapshot(),a.document.states,a.document.index))
        for key in ('module','width'):
            b=owner.bindings[key]
            for index,scale in enumerate((1,1.25,1.5)):
                with self.subTest(parameter=key,text_scale=scale):
                    owner.close();a.text_size.set_selected(index);pump()
                    b.open();pump(.12)
                    popup=owner.popover;root=b.label.get_root()
                    self.assertEqual(owner.scroll.get_min_content_width(),round(320*scale))
                    self.assertGreaterEqual(owner.scroll.get_width(),round(320*scale))
                    compact=popup.get_width()
                    self.assertEqual(owner.diagram_expander.get_label(),'Show diagram')
                    owner.diagram_expander.grab_focus()
                    owner.diagram_expander.emit('activate');pump(.18)
                    self.assertTrue(owner.diagram_expander.get_expanded())
                    self.assertTrue(owner.drawing.get_visible())
                    self.assertEqual(owner.diagram_expander.get_label(),'Diagram')
                    self.assertGreater(popup.get_width(),compact+40*scale)
                    self.assertGreaterEqual(owner.drawing.get_width(),round(358*scale))
                    self.assertAlmostEqual(owner.drawing.get_height()/owner.drawing.get_width(),220/360,delta=.01)
                    owner.diagram_expander.emit('activate');pump(.18)
                    self.assertFalse(owner.drawing.get_visible())
                    self.assertEqual(popup.get_width(),compact)
                    self.assertGreaterEqual(owner.scroll.get_width(),round(320*scale))
                    self.assertEqual(owner.scroll.get_min_content_width(),round(320*scale))
                    surface=popup.get_surface()
                    if isinstance(surface,Gdk.Popup):
                        self.assertGreaterEqual(surface.get_position_x(),0)
                        self.assertGreaterEqual(surface.get_position_y(),0)
                        self.assertLessEqual(surface.get_position_x()+surface.get_width(),root.get_width())
                        self.assertLessEqual(surface.get_position_y()+surface.get_height(),root.get_height())
                    self.assertEqual((a.project_snapshot(),a.document.states,a.document.index),before)

    def test_optional_friction_help_distinguishes_unknown_zero_and_blank_draft(self):
        from geometry import generate
        from gui_workflow import show_page
        a=self.app;key='worm_static_friction'
        def state():
            return copy.deepcopy((a.project_snapshot(),a.option_values,a.values,
                                  a.document.states,a.document.index,a.design.values))
        try:
            a.load_config_data(dict(format='solidcraft-riduttori/1',family='worm',
                                   parameters=generate('worm',{}).values))
            show_page(a,'motion');a.io_frame.set_expanded(True);pump()
            owner=a.parameter_help;b=owner.bindings[key]
            self.assertIs(b.control,a.io_friction_entry)
            before=state()
            with patch.object(a,'rebuild_options',wraps=a.rebuild_options) as rebuild:
                b.motion.emit('enter',0.,0.);pump(HOVER_DELAY_MS/1000+.08)
                self.assertTrue(owner.popover.get_mapped())
                self.assertEqual(owner.value_label.get_text(),'Not specified')
                self.assertFalse(owner.drawing.get_visible())
                self.assertFalse(owner.diagram_expander.get_visible())
                self.assertEqual(owner.details.get_label(),'Model and limits')
                self.assertEqual(owner.footer.get_first_child().get_text(),'Static contact model')
                self.assertEqual(state(),before)
                owner.close();b.button.emit('clicked');pump()
                self.assertTrue(owner.popover.get_mapped())
                owner.close();b.control.grab_focus()
                self.assertTrue(b.key_controllers[0].emit('key-pressed',Gdk.KEY_F1,0,0));pump()
                self.assertTrue(owner.popover.get_mapped())
                self.assertEqual(state(),before)
                b.control.set_text('0');pump()
                self.assertEqual(owner.value_label.get_text(),'0')
                self.assertEqual(state(),before)
                rebuild.assert_not_called()
            owner.close()
            # Explicit setup of saved physical evidence, independently of help.
            a.rebuild_options({key:0.2});pump()
            b=owner.bindings[key];before=state()
            with patch.object(a,'rebuild_options',wraps=a.rebuild_options) as rebuild:
                b.control.set_text('');b.open();pump()
                self.assertEqual(owner.value_label.get_text(),'Editing value')
                self.assertEqual(state(),before)
                self.assertEqual(a.option_values[key],0.2)
                rebuild.assert_not_called()
        finally:
            a.parameter_help.close()
            a.load_config_data(dict(format='solidcraft-riduttori/1',family='parallel',
                                   parameters=generate('parallel',{}).values))
            show_page(a,'geometry')
            pump()


if __name__ == '__main__':
    unittest.main()
