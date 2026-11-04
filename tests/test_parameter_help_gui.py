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
        for _ in range(24):
            if not context.pending() or time.monotonic() >= until:break
            context.iteration(False)
        time.sleep(.004)


def wait_for(predicate, seconds=1.5):
    until=time.monotonic()+seconds
    while not predicate() and time.monotonic()<until:
        pump(.02)
    return predicate()


def emit_motion(controller, signal, *args):
    controller._help_manual_signal=True
    try:
        return controller.emit(signal,*args)
    finally:
        controller._help_manual_signal=False


class ParameterHelpGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            if os.environ.get('RATIOLAB_REQUIRE_DISPLAY') == '1':
                raise RuntimeError('The required real GTK display is unavailable')
            raise unittest.SkipTest('A working local GTK display is required')
        cls.temp=TemporaryDirectory(prefix='ratiolab-help-gui-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.env=patch.dict(os.environ, {'XDG_CONFIG_HOME': cls.temp.name, 'XDG_DATA_HOME': cls.temp.name, 'APPDATA': cls.temp.name, 'LOCALAPPDATA': cls.temp.name})
        cls.env.start()
        cls.addClassCleanup(cls.env.stop)
        # Keep mapped allocation/rendering real, but make synthetic motion
        # transitions independent of the user's stationary physical pointer.
        # Otherwise a popup resize can generate an unrelated native re-entry.
        motion_type=Gtk.EventControllerMotion
        cls.motion_type=motion_type
        cls.motions=[]
        def controlled_motion(*args, **kwargs):
            motion=motion_type(*args, **kwargs)
            native_connect=motion.connect
            def connect(signal, callback, *data):
                if signal in ('enter','leave'):
                    def manual_callback(*events):
                        if getattr(motion,'_help_manual_signal',False):
                            return callback(*events)
                    return native_connect(signal,manual_callback,*data)
                return native_connect(signal,callback,*data)
            motion.connect=connect
            cls.motions.append((motion,motion.get_propagation_phase()))
            motion.set_propagation_phase(Gtk.PropagationPhase.NONE)
            return motion
        # Help uses the Python constructor; the cube uses GTK's .new() factory.
        # Both must retain real mapped controllers and the same manual filtering.
        controlled_motion.new=controlled_motion
        cls.motion_patch=patch.object(Gtk,'EventControllerMotion',controlled_motion)
        cls.motion_patch.start();cls.addClassCleanup(cls.motion_patch.stop)
        from app import ReducerApp
        cls.app=ReducerApp()
        cls.app.set_application_id('local.ratiolab.parameterhelp.'+cls.__name__.lower()+'.p'+str(os.getpid()))
        cls.app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        cls.app.register(None);cls.app.activate();pump(.4)
        if not cls.app.canvas.gl or cls.app.canvas.failure:
            raise RuntimeError('Actual OpenGL preview initialization failed: '+str(cls.app.canvas.failure))

    @classmethod
    def tearDownClass(cls):
        cls.app.parameter_help.close()
        for motion,phase in cls.motions:motion.set_propagation_phase(phase)
        for window in cls.app.get_windows():window.destroy()

    def tearDown(self):
        self.app.parameter_help.close()
        self.app.parameter_help.suppressed = None
        self.app.text_size.set_selected(0)
        pump()

    def test_motion_constructor_and_new_share_manual_enter_leave_filtering(self):
        controllers=(Gtk.EventControllerMotion(),Gtk.EventControllerMotion.new())
        for motion in controllers:
            self.assertIsInstance(motion,self.motion_type)
            self.assertEqual(motion.get_propagation_phase(),Gtk.PropagationPhase.NONE)
            received=[]
            motion.connect('enter',lambda *_:received.append('enter'))
            motion.connect('leave',lambda *_:received.append('leave'))
            motion.emit('enter',1.,1.);motion.emit('leave')
            self.assertEqual(received,[])
            emit_motion(motion,'enter',1.,1.);emit_motion(motion,'leave')
            self.assertEqual(received,['enter','leave'])

    def test_visible_choice_hover_f1_escape_and_focus_preserve_selection(self):
        from geometry import generate
        from gui_workflow import show_page
        a=self.app
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='parallel',
                               parameters=generate('parallel').values))
        show_page(a,'assembly');a.sections['bearings'][0].set_expanded(True);pump()
        owner=a.parameter_help;b=owner.bindings['bearing_mode']
        self.assertIsInstance(b.control,Gtk.DropDown)
        self.assertTrue(b.control.get_mapped());self.assertFalse(b.button.get_mapped())
        self.assertTrue(b.control.grab_focus());focus=a.win.get_focus()
        selected=b.control.get_selected()
        before=copy.deepcopy((a.project_snapshot(),a.document.states,a.document.index))
        emit_motion(b.motion,'enter',1.,1.)
        self.assertTrue(wait_for(lambda:owner.popover is not None and owner.popover.get_mapped()))
        self.assertIs(owner.active,b);self.assertIs(a.win.get_focus(),focus)
        emit_motion(b.motion,'leave');emit_motion(owner.popup_motion,'enter',1.,1.)
        pump(LEAVE_DELAY_MS/1000+.05)
        self.assertIs(owner.active,b)
        emit_motion(owner.popup_motion,'leave')
        self.assertTrue(wait_for(lambda:owner.popover is None))
        self.assertTrue(b.key_controllers[0].emit('key-pressed',Gdk.KEY_F1,0,Gdk.ModifierType(0)))
        self.assertTrue(wait_for(lambda:owner.popover is not None and owner.popover.get_mapped()))
        self.assertEqual(owner.activation,'explicit');self.assertIs(a.win.get_focus(),focus)
        owner.close_button.grab_focus();pump()
        keys=next(c for c in owner.popover.observe_controllers()
                  if isinstance(c,Gtk.EventControllerKey))
        self.assertTrue(keys.emit('key-pressed',Gdk.KEY_Escape,0,Gdk.ModifierType(0)))
        self.assertIsNone(owner.popover);self.assertIs(a.win.get_focus(),focus)
        self.assertEqual(b.control.get_selected(),selected)
        self.assertEqual((a.project_snapshot(),a.document.states,a.document.index),before)

    def test_delayed_hover_preserves_pending_input_and_focus(self):
        a=self.app;owner=a.parameter_help;b=owner.bindings['module']
        b.control.grab_focus();b.control.set_text('1e-')
        focus=b.control.get_root().get_focus()
        owner.close();before=GLib.get_monotonic_time();owner.enter(b)
        after=GLib.get_monotonic_time()
        source=GLib.MainContext.default().find_source_by_id(owner.timer)
        self.assertIsNotNone(source)
        self.assertGreaterEqual(source.get_ready_time(),before+HOVER_DELAY_MS*1000-1000)
        self.assertLessEqual(source.get_ready_time(),after+HOVER_DELAY_MS*1000)
        self.assertIsNone(owner.popover)
        self.assertTrue(wait_for(lambda: owner.popover is not None and owner.popover.get_mapped()))
        self.assertEqual(b.control.get_root().get_focus(),focus)
        self.assertEqual(b.control.get_text(),'1e-')
        emit_motion(b.row_motion,'leave');emit_motion(b.motion,'leave');emit_motion(owner.popup_motion,'leave')
        self.assertTrue(wait_for(lambda: owner.popover is None))
        b.control.set_text('2');b.control.update()

    def test_keyboard_clickable_info_escape_and_rebuild(self):
        a=self.app;owner=a.parameter_help;b=owner.bindings['module']
        self.assertFalse(b.button.get_mapped())
        self.assertTrue(b.control.get_mapped());self.assertTrue(b.control.grab_focus())
        focus=a.win.get_focus()
        self.assertTrue(b.key_controllers[0].emit('key-pressed',Gdk.KEY_F1,0,Gdk.ModifierType(0)))
        pump()
        self.assertTrue(owner.popover.get_mapped())
        self.assertEqual(owner.activation,'explicit')
        self.assertIs(a.win.get_focus(),focus)
        owner.close_button.grab_focus()
        self.assertTrue(b.key_pressed(None,Gdk.KEY_Escape,0,0))
        self.assertIsNone(owner.popover)
        self.assertIs(a.win.get_focus(),focus)
        class TouchBegin:
            def get_event_type(self):return Gdk.EventType.TOUCH_BEGIN
        b.button_event(None,TouchBegin());b.button.emit('clicked');pump()
        self.assertEqual(owner.activation,'explicit')
        owner.close()
        self.assertTrue(b.key_pressed(None,Gdk.KEY_F1,0,0));pump()
        old_motion,old_expander=owner.popup_motion,owner.diagram_expander
        owner.open(b,activation='explicit');pump()
        current_popup=owner.popover
        emit_motion(owner.popup_motion,'enter',1.,1.)
        emit_motion(old_motion,'leave')
        self.assertTrue(owner.over_popup)
        emit_motion(owner.popup_motion,'leave')
        emit_motion(old_motion,'enter',1.,1.)
        self.assertFalse(owner.over_popup)
        old_expander.set_expanded(True)
        self.assertIs(owner.popover,current_popup)
        self.assertFalse(owner.drawing.get_visible())
        a.rebuild_options({'variant':'helical'});pump()
        self.assertIsNone(owner.popover)
        self.assertNotIn('variant', owner.bindings)  # Variants now live in the illustrated catalog.
        self.assertIs(owner.section_binding.control,a.catalog_button)
        self.assertIs(owner.bindings['helix'].control,a.inputs['helix'])
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
        b.control.set_text('2.125')
        self.assertTrue(wait_for(lambda: owner.value_label.get_text()=='2.125 mm'),
                        owner.value_label.get_text())
        owner.close();b.control.set_text('2');b.control.update()

    def test_pointer_card_keeps_alive_across_row_and_popup_then_closes_after_expand(self):
        owner=self.app.parameter_help;b=owner.bindings['module']
        b.control.grab_focus();focus=self.app.win.get_focus()
        emit_motion(b.row_motion,'enter',1.,1.)
        self.assertTrue(wait_for(lambda: owner.popover is not None and owner.popover.get_mapped()))
        popup=owner.popover
        self.assertTrue(popup.get_mapped())
        self.assertFalse(popup.get_autohide())
        self.assertEqual(owner.activation,'pointer')
        self.assertFalse(hasattr(owner,'pin'))
        self.assertIs(owner.body.get_first_child(),owner.diagram_expander)
        self.assertFalse(owner.drawing.get_visible())
        emit_motion(b.row_motion,'leave');pump(LEAVE_DELAY_MS/2000)
        emit_motion(owner.popup_motion,'enter',1.,1.)
        pump(LEAVE_DELAY_MS/1000+.05)
        self.assertIs(owner.popover,popup)
        owner.diagram_expander.grab_focus()
        owner.diagram_expander.emit('activate');pump(.15)
        self.assertTrue(owner.drawing.get_visible())
        emit_motion(b.row_motion,'leave');emit_motion(b.motion,'leave');emit_motion(owner.popup_motion,'leave')
        self.assertTrue(wait_for(lambda: owner.popover is None),
                        (owner.activation,b.over_row,b.over_control,owner.over_popup))
        self.assertIs(self.app.win.get_focus(),focus)
        class MousePress:
            def get_event_type(self):return Gdk.EventType.BUTTON_PRESS
        b.button_event(None,MousePress());b.button.emit('clicked');pump()
        self.assertEqual(owner.activation,'pointer')
        emit_motion(b.row_motion,'leave');emit_motion(b.motion,'leave');emit_motion(owner.popup_motion,'leave')
        self.assertTrue(wait_for(lambda: owner.popover is None))

    def test_escape_close_suppresses_hover_until_source_leave_reentry(self):
        owner=self.app.parameter_help;b=owner.bindings['module']
        emit_motion(b.row_motion,'enter',1.,1.)
        self.assertTrue(wait_for(lambda: owner.popover is not None and owner.popover.get_mapped()))
        self.assertTrue(b.key_pressed(None,Gdk.KEY_Escape,0,0))
        self.assertIsNone(owner.popover)
        owner.enter(b);pump(HOVER_DELAY_MS/1000+.08)
        self.assertIsNone(owner.popover)
        emit_motion(b.row_motion,'leave');emit_motion(b.row_motion,'enter',1.,1.)
        self.assertTrue(wait_for(lambda: owner.popover is not None and owner.popover.get_mapped()))
        emit_motion(b.row_motion,'leave')

    def test_section_uses_same_card_and_preserves_parameter_guides_on_rebuild(self):
        owner=self.app.parameter_help
        b=owner.section_binding
        self.assertIsNotNone(b)
        snapshot=copy.deepcopy((self.app.project_snapshot(),self.app.document.states,self.app.document.index))
        emit_motion(b.row_motion,'enter',1.,1.)
        self.assertTrue(wait_for(lambda: owner.popover is not None and owner.popover.get_mapped()))
        self.assertEqual(owner.title.get_text(),'Model & dimensions')
        self.assertFalse(owner.diagram_expander.get_visible())
        self.assertFalse(owner.value_label.get_visible())
        self.assertIn('Choose',owner.help_for(b).meaning)
        owner.close();emit_motion(b.row_motion,'leave')
        parameter=owner.bindings['module'];parameter.open();pump()
        self.assertIs(owner.active,parameter)
        self.assertTrue(owner.diagram_expander.get_visible())
        self.assertEqual((self.app.project_snapshot(),self.app.document.states,self.app.document.index),snapshot)
        self.app.rebuild_options({'variant':'helical'});pump()
        self.assertIs(owner.section_binding,b)
        self.assertIn(b,owner.all_bindings)

    def test_compact_diagram_expands_and_really_shrinks_without_project_changes(self):
        a=self.app;owner=a.parameter_help
        before=copy.deepcopy((a.project_snapshot(),a.document.states,a.document.index))
        for key in ('module','width'):
            b=owner.bindings[key]
            for index,scale in enumerate((1,1.25,1.5)):
                with self.subTest(parameter=key,text_scale=scale):
                    owner.close();a.text_size.set_selected(index);pump()
                    from gui_workflow import show_page
                    show_page(a,a.input_pages[key]);b.control.grab_focus();pump()
                    body=a.pages[a.input_pages[key]];viewport=a.page_scrolls[a.input_pages[key]]
                    ok,anchor=b.row.compute_bounds(body);self.assertTrue(ok)
                    viewport.get_vadjustment().clamp_page(max(0,anchor.get_y()-8),
                                                        anchor.get_y()+anchor.get_height()+8)
                    def anchor_visible():
                        ok,rect=b.row.compute_bounds(viewport)
                        return ok and rect.get_y()>=-1 and rect.get_y()+rect.get_height()<=viewport.get_height()+1
                    self.assertTrue(wait_for(anchor_visible),'Parameter anchor clipped')
                    self.assertTrue(b.key_pressed(None,Gdk.KEY_F1,0,0))
                    self.assertTrue(wait_for(lambda: owner.popover is not None and
                        owner.popover.get_mapped() and owner.scroll.get_width()>=round(286*scale)))
                    popup=owner.popover;root=b.label.get_root()
                    self.assertEqual(owner.scroll.get_min_content_width(),round(286*scale))
                    self.assertGreaterEqual(owner.scroll.get_width(),round(286*scale))
                    compact=popup.get_width()
                    self.assertEqual(owner.diagram_expander.get_label(),'Show diagram')
                    owner.diagram_expander.grab_focus()
                    owner.diagram_expander.emit('activate')
                    self.assertTrue(wait_for(lambda: owner.drawing.get_visible() and
                        popup.get_width()>compact+40*scale))
                    self.assertTrue(owner.diagram_expander.get_expanded())
                    self.assertTrue(owner.drawing.get_visible())
                    self.assertEqual(owner.diagram_expander.get_label(),'Diagram')
                    self.assertGreater(popup.get_width(),compact+40*scale)
                    self.assertGreaterEqual(owner.drawing.get_width(),round(360*scale))
                    self.assertAlmostEqual(owner.drawing.get_height()/owner.drawing.get_width(),220/360,delta=.01)
                    emit_motion(owner.popup_motion,'enter',1.,1.)
                    emit_motion(owner.popup_motion,'leave');pump(LEAVE_DELAY_MS/1000+.05)
                    self.assertIs(owner.popover,popup)
                    self.assertTrue(popup.get_mapped())
                    owner.diagram_expander.emit('activate')
                    self.assertTrue(wait_for(lambda: not owner.drawing.get_visible() and
                        popup.get_width()==compact))
                    self.assertFalse(owner.drawing.get_visible())
                    self.assertEqual(popup.get_width(),compact)
                    self.assertGreaterEqual(owner.scroll.get_width(),round(286*scale))
                    self.assertEqual(owner.scroll.get_min_content_width(),round(286*scale))
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
                emit_motion(b.motion,'enter',0.,0.)
                self.assertTrue(wait_for(lambda: owner.popover is not None and owner.popover.get_mapped()))
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


