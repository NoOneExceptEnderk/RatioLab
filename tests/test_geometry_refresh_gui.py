# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Real GTK responsiveness, current-result gates and unchanged scene generation."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event,get_ident
import time
import unittest
from unittest.mock import patch
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk,Gio,GLib
import app as module
from geometry import generate
import preview3d
from motion_controls import scale_rpm


def pump(seconds=.05):
    until=time.monotonic()+seconds;context=GLib.MainContext.default()
    while time.monotonic()<until:
        while context.pending() and time.monotonic()<until:context.iteration(False)
        time.sleep(.002)


def wait_until(predicate,seconds=8):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        if predicate():return
        pump(.01)
    raise AssertionError('Timed out waiting for geometry preparation')


class GeometryRefreshGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            raise unittest.SkipTest('GTK display required')
        cls.temp=TemporaryDirectory(prefix='ratiolab-geometry-refresh-');cls.root=Path(cls.temp.name)
        cls.env=patch.dict(os.environ,dict(RATIOLAB_UPDATE_CHECK='0',
            XDG_CONFIG_HOME=str(cls.root/'config'),XDG_DATA_HOME=str(cls.root/'data'),
            XDG_CACHE_HOME=str(cls.root/'cache'),APPDATA=str(cls.root/'roaming'),LOCALAPPDATA=str(cls.root/'local')))
        cls.env.start();cls.app=module.ReducerApp()
        cls.app.set_application_id(f'local.solidcraft.reducers.geometryrefresh.p{os.getpid()}')
        cls.app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        cls.app.register(None);cls.app.activate();pump(.2)

    @classmethod
    def tearDownClass(cls):
        for window in list(cls.app.get_windows()):window.destroy()
        cls.env.stop();cls.temp.cleanup()

    def setUp(self):
        a=self.app;a.canvas.reset_motion();a.components.restore();a.interference.restore_view()
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='parallel',parameters=generate('parallel').values))
        for key in ('support','housing','exploded','section'):a.view_options[key].set_active(False)
        a.export_feedback.dismiss();pump(.08)

    def edit(self,value):
        self.app.inputs['width'].set_text(str(value))

    def held_generator(self,release,started,*,fail=False,calls=None):
        main=get_ident()
        def work(family,values):
            if get_ident()!=main:
                if calls is not None:calls.append((values['width'],get_ident()))
                if not started.is_set():
                    started.set()
                    if not release.wait(5):raise TimeoutError('Test worker was not released')
                    if fail:raise ValueError('Obsolete generator failure')
            return generate(family,values)
        return patch.object(module,'generate',side_effect=work)

    def test_held_worker_keeps_widgets_and_timer_responsive_and_latest_request_wins(self):
        a=self.app;previous=a.design;scene=a.canvas.scene;started=Event();release=Event();calls=[];main=get_ident()
        applies=[];builds=[];set_design=a.canvas.set_design;build_scene=preview3d.build_scene
        def apply(*args,**kwargs):applies.append(get_ident());return set_design(*args,**kwargs)
        def build(*args,**kwargs):builds.append(get_ident());return build_scene(*args,**kwargs)
        ticks=[];timer=GLib.timeout_add(10,lambda:ticks.append(time.monotonic()) or True)
        try:
            with self.held_generator(release,started,calls=calls), \
                 patch.object(a.canvas,'set_design',side_effect=apply),patch.object(preview3d,'build_scene',side_effect=build):
                self.edit(previous.values['width']+1);wait_until(started.is_set)
                self.assertTrue(a.pending);self.assertFalse(a.busy);self.assertTrue(a.fields.get_sensitive())
                self.assertTrue(a.inputs['width'].get_sensitive());self.assertFalse(a.metric_cards.get_sensitive())
                self.assertFalse(a.export_menu.get_sensitive());self.assertFalse(a.canvas.motion_valid)
                before=len(ticks);a.view_buttons['top'].emit('clicked')
                wait_until(lambda:len(ticks)-before>=5,seconds=1)
                self.assertFalse(release.is_set());self.assertIsNotNone(a.geometry_worker.thread)
                self.assertTrue(a.view_buttons['top'].get_active())
                self.assertIs(a.design,previous);self.assertIs(a.canvas.scene,scene)
                for offset in range(2,22):self.edit(previous.values['width']+offset)
                wait_until(lambda:a.geometry_worker.queued is not None)
                self.assertEqual(a.geometry_worker.queued[1].values['width'],previous.values['width']+21)
                release.set();wait_until(lambda:not a.pending)
            self.assertEqual([value for value,_ in calls],[previous.values['width']+1,previous.values['width']+21])
            self.assertTrue(all(thread!=main for _,thread in calls));self.assertTrue(all(thread!=main for thread in builds))
            self.assertEqual(len(builds),1)
            self.assertEqual(applies,[main]);self.assertEqual(a.design.values['width'],previous.values['width']+21)
            self.assertTrue(a.export_menu.get_sensitive());self.assertTrue(a.metric_cards.get_sensitive())
        finally:release.set();GLib.source_remove(timer)

    def test_prepared_scene_matches_existing_geometry_and_scene_bytes(self):
        a=self.app;target=a.design.values['width']+1
        a.inputs['width'].set_text(f'{target:.6f}');wait_until(lambda:not a.pending)
        expected=generate('parallel',a.design.values)
        scene=preview3d.build_scene(expected,a.canvas.show_support,a.canvas.show_housing,frame_explosion=True)
        self.assertEqual(a.canvas.scene.vertices.tobytes(),scene.vertices.tobytes())
        self.assertEqual(a.canvas.scene.materials.tobytes(),scene.materials.tobytes())
        self.assertEqual(a.canvas.scene.bounds,scene.bounds)
        self.assertEqual(a.design.analysis,expected.analysis)
        self.assertEqual(a.inputs['width'].get_text(),f'{target:.6f}')
        self.assertIsNone(a.canvas.failure)

    def test_changed_view_flags_are_reprepared_before_acceptance(self):
        a=self.app;started=Event();release=Event();target=a.design.values['width']+1
        try:
            with self.held_generator(release,started):
                self.edit(target);wait_until(started.is_set)
                a.view_options['support'].set_active(True);release.set();wait_until(lambda:not a.pending)
            self.assertEqual(a.design.values['width'],target)
            self.assertTrue(any(a.design.parts[part.source_index].role=='support' for part in a.canvas.scene.parts))
        finally:release.set()

    def test_stale_error_cannot_replace_latest_valid_design(self):
        a=self.app;started=Event();release=Event();target=a.design.values['width']+2
        try:
            with self.held_generator(release,started,fail=True):
                self.edit(target-1);wait_until(started.is_set);self.edit(target)
                wait_until(lambda:a.geometry_worker.queued is not None)
                release.set();wait_until(lambda:not a.pending)
            self.assertEqual(a.design.values['width'],target)
            self.assertFalse(a.parameter_error.get_visible());self.assertNotIn('Obsolete',a.status.get_text())
        finally:release.set()

    def test_invalid_field_rejects_pending_success_and_keeps_raw_draft(self):
        a=self.app;previous=a.design;started=Event();release=Event()
        try:
            with self.held_generator(release,started):
                self.edit(previous.values['width']+1);wait_until(started.is_set)
                a.inputs['module'].set_text('-');wait_until(lambda:not a.pending)
                self.assertIsNone(a.design);self.assertTrue(a.field_feedback['module'].get_visible())
                release.set();wait_until(lambda:a.geometry_worker.thread is None);pump()
            self.assertIsNone(a.design);self.assertIs(a.canvas.design,previous)
            self.assertEqual(a.inputs['module'].get_text(),'-');self.assertFalse(a.export_menu.get_sensitive())
        finally:release.set()

    def test_current_worker_errors_keep_existing_invalid_configuration_behavior(self):
        a=self.app
        for family in ('parallel','wolfrom'):
            with self.subTest(family=family):
                a.load_config_data(dict(format='solidcraft-riduttori/1',family=family,parameters=generate(family).values))
                previous=a.design;self.edit(0);wait_until(lambda:not a.pending)
                if family=='wolfrom':self.assertIs(a.design,previous)
                else:self.assertIsNone(a.design)
                self.assertIs(a.canvas.design,previous);self.assertTrue(a.empty.has_css_class('invalid'))
                self.assertFalse(a.metric_cards.get_sensitive());self.assertFalse(a.export_menu.get_sensitive())
                self.assertFalse(a.canvas.motion_valid);self.assertEqual(a.inputs['width'].get_text(),'0')

    def test_completion_is_not_starved_by_continuously_ready_default_sources(self):
        a=self.app;target=a.design.values['width']+1
        source=GLib.idle_add(lambda:True,priority=GLib.PRIORITY_DEFAULT)
        try:
            self.edit(target);wait_until(lambda:not a.pending)
            self.assertEqual(a.design.values['width'],target)
        finally:GLib.source_remove(source)

    def test_family_and_document_replacement_discard_older_results(self):
        a=self.app
        for family in ('parallel','spur'):
            with self.subTest(family=family):
                started=Event();release=Event();identity=a.document.token[0]
                try:
                    with self.held_generator(release,started):
                        self.edit(a.design.values['width']+1);wait_until(started.is_set)
                        a.load_config_data(dict(format='solidcraft-riduttori/1',family=family,parameters=generate(family).values))
                        loaded=a.design;self.assertNotEqual(a.document.token[0],identity)
                        release.set();wait_until(lambda:a.geometry_worker.thread is None);pump()
                    self.assertIs(a.design,loaded);self.assertEqual(a.design.family,family);self.assertFalse(a.pending)
                finally:release.set()

    def test_save_is_synchronous_and_invalidates_inflight_preparation(self):
        a=self.app;started=Event();release=Event();target=a.design.values['width']+1;path=self.root/'saved-current.json'
        try:
            with self.held_generator(release,started):
                self.edit(target);wait_until(started.is_set);a.save_project(path=path)
                saved=a.design;self.assertFalse(a.pending);self.assertFalse(a.document.dirty)
                self.assertEqual(json.loads(path.read_text())['parameters']['width'],target)
                release.set();wait_until(lambda:a.geometry_worker.thread is None);pump()
            self.assertIs(a.design,saved);self.assertEqual(a.design.values['width'],target)
        finally:release.set()

    def test_unmapped_window_does_not_apply_and_reprepares_after_show(self):
        a=self.app;previous=a.design;started=Event();release=Event();target=previous.values['width']+1
        try:
            with self.held_generator(release,started):
                self.edit(target);wait_until(started.is_set);a.win.hide();release.set()
                wait_until(lambda:a.geometry_worker.thread is None);pump(.12)
                self.assertIs(a.design,previous);self.assertTrue(a.pending)
                a.win.present();wait_until(lambda:not a.pending)
            self.assertEqual(a.design.values['width'],target)
        finally:release.set();a.win.present()

    def test_rate_only_path_remains_immediate_and_never_submits_geometry(self):
        a=self.app;scene=a.canvas.scene
        with patch.object(a.geometry_worker,'submit',wraps=a.geometry_worker.submit) as submits, \
             patch.object(module,'generate',wraps=module.generate) as generations, \
             patch.object(preview3d,'build_scene',wraps=preview3d.build_scene) as builds:
            a.motion_speed.set_value(scale_rpm(123))
            self.assertEqual(a.design.values['input_rpm'],123)
            a.motion_speed_text.set_text('234');a.motion_speed_text.emit('activate')
            self.assertEqual(a.design.values['input_rpm'],234)
            self.assertEqual((submits.call_count,generations.call_count,builds.call_count),(0,0,0))
        self.assertIs(a.canvas.scene,scene);self.assertFalse(a.pending)

    def test_z_close_discards_late_result_without_waiting_for_worker(self):
        a=self.app;started=Event();release=Event()
        try:
            with self.held_generator(release,started),patch.object(a,'apply_design',wraps=a.apply_design) as applies:
                self.edit(a.design.values['width']+1);wait_until(started.is_set)
                worker=a.geometry_worker.thread;self.assertTrue(worker.daemon)
                a.win.destroy();self.assertTrue(a.geometry_worker.closed);self.assertFalse(a.pending)
                release.set();wait_until(lambda:a.geometry_worker.thread is None);pump()
                self.assertFalse(applies.called)
        finally:release.set()


if __name__=='__main__':unittest.main()
