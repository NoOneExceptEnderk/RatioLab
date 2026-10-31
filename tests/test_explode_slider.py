# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Continuous desktop display placement and native GTK/OpenGL regressions."""
import os
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import component_geometry as cg
from geometry import generate, FAMILIES
from solid_geometry import point


class ExplodePlacementTests(unittest.TestCase):
    def test_linear_desktop_offsets_across_families_axes_frames_and_meshes(self):
        designs=[generate(family) for family in FAMILIES]
        designs.append(generate('differential',dict(configuration='classic')))
        for design in designs:
            mid=sum(p.z+p.width/2 for p in design.parts)/len(design.parts)
            for index,source in enumerate(design.parts):
                offset=(source.z+source.width/2-mid)*1.1
                if source.role!='gear':offset+=8 if source.z+source.width/2>=mid else -8
                full=replace(source,z=source.z+offset,center=tuple(v*1.12 for v in source.center))
                self.assertIs(cg.displayed_part(design,index,0),source)
                self.assertEqual(cg.displayed_part(design,index,1),full)
                # Compare real world points to the historical endpoint, rather
                # than assuming local Z is world Z (worm and differential).
                for amount in (.25,.5,.75):
                    with self.subTest(family=design.family,index=index,amount=amount):
                        shown=cg.displayed_part(design,index,amount)
                        translation=cg.explosion_offset(design,index,amount)
                        for xy,z in (((0,0),0),((2,-3),source.width)):
                            nominal=point(source,xy,z,0);endpoint=point(full,xy,z,0)
                            actual=point(shown,xy,z,0)
                            for j in range(3):
                                self.assertAlmostEqual(actual[j],nominal[j]+amount*(endpoint[j]-nominal[j]),places=10)
                                self.assertAlmostEqual(actual[j],nominal[j]+translation[j],places=10)
                self.assertIs(design.parts[index],source)


class ExplodeSliderGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import gi
        gi.require_version('Gtk','4.0')
        from gi.repository import Gtk,Gdk,Gio
        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            raise unittest.SkipTest('Native GTK/OpenGL display required')
        import app
        from test_interference_gui import pump,wait_until
        cls.pump=staticmethod(pump);cls.wait_until=staticmethod(wait_until)
        cls.temp=TemporaryDirectory(prefix='ratiolab-explode-');root=Path(cls.temp.name)
        cls.env=patch.dict(os.environ,dict(XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'),APPDATA=str(root/'roaming'),LOCALAPPDATA=str(root/'local')))
        cls.env.start()
        cls.app=app.ReducerApp()
        cls.app.set_application_id(f'local.solidcraft.reducers.explodetests.p{os.getpid()}')
        cls.app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        cls.app.register(None);cls.app.activate()
        if not wait_until(lambda:cls.app.canvas.gl and not cls.app.pending):
            raise AssertionError('Native preview did not initialize')

    @classmethod
    def tearDownClass(cls):
        for window in cls.app.get_windows():window.destroy()
        cls.pump();cls.env.stop();cls.temp.cleanup()

    def setUp(self):
        a=self.app
        a.components.restore();a.interference.restore_view();a.canvas.reset_motion()
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='parallel',parameters=generate('parallel',dict(input_rpm=60)).values))
        a.restore_view_state(dict(support=False,housing=False,exploded=0.,section=False))
        a.canvas.view('top');a.pick_mode.set_selected(1)
        a.components.open();a.components.measure.set_active(False)
        a.output_dir=Path(self.temp.name)/self._testMethodName
        self.pump(.06)

    def png(self):
        result=[];self.app.canvas.capture_png(lambda data,error:result.append((data,error)))
        self.assertIsNone(result[0][1]);self.assertTrue(result[0][0].startswith(b'\x89PNG'))
        return result[0][0]

    def click(self,q):
        c=self.app.canvas;s=c.scene
        xy=cg.project(q,s.center,s.radius,c.zoom,c.yaw,c.tilt,c.get_width(),c.get_height())
        c.emit('component-click',*xy,False)

    def test_slider_sweep_reuses_gpu_mesh_and_stable_framing(self):
        import preview3d
        a=self.app;c=a.canvas;scene=c.scene;vertices=scene.vertices.tobytes()
        token=a.document.token;history=len(a.document.states);config=a.config()
        self.assertIsNone(a.view_options['exploded'].get_parent())
        self.assertEqual(a.explode_slider.get_adjustment().get_upper(),1.)
        self.assertEqual(a.explode_slider.get_adjustment().get_step_increment(),.01)
        self.assertEqual(a.explode_slider.get_digits(),2)
        captures=[]
        self.png() # Finish any initial GPU upload before counting slider work.
        with patch('preview3d.build_scene',wraps=preview3d.build_scene) as build,patch.object(c.gl,'BufferData',wraps=c.gl.BufferData) as upload:
            for amount in (.25,.5,.75):
                a.explode_slider.set_value(amount)
                self.assertEqual(c.exploded,amount)
                self.assertTrue(a.view_options['exploded'].get_active())
                self.assertIs(c.scene,scene)
                captures.append(self.png())
            for step in range(101):a.explode_slider.set_value(step/100)
            self.png()
            self.assertEqual(build.call_count,0);self.assertEqual(upload.call_count,0)
        self.assertEqual(len(set(captures)),3)
        self.assertEqual(scene.vertices.tobytes(),vertices)
        self.assertEqual(a.config(),config);self.assertEqual(a.document.token,token)
        self.assertEqual(len(a.document.states),history)
        self.assertEqual(c.gl.GetError(),0);self.assertIsNone(c.failure)
        # Existing selections must not make every amount change rebuild their
        # unchanged nominal bounds in the component inspector.
        a.components.select((0,1));a.explode_slider.set_value(.4)
        with patch.object(a.components,'update',wraps=a.components.update) as update:
            for amount in (.41,.42,.43):a.explode_slider.set_value(amount)
            self.assertEqual(update.call_count,0)

    def test_partial_surface_picking_measurement_and_bounded_cache(self):
        a=self.app;c=a.components
        for amount in (.25,.5,.75):
            a.explode_slider.set_value(amount);c.measure.set_active(False)
            offset=cg.explosion_offset(a.design,0,amount)
            q=tuple(v+d for v,d in zip((10,0,10),offset))
            self.click(q);self.assertEqual(c.selected,(0,))
            c.measure.set_active(True);self.click(q)
            self.assertEqual(len(c.points),1)
            for actual,expected in zip(c.points[0][1],q):self.assertAlmostEqual(actual,expected,places=6)
            self.assertEqual({key[1] for key in c.cache},{amount})
            self.assertLessEqual(len(c.cache),len(a.design.parts))
            a.explode_slider.set_value(amount+.01)
            self.assertFalse(c.points);self.assertFalse(c.cache)

    def test_pause_preserves_phase_start_assembles_and_initial_pose_resets(self):
        a=self.app;c=a.canvas
        c.motion_phase=.42;c.motion_enabled=True
        c.set_motion_playing(True);self.pump(.04)
        before=c.motion_phase
        a.explode_slider.set_value(.37)
        self.assertFalse(c.motion_playing);self.assertTrue(c.motion_enabled)
        self.assertGreaterEqual(c.motion_phase,before)
        paused=c.motion_phase;self.pump(.04);self.assertEqual(c.motion_phase,paused)
        a.motion_play.emit('clicked')
        self.assertTrue(c.motion_playing);self.assertEqual(c.exploded,0.)
        self.assertEqual(a.explode_slider.get_value(),0.);self.assertEqual(c.motion_phase,paused)
        a.explode_slider.set_value(.75);a.motion_reset.emit('clicked')
        self.assertEqual((c.exploded,c.motion_phase,c.motion_enabled,c.motion_playing),(0.,0.,False,False))
        self.assertEqual(a.explode_slider.get_value(),0.)

    def test_exact_restore_isolate_interference_and_selected_package(self):
        from interference import Settings
        a=self.app;c=a.components
        a.explode_slider.set_value(.37);c.select((0,1));c.isolate()
        a.explode_slider.set_value(.81);c.restore()
        self.assertEqual(a.canvas.exploded,.37);self.assertEqual(a.explode_slider.get_value(),.37)
        i=a.interference;i.open();i.start(Settings(step_degrees=180,max_seconds=20))
        self.assertTrue(self.wait_until(lambda:i.cancel is None,25));self.assertTrue(i.result.rows)
        i.list.select_row(i.list.get_row_at_index(0))
        self.assertEqual(a.canvas.exploded,0.);self.assertIsNotNone(a.canvas.inspection_phase)
        i.restore_view()
        self.assertEqual(a.canvas.exploded,.37);self.assertEqual(a.explode_slider.get_value(),.37)
        c.select((0,1));c.points=[(0,(10,0,10))];c.pose=c.pose_key();c.measure_text.set_text('Fractional displayed point')
        points=list(c.points);pose=c.pose
        with patch.object(a.canvas,'capture_png',wraps=a.canvas.capture_png) as capture:
            c.export('package')
            self.assertEqual(capture.call_count,1)
        self.assertTrue(self.wait_until(lambda:not a.busy,20))
        self.assertEqual(a.canvas.exploded,.37);self.assertEqual(a.explode_slider.get_value(),.37)
        self.assertEqual(c.points,points);self.assertEqual(c.pose,pose)
        self.assertEqual(c.measure_text.get_text(),'Fractional displayed point')
        self.assertEqual(len(list(a.output_dir.glob('*.selected-package/preview.png'))),1)

    def test_nominal_export_coordinates_and_package_frame_at_partial_amount(self):
        import stl_export,cad_export
        a=self.app;c=a.canvas
        a.output_dir.mkdir()
        stl=a.output_dir/'nominal.stl';step=a.output_dir/'nominal.step'
        stl_export.write_stl(stl,a.design.parts);cad_export.write(step,a.design.parts)
        nominal_stl=stl.read_bytes();nominal_step=step.read_bytes()
        a.explode_slider.set_value(.75)
        stl_export.write_stl(stl,a.design.parts);cad_export.write(step,a.design.parts)
        self.assertEqual(stl.read_bytes(),nominal_stl);self.assertEqual(step.read_bytes(),nominal_step)
        observed=[];capture=c.capture_png
        def check_capture(callback):
            observed.append((c.exploded,c.motion_phase,c.section))
            capture(callback)
        with patch.object(c,'capture_png',side_effect=check_capture):a.export()
        self.assertTrue(self.wait_until(lambda:not a.busy,20))
        self.assertEqual(observed,[(0.,0.,False)])
        self.assertEqual(a.explode_slider.get_value(),0.)
        package=next(a.output_dir.glob('*.package'))
        self.assertEqual((package/'preview.png').read_bytes(),self.png())
        self.assertEqual((package/'model.stl').read_bytes(),nominal_stl)
        self.assertEqual((package/'assembly.step').read_bytes(),nominal_step)


if __name__=='__main__':unittest.main()
