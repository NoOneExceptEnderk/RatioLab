# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Real paper views, differential actions and exact 0.25 context opacity."""
from copy import deepcopy
from dataclasses import replace
from io import BytesIO
import unittest

import cairo
from geometry import Part,generate,circle
from solid_geometry import signature
from tooth_tip_preview import prepare_component
from view_navigation import rotate
import test_tooth_tip_preview_gui as fixtures
from test_interference_gui import pump,wait_until
from test_tooth_view_geometry import rigid


class ToothViewGuiTests(unittest.TestCase):
    setUpClass=fixtures.ToothTipPreviewGuiTests.__dict__['setUpClass']
    setUp=fixtures.ToothTipPreviewGuiTests.setUp
    close_apps=fixtures.ToothTipPreviewGuiTests.close_apps
    launch=fixtures.ToothTipPreviewGuiTests.launch
    load=fixtures.ToothTipPreviewGuiTests.load
    ready=fixtures.ToothTipPreviewGuiTests.ready
    capture=fixtures.ToothTipPreviewGuiTests.capture

    def vector(self,a,b):
        for x,y in zip(a,b):self.assertAlmostEqual(x,y,places=7)

    def test_real_differential_parts_button_faces_each_actual_shaft_plane(self):
        a=self.launch()
        for configuration,variant in (('wrist','straight'),('wrist','spiral'),('classic','straight'),('classic','spiral')):
            with self.subTest(configuration=configuration,variant=variant):
                self.load(a,'differential',dict(configuration=configuration,variant=variant))
                a.components.open();snapshot=deepcopy(a.project_snapshot());main=a.canvas.scene
                for index,normal in enumerate(((1,0,0),(-1,0,0),(0,0,1))):
                    a.components.select((index,))
                    self.assertTrue(a.components.teeth_button.get_sensitive())
                    a.components.teeth_button.emit('clicked');self.ready(a)
                    detail=a.canvas.tooth_detail
                    self.assertEqual(detail.source_index,index)
                    self.vector(detail.direction,normal)
                    self.vector(rotate(normal,a.canvas.yaw,a.canvas.tilt,a.canvas.roll),(0,0,1))
                    self.vector(rotate(detail.up,a.canvas.yaw,a.canvas.tilt,a.canvas.roll),(0,1,0))
                    self.assertFalse(detail.has_tip_controls)
                    self.assertTrue(any(p.source_index==index and p.opacity==1 for p in detail.scene.parts))
                    self.assertEqual({p.source_index for p in detail.scene.parts},{p.source_index for p in main.parts})
                    self.assertTrue(self.capture(a).startswith(b'\x89PNG'))
                    self.assertIs(a.canvas.scene,main)
                    self.assertEqual(a.project_snapshot(),snapshot)
                a.components.select((3,))
                self.assertFalse(a.components.teeth_button.get_sensitive())
                a.tooth_tips.close();a.components.window.close();pump()

    def test_generic_component_view_tracks_tooth_count_edits_without_changing_the_model(self):
        a=self.launch();self.load(a,'differential')
        a.tooth_tips.focus_component(0);self.ready(a)
        previous=a.canvas.tooth_detail
        a.inputs['side_teeth'].set_text('26')
        self.ready(a)
        self.assertEqual(a.design.values['side_teeth'],26)
        self.assertEqual(a.canvas.tooth_detail.part_name,'Bevel_input_A')
        self.assertIsNot(a.canvas.tooth_detail,previous)
        self.assertTrue(a.export_menu.get_sensitive())

    def test_bevel_variants_are_view_only_and_other_surface_constructions_are_excluded(self):
        from geometry import get_specs
        from tooth_tip_preview import supported
        a=self.launch()
        for variant in ('straight','spiral','zerol'):
            self.load(a,'bevel',dict(variant=variant))
            self.assertFalse(any('topping' in field[0] for field in get_specs('bevel',variant)))
            for index in (0,1):
                a.tooth_tips.focus_component(index);self.ready(a)
                detail=a.canvas.tooth_detail
                self.assertFalse(detail.has_tip_controls)
                self.assertEqual(detail.removed_sections,0)
                self.vector(rotate(detail.direction,a.canvas.yaw,a.canvas.tilt,a.canvas.roll),(0,0,1))
                self.vector(rotate(detail.up,a.canvas.yaw,a.canvas.tilt,a.canvas.roll),(0,1,0))
                self.assertTrue(self.capture(a).startswith(b'\x89PNG'))
            a.tooth_tips.close()
        for family in ('face','hypoid'):
            self.assertFalse(any(supported(p) for p in generate(family).parts))

    def blockers(self):
        design=generate('spur');tip=design.parts[0].profile_metadata['tooth_profile']['tip_radius_mm']
        square=[(-8,-8),(8,-8),(8,8),(-8,8)]
        cover=Part('Front cover',square,width=2,z=15,center=(0,tip),color=(1.,.05,.05))
        behind=replace(cover,name='Behind',z=-15)
        outside=replace(cover,name='Outside',center=(100,100))
        ring=Part('Clear hole',circle(15),[circle(10)],width=2,z=20,center=(0,tip),color=(.4,.7,.4))
        return replace(design,parts=[*design.parts,cover,behind,outside,ring])

    def test_only_real_front_obstructions_fade_and_normal_scene_is_unchanged(self):
        design=self.blockers()
        before=[signature(p) for p in design.parts]
        detail=prepare_component(design,0)
        self.assertEqual(detail.occluded_indices,(1,))
        self.assertEqual({p.source_index:p.opacity for p in detail.scene.parts},{0:1.,1:.25,2:1.,3:1.,4:1.})
        self.assertEqual([signature(p) for p in design.parts],before)
        hidden=prepare_component(design,0,visible_indices=(0,2,3,4))
        self.assertEqual(hidden.occluded_indices,())
        self.assertNotIn(1,{p.source_index for p in hidden.scene.parts})
        frame=((13,-7,21),rigid((1,0,0)),rigid((0,1,0)),rigid((0,0,1)))
        oblique=replace(design,parts=[replace(p,frame=frame) for p in design.parts])
        moved=prepare_component(oblique,0)
        self.assertEqual(moved.occluded_indices,(1,))
        self.vector(moved.direction,rigid((0,0,1)))

    def test_context_opacity_renders_between_zero_and_one_and_restores_camera(self):
        a=self.launch();design=self.blockers()
        a.canvas.set_design(design);a.canvas.view('iso')
        main=a.canvas.scene
        state=(a.canvas.yaw,a.canvas.tilt,a.canvas.roll,a.canvas.zoom,a.canvas.pan_offset)
        detail=prepare_component(design,0,base_scene=main)
        a.canvas.show_tooth_detail(detail)
        self.assertTrue(wait_until(lambda:a.canvas.camera_transition is None))
        cover=next(p for p in detail.scene.parts if p.source_index==1)
        self.assertEqual(cover.opacity,.25)
        order=a.canvas.render_parts(detail.scene)
        self.assertGreater(order.index(cover),max(i for i,p in enumerate(order) if p.opacity==1))
        shots=[]
        for opacity in (0.,.25,1.):
            cover.opacity=opacity
            shots.append(self.capture(a))
        def pixels(png):return bytes(cairo.ImageSurface.create_from_png(BytesIO(png)).get_data())
        p0,pa,p1=map(pixels,shots)
        self.assertGreater(sum(min(x,z)<y<max(x,z) for x,y,z in zip(p0,pa,p1)),100)
        a.canvas.clear_tooth_detail()
        self.assertTrue(wait_until(lambda:a.canvas.camera_transition is None))
        self.assertIs(a.canvas.scene,main)
        self.assertTrue(all(p.opacity==1 for p in main.parts))
        self.assertEqual((a.canvas.yaw,a.canvas.tilt,a.canvas.roll,a.canvas.zoom,a.canvas.pan_offset),state)
        self.assertTrue(self.capture(a).startswith(b'\x89PNG'))

    def test_equal_height_pinion_is_transparent_over_the_rack_working_band(self):
        design=generate('rack',dict(variant='helical',rack_topping_mm=.3))
        detail=prepare_component(design,1)
        self.assertIn(0,detail.occluded_indices)
        self.assertEqual(next(p for p in detail.scene.parts if p.source_index==0).opacity,.25)
        self.assertEqual(next(p for p in detail.scene.parts if p.source_index==1 and p.opacity==1).opacity,1.)

    def test_translucent_cap_keeps_its_actual_hole_open(self):
        a=self.launch();design=generate('spur');tip=design.parts[0].profile_metadata['tooth_profile']['tip_radius_mm']
        ring=Part('Partial obstruction with hole',circle(15),[circle(10)],width=2,z=20,
                  center=(7,tip),color=(1.,.05,.05))
        design=replace(design,parts=[*design.parts,ring])
        a.canvas.set_design(design)
        detail=prepare_component(design,0,base_scene=a.canvas.scene)
        self.assertEqual(detail.occluded_indices,(1,))
        a.canvas.show_tooth_detail(detail)
        self.assertTrue(wait_until(lambda:a.canvas.camera_transition is None))
        mesh=next(p for p in detail.scene.parts if p.source_index==1)
        frames=[]
        for opacity in (0.,.25):
            mesh.opacity=opacity
            surface=cairo.ImageSurface.create_from_png(BytesIO(self.capture(a)))
            from component_geometry import project
            x,y=project((0,tip-1,10),a.canvas.camera_center,detail.radius,a.canvas.zoom,
                a.canvas.yaw,a.canvas.tilt,surface.get_width(),surface.get_height(),a.canvas.roll)
            offset=int(y)*surface.get_stride()+4*int(x)
            frames.append(bytes(surface.get_data())[offset:offset+4])
        self.assertEqual(frames[0],frames[1])


if __name__=='__main__':unittest.main()
