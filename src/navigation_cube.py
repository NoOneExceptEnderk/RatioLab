# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Compact interactive orientation cube for the native workspace."""
from math import pi
from gi.repository import Gtk, Gdk
from view_navigation import FACES, cube_patches, hit_cube


class NavigationCube(Gtk.DrawingArea):
    def __init__(self, canvas):
        super().__init__(width_request=116,height_request=116,focusable=True)
        self.set_halign(Gtk.Align.CENTER)
        self.canvas=canvas;self.hover=None;self.distance=0
        self.set_cursor_from_name('grab')
        self.set_tooltip_text('Click a face, edge or corner to orient · drag to orbit\n1 Front · 2 Back · 3 Right · 4 Left · 5 Top · 6 Bottom · Home to fit')
        self.update_property([Gtk.AccessibleProperty.LABEL],['3D orientation cube. Click faces, edges or corners; drag to orbit. Keys 1–6 select faces; Home fits.'])
        self.set_draw_func(self.draw)
        motion=Gtk.EventControllerMotion.new();motion.connect('motion',self.motion);motion.connect('leave',self.leave);self.add_controller(motion)
        drag=Gtk.GestureDrag.new();drag.set_button(1);drag.connect('drag-begin',self.begin);drag.connect('drag-update',self.drag);drag.connect('drag-end',self.end);self.add_controller(drag)
        keys=Gtk.EventControllerKey.new();keys.connect('key-pressed',self.key);self.add_controller(keys)
        canvas.connect('view-changed',lambda *_:self.queue_draw())
    def patches(self):return cube_patches(self.canvas.yaw,self.canvas.tilt,self.get_width())
    def motion(self,controller,x,y):
        self.hover=hit_cube(self.patches(),x,y);self.queue_draw()
    def leave(self,*_):self.hover=None;self.queue_draw()
    def begin(self,gesture,x,y):
        self.grab_focus();self.start=(x,y);self.orbit=(self.canvas.yaw,self.canvas.tilt);self.distance=0
        self.set_cursor_from_name('grabbing')
    def drag(self,gesture,x,y):
        self.distance=max(self.distance,(x*x+y*y)**.5)
        if self.distance<4:return
        speed=.008*getattr(self.canvas,'rotation_speed',1)
        self.canvas.yaw=self.orbit[0]+x*speed;self.canvas.tilt=max(-pi,min(pi,self.orbit[1]+y*speed))
        self.canvas.queue_render();self.canvas.emit('view-changed','custom')
    def end(self,gesture,x,y):
        if self.distance<4:
            direction=hit_cube(self.patches(),*self.start)
            if direction:self.canvas.orient(direction)
        self.set_cursor_from_name('grab')
    def key(self,controller,keyval,keycode,state):
        key=Gdk.keyval_name(keyval)
        shortcuts=getattr(self.canvas,'keyboard_shortcuts',None)
        if shortcuts is not None:
            if shortcuts.view_key(keyval,state):return True
        else:
            directions=[FACES[i][1] for i in (3,2,0,1,4,5)]
            if key and len(key)==1 and key in '123456':self.canvas.orient(directions[int(key)-1]);return True
            if key=='Home':self.canvas.view('iso');return True
        if key in ('Left','Right','Up','Down'):
            self.canvas.yaw+=.12*((key=='Right')-(key=='Left'))
            self.canvas.tilt=max(-pi,min(pi,self.canvas.tilt+.12*((key=='Down')-(key=='Up'))))
            self.canvas.queue_render();self.canvas.emit('view-changed','custom');return True
        return False
    def draw(self,widget,cr,width,height):
        light=self.canvas.theme=='light'
        for name,polygon,direction,central,shade in self.patches():
            cr.move_to(*polygon[0])
            for p in polygon[1:]:cr.line_to(*p)
            cr.close_path()
            if direction==self.hover:cr.set_source_rgb(*((.80,.66,.54) if light else (.29,.53,.55)))
            else:
                value=(.72+.19*shade) if light else (.15+.10*shade)
                cr.set_source_rgb(value,value+.025,value+.045)
            cr.fill_preserve()
            cr.set_source_rgba(*((.40,.49,.54) if light else (.46,.58,.63)),.32)
            cr.set_line_width(.65);cr.stroke()
            if central:
                cr.set_source_rgb(*self.canvas.palette['axes'])
                cr.set_font_size(9)
                text=name.upper();ex=cr.text_extents(text)
                x=sum(p[0] for p in polygon)/4;y=sum(p[1] for p in polygon)/4
                cr.move_to(x-ex.width/2-ex.x_bearing,y-ex.height/2-ex.y_bearing);cr.show_text(text)
