// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
// Exercise the actual app scheduler with delayed canonical worker responses.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {webModules} from './webapp_modules.mjs';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
class Custom extends Event {constructor(type,{detail}={}){super(type);this.detail=detail;}}
globalThis.CustomEvent=Custom;
class Element {
  constructor(){this.value='';this.dataset={};this.style={setProperty(key,value){this[key]=value;}};this.disabled=false;this.hidden=false;this.className='';}
  setAttribute(){}
  getAnimations(){return [];}
  querySelectorAll(){return [];}
}
const nodes=new Map();const el=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);};
globalThis.document=Object.assign(new EventTarget(),{getElementById:el,querySelectorAll:()=>[],activeElement:null});
globalThis.localStorage={getItem:()=>null};
let nextFrame=0;globalThis.requestAnimationFrame=()=>++nextFrame;globalThis.cancelAnimationFrame=()=>{};
const {modules,load}=webModules(root);
for(const name of ['document','preferences','settings','controls','themes'])await load('./'+name+'.js');
const stub=values=>new vm.SyntheticModule(Object.keys(values),function(){for(const [key,value] of Object.entries(values))this.setExport(key,value);});
Object.assign(modules,{
  './engine-client.js':stub({EngineClient:class{}}),'./viewer.js':stub({ModelViewer:class{}}),
  './tools.js':stub({initTools(){}}),'./model-catalog.js':stub({initModelCatalog(){},selectionSummary(){return '';}}),
  './choice-menu.js':stub({initChoiceMenus(){}}),'./ui-language.js':stub({LANGUAGES:{},initLanguage(){}})
});
let source=fs.readFileSync(root+'webapp/app.js','utf8').replace(/setup\(\);\s*$/,'');
source+=`\nrenderFields=()=>{};renderMetrics=()=>{};renderInspection=()=>{};applyFieldErrors=()=>{};
export {tick,editSpeed,commitRates,scrubPreviewPhase,doc,syncMotionControl,previewSpeed,commitSpeedPreview,cancelSpeedPreview};
export function initialize(transport){
 startup=true;schema={fields:[{key:'input_rpm',label:'Input speed',default:60,minimum:-100000,maximum:100000}],options:[]};
 doc.replace('parallel',schema,{input_rpm:60});previousRevision=doc.revision;
 engine=transport;fatal=false;busy=false;generationRunning=false;schemaPending=false;analysisActive=false;
 clearTimeout(generationTimer);rateEditing=false;ratePending=false;rateCompletion=null;sliderRateQueued=false;speedSliderActive=false;speedSliderPreview=null;speedSliderKeyActive=false;
 poseCompletion=Promise.resolve();posePending=false;scrubTarget=null;scrubCompletion=null;
 design={family:'parallel',design_id:1,values:{input_rpm:60},motion:{supported:true,phase_radians_per_second:1,rates:{0:1},angular_rates:{},coordinates:[]},parts:[]};
 viewer={design,frames:[],render(){},applyFrame(frame){this.frames.push(frame);this.frame=frame;}};
 phase=0;lastTick=0;playing=true;validToken=doc.token();rememberSourceParameters();startup=false;
}
doc.addEventListener('change',onDocumentChange);
export function state(){return {phase,design,posePending,ratePending,rateEditing,viewer};}
export function slider(active){speedSliderActive=active;}
`;
const app=new vm.SourceTextModule(source);await app.link(path=>modules[path]);await app.evaluate();const a=app.namespace;
const settle=()=>new Promise(resolve=>setImmediate(resolve));
const gates=[];let canonical={input_rpm:60};let designId=1;
const engine={request(method,payload){return new Promise(resolve=>gates.push({method,payload,resolve}));}};
function release(){const g=gates.shift();assert.ok(g);if(g.method==='pose')g.resolve({frames:[{phase:g.payload.phases[0],parts:[]}]});else{canonical={...canonical,...g.payload.rpm_patch};g.resolve({design_id:++designId,values:{...canonical},ports:[],buffers:[],motion:{supported:true,phase_radians_per_second:1,rates:{0:1},angular_rates:{},coordinates:[]}});}return g;}
a.initialize(engine);el('playback-speed').value='1';
// A 60 Hz display must no longer skip every alternate frame. No backlog when
// the worker takes longer than a frame, and no independent interpolated pose.
a.tick(100);assert.equal(gates.length,0);
a.tick(100+1000/60);assert.equal(gates.length,1);assert.equal(a.state().posePending,true);
a.tick(100+2000/60);assert.equal(gates.length,1);release();await settle();
a.tick(150);assert.equal(gates.length,1);release();await settle();
assert.ok(a.state().phase>0);assert.equal(a.state().viewer.frames.length,2);
// Rapid input retains the pointer position, accepts new revisions while a rate
// request is pending, and commits only the last queued value without geometry.
a.initialize(engine);a.slider(true);el('rpm-slider').value='2.345';
a.editSpeed(12);await settle();assert.equal(gates[0].method,'rates');
a.editSpeed(30);a.editSpeed(45);assert.equal(el('rpm-slider').disabled,false);assert.equal(el('rpm-slider').value,'2.345');
const draining=a.commitRates();release();await settle();assert.equal(gates.length,1);assert.equal(gates[0].payload.rpm_patch.input_rpm,45);
release();await draining;assert.equal(a.state().design.values.input_rpm,45);assert.equal(a.state().rateEditing,false);assert.equal(gates.length,0);
a.tick(performance.now()+1000/60);assert.equal(gates.length,1);release();await settle();
// A delayed phase reply must never overwrite the newest scrub target.
a.initialize(engine);el('phase-range').value=String(.5*180/Math.PI);const scrub=a.scrubPreviewPhase();await settle();
el('phase-range').value=String(1.5*180/Math.PI);a.scrubPreviewPhase();release();await settle();assert.equal(gates.length,1);assert.equal(gates[0].payload.phases[0],1.5);
el('phase-range').value=String(2.5*180/Math.PI);a.scrubPreviewPhase();release();await settle();assert.equal(gates[0].payload.phases[0],2.5);
release();await scrub;assert.equal(a.state().phase,2.5);assert.equal(gates.length,0);
// Returning a typed draft to the same RPM through the slider still confirms it.
a.initialize(engine);a.doc.editNumber('input_rpm','60');assert.equal(a.state().rateEditing,true);
a.editSpeed(60);const confirm=a.commitRates();await settle();assert.equal(gates[0].method,'rates');release();await confirm;
assert.equal(a.state().rateEditing,false);
// Dragging is presentation only until release, including on a moving model.
a.initialize(engine);el('rpm-slider').value='2.345';
const revision=a.doc.revision,history=a.doc.past.length;
for(const value of [12,30,45])a.previewSpeed(value);
assert.equal(el('motion-rpm').value,'45');assert.equal(a.doc.revision,revision);
assert.equal(a.state().design.values.input_rpm,60);assert.equal(gates.length,0);
a.syncMotionControl();assert.equal(el('motion-rpm').value,'45');
a.commitSpeedPreview();const released=a.commitRates();await settle();
assert.equal(gates.length,1);assert.equal(gates[0].payload.rpm_patch.input_rpm,45);
release();await released;assert.equal(a.doc.revision,revision+1);assert.equal(a.doc.past.length,history+1);
a.previewSpeed(-15);a.commitSpeedPreview();const secondDrag=a.commitRates();await settle();release();await secondDrag;
assert.equal(a.doc.past.length,history+2);
a.previewSpeed(100);a.cancelSpeedPreview();assert.equal(el('motion-rpm').value,'-15');assert.equal(a.doc.revision,revision+2);assert.equal(gates.length,0);
console.log('Motion cadence, bounded rate queue and latest scrub checks passed.');
