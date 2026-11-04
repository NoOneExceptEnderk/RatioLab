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
  constructor(tag='div'){super();this.tagName=tag.toUpperCase();this.children=[];this.dataset={};this.attributes={};this.value='';this.hidden=false;this.disabled=false;this.isConnected=true;this.style={};this.classList={values:new Set(),toggle(k){if(this.values.has(k)){this.values.delete(k);return false;}this.values.add(k);return true;},remove(k){this.values.delete(k);},contains(k){return this.values.has(k);}};}
  append(...nodes){for(const n of nodes){if(n.parent){const i=n.parent.children.indexOf(n);if(i>=0)n.parent.children.splice(i,1);}n.parent=this;this.children.push(n);}}
  replaceChildren(...nodes){this.children=[];this.append(...nodes);}
  querySelector(selector){return this.children.find(c=>c.tagName===selector.toUpperCase())??null;}
  closest(){return this;}
  contains(other){return other===this || this.children.some(c=>c.contains(other));}
  setAttribute(key,value){this.attributes[key]=String(value);}
  getAttribute(key){return this.attributes[key];}
  getContext(){return gl;}
  getBoundingClientRect(){return {left:20,right:320,top:80,width:300,height:260};}
  focus(){document.activeElement=this;}
  querySelectorAll(selector){return this.children.filter(child=>selector==='[role=tab]' && child.getAttribute('role')==='tab');}
  setPointerCapture(){}
  click(){if(!this.disabled)this.dispatchEvent(new Event('click'));}
}
const nodes=new Map();
const el=id=>{if(!nodes.has(id))nodes.set(id,new Element(id==='model-canvas'?'canvas':'div'));return nodes.get(id);};
const parameterTabs=new Element(),tabButtons=['dimensions','motion','assembly'].map(name=>{const button=el('tab-'+name);button.dataset.tab=name;button.setAttribute('role','tab');button.setAttribute('aria-selected',String(name==='dimensions'));button.tabIndex=name==='dimensions'?0:-1;return button;});parameterTabs.append(...tabButtons);

globalThis.document=Object.assign(new EventTarget(),{
  getElementById:id=>id.startsWith('viewport-')?null:el(id),
  createElement:tag=>new Element(tag),querySelectorAll:selector=>selector==='[data-tab]'?tabButtons:selector==='[role=tablist]'?[parameterTabs]:[],body:new Element('body'),documentElement:{dataset:{},clientWidth:1280,style:{setProperty(){}}},
});
globalThis.window=Object.assign(new EventTarget(),{innerHeight:800});
const preferencesStorage=new Map();let preferenceWrites=0;
globalThis.localStorage={getItem:key=>preferencesStorage.get(key)??null,setItem:(key,value)=>{preferenceWrites++;preferencesStorage.set(key,value);}};
globalThis.ResizeObserver=class{observe(){}disconnect(){}};
globalThis.requestAnimationFrame=()=>0;globalThis.cancelAnimationFrame=()=>{};
const modules={};
const languageModule = new vm.SourceTextModule('export const LANGUAGES={}; export async function initLanguage(){return {setLanguage(){}};}');
await languageModule.link(()=>{}); await languageModule.evaluate();
modules['./ui-language.js']=languageModule;

for(const name of ['document','viewer','preferences']){
  const module=modules['./'+name+'.js']=new vm.SourceTextModule(fs.readFileSync(root+'webapp/'+name+'.js','utf8'));
  await module.link(()=>{throw Error('Unexpected module dependency');});await module.evaluate();
}
function dependency(name,value){return new vm.SyntheticModule([name],function(){this.setExport(name,value);});}
modules['./engine-client.js']=dependency('EngineClient',class{});
modules['./tools.js']=dependency('initTools',()=>{});

