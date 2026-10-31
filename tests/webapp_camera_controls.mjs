// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
// Actual app setup and ModelViewer handlers with DOM/WebGL doubles.
// These assertions cover camera commands and UI state, not browser rendering.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
class Custom extends Event {constructor(type,{detail}={}){super(type);this.detail=detail;}}
globalThis.CustomEvent=Custom;
const gl=new Proxy({getShaderParameter:()=>true,getProgramParameter:()=>true,createShader:()=>({}),createProgram:()=>({})},{get:(o,k)=>k in o?o[k]:()=>{}});
class Element extends EventTarget {
  constructor(tag='div'){super();this.tagName=tag.toUpperCase();this.children=[];this.dataset={};this.attributes={};this.value='';this.hidden=false;this.disabled=false;}
  setAttribute(key,value){this.attributes[key]=String(value);}
  getAttribute(key){return this.attributes[key];}
  getContext(){return gl;}
  getBoundingClientRect(){return {left:0,top:0,width:640,height:480};}
  focus(){}
  setPointerCapture(){}
  click(){if(!this.disabled)this.dispatchEvent(new Event('click'));}
}
const nodes=new Map();
const el=id=>{if(!nodes.has(id))nodes.set(id,new Element(id==='model-canvas'?'canvas':'div'));return nodes.get(id);};
globalThis.document=Object.assign(new EventTarget(),{
  getElementById:id=>id.startsWith('viewport-')?null:el(id),
  createElement:tag=>new Element(tag),querySelectorAll:()=>[],
});
globalThis.window=new EventTarget();
globalThis.localStorage={getItem:()=>null};
globalThis.ResizeObserver=class{observe(){}disconnect(){}};
const modules={};
for(const name of ['document','viewer']){
  const module=modules['./'+name+'.js']=new vm.SourceTextModule(fs.readFileSync(root+'webapp/'+name+'.js','utf8'));
  await module.link(()=>{throw Error('Unexpected module dependency');});await module.evaluate();
}
function dependency(name,value){return new vm.SyntheticModule([name],function(){this.setExport(name,value);});}
modules['./engine-client.js']=dependency('EngineClient',class{});
modules['./tools.js']=dependency('initTools',()=>{});
// Keep the actual setup, camera listeners and all renderer handlers. Suppress
// only worker boot: camera commands do not depend on a calculation result.
const source=fs.readFileSync(root+'webapp/app.js','utf8').replace(/setup\(\);\s*$/,'boot=()=>{}; setup();');
const app=new vm.SourceTextModule(source);await app.link(path=>modules[path]);await app.evaluate();
const viewer=globalThis.ratiolab.viewer,canvas=el('model-canvas');
const names=[['isometric-view','isometric'],['top-view','top'],['front-view','front']];
function named(name){
  assert.equal(el('view-label').textContent,name.toUpperCase());
  for(const [id,key]of names)assert.equal(el(id).getAttribute('aria-pressed'),String(key===name));
}
function custom(){
  assert.equal(el('view-label').textContent,'CUSTOM VIEW');
  for(const [id]of names)assert.equal(el(id).getAttribute('aria-pressed'),'false');
}
function key(key){const event=new Event('keydown',{cancelable:true});event.key=key;canvas.dispatchEvent(event);return event;}
function pointer(type,x,y){const event=new Event(type);Object.assign(event,{button:0,pointerId:1,clientX:x,clientY:y});canvas.dispatchEvent(event);}
function fitted(){assert.equal(viewer.zoom,1);assert.equal(viewer.yaw,-35*Math.PI/180);assert.equal(viewer.pitch,-55*Math.PI/180);named('isometric');}

// Named buttons retain zoom, while Fit resets both zoom and orientation.
el('top-view').click();named('top');key('+');assert.equal(viewer.zoom,1.15);
el('front-view').click();named('front');assert.equal(viewer.zoom,1.15);
el('isometric-view').click();named('isometric');assert.equal(viewer.zoom,1.15);
el('top-view').click();el('fit-view').click();fitted();

// Both F variants share Fit's state change, including the visible named view.
for(const letter of ['f','F']){el('top-view').click();key('+');key(letter);fitted();}

// Each orbit key revokes TOP and marks the same custom state as pointer drag.
for(const [arrow,yaw,pitch]of [['ArrowLeft',-.12,0],['ArrowRight',.12,0],['ArrowUp',0,-.12],['ArrowDown',0,.12]]){
  el('top-view').click();const event=key(arrow);
  assert.equal(event.defaultPrevented,true);assert.equal(viewer.yaw,yaw);assert.equal(viewer.pitch,pitch);custom();
  assert.equal(viewer.zoom,1);
}
el('top-view').click();pointer('pointerdown',10,10);pointer('pointermove',20,20);pointer('pointerup',20,20);custom();
el('fit-view').click();fitted();

// Zoom alone preserves the named orientation; camera commands stay blocked
// during an export capture just as before.
el('top-view').click();key('=');named('top');key('-');assert.equal(viewer.zoom,1);named('top');
viewer.captureBusy=true;key('f');key('ArrowLeft');assert.equal(viewer.yaw,0);assert.equal(viewer.pitch,0);named('top');viewer.captureBusy=false;
viewer.dispose();
console.log('Camera Fit, keyboard orbit and named-view state checks passed.');
