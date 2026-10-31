// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
// Material map and tangent-frame normal transport follow preview3d.py and
// website/assets/mechanism.js. All rigid poses come from the canonical worker.
const VERTEX = `
precision highp float;
attribute vec3 aPosition, aNormal, aMaterial;
uniform mat4 uModel;
uniform vec3 uCenter, uProjection, uExplode, uFlexCenter;
uniform vec2 uOrbit;
uniform vec4 uFlexShape, uFlexBody, uArcFirst, uArcSecond;
varying vec3 vNormal, vWorld;
vec3 camera(vec3 p){float c=cos(uOrbit.x),s=sin(uOrbit.x),a=cos(uOrbit.y),b=sin(uOrbit.y);vec3 q=vec3(c*p.x-s*p.y,s*p.x+c*p.y,p.z);return vec3(q.x,a*q.y-b*q.z,b*q.y+a*q.z);}
float waveSin(float angle){
 float x=mod(angle+3.141592653589793,6.283185307179586)-3.141592653589793;
 if(x>1.570796326794897)x=3.141592653589793-x;
 if(x< -1.570796326794897)x= -3.141592653589793-x;
 float q=x*x;
 return x*(1.0+q*(-0.166666666666667+q*(0.008333333333333+q*(-0.000198412698413+q*(0.000002755731922+q*(-0.000000025052108+q*0.000000000160590))))));
}
float waveCos(float angle){return waveSin(angle+1.570796326794897);}
float arcCoeff(int k){return k<4?uArcFirst[k]:uArcSecond[k-4];}
vec2 waveFrame(float u,float d,float w,float flex,float wave,out vec2 tangent){
 float angle=u+flex-wave,t=angle;
 for(int j=0;j<4;j++){
  float f=t-angle,der=1.0;
  for(int k=0;k<8;k++){float h=2.0*float(k+1);f+=arcCoeff(k)*waveSin(h*t);der+=h*arcCoeff(k)*waveCos(h*t);}
  t-=f/der;
 }
 float ct=waveCos(t),st=waveSin(t),cu=waveCos(u+flex),su=waveSin(u+flex);
 vec2 E=vec2(uFlexShape.z*ct,uFlexShape.w*st);
 vec2 N=normalize(vec2(ct/uFlexShape.z,st/uFlexShape.w));
 vec2 T=vec2(-uFlexShape.z*st,uFlexShape.w*ct);float speed=length(T);
 float curvature=uFlexShape.z*uFlexShape.w/(speed*speed*speed);
 T*=uFlexBody.x*(1.0+d*curvature)/speed;
 E+=d*N;float c=waveCos(wave),s=waveSin(wave);mat2 rotation=mat2(c,s,-s,c);E=rotation*E;
 tangent=normalize(mix((uFlexBody.x+d)*vec2(-su,cu),rotation*T,w));
 return mix((uFlexBody.x+d)*vec2(cu,su),E,w);
}
void main(){
 vec3 p=aPosition,nn=aNormal;
 if(uFlexBody.w>0.5){
  vec2 oldT,newT;
  p.xy=waveFrame(aMaterial.x,aMaterial.y,aMaterial.z,uFlexShape.x,uFlexShape.y,newT)+uFlexCenter.xy;
  waveFrame(aMaterial.x,aMaterial.y,aMaterial.z,0.0,0.0,oldT);
  vec2 oldN=vec2(oldT.y,-oldT.x),newN=vec2(newT.y,-newT.x);
  nn.xy=dot(nn.xy,oldT)*newT+dot(nn.xy,oldN)*newN;
 }
 vWorld=(uModel*vec4(p,1.0)).xyz+uExplode;
 vec3 cp=camera(vWorld-uCenter);
 vNormal=camera(mat3(uModel)*nn);
 gl_Position=vec4(cp.x*uProjection.x,cp.y*uProjection.y,-cp.z*uProjection.z,1.0);
}`;
const FRAGMENT = `
precision mediump float;
uniform vec3 uColor;
uniform float uSection, uSectionY, uSelected;
varying vec3 vNormal, vWorld;
void main(){
 if(uSection>0.5 && vWorld.y>uSectionY)discard;
 vec3 n=normalize(vNormal);
 float d=max(dot(n,normalize(vec3(-0.35,-0.25,1.0))),0.0);
 vec3 color=mix(uColor,vec3(0.98,0.65,0.30),uSelected*0.65);
 gl_FragColor=vec4(color*(0.48+0.52*d),1.0);
}`;
export const identityMatrix = () => [1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1];
// Exact inverse of camera() and uProjection in VERTEX. The near plane is
// camera z=+4r because gl_Position.z=-camera.z/(4r).
export function cameraRay({yaw,pitch,center,radius,zoom,width,height}, x, y) {
  const c=Math.cos(yaw),s=Math.sin(yaw),a=Math.cos(pitch),b=Math.sin(pitch);
  const inverse=([px,py,pz]) => { const qy=a*py+b*pz; return [c*px+s*qy,-s*px+c*qy,-b*py+a*pz]; };
  const scale=.86/radius*zoom, aspect=width/height;
  const point=inverse([x/(scale/Math.max(1,aspect)),y/(scale*Math.min(1,aspect)),radius*4]);
  return {ray_origin:point.map((v,i)=>v+center[i]),ray_direction:inverse([0,0,-1])};
}
const angle = x => ((x + Math.PI) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI) - Math.PI;
const nextFrame = () => new Promise(resolve => requestAnimationFrame(resolve));

