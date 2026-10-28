# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Controlli della geometria 3D relative to quote, twist e assi del CAD."""
import unittest
from unittest.mock import Mock, patch
from math import hypot, isfinite
from geometry import generate, Part
from preview3d import (build_scene, point, create_preview_context, context_uses_es,
                       Preview3D, Gdk, GLib, VERTEX, FRAGMENT, shader_source)


class ContextNegotiationTests(unittest.TestCase):
    def context(self, api=Gdk.GLAPI.GL, version=(3,3), error=None):
        context=Mock()
        context.get_api.return_value=api
        context.get_version.return_value=version
        context.realize.side_effect=error
        return context

    def test_desktop_backend_is_allowed_and_requests_33(self):
        context=self.context()
        surface=Mock()
        surface.create_gl_context.return_value=context
        self.assertIs(create_preview_context(surface,Gdk.GLAPI.GL|Gdk.GLAPI.GLES),context)
        context.set_allowed_apis.assert_called_once_with(Gdk.GLAPI.GL)
        context.set_required_version.assert_called_once_with(3,3)
        surface.create_gl_context.assert_called_once()

    def test_unavailable_desktop_falls_back_to_gles_30(self):
        desktop=self.context(error=GLib.Error('desktop unavailable'))
        es=self.context(Gdk.GLAPI.GLES,(3,0))
        surface=Mock()
        surface.create_gl_context.side_effect=[desktop,es]
        self.assertIs(create_preview_context(surface,Gdk.GLAPI.GL|Gdk.GLAPI.GLES),es)
        es.set_allowed_apis.assert_called_once_with(Gdk.GLAPI.GLES)
        es.set_required_version.assert_called_once_with(3,0)

    def test_explicit_api_does_not_try_the_other_backend(self):
        for api,version in ((Gdk.GLAPI.GL,(3,3)),(Gdk.GLAPI.GLES,(3,0))):
            with self.subTest(api=api):
                context=self.context(api,version)
                surface=Mock()
                surface.create_gl_context.return_value=context
                self.assertIs(create_preview_context(surface,api),context)
                context.set_allowed_apis.assert_called_once_with(api)
                context.set_required_version.assert_called_once_with(*version)
                surface.create_gl_context.assert_called_once()

    def test_actual_versions_are_checked_before_accepting_a_context(self):
        desktop=self.context(version=(3,2))
        es=self.context(Gdk.GLAPI.GLES,(2,0))
        surface=Mock()
        surface.create_gl_context.side_effect=[desktop,es]
        with self.assertRaisesRegex(GLib.Error,'OpenGL 3.3 / GLES 3.0') as raised:
            create_preview_context(surface,Gdk.GLAPI.GL|Gdk.GLAPI.GLES)
        self.assertEqual(surface.create_gl_context.call_count,2)
        self.assertIn('OpenGL 3.3:',str(raised.exception))
        self.assertIn('OpenGL ES 3.0:',str(raised.exception))

    def test_creation_failures_keep_both_backend_diagnostics(self):
        surface=Mock()
        surface.create_gl_context.side_effect=[GLib.Error('desktop unavailable'),GLib.Error('ES unavailable')]
        with self.assertRaises(GLib.Error) as raised:
            create_preview_context(surface,Gdk.GLAPI.GL|Gdk.GLAPI.GLES)
        self.assertIn('desktop unavailable',str(raised.exception))
        self.assertIn('ES unavailable',str(raised.exception))

    def test_no_allowed_api_reports_failure_without_creating_context(self):
        surface=Mock()
        with self.assertRaisesRegex(GLib.Error,'no API allowed'):
            create_preview_context(surface,0)
        surface.create_gl_context.assert_not_called()

    def test_shader_dialect_follows_the_realized_context(self):
        for api,version,use_es in ((Gdk.GLAPI.GL,(4,6),False),(Gdk.GLAPI.GLES,(3,0),True)):
            with self.subTest(api=api):
                canvas=Mock(use_es=not use_es)
                canvas.get_error.return_value=None
                canvas.get_context.return_value=self.context(api,version)
                gl=Mock()
                gl.GetProgramiv.side_effect=lambda program,key,status: setattr(status._obj,'value',1)
                with patch('preview3d.GL',return_value=gl):
                    Preview3D.on_realize(canvas)
                self.assertIs(canvas.use_es,use_es)
                self.assertIsNone(canvas.failure)
                self.assertEqual(gl.shader.call_args_list[0].args,(0x8B31,shader_source(VERTEX,use_es)))
                self.assertEqual(gl.shader.call_args_list[1].args,(0x8B30,shader_source(FRAGMENT,use_es)))
                self.assertTrue(shader_source(VERTEX,use_es).startswith('#version 300 es' if use_es else '#version 330 core'))

    def test_below_minimum_context_never_initializes_shaders(self):
        canvas=Mock()
        canvas.get_error.return_value=None
        canvas.get_context.return_value=self.context(version=(3,2))
        with patch('preview3d.GL') as gl, patch('traceback.print_exc'):
            Preview3D.on_realize(canvas)
        gl.assert_not_called()
        self.assertIn('or newer is required',canvas.failure)

    def test_unknown_context_api_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'requires an OpenGL'):
            context_uses_es(self.context(api=0))