modules['./model-catalog.js']=new vm.SyntheticModule(['initModelCatalog','selectionSummary'],function(){this.setExport('initModelCatalog',()=>{});this.setExport('selectionSummary',()=> '');});
modules['./choice-menu.js']=dependency('initChoiceMenus',()=>({close(){}}));
// Keep the actual setup, camera listeners and all renderer handlers. Suppress
// only worker boot: camera commands do not depend on a calculation result.
const source=fs.readFileSync(root+'webapp/app.js','utf8').replace(/setup\(\);\s*$/,'boot=()=>{}; setup();');
// The general Help button and its cancelled guide are absent; the actual
// parameter/section question-guide handlers below remain exercised.
assert.doesNotMatch(fs.readFileSync(root+'webapp/index.html','utf8'),/id=["']help["']/);
assert.doesNotMatch(source,/function showHelp|app-guide\.json|guideResources/);
const app=new vm.SourceTextModule(source+'\nexport {bindParameterHelp,showParameterHelp,closeParameterHelp,changePreference};');await app.link(path=>modules[path]);await app.evaluate();
const viewer=globalThis.ratiolab.viewer,canvas=el('model-canvas');
// The final layout is Model/family/variant, then one horizontal tablist,
// then the one real form. Navigation edits no model/history/camera state.
const html=fs.readFileSync(root+'webapp/index.html','utf8');
assert.ok(html.indexOf('id="family"')<html.indexOf('class="parameter-tabs"'));
assert.ok(html.indexOf('class="parameter-tabs"')<html.indexOf('id="parameters"'));
assert.doesNotMatch(html,/data-parameter-section=|name="parameter-sections"/);
assert.equal((html.match(/id="parameters"/g)??[]).length,1);
for(const name of ['dimensions','motion','assembly'])assert.doesNotMatch(html,new RegExp('<button id="tab-'+name+'"[^>]*\\bhidden\\b'));
const savedTabsDocument=structuredClone(globalThis.ratiolab.document.state),savedTabsHistory=structuredClone(globalThis.ratiolab.document.past),savedTabsCamera={yaw:viewer.yaw,pitch:viewer.pitch,zoom:viewer.zoom};
function selectedTab(name){for(const button of tabButtons){const active=button.dataset.tab===name;assert.equal(button.getAttribute('aria-selected'),String(active));assert.equal(button.tabIndex,active?0:-1);assert.equal(button.hidden,false);}assert.equal(el('parameters').getAttribute('aria-labelledby'),'tab-'+name);}
tabButtons[1].click();selectedTab('motion');tabButtons[1].focus();
for(const [key,name]of [['ArrowRight','assembly'],['Home','dimensions'],['End','assembly'],['ArrowRight','dimensions']]){const event=new Event('keydown',{cancelable:true});event.key=key;parameterTabs.dispatchEvent(event);assert.equal(event.defaultPrevented,true);selectedTab(name);assert.equal(document.activeElement.dataset.tab,name);}
el('motion-io').click();selectedTab('motion');
assert.deepEqual(globalThis.ratiolab.document.state,savedTabsDocument);assert.deepEqual(globalThis.ratiolab.document.past,savedTabsHistory);assert.deepEqual({yaw:viewer.yaw,pitch:viewer.pitch,zoom:viewer.zoom},savedTabsCamera);

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
function pointer(type,x,y,button=0){const event=new Event(type);Object.assign(event,{button,pointerId:1,clientX:x,clientY:y});canvas.dispatchEvent(event);}
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
// The same panel switches content without touching camera, phase, or selection.
el('tool-dock').hidden=true;el('view-panel').hidden=true;viewer.selected=new Set([2]);el('top-view').click();key('+');
const camera={yaw:viewer.yaw,pitch:viewer.pitch,zoom:viewer.zoom};
el('open-view-panel').click();assert.equal(el('view-panel').hidden,false);assert.equal(el('tool-dock').hidden,true);
assert.equal(el('open-view-panel').getAttribute('aria-expanded'),'true');
el('open-tools-panel').click();assert.equal(el('view-panel').hidden,true);assert.equal(el('tools-menu-extension').hidden,false);
el('expand-tool-dock').click();assert.equal(el('expand-tool-dock').getAttribute('aria-pressed'),'true');
el('close-tool-dock').click();assert.equal(el('tool-dock').hidden,true);assert.equal(el('open-tools-panel').getAttribute('aria-expanded'),'false');
assert.deepEqual({yaw:viewer.yaw,pitch:viewer.pitch,zoom:viewer.zoom},camera);assert.deepEqual([...viewer.selected],[2]);

// Right drag is pan, never orbit or surface selection. Fit restores framing;
// camera target changes must feed the same inverse projection used for picking.
const nav=modules['./viewer.js'].namespace;
const allDirections=[];
for(let x=-1;x<=1;x++)for(let y=-1;y<=1;y++)for(let z=-1;z<=1;z++)if(x||y||z)allDirections.push([x,y,z]);
for(const d of allDirections){viewer.orient(d);const q=viewer.projectVector(d);assert.ok(Math.abs(q[0])<1e-12&&Math.abs(q[1])<1e-12&&q[2]>0);}
el('cube-home').click();const beforePan={yaw:viewer.yaw,pitch:viewer.pitch};let picks=0;viewer.addEventListener('surfaceclick',()=>picks++);
pointer('pointerdown',100,100,2);pointer('pointermove',145,125,2);pointer('pointerup',145,125,2);
assert.deepEqual({yaw:viewer.yaw,pitch:viewer.pitch},beforePan);assert.ok(viewer.panOffset.some(v=>v!==0));assert.equal(picks,0);
const target=viewer.cameraCenter,ray=nav.cameraRay({yaw:viewer.yaw,pitch:viewer.pitch,center:target,radius:viewer.radius,zoom:viewer.zoom,width:300,height:260},0,0);
assert.deepEqual(ray.ray_origin.map((v,i)=>Math.round((v+ray.ray_direction[i]*viewer.radius*4-target[i])*1e8)||0),[0,0,0]);
el('cube-fit').click();assert.deepEqual(viewer.panOffset,[0,0,0]);assert.deepEqual({yaw:viewer.yaw,pitch:viewer.pitch},beforePan);
const contextMenu=new Event('contextmenu',{cancelable:true});canvas.dispatchEvent(contextMenu);assert.equal(contextMenu.defaultPrevented,true);
el('pan-view').click();assert.equal(viewer.panMode,true);pointer('pointerdown',10,10);pointer('pointermove',30,20);pointer('pointerup',30,20);assert.equal(picks,0);
el('pan-view').click();el('cube-home').click();assert.deepEqual(viewer.panOffset,[0,0,0]);

// Hover intent, crossing to the pane, expansion, and pointer departure use
// real controller handlers with a deterministic clock (not timing sleeps).
const timers=new Map();let timerId=0;
globalThis.setTimeout=(fn,delay)=>{timers.set(++timerId,{fn,delay});return timerId;};
globalThis.clearTimeout=id=>timers.delete(id);
function advance(delay){for(const [id,t]of [...timers])if(t.delay<=delay){timers.delete(id);t.fn();}}
const anchor=new Element(),trigger=new Element('button');anchor.append(trigger);trigger.closest=()=>anchor;
app.namespace.bindParameterHelp(anchor,{help:{title:'Module',meaning:'Tooth size.',effect:'Sets pitch dimensions.',diagram_url:'diagram.svg'}},trigger,{clickToOpen:true});
anchor.dispatchEvent(new Event('pointerenter'));assert.equal(document.body.children.length,0);advance(249);assert.equal(document.body.children.length,0);advance(250);
const pane=document.body.children[0];assert.equal(pane.hidden,false);assert.equal(trigger.getAttribute('aria-expanded'),'true');
anchor.dispatchEvent(new Event('pointerleave'));pane.dispatchEvent(new Event('pointerenter'));advance(220);assert.equal(pane.hidden,false);
const expand=pane.children[1].children.find(c=>c.tagName==='BUTTON');expand.click();assert.equal(pane.classList.contains('expanded'),true);
pane.dispatchEvent(new Event('pointerleave'));advance(220);assert.equal(pane.hidden,true);assert.equal(trigger.getAttribute('aria-expanded'),'false');
trigger.click();assert.equal(pane.hidden,false);app.namespace.closeParameterHelp();assert.equal(pane.hidden,true);
const f1=new Event('keydown',{cancelable:true});f1.key='F1';anchor.dispatchEvent(f1);assert.equal(f1.defaultPrevented,true);assert.equal(pane.hidden,false);
// Keyboard origin survives incidental pointerleave caused by pane expansion,
// text scaling or repositioning. A real focus departure still dismisses it.
pane.dispatchEvent(new Event('pointerleave'));advance(220);assert.equal(pane.hidden,false);
const keyboardExpand=pane.children[1].children.find(c=>c.tagName==='BUTTON');keyboardExpand.click();
pane.dispatchEvent(new Event('pointerleave'));anchor.dispatchEvent(new Event('pointerleave'));advance(220);assert.equal(pane.hidden,false);
const focusDeparture=new Event('focusout');focusDeparture.relatedTarget=new Element('input');pane.dispatchEvent(focusDeparture);advance(220);assert.equal(pane.hidden,true);
anchor.dispatchEvent(f1);assert.equal(pane.hidden,false);

const escape=new Event('keydown');escape.key='Escape';document.dispatchEvent(escape);assert.equal(pane.hidden,true);
// Explicit dismissal suppresses hover reopening until the anchor is left.
anchor.dispatchEvent(new Event('pointerenter'));advance(250);assert.equal(pane.hidden,true);
anchor.dispatchEvent(new Event('pointerleave'));anchor.dispatchEvent(new Event('pointerenter'));advance(250);assert.equal(pane.hidden,false);
const leaveTouch=new Event('pointerleave');leaveTouch.pointerType='touch';anchor.dispatchEvent(leaveTouch);advance(220);assert.equal(pane.hidden,false);
const outside=new Event('pointerdown');document.dispatchEvent(outside);assert.equal(pane.hidden,true);
// Closing keyboard help must not leave a stale activation origin that prevents
// a later fast hover departure from cancelling the pending intent timer.
anchor.dispatchEvent(f1);document.dispatchEvent(escape);assert.equal(pane.hidden,true);
anchor.dispatchEvent(new Event('pointerenter'));advance(100);
anchor.dispatchEvent(new Event('pointerleave'));advance(250);assert.equal(pane.hidden,true);

// Promotion to the whole parameter removes the icon wrapper's old listeners.
const wrapper=new Element(),promoted=new Element(),promotedTrigger=new Element('button');wrapper.append(promotedTrigger);promoted.append(wrapper);
app.namespace.bindParameterHelp(wrapper,{help:{title:'Old'}},promotedTrigger,{clickToOpen:true});
app.namespace.bindParameterHelp(promoted,{help:{title:'Promoted'}},promotedTrigger,{clickToOpen:true});
wrapper.dispatchEvent(new Event('pointerenter'));advance(250);assert.equal(pane.hidden,true);
promotedTrigger.click();assert.equal(pane.hidden,false);assert.equal(pane.children[0].children[0].textContent,'Promoted');
app.namespace.closeParameterHelp();
// A late illustration response cannot append content to another parameter.
let resolveAsset;globalThis.fetch=()=>new Promise(resolve=>{resolveAsset=resolve;});
const late=new Element(),lateTrigger=new Element('button');late.append(lateTrigger);
app.namespace.bindParameterHelp(late,{help:{title:'Late',diagram_context:'test/context'}},lateTrigger,{clickToOpen:true});lateTrigger.click();
trigger.click();const latestBody=pane.children[1],initialCount=latestBody.children.length;
resolveAsset({ok:true,json:async()=>({format:'ratiolab-help-illustrations/1',entries:{'test/context':'hash'},images:{hash:'data:image/png;base64,cHJvYmU='}})});
await new Promise(resolve=>setImmediate(resolve));assert.equal(latestBody.children.length,initialCount);
app.namespace.closeParameterHelp();
// Global preferences use the actual controls without editing a project,
// moving its camera, or replacing geometry/selection.
const beforePreferences=structuredClone(globalThis.ratiolab.document.state);
const beforeCamera={yaw:viewer.yaw,pitch:viewer.pitch,zoom:viewer.zoom};
const beforeMeshes=viewer.meshes,beforeSelection=[...viewer.selected];
assert.equal(preferenceWrites,0,'Startup only reads preferences');
el('theme-toggle').click();
assert.equal(el('theme-toggle').getAttribute('aria-checked'),'true');
app.namespace.changePreference('language','it');
assert.equal(preferenceWrites,2);
assert.equal(document.documentElement.dataset.theme,'light');
assert.deepEqual(globalThis.ratiolab.document.state,beforePreferences);
assert.deepEqual({yaw:viewer.yaw,pitch:viewer.pitch,zoom:viewer.zoom},beforeCamera);
assert.equal(viewer.meshes,beforeMeshes);assert.deepEqual([...viewer.selected],beforeSelection);
assert.equal(JSON.parse(preferencesStorage.get('ratiolab.web.preferences.v1')).language,'it');
localStorage.setItem=()=>{throw Error('Storage full');};el('theme-toggle').click();
assert.equal(el('theme-toggle').getAttribute('aria-checked'),'false');
assert.equal(document.documentElement.dataset.theme,'dark');assert.equal(el('preference-error').hidden,false);
viewer.dispose();
console.log('Camera Fit, keyboard orbit and named-view state checks passed.');
console.log('Studio overlay and parameter hover lifecycle checks passed.');
console.log('Theme/language preference persistence and document isolation checks passed.');
