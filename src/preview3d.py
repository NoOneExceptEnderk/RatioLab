# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""OpenGL viewport through GTK: depth buffer and even/odd stencil section caps.
Profiles and twist use the shared geometry sent to CAD; no pip GL dependency.
"""
import ctypes as C
import sys
from array import array
from dataclasses import dataclass
from math import sin,cos,radians,ceil,sqrt,pi
from app_paths import prepare_native_runtime
prepare_native_runtime()
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk, Gdk, GLib, GObject
from motion import build_plan,IDENTITY,wrapped_angle
from gl_loader import load_epoxy, bind_function




from solid_geometry import point,section_loops,PALETTE
from component_geometry import displayed_part


def normal(a,b,c):
    u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
    n=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]);size=sqrt(sum(x*x for x in n)) or 1
    return tuple(x/size for x in n)


def vertex(data,p,n):data.extend((*p,*n))
def triangle(data,a,b,c,n=None):
    if a==b or b==c or a==c:return
    n=n or normal(a,b,c)
    for p in (a,b,c):vertex(data,p,n)

@dataclass
class Cap:
    fan: tuple
    plane: tuple

@dataclass
class MeshPart:
    side: tuple
    edges: tuple
    caps: list
    color: tuple
    source_index: int = 0

@dataclass
class Scene:
    vertices: array
    parts: list
    grid: tuple
    center: tuple
    radius: float
    bounds: tuple
    materials: array


def build_scene(design,show_support=False,show_housing=False,exploded=False):
    from dataclasses import replace
    from geometry import profile_sections,section_holes
    data=array('f');parts=[];allpoints=[]
    mid=sum(p.z+p.width/2 for p in design.parts)/len(design.parts)
    for index,source in enumerate(design.parts):
        if source.role=='support' and not show_support:continue
        if source.role=='housing' and not show_housing:continue
        p=displayed_part(design,index,exploded)
        if p.mesh:
            from solid_geometry import faces
            begin=len(data)//6
            for face in faces(p):
                for loop in face:
                    allpoints.extend(loop)
                    for j in range(1,len(loop)-1):triangle(data,loop[0],loop[j],loop[j+1])
            color=PALETTE[index%len(PALETTE)] if p.color==(.35,.72,.9) else p.color
            parts.append(MeshPart((begin,len(data)//6-begin),(len(data)//6,0),[],color,index))
            continue
        sections=profile_sections(p)
    # Corresponding section vertices keep the preview on the shared faceted surface.
        def loops_at(outer,z):return section_loops(p,outer,z)
        begin=len(data)//6;first_z,first_a,first_outer=sections[0]
        prev=[[point(p,q,first_z,radians(first_a)) for q in loop] for loop in loops_at(first_outer,first_z)]
        for loop in prev:allpoints.extend(loop)
        for z,angle,outer in sections[1:]:
            current=[[point(p,q,z,radians(angle)) for q in loop] for loop in loops_at(outer,z)]
            for lower,upper in zip(prev,current):
                for j in range(len(lower)):
                    k=(j+1)%len(lower);a,b,c,d=lower[j],lower[k],upper[k],upper[j]
                    if p.alternate_diagonal:triangle(data,a,b,d);triangle(data,b,c,d)
                    else:triangle(data,a,b,c);triangle(data,a,c,d)
                allpoints.extend(upper)
            prev=current
        side=(begin,len(data)//6-begin);caps=[];edges=[]
        for (z,angle,outer),top in [(sections[0],False),(sections[-1],True)]:
            caploops=[[point(p,q,z,radians(angle)) for q in loop] for loop in loops_at(outer,z)]
            n=p.frame[3] if p.frame else ((1,0,0) if p.axis_x else (0,0,1))
            if not top:n=tuple(-x for x in n)
            begin=len(data)//6
            for loop in caploops:
                for j in range(1,len(loop)-1):triangle(data,loop[0],loop[j],loop[j+1],n)
            fan=(begin,len(data)//6-begin)
            a=radians(angle);c,s=cos(a),sin(a);rotated=[(x*c-y*s,x*s+y*c) for x,y in outer]
            xmin=min(x for x,y in rotated);xmax=max(x for x,y in rotated);ymin=min(y for x,y in rotated);ymax=max(y for x,y in rotated)
            corners=[point(p,q,z,0) for q in [(xmin,ymin),(xmax,ymin),(xmax,ymax),(xmin,ymax)]]
            begin=len(data)//6;triangle(data,*corners[:3],n);triangle(data,corners[0],corners[2],corners[3],n);caps.append(Cap(fan,(begin,6)))
            edges.extend(caploops)
        # Show groove edges on the continuous double helix without adding internal cap faces.
        if p.double and p.gap:
            for z,angle,outer in sections:
                if (not p.stations and outer is not p.outer) or (p.stations and min(abs(z-(p.width-p.gap)/2),abs(z-(p.width+p.gap)/2))<1e-7):edges.append([point(p,q,z,radians(angle)) for q in outer])
        begin=len(data)//6
        for loop in edges:
            for a,b in zip(loop,loop[1:]+loop[:1]):vertex(data,a,(0,0,1));vertex(data,b,(0,0,1))
        edge=(begin,len(data)//6-begin)
        color=PALETTE[index%len(PALETTE)] if p.color==(.35,.72,.9) else p.color
        parts.append(MeshPart(side,edge,caps,color,index))
    if not allpoints:
        from solid_geometry import faces
        allpoints=[q for part in design.parts for face in faces(part) for loop in face for q in loop]
        if not allpoints:raise ValueError('The model contains no components')
    mins=tuple(min(p[i] for p in allpoints) for i in range(3));maxs=tuple(max(p[i] for p in allpoints) for i in range(3))
    center=tuple((a+b)/2 for a,b in zip(mins,maxs));radius=max(sqrt(sum((p[i]-center[i])**2 for i in range(3))) for p in allpoints)
    begin=len(data)//6
    span=max(maxs[0]-mins[0],maxs[1]-mins[1],10);step=10**int(__import__('math').floor(__import__('math').log10(span/8)))
    if span/step>16:step*=2
    extent=ceil(span*.7/step)*step;ground=mins[2]-max(.5,span*.025);cx,cy=center[:2]
    for j in range(-int(extent/step),int(extent/step)+1):
        off=j*step
        for a,b in [((cx+off,cy-extent,ground),(cx+off,cy+extent,ground)),((cx-extent,cy+off,ground),(cx+extent,cy+off,ground))]:vertex(data,a,(0,0,1));vertex(data,b,(0,0,1))
    materials=array('f',[0.0])*(len(data)//2)
    if design.family=='harmonic' and not exploded and any(p.name.startswith('Flexspline') for p in design.parts):
        from wave_geometry import unmap_point
        rp=design.values['module']*design.values['teeth']/2
        from special_drives import ellipse_axes
        a,b=design.analysis.get('pitch_ellipse_semiaxes_mm',ellipse_axes(rp,design.values['module']*design.values['wave_factor']))
        length=design.values['cup_length'];diaphragm=design.values['diaphragm'];cache={}
        for part in parts:
            source=design.parts[part.source_index]
            if not source.name.startswith('Flexspline'):continue
            for station in source.stations:
                references=[station.get('material_outer',[])]+station.get('material_holes',[])
                for loop,reference in zip([station['outer']]+station['holes'],references):
                    for xy,material in zip(loop,reference):
                        xyz=tuple(array('f',point(source,xy,station['z'],0)))
                        cache[xyz]=material
            for i in range(part.side[0],part.edges[0]+part.edges[1]):
                xyz=tuple(data[6*i:6*i+3])
                if xyz not in cache:
                    x,y,z=xyz;weight=max(0,min(1,(z+length-diaphragm)/(length-diaphragm)))
                    cache[xyz]=unmap_point(x,y,weight,a,b,rp)
                materials[3*i:3*i+3]=array('f',cache[xyz])
    return Scene(data,parts,(begin,len(data)//6-begin),center,max(radius,1),(mins,maxs),materials)


class GL:
    """Small, explicitly typed OpenGL ABI; use the current Gtk.GLArea context."""
    def __init__(self):
        self.lib=load_epoxy()
        u=C.c_uint;i=C.c_int;f=C.c_float;p=C.c_void_p
        signatures={
            'CreateShader':(u,[u]),'ShaderSource':(None,[u,i,C.POINTER(C.c_char_p),C.POINTER(i)]),'CompileShader':(None,[u]),
            'GetShaderiv':(None,[u,u,C.POINTER(i)]),'GetShaderInfoLog':(None,[u,i,C.POINTER(i),p]),'DeleteShader':(None,[u]),
            'CreateProgram':(u,[]),'AttachShader':(None,[u,u]),'LinkProgram':(None,[u]),'GetProgramiv':(None,[u,u,C.POINTER(i)]),
            'GetProgramInfoLog':(None,[u,i,C.POINTER(i),p]),'DeleteProgram':(None,[u]),'UseProgram':(None,[u]),
            'GetUniformLocation':(i,[u,C.c_char_p]),'Uniform4f':(None,[i,f,f,f,f]),'UniformMatrix4fv':(None,[i,i,C.c_ubyte,C.POINTER(f)]),'Uniform1f':(None,[i,f]),'Uniform2f':(None,[i,f,f]),'Uniform3f':(None,[i,f,f,f]),
            'GenVertexArrays':(None,[i,C.POINTER(u)]),'BindVertexArray':(None,[u]),'DeleteVertexArrays':(None,[i,C.POINTER(u)]),
            'GenBuffers':(None,[i,C.POINTER(u)]),'BindBuffer':(None,[u,u]),'BufferData':(None,[u,C.c_ssize_t,p,u]),'DeleteBuffers':(None,[i,C.POINTER(u)]),
            'EnableVertexAttribArray':(None,[u]),'VertexAttribPointer':(None,[u,i,u,C.c_ubyte,i,p]),
            'Viewport':(None,[i,i,i,i]),'Enable':(None,[u]),'Disable':(None,[u]),'ClearColor':(None,[f,f,f,f]),'Clear':(None,[u]),
            'DepthFunc':(None,[u]),'DepthMask':(None,[C.c_ubyte]),'ColorMask':(None,[C.c_ubyte]*4),'StencilMask':(None,[u]),
            'StencilFunc':(None,[u,i,u]),'StencilOp':(None,[u,u,u]),'DrawArrays':(None,[u,i,i]),'PolygonOffset':(None,[f,f]),
            'ReadPixels':(None,[i,i,i,i,u,u,p]),'GetError':(u,[]),
        }
        for name,(restype,args) in signatures.items():
            setattr(self,name,bind_function(self.lib,name,restype,args))
    def shader(self,kind,source):
        shader=self.CreateShader(kind);string=C.c_char_p(source.encode());self.ShaderSource(shader,1,C.byref(string),None);self.CompileShader(shader)
        status=C.c_int();self.GetShaderiv(shader,0x8B81,C.byref(status))
        if not status.value:
            log=C.create_string_buffer(4096);self.GetShaderInfoLog(shader,4096,None,log);raise RuntimeError(log.value.decode())
        return shader

VERTEX='''#version 330 core
layout(location=0) in vec3 position;
layout(location=1) in vec3 normal;
layout(location=2) in vec3 material;
uniform vec3 center;
uniform vec2 orbit;
uniform vec3 projection;
uniform float edge;
uniform mat4 model;
uniform vec4 flexShape; // flex material angle, wave angle, ellipse a,b
uniform vec4 flexBody;  // pitch radius, body length, diaphragm, enabled
uniform vec4 arcFirst;
uniform vec4 arcSecond;
uniform vec4 ropeShape; // mode, cx,cy,left-end y
uniform vec2 ropeEnds;  // right-end y, right-end x
uniform vec3 ropeLeft;
uniform vec3 ropeRight;
uniform vec3 ropeWheel;
out vec3 n;
out vec3 world;
vec3 rotate(vec3 p){float c=cos(orbit.x),s=sin(orbit.x),a=cos(orbit.y),b=sin(orbit.y);vec3 q=vec3(c*p.x-s*p.y,s*p.x+c*p.y,p.z);return vec3(q.x,a*q.y-b*q.z,b*q.y+a*q.z);}
// Explicit range reduction avoids implementation-dependent native trig
// precision on wave material coordinates (verified by transform feedback).
float waveSin(float angle){
 float x=mod(angle+3.141592653589793,6.283185307179586)-3.141592653589793;
 if(x>1.570796326794897)x=3.141592653589793-x;
 if(x< -1.570796326794897)x= -3.141592653589793-x;
 float q=x*x;
 return x*(1.0+q*(-0.166666666666667+q*(0.008333333333333+q*(-0.000198412698413+q*(0.000002755731922+q*(-0.000000025052108+q*0.000000000160590))))));
}
float waveCos(float angle){return waveSin(angle+1.570796326794897);}
float arcCoeff(int k){return k<4?arcFirst[k]:arcSecond[k-4];}
vec2 waveFrame(float u,float d,float w,float flex,float wave,out vec2 tangent){
 float angle=u+flex-wave,t=angle;
 for(int j=0;j<4;j++){
  float f=t-angle,der=1.0;
  for(int k=0;k<8;k++){float h=2.0*float(k+1);f+=arcCoeff(k)*waveSin(h*t);der+=h*arcCoeff(k)*waveCos(h*t);}
  t-=f/der;
 }
 float ct=waveCos(t),st=waveSin(t),cu=waveCos(u+flex),su=waveSin(u+flex);
 vec2 E=vec2(flexShape.z*ct,flexShape.w*st);
 vec2 N=normalize(vec2(ct/flexShape.z,st/flexShape.w));
 vec2 T=vec2(-flexShape.z*st,flexShape.w*ct);float speed=length(T);
 float curvature=flexShape.z*flexShape.w/(speed*speed*speed);
 T*=flexBody.x*(1.0+d*curvature)/speed;
 E+=d*N;float c=waveCos(wave),s=waveSin(wave);mat2 rotation=mat2(c,s,-s,c);E=rotation*E;
 tangent=normalize(mix((flexBody.x+d)*vec2(-su,cu),rotation*T,w));
 return mix((flexBody.x+d)*vec2(cu,su),E,w);
}
vec2 wavePoint(float u,float d,float w,float flex,float wave){vec2 tangent;return waveFrame(u,d,w,flex,wave,tangent);}
vec3 deform(vec3 p){
 if(flexBody.w>0.5)p.xy=wavePoint(material.x,material.y,material.z,flexShape.x,flexShape.y);
 if(ropeShape.x>0.5){
  bool left=p.x<ropeShape.y;
  bool arc=ropeShape.x<1.5 ? p.y>=ropeShape.z : ropeShape.x<2.5 ? p.y<=ropeShape.z : p.y>=ropeShape.z && p.x<=ropeShape.y;
  if(arc)p+=ropeWheel;
  else{
   bool horizontal=ropeShape.x>2.5 && !left;
   float endpoint=horizontal?ropeEnds.y:left?ropeShape.w:ropeEnds.x;
   float tangent=horizontal?ropeShape.y:ropeShape.z;
   float coordinate=horizontal?p.x:p.y;
   float t=clamp((coordinate-endpoint)/(tangent-endpoint),0.0,1.0);
   p+=mix(left?ropeLeft:ropeRight,ropeWheel,t);
  }
 }
 return p;
}
void main(){world=(model*vec4(deform(position),1.0)).xyz;vec3 p=rotate(world-center);gl_Position=vec4(p.x*projection.x,p.y*projection.y,-p.z*projection.z-edge*0.00005,1);vec3 nn=normal;if(flexBody.w>0.5){vec2 oldT,newT;waveFrame(material.x,material.y,material.z,0.0,0.0,oldT);waveFrame(material.x,material.y,material.z,flexShape.x,flexShape.y,newT);vec2 oldN=vec2(oldT.y,-oldT.x),newN=vec2(newT.y,-newT.x);nn.xy=dot(nn.xy,oldT)*newT+dot(nn.xy,oldN)*newN;}n=rotate(mat3(model)*nn);}
'''
FRAGMENT='''#version 330 core
in vec3 n;
in vec3 world;
uniform vec3 center;
uniform float section;
uniform vec3 color;
uniform float lit;
out vec4 frag;
void main(){if(section>0.5 && world.y>center.y)discard;vec3 norm=normalize(n);float light=0.48+0.52*max(dot(norm,normalize(vec3(-0.35,-0.25,1.0))),0.0);frag=vec4(color*mix(1.0,light,lit),1.0);}
'''


def shader_source(source, use_es=False):
    if use_es:
        return source.replace('#version 330 core', '#version 300 es\nprecision highp float;\nprecision highp int;', 1)
    return source


def context_uses_es(context):
    """Validate the realized context before choosing its GLSL dialect."""
    api=context.get_api()
    if api not in (Gdk.GLAPI.GL,Gdk.GLAPI.GLES):
        raise RuntimeError('The 3D preview requires an OpenGL or OpenGL ES context')
    use_es=api==Gdk.GLAPI.GLES
    if tuple(context.get_version()) < ((3,0) if use_es else (3,3)):
        raise RuntimeError('OpenGL ES 3.0 or desktop OpenGL 3.3 or newer is required')
    return use_es


def create_preview_context(surface, allowed_apis):
    """Try each supported API with its own minimum, without an OS assumption.

    GLArea has one required-version property for both APIs. Requesting 3.3
    there would also request nonexistent GLES 3.3 and exclude GLES 3.0 devices.
    Create separate candidates so a backend can reject desktop GL and still
    provide GLES (or the reverse), while retaining both renderer requirements.
    """
    errors=[]
    for api,version,name in ((Gdk.GLAPI.GL,(3,3),'OpenGL 3.3'),
                             (Gdk.GLAPI.GLES,(3,0),'OpenGL ES 3.0')):
        if not allowed_apis & api:continue
        try:
            context=surface.create_gl_context()
            context.set_allowed_apis(api)
            context.set_required_version(*version)
            context.realize()
            context_uses_es(context)
            return context
        except (GLib.Error,RuntimeError) as error:
            errors.append(f'{name}: {error}')
    message='Could not create the 3D preview context (OpenGL 3.3 / GLES 3.0): '+('; '.join(errors) or 'no API allowed')
    raise GLib.Error.new_literal(Gdk.gl_error_quark(),message,int(Gdk.GLError.NOT_AVAILABLE))


def framebuffer_argb32(pixels, width, height):
    """Convert bottom-up GL_RGBA bytes to Cairo's native-endian ARGB32."""
    raw=bytearray().join(pixels[row*width*4:(row+1)*width*4] for row in range(height-1,-1,-1))
    if sys.byteorder == 'little':
        raw[0::4],raw[2::4]=raw[2::4],raw[0::4]
    else:
        red,green,blue,alpha=raw[0::4],raw[1::4],raw[2::4],raw[3::4]
        raw[0::4],raw[1::4],raw[2::4],raw[3::4]=alpha,red,green,blue
    return raw