class FramebufferTests(unittest.TestCase):
    def test_rgba_capture_keeps_color_and_vertical_orientation_in_cairo(self):
        import sys
        from unittest.mock import patch
        from preview3d import framebuffer_argb32
        # GL bottom row red/green; top row blue/white.
        pixels=bytes((255,0,0,255,0,255,0,255,0,0,255,255,255,255,255,255))
        for endian in ('little','big'):
            with self.subTest(endian=endian), patch.object(sys,'byteorder',endian):
                raw=framebuffer_argb32(pixels,2,2)
                words=[int.from_bytes(raw[i:i+4],endian) for i in range(0,16,4)]
                self.assertEqual(words,[0xff0000ff,0xffffffff,0xffff0000,0xff00ff00])

class PreviewTests(unittest.TestCase):

    def test_spur_thickness_and_bounding(self):
        scene = build_scene(generate('spur', {'width': 17}))
        self.assertEqual(scene.bounds[0][2], 0)
        self.assertEqual(scene.bounds[1][2], 17)
        self.assertAlmostEqual(scene.center[2], 8.5)
        start, count = scene.parts[0].side
        for i in range(start * 6, (start + count) * 6, 6):
            p = scene.vertices[i:i + 3]
            self.assertLessEqual(sum(((p[j] - scene.center[j]) ** 2 for j in range(3))), scene.radius ** 2 + 0.001)

    def test_screw_axis_is_x(self):
        p = Part('screw', [(2, 0), (0, 2), (-2, 0), (0, -2)], width=24, axis_x=True)
        self.assertEqual(point(p, (2, 0), 0, 0), (-12, 0, -2))
        self.assertEqual(point(p, (2, 0), 24, 0), (12, 0, -2))

    def test_double_is_one_continuous_closed_surface(self):
        design = generate('double', {'width': 12, 'gap': 2})
        scene = build_scene(design)
        self.assertEqual(len(scene.parts), 1)
        self.assertEqual(len(scene.parts[0].caps), 2)
        from geometry import profile_sections
        sections = profile_sections(design.parts[0])
        self.assertEqual(sections[0][0], 0)
        self.assertEqual(sections[-1][0], 12)
        groove = [(z, outline) for z, angle, outline in sections if outline is not design.parts[0].outer]
        self.assertEqual([z for z, outline in groove], [5, 7])
        self.assertTrue(all((min((hypot(x, y) for x, y in outline)) > 3 for z, outline in groove)))

    def test_finite_scene_for_every_family(self):
        for family in ('spur', 'helical', 'double', 'planetary', 'cycloidal', 'harmonic', 'worm'):
            with self.subTest(family=family):
                s = build_scene(generate(family))
                self.assertTrue(all((isfinite(v) for v in s.vertices)))
                for p in s.parts:
                    for cap in p.caps:
                        self.assertEqual(cap.plane[1], 6)
if __name__ == '__main__':
    unittest.main(verbosity=2)
