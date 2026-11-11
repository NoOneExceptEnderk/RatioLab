# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Automatic native edits, rendered transparency, camera restoration and staleness."""
from copy import deepcopy
from io import BytesIO
from math import hypot
from threading import Event
import unittest
from unittest.mock import patch

import cairo
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk
import stl_export
import tooth_tip_ui
import tooth_tip_preview
import preview3d
from geometry import generate
from geometry_quality import with_quality
from tooth_tip_preview import component_index
import test_tooth_tips_gui as fixtures
from test_interference_gui import pump, wait_until


class ToothTipPreviewGuiTests(unittest.TestCase):
    setUpClass = fixtures.ToothTipGuiTests.__dict__['setUpClass']
    setUp = fixtures.ToothTipGuiTests.setUp
    close_apps = fixtures.ToothTipGuiTests.close_apps
    launch = fixtures.ToothTipGuiTests.launch
    load = fixtures.ToothTipGuiTests.load

    def ready(self, app):
        self.assertTrue(wait_until(lambda: not app.pending and not app.tooth_tips.waiting
                        and app.canvas.tooth_detail is not None and app.canvas.camera_transition is None))

    def edit(self, app, field, text):
        app.geometry_group_boxes[app.input_geometry_groups[field]]._section.set_expanded(True)
        app.inputs[field].grab_focus()
        app.inputs[field].set_text(text)
        self.ready(app)

    def capture(self, app):
        output = []
        app.canvas.capture_png(lambda data, error: output.append((data, error)))
        self.assertTrue(wait_until(lambda: bool(output)))
        self.assertIsNone(output[0][1])
        return output[0][0]

    def test_removed_band_follows_the_current_preview_sweep_quality(self):
        design = generate('helical', dict(semitopping_mm=.25))
        counts = []
        for tolerance in (.1, .005):
            with patch.object(preview3d, 'build_scene', wraps=preview3d.build_scene) as build:
                tooth_tip_preview.prepare(with_quality(design, dict(preview_mm=tolerance)), 'semitopping_mm')
            parts = build.call_args[0][0].parts
            self.assertTrue(all(p.surface_tolerance_mm == tolerance for p in parts))
            counts.append(len(parts[1].stations))
        self.assertGreater(counts[1], counts[0])

    def test_real_spin_increment_changes_geometry_and_focuses_without_manual_refresh(self):
        a = self.launch(); self.load(a, 'spur')
        full_scene = a.canvas.scene
        original = list(a.design.parts[0].outer)
        a.canvas.yaw = .2; a.canvas.tilt = -.4; a.canvas.zoom = 1.7
        a.canvas.pan_offset = (1., 2., 3.)
        camera = (a.canvas.yaw, a.canvas.tilt, a.canvas.zoom, a.canvas.pan_offset)
        before_scale=a.canvas.zoom/a.canvas.camera_radius
        a.geometry_group_boxes['tooth_tips_']._section.set_expanded(True)
        a.inputs['topping_mm'].grab_focus(); self.ready(a)
        self.assertEqual(a.canvas.tooth_detail.removed_sections, 0)
        focused_center=a.canvas.camera_center
        a.inputs['topping_mm'].spin(Gtk.SpinType.STEP_FORWARD, 0)
        self.ready(a)
        self.assertEqual(a.design.values['topping_mm'], .01)
        self.assertNotEqual(a.design.parts[0].outer, original)
        self.assertEqual(a.canvas.tooth_detail.source_index, 0)
        self.assertEqual(a.canvas.tooth_detail.removed_sections, 3)
        self.assertLess(a.canvas.camera_radius, full_scene.radius/3)
        self.assertEqual(a.canvas.camera_center, focused_center)
        restored_views = []
        a.canvas.connect('view-changed', lambda canvas, name: restored_views.append(
            (canvas.yaw, canvas.tilt, canvas.zoom, canvas.pan_offset)))
        a.tooth_tips.close(); self.assertTrue(wait_until(lambda:a.canvas.camera_transition is None))
        self.assertIsNone(a.canvas.tooth_detail)
        self.assertEqual((a.canvas.yaw,a.canvas.tilt,a.canvas.pan_offset),(camera[0],camera[1],camera[3]))
        self.assertAlmostEqual(a.canvas.zoom/a.canvas.camera_radius,before_scale)
        self.assertEqual(restored_views[-1],(a.canvas.yaw,a.canvas.tilt,a.canvas.zoom,a.canvas.pan_offset))

    def test_transparent_material_is_rendered_and_never_enters_model_or_stl(self):
        a = self.launch(); self.load(a, 'spur')
        self.edit(a, 'semitopping_mm', '.35')
        design = a.design; scene = a.canvas.scene
        snapshot = deepcopy(a.project_snapshot())
        signature = stl_export.write_stl(self.root/'before.stl', design.parts).read_bytes()
        detail = a.canvas.tooth_detail
        translucent = self.capture(a)
        for mesh in detail.scene.parts[1:]: mesh.opacity = 0.
        hidden = self.capture(a)
        for mesh in detail.scene.parts[1:]: mesh.opacity = 1.
        opaque = self.capture(a)
        self.assertNotEqual(translucent, hidden)
        self.assertNotEqual(translucent, opaque)
        def pixels(png):
            surface = cairo.ImageSurface.create_from_png(BytesIO(png))
            return bytes(surface.get_data())
        p0, pa, p1 = map(pixels, (hidden, translucent, opaque))
        self.assertGreater(sum(min(x,z) < y < max(x,z) for x,y,z in zip(p0,pa,p1)), 20)
        self.assertIs(a.design, design); self.assertIs(a.canvas.scene, scene)
        self.assertEqual(a.project_snapshot(), snapshot)
        self.assertEqual(stl_export.write_stl(self.root/'after.stl', design.parts).read_bytes(), signature)
        self.assertEqual(len(design.parts), 1)
        a.canvas.reset_motion()
        self.assertIsNone(a.canvas.tooth_detail)
        self.assertFalse(a.tooth_tips.reset_camera.get_visible())

    def test_focus_follows_helical_multistage_internal_wolfrom_and_both_rack_members(self):
        a = self.launch()
        cases = [('helical', {}, 'semitopping_mm'),
            ('double', {'variant':'separated'}, 'topping_mm'),
            ('parallel', {'variant':'two_stage_helical'}, 'wheel2_semitopping_mm'),
            ('internal', {'variant':'helical'}, 'ring_semitopping_mm'),
            ('planetary', {'variant':'two_stage_double'}, 'planet2_topping_mm'),
            ('wolfrom', {'variant':'double'}, 'planet2_semitopping_mm'),
            ('rack', {'variant':'double'}, 'pinion_semitopping_mm'),
            ('rack', {'variant':'helical'}, 'rack_topping_mm')]
        for family, values, field in cases:
            with self.subTest(family=family, field=field):
                self.load(a, family, values)
                self.edit(a, field, '.15')
                detail = a.canvas.tooth_detail
                index = component_index(a.design, field)
                part = a.design.parts[index]
                self.assertEqual(detail.source_index, index)
                self.assertEqual(detail.part_name, part.name)
                self.assertGreater(detail.removed_sections, 0)
                self.assertTrue(any(p.source_index==index and p.opacity==1. for p in detail.scene.parts))
                self.assertTrue({p.source_index for p in a.canvas.scene.parts}.issubset(
                    {p.source_index for p in detail.scene.parts}))
                self.assertEqual(a.design.values[field], .15)
                self.assertGreater(detail.band_mm[0], part.width/2+part.gap/2 if part.double else 0.)
                self.assertTrue(self.capture(a).startswith(b'\x89PNG'))
                self.assertIsNone(a.canvas.failure)
                if part.internal:
                    self.assertAlmostEqual(hypot(detail.target[0]-part.center[0],
                        detail.target[1]-part.center[1]), part.profile_metadata['tooth_profile']['tip_radius_mm'])

    def test_rack_camera_and_removed_band_follow_actual_tooth_lands_not_fixed_base(self):
        for variant, helix in (('helical', 30), ('helical', -30), ('double', 30)):
            with self.subTest(variant=variant, helix=helix):
                design = generate('rack', dict(variant=variant, helix=helix,
                                              rack_topping_mm=.2, rack_semitopping_mm=.25))
                source = design.parts[1]
                with patch.object(preview3d, 'build_scene', wraps=preview3d.build_scene) as build:
                    detail = tooth_tip_preview.prepare(design, 'rack_semitopping_mm')
                count = int(design.values['rack_teeth'])
                first = 3+6*(count-1-count//2)
                def land(station):
                    a,b = station['outer'][first+2:first+4]
                    return ((a[0]+b[0])/2., (a[1]+b[1])/2.)
                def actual_land(z):
                    for a,b in zip(source.stations,source.stations[1:]):
                        if a['z'] <= z <= b['z'] and b['z'] > a['z']:
                            f=(z-a['z'])/(b['z']-a['z'])
                            return tuple((1-f)*x+f*y for x,y in zip(land(a),land(b)))
                    self.fail('Focused tooth is outside the actual rack sections')
                expected = actual_land(detail.target[2]-source.z)
                for actual,expected_coordinate in zip(detail.target[:2], expected):
                    self.assertAlmostEqual(actual, expected_coordinate, places=7)
                # The removed sections must translate with those same actual
                # tooth lands, independently of the fixed base/end vertices.
                ghosts = build.call_args[0][0].parts[1:]
                self.assertGreater(len(ghosts), 0)
                head = tooth_tip_preview.call('tooth_tip_preview', dict(
                    source=source.profile_metadata['tip_preview_source']))
                for polygon,ghost in zip(head['polygons'],ghosts):
                    for station in ghost.stations:
                        expected = actual_land(station['z'])
                        delta = tuple(x-y for x,y in zip(expected,head['target_xy']))
                        for q,shown in zip(polygon,station['outer']):
                            for coordinate,base,shift in zip(shown,q,delta):
                                self.assertAlmostEqual(coordinate,base+shift,places=7)
                if variant=='helical':
                    self.assertNotEqual(source.stations[0]['outer'][3][0], source.stations[-1]['outer'][3][0])
                self.assertEqual(source.stations[0]['outer'][0], source.stations[-1]['outer'][0])

    def test_invalid_draft_labels_last_valid_detail_and_unrelated_edit_exits(self):
        a = self.launch(); self.load(a, 'spur')
        self.edit(a, 'semitopping_mm', '.2')
        detail = a.canvas.tooth_detail
        a.inputs['semitopping_mm'].set_text('4')
        self.assertTrue(wait_until(lambda: not a.pending))
        self.assertIs(a.canvas.tooth_detail, detail)
        self.assertIn('Last valid', a.empty.get_text())
        self.assertFalse(a.export_menu.get_sensitive())
        self.edit(a, 'semitopping_mm', '.15')
        self.assertIsNot(a.canvas.tooth_detail, detail)
        a.inputs['width'].set_text('12')
        self.ready(a)
        self.assertIsNotNone(a.canvas.tooth_detail)
        self.assertIsNotNone(a.tooth_tips.field)

    def test_focus_is_view_only_and_obsolete_background_result_cannot_reopen_it(self):
        a = self.launch(); self.load(a, 'spur')
        snapshot = deepcopy(a.project_snapshot()); design = a.design; scene = a.canvas.scene
        started, release = Event(), Event()
        original = tooth_tip_ui.prepare
        def held(*args,**kwargs):
            started.set()
            if not release.wait(5): raise TimeoutError('Test detail worker not released')
            return original(*args,**kwargs)
        try:
            with patch.object(tooth_tip_ui, 'prepare', side_effect=held):
                a.tooth_tips.focus('topping_mm')
                self.assertTrue(wait_until(started.is_set))
                a.canvas.view('top')
                release.set()
                self.assertTrue(wait_until(lambda: a.tooth_tips.worker.thread is None))
                pump(.1)
            self.assertIsNone(a.canvas.tooth_detail)
            self.assertFalse(a.tooth_tips.reset_camera.get_visible())
            self.assertIs(a.design, design); self.assertIs(a.canvas.scene, scene)
            self.assertEqual(a.project_snapshot(), snapshot)
        finally:
            release.set()


if __name__ == '__main__':
    unittest.main()
