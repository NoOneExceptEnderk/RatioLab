# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Real GTK integration for the dock, explicit export scope and compact layout."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import time
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk,Gio,GLib
import app as module
from geometry import generate
from test_interference_gui import pump,wait_until


class ToolWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            raise unittest.SkipTest('GTK display required')
        cls.temp=TemporaryDirectory(prefix='ratiolab-tool-workspace-')
        root=Path(cls.temp.name)
        cls.env=patch.dict(os.environ,dict(XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'),APPDATA=str(root/'roaming'),LOCALAPPDATA=str(root/'local')))
        cls.env.start()
        cls.app=module.ReducerApp();cls.app.set_application_id(f'local.ratiolab.tools.p{os.getpid()}')
        cls.app.set_flags(Gio.ApplicationFlags.NON_UNIQUE);cls.app.register(None);cls.app.activate();pump(.15)

    @classmethod
    def tearDownClass(cls):
        cls.app.text_size.set_selected(0)
        for win in cls.app.get_windows():win.destroy()
        pump();cls.env.stop();cls.temp.cleanup()

    def setUp(self):
        a=self.app
        for c in (a.components,a.combination_search,a.interference):
            if c.window:c.window.close()
        a.text_size.set_selected(0);a.pick_mode.set_selected(1)
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='parallel',parameters=generate('parallel').values))
        monitor=Gdk.Display.get_default().get_monitor_at_surface(a.win.get_surface())
        # X11 exposes the desktop work area; other backends expose its monitor.
        area=monitor.get_workarea() if hasattr(monitor,'get_workarea') else monitor.get_geometry()
        # Keep the compact test inside the available desktop. The window
        # manager can allocate less client space to accommodate decorations.
        self.window_limit=(min(1280,area.width),min(800,area.height))
        a.win.unfullscreen();a.win.unmaximize();pump(.1)
        a.win.set_visible(False);a.win.set_default_size(*self.window_limit);a.win.present();pump(.15)
        # Some window managers automatically maximize large newly mapped windows.
        a.win.unmaximize()
        self.assertTrue(wait_until(lambda:not a.win.is_maximized(),2))
        pump(.15)
        self.assertLessEqual(a.win.get_width(),self.window_limit[0],self.layout_budget())
        self.assertLessEqual(a.win.get_height(),self.window_limit[1],self.layout_budget())

    def layout_budget(self):
        a=self.app
        return f'actual window {a.win.get_width()}x{a.win.get_height()}, desktop-constrained request {self.window_limit[0]}x{self.window_limit[1]}'

    def wait_for(self,predicate,seconds=3):
        deadline=time.monotonic()+seconds;context=GLib.MainContext.default()
        while time.monotonic()<deadline:
            if predicate():return
            if context.pending():context.iteration(False)
            else:time.sleep(.002)
        self.fail('Tool layout did not settle: '+self.layout_budget())

    def assert_reachable(self,widget):
        self.assertTrue(widget.get_mapped())
        ok,bounds=widget.compute_bounds(self.app.win)
        self.assertTrue(ok);self.assertGreaterEqual(bounds.get_x(),0);self.assertGreaterEqual(bounds.get_y(),0)
        self.assertLessEqual(bounds.get_x()+bounds.get_width(),self.app.win.get_width())
        self.assertLessEqual(bounds.get_y()+bounds.get_height(),self.app.win.get_height())

    def next_frame(self):
        painted=[];clock=self.app.win.get_frame_clock()
        handler=clock.connect('after-paint',lambda *_:painted.append(True))
        try:
            self.app.win.queue_draw();self.wait_for(lambda:bool(painted))
        finally:clock.disconnect(handler)

    def test_closed_dock_gives_space_back_to_model(self):
        a=self.app
        self.assertFalse(a.tools.box.get_visible())
        # The approved second toolbar and visible transport/rate rows share
        # the native window height with the model; retain a usable 3D area.
        self.assertGreaterEqual(a.canvas.get_height(),max(250,a.win.get_height()-420),self.layout_budget())
        width=a.canvas.get_width();a.components.open();pump(.05)
        self.assertEqual(a.canvas.get_width(),width);self.assertEqual(a.tools.active,'components')
        a.tools.close_current();pump(.05)
        self.assertIsNone(a.components.window);self.assertFalse(a.tools.box.get_visible())
        self.assertEqual(a.canvas.get_width(),width)

    def test_components_reopen_keeps_summary_in_the_current_panel(self):
        a=self.app;c=a.components
        snapshot=a.project_snapshot();token=a.document.token;design=a.design
        summary=c.summary
        for _ in range(3):
            c.open();self.next_frame()
            self.assertIs(c.summary,summary)
            self.assertIs(summary.get_parent(),c.window.body)
            self.assertTrue(summary.get_mapped())
            self.assertTrue(summary.get_text())
            c.window.close();pump(.05)
            self.assertIsNone(c.window)
        self.assertEqual(a.project_snapshot(),snapshot)
        self.assertEqual(a.document.token,token)
        self.assertIs(a.design,design)

    def test_new_scroll_position_wins_over_an_older_pending_rebuild(self):
        import gui_workflow
        a=self.app
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='cycloidal',parameters=generate('cycloidal',dict(variant='dual')).values))
        gui_workflow.show_page(a,'geometry');a.advanced_expander.set_expanded(True);pump(.3)
        adj=a.page_scrolls['geometry'].get_vadjustment()
        adj.set_value(0);gui_workflow.preserve_scroll(a)
        adj.set_value(100);self.assertEqual(adj.get_value(),100)
        a.make_fields();pump(.3)
        self.assertAlmostEqual(adj.get_value(),100,delta=1)
        self.assertTrue(a.advanced_expander.get_expanded())

    def test_switch_preserves_form_and_selection_without_document_edits(self):
        a=self.app;token=a.document.token
        a.components.open();a.components.select((0,1));component_panel=a.components.window
        a.combination_search.open();search_panel=a.combination_search.window
        a.combination_search.fields['target'].set_text('7.125')
        a.components.open();self.assertIs(a.components.window,component_panel)
        self.assertEqual(a.components.selected,(0,1));self.assertEqual(a.document.token,token)
        a.combination_search.open();self.assertIs(a.combination_search.window,search_panel)
        self.assertEqual(a.combination_search.fields['target'].get_text(),'7.125')
        a.viewport_paned.set_position(450);pump(.05);position=a.viewport_paned.get_position()
        a.components.open();pump(.05);self.assertEqual(a.viewport_paned.get_position(),position)

    def test_measure_and_navigation_are_distinct_and_reversible(self):
        a=self.app;a.pick_mode.set_selected(2);pump(.05)
        self.assertTrue(a.components.measure.get_active())
        self.assertEqual(a.components.inspector_stack.get_visible_child_name(),'measure')
        a.components.inspector_stack.set_visible_child_name('parts')
        self.assertEqual(a.pick_mode.get_selected(),1)
        a.components.inspector_stack.set_visible_child_name('measure')
        self.assertEqual(a.pick_mode.get_selected(),2)
        a.pick_mode.set_selected(0)
        self.assertEqual(a.pick_mode.get_selected(),0);self.assertFalse(a.components.measure.get_active())
        a.components.select((0,));a.canvas.emit('component-click',0,0,False)
        self.assertEqual(a.components.selected,(0,))
        a.pick_mode.set_selected(1);a.canvas.emit('component-click',0,0,False)
        self.assertEqual(a.components.selected,())

    def test_export_scope_counts_and_routes_ignore_visibility(self):
        a=self.app;c=a.components;c.select((0,1));a.export_scope.set_selected(1);a.update_export_scope()
        self.assertIn('2 selected / 4',a.export_count.get_text())
        a.view_options['support'].set_active(True);c.isolate();a.update_export_scope()
        self.assertIn('2 selected / 4',a.export_count.get_text())
        # Activate the real format command; do not write mock geometry.
        body=a.export_scope.get_parent();child=body.get_first_child();step=None
        while child:
            if isinstance(child,Gtk.Button) and child.get_child():
                text=child.get_child().get_first_child()
                if isinstance(text,Gtk.Label) and text.get_text()=='STEP for CAD':step=child;break
            child=child.get_next_sibling()
        self.assertIsNotNone(step)
        with patch.object(c,'export') as selected:
            step.emit('clicked');selected.assert_called_once_with('step')
        a.export_scope.set_selected(0);a.update_export_scope()
        self.assertIn('All 4',a.export_count.get_text())
        c.select(());a.export_scope.set_selected(1);a.update_export_scope()
        self.assertFalse(step.get_sensitive());self.assertIn('0 selected',a.export_count.get_text())

    def test_interference_coverage_stays_visible_when_a_pose_is_selected(self):
        from interference import Settings
        from test_interference_gui import wait_until
        a=self.app;c=a.interference;c.open();c.start(Settings(step_degrees=180,max_seconds=20))
        self.assertTrue(wait_until(lambda:c.cancel is None,25));self.assertIsNotNone(c.result)
        c.list.select_row(c.list.get_row_at_index(0));pump(.03)
        self.assertTrue(c.coverage.get_visible())
        self.assertIn('Complete sampled coverage' if c.result.coverage_complete else 'INCOMPLETE coverage',c.coverage.get_text())
        self.assertIn('180°',c.coverage.get_text())
        self.assertIn(f'{c.result.completed_poses}/{c.result.planned_poses} poses',c.coverage.get_text())
        a.inputs['module'].set_text('-')
        self.assertFalse(c.coverage.get_visible());self.assertIsNone(c.result)

    def test_compact_enlarged_tools_keep_actions_and_focus_reachable(self):
        a=self.app
        for scale in (0,1,2):
            with self.subTest(scale=scale):
                a.text_size.set_selected(scale)
                for controller in (a.components,a.combination_search,a.interference):
                    controller.open();pump(.1)
                    self.assertLessEqual(a.win.get_width(),self.window_limit[0],self.layout_budget())
                    self.assertLessEqual(a.win.get_height(),self.window_limit[1],self.layout_budget())
                    self.assertGreater(a.canvas.get_width(),250)
                    for control in (a.tools.menu,a.export_menu,a.cad_menu,a.motion_reset):
                        ok,rect=control.compute_bounds(a.win)
                        self.assertTrue(ok)
                        self.assertGreaterEqual(rect.get_x(),0)
                        self.assertLessEqual(rect.get_x()+rect.get_width(),a.win.get_width())
                        self.assertGreaterEqual(rect.get_y(),0)
                        self.assertLessEqual(rect.get_y()+rect.get_height(),a.win.get_height())
                    panel=controller.window
                    self.assertGreater(panel.scroll.get_height(),80)
                    target=controller.export_buttons[0] if controller is a.components else controller.cancel_button
                    if controller is a.components:
                        a.components.inspector_stack.set_visible_child_name('parts')
                        a.components.select((0,))
                    else:
                        # Cancel stays in the pinned bar, outside the scrolling form.
                        self.assertIsNot(target.get_parent(),panel.scroll.get_child())
                        target=controller.run_button
                    self.assertTrue(target.grab_focus());pump(.08)
                    ok,bounds=target.compute_bounds(a.win)
                    self.assertTrue(ok);self.assertGreaterEqual(bounds.get_y(),0)
                    self.assertLessEqual(bounds.get_y()+bounds.get_height(),a.win.get_height())
                    self.assertGreaterEqual(bounds.get_x(),0)
                    self.assertLessEqual(bounds.get_x()+bounds.get_width(),a.win.get_width())
        a.text_size.set_selected(0)

    def test_expand_restore_preserves_document_selection_scene_and_parent_visibility(self):
        a=self.app;c=a.components;c.open();c.select((0,1));pump(.05)
        a.workspace_paned.set_position(330);a.viewport_paned.set_position(420);pump(.05)
        positions=(a.workspace_paned.get_position(),a.viewport_paned.get_position())
        token=a.document.token;snapshot=a.project_snapshot();scene=a.canvas.scene;design=a.design;panel=c.window
        visibility=(a.parameter_panel.get_visible(),a.preview_overlay.get_visible(),a.workspace_extras.get_visible())
        child_visible=a.warning_bar.get_visible()
        a.tools.expand_button.emit('clicked');self.assertTrue(a.tools.expanded)
        self.wait_for(lambda:a.tools.box.get_width()>=a.win.get_width()-32)
        for parent in (a.parameter_panel,a.canvas,a.workspace_extras):self.assertFalse(parent.get_visible())
        self.assertTrue(a.preview_overlay.get_visible())
        self.assertEqual(a.warning_bar.get_visible(),child_visible)
        # New child state while the parent is hidden must remain current.
        a.warning_bar.set_visible(not child_visible)
        self.assertEqual(a.tools.expand_button.get_label(),'Restore workspace');self.assert_reachable(a.tools.expand_button)
        self.assertIs(c.window,panel);self.assertEqual(c.selected,(0,1))
        a.tools.expand_button.emit('clicked');self.wait_for(lambda:not a.tools.restoring)
        self.assertEqual((a.parameter_panel.get_visible(),a.preview_overlay.get_visible(),a.workspace_extras.get_visible()),visibility)
        self.assertEqual(a.warning_bar.get_visible(),not child_visible)
        self.assertEqual((a.workspace_paned.get_position(),a.viewport_paned.get_position()),positions)
        self.assertEqual(a.document.token,token);self.assertEqual(a.project_snapshot(),snapshot)
        self.assertIs(a.design,design);self.assertIs(a.canvas.scene,scene);self.assertEqual(c.selected,(0,1))
        self.assertIs(c.window,panel);self.assertFalse(a.tools.expanded)

    def test_switch_and_nonactive_close_keep_expansion_and_existing_forms(self):
        a=self.app;a.components.open();a.components.select((0,));components=a.components.window
        a.combination_search.open();a.combination_search.fields['target'].set_text('7.125')
        search=a.combination_search.window;a.components.open();a.tools.expand_button.emit('clicked')
        a.combination_search.open();self.assertTrue(a.tools.expanded);self.assertIs(a.combination_search.window,search)
        self.assertEqual(a.combination_search.fields['target'].get_text(),'7.125')
        a.components.open();self.assertIs(a.components.window,components);self.assertEqual(a.components.selected,(0,))
        search.close();self.assertTrue(a.tools.expanded);self.assertEqual(a.tools.active,'components')
        self.assertFalse(a.parameter_panel.get_visible());self.assertFalse(a.canvas.get_visible())
        a.tools.expand_button.emit('clicked');self.wait_for(lambda:not a.tools.restoring)
        self.assertEqual(a.components.selected,(0,))

    def test_restore_then_close_same_frame_keeps_normal_reopen_width(self):
        a=self.app;a.components.open();a.viewport_paned.set_position(450);pump(.05)
        normal=a.tools.box.get_width();a.tools.expand_button.emit('clicked')
        self.wait_for(lambda:a.tools.box.get_width()>=a.win.get_width()-32)
        self.assertGreater(a.tools.box.get_width(),normal)
        a.tools.expand_button.emit('clicked');a.tools.close_button.emit('clicked')
        self.assertFalse(a.tools.expanded);self.assertIsNone(a.components.window)
        self.assertEqual(a.tools.last_width,normal)
        self.wait_for(lambda:not a.tools.restoring)
        a.components.open();pump(.08)
        self.assertAlmostEqual(a.tools.box.get_width(),normal,delta=2)
        self.assertTrue(a.parameter_panel.get_visible());self.assertTrue(a.preview_overlay.get_visible())

    def test_escape_registered_action_restores_before_normal_tool_close(self):
        a=self.app;a.components.open();a.components.select((0,));token=a.document.token
        a.tools.expand_button.emit('clicked')
        self.assertTrue(a.tools.shortcuts.get_item(0).get_action().activate(Gtk.ShortcutActionFlags.EXCLUSIVE,a.win,None))
        self.assertFalse(a.tools.expanded);self.assertIsNone(a.components.window)
        self.assertTrue(a.parameter_panel.get_visible());self.assertTrue(a.preview_overlay.get_visible())
        self.assertTrue(a.workspace_extras.get_visible());self.assertEqual(a.document.token,token)
        self.assertEqual(a.components.selected,(0,))

    def test_expanded_tools_use_compact_workspace_at_normal_and_large_font(self):
        a=self.app
        monitor=Gdk.Display.get_default().get_monitor_at_surface(a.win.get_surface())
        area=monitor.get_workarea() if hasattr(monitor,'get_workarea') else monitor.get_geometry()
        for width in (1280,1366):
            self.window_limit=(min(width,area.width),min(768,area.height))
            a.win.set_visible(False);a.win.set_default_size(*self.window_limit);a.win.present();pump(.12)
            a.win.unmaximize();self.wait_for(lambda:not a.win.is_maximized())
            for scale in (0,2):
                a.text_size.set_selected(scale)
                for controller in (a.components,a.combination_search,a.interference):
                    with self.subTest(width=width,scale=scale,tool=type(controller).__module__):
                        controller.open();self.next_frame()
                        normal_height=controller.window.scroll.get_height()
                        a.tools.expand_button.emit('clicked')
                        try:
                            self.wait_for(lambda:a.tools.box.get_width()>=a.win.get_width()-32 and controller.window.scroll.get_height()>0)
                            self.next_frame()
                            self.assertLessEqual(a.win.get_width(),self.window_limit[0],self.layout_budget())
                            self.assertLessEqual(a.win.get_height(),self.window_limit[1],self.layout_budget())
                            self.assertGreaterEqual(controller.window.scroll.get_height(),max(220,normal_height+80))
                            self.assert_reachable(a.tools.expand_button);self.assert_reachable(a.tools.close_button)
                            self.assert_reachable(a.tools.menu)
                            self.assert_reachable(a.view_menu)
                            if controller is a.components:
                                controller.select((0,));target=controller.export_buttons[0]
                            else:
                                self.assert_reachable(controller.cancel_button);target=controller.run_button
                            self.assertTrue(target.grab_focus());pump(.04);self.assert_reachable(target)
                        finally:
                            a.tools.restore_workspace();self.wait_for(lambda:not a.tools.restoring)
        a.text_size.set_selected(0)

    def test_reference_controls_use_local_vectors_and_separate_buttons(self):
        from copy import deepcopy
        from navigation_cube import NavigationCube
        a=self.app
        self.assertFalse(hasattr(a,'help_button'))
        self.assertFalse(hasattr(a,'app_guide'))
        self.assertIsInstance(a.navigation_cube,NavigationCube)
        self.assertTrue(a.navigation_cube.get_mapped())
        self.assertEqual((a.navigation_cube.get_width(),a.navigation_cube.get_height()),(116,116))
        buttons=(a.view_menu,a.pan_button,a.tools.menu)
        for button,name in zip(buttons,('sliders','pan','wrench')):
            with self.subTest(glyph=name):
                icon=button.workspace_icon if button is a.tools.menu else button.get_child()
                self.assertTrue(button.get_mapped())
                self.assertIsInstance(icon,Gtk.DrawingArea)
                self.assertEqual(icon.glyph_name,name)
                size=16 if button is a.tools.menu else 19
                self.assertEqual((icon.get_width(),icon.get_height()),(size,size))
                self.assertTrue(icon.is_ancestor(button.get_parent()))
                wrapper=button.get_parent()
                ok,glyph=icon.compute_bounds(wrapper);self.assertTrue(ok)
                ok,action=button.compute_bounds(wrapper);self.assertTrue(ok)
                self.assertGreaterEqual(glyph.get_x(),action.get_x())
                self.assertLessEqual(glyph.get_x()+glyph.get_width(),action.get_x()+action.get_width())
        self.assertEqual(a.tools.menu.get_label(),'Tools')
        self.assertEqual(a.view_menu.get_tooltip_text(),'Display options')
        self.assertEqual(a.preview_toolbar.get_spacing(),6)
        ok,view=a.view_menu.compute_bounds(a.navigation_controls);self.assertTrue(ok)
        ok,pan=a.pan_button.compute_bounds(a.navigation_controls);self.assertTrue(ok)
        self.assertEqual(round(view.get_x()-pan.get_x()-pan.get_width()),2)
        self.assertEqual(round(view.get_height()),29)
        self.assertEqual(round(pan.get_y()),round(view.get_y()))
        ok,tools=a.tools.menu.compute_bounds(a.win);self.assertTrue(ok)
        ok,cube=a.navigation_cube.compute_bounds(a.win);self.assertTrue(ok)
        self.assertLessEqual(tools.get_y()+tools.get_height(),cube.get_y())
        self.assertEqual(round(tools.get_height()),34)
        self.assertEqual(round(a.preview_toolbar.get_height()),34)
        snapshot=deepcopy(a.project_snapshot());token=a.document.token
        self.assertIsInstance(a.theme_switch,Gtk.Switch)
        self.assertIs(a.appearance_button,a.settings_button)
        self.assertIsNone(a.theme_switch.get_parent())
        self.assertFalse(a.theme_switch.get_mapped())
        theme=a.theme_switch.get_active();design=a.design
        try:
            a.theme_switch.set_active(not theme);pump(.05)
            self.assertEqual(a.workspace_theme,'light' if not theme else 'dark')
            self.assertIs(a.design,design)
        finally:a.theme_switch.set_active(theme)
        a.pan_button.set_active(True);self.assertTrue(a.canvas.pan_mode)
        a.pan_button.set_active(False);self.assertFalse(a.canvas.pan_mode)
        keys=next(c for c in a.navigation_cube.observe_controllers()
                  if isinstance(c,Gtk.EventControllerKey))
        self.assertTrue(keys.emit('key-pressed',Gdk.KEY_5,0,Gdk.ModifierType(0)))
        self.assertEqual((a.canvas.yaw,a.canvas.tilt),(0,0))
        self.assertTrue(keys.emit('key-pressed',Gdk.KEY_Home,0,Gdk.ModifierType(0)))
        # Display and Tools still control their actual mutually exclusive overlays.
        a.view_menu.emit('clicked');pump(.05)
        self.assertTrue(a.view_panel.get_visible());self.assertTrue(a.view_menu.get_active())
        self.assertIsInstance(a.view_panel,Gtk.Popover)
        self.assertTrue(a.pick_mode.get_mapped());self.assertTrue(a.explode_slider.get_mapped())
        a.tools.menu.emit('clicked');pump(.05)
        self.assertTrue(a.tools.box.get_visible());self.assertTrue(a.tools.menu.get_active())
        self.assertFalse(a.view_menu.get_active());self.assertFalse(a.view_panel.get_visible())
        a.tools.close_current()
        self.assertEqual(a.project_snapshot(),snapshot);self.assertEqual(a.document.token,token)

    def test_reference_tool_chooser_uses_local_vectors_and_compact_rows(self):
        a=self.app
        a.tools.menu.set_active(True);pump(.1)
        try:
            self.assertEqual(len(a.tools.command_buttons),8)
            for button in a.tools.command_buttons:
                with self.subTest(action=button.get_label()):
                    self.assertIsInstance(button.workspace_icon,Gtk.DrawingArea)
                    self.assertEqual(button.workspace_icon.get_width(),16)
                    self.assertEqual(button.workspace_icon.get_height(),16)
                    row=button.get_parent()
                    ok,rect=button.compute_bounds(row);self.assertTrue(ok)
                    self.assertEqual(round(rect.get_height()),41)
                    ok,icon=button.workspace_icon.compute_bounds(row);self.assertTrue(ok)
                    ok,text=button.get_child().compute_bounds(row);self.assertTrue(ok)
                    self.assertEqual(round(text.get_x()-icon.get_x()-icon.get_width()),6)
        finally:a.tools.close_current()

    def test_tools_button_chooser_back_and_view_keep_actual_forms(self):
        a=self.app;tools=a.tools
        width,height=a.canvas.get_width(),a.canvas.get_height()
        token=a.document.token;scene=a.canvas.scene
        tools.menu.emit('clicked');pump(.05)
        self.assertTrue(tools.menu.get_active());self.assertTrue(tools.box.get_visible())
        self.assertEqual(tools.stack.get_visible_child_name(),'chooser')
        self.assertFalse(tools.back_button.get_visible())
        self.assertFalse(tools.expand_button.get_visible())
        self.assertEqual(set(tools.controllers),{'components','search','interference','gear_measurement','backlash'})
        rows=[];row=tools.commands.get_first_child()
        while row:
            rows.append(row.get_child());row=row.get_next_sibling()
        self.assertEqual(rows[:5],[tools.controllers[key].button for key in
            ('components','search','interference','gear_measurement','backlash')])
        self.assertEqual(len(tools.command_buttons),8)
        self.assertTrue({'Bill of materials','Calculation report','Model notes'} <= {button.get_label() for button in tools.command_buttons})
        for controller in tools.controllers.values():
            self.assertTrue(controller.button.is_ancestor(tools.commands))
        a.combination_search.button.emit('clicked');pump(.05)
        panel=a.combination_search.window
        a.combination_search.fields['target'].set_text('7.125')
        self.assertEqual(tools.stack.get_visible_child_name(),'search')
        self.assertTrue(tools.back_button.get_visible());self.assertTrue(tools.menu.get_active())
        tools.back_button.emit('clicked');pump(.05)
        self.assertEqual(tools.stack.get_visible_child_name(),'chooser')
        tools.close_button.emit('clicked');pump(.05)
        self.assertFalse(tools.menu.get_active());self.assertFalse(tools.box.get_visible())
        self.assertIs(a.combination_search.window,panel)
        tools.menu.emit('clicked');a.combination_search.button.emit('clicked');pump(.05)
        self.assertEqual(a.combination_search.fields['target'].get_text(),'7.125')
        tools.expand_button.emit('clicked');self.assertTrue(tools.expanded)
        a.view_menu.set_active(True);pump(.1)
        self.assertFalse(tools.expanded);self.assertFalse(tools.menu.get_active())
        self.assertTrue(a.view_panel.get_visible());self.assertFalse(tools.box.get_visible())
        tools.menu.emit('clicked');pump(.05)
        self.assertFalse(a.view_menu.get_active());self.assertFalse(a.view_panel.get_visible())
        self.assertEqual(tools.stack.get_visible_child_name(),'chooser')
        a.combination_search.button.emit('clicked');pump(.05)
        self.assertIs(a.combination_search.window,panel)
        self.assertEqual(a.combination_search.fields['target'].get_text(),'7.125')
        self.assertEqual((a.canvas.get_width(),a.canvas.get_height()),(width,height))
        self.assertEqual(a.document.token,token);self.assertEqual(id(a.canvas.scene),id(scene))
        tools.close_current();pump(.05)
        self.assertIsNone(a.combination_search.window)
        self.assertFalse(tools.menu.get_active());self.assertFalse(tools.box.get_visible())

    def test_view_and_all_tools_overlay_preserve_camera_viewport_and_drafts(self):
        a=self.app
        a.canvas.view('front');pump(.05)
        a.inputs['module'].set_text('-')
        self.assertFalse(a.refresh());pump(.2)
        scene=a.canvas.scene;token=a.document.token
        width,height=a.canvas.get_width(),a.canvas.get_height()
        raw=a.inputs['module'].get_text()
        for controller in (a.components,a.combination_search,a.interference,a.gear_measurement,a.backlash):
            controller.open();pump(.08)
            self.assertIs(controller.window.get_parent(),a.tools.stack)
            self.assertTrue(a.tools.box.get_visible())
            self.assertEqual((a.canvas.get_width(),a.canvas.get_height()),(width,height))
            ok,panel=a.tools.box.compute_bounds(a.preview_overlay)
            self.assertTrue(ok);self.assertGreaterEqual(panel.get_x(),0)
            self.assertLessEqual(panel.get_x()+panel.get_width(),a.preview_overlay.get_width())
            self.assertEqual(a.inputs['module'].get_text(),raw)
            a.view_menu.set_active(True);pump(.05)
            self.assertFalse(a.tools.box.get_visible());self.assertTrue(a.view_panel.get_visible())
            self.assertEqual((a.canvas.get_width(),a.canvas.get_height()),(width,height))
            a.view_menu.set_active(False)
            controller.window.close()
        self.assertEqual(id(a.canvas.scene),id(scene));self.assertEqual(a.document.token,token)


if __name__=='__main__':unittest.main()