class Preview3D(Gtk.GLArea):
    __gsignals__ = {'view-changed': (GObject.SignalFlags.RUN_FIRST, None, (str,)), 'motion-state': (GObject.SignalFlags.RUN_FIRST, None, ()), 'inspection-state': (GObject.SignalFlags.RUN_FIRST, None, ()), 'component-click': (GObject.SignalFlags.RUN_FIRST, None, (float,float,bool)), 'display-state': (GObject.SignalFlags.RUN_FIRST, None, ())}
    def __init__(self, use_es=None):
        super().__init__()
        # An explicit API remains useful for diagnostics; normal startup lets
        # GTK negotiate either backend, including native Windows desktop GL.
        self.set_allowed_apis((Gdk.GLAPI.GL|Gdk.GLAPI.GLES) if use_es is None else
                              Gdk.GLAPI.GLES if use_es else Gdk.GLAPI.GL)
        self.set_required_version(3,0 if use_es else 3)
        self.use_es=None
        self.set_has_depth_buffer(True);self.set_has_stencil_buffer(True);self.set_auto_render(False)
        self.set_hexpand(True);self.set_vexpand(True);self.set_size_request(320,280)
        self.design=None;self.show_support=False;self.show_housing=False;self.exploded=False;self.section=False;self.scene=None;self.dirty=False;self.gl=None;self.failure=None;self.zoom=1.;self.yaw=radians(-35);self.tilt=radians(-55)
        self.inspection_phase=None;self.inspection_indices=();self.inspection_motion_plan=None
        self.selected_indices=();self.isolated_indices=None;self.drag_distance=0.;self.rendered_phase=0.
        self.motion_plan=None;self.motion_enabled=False;self.motion_playing=False;self.motion_speed=1.;self.motion_phase=0.;self.motion_tick=0;self.motion_last=None;self.motion_valid=True
        self.connect('realize',self.on_realize);self.connect('unrealize',self.on_unrealize);self.connect('render',self.on_render)
        drag=Gtk.GestureDrag.new();drag.set_button(1);drag.connect('drag-begin',self.drag_begin);drag.connect('drag-update',self.drag_update);self.add_controller(drag)
        scroll=Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL);scroll.connect('scroll',self.scroll);self.add_controller(scroll)
        self.set_tooltip_text('Drag to rotate · scroll to zoom · double click to fit')
        click=Gtk.GestureClick.new();click.set_button(1);click.connect('released',self.component_click);self.add_controller(click)
    def do_create_context(self):
        try:
            return create_preview_context(self.get_native().get_surface(),self.get_allowed_apis())
        except GLib.Error as error:
            self.set_error(error)
            return None
    def set_design(self,design):
        changed=design is not self.design
        speed_keys={'input_rpm','input_b_rpm','output_difference_rpm'}
        keep_phase=bool(design and self.design and design.family==self.design.family and {k:v for k,v in design.values.items() if k not in speed_keys}=={k:v for k,v in self.design.values.items() if k not in speed_keys})
        if self.design is not None and (not design or design.family!=self.design.family or design.values!=self.design.values):self.clear_inspection()
        self.design=design;self.scene=build_scene(design,self.show_support,self.show_housing,self.exploded) if design else None;self.dirty=True
        if changed:
            previous=self.motion_plan if keep_phase and design.family=='differential' else None
            self.motion_plan=build_plan(design,previous,self.motion_phase) if design else None
            if not keep_phase:self.motion_phase=0.;self.motion_last=None
            self.motion_valid=True
            if not self.motion_plan or not self.motion_plan.supported:self.set_motion_playing(False)
            self.emit('motion-state')
        self.queue_render()
    def show_inspection(self,phase,indices):
        self.set_motion_playing(False)
        if self.design and self.design.family=='differential' and self.inspection_motion_plan is None:
            self.inspection_motion_plan=self.motion_plan
            self.motion_plan=build_plan(self.design)
        self.inspection_phase=float(phase);self.inspection_indices=tuple(indices)
        self.queue_render();self.emit('motion-state');self.emit('inspection-state')
    def clear_inspection(self):
        changed=self.inspection_phase is not None
        self.inspection_phase=None;self.inspection_indices=()
        if self.inspection_motion_plan is not None:
            self.motion_plan=self.inspection_motion_plan;self.inspection_motion_plan=None
        self.queue_render()
        if changed:self.emit('inspection-state')
    def set_motion_playing(self,playing):
        if playing:self.clear_inspection()
        playing=bool(playing and self.motion_valid and self.motion_plan and self.motion_plan.supported and not self.exploded and not self.failure)
        self.motion_playing=playing
        if playing:
            self.motion_enabled=True;self.motion_last=None
            if not self.motion_tick:self.motion_tick=self.add_tick_callback(self.on_motion_tick)
        elif self.motion_tick:
            self.remove_tick_callback(self.motion_tick);self.motion_tick=0;self.motion_last=None
        self.queue_render();self.emit('motion-state')
    def on_motion_tick(self,widget,clock):
        if not self.motion_playing:self.motion_tick=0;return False
        now=clock.get_frame_time()/1000000
        if self.motion_last is not None:
            if self.design and 'input_rpm' in self.design.values:
                keys=('input_rpm','output_difference_rpm') if self.design.family=='differential' and self.design.values.get('configuration')=='classic' else ('input_rpm','input_b_rpm','secondary_rpm')
                rpm=self.motion_plan.reference_rpm if any(self.design.values.get(key,0) for key in keys) else 0
            else:rpm=12*self.motion_speed
            self.motion_phase+=max(0,now-self.motion_last)*2*pi/60*rpm
        self.motion_last=now;self.queue_render();return True
    def reset_motion(self):
        self.clear_inspection();self.set_motion_playing(False);self.motion_phase=0.;self.motion_enabled=False
        if self.design and self.design.family=='differential':self.motion_plan=build_plan(self.design)
        self.queue_render();self.emit('motion-state')
    def invalidate_motion(self):
        self.clear_inspection();self.motion_valid=False;self.set_motion_playing(False)
    def set_motion_speed(self,speed):
        self.motion_speed=max(0.,min(5.,float(speed)));self.emit('motion-state')
    def set_options(self,support,housing,exploded,section):
        if exploded or section:self.clear_inspection()
        if exploded:self.set_motion_playing(False)
        self.show_support=support;self.show_housing=housing;self.exploded=exploded;self.section=section;self.set_design(self.design);self.emit('display-state')
    def view(self,name):
        if name=='top':self.yaw=0;self.tilt=0
        elif name=='front':self.yaw=0;self.tilt=-pi/2
        else:self.yaw=radians(-35);self.tilt=radians(-55)
        self.zoom=1.;self.queue_render();self.emit('view-changed',name)
    def component_click(self,gesture,n,x,y):
        if self.drag_distance>4:return
        if n==2:self.view('iso');return
        from gi.repository import Gdk
        modifiers=gesture.get_current_event_state()
        self.emit('component-click',x,y,bool(modifiers & (Gdk.ModifierType.CONTROL_MASK|Gdk.ModifierType.SHIFT_MASK)))
    def drag_begin(self,g,x,y):self.drag_origin=(self.yaw,self.tilt);self.drag_distance=0.
    def drag_update(self,g,x,y):
        self.drag_distance=max(self.drag_distance,sqrt(x*x+y*y))
        if self.drag_distance<=4:return
        self.yaw=self.drag_origin[0]+x*.008;self.tilt=max(-pi,min(pi,self.drag_origin[1]+y*.008));self.queue_render();self.emit('view-changed','custom')
    def scroll(self,c,dx,dy):self.zoom=max(.25,min(8,self.zoom*1.12**(-dy)));self.queue_render();self.emit('view-changed','custom');return True
    def on_realize(self,*args):
        self.failure=None;self.use_es=None
        self.make_current()
        if self.get_error():self.failure=str(self.get_error());return
        try:
            self.use_es=context_uses_es(self.get_context())
            g=self.gl=GL()
            vs=g.shader(0x8B31,shader_source(VERTEX,self.use_es));fs=g.shader(0x8B30,shader_source(FRAGMENT,self.use_es))
            self.program=g.CreateProgram();g.AttachShader(self.program,vs);g.AttachShader(self.program,fs);g.LinkProgram(self.program)
            status=C.c_int();g.GetProgramiv(self.program,0x8B82,C.byref(status));g.DeleteShader(vs);g.DeleteShader(fs)
            if not status.value:raise RuntimeError('Could not initialize the 3D shader')
            self.locations={k:g.GetUniformLocation(self.program,k.encode()) for k in ['center','orbit','projection','color','lit','edge','section','model','flexShape','flexBody','arcFirst','arcSecond','ropeShape','ropeEnds','ropeLeft','ropeRight','ropeWheel']}
            self.vao=C.c_uint();self.vbo=C.c_uint();g.GenVertexArrays(1,C.byref(self.vao));g.GenBuffers(1,C.byref(self.vbo));g.BindVertexArray(self.vao.value);g.BindBuffer(0x8892,self.vbo.value)
            for index,offset in [(0,0),(1,12)]:g.EnableVertexAttribArray(index);g.VertexAttribPointer(index,3,0x1406,0,24,C.c_void_p(offset))
            self.material_vbo=C.c_uint();g.GenBuffers(1,C.byref(self.material_vbo));g.BindBuffer(0x8892,self.material_vbo.value);g.EnableVertexAttribArray(2);g.VertexAttribPointer(2,3,0x1406,0,12,C.c_void_p(0))
            self.dirty=True;self.queue_render()
        except Exception as e:self.failure=str(e);__import__('traceback').print_exc()
    def on_unrealize(self,*args):
        self.set_motion_playing(False)
        if self.gl and not self.get_error() and hasattr(self,'vbo'):
            self.make_current();self.gl.DeleteBuffers(1,C.byref(self.vbo));self.gl.DeleteBuffers(1,C.byref(self.material_vbo));self.gl.DeleteVertexArrays(1,C.byref(self.vao));self.gl.DeleteProgram(self.program)
        self.gl=None
    def save_png(self,path):
        if self.failure or self.get_error():raise RuntimeError('3D preview unavailable')
        self.capture_path=str(path);self.queue_render()
    def capture_png(self,callback):
        """Capture complete bytes on GTK's main thread; callback(data, error).

        GLArea.attach_buffers explicitly supports rendering outside its render
        signal. Capture synchronously so compositor throttling of an occluded
        window cannot leave an otherwise complete export waiting for a frame.
        """
        if self.failure or self.get_error() or not self.gl or not self.scene:
            raise RuntimeError('3D preview unavailable')
        if getattr(self,'capture_callback',None):
            raise RuntimeError('A preview capture is already pending')
        self.make_current()
        if self.get_error():raise RuntimeError('3D preview context unavailable')
        self.attach_buffers()
        self.capture_callback=callback
        try:self.on_render(self,None)
        except Exception:
            self.capture_callback=None
            raise
    def motion_uniforms(self,index):
        g=self.gl;loc=self.locations;phase=self.inspection_phase if self.inspection_phase is not None else self.motion_phase
        plan=self.motion_plan if (self.motion_enabled or self.inspection_phase is not None) and not self.exploded else None
        matrix=plan.matrix(index,phase) if plan and index is not None else IDENTITY
        g.UniformMatrix4fv(loc['model'],1,0,(C.c_float*16)(*matrix))
        flex=plan.deformation(index,phase) if plan and index is not None else None
        if flex:
            a,b,c,d,e,f,t=flex;a=wrapped_angle(a);b=wrapped_angle(b);g.Uniform4f(loc['flexShape'],a,b,c,d);g.Uniform4f(loc['flexBody'],e,f,t,1)
            coefficients=self.design.analysis['wave_mapping']['arc_coefficients'];g.Uniform4f(loc['arcFirst'],*coefficients[:4]);g.Uniform4f(loc['arcSecond'],*coefficients[4:])
        else:g.Uniform4f(loc['flexBody'],0,1,0,0)
        rope=plan.warp(index,phase) if plan and index is not None else None
        if rope:
            mode,cx,cy,ly,ry,rx,lx,ld,rdx,rdy,wx,wy=rope
            g.Uniform4f(loc['ropeShape'],mode,cx,cy,ly);g.Uniform2f(loc['ropeEnds'],ry,rx)
            g.Uniform3f(loc['ropeLeft'],lx,ld,0);g.Uniform3f(loc['ropeRight'],rdx,rdy,0);g.Uniform3f(loc['ropeWheel'],wx,wy,0)
        else:g.Uniform4f(loc['ropeShape'],0,0,0,0)
    def on_render(self,area,context):
        if not self.gl or self.failure:return True
        g=self.gl;ratio=self.get_scale_factor();w,h=self.get_width()*ratio,self.get_height()*ratio
        g.Viewport(0,0,w,h);g.ClearColor(.065,.085,.115,1);g.DepthMask(1);g.ColorMask(1,1,1,1);g.StencilMask(0xFF);g.Clear(0x4000|0x0100|0x0400)
        if not self.scene:return True
        s=self.scene;g.UseProgram(self.program);g.BindVertexArray(self.vao.value);g.BindBuffer(0x8892,self.vbo.value)
        if self.dirty:
            raw=s.vertices.tobytes();buf=C.create_string_buffer(raw);g.BufferData(0x8892,len(raw),buf,0x88E8)
            g.BindBuffer(0x8892,self.material_vbo.value);raw=s.materials.tobytes();buf=C.create_string_buffer(raw);g.BufferData(0x8892,len(raw),buf,0x88E8);g.BindBuffer(0x8892,self.vbo.value);self.dirty=False
        loc=self.locations
        g.Uniform1f(loc['section'],float(self.section))
        g.Uniform3f(loc['center'],*s.center);g.Uniform2f(loc['orbit'],self.yaw,self.tilt)
        scale=.86/s.radius*self.zoom;aspect=max(w,1)/max(h,1)
        g.Uniform3f(loc['projection'],scale/max(aspect,1),scale*min(aspect,1),1/(s.radius*4))
        self.motion_uniforms(None)
        g.Uniform1f(loc['edge'],0);g.Enable(0x0B71);g.DepthFunc(0x0203);g.Disable(0x0B90)
        g.Uniform1f(loc['lit'],0);g.Uniform3f(loc['color'],.12,.16,.205);g.DrawArrays(1,*s.grid)
        self.rendered_phase=self.inspection_phase if self.inspection_phase is not None else self.motion_phase
        for part in s.parts:
            if self.isolated_indices is not None and part.source_index not in self.isolated_indices:continue
            self.motion_uniforms(part.source_index)
            color=((1.,.42,.08) if part.source_index==self.inspection_indices[0] else (.95,.12,.65)) if part.source_index in self.inspection_indices else (.28,.32,.37) if self.inspection_phase is not None else (1.,.78,.18) if part.source_index in self.selected_indices else part.color
            g.Uniform1f(loc['lit'],1);g.Uniform3f(loc['color'],*color);g.Enable(0x8037);g.PolygonOffset(1,1);g.DrawArrays(4,*part.side)
            for cap in part.caps:
                g.StencilMask(1);g.Clear(0x0400);g.Enable(0x0B90);g.Disable(0x0B71);g.DepthMask(0);g.ColorMask(0,0,0,0)
                g.StencilFunc(0x0207,0,1);g.StencilOp(0x1E00,0x1E00,0x150A);g.DrawArrays(4,*cap.fan)
                g.ColorMask(1,1,1,1);g.DepthMask(1);g.Enable(0x0B71);g.StencilMask(0);g.StencilFunc(0x0202,1,1);g.StencilOp(0x1E00,0x1E00,0x1E00);g.DrawArrays(4,*cap.plane);g.Disable(0x0B90)
            g.Disable(0x8037);g.Uniform1f(loc['lit'],0);g.Uniform1f(loc['edge'],1);g.Uniform3f(loc['color'],*(x*.55 for x in color));g.DrawArrays(1,*part.edges);g.Uniform1f(loc['edge'],0)
        if getattr(self,'capture_path',None) or getattr(self,'capture_callback',None):
            callback=getattr(self,'capture_callback',None);self.capture_callback=None
            try:
                import cairo
                import io
                pixels=C.create_string_buffer(w*h*4);g.ReadPixels(0,0,w,h,0x1908,0x1401,pixels)
                if g.GetError():raise RuntimeError('OpenGL framebuffer capture failed')
                raw=framebuffer_argb32(pixels.raw,w,h)
                surface=cairo.ImageSurface.create_for_data(raw,cairo.FORMAT_ARGB32,w,h,w*4)
                if getattr(self,'capture_path',None):
                    surface.write_to_png(self.capture_path);self.capture_path=None
                if callback:
                    encoded=io.BytesIO();surface.write_to_png(encoded);callback(encoded.getvalue(),None)
            except Exception as error:
                if callback:callback(None,error)
                else:raise
        g.StencilMask(0xFF);g.BindVertexArray(0);g.UseProgram(0)
        return True
