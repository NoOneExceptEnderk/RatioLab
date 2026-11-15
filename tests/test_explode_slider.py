# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Continuous desktop display placement and native GTK/OpenGL regressions."""
import os
from itertools import combinations, product
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import component_geometry as cg
from geometry import DOUBLE_STYLES, FAMILIES, VARIANTS, generate, is_double
from solid_geometry import point


def catalog_configurations(family):
    from differential_wrist import CONFIGURATIONS, OUTPUT_INTERFACES, CARRIER_STYLES, RATIO_MODES
    from kinematics import options
    from printed_shaft import DESIGNS, KEYED_PRESET, SUPPORTED_SCHEMES

    schemes = options(family)
    for variant in VARIANTS.get(family, (None,)):
        base = {} if variant is None else dict(variant=variant)
        styles = DOUBLE_STYLES if family != 'double' and is_double(family, variant) else (None,)
        for style in styles:
            params = dict(base, double_style=style) if style else base
            if family == 'cycloidal':
                for construction in DESIGNS:
                    preset = KEYED_PRESET if construction == 'keyed_shaft' else {}
                    for scheme in SUPPORTED_SCHEMES if construction == 'fdm_bolted' else schemes:
                        yield dict(params, **preset, eccentric_design=construction, io_scheme=scheme)
            elif family == 'differential':
                for config,interface,carrier,ratio in product(CONFIGURATIONS, OUTPUT_INTERFACES, CARRIER_STYLES, RATIO_MODES):
                    yield dict(params, configuration=config, output_interface=interface, carrier_style=carrier, ratio_mode=ratio)
            elif family == 'planetary' and variant in ('two_stage', 'two_stage_double'):
                for first,second in product(schemes, repeat=2):
                    yield dict(params, io_scheme=first, io_scheme2=second)
            elif schemes:
                for scheme in schemes:
                    yield dict(params, io_scheme=scheme)
            else:
                yield params


