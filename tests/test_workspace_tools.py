# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Real GTK integration for the dock, explicit export scope and compact layout."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk,Gio
import app as module
from geometry import generate
from test_interference_gui import pump


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
        a.win.set_visible(False);a.win.set_default_size(1280,800);a.win.present();pump(.15)

    def test_closed_dock_gives_space_back_to_model(self):
        a=self.app
        self.assertFalse(a.tools.box.get_visible());self.assertGreaterEqual(a.canvas.get_height(),470)
        width=a.canvas.get_width();a.components.open();pump(.05)
        self.assertLess(a.canvas.get_width(),width);self.assertEqual(a.tools.active,'components')
        a.tools.close_current();pump(.05)
        self.assertIsNone(a.components.window);self.assertFalse(a.tools.box.get_visible())
        self.assertEqual(a.canvas.get_width(),width)

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
                    self.assertLessEqual(a.win.get_width(),1280)
                    self.assertLessEqual(a.win.get_height(),800)
                    self.assertGreater(a.canvas.get_width(),250)
                    for control in (a.tools.menu,a.export_menu,a.cad_menu,a.pick_mode,a.motion_reset):
                        ok,rect=control.compute_bounds(a.win)
                        self.assertTrue(ok)
                        self.assertGreaterEqual(rect.get_x(),0)
                        self.assertLessEqual(rect.get_x()+rect.get_width(),1280)
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
        a.text_size.set_selected(0)


if __name__=='__main__':unittest.main()
