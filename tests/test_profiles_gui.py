# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Real OpenGL shader checks for the arc-length wave mapping.

Requires a desktop display. Transform feedback measures shader coordinates;
this is a numeric comparison, not a screenshot-only smoke test.
"""
import ctypes as C
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from math import hypot
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gio,GLib,Gdk
from geometry import generate
from preview3d import VERTEX,FRAGMENT,GL,IDENTITY,shader_source
from wave_geometry import map_point,unmap_point,arc_coefficients
from special_drives import ellipse_axes
from motion import wrapped_angle
from gl_loader import bind_function


Gtk.init_check()

@unittest.skipUnless(Gdk.Display.get_default(), 'A real display is required for GL transform feedback')
class ProfileShaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory(prefix='ratiolab-profile-gui-')
        root=Path(cls.temporary.name)
        cls.environment=patch.dict(os.environ,dict(XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'),APPDATA=str(root/'roaming'),LOCALAPPDATA=str(root/'local')));cls.environment.start()
        from app import ReducerApp
        cls.app=ReducerApp();cls.app.set_application_id(f'local.solidcraft.reducers.profiles.p{os.getpid()}');cls.app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        cls.app.register(None);cls.app.activate()
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            while GLib.MainContext.default().iteration(False):pass
            if cls.app.canvas.gl and not cls.app.pending:break
            time.sleep(.01)
        if not cls.app.canvas.gl:raise RuntimeError('OpenGL failed to initialize: '+str(cls.app.canvas.failure))

    @classmethod
    def tearDownClass(cls):
        for w in cls.app.get_windows():w.destroy()
        cls.environment.stop();cls.temporary.cleanup()

    def test_actual_gpu_wave_coordinates_match_cpu_at_zero_and_moving_phases(self):
        canvas=self.app.canvas;canvas.make_current();g=canvas.gl
        signatures=dict(TransformFeedbackVaryings=(None,[C.c_uint,C.c_int,C.POINTER(C.c_char_p),C.c_uint]),BindBufferBase=(None,[C.c_uint,C.c_uint,C.c_uint]),BeginTransformFeedback=(None,[C.c_uint]),EndTransformFeedback=(None,[]),MapBufferRange=(C.c_void_p,[C.c_uint,C.c_ssize_t,C.c_ssize_t,C.c_uint]),UnmapBuffer=(C.c_ubyte,[C.c_uint]))
        extra={name:bind_function(g.lib,name,*signature) for name,signature in signatures.items()}
        shader=g.shader(0x8B31,shader_source(VERTEX,canvas.use_es));fragment=g.shader(0x8B30,shader_source(FRAGMENT,canvas.use_es))
        program=g.CreateProgram();g.AttachShader(program,shader);g.AttachShader(program,fragment)
        varying=(C.c_char_p*1)(b'world');extra['TransformFeedbackVaryings'](program,1,varying,0x8C8C);g.LinkProgram(program)
        status=C.c_int();g.GetProgramiv(program,0x8B82,C.byref(status));self.assertEqual(status.value,1)
        vao=C.c_uint();buffers=(C.c_uint*2)();g.GenVertexArrays(1,C.byref(vao));g.GenBuffers(2,buffers)
        try:
            g.BindVertexArray(vao.value);g.BindBuffer(0x8892,buffers[0])
            for index,offset in [(0,0),(1,12),(2,24)]:g.EnableVertexAttribArray(index);g.VertexAttribPointer(index,3,0x1406,0,36,C.c_void_p(offset))
            g.UseProgram(program)
            uniform=lambda name:g.GetUniformLocation(program,name.encode())
            g.UniformMatrix4fv(uniform('model'),1,0,(C.c_float*16)(*IDENTITY));g.Uniform4f(uniform('ropeShape'),0,0,0,0)
            for teeth,factor in [(30,1.5),(60,1),(160,.5)]:
                d=generate('harmonic');rp=teeth;a,b=ellipse_axes(rp,2*factor)
                coefficients=arc_coefficients(a,b,rp);g.Uniform4f(uniform('arcFirst'),*coefficients[:4]);g.Uniform4f(uniform('arcSecond'),*coefficients[4:])
                g.Uniform4f(uniform('flexBody'),rp,d.values['cup_length'],d.values['diaphragm'],1)
                for weight in (0,.3,1):
                    for u in (.1,1.2,3.8):
                        p=map_point(u,-3,weight,a,b,rp);material=unmap_point(*p,weight,a,b,rp)
                        raw=(C.c_float*9)(p[0],p[1],0,0,0,1,*material);g.BindBuffer(0x8892,buffers[0]);g.BufferData(0x8892,C.sizeof(raw),raw,0x88E8)
                        for flex,wave in [(0,0),(.4,1.5),(-1,3),(1e9+.4,-1e10+1.5)]:
                            flex,wave=wrapped_angle(flex),wrapped_angle(wave)
                            g.Uniform4f(uniform('flexShape'),flex,wave,a,b)
                            g.BindBuffer(0x8C8E,buffers[1]);g.BufferData(0x8C8E,12,None,0x88E8);extra['BindBufferBase'](0x8C8E,0,buffers[1])
                            g.Enable(0x8C89);extra['BeginTransformFeedback'](0);g.DrawArrays(0,0,1);extra['EndTransformFeedback']();g.Disable(0x8C89)
                            result=(C.c_float*3)();mapped=extra['MapBufferRange'](0x8C8E,0,12,1)
                            self.assertTrue(mapped,'Transform feedback buffer could not be read')
                            C.memmove(result,mapped,12);self.assertTrue(extra['UnmapBuffer'](0x8C8E))
                            expected=map_point(u,-3,weight,a,b,rp,flex,wave)
                            self.assertLess(hypot(result[0]-expected[0],result[1]-expected[1]),.00015,(teeth,weight,u,flex,wave,list(result),expected))
            self.assertEqual(g.GetError(),0)
        finally:
            g.Disable(0x8C89);g.BindVertexArray(0);g.DeleteBuffers(2,buffers);g.DeleteVertexArrays(1,C.byref(vao));g.DeleteShader(shader);g.DeleteShader(fragment);g.DeleteProgram(program);g.UseProgram(0)
        canvas.dirty=True;canvas.queue_render()

if __name__=='__main__':unittest.main(verbosity=2)
