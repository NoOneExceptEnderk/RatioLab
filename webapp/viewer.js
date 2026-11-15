// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
// Material map and tangent-frame normal transport follow preview3d.py and
// website/assets/mechanism.js. All rigid poses come from the canonical worker.
import {dragMode} from './controls.js';
const VERTEX = `
precision highp float;
attribute vec3 aPosition, aNormal, aMaterial;
uniform mat4 uModel;
uniform vec3 uCenter, uProjection, uExplode, uFlexCenter;
uniform vec2 uOrbit;
uniform float uSection, uSectionY;
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
 if(uSection==3.0){
  vec3 n=camera(vec3(0,1,0));
  float z=(uSectionY-uCenter.y-dot(n.xy,aPosition.xy/uProjection.xy))/n.z;
  gl_Position=vec4(aPosition.xy,-z*uProjection.z,1);
  vNormal=n; vWorld=vec3(0,uSectionY,0);
  return;
 }
 vec3 p=aPosition,nn=aNormal;
 if(uFlexBody.w>0.5){
  vec2 oldT,newT;
  p.xy=waveFrame(aMaterial.x,aMaterial.y,aMaterial.z,uFlexShape.x,uFlexShape.y,newT)+uFlexCenter.xy;
  if(uSection!=2.0){
   waveFrame(aMaterial.x,aMaterial.y,aMaterial.z,0.0,0.0,oldT);
   vec2 oldN=vec2(oldT.y,-oldT.x),newN=vec2(newT.y,-newT.x);
   nn.xy=dot(nn.xy,oldT)*newT+dot(nn.xy,oldN)*newN;
  }
 }
 vWorld=(uModel*vec4(p,1.0)).xyz+uExplode;
 vec3 cp=camera(vWorld-uCenter);
 vNormal=camera(mat3(uModel)*nn);
 gl_Position=vec4(cp.x*uProjection.x,cp.y*uProjection.y,uSection==2.0?0.0:-cp.z*uProjection.z,1.0);
}`;
const FRAGMENT = `
precision highp float;
uniform vec3 uColor;
uniform float uSection, uSectionY, uSelected, uPicking, uOpacity;
uniform vec3 uSelectionColor;
varying vec3 vNormal, vWorld;
void main(){
 if((uSection==1.0 && vWorld.y>uSectionY)||(uSection==2.0 && vWorld.y>=uSectionY))discard;
 vec3 n=normalize(vNormal);
 float d=max(dot(n,normalize(vec3(-0.35,-0.25,1.0))),0.0);
 vec3 color=mix(uColor,uSelectionColor,uSelected*0.65);
 gl_FragColor=vec4(color*(uPicking>0.5?1.0:uSection==3.0?0.85:0.48+0.52*d),uOpacity);
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

// Z-up face normals and tangent bases, shared with view_navigation.py.
export const cubeFaces = [
  ['Right',[1,0,0],[0,1,0],[0,0,1]],['Left',[-1,0,0],[0,-1,0],[0,0,1]],
  ['Back',[0,1,0],[-1,0,0],[0,0,1]],['Front',[0,-1,0],[1,0,0],[0,0,1]],
  ['Top',[0,0,1],[1,0,0],[0,1,0]],['Bottom',[0,0,-1],[1,0,0],[0,-1,0]]
];
export function viewOrientation([x,y,z]) {
  return {yaw:(x || y ? Math.atan2(-x,-y) : 0)||0,pitch:-Math.acos(Math.max(-1,Math.min(1,z/Math.hypot(x,y,z))))||0};
}
export function cameraPanDelta(dx,dy,{radius,zoom,yaw,pitch},width,height) {
  const scale=.43/Math.max(radius,1e-12)*zoom*Math.max(1,Math.min(width,height));
  const x=-dx/scale,y=dy/scale,c=Math.cos(yaw),s=Math.sin(yaw),a=Math.cos(pitch),b=Math.sin(pitch);
  return [c*x+s*a*y,-s*x+c*a*y,-b*y];
}
export function cubePatches(project,size=116) {
  const cuts=[-1,-.62,.62,1],patches=[];
  for (const [name,n,u,v] of cubeFaces) {
    const shade=project(n)[2]; if (shade<1e-6) continue;
    for (let i=0;i<3;i++) for (let j=0;j<3;j++) {
      const point=(a,b)=>n.map((v0,k)=>v0+a*u[k]+b*v[k]);
      const polygon=[[cuts[i],cuts[j]],[cuts[i+1],cuts[j]],[cuts[i+1],cuts[j+1]],[cuts[i],cuts[j+1]]].map(([a,b])=>{const q=project(point(a,b));return [size/2+size*.255*q[0],size/2-size*.255*q[1]];});
      patches.push({name,polygon,direction:n.map((v0,k)=>v0+(i-1)*u[k]+(j-1)*v[k]),central:i===1&&j===1,shade});
    }
  }
  return patches;
}
export function hitCube(patches,x,y) {
  return patches.find(({polygon})=>{
    const cross=polygon.map((a,i)=>{const b=polygon[(i+1)%4];return (b[0]-a[0])*(y-a[1])-(b[1]-a[1])*(x-a[0]);});
    return Math.min(...cross)>=-1e-7 || Math.max(...cross)<=1e-7;
  })?.direction;
}

export class ModelViewer extends EventTarget {
  constructor(canvas, {guides = true} = {}) {
    super(); this.canvas = canvas; this.meshes = []; this.design = null; this.frame = null;
    this.selected = new Set(); this.hidden = new Set(); this.supports = false; this.housing = false;
    this.explosion = 0; this.section = false; this.yaw = -35*Math.PI/180; this.pitch = -55*Math.PI/180; this.zoom = 1; this.panOffset=[0,0,0]; this.panMode=false;
    this.center = [0,0,0]; this.radius = this.explodedRadius = 30; this.lost = false; this.disposed = false; this.captureBusy = false;
    this.zoomSpeed = 1; this.rotationSpeed = 1; this.invertZoom = false;
    this.mouseNavigation='ratiolab';this.selectionColor=[0.98,0.65,0.30];this.gridColor=null;this.managedShortcuts=false;
    this.guides = guides;
    this.contextOpacity = null; this.pickableIndices = null;
    this.events = new AbortController(); const signal = this.events.signal;
    this.gl = canvas.getContext('webgl', {antialias: true, alpha: true, stencil: true, preserveDrawingBuffer: true});
    if (!this.gl) throw Error('WebGL is unavailable. Enable hardware acceleration or use another WebGL-capable browser.');
    this.initialize();
    canvas.addEventListener('webglcontextlost', event => {
      event.preventDefault(); this.lost = true; this.release(); this.program = this.sectionQuad = null;
      this.dispatchEvent(new CustomEvent('context', {detail: {lost: true}}));
    }, {signal});
    canvas.addEventListener('webglcontextrestored', () => {
      try { this.lost = false; this.initialize(); if (this.design) this.upload(this.design); this.render(); this.dispatchEvent(new CustomEvent('context', {detail: {lost: false}})); }
      catch (error) { this.dispatchEvent(new CustomEvent('error', {detail: error})); }
    }, {signal});
    let drag = null;
    canvas.addEventListener('pointerdown', event => { if (![0,1,2].includes(event.button) || this.captureBusy) return; event.preventDefault(); const mode=dragMode(this.mouseNavigation,event.buttons??[1,4,2][event.button??drag?.button??0],{shift:event.shiftKey,control:event.ctrlKey,alt:event.altKey,panMode:this.panMode});drag={pan:mode==='pan',button:event.button,x:event.clientX,y:event.clientY,startX:event.clientX,startY:event.clientY,moved:false};if(drag.pan)canvas.style.cursor='grabbing';canvas.setPointerCapture(event.pointerId);canvas.focus({preventScroll:true}); }, {signal});
    canvas.addEventListener('pointermove', event => {
      if (!drag) return;
      if (!drag.moved && Math.hypot(event.clientX-drag.startX,event.clientY-drag.startY)<4) return;
      const mode=dragMode(this.mouseNavigation,event.buttons??[1,4,2][event.button??drag?.button??0],{shift:event.shiftKey,control:event.ctrlKey,alt:event.altKey,panMode:this.panMode});
      const dx=event.clientX-drag.x,dy=event.clientY-drag.y;
      if(mode==='pan')this.panBy(dx,dy);
      else if(mode==='orbit'){this.yaw+=dx*.008*this.rotationSpeed;this.pitch=Math.max(-Math.PI,Math.min(Math.PI,this.pitch+dy*.008*this.rotationSpeed));}
      else if(mode==='zoom')this.zoom=Math.max(.12,Math.min(14,this.zoom*Math.exp(-dy*.01*this.zoomSpeed)));
      drag = {...drag,x:event.clientX,y:event.clientY,moved:true}; this.render(); this.dispatchEvent(new Event('camera'));
    }, {signal});
    canvas.addEventListener('pointerup',event => { const click=drag && drag.button===0 && !drag.pan && !drag.moved; drag=null;canvas.style.cursor=''; if (click) this.dispatchEvent(new CustomEvent('surfaceclick',{detail:{clientX:event.clientX,clientY:event.clientY,add:event.ctrlKey||event.metaKey||event.shiftKey}})); },{signal});
    canvas.addEventListener('contextmenu',event=>event.preventDefault(),{signal});
    canvas.addEventListener('dblclick',event=>{if(!this.captureBusy){event.preventDefault();this.fitCurrent();}},{signal});
    for (const name of ['pointercancel','lostpointercapture']) canvas.addEventListener(name, () => { drag = null;canvas.style.cursor=''; }, {signal});
    canvas.addEventListener('wheel', event => { if (this.captureBusy) return; event.preventDefault(); const delta = Math.max(-20,Math.min(20,-event.deltaY*0.001*this.zoomSpeed*(this.invertZoom ? -1 : 1))); this.zoom = Math.max(0.12, Math.min(14, this.zoom*Math.exp(delta))); this.render(); }, {signal, passive: false});
    canvas.addEventListener('keydown', event => {
      if (this.captureBusy) return;
      if (!this.managedShortcuts && event.key.toLowerCase() === 'f') this.fit();
      else if (event.key === '+' || event.key === '=') { this.zoom = Math.min(14,this.zoom*1.15); this.render(); }
      else if (event.key === '-') { this.zoom = Math.max(.12,this.zoom/1.15); this.render(); }
      else if (event.key.startsWith('Arrow')) { event.preventDefault(); if (event.key === 'ArrowLeft') this.yaw -= .12; if (event.key === 'ArrowRight') this.yaw += .12; if (event.key === 'ArrowUp') this.pitch -= .12; if (event.key === 'ArrowDown') this.pitch += .12; this.pitch = Math.max(-Math.PI,Math.min(Math.PI,this.pitch)); this.render(); this.dispatchEvent(new Event('camera')); }
    }, {signal});
    if (guides) this.installCube();
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
      for (const name of ['uModel','uCenter','uProjection','uOrbit','uExplode','uColor','uSection','uSectionY','uSelected','uSelectionColor','uFlexShape','uFlexBody','uArcFirst','uArcSecond','uFlexCenter','uPicking','uOpacity']) this.uniforms[name] = gl.getUniformLocation(program,name);
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
  get cameraCenter() { return this.center.map((v,i)=>v+this.panOffset[i]); }
  get explosionScale() {
    const view = Number(this.supports) + 2 * Number(this.housing);
    const gradual = this.design?.explosion_gradual_views?.includes(view);
    const minimum = gradual ? 0 : this.design?.explosion_minimum ?? 0;
    return this.explosion ? minimum + this.explosion * (1 - minimum) : 0;
  }
  get cameraRadius() { return this.radius + this.explosionScale * (this.explodedRadius - this.radius); }
  panBy(dx,dy) {
    const rect=this.canvas.getBoundingClientRect();
    const {yaw,pitch,zoom}=this;
    const delta=cameraPanDelta(dx,dy,{yaw,pitch,zoom,radius:this.cameraRadius},rect.width,rect.height);
    this.panOffset=this.panOffset.map((v,i)=>v+delta[i]);
  }
  orient(direction) {
    if (this.captureBusy) return;
    Object.assign(this,viewOrientation(direction));this.render();
    const face=cubeFaces.find(([,n])=>n.every((v,i)=>v===direction[i]));
    this.dispatchEvent(new CustomEvent('camera',{detail:{view:face?.[0].toLowerCase()}}));
  }
  setView(name) {
    if (this.captureBusy) return;
    const face=cubeFaces.find(([label])=>label.toLowerCase()===name);
    if (face) Object.assign(this,viewOrientation(face[1]));
    else { this.yaw=-35*Math.PI/180;this.pitch=-55*Math.PI/180; }
    this.render();
    this.dispatchEvent(new CustomEvent('camera',{detail:{view:face ? name : 'isometric'}}));
  }
  fit() { if (this.captureBusy) return; this.zoom=1;this.panOffset=[0,0,0];this.setView('isometric'); }
  fitCurrent() {
    if (this.captureBusy) return;
    this.zoom=1;this.panOffset=[0,0,0];this.render();this.dispatchEvent(new CustomEvent('camera',{detail:{fitOnly:true}}));
  }
  installCube() {
    const cube=document.getElementById('viewport-cube');if (!cube) return;
    this.cube=cube;const signal=this.events.signal;let drag=null;
    const point=event=>{const r=cube.getBoundingClientRect();return [(event.clientX-r.left)*116/r.width,(event.clientY-r.top)*116/r.height];};
    cube.addEventListener('pointerdown',event=>{
      if (event.button!==0 || this.captureBusy) return;
      event.preventDefault();cube.focus({preventScroll:true});cube.setPointerCapture(event.pointerId);
      drag={x:event.clientX,y:event.clientY,yaw:this.yaw,pitch:this.pitch,moved:false,point:point(event)};
    },{signal});
    cube.addEventListener('pointermove',event=>{
      if (!drag || this.captureBusy) return;
      const dx=event.clientX-drag.x,dy=event.clientY-drag.y;
      if (!drag.moved && Math.hypot(dx,dy)<4) return;
      drag.moved=true;this.yaw=drag.yaw+dx*.008;this.pitch=Math.max(-Math.PI,Math.min(Math.PI,drag.pitch+dy*.008));
      this.render();this.dispatchEvent(new Event('camera'));
    },{signal});
    cube.addEventListener('pointerup',()=>{
      if (drag && !drag.moved) { const d=hitCube(cubePatches(p=>this.projectVector(p)),...drag.point);if(d)this.orient(d); }
      drag=null;
    },{signal});
    for (const name of ['pointercancel','lostpointercapture']) cube.addEventListener(name,()=>{drag=null;},{signal});
    cube.addEventListener('keydown',event=>{
      if (this.captureBusy) return;
      const i='123456'.indexOf(event.key);
      if (event.key.length===1 && i>=0) { event.preventDefault();this.orient(cubeFaces[[3,2,0,1,4,5][i]][1]); }
      else if (event.key==='Home') { event.preventDefault();this.fit(); }
      else if (event.key.startsWith('Arrow')) {
        event.preventDefault();this.yaw+=.12*((event.key==='ArrowRight')-(event.key==='ArrowLeft'));
        this.pitch=Math.max(-Math.PI,Math.min(Math.PI,this.pitch+.12*((event.key==='ArrowDown')-(event.key==='ArrowUp'))));
        this.render();this.dispatchEvent(new Event('camera'));
      }
    },{signal});
  }
  renderCube() {
    if (!this.cube) return;
    const key=JSON.stringify([this.yaw,this.pitch]);if(this.cubeCache===key)return;this.cubeCache=key;
    const ns='http://www.w3.org/2000/svg',fragment=document.createDocumentFragment();
    for (const {name,polygon,direction,central,shade} of cubePatches(p=>this.projectVector(p))) {
      const tile=document.createElementNS(ns,'polygon');tile.setAttribute('points',polygon.map(p=>p.join(',')).join(' '));
      tile.style.setProperty('--shade',shade);tile.setAttribute('class','cube-tile');
      const title=document.createElementNS(ns,'title');title.textContent=direction.filter(v=>v!==0).length===1 ? name : direction.map((v,i)=>v ? (i===0 ? v>0?'Right':'Left' : i===1 ? v>0?'Back':'Front' : v>0?'Top':'Bottom') : '').filter(Boolean).join(' / ');
      tile.append(title);fragment.append(tile);
      if (central) { const text=document.createElementNS(ns,'text');text.setAttribute('x',polygon.reduce((sum,p)=>sum+p[0],0)/4);text.setAttribute('y',polygon.reduce((sum,p)=>sum+p[1],0)/4);text.textContent=name.toUpperCase();fragment.append(text); }
    }
    this.cube.replaceChildren(fragment);
  }
  updateFraming() {
    if (!this.design) return;
    const visible = this.design.parts.filter(part => this.isVisible(part));
    if (!visible.length) return;
    const minimum = [Infinity,Infinity,Infinity], maximum = [-Infinity,-Infinity,-Infinity];
    for (const part of visible) for (let i=0;i<3;i++) {
      minimum[i] = Math.min(minimum[i],part.bounds_mm.minimum[i]); maximum[i] = Math.max(maximum[i],part.bounds_mm.maximum[i]);
    }
    this.visibleBounds = {minimum,maximum}; this.center = minimum.map((v,i) => (v+maximum[i])/2);
    let squared = 1, explodedSquared = 1;
    // The desktop radius is the furthest sampled surface point from the centre,
    // rather than the diagonal of a bounding box including hidden supports.
    for (const part of visible) {
      const positions = new Float32Array(this.design.buffers[part.mesh.positions]);
      const [dx,dy,dz] = this.explosionOffset(part, 1);
      for (let i=0;i<positions.length;i+=3) {
        const x=positions[i]-this.center[0], y=positions[i+1]-this.center[1], z=positions[i+2]-this.center[2];
        squared = Math.max(squared,x*x+y*y+z*z);
        explodedSquared = Math.max(explodedSquared,(x+dx)**2+(y+dy)**2+(z+dz)**2);
      }
    }
    this.radius = Math.sqrt(squared);
    this.explodedRadius = Math.sqrt(Math.max(squared,explodedSquared));
  }
  projectVector([x,y,z]) {
    const c=Math.cos(this.yaw),s=Math.sin(this.yaw),a=Math.cos(this.pitch),b=Math.sin(this.pitch);
    return [c*x-s*y,a*(s*x+c*y)-b*z,b*(s*x+c*y)+a*z];
  }
  explosionOffset(part, scale = this.explosionScale) {
    return (part.explosion_offset_mm ?? [0,0,0]).map(value => value * scale);
  }
  pickState(clientX,clientY) {
    if (!this.design || this.lost || this.captureBusy) throw Error('The preview is unavailable for picking.');
    const rect=this.canvas.getBoundingClientRect(), visible=this.meshes.filter(m=>this.isVisible(m.part));
    const state={yaw:this.yaw,pitch:this.pitch,zoom:this.zoom,center:this.cameraCenter,radius:this.cameraRadius,width:this.canvas.width,height:this.canvas.height};
    const identity = identityMatrix();
    const payload={...cameraRay(state,2*(clientX-rect.left)/rect.width-1,1-2*(clientY-rect.top)/rect.height),visible_indices:visible.map(m=>m.part.index),matrices:visible.map(m=>({index:m.part.index,matrix:this.explosion ? identity : [...m.matrix]})),explosion_offsets:visible.map(m=>({index:m.part.index,offset:this.explosionOffset(m.part)})),animated:!this.explosion && visible.some(m=>m.deformation || m.matrix.some((v,i)=>v!==identity[i]))};
    if (this.section) payload.section_y=this.center[1];
    return {payload,key:JSON.stringify([state,rect.left,rect.top,rect.width,rect.height,payload.visible_indices,payload.matrices,payload.explosion_offsets,payload.section_y,visible.map(m=>m.deformation)])};
  }
  updateGuides(width,height) {
    const grid = document.getElementById('viewport-grid');
    if (!grid) return;
    const cache = JSON.stringify([width,height,this.center,this.panOffset,this.cameraRadius,this.yaw,this.pitch,this.zoom,!!this.design,this.gridColor]);
    if (cache === this.guideCache) return; this.guideCache = cache;
    const ns = 'http://www.w3.org/2000/svg', element = (name,attrs) => {
      const el = document.createElementNS(ns,name); for (const [key,value] of Object.entries(attrs)) el.setAttribute(key,String(value)); return el;
    };
    grid.replaceChildren(); grid.setAttribute('viewBox',`0 0 ${width} ${height}`);
    const projection = .86/this.cameraRadius*this.zoom*Math.min(width,height)/2;
    if (this.design) {
      const bounds=this.visibleBounds ?? this.design.bounds_mm;
      const span=Math.max(bounds.maximum[0]-bounds.minimum[0],bounds.maximum[1]-bounds.minimum[1],10);
      let step=10**Math.floor(Math.log10(span/8)); if (span/step>16) step*=2;
      const extent=Math.ceil(span*.7/step)*step, ground=bounds.minimum[2]-Math.max(.5,span*.025);
      const project = p => { const q=this.projectVector(p.map((v,i)=>v-this.cameraCenter[i])); return [width/2+q[0]*projection,height/2-q[1]*projection]; };
      let path='';
      for (let j=-Math.round(extent/step);j<=Math.round(extent/step);j++) {
        const off=j*step,cx=this.center[0],cy=this.center[1];
        for (const [a,b] of [[[cx+off,cy-extent,ground],[cx+off,cy+extent,ground]],[[cx-extent,cy+off,ground],[cx+extent,cy+off,ground]]]) {
          const p=project(a),q=project(b); path+=`M${p[0]},${p[1]}L${q[0]},${q[1]}`;
        }
      }
      grid.append(element('path',{d:path,fill:'none',stroke:this.gridColor??(document.documentElement.dataset.theme === 'light' ? '#c6d1d8' : '#1f2934'),'stroke-width':.7}));
    }
  }

  renderSectionCap(vertexCount) {
    const gl = this.gl, u = this.uniforms, position = this.attributes.aPosition;
    if (!this.sectionQuad) {
      this.sectionQuad = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER,this.sectionQuad);
      gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,0, 1,-1,0, -1,1,0, 1,1,0]),gl.STATIC_DRAW);
    }
    // Along a viewing ray, an odd number of crossings on the kept side
    // means the plane intersects solid material at this pixel.
    gl.uniform1f(u.uSection,2);
    gl.stencilMask(1); gl.clear(gl.STENCIL_BUFFER_BIT);
    gl.enable(gl.STENCIL_TEST); gl.disable(gl.DEPTH_TEST);
    gl.depthMask(false); gl.colorMask(false,false,false,false);
    gl.stencilFunc(gl.ALWAYS,0,1); gl.stencilOp(gl.KEEP,gl.KEEP,gl.INVERT);
    gl.drawArrays(gl.TRIANGLES,0,vertexCount);

    gl.colorMask(true,true,true,true); gl.depthMask(true); gl.enable(gl.DEPTH_TEST);
    gl.stencilMask(0); gl.stencilFunc(gl.EQUAL,1,1); gl.stencilOp(gl.KEEP,gl.KEEP,gl.KEEP);
    gl.uniform1f(u.uSection,3);
    gl.bindBuffer(gl.ARRAY_BUFFER,this.sectionQuad); gl.vertexAttribPointer(position,3,gl.FLOAT,false,0,0);
    for (const attribute of [this.attributes.aNormal,this.attributes.aMaterial]) gl.disableVertexAttribArray(attribute);
    gl.drawArrays(gl.TRIANGLE_STRIP,0,4);
    gl.disable(gl.STENCIL_TEST); gl.uniform1f(u.uSection,1);
  }

  render({indices = null, nominal = false, picking = false} = {}) {
    if (this.lost || this.disposed || !this.program) return;
    const gl = this.gl, canvas = this.canvas, rect = canvas.getBoundingClientRect(), dpr = Math.min(2,globalThis.devicePixelRatio || 1);
    const width = Math.max(1,Math.round(rect.width*dpr)), height = Math.max(1,Math.round(rect.height*dpr));
    if (!picking && (canvas.width !== width || canvas.height !== height)) { canvas.width = width; canvas.height = height; }
    gl.viewport(0,0,width,height); gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT); gl.useProgram(this.program);
    const u = this.uniforms, radius = nominal ? this.radius : this.cameraRadius, scale = .86/radius*this.zoom, aspect = width/height;
    if (!picking) {
      if (this.guides !== false) this.updateGuides(rect.width,rect.height);
      this.renderCube();
    }
    gl.uniform1f(u.uPicking,Number(picking));
    gl.uniform3fv(u.uCenter,nominal ? this.center : this.cameraCenter); gl.uniform2f(u.uOrbit,this.yaw,this.pitch);
    gl.uniform3f(u.uProjection,scale/Math.max(1,aspect),scale*Math.min(1,aspect),1/(radius*4));
    gl.uniform3fv(u.uSelectionColor,this.selectionColor);
    const section = !nominal && this.section;
    const capVisible = section && Math.abs(Math.cos(this.yaw)*Math.sin(this.pitch)) > 1e-6;
    gl.uniform1f(u.uSection,section ? 1 : 0); gl.uniform1f(u.uSectionY,this.center[1]);
    const selected = indices && new Set(indices);
    const exploded = !nominal && this.explosion > 0, identity = exploded && identityMatrix();
    // Explicit export indices can include hidden support and housing parts.
    const meshes = this.meshes.filter(({part}) =>
      (selected ? selected.has(part.index) : this.isVisible(part)) &&
      (!picking || !this.pickableIndices || this.pickableIndices.has(part.index)));
    let passes = [{meshes}];
    if (this.contextOpacity !== null && this.selected.size && !nominal && !section) {
      const context = meshes.filter(({part}) => !this.selected.has(part.index));
      const focus = meshes.filter(({part}) => this.selected.has(part.index));
      // Limit the translucent context to the nearest surface before painting
      // the fully opaque selected parts over it.
      passes = picking ? [{meshes:context}] : [
        {meshes:context, depthOnly:true}, {meshes:context, ghost:true}];
      passes.push({meshes:focus, clearDepth:true});
    }
    const coefficients = this.design?.motion.wave_arc_coefficients ?? [0,0,0,0,0,0,0,0];
    gl.uniform4fv(u.uArcFirst,coefficients.slice(0,4)); gl.uniform4fv(u.uArcSecond,coefficients.slice(4,8));
    for (const pass of passes) {
      gl.depthMask(!pass.ghost);
      if (pass.clearDepth) gl.clear(gl.DEPTH_BUFFER_BIT);
      gl.depthFunc(pass.ghost ? gl.EQUAL : gl.LESS);
      gl.colorMask(!pass.depthOnly,!pass.depthOnly,!pass.depthOnly,!pass.depthOnly);
      if (pass.ghost) {
        gl.enable(gl.BLEND);
        gl.blendFuncSeparate(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA,gl.ONE,gl.ONE_MINUS_SRC_ALPHA);
      } else gl.disable(gl.BLEND);
      gl.uniform1f(u.uOpacity,pass.ghost ? this.contextOpacity : 1);
      for (const mesh of pass.meshes) {
        const part = mesh.part;
        const id=part.index+1;
        gl.uniformMatrix4fv(u.uModel,false,exploded ? identity : mesh.matrix);
        gl.uniform3fv(u.uColor,picking ? [id&255,(id>>8)&255,(id>>16)&255].map(value=>value/255) : part.color);
        gl.uniform1f(u.uSelected,!picking && !nominal && this.selected.has(part.index) ? 1 : 0);
        gl.uniform3fv(u.uExplode,nominal ? [0,0,0] : this.explosionOffset(part));
        const flex = exploded ? null : mesh.deformation;
        gl.uniform4fv(u.uFlexShape,flex ? [angle(flex[0]),angle(flex[1]),flex[2],flex[3]] : [0,0,1,1]);
        gl.uniform4fv(u.uFlexBody,flex ? [flex[4],flex[5],flex[6],1] : [1,1,0,0]);
        gl.uniform3fv(u.uFlexCenter,[...(part.center ?? [0,0]),0].slice(0,3));
        for (const [channel, attribute] of [['positions','aPosition'],['normals','aNormal'],['material','aMaterial']]) {
          const location = this.attributes[attribute];
          if (mesh.gpu[channel]) { gl.bindBuffer(gl.ARRAY_BUFFER,mesh.gpu[channel]); gl.enableVertexAttribArray(location); gl.vertexAttribPointer(location,3,gl.FLOAT,false,0,0); }
          else { gl.disableVertexAttribArray(location); gl.vertexAttrib3f(location,0,0,0); }
        }
        gl.drawArrays(gl.TRIANGLES,0,part.mesh.vertex_count);
        if (capVisible) this.renderSectionCap(part.mesh.vertex_count);
      }
    }
    gl.colorMask(true,true,true,true);
    gl.depthMask(true);
    gl.depthFunc(gl.LESS);
    gl.disable(gl.BLEND);
  }
  partIdFrame(clientX, clientY) {
    // Use an opaque, single-sample target so edge blending and the default
    // canvas antialiasing cannot turn two adjacent IDs into a third one.
    if (!this.design || this.lost || this.disposed || this.captureBusy || this.section || this.frame) return null;
    const gl=this.gl, rect=this.canvas.getBoundingClientRect(), dpr=Math.min(2,globalThis.devicePixelRatio || 1);
    const width=Math.round(rect.width*dpr), height=Math.round(rect.height*dpr);
    if (!width || !height) return null;
    const atPoint=clientX !== undefined;
    const x=atPoint ? Math.floor((clientX-rect.left)*width/rect.width) : 0;
    const y=atPoint ? height-1-Math.floor((clientY-rect.top)*height/rect.height) : 0;
    if (x<0 || y<0 || x>=width || y>=height) return null;
    const savedFramebuffer=gl.getParameter(gl.FRAMEBUFFER_BINDING);
    const savedRenderbuffer=gl.getParameter(gl.RENDERBUFFER_BINDING);
    const savedTexture=gl.getParameter(gl.TEXTURE_BINDING_2D);
    const dither=gl.isEnabled(gl.DITHER);
    const target=gl.createFramebuffer(), color=gl.createTexture(), depth=gl.createRenderbuffer();
    try {
      if (!(target && color && depth)) return null;
      gl.bindFramebuffer(gl.FRAMEBUFFER,target);
      gl.bindTexture(gl.TEXTURE_2D,color);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.NEAREST);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.NEAREST);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
      gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,width,height,0,gl.RGBA,gl.UNSIGNED_BYTE,null);
      gl.framebufferTexture2D(gl.FRAMEBUFFER,gl.COLOR_ATTACHMENT0,gl.TEXTURE_2D,color,0);
      gl.bindRenderbuffer(gl.RENDERBUFFER,depth);
      gl.renderbufferStorage(gl.RENDERBUFFER,gl.DEPTH_COMPONENT16,width,height);
      gl.framebufferRenderbuffer(gl.FRAMEBUFFER,gl.DEPTH_ATTACHMENT,gl.RENDERBUFFER,depth);
      if (gl.checkFramebufferStatus(gl.FRAMEBUFFER)!==gl.FRAMEBUFFER_COMPLETE) return null;
      gl.disable(gl.DITHER);
      this.render({picking:true});
      const w=atPoint?1:width, h=atPoint?1:height;
      const result=new Uint8Array(w*h*4);
      gl.readPixels(x,y,w,h,gl.RGBA,gl.UNSIGNED_BYTE,result);
      return result;
    } finally {
      if (dither) gl.enable(gl.DITHER);
      gl.bindFramebuffer(gl.FRAMEBUFFER,savedFramebuffer);
      gl.bindRenderbuffer(gl.RENDERBUFFER,savedRenderbuffer);
      gl.bindTexture(gl.TEXTURE_2D,savedTexture);
      gl.deleteFramebuffer(target);gl.deleteRenderbuffer(depth);gl.deleteTexture(color);
    }
  }
  pickComponent(x,y) {
    const pixels=this.partIdFrame(x,y);
    return pixels ? (pixels[0]+256*pixels[1]+65536*pixels[2]-1) : -1;
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
  dispose() { this.disposed = true; this.events.abort(); this.resizeObserver.disconnect(); this.release(); if (this.program) this.gl.deleteProgram(this.program); if (this.sectionQuad) this.gl.deleteBuffer(this.sectionQuad); this.sectionQuad = this.program = this.design = null; }
}
