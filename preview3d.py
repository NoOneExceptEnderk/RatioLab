"""Viewport OpenGL 3.3 via GTK: depth buffer e cap con stencil pari/dispari.
Nessuna dipendenza pip; profili e twist provengono dalla stessa geometria inviata al CAD.
"""
import ctypes as C
from array import array
from dataclasses import dataclass
from math import sin,cos,radians,ceil,sqrt,pi
from app_paths import prepare_native_runtime
prepare_native_runtime()
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk, GObject
from motion import build_plan,IDENTITY
from gl_loader import load_epoxy, bind_function




from solid_geometry import point,section_loops,PALETTE


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


def build_scene(design,show_support=False,show_housing=False,exploded=False):
    from dataclasses import replace
    from geometry import profile_sections,section_holes
    data=array('f');parts=[];allpoints=[]
    mid=sum(p.z+p.width/2 for p in design.parts)/len(design.parts)
    for index,source in enumerate(design.parts):
        if source.role=='support' and not show_support:continue
        if source.role=='housing' and not show_housing:continue
        p=source
        if exploded:
            offset=(p.z+p.width/2-mid)*1.1
            if p.role!='gear':offset+=(8 if p.z+p.width/2>=mid else -8)
            p=replace(p,z=p.z+offset,center=tuple(v*1.12 for v in p.center))
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
        # Every loft section carries corresponding vertices. Circular holes remain exact in CAD.
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
    return Scene(data,parts,(begin,len(data)//6-begin),center,max(radius,1),(mins,maxs))


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
uniform vec3 center;
uniform vec2 orbit;
uniform vec3 projection;
uniform float edge;
uniform mat4 model;
uniform vec4 flexShape; // flex material angle, wave angle, ellipse a,b
uniform vec4 flexBody;  // pitch radius, body length, diaphragm, enabled
uniform vec4 ropeShape; // mode, cx,cy,left-end y
uniform vec2 ropeEnds;  // right-end y, right-end x
uniform vec3 ropeLeft;
uniform vec3 ropeRight;
uniform vec3 ropeWheel;
out vec3 n;
out vec3 world;
vec3 rotate(vec3 p){float c=cos(orbit.x),s=sin(orbit.x),a=cos(orbit.y),b=sin(orbit.y);vec3 q=vec3(c*p.x-s*p.y,s*p.x+c*p.y,p.z);return vec3(q.x,a*q.y-b*q.z,b*q.y+a*q.z);}
float rho(float a){return flexShape.z*flexShape.w/length(vec2(flexShape.w*cos(a),flexShape.z*sin(a)));}
vec3 deform(vec3 p){
 if(flexBody.w>0.5){
  float theta=atan(p.y,p.x),r=length(p.xy),weight=clamp((p.z+flexBody.y-flexBody.z)/(flexBody.y-flexBody.z),0.0,1.0);
  float rest=r-weight*(rho(theta)-flexBody.x),angle=theta+flexShape.x;
  r=rest+weight*(rho(angle-flexShape.y)-flexBody.x);p.xy=r*vec2(cos(angle),sin(angle));
 }
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
void main(){world=(model*vec4(deform(position),1.0)).xyz;vec3 p=rotate(world-center);gl_Position=vec4(p.x*projection.x,p.y*projection.y,-p.z*projection.z-edge*0.00005,1);vec3 nn=normal;if(flexBody.w>0.5){float c=cos(flexShape.x),s=sin(flexShape.x);nn.xy=mat2(c,s,-s,c)*nn.xy;}n=rotate(mat3(model)*nn);}
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


class Preview3D(Gtk.GLArea):
    __gsignals__ = {'view-changed': (GObject.SignalFlags.RUN_FIRST, None, (str,)), 'motion-state': (GObject.SignalFlags.RUN_FIRST, None, ())}
    def __init__(self):
        super().__init__();self.set_required_version(3,3);self.set_use_es(False)
        self.set_has_depth_buffer(True);self.set_has_stencil_buffer(True);self.set_auto_render(False)
        self.set_hexpand(True);self.set_vexpand(True);self.set_size_request(320,280)
        self.design=None;self.show_support=False;self.show_housing=False;self.exploded=False;self.section=False;self.scene=None;self.dirty=False;self.gl=None;self.failure=None;self.zoom=1.;self.yaw=radians(-35);self.tilt=radians(-55)
        self.motion_plan=None;self.motion_enabled=False;self.motion_playing=False;self.motion_speed=1.;self.motion_phase=0.;self.motion_tick=0;self.motion_last=None;self.motion_valid=True
        self.connect('realize',self.on_realize);self.connect('unrealize',self.on_unrealize);self.connect('render',self.on_render)
        drag=Gtk.GestureDrag.new();drag.set_button(1);drag.connect('drag-begin',self.drag_begin);drag.connect('drag-update',self.drag_update);self.add_controller(drag)
        scroll=Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL);scroll.connect('scroll',self.scroll);self.add_controller(scroll)
        self.set_tooltip_text('Drag to rotate · scroll to zoom · double click to fit')
        click=Gtk.GestureClick.new();click.connect('pressed',lambda _,n,x,y:self.view('iso') if n==2 else None);self.add_controller(click)
    def set_design(self,design):
        changed=design is not self.design
        keep_phase=bool(design and self.design and design.family==self.design.family and {k:v for k,v in design.values.items() if k!='input_rpm'}=={k:v for k,v in self.design.values.items() if k!='input_rpm'})
        self.design=design;self.scene=build_scene(design,self.show_support,self.show_housing,self.exploded) if design else None;self.dirty=True
        if changed:
            self.motion_plan=build_plan(design) if design else None
            if not keep_phase:self.motion_phase=0.;self.motion_last=None
            self.motion_valid=True
            if not self.motion_plan or not self.motion_plan.supported:self.set_motion_playing(False)
            self.emit('motion-state')
        self.queue_render()
    def set_motion_playing(self,playing):
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
        if self.motion_last is not None:self.motion_phase+=max(0,now-self.motion_last)*2*pi/60*((self.motion_plan.reference_rpm if self.design.values.get('input_rpm',0) or self.design.values.get('secondary_rpm',0) else 0) if self.design and 'input_rpm' in self.design.values else 12*self.motion_speed)
        self.motion_last=now;self.queue_render();return True
    def reset_motion(self):
        self.set_motion_playing(False);self.motion_phase=0.;self.motion_enabled=False;self.queue_render();self.emit('motion-state')
    def invalidate_motion(self):
        self.motion_valid=False;self.set_motion_playing(False)
    def set_motion_speed(self,speed):
        self.motion_speed=max(0.,min(5.,float(speed)));self.emit('motion-state')
    def set_options(self,support,housing,exploded,section):
        if exploded:self.set_motion_playing(False)
        self.show_support=support;self.show_housing=housing;self.exploded=exploded;self.section=section;self.set_design(self.design)
    def view(self,name):
        if name=='top':self.yaw=0;self.tilt=0
        elif name=='front':self.yaw=0;self.tilt=-pi/2
        else:self.yaw=radians(-35);self.tilt=radians(-55)
        self.zoom=1.;self.queue_render();self.emit('view-changed',name)
    def drag_begin(self,g,x,y):self.drag_origin=(self.yaw,self.tilt)
    def drag_update(self,g,x,y):
        self.yaw=self.drag_origin[0]+x*.008;self.tilt=max(-pi,min(pi,self.drag_origin[1]+y*.008));self.queue_render();self.emit('view-changed','custom')
    def scroll(self,c,dx,dy):self.zoom=max(.25,min(8,self.zoom*1.12**(-dy)));self.queue_render();return True
    def on_realize(self,*args):
        self.make_current()
        if self.get_error():self.failure=str(self.get_error());return
        try:
            g=self.gl=GL();vs=g.shader(0x8B31,VERTEX);fs=g.shader(0x8B30,FRAGMENT)
            self.program=g.CreateProgram();g.AttachShader(self.program,vs);g.AttachShader(self.program,fs);g.LinkProgram(self.program)
            status=C.c_int();g.GetProgramiv(self.program,0x8B82,C.byref(status));g.DeleteShader(vs);g.DeleteShader(fs)
            if not status.value:raise RuntimeError('Could not initialize the 3D shader')
            self.locations={k:g.GetUniformLocation(self.program,k.encode()) for k in ['center','orbit','projection','color','lit','edge','section','model','flexShape','flexBody','ropeShape','ropeEnds','ropeLeft','ropeRight','ropeWheel']}
            self.vao=C.c_uint();self.vbo=C.c_uint();g.GenVertexArrays(1,C.byref(self.vao));g.GenBuffers(1,C.byref(self.vbo));g.BindVertexArray(self.vao.value);g.BindBuffer(0x8892,self.vbo.value)
            for index,offset in [(0,0),(1,12)]:g.EnableVertexAttribArray(index);g.VertexAttribPointer(index,3,0x1406,0,24,C.c_void_p(offset))
            self.dirty=True;self.queue_render()
        except Exception as e:self.failure=str(e);__import__('traceback').print_exc()
    def on_unrealize(self,*args):
        self.set_motion_playing(False)
        if self.gl and not self.get_error() and hasattr(self,'vbo'):
            self.make_current();self.gl.DeleteBuffers(1,C.byref(self.vbo));self.gl.DeleteVertexArrays(1,C.byref(self.vao));self.gl.DeleteProgram(self.program)
        self.gl=None
    def save_png(self,path):
        if self.failure or self.get_error():raise RuntimeError('3D preview unavailable')
        self.capture_path=str(path);self.queue_render()
    def motion_uniforms(self,index):
        g=self.gl;loc=self.locations;plan=self.motion_plan if self.motion_enabled and not self.exploded else None
        matrix=plan.matrix(index,self.motion_phase) if plan and index is not None else IDENTITY
        g.UniformMatrix4fv(loc['model'],1,0,(C.c_float*16)(*matrix))
        flex=plan.deformation(index,self.motion_phase) if plan and index is not None else None
        if flex:
            a,b,c,d,e,f,t=flex;g.Uniform4f(loc['flexShape'],a,b,c,d);g.Uniform4f(loc['flexBody'],e,f,t,1)
        else:g.Uniform4f(loc['flexBody'],0,1,0,0)
        rope=plan.warp(index,self.motion_phase) if plan and index is not None else None
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
            raw=s.vertices.tobytes();buf=C.create_string_buffer(raw);g.BufferData(0x8892,len(raw),buf,0x88E8);self.dirty=False
        loc=self.locations
        g.Uniform1f(loc['section'],float(self.section))
        g.Uniform3f(loc['center'],*s.center);g.Uniform2f(loc['orbit'],self.yaw,self.tilt)
        scale=.86/s.radius*self.zoom;aspect=max(w,1)/max(h,1)
        g.Uniform3f(loc['projection'],scale/max(aspect,1),scale*min(aspect,1),1/(s.radius*4))
        self.motion_uniforms(None)
        g.Uniform1f(loc['edge'],0);g.Enable(0x0B71);g.DepthFunc(0x0203);g.Disable(0x0B90)
        g.Uniform1f(loc['lit'],0);g.Uniform3f(loc['color'],.12,.16,.205);g.DrawArrays(1,*s.grid)
        for part in s.parts:
            self.motion_uniforms(part.source_index)
            g.Uniform1f(loc['lit'],1);g.Uniform3f(loc['color'],*part.color);g.Enable(0x8037);g.PolygonOffset(1,1);g.DrawArrays(4,*part.side)
            for cap in part.caps:
                g.StencilMask(1);g.Clear(0x0400);g.Enable(0x0B90);g.Disable(0x0B71);g.DepthMask(0);g.ColorMask(0,0,0,0)
                g.StencilFunc(0x0207,0,1);g.StencilOp(0x1E00,0x1E00,0x150A);g.DrawArrays(4,*cap.fan)
                g.ColorMask(1,1,1,1);g.DepthMask(1);g.Enable(0x0B71);g.StencilMask(0);g.StencilFunc(0x0202,1,1);g.StencilOp(0x1E00,0x1E00,0x1E00);g.DrawArrays(4,*cap.plane);g.Disable(0x0B90)
            g.Disable(0x8037);g.Uniform1f(loc['lit'],0);g.Uniform1f(loc['edge'],1);g.Uniform3f(loc['color'],*(x*.55 for x in part.color));g.DrawArrays(1,*part.edges);g.Uniform1f(loc['edge'],0)
        if getattr(self,'capture_path',None):
            import cairo
            pixels=C.create_string_buffer(w*h*4);g.ReadPixels(0,0,w,h,0x80E1,0x1401,pixels)
            raw=bytearray().join(pixels.raw[row*w*4:(row+1)*w*4] for row in range(h-1,-1,-1))
            surface=cairo.ImageSurface.create_for_data(raw,cairo.FORMAT_ARGB32,w,h,w*4);surface.write_to_png(self.capture_path);self.capture_path=None
        g.StencilMask(0xFF);g.BindVertexArray(0);g.UseProgram(0)
        return True
