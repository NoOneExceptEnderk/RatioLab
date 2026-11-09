# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Native remapping keeps exact document data and supports hidden preview export."""
from copy import deepcopy
import io
import unittest
import cairo

import test_component_labels as fixture
from geometry import generate


class WindowRemapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.ComponentLabelGuiTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        fixture.ComponentLabelGuiTests.tearDownClass.__func__(cls)

    def setUp(self):
        a=self.app
        if a.tools.expanded:a.tools.restore_workspace()
        a.canvas.set_motion_playing(False)
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='helical',
            parameters=generate('helical',dict(module=2,_decimal_inputs={'module':'2.00000000000000000001'})).values,
            quality=dict(preview_mm=.1,export_mm=.005)))
        self.assertTrue(fixture.wait_until(lambda:a.canvas.gl is not None and a.canvas.get_mapped(),seconds=8))

    def capture(self):
        c=self.app.canvas;before=c.render_serial;result=[]
        c.capture_png(lambda data,error:result.append((data,error)))
        self.assertTrue(fixture.wait_until(lambda:bool(result),seconds=8))
        self.assert_capture(result[0],before)
        return result[0][0]

    def assert_capture(self,result,before):
        c=self.app.canvas;data,error=result;self.assertIsNone(error)
        self.assertIsNone(c.failure);self.assertIsNone(c.get_error())
        self.assertGreater(c.render_serial,before)
        image=cairo.ImageSurface.create_from_png(io.BytesIO(data))
        self.assertEqual((image.get_width(),image.get_height()),
                         (c.get_width()*c.get_scale_factor(),c.get_height()*c.get_scale_factor()))
        pixels=bytes(image.get_data())
        self.assertTrue(any(pixels[i:i+4]!=pixels[:4] for i in range(4,len(pixels),4)))
        self.assertEqual(c.gl.GetError(),0)

    def test_toplevel_remap_keeps_exact_document_scene_view_and_pose(self):
        a=self.app;c=a.canvas
        a.inputs['module'].set_text('02.00000000000000000001');self.assertTrue(a.refresh())
        c.motion_phase=.123;c.pan_offset=(1.,2.,0.);c.zoom=1.2
        values=deepcopy(a.design.values);quality=deepcopy(a.quality);token=a.document.token
        raw=a.inputs['module'].get_text();scene=c.scene;design=a.design
        view=(c.yaw,c.tilt,c.pan_offset,c.zoom,c.motion_phase)
        for scale,size in ((0,(1200,700)),(2,(1280,736)),(0,(1100,680))):
            with self.subTest(scale=scale,size=size):
                a.text_size.set_selected(scale);fixture.pump(.05)
                a.win.set_visible(False)
                self.assertFalse(c.get_mapped())
                if a.win.get_display().__gtype__.name=='GdkWaylandDisplay':
                    self.assertFalse(c.get_realized());self.assertIsNone(c.gl)
                a.win.set_default_size(*size);a.win.present()
                self.assertTrue(fixture.wait_until(lambda:c.get_mapped() and c.gl is not None,seconds=8))
                self.capture()
                self.assertIs(a.design,design);self.assertIs(c.scene,scene)
                self.assertEqual(a.design.values,values);self.assertEqual(a.quality,quality)
                self.assertEqual(a.document.token,token);self.assertEqual(a.inputs['module'].get_text(),raw)
                self.assertEqual((c.yaw,c.tilt,c.pan_offset,c.zoom,c.motion_phase),view)
                self.assertTrue(a.export_menu.get_sensitive())

    def test_expanded_tools_keep_context_and_pending_capture_recovers(self):
        a=self.app;c=a.canvas
        a.components.open();fixture.pump(.1)
        scene=c.scene;design=a.design;gl=c.gl;token=a.document.token
        a.tools.expand()
        self.assertTrue(fixture.wait_until(lambda:not c.get_mapped()))
        self.assertTrue(a.win.get_visible());self.assertIs(c.gl,gl)
        # A hidden GLArea may have no allocation. Its documented capture
        # contract then defers reading until the next allocated native frame.
        # Keep the context and deliver that request when the preview returns.
        before=c.render_serial;result=[]
        c.capture_png(lambda data,error:result.append((data,error)))
        a.tools.restore_workspace()
        self.assertTrue(fixture.wait_until(c.get_mapped,seconds=8))
        self.assertTrue(fixture.wait_until(lambda:bool(result),seconds=8))
        self.assert_capture(result[0],before)
        self.capture()
        self.assertIs(a.design,design);self.assertIs(c.scene,scene)
        self.assertEqual(a.document.token,token)

    def test_toplevel_remap_also_releases_an_already_hidden_preview(self):
        a=self.app;c=a.canvas
        a.components.open();fixture.pump(.05);a.tools.expand()
        self.assertTrue(fixture.wait_until(lambda:not c.get_mapped()))
        scene=c.scene;design=a.design;token=a.document.token
        a.win.set_visible(False)
        if a.win.get_display().__gtype__.name=='GdkWaylandDisplay':
            self.assertFalse(c.get_realized());self.assertIsNone(c.gl)
        a.win.present()
        self.assertTrue(fixture.wait_until(a.win.get_mapped,seconds=8))
        self.assertTrue(a.tools.expanded)
        a.tools.restore_workspace()
        self.assertTrue(fixture.wait_until(lambda:c.get_mapped() and c.gl is not None,seconds=8))
        self.capture()
        self.assertIs(a.design,design);self.assertIs(c.scene,scene)
        self.assertEqual(a.document.token,token)


if __name__=='__main__':unittest.main()
