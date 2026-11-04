# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Motion controls remain usable in a narrow sidebar without changing the model."""
from copy import deepcopy
import unittest
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,GLib
import test_workspace_theme_preferences as fixtures
from geometry import generate
from gui_workflow import show_page
from ratiolab_checks import _wait_for_frame


class MotionLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures.WorkspaceThemePreferencesTests.setUpClass()

    setUp=fixtures.WorkspaceThemePreferencesTests.setUp
    close_apps=fixtures.WorkspaceThemePreferencesTests.close_apps
    launch=fixtures.WorkspaceThemePreferencesTests.launch

    def load(self,app,family,**values):
        d=generate(family,values)
        app.load_config_data(dict(format='solidcraft-riduttori/1',family=family,parameters=d.values))
        self.assertTrue(fixtures.wait_until(lambda:app.design and not app.pending and not app._geometry_waiting))
        show_page(app,'motion');app.io_frame.set_expanded(True)

    def test_two_stage_choices_use_full_width_at_all_text_scales(self):
        app=self.launch();self.load(app,'planetary',variant='two_stage')
        before=deepcopy(app.project_snapshot());token=app.document.token
        for scale in (0,1,2):
            app.text_size.set_selected(scale);app.workspace_paned.set_position(230)
            _wait_for_frame(app.canvas,GLib.MainContext.default())
            self.assertEqual(app.parameter_panel.get_width(),230)
            self.assertEqual(set(app.io_role_selectors),{'io_scheme','io_scheme2'})
            for roles in app.io_role_selectors.values():
                for role in ('input','output'):
                    control=roles[role];self.assertTrue(control.get_mapped())
                    ok,rect=control.compute_bounds(app.parameter_panel);self.assertTrue(ok)
                    self.assertGreaterEqual(rect.get_width(),140)
                    self.assertGreaterEqual(rect.get_x(),0)
                    self.assertLessEqual(rect.get_x()+rect.get_width(),230)
        self.assertEqual(app.project_snapshot(),before);self.assertEqual(app.document.token,token)

    def test_long_topology_headers_keep_sidebar_and_controls_bounded(self):
        app=self.launch()
        for family,values in [('differential',{'configuration':'classic'}),('wolfrom',{})]:
            self.load(app,family,**values);before=deepcopy(app.project_snapshot())
            for scale in (0,1,2):
                app.text_size.set_selected(scale);app.workspace_paned.set_position(230)
                _wait_for_frame(app.canvas,GLib.MainContext.default())
                self.assertEqual(app.parameter_panel.get_width(),230)
                self.assertTrue(app.io_frame.get_label_widget().get_wrap())
                self.assertTrue(app.motion_play.get_mapped())
                self.assertTrue(app.motion_speed_text.get_mapped())
                self.assertIs(app.motion_rate_display.get_child_by_name('value'),app.motion_speed_text)
            self.assertEqual(app.project_snapshot(),before)

    def test_fixed_drive_details_retain_member_rates_and_nominal_readout(self):
        app=self.launch();self.load(app,'wolfrom');before=deepcopy(app.project_snapshot())
        detail=next(w for w in app.io_box if isinstance(w,Gtk.Expander))
        self.assertFalse(detail.get_expanded())
        full=app.io_results[0][1]
        for text in ('Sun input:','Common carrier:','Compound spin:','Output ring:','First ring: 0 rpm'):
            self.assertIn(text,full.get_text())
        output=app.io_results[1][1]
        self.assertTrue(output.has_css_class('drive-result-value'))
        self.assertTrue(output.get_mapped())
        self.assertAlmostEqual(float(output.get_text()),app.design.analysis['kinematics']['rates_rpm']['output'],places=2)
        detail.emit('activate');fixtures.pump();self.assertTrue(full.get_mapped())
        self.assertEqual(app.project_snapshot(),before)
