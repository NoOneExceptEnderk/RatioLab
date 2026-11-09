# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Real GTK acceptance of nominal reuse and transactional surface detail."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk,Gio,GLib
import app as module
from quality_ui import open_quality


def pump(until=lambda:False,seconds=3.):
    deadline=time.monotonic()+seconds;context=GLib.MainContext.default()
    while time.monotonic()<deadline:
        while context.pending() and time.monotonic()<deadline:context.iteration(False)
        if until():return True
        time.sleep(.003)
    return bool(until())


class GeometryQualityGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            raise unittest.SkipTest('Real GTK display required')
        cls.temp=TemporaryDirectory(prefix='ratiolab-quality-gui-');cls.root=Path(cls.temp.name)
        cls.env=patch.dict(os.environ,dict(XDG_CONFIG_HOME=str(cls.root/'config'),XDG_DATA_HOME=str(cls.root/'data')));cls.env.start()
        cls.app=module.ReducerApp();cls.app.set_application_id('local.ratiolab.quality.p'+str(os.getpid()))
        cls.app.set_flags(Gio.ApplicationFlags.NON_UNIQUE);cls.app.register(None);cls.app.activate()
        assert pump(lambda:cls.app.canvas.gl is not None)

    @classmethod
    def tearDownClass(cls):
        for w in cls.app.get_windows():w.destroy()
        cls.env.stop();cls.temp.cleanup()

    def setUp(self):
        worker=getattr(self.app,'quality_worker',None)
        if worker:
            worker.invalidate()
            self.assertTrue(pump(lambda:worker.thread is None,seconds=5.))
        self.app.canvas.reset_motion()
        self.app.load_config_data(dict(format='solidcraft-riduttori/1',family='helical',parameters={'teeth':24,'helix':25}))
        pump(lambda:not self.app.pending,seconds=.1)

    def apply(self,preview='',export=''):
        dialog=open_quality(self.app);self.assertIsNotNone(dialog)
        self.app.quality_entries['preview_mm'].set_text(preview)
        self.app.quality_entries['export_mm'].set_text(export)
        dialog.response(Gtk.ResponseType.APPLY)
        self.assertTrue(pump(lambda:not dialog.get_visible(),seconds=10.))

    def test_export_only_change_reuses_scene_and_nominal_parts_and_keeps_phase(self):
        app=self.app;scene=app.canvas.scene;parts=app.design.parts;values=app.design.values.copy()
        app.canvas.motion_phase=1.234;app.components.selected=(0,);app.canvas.selected_indices=(0,)
        with patch('app.generate',side_effect=AssertionError('No nominal regeneration')):
            self.apply(export='.005')
        self.assertIs(app.canvas.scene,scene);self.assertIs(app.design.parts,parts)
        self.assertEqual(app.design.values,values);self.assertEqual(app.canvas.motion_phase,1.234)
        self.assertEqual(app.components.selected,(0,));self.assertEqual(app.quality,{'export_mm':.005})

    def test_preview_changes_mesh_and_picking_policy_without_nominal_regeneration(self):
        from component_geometry import displayed_part
        app=self.app;scene=app.canvas.scene;parts=app.design.parts
        with patch('app.generate',side_effect=AssertionError('No nominal regeneration')):
            self.apply(preview='.1',export='.005')
        self.assertIs(app.design.parts,parts);self.assertIsNot(app.canvas.scene,scene)
        self.assertLess(len(app.canvas.scene.vertices),len(scene.vertices))
        self.assertEqual(displayed_part(app.design,0).surface_tolerance_mm,.1)
        self.assertEqual(parts[0].surface_tolerance_mm,.02)

    def test_save_open_and_undo_redo_keep_independent_requests(self):
        app=self.app;self.apply('.1','.005')
        path=self.root/'quality.config.json';self.assertTrue(app.save_project(path=path))
        config=json.loads(path.read_text());self.assertEqual(config['quality'],app.quality)
        self.apply('.05','.01');app.undo_project();self.assertEqual(app.quality,{'preview_mm':.1,'export_mm':.005})
        app.redo_project();self.assertEqual(app.quality,{'preview_mm':.05,'export_mm':.01})
        app.load_config_data(config,path);self.assertEqual(app.quality,config['quality']);self.assertFalse(app.document.dirty)

    def test_failed_preview_preserves_accepted_source_document_and_scene(self):
        app=self.app;dialog=open_quality(app);source=app.design;scene=app.canvas.scene;token=app.document.token
        app.quality_entries['preview_mm'].set_text('1e-12');dialog.response(Gtk.ResponseType.APPLY)
        self.assertTrue(pump(lambda:dialog.get_widget_for_response(Gtk.ResponseType.APPLY).get_sensitive(),seconds=10.))
        self.assertTrue(dialog.get_visible());self.assertIs(app.design,source);self.assertIs(app.canvas.scene,scene)
        self.assertEqual(app.document.token,token);self.assertEqual(app.quality,{})
        dialog.response(Gtk.ResponseType.CANCEL)

    def test_stale_quality_reply_and_cancel_never_replace_the_accepted_source(self):
        from threading import Event
        from preview3d import build_scene
        for cancel in (False,True):
            started=Event();release=Event();finished=Event();app=self.app;source=app.design;scene=app.canvas.scene
            def delayed(*args,**kwargs):
                started.set();release.wait(4.)
                try:return build_scene(*args,**kwargs)
                finally:finished.set()
            with patch('preview3d.build_scene',side_effect=delayed):
                dialog=open_quality(app);app.quality_entries['preview_mm'].set_text('.1');dialog.response(Gtk.ResponseType.APPLY)
                self.assertTrue(pump(started.is_set,seconds=2.))
                if cancel:dialog.response(Gtk.ResponseType.CANCEL)
                else:
                    snapshot=app.project_snapshot();snapshot['quality']={'export_mm':.01};app.document.record(snapshot)
                release.set();self.assertTrue(pump(finished.is_set,seconds=3.));pump(seconds=.05)
                self.assertIs(app.design,source);self.assertIs(app.canvas.scene,scene);self.assertEqual(app.quality,{})
                if not cancel:dialog.response(Gtk.ResponseType.CANCEL)

    def test_submicrometre_export_request_is_saved_without_blocking_preview(self):
        app=self.app;scene=app.canvas.scene
        self.apply(export='0.0000001')
        self.assertIs(app.canvas.scene,scene);self.assertEqual(app.config()['quality']['export_mm'],1e-7)


    def test_cancel_before_worker_start_and_reopen_share_one_worker(self):
        app=self.app;source=app.design;scene=app.canvas.scene;token=app.document.token;threads=[]
        class Deferred:
            def __init__(self,target,**kwargs):self.target=target
            def start(self):threads.append(self)
        from preview3d import build_scene
        with patch('geometry_refresh.Thread',Deferred),patch('preview3d.build_scene',wraps=build_scene) as build:
            dialog=open_quality(app);app.quality_entries['preview_mm'].set_text('.1')
            dialog.response(Gtk.ResponseType.APPLY);worker=app.quality_worker
            dialog.response(Gtk.ResponseType.CANCEL)
            self.assertEqual(app.document.token,token);self.assertIs(app.design,source);self.assertIs(app.canvas.scene,scene)
            reopened=open_quality(app);app.quality_entries['preview_mm'].set_text('.05')
            reopened.response(Gtk.ResponseType.APPLY)
            self.assertIs(app.quality_worker,worker);self.assertEqual(len(threads),1)
            threads[0].target()
            self.assertTrue(pump(lambda:not reopened.get_visible(),seconds=5.))
            self.assertEqual(build.call_count,1);self.assertEqual(app.quality,{'preview_mm':.05})
        self.assertIsNone(worker.thread)

    def test_cancel_interrupts_native_work_and_releases_cursors(self):
        from threading import Event
        import rust_geometry as kernel
        from solid_geometry import kernel_part
        from preview3d import build_scene
        started=Event();release=Event();stopped=Event();finished=Event();checks=[]
        app=self.app;source=app.design;scene=app.canvas.scene;token=app.document.token
        def hold():
            checks.append(True)
            if len(checks)==8:
                started.set()
                if not release.wait(5.):raise TimeoutError('Native test callback was not released')
            kernel.control_check()
        def native_then_scene(*args,**kwargs):
            try:
                kernel.call_buffer('solid_triangles',dict(part=kernel_part(source.parts[0])),72,check=hold)
                return build_scene(*args,**kwargs)
            except Exception:
                stopped.set();raise
            finally:finished.set()
        try:
            with patch('preview3d.build_scene',side_effect=native_then_scene):
                dialog=open_quality(app);app.quality_entries['preview_mm'].set_text('.1')
                dialog.response(Gtk.ResponseType.APPLY)
                self.assertTrue(pump(started.is_set,seconds=3.))
                dialog.response(Gtk.ResponseType.CANCEL);release.set()
                self.assertTrue(pump(finished.is_set,seconds=3.))
                self.assertTrue(pump(lambda:app.quality_worker.thread is None,seconds=3.))
            self.assertTrue(stopped.is_set());self.assertEqual(app.document.token,token)
            self.assertIs(app.design,source);self.assertIs(app.canvas.scene,scene);self.assertEqual(app.quality,{})
            self.assertEqual(kernel.call('surface_stats')['cursors'],0)
        finally:release.set()

    def test_late_completion_cannot_apply_to_reopened_dialog(self):
        app=self.app;source=app.design;scene=app.canvas.scene;token=app.document.token;posted=[]
        dialog=open_quality(app);worker=app.quality_worker
        with patch.object(worker,'post',side_effect=lambda *args:posted.append(args)):
            app.quality_entries['preview_mm'].set_text('.1');dialog.response(Gtk.ResponseType.APPLY)
            self.assertTrue(pump(lambda:bool(posted),seconds=5.))
            dialog.response(Gtk.ResponseType.CANCEL);reopened=open_quality(app)
            callback,*args=posted.pop();callback(*args)
            self.assertIs(app.quality_dialog,reopened);self.assertTrue(reopened.get_visible())
            self.assertEqual(app.document.token,token);self.assertIs(app.design,source);self.assertIs(app.canvas.scene,scene)
            self.assertEqual(app.quality,{})
            reopened.response(Gtk.ResponseType.CANCEL)

    def test_large_fine_static_materials_render_and_dynamic_attributes_restore(self):
        import ctypes
        from gl_loader import bind_function
        app=self.app
        cases=[('planetary',dict(variant='two_stage_double'),{'preview_mm':.005},0),
               ('harmonic',{},None,1),('helical',{},None,1)]
        for family,parameters,quality,enabled in cases:
            config=dict(format='solidcraft-riduttori/1',family=family,parameters=parameters)
            if quality:config['quality']=quality
            app.load_config_data(config)
            captured=[];app.canvas.capture_png(lambda data,error:captured.append((data,error)))
            self.assertTrue(captured);self.assertIsNone(captured[0][1]);self.assertGreater(len(captured[0][0]),1000)
            app.canvas.make_current();state=ctypes.c_int()
            get=bind_function(app.canvas.gl.lib,'GetVertexAttribiv',None,
                [ctypes.c_uint,ctypes.c_uint,ctypes.POINTER(ctypes.c_int)])
            # Rendering unbinds its VAO. Inspect the viewport's actual array,
            # not the default VAO's unrelated attribute state.
            app.canvas.gl.BindVertexArray(app.canvas.vao.value)
            try:get(2,0x8622,ctypes.byref(state))
            finally:app.canvas.gl.BindVertexArray(0)
            self.assertEqual(state.value,enabled);self.assertEqual(app.canvas.gl.GetError(),0)
            self.assertEqual(bool(app.canvas.scene.materials),bool(enabled))


if __name__=='__main__':unittest.main()