class ParameterHelpIconGuiTests(unittest.TestCase):
    """Fresh native controls for pixel/allocation checks, separate from draft tests."""
    @classmethod
    def setUpClass(cls):
        ParameterHelpGuiTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        ParameterHelpGuiTests.tearDownClass.__func__(cls)

    def tearDown(self):
        ParameterHelpGuiTests.tearDown(self)

    def test_parameter_icons_are_absent_without_losing_f1_or_native_stepping(self):
        from geometry import generate
        from gui_workflow import show_page
        from ratiolab_checks import _wait_for_frame
        a=self.app
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='parallel',parameters=generate('parallel').values))
        show_page(a,'geometry');a.workspace_paned.set_position(230)
        self.assertTrue(wait_for(lambda:a.parameter_panel.get_width()==230))
        before=copy.deepcopy(a.project_snapshot())
        for scale in (0,1,2):
            a.text_size.set_selected(scale);_wait_for_frame(a.canvas,GLib.MainContext.default())
            owner=a.parameter_help
            for binding in owner.all_bindings:
                self.assertFalse(binding.button.get_visible())
                self.assertFalse(binding.glyph.get_mapped())
            b=owner.bindings['module'];b.control.grab_focus()
            self.assertTrue(b.key_controllers[0].emit('key-pressed',Gdk.KEY_F1,0,0));pump()
            self.assertTrue(owner.popover.get_mapped())
            self.assertIs(owner.active,b)
            owner.close();_wait_for_frame(a.canvas,GLib.MainContext.default())
            self.assertEqual(a.parameter_panel.get_width(),230)
            control=owner.bindings['pinion'].control;control.grab_focus();pump()
            child=control.get_first_child();steps=[]
            while child:
                if isinstance(child,Gtk.Button):steps.append(child)
                child=child.get_next_sibling()
            self.assertTrue(steps and all(button.get_visible() for button in steps))
        self.assertEqual(a.project_snapshot(),before)


if __name__ == '__main__':
    unittest.main()