class ExplodePlacementTests(unittest.TestCase):
    def test_every_catalog_configuration_has_clearance_from_the_first_step(self):
        from rust_surfaces import surface
        for family in FAMILIES:
            for params in catalog_configurations(family):
                with self.subTest(family=family, **params):
                    design = generate(family, params)
                    boxes = [surface(cg.displayed_part(design, i)).call('solid_bounds')
                             for i in range(len(design.parts))]
                    offsets,minimum = cg.explosion_layout(boxes, family)
                    self.assertTrue(0. <= minimum < 1.)
                    self.assertEqual(cg.explosion_scale(0., minimum), 0.)
                    for amount in (.01, .25, .5, .75, 1.):
                        scale = cg.explosion_scale(amount, minimum)
                        shifted = [(tuple(lo[k]+scale*offset[k] for k in range(3)),
                                    tuple(hi[k]+scale*offset[k] for k in range(3)))
                                   for (lo,hi),offset in zip(boxes, offsets)]
                        for i,j in combinations(range(len(boxes)), 2):
                            a,b = shifted[i],shifted[j]
                            gap = max(max(a[0][k]-b[1][k], b[0][k]-a[1][k]) for k in range(3))
                            self.assertGreater(gap, 0., (amount, design.parts[i].name, design.parts[j].name))

    def test_explosion_preserves_world_translations_for_axes_frames_and_meshes(self):
        from rust_surfaces import surface
        designs = [generate('worm'), generate('differential', dict(configuration='classic')),
                   generate('planetary', dict(variant='two_stage_double')), generate('cycloidal', dict(variant='dual'))]
        for design in designs:
            boxes = [surface(cg.displayed_part(design, i)).call('solid_bounds')
                     for i in range(len(design.parts))]
            offsets,minimum,_ = cg.preview_explosion_layout(design, boxes)
            for index,(source,offset) in enumerate(zip(design.parts, offsets)):
                self.assertIs(cg.displayed_part(design,index,0),source)
                for amount in (.01,.25,.5,.75,1.):
                    with self.subTest(family=design.family,index=index,amount=amount):
                        shift = tuple(v*cg.explosion_scale(amount, minimum) for v in offset)
                        shown=cg.displayed_part(design,index,shift=shift)
                        for xy,z in (((0,0),0),((2,-3),source.width)):
                            nominal=point(source,xy,z,0)
                            actual=point(shown,xy,z,0)
                            for j in range(3):
                                self.assertAlmostEqual(actual[j],nominal[j]+shift[j],places=10)
                self.assertIs(design.parts[index],source)

    def test_internal_pair_sampled_surfaces_stay_clear_through_explosion(self):
        from collision_geometry import Surface, relation
        from motion import translation
        design = generate('internal')
        pinion, ring = [Surface.from_part(p) for p in design.parts[:2]]
        for amount in (.01,.25,.5,.75,1.):
            a = pinion.posed(translation(*cg.explosion_offset(design, 0, amount)))
            b = ring.posed(translation(*cg.explosion_offset(design, 1, amount)))
            self.assertEqual(relation(a,b,.001)['kind'], 'Separated')

    def test_gradual_dual_cycloidal_extraction_keeps_main_surfaces_clear(self):
        from collision_geometry import Surface, relation
        from motion import translation
        from rust_surfaces import surface
        for params in catalog_configurations('cycloidal'):
            if params['variant'] != 'dual':
                continue
            with self.subTest(**params):
                design = generate('cycloidal', params)
                boxes = [surface(part).call('solid_bounds') for part in design.parts]
                offsets,minimum,views = cg.preview_explosion_layout(design, boxes)
                if params['eccentric_design'] == 'fdm_bolted':
                    self.assertNotIn(0, views)
                    self.assertGreater(minimum, 0.)
                    continue
                self.assertIn(0, views)
                main = [i for i,part in enumerate(design.parts) if part.role == 'gear']
                pairs = [(i,j) for i,j in combinations(main,2)
                         if all(max(boxes[i][0][axis]-boxes[j][1][axis],
                                    boxes[j][0][axis]-boxes[i][1][axis]) <= .001 for axis in (0,1))]
                meshes = {i:Surface.from_part(design.parts[i]) for i in {k for pair in pairs for k in pair}}
                for amount in (.01, .02, .05, .1, .15, .25, .4, .5, .6, .75, .9, 1.):
                    for i,j in pairs:
                        relative = amount*(offsets[i][2]-offsets[j][2])
                        a,b = boxes[i],boxes[j]
                        if max(a[0][2]+relative-b[1][2], b[0][2]-a[1][2]-relative) > .001:
                            continue
                        result = relation(meshes[i].posed(translation(0.,0.,relative)), meshes[j], .001)
                        self.assertIn(result['kind'], ('Separated', 'Boundary contact / unresolved'),
                                      (amount, design.parts[i].name, design.parts[j].name, result))

    def test_sweep_selects_radial_opening_and_retains_clearance_step_for_blocked_mesh(self):
        from rust_surfaces import surface
        for family,variant,expected in [('planetary','spur',{2}), ('parallel','helical',{0}),
                                        ('parallel','three_stage_helical',{0,2}),
                                        ('parallel','two_stage_double',{0,2}),
                                        ('differential','spiral',{0,2}), ('wolfrom','spur',{2}),
                                        ('rack','helical',{1}), ('harmonic','cup',None)]:
            with self.subTest(family=family, variant=variant):
                design = generate(family, dict(variant=variant))
                boxes = [surface(part).call('solid_bounds') for part in design.parts]
                offsets,minimum,views = cg.preview_explosion_layout(design, boxes)
                self.assertGreater(minimum, 0.)
                self.assertEqual(0 in views, expected is not None)
                if expected is not None:
                    self.assertEqual({k for shift in offsets for k,value in enumerate(shift) if value}, expected)

    def test_double_helical_planetary_explodes_by_stage(self):
        from collision_geometry import Surface, translation_clear
        from rust_surfaces import surface
        for variant,style in product(('double','two_stage_double'), DOUBLE_STYLES):
            with self.subTest(variant=variant, style=style):
                design = generate('planetary', dict(variant=variant, double_style=style))
                boxes = [surface(part).call('solid_bounds') for part in design.parts]
                offsets,entry,views = cg.preview_explosion_layout(design, boxes)
                self.assertEqual((entry,views), (0., (0,1,2,3)))
                stages = ('S1', 'S2') if variant == 'two_stage_double' else ('S1',)
                stage_offsets = []
                for stage in stages:
                    members = [shift for part,shift in zip(design.parts, offsets)
                               if part.name.startswith((stage+'_Sun', stage+'_Planet_', stage+'_Ring'))
                               and part.role == 'gear']
                    self.assertEqual(len(members), design.values['planets']+2)
                    self.assertEqual(len(set(members)), 1)
                    stage_offsets.append(members[0])
                self.assertEqual(len(set(stage_offsets)), len(stages))
                self.assertGreater(len(set(offsets)), len(stages))
                meshes = {}
                for i,j in combinations(range(len(boxes)), 2):
                    if offsets[i] == offsets[j]:
                        continue
                    a,b = boxes[i],boxes[j]
                    delta = cg.sub(offsets[i], offsets[j])
                    self.assertTrue(any(a[1][k]+delta[k]<b[0][k] or b[1][k]<a[0][k]+delta[k]
                                        for k in range(3)))
                    if any(a[1][k]+max(0.,delta[k])+1e-8<b[0][k] or b[1][k]+1e-8<a[0][k]+min(0.,delta[k])
                           for k in range(3)):
                        continue
                    if not any(delta[:2]) and cg._matching_bore(design.parts[i], design.parts[j]):
                        continue
                    for k in (i,j):
                        if k not in meshes:
                            meshes[k] = Surface.from_part(design.parts[k])
                    self.assertTrue(translation_clear(meshes[i], meshes[j], delta),
                                    (design.parts[i].name, design.parts[j].name))


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
        # The axial separation is foreshortened in the top view.
        c.view('iso')
        self.assertTrue(self.wait_until(lambda:c.camera_transition is None))
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
        observed=[];captured=[];capture=c.capture_png
        def check_capture(callback):
            observed.append((c.exploded,c.motion_phase,c.section))
            def record(data,error):
                captured.append(data)
                callback(data,error)
            capture(record)
        with patch.object(c,'capture_png',side_effect=check_capture):a.export()
        self.assertTrue(self.wait_until(lambda:not a.busy,20))
        self.assertEqual(observed,[(0.,0.,False)])
        self.assertEqual(a.explode_slider.get_value(),.75)
        package=next(a.output_dir.glob('*.package'))
        self.assertEqual((package/'preview.png').read_bytes(),captured[0])
        self.assertEqual((package/'model.stl').read_bytes(),nominal_stl)
        self.assertEqual((package/'assembly.step').read_bytes(),nominal_step)


if __name__=='__main__':unittest.main()
