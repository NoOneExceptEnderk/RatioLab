# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Display-backed preview seeking, bounded rack travel and unchanged project data."""
from copy import deepcopy
from math import degrees, radians, isclose, pi
from unittest.mock import patch
import unittest
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk, GLib
import app as app_module
import preview3d
import test_workspace_theme_preferences as fixtures
from test_interference_gui import pump, wait_until


class PhaseSliderGuiTests(unittest.TestCase):
    setUpClass = fixtures.WorkspaceThemePreferencesTests.__dict__['setUpClass']
    setUp = fixtures.WorkspaceThemePreferencesTests.setUp
    close_apps = fixtures.WorkspaceThemePreferencesTests.close_apps
    launch = fixtures.WorkspaceThemePreferencesTests.launch

    def model(self, family='parallel', **parameters):
        a=self.launch()
        a.load_config_data(dict(format='solidcraft-riduttori/1',family=family,parameters=parameters))
        self.assertTrue(wait_until(lambda:not a.busy and not a.pending and not a._geometry_waiting
                                  and a.canvas.design is not None and a.canvas.design.family==family))
        return a

    def test_scrubbing_pauses_and_renders_without_generating_geometry_or_changing_project(self):
        a=self.model(input_rpm=125.5);c=a.canvas
        before=deepcopy(a.project_snapshot());states=deepcopy(a.document.states);token=a.document.token
        design,scene,plan=a.design,c.scene,c.motion_plan
        c.set_motion_playing(True);pump(.08)
        self.assertTrue(c.motion_playing)
        with patch.object(app_module,'generate',side_effect=AssertionError('Unexpected regeneration')), \
             patch.object(preview3d,'build_scene',side_effect=AssertionError('Unexpected scene rebuild')):
            a.motion_phase.set_value(37.25)
            self.assertFalse(c.motion_playing);self.assertTrue(c.motion_enabled)
            self.assertAlmostEqual(c.motion_phase,radians(37.25))
            self.assertTrue(wait_until(lambda:isclose(c.rendered_phase,radians(37.25),abs_tol=1e-10)))
            a.motion_phase.set_value(360)
            self.assertAlmostEqual(c.motion_phase,2*pi)
            self.assertAlmostEqual(a.motion_phase.get_value(),360)
            captured=[];c.capture_png(lambda data,error:captured.append((data,error)))
            self.assertIsNone(captured[0][1]);self.assertTrue(captured[0][0].startswith(b'\x89PNG'))
        self.assertIs(c.motion_plan,plan);self.assertIs(c.scene,scene);self.assertIs(a.design,design)
        self.assertEqual(a.document.token,token);self.assertEqual(a.document.states,states)
        self.assertEqual(a.project_snapshot(),before);self.assertEqual(a.motion_rpm,125.5)
        a.motion_reset.emit('clicked');self.assertEqual(c.motion_phase,0)
        self.assertEqual(a.motion_phase.get_value(),0)
        c.set_motion_playing(True);pump(.15);c.set_motion_playing(False)
        self.assertAlmostEqual(a.motion_phase.get_value(),degrees(c.motion_phase)%360,places=5)

    def test_rack_uses_working_stroke_and_invalid_or_stationary_preview_disables_slider(self):
        a=self.model('rack',input_rpm=-60);c=a.canvas
        low,high=c.motion_plan.phase_limits
        adjustment=a.motion_phase.get_adjustment()
        self.assertAlmostEqual(adjustment.get_lower(),degrees(low))
        self.assertAlmostEqual(adjustment.get_upper(),degrees(high))
        for value in (low,high,(low+high)/2):
            a.motion_phase.set_value(degrees(value))
            self.assertAlmostEqual(c.motion_phase,value)
            self.assertTrue(wait_until(lambda:isclose(c.rendered_phase,value,abs_tol=1e-10)))
        self.assertTrue(a.motion_phase_label.get_text().startswith('Rack travel ·'))
        c.seek_motion_phase(high+1);self.assertEqual(c.motion_phase,high)
        with self.assertRaises(ValueError):c.seek_motion_phase(float('nan'))
        self.assertEqual(c.motion_phase,high)
        c.invalidate_motion();self.assertFalse(a.motion_phase.get_sensitive())
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='spur',parameters={'input_rpm':0}))
        self.assertTrue(wait_until(lambda:not a.busy and not a.pending and not a._geometry_waiting
                                  and a.canvas.design is not None and a.canvas.design.family=='spur'))
        self.assertFalse(a.motion_phase.get_sensitive())
        self.assertEqual(a.motion_rpm,0)

    def test_slider_and_transport_stay_visible_in_both_themes_and_large_translated_text(self):
        a=self.model()
        for language in ('it','ta'):
            a.language.change(language)
            for mode in (0,1):
                a.theme_selector.set_selected(mode)
                for scale in (0,1,2):
                    a.text_size.set_selected(scale);pump(.15)
                    for widget in (a.motion_play,a.motion_phase_label,a.motion_phase,a.motion_connections,a.motion_speed_text):
                        self.assertTrue(widget.get_mapped())
                        ok,bounds=widget.compute_bounds(a.win);self.assertTrue(ok)
                        self.assertGreaterEqual(bounds.get_x(),0)
                        self.assertLessEqual(bounds.get_x()+bounds.get_width(),a.win.get_width()+1)
                        self.assertLessEqual(bounds.get_y()+bounds.get_height(),a.win.get_height()+1)
                    self.assertGreaterEqual(a.motion_phase.get_width(),120)
        self.assertEqual(a.motion_phase.get_accessible_role(),Gtk.AccessibleRole.SLIDER)

    def test_phase_track_keeps_its_bounds_across_digits_play_pause_and_wrap(self):
        a=self.model(input_rpm=60)
        for language in ('en','it','ta'):
            a.language.change(language)
            for scale in (0,2):
                a.text_size.set_selected(scale);pump(.2)
                bounds=[]
                for angle in (0,9.9,10,99.9,100,359.9):
                    a.canvas.seek_motion_phase(radians(angle));pump(.04)
                    for playing in (False,True):
                        a.canvas.set_motion_playing(playing);pump(.04)
                        ok,rect=a.motion_phase.compute_bounds(a.win);self.assertTrue(ok)
                        bounds.append((rect.get_x(),rect.get_y(),rect.get_width(),rect.get_height()))
                    a.canvas.set_motion_playing(False)
                for column in zip(*bounds):
                    self.assertLessEqual(max(column)-min(column),.5,(language,scale,bounds))

    def test_stripes_keep_their_position_when_rates_change_and_stop_at_zero(self):
        a=self.model(input_rpm=60);phase=a.motion_phase
        a.canvas.set_motion_playing(True);pump(.2)
        original=phase.set_stripes
        def check_update(playing,rpm):
            before,speed,stamp=phase.stripe_offset,phase.stripe_speed,phase._stripe_time
            now=GLib.get_monotonic_time()
            expected=(before+speed*max(0,now/1000000-stamp))%28 if stamp is not None else before
            with patch('motion_controls.GLib.get_monotonic_time',return_value=now):
                original(playing,rpm)
            self.assertAlmostEqual(phase.stripe_offset,expected,places=5)
        for rpm in (600,6,100000,0,60):
            old_speed=phase.stripe_speed
            tick=phase._stripe_tick
            with patch.object(phase,'set_stripes',side_effect=check_update):
                a.motion_speed_text.set_text(str(rpm));a.commit_motion_rate()
            if rpm:
                self.assertGreater(phase.stripe_speed,7)
                self.assertLess(phase.stripe_speed,70)
            else:self.assertEqual(phase.stripe_speed,0)
            if rpm==60:self.assertAlmostEqual(phase.stripe_speed,35)
            if rpm and old_speed:self.assertEqual(phase._stripe_tick,tick)
            pump(.12)
            if not rpm:
                offset=phase.stripe_offset;pump(.1)
                self.assertEqual(phase.stripe_offset,offset);self.assertEqual(phase._stripe_tick,0)
        a.canvas.set_motion_playing(False)
        self.assertEqual(phase._stripe_tick,0)

    def test_rack_keeps_track_width_when_input_is_zero_or_reversed(self):
        a=self.model('rack',input_rpm=60);pump(.1)
        bounds=[]
        for rpm in (60,0,-60,60):
            a.motion_speed_text.set_text(str(rpm));a.commit_motion_rate();pump(.08)
            for playing in (False,True):
                a.canvas.set_motion_playing(playing);pump(.05)
                ok,rect=a.motion_phase.compute_bounds(a.win);self.assertTrue(ok)
                bounds.append((rect.get_x(),rect.get_width(),rect.get_height()))
            a.canvas.set_motion_playing(False)
        for values in zip(*bounds):
            self.assertLessEqual(max(values)-min(values),.5,bounds)

    def test_play_indicator_repaints_at_low_rpm_with_desktop_animations_disabled(self):
        a=self.model(input_rpm=2);phase=a.motion_phase;settings=phase.get_settings()
        previous=settings.get_property('gtk-enable-animations')
        self.addCleanup(settings.set_property,'gtk-enable-animations',previous)
        settings.set_property('gtk-enable-animations',False)
        def capture():
            snapshot=Gtk.Snapshot()
            Gtk.WidgetPaintable.new(phase).snapshot(snapshot,phase.get_width(),phase.get_height())
            return a.win.get_renderer().render_texture(snapshot.to_node(),None).save_to_png_bytes().get_data()
        a.canvas.set_motion_playing(True);pump(.15)
        self.assertTrue(phase._stripe_tick)
        self.assertGreater(phase.stripe_speed,7)
        first=capture();pump(.3);self.assertNotEqual(capture(),first)
        a.motion_speed_text.set_text('0');a.commit_motion_rate();pump(.1)
        self.assertEqual(phase._stripe_tick,0)
        first=capture();pump(.2);self.assertEqual(capture(),first)


if __name__=='__main__':unittest.main()
