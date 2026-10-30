// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
/* One local WebGL renderer for canonical RatioLab surfaces and v2 rigid poses. */
((root, factory) => {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root.document) api.mount(root);
})(globalThis, () => {
  'use strict';
  // Strain-wave map and tangent-frame normal transport ported from RatioLab preview3d.py.
  const vertexSource = `
precision highp float;
attribute vec3 aPosition, aNormal, aMaterial;
uniform mat4 uModel, uView, uProjection;
uniform vec4 uFlexShape, uFlexBody, uArcFirst, uArcSecond;
uniform vec3 uFlexCenter;
varying vec3 vNormal;
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
vec2 wavePoint(float u,float d,float w,float flex,float wave){vec2 tangent;return waveFrame(u,d,w,flex,wave,tangent);}

void main(){
 vec3 p=aPosition,nn=aNormal;
 if(uFlexBody.w>0.5){
  p.xy=wavePoint(aMaterial.x,aMaterial.y,aMaterial.z,uFlexShape.x,uFlexShape.y)+uFlexCenter.xy;
  vec2 oldT,newT;
  waveFrame(aMaterial.x,aMaterial.y,aMaterial.z,0.0,0.0,oldT);
  waveFrame(aMaterial.x,aMaterial.y,aMaterial.z,uFlexShape.x,uFlexShape.y,newT);
  vec2 oldN=vec2(oldT.y,-oldT.x),newN=vec2(newT.y,-newT.x);
  nn.xy=dot(nn.xy,oldT)*newT+dot(nn.xy,oldN)*newN;
 }
 vec4 world=uModel*vec4(p,1.0);
 vNormal=mat3(uModel)*nn;
 gl_Position=uProjection*uView*world;
}`;
  const wrappedAngle=angle=>{const v=angle%(2*Math.PI);return v>Math.PI?v-2*Math.PI:v< -Math.PI?v+2*Math.PI:v;};
  function deformationUniforms(mesh,phase){
    const d=mesh.deformation;
    return d?{flexShape:[wrappedAngle(d.flexOffset+d.flexRate*phase),wrappedAngle(d.waveOffset+d.waveRate*phase),...d.ellipseAxes],flexBody:[d.pitchRadius,d.bodyLength,d.diaphragm,1],arcFirst:d.arcCoefficients.slice(0,4),arcSecond:d.arcCoefficients.slice(4,8),center:d.center}:{flexShape:[0,0,1,1],flexBody:[1,1,0,0],arcFirst:[0,0,0,0],arcSecond:[0,0,0,0],center:[0,0,0]};
  }
  // Float64 counterpart of the canonical material map: eight Newton steps.
  function waveFrame(material,d,flex,wave){
    const [u,offset,weight]=material,[a,b]=d.ellipseAxes,rp=d.pitchRadius,angle=u+flex-wave;let theta=angle;
    for(let j=0;j<8;j++){
      let residual=theta-angle,derivative=1;
      d.arcCoefficients.forEach((c,k)=>{const h=2*(k+1);residual+=c*Math.sin(h*theta);derivative+=h*c*Math.cos(h*theta);});
      theta-=residual/derivative;
    }
    const ct=Math.cos(theta),st=Math.sin(theta),cu=Math.cos(u+flex),su=Math.sin(u+flex),c=Math.cos(wave),s=Math.sin(wave);
    const length=Math.hypot(ct/a,st/b),nx=ct/a/length,ny=st/b/length;
    const ex=a*ct+offset*nx,ey=b*st+offset*ny,speed=Math.hypot(a*st,b*ct),curvature=a*b/(speed*speed*speed),scale=rp*(1+offset*curvature)/speed;
    const tx=-a*st*scale,ty=b*ct*scale;
    const tangent=[(1-weight)*(rp+offset)*(-su)+weight*(c*tx-s*ty),(1-weight)*(rp+offset)*cu+weight*(s*tx+c*ty)];
    const tl=Math.hypot(...tangent);
    return {position:[(1-weight)*(rp+offset)*cu+weight*(c*ex-s*ey),(1-weight)*(rp+offset)*su+weight*(s*ex+c*ey)],tangent:tangent.map(v=>v/tl)};
  }
  function deformVertex(position,normal,material,d,phase){
    if(!d)return {position:[...position],normal:[...normal]};
    const old=waveFrame(material,d,0,0),now=waveFrame(material,d,d.flexOffset+d.flexRate*phase,d.waveOffset+d.waveRate*phase);
    const oldT=old.tangent,newT=now.tangent,oldN=[oldT[1],-oldT[0]],newN=[newT[1],-newT[0]],along=normal[0]*oldT[0]+normal[1]*oldT[1],across=normal[0]*oldN[0]+normal[1]*oldN[1];
    return {position:[now.position[0]+d.center[0],now.position[1]+d.center[1],position[2]],normal:[along*newT[0]+across*newN[0],along*newT[1]+across*newN[1],normal[2]]};
  }
  async function decodeGeometry(data,buffer,id,cryptoAPI=globalThis.crypto){
    if(data.metadata?.id!==id)throw Error('Scene identity mismatch');
    if(data.metadata.format==='ratiolab-showcase/2'){
      if(data.geometryBuffer)throw Error('Unexpected geometry buffer');return data;
    }
    const info=data.geometryBuffer;
    if(data.metadata.format!=='ratiolab-showcase/3'||!info||info.uri!==id+'.bin'||info.byteOrder!=='little-endian'||!Number.isSafeInteger(info.byteLength)||info.byteLength<=0||!/^[a-f0-9]{64}$/.test(info.sha256)||Object.prototype.toString.call(buffer)!=='[object ArrayBuffer]'||buffer.byteLength!==info.byteLength||!Array.isArray(data.meshes))throw Error('Invalid geometry buffer');
    if(new Uint8Array(new Uint32Array([1]).buffer)[0]!==1)throw Error('Unsupported byte order');
    if(cryptoAPI?.subtle){const hash=Array.from(new Uint8Array(await cryptoAPI.subtle.digest('SHA-256',buffer)),v=>v.toString(16).padStart(2,'0')).join('');if(hash!==info.sha256)throw Error('Geometry checksum mismatch');}
    const ranges=[];
    const meshes=data.meshes.map(mesh=>{
      const views=mesh.bufferViews;if(!views||!['positions','normals','indices'].every(k=>Object.hasOwn(views,k))||Object.keys(views).some(k=>!['positions','normals','indices','materials'].includes(k)))throw Error('Invalid buffer fields');
      const decoded={...mesh};
      for(const [field,v]of Object.entries(views)){
        if(Object.hasOwn(mesh,field)||!v||v.componentType!==(field==='indices'?'uint32':'float32')||!Number.isSafeInteger(v.byteOffset)||v.byteOffset<0||v.byteOffset%4||!Number.isSafeInteger(v.length)||v.length<=0||!Number.isSafeInteger(v.length*4)||v.length*4>buffer.byteLength-v.byteOffset)throw Error('Invalid buffer view');
        ranges.push([v.byteOffset,v.byteOffset+v.length*4]);decoded[field]=field==='indices'?new Uint32Array(buffer,v.byteOffset,v.length):new Float32Array(buffer,v.byteOffset,v.length);
      }
      return decoded;
    });
    ranges.sort((a,b)=>a[0]-b[0]);if(ranges.some((r,i)=>i&&r[0]<ranges[i-1][1]))throw Error('Overlapping buffer views');
    return {...data,meshes};
  }
  const identity = () => [1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1];
  function mul(a, b) {
    const out = Array(16).fill(0);
    for (let c=0;c<4;c++) for(let r=0;r<4;r++) for(let k=0;k<4;k++) out[c*4+r]+=a[k*4+r]*b[c*4+k];
    return out;
  }
  function translate(v) { const m=identity(); m[12]=v[0];m[13]=v[1];m[14]=v[2];return m; }
  function rotate(axis, angle) {
    const length=Math.hypot(...axis),x=axis[0]/length,y=axis[1]/length,z=axis[2]/length,c=Math.cos(angle),s=Math.sin(angle),t=1-c;
    return [t*x*x+c,t*x*y+s*z,t*x*z-s*y,0,t*x*y-s*z,t*y*y+c,t*y*z+s*x,0,t*x*z+s*y,t*y*z-s*x,t*z*z+c,0,0,0,0,1];
  }
  function rotation(spin, phase) {
    return mul(translate(spin.pivot), mul(rotate(spin.axis, spin.rate*phase), translate(spin.pivot.map(v=>-v))));
  }
  function point(matrix, p) { return [0,1,2].map(i=>matrix[i]*p[0]+matrix[4+i]*p[1]+matrix[8+i]*p[2]+matrix[12+i]); }
  function transform(mesh, phase) {
    const d=mesh.transform;
    if(d.kind==='fixed') return identity();
    const spin=rotation(d.rotation, phase);
    if(d.kind!=='orbital') return spin;
    const orbit=point(rotation(d.orbit, phase),d.orbit.center);
    return mul(translate(orbit.map((v,i)=>v-d.orbit.center[i])),spin);
  }
  /* A successful selection commits model, metadata and ARIA together. Old resources
     remain active through network/upload failures. Every superseded request is invalidated. */
  function createSceneLoader({fetchScene, prepare, commit, release, report}) {
    const cache=new Map();let serial=0,controller=null,current=null;
    return {
      async select(id) {
        const request=++serial; controller?.abort();controller=new AbortController();
        const signal=controller.signal;let prepared=null;
        report('loading',id);
        try {
          const data=cache.has(id)?cache.get(id):await fetchScene(id,signal);
          if(request!==serial) return false;
          prepared=prepare(data,id);
          if(request!==serial){release(prepared);return false;}
          commit(prepared,id);
          const previous=current;current=prepared;cache.set(id,data);
          if(previous) release(previous);
          report('ready',id);return true;
        } catch(error) {
          if(prepared && prepared!==current) release(prepared);
          if(request===serial) report('error',id,error);
          return false;
        }
      },
      dispose() { ++serial;controller?.abort();if(current)release(current);current=null;cache.clear(); }
    };
  }
  function mount(win) {
    const doc=win.document,stage=doc.getElementById('mechanism-stage'),canvas=doc.getElementById('mechanism-canvas');
    const toggle=doc.querySelector('[data-motion-toggle]'),views=doc.querySelector('.view-controls');
    const tablist=doc.querySelector('[data-scene-tabs]'),tabs=tablist?[...tablist.querySelectorAll('[data-scene]')]:[];
    const panel=doc.getElementById('mechanism-panel'),status=doc.querySelector('[data-scene-status]'),scope=doc.querySelector('[data-scene-scope]');
    if(!stage||!canvas||!toggle||!tablist||!panel||!win.WebGLRenderingContext)return;
    const gl=canvas.getContext('webgl',{antialias:true,alpha:true});if(!gl)return;
    const reduced=win.matchMedia('(prefers-reduced-motion: reduce)');
    let frame=0,last=0,phase=0,paused=reduced.matches,inView=true,drag=null,yaw=-1,pitch=.72,active=null,lost=false;
    const fragment='precision mediump float;uniform vec3 uColor;varying vec3 vNormal;void main(){vec3 n=normalize(vNormal);float d=max(dot(n,normalize(vec3(0.45,-0.35,0.85))),0.0);float b=max(dot(n,normalize(vec3(-0.8,0.4,0.3))),0.0);gl_FragColor=vec4(uColor*(0.38+0.56*d+0.16*b),1.0);}';
    let program;const shaders=[];
    try {
      program=gl.createProgram();
      for(const [type,source] of [[gl.VERTEX_SHADER,vertexSource],[gl.FRAGMENT_SHADER,fragment]]){
        const s=gl.createShader(type);shaders.push(s);gl.shaderSource(s,source);gl.compileShader(s);
        if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error('Shader unavailable');gl.attachShader(program,s);
      }
      gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error('Renderer unavailable');
    }catch(_){if(program)gl.deleteProgram(program);shaders.forEach(s=>gl.deleteShader(s));return;}
    shaders.forEach(s=>gl.deleteShader(s));gl.useProgram(program);
    const attr={position:gl.getAttribLocation(program,'aPosition'),normal:gl.getAttribLocation(program,'aNormal'),material:gl.getAttribLocation(program,'aMaterial')};
    const uni=Object.fromEntries(['Model','View','Projection','Color','FlexShape','FlexBody','ArcFirst','ArcSecond','FlexCenter'].map(k=>[k.toLowerCase(),gl.getUniformLocation(program,'u'+k)]));
    const norm=v=>{const l=Math.hypot(...v)||1;return v.map(x=>x/l);};
    const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
    const dot=(a,b)=>a.reduce((v,x,i)=>v+x*b[i],0);
    function look(eye,target){const z=norm(eye.map((x,i)=>x-target[i])),x=norm(cross([0,0,1],z)),y=cross(z,x);return [x[0],y[0],z[0],0,x[1],y[1],z[1],0,x[2],y[2],z[2],0,-dot(x,eye),-dot(y,eye),-dot(z,eye),1];}
    function perspective(aspect,near,far){const f=1/Math.tan(Math.PI/7);return [f/aspect,0,0,0,0,f,0,0,0,0,(far+near)/(near-far),-1,0,0,2*far*near/(near-far),0];}
    function stop(){if(frame)win.cancelAnimationFrame(frame);frame=0;last=0;}
    function schedule(){if(!frame&&active&&!lost&&inView&&!doc.hidden)frame=win.requestAnimationFrame(render);}
    function render(time){
      frame=0;if(!active||lost||doc.hidden||!inView)return;
      const w=canvas.clientWidth,h=canvas.clientHeight;if(!w||!h)return;
      const pixel=Math.min(win.devicePixelRatio||1,2);
      if(canvas.width!==Math.round(w*pixel)||canvas.height!==Math.round(h*pixel)){canvas.width=Math.round(w*pixel);canvas.height=Math.round(h*pixel);}
      gl.viewport(0,0,canvas.width,canvas.height);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.enable(gl.DEPTH_TEST);
      if(!paused&&last)phase+=Math.min((time-last)/1000,.05)*.65;last=time;
      const {mid,extent,meshes}=active,dist=extent*Math.max(1.65,1.32/(w/h));
      const eye=[mid[0]+dist*Math.cos(pitch)*Math.cos(yaw),mid[1]+dist*Math.cos(pitch)*Math.sin(yaw),mid[2]+dist*Math.sin(pitch)];
      gl.uniformMatrix4fv(uni.view,false,new Float32Array(look(eye,mid)));gl.uniformMatrix4fv(uni.projection,false,new Float32Array(perspective(w/h,extent*.01,extent*12)));
      for(const mesh of meshes){
        const flex=deformationUniforms(mesh,phase);
        gl.uniform4fv(uni.flexshape,flex.flexShape);gl.uniform4fv(uni.flexbody,flex.flexBody);gl.uniform4fv(uni.arcfirst,flex.arcFirst);gl.uniform4fv(uni.arcsecond,flex.arcSecond);gl.uniform3fv(uni.flexcenter,flex.center);
        if(mesh.mb){gl.bindBuffer(gl.ARRAY_BUFFER,mesh.mb);gl.enableVertexAttribArray(attr.material);gl.vertexAttribPointer(attr.material,3,gl.FLOAT,false,0,0);}else{gl.disableVertexAttribArray(attr.material);gl.vertexAttrib3f(attr.material,0,0,0);}
        gl.uniformMatrix4fv(uni.model,false,new Float32Array(transform(mesh,phase)));gl.uniform3fv(uni.color,mesh.color||[.65,.8,.8]);
        gl.bindBuffer(gl.ARRAY_BUFFER,mesh.vb);gl.enableVertexAttribArray(attr.position);gl.vertexAttribPointer(attr.position,3,gl.FLOAT,false,0,0);
        gl.bindBuffer(gl.ARRAY_BUFFER,mesh.nb);gl.enableVertexAttribArray(attr.normal);gl.vertexAttribPointer(attr.normal,3,gl.FLOAT,false,0,0);
        gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,mesh.ib);gl.drawElements(gl.TRIANGLES,mesh.count,mesh.type,0);
      }
      if(!paused)schedule();
    }
    const vector=v=>Array.isArray(v)&&v.length===3&&v.every(Number.isFinite);
    function validSpin(s){return s&&vector(s.axis)&&Math.hypot(...s.axis)>0&&vector(s.pivot)&&Number.isFinite(s.rate);}
    const numericArray=v=>Array.isArray(v)||ArrayBuffer.isView(v)&&!(v instanceof DataView);
    function validDeformation(d){return d&&d.kind==='strain-wave'&&['flexRate','waveRate','flexOffset','waveOffset','pitchRadius','bodyLength','diaphragm'].every(k=>Number.isFinite(d[k]))&&d.pitchRadius>0&&d.bodyLength>0&&d.diaphragm>=0&&d.diaphragm<=d.bodyLength&&vector(d.center)&&Array.isArray(d.ellipseAxes)&&d.ellipseAxes.length===2&&d.ellipseAxes.every(v=>Number.isFinite(v)&&v>0)&&d.ellipseAxes[1]<=d.ellipseAxes[0]&&Array.isArray(d.arcCoefficients)&&d.arcCoefficients.length===8&&d.arcCoefficients.every(Number.isFinite);}

    function release(resource){resource.buffers.forEach(buffer=>gl.deleteBuffer(buffer));}
    function prepare(data,id){
      const m=data.metadata,b=data.bounds;
      if(!m||!['ratiolab-showcase/2','ratiolab-showcase/3'].includes(m.format)||m.id!==id||typeof m.title!=='string'||(!Number.isFinite(m.ratioMagnitude)||m.ratioMagnitude<=0)||typeof m.direction!=='string'||typeof m.scope!=='string'||!m.members||!['input','fixed','output'].every(k=>typeof m.members[k]==='string')||!Array.isArray(m.specs)||!m.specs.every(s=>typeof s.label==='string'&&typeof s.value==='string')||!b||!vector(b.min)||!vector(b.max)||!Array.isArray(data.meshes)||!data.meshes.length)throw Error('Invalid scene');
      const extent=Math.max(...b.max.map((v,i)=>v-b.min[i]));if(!(extent>0))throw Error('Invalid bounds');
      const resource={metadata:m,mid:b.min.map((v,i)=>(v+b.max[i])/2),extent,meshes:[],buffers:[]};
      function upload(target,values){const buffer=gl.createBuffer();if(!buffer)throw Error('GPU allocation failed');resource.buffers.push(buffer);gl.bindBuffer(target,buffer);gl.bufferData(target,values,gl.STATIC_DRAW);return buffer;}
      try{
        for(const mesh of data.meshes){
          const d=mesh.transform,positions=mesh.positions,normals=mesh.normals,indices=mesh.indices;
          if(!d||!['fixed','rigid','orbital'].includes(d.kind)||(d.kind!=='fixed'&&!validSpin(d.rotation))||(d.kind==='orbital'&&(!validSpin(d.orbit)||!vector(d.orbit.center)))||!numericArray(positions)||!positions.length||positions.length%3||!positions.every(Number.isFinite)||!numericArray(normals)||normals.length!==positions.length||!normals.every(Number.isFinite)||!numericArray(indices)||!indices.length||indices.length%3||!indices.every(i=>Number.isInteger(i)&&i>=0&&i<positions.length/3))throw Error('Invalid mesh');
          if(mesh.deformation&&(!validDeformation(mesh.deformation)||!numericArray(mesh.materials)||mesh.materials.length!==positions.length||!mesh.materials.every((v,i)=>Number.isFinite(v)&&(i%3!==2||v>=0&&v<=1))))throw Error('Invalid deformation');
          let max=0;for(const i of indices)max=Math.max(max,i);const large=max>65535;
          if(large&&!gl.getExtension('OES_element_index_uint'))throw Error('Mesh unsupported');
          const vb=upload(gl.ARRAY_BUFFER,new Float32Array(positions)),nb=upload(gl.ARRAY_BUFFER,new Float32Array(normals));
          const ib=upload(gl.ELEMENT_ARRAY_BUFFER,large?new Uint32Array(indices):new Uint16Array(indices));
          const mb=mesh.deformation?upload(gl.ARRAY_BUFFER,new Float32Array(mesh.materials)):null;
          if(gl.getError()!==gl.NO_ERROR)throw Error('GPU upload failed');
          resource.meshes.push({...mesh,vb,nb,ib,mb,type:large?gl.UNSIGNED_INT:gl.UNSIGNED_SHORT,count:indices.length});
        }
        return resource;
      }catch(error){release(resource);throw error;}
    }
    function text(tag,value,className){const el=doc.createElement(tag);el.textContent=value;if(className)el.className=className;return el;}
    function updateToggle(){toggle.setAttribute('aria-pressed',String(paused));toggle.replaceChildren(doc.createTextNode(paused?'Resume motion ':'Pause motion '),text('span',paused?'▶':'Ⅱ'));toggle.lastChild.setAttribute('aria-hidden','true');}
    function commit(resource,id){
      const m=resource.metadata;
      doc.querySelector('[data-scene-title]').textContent=m.title;
      doc.querySelector('[data-scene-ratio]').replaceChildren(doc.createTextNode(String(m.ratioMagnitude)),text('span',':1'));
      doc.querySelector('[data-scene-direction]').textContent=m.direction;
      const members=doc.querySelector('[data-scene-members]');members.replaceChildren();
      const annotations=doc.querySelector('.model-annotation');annotations.replaceChildren();
      for(const key of ['input','fixed','output']){
        const row=text('div','');row.append(text('span',key.toUpperCase()),text('strong',m.members[key]));members.append(row);
        const note=text('div','');note.append(text('span',key.toUpperCase()),text('strong',m.members[key]));annotations.append(note);
      }
      const specs=doc.querySelector('[data-scene-specs]');specs.replaceChildren();
      m.specs.forEach(s=>{const row=text('div','');row.append(text('span',s.label),text('strong',s.value));specs.append(row);});
      scope.textContent=m.scope+' This is a precomputed illustration, not a browser CAD tool.';scope.hidden=false;
      canvas.setAttribute('aria-label',m.title+' generated by RatioLab. Drag or use arrow keys to orbit. '+m.direction+'.');
      tabs.forEach(t=>t.setAttribute('aria-selected',String(t.dataset.scene===id)));
      panel.setAttribute('role','tabpanel');panel.setAttribute('aria-labelledby','scene-tab-'+id);panel.removeAttribute('aria-label');
      phase=0;last=0;active=resource;stage.classList.add('model-ready');canvas.setAttribute('tabindex','0');toggle.hidden=false;views.hidden=false;updateToggle();schedule();
    }
    const loader=createSceneLoader({
      fetchScene:async(id,signal)=>{
        const response=await win.fetch('assets/'+id+'.json',{signal,cache:'no-cache'});if(!response.ok)throw Error('Scene unavailable');const data=await response.json();
        let buffer;
        if(data.geometryBuffer){if(data.geometryBuffer.uri!==id+'.bin')throw Error('Invalid geometry location');const binary=await win.fetch('assets/'+id+'.bin',{signal,cache:'no-cache'});if(!binary.ok)throw Error('Geometry unavailable');buffer=await binary.arrayBuffer();}
        return decodeGeometry(data,buffer,id,win.crypto);
      },
      prepare,commit,release,
      report(state,id){
        panel.setAttribute('aria-busy',String(state==='loading'));
        status.classList.toggle('sr-only',state==='ready');status.classList.toggle('is-error',state==='error');status.classList.toggle('is-loading',state==='loading');
        const name=tabs.find(t=>t.dataset.scene===id)?.textContent.trim()||id;
        status.textContent=state==='loading'?'Loading '+name+'…':state==='ready'?name+' ready.':name+' could not be loaded. '+(active?'The previous model is still shown. ':'')+'Select it again to retry.';
      }
    });
    tablist.hidden=false;
    tabs.forEach((tab,index)=>{
      tab.addEventListener('click',()=>{tabs.forEach(t=>t.tabIndex=t===tab?0:-1);loader.select(tab.dataset.scene);});
      tab.addEventListener('keydown',event=>{
        let next;
        if(event.key==='ArrowRight')next=(index+1)%tabs.length;else if(event.key==='ArrowLeft')next=(index+tabs.length-1)%tabs.length;else if(event.key==='Home')next=0;else if(event.key==='End')next=tabs.length-1;else return;
        event.preventDefault();tabs.forEach((t,i)=>t.tabIndex=i===next?0:-1);tabs[next].focus();tabs[next].scrollIntoView({block:'nearest',inline:'nearest',behavior:'instant'});
      });
    });
    function clearView(){views.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed','false'));}
    views.addEventListener('click',event=>{const b=event.target.closest('[data-view]');if(!b)return;yaw=-1;pitch=b.dataset.view==='top'?1.52:.72;clearView();b.setAttribute('aria-pressed','true');schedule();});
    canvas.addEventListener('pointerdown',e=>{drag=[e.clientX,e.clientY];canvas.setPointerCapture(e.pointerId);});
    canvas.addEventListener('pointermove',e=>{if(!drag)return;yaw-=(e.clientX-drag[0])*.008;pitch=Math.max(.12,Math.min(1.52,pitch+(e.clientY-drag[1])*.008));drag=[e.clientX,e.clientY];clearView();schedule();});
    ['pointerup','pointercancel','lostpointercapture'].forEach(name=>canvas.addEventListener(name,()=>{drag=null;}));
    canvas.addEventListener('keydown',e=>{if(e.key==='ArrowLeft')yaw-=.1;else if(e.key==='ArrowRight')yaw+=.1;else if(e.key==='ArrowUp')pitch=Math.min(1.52,pitch+.1);else if(e.key==='ArrowDown')pitch=Math.max(.12,pitch-.1);else return;e.preventDefault();clearView();schedule();});
    toggle.addEventListener('click',()=>{paused=!paused;stop();updateToggle();schedule();});
    reduced.addEventListener('change',event=>{if(event.matches){paused=true;stop();updateToggle();schedule();}});
    doc.addEventListener('visibilitychange',()=>{if(doc.hidden)stop();else schedule();});
    if('IntersectionObserver' in win)new win.IntersectionObserver(entries=>{inView=entries[0].isIntersecting;if(inView)schedule();else stop();},{threshold:0}).observe(stage);
    if('ResizeObserver' in win)new win.ResizeObserver(schedule).observe(stage);else win.addEventListener('resize',schedule);
    canvas.addEventListener('webglcontextlost',event=>{event.preventDefault();lost=true;stop();loader.dispose();active=null;stage.classList.remove('model-ready');toggle.hidden=true;views.hidden=true;tablist.hidden=true;scope.hidden=true;canvas.removeAttribute('tabindex');panel.setAttribute('aria-busy','false');panel.setAttribute('role','region');panel.setAttribute('aria-label','RatioLab workspace preview');panel.removeAttribute('aria-labelledby');status.textContent='3D is unavailable. The desktop workspace screenshot is shown.';});
    loader.select('planetary');
  }
  return {transform,point,createSceneLoader,mount,decodeGeometry,vertexSource,deformationUniforms,deformVertex,waveFrame};
});