export class ModelViewer extends EventTarget {
  constructor(canvas) {
    super(); this.canvas = canvas; this.meshes = []; this.design = null; this.frame = null;
    this.selected = new Set(); this.hidden = new Set(); this.supports = false; this.housing = false;
    this.explosion = 0; this.section = false; this.yaw = -35*Math.PI/180; this.pitch = -55*Math.PI/180; this.zoom = 1;
    this.center = [0,0,0]; this.radius = 30; this.lost = false; this.disposed = false; this.captureBusy = false;
    this.events = new AbortController(); const signal = this.events.signal;
    this.gl = canvas.getContext('webgl', {antialias: true, alpha: true, preserveDrawingBuffer: true});
    if (!this.gl) throw Error('WebGL is unavailable. Enable hardware acceleration or use another WebGL-capable browser.');
    this.initialize();
    canvas.addEventListener('webglcontextlost', event => {
      event.preventDefault(); this.lost = true; this.release(); this.program = null;
      this.dispatchEvent(new CustomEvent('context', {detail: {lost: true}}));
    }, {signal});
    canvas.addEventListener('webglcontextrestored', () => {
      try { this.lost = false; this.initialize(); if (this.design) this.upload(this.design); this.render(); this.dispatchEvent(new CustomEvent('context', {detail: {lost: false}})); }
      catch (error) { this.dispatchEvent(new CustomEvent('error', {detail: error})); }
    }, {signal});
    let drag = null;
    canvas.addEventListener('pointerdown', event => { if (event.button !== 0 || this.captureBusy) return; drag = {x:event.clientX,y:event.clientY,startX:event.clientX,startY:event.clientY,moved:false}; canvas.setPointerCapture(event.pointerId); canvas.focus({preventScroll: true}); }, {signal});
    canvas.addEventListener('pointermove', event => {
      if (!drag) return;
      if (!drag.moved && Math.hypot(event.clientX-drag.startX,event.clientY-drag.startY)<4) return;
      this.yaw += (event.clientX-drag.x)*0.008; this.pitch = Math.max(-Math.PI, Math.min(Math.PI, this.pitch+(event.clientY-drag.y)*0.008));
      drag = {...drag,x:event.clientX,y:event.clientY,moved:true}; this.render(); this.dispatchEvent(new Event('camera'));
    }, {signal});
    canvas.addEventListener('pointerup',event => { const click=drag && !drag.moved; drag=null; if (click) this.dispatchEvent(new CustomEvent('surfaceclick',{detail:{clientX:event.clientX,clientY:event.clientY,add:event.ctrlKey||event.metaKey||event.shiftKey}})); },{signal});
    for (const name of ['pointercancel','lostpointercapture']) canvas.addEventListener(name, () => { drag = null; }, {signal});
    canvas.addEventListener('wheel', event => { if (this.captureBusy) return; event.preventDefault(); this.zoom = Math.max(0.12, Math.min(14, this.zoom*Math.exp(-event.deltaY*0.001))); this.render(); }, {signal, passive: false});
    canvas.addEventListener('keydown', event => {
      if (this.captureBusy) return;
      if (event.key.toLowerCase() === 'f') this.fit();
      else if (event.key === '+' || event.key === '=') { this.zoom = Math.min(14,this.zoom*1.15); this.render(); }
      else if (event.key === '-') { this.zoom = Math.max(.12,this.zoom/1.15); this.render(); }
      else if (event.key.startsWith('Arrow')) { event.preventDefault(); if (event.key === 'ArrowLeft') this.yaw -= .12; if (event.key === 'ArrowRight') this.yaw += .12; if (event.key === 'ArrowUp') this.pitch -= .12; if (event.key === 'ArrowDown') this.pitch += .12; this.pitch = Math.max(-Math.PI,Math.min(Math.PI,this.pitch)); this.render(); this.dispatchEvent(new Event('camera')); }
    }, {signal});
    this.resizeObserver = new ResizeObserver(() => this.render()); this.resizeObserver.observe(canvas);
  }
  initialize() {
    const gl = this.gl, shaders = []; let program;
    try {
      for (const [type, source] of [[gl.VERTEX_SHADER,VERTEX],[gl.FRAGMENT_SHADER,FRAGMENT]]) {
        const shader = gl.createShader(type); shaders.push(shader); gl.shaderSource(shader, source); gl.compileShader(shader);
        if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw Error('Could not compile the 3D renderer: '+gl.getShaderInfoLog(shader));
      }
      program = gl.createProgram(); for (const shader of shaders) gl.attachShader(program,shader); gl.linkProgram(program);
      if (!gl.getProgramParameter(program,gl.LINK_STATUS)) throw Error('Could not initialize the 3D renderer: '+gl.getProgramInfoLog(program));
      this.program = program; this.attributes = {};
      for (const name of ['aPosition','aNormal','aMaterial']) this.attributes[name] = gl.getAttribLocation(program,name);
      this.uniforms = {};
      for (const name of ['uModel','uCenter','uProjection','uOrbit','uExplode','uColor','uSection','uSectionY','uSelected','uFlexShape','uFlexBody','uArcFirst','uArcSecond','uFlexCenter']) this.uniforms[name] = gl.getUniformLocation(program,name);
      gl.enable(gl.DEPTH_TEST); gl.disable(gl.CULL_FACE); gl.clearColor(0,0,0,0);
    } catch (error) { if (program) gl.deleteProgram(program); throw error; }
    finally { for (const shader of shaders) gl.deleteShader(shader); }
  }
  release() { for (const mesh of this.meshes) for (const b of Object.values(mesh.gpu)) this.gl.deleteBuffer(b); this.meshes = []; }
  upload(design) {
    const gl = this.gl; const meshes = [];
    try {
      for (const part of design.parts) {
        const mesh = {part, gpu: {}, matrix: identityMatrix(), deformation: null}; meshes.push(mesh);
        for (const channel of ['positions','normals','material']) {
          if (part.mesh[channel] == null) continue;
          const view = new Float32Array(design.buffers[part.mesh[channel]]);
          if (view.length !== part.mesh.vertex_count*3) throw Error('Incomplete '+channel+' buffer.');
          const buffer = gl.createBuffer(); if (!buffer) throw Error('Insufficient GPU memory for this model.');
          mesh.gpu[channel] = buffer; gl.bindBuffer(gl.ARRAY_BUFFER,buffer); gl.bufferData(gl.ARRAY_BUFFER,view,gl.STATIC_DRAW);
        }
      }
      if (gl.getError() !== gl.NO_ERROR) throw Error('The graphics device could not upload this model.');
    } catch (error) { for (const mesh of meshes) for (const b of Object.values(mesh.gpu)) gl.deleteBuffer(b); throw error; }
    this.release(); this.meshes = meshes;
    if (this.frame) this.applyFrame(this.frame, false);
  }
  setDesign(design, {fit = true} = {}) {
    if (design.motion.warping_indices?.length) throw Error('This model requires a deformation not supported by this browser renderer.');
    this.frame = null;
    this.upload(design); this.design = design; this.selected.clear(); this.hidden.clear();
    this.updateFraming();
    if (fit) this.zoom = 1;
    this.render();
  }
  clear() { this.release(); this.design = this.frame = null; this.selected.clear(); this.hidden.clear(); this.render(); }
  applyFrame(frame, render = true) {
    if (!this.design && render) return;
    if (frame.parts.length !== this.meshes.length) throw Error('Incomplete canonical motion frame.');
    for (const part of frame.parts) {
      const mesh = this.meshes[part.index];
      if (!mesh || part.warp != null) throw Error('Unsupported motion warp. Motion has stopped.');
      if (!Array.isArray(part.matrix) || part.matrix.length !== 16 || !part.matrix.every(Number.isFinite)) throw Error('Invalid motion transform.');
      if (part.deformation != null && (!mesh.gpu.material || part.deformation.length !== 7 || !part.deformation.every(Number.isFinite))) throw Error('Unsupported material deformation.');
      mesh.matrix = part.matrix; mesh.deformation = part.deformation;
    }
    this.frame = frame; if (render) this.render();
  }
  isVisible(part) { return !this.hidden.has(part.index) && (part.role !== 'support' || this.supports) && (part.role !== 'housing' || this.housing); }
  setVisibility(index, visible) { if (visible) this.hidden.delete(index); else this.hidden.add(index); this.render(); }
  setSelection(indices) { this.selected = new Set(indices); this.render(); }
  setView(name) {
    if (name === 'top') { this.yaw = 0; this.pitch = 0; }
    else if (name === 'front') { this.yaw = 0; this.pitch = -Math.PI/2; }
    else { this.yaw = -35*Math.PI/180; this.pitch = -55*Math.PI/180; }
    this.render();
    this.dispatchEvent(new CustomEvent('camera',{detail:{view:['top','front'].includes(name) ? name : 'isometric'}}));
  }
  fit() { this.zoom = 1; this.setView('isometric'); }
  updateFraming() {
    if (!this.design) return;
    const visible = this.design.parts.filter(part => this.isVisible(part));
    if (!visible.length) return;
    const minimum = [Infinity,Infinity,Infinity], maximum = [-Infinity,-Infinity,-Infinity];
    for (const part of visible) for (let i=0;i<3;i++) {
      minimum[i] = Math.min(minimum[i],part.bounds_mm.minimum[i]); maximum[i] = Math.max(maximum[i],part.bounds_mm.maximum[i]);
    }
    this.visibleBounds = {minimum,maximum}; this.center = minimum.map((v,i) => (v+maximum[i])/2);
    let squared = 1;
    // The desktop radius is the furthest sampled surface point from the centre,
    // rather than the diagonal of a bounding box including hidden supports.
    for (const part of visible) {
      const positions = new Float32Array(this.design.buffers[part.mesh.positions]);
      for (let i=0;i<positions.length;i+=3) squared = Math.max(squared,(positions[i]-this.center[0])**2+(positions[i+1]-this.center[1])**2+(positions[i+2]-this.center[2])**2);
    }
    this.radius = Math.sqrt(squared);
  }
  projectVector([x,y,z]) {
    const c=Math.cos(this.yaw),s=Math.sin(this.yaw),a=Math.cos(this.pitch),b=Math.sin(this.pitch);
    return [c*x-s*y,a*(s*x+c*y)-b*z,b*(s*x+c*y)+a*z];
  }
  explosionOffset(part) {
    const direction=part.bounds_mm.minimum.map((v,i)=>(v+part.bounds_mm.maximum[i])/2-this.center[i]);
    if (Math.hypot(...direction)<this.radius*.025) direction[2]=((part.index%2)*2-1)*this.radius*.15;
    return direction.map(v=>v*this.explosion*1.7);
  }
  pickState(clientX,clientY) {
    if (!this.design || this.lost || this.captureBusy) throw Error('The preview is unavailable for picking.');
    const rect=this.canvas.getBoundingClientRect(), visible=this.meshes.filter(m=>this.isVisible(m.part));
    const state={yaw:this.yaw,pitch:this.pitch,zoom:this.zoom,center:[...this.center],radius:this.radius,width:this.canvas.width,height:this.canvas.height};
    const payload={...cameraRay(state,2*(clientX-rect.left)/rect.width-1,1-2*(clientY-rect.top)/rect.height),visible_indices:visible.map(m=>m.part.index),matrices:visible.map(m=>({index:m.part.index,matrix:[...m.matrix]})),explosion_offsets:visible.map(m=>({index:m.part.index,offset:this.explosionOffset(m.part)})),animated:!!visible.some(m=>m.deformation || m.matrix.some((v,i)=>v!==identityMatrix()[i]))};
    if (this.section) payload.section_y=this.center[1];
    return {payload,key:JSON.stringify([state,rect.left,rect.top,rect.width,rect.height,payload.visible_indices,payload.matrices,payload.explosion_offsets,payload.section_y,visible.map(m=>m.deformation)])};
  }
  updateGuides(width,height) {
    const grid = document.getElementById('viewport-grid'), axes = document.getElementById('viewport-axes');
    if (!grid || !axes) return;
    const cache = JSON.stringify([width,height,this.center,this.radius,this.yaw,this.pitch,this.zoom,!!this.design]);
    if (cache === this.guideCache) return; this.guideCache = cache;
    const ns = 'http://www.w3.org/2000/svg', element = (name,attrs) => {
      const el = document.createElementNS(ns,name); for (const [key,value] of Object.entries(attrs)) el.setAttribute(key,String(value)); return el;
    };
    grid.replaceChildren(); axes.replaceChildren(); grid.setAttribute('viewBox',`0 0 ${width} ${height}`);
    const projection = .86/this.radius*this.zoom*Math.min(width,height)/2;
    if (this.design) {
      const bounds=this.visibleBounds ?? this.design.bounds_mm;
      const span=Math.max(bounds.maximum[0]-bounds.minimum[0],bounds.maximum[1]-bounds.minimum[1],10);
      let step=10**Math.floor(Math.log10(span/8)); if (span/step>16) step*=2;
      const extent=Math.ceil(span*.7/step)*step, ground=bounds.minimum[2]-Math.max(.5,span*.025);
      const project = p => { const q=this.projectVector(p.map((v,i)=>v-this.center[i])); return [width/2+q[0]*projection,height/2-q[1]*projection]; };
      let path='';
      for (let j=-Math.round(extent/step);j<=Math.round(extent/step);j++) {
        const off=j*step,cx=this.center[0],cy=this.center[1];
        for (const [a,b] of [[[cx+off,cy-extent,ground],[cx+off,cy+extent,ground]],[[cx-extent,cy+off,ground],[cx+extent,cy+off,ground]]]) {
          const p=project(a),q=project(b); path+=`M${p[0]},${p[1]}L${q[0]},${q[1]}`;
        }
      }
      grid.append(element('path',{d:path,fill:'none',stroke:'#1f2934','stroke-width':.7}));
    }
    for (const [name,v] of [['X',[1,0,0]],['Y',[0,1,0]],['Z',[0,0,1]]]) {
      const q=this.projectVector(v),x=43+26*q[0],y=43-26*q[1],attrs={stroke:'#c2d6e6','stroke-width':1.4,fill:'none'};
      axes.append(element('path',{d:`M43,43L${x},${y}`,...attrs}));
      if (Math.hypot(q[0],q[1])*26>4) {
        const angle=Math.atan2(y-43,x-43); let d='';
        for (const delta of [-.45,.45]) d+=`M${x},${y}L${x-5*Math.cos(angle+delta)},${y-5*Math.sin(angle+delta)}`;
        axes.append(element('path',{d,...attrs}));
      }
      const label=element('text',{x:x+4,y:y-4,fill:'#c2d6e6','font-size':12}); label.textContent=name; axes.append(label);
    }
  }
  render({indices = null, nominal = false} = {}) {
    if (this.lost || this.disposed || !this.program) return;
    const gl = this.gl, canvas = this.canvas, rect = canvas.getBoundingClientRect(), dpr = Math.min(2,globalThis.devicePixelRatio || 1);
    const width = Math.max(1,Math.round(rect.width*dpr)), height = Math.max(1,Math.round(rect.height*dpr));
    if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
    gl.viewport(0,0,width,height); gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT); gl.useProgram(this.program);
    const u = this.uniforms, scale = .86/this.radius*this.zoom, aspect = width/height;
    if (this.guides !== false) this.updateGuides(rect.width,rect.height);
    gl.uniform3fv(u.uCenter,this.center); gl.uniform2f(u.uOrbit,this.yaw,this.pitch);
    gl.uniform3f(u.uProjection,scale/Math.max(1,aspect),scale*Math.min(1,aspect),1/(this.radius*4));
    gl.uniform1f(u.uSection, !nominal && this.section ? 1 : 0); gl.uniform1f(u.uSectionY,this.center[1]);
    const selected = indices && new Set(indices);
    for (const mesh of this.meshes) {
      const part = mesh.part;
      // An explicit subset is the export scope, including selected support or
      // housing parts currently hidden in the regular inspection view.
      if (selected ? !selected.has(part.index) : !this.isVisible(part)) continue;
      gl.uniformMatrix4fv(u.uModel,false,mesh.matrix); gl.uniform3fv(u.uColor,part.color);
      gl.uniform1f(u.uSelected,!nominal && this.selected.has(part.index) ? 1 : 0);
      gl.uniform3fv(u.uExplode,nominal ? [0,0,0] : this.explosionOffset(part));
      const flex = mesh.deformation;
      gl.uniform4fv(u.uFlexShape,flex ? [angle(flex[0]),angle(flex[1]),flex[2],flex[3]] : [0,0,1,1]);
      gl.uniform4fv(u.uFlexBody,flex ? [flex[4],flex[5],flex[6],1] : [1,1,0,0]);
      const coefficients = this.design?.motion.wave_arc_coefficients ?? [0,0,0,0,0,0,0,0];
      gl.uniform4fv(u.uArcFirst,coefficients.slice(0,4)); gl.uniform4fv(u.uArcSecond,coefficients.slice(4,8));
      gl.uniform3fv(u.uFlexCenter,[...(part.center ?? [0,0]),0].slice(0,3));
      for (const [channel, attribute] of [['positions','aPosition'],['normals','aNormal'],['material','aMaterial']]) {
        const location = this.attributes[attribute];
        if (mesh.gpu[channel]) { gl.bindBuffer(gl.ARRAY_BUFFER,mesh.gpu[channel]); gl.enableVertexAttribArray(location); gl.vertexAttribPointer(location,3,gl.FLOAT,false,0,0); }
        else { gl.disableVertexAttribArray(location); gl.vertexAttrib3f(location,0,0,0); }
      }
      gl.drawArrays(gl.TRIANGLES,0,part.mesh.vertex_count);
    }
  }
  async captureNominal(frame, indices = null) {
    if (this.lost || !this.design || this.captureBusy) throw Error('The preview is not available for capture.');
    if (!this.design.parts.some(p => indices ? indices.includes(p.index) : this.isVisible(p))) throw Error('Show at least one exported component before capturing a package preview.');
    this.captureBusy = true; const previous = this.frame, design = this.design;
    try {
      this.applyFrame(frame,false); this.render({indices,nominal:true}); await nextFrame();
      if (this.design !== design || this.lost) throw Error('The model changed during preview capture.');
      // Repaint after the animation frame and finish actual GL work before PNG.
      this.applyFrame(frame,false); this.render({indices,nominal:true}); this.gl.finish();
      const blob = await new Promise((resolve,reject) => this.canvas.toBlob(value => value ? resolve(value) : reject(Error('The browser could not capture the 3D preview.')),'image/png'));
      return new Uint8Array(await blob.arrayBuffer());
    } finally { this.captureBusy = false; if (this.design === design) { if (previous) this.applyFrame(previous,false); this.render(); } }
  }
  dispose() { this.disposed = true; this.events.abort(); this.resizeObserver.disconnect(); this.release(); if (this.program) this.gl.deleteProgram(this.program); this.program = null; this.design = null; }
}
