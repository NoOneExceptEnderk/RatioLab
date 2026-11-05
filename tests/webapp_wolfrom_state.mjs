// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
// Actual app/document functions with DOM and engine doubles; no browser claim.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const fixture=JSON.parse(fs.readFileSync(0,'utf8'));
class Custom extends Event {constructor(type,{detail}={}){super(type);this.detail=detail;}}
globalThis.CustomEvent=Custom;
class Element extends EventTarget {
  constructor(tag='div'){super();this.tagName=tag.toUpperCase();this.children=[];this.dataset={};this.attributes={};this.value='';this.hidden=false;this.disabled=false;this.open=false;this.className='';this.scrollTop=0;this.parent=null;this.connected=false;this.style={};this.classList={add:(...values)=>{this.className=[...new Set([...this.className.split(' ').filter(Boolean),...values])].join(' ');},contains:value=>this.className.split(' ').includes(value),remove:value=>{this.className=this.className.split(' ').filter(c=>c!==value).join(' ');},toggle:value=>{const had=this.classList.contains(value);if(had)this.classList.remove(value);else this.className+=' '+value;return !had;}};}
  get isConnected(){return this.connected || !!this.parent?.isConnected;}
  // The actual UI now adds presentation classes to fixed/three-member drives.
  // Keep the DOM double's className and classList views in sync.
  get parentElement(){return this.parent;}
  append(...children){for(const child of children){if(child.parent){const i=child.parent.children.indexOf(child);if(i>=0)child.parent.children.splice(i,1);}child.parent=this;this.children.push(child);}}
  replaceChildren(...children){for(const child of this.children)child.parent=null;this.children=[];this.append(...children);}
  insertBefore(child,before){const i=this.children.indexOf(before);child.parent=this;this.children.splice(i<0?this.children.length:i,0,child);}
  setAttribute(k,v){this.attributes[k]=String(v);}
  getAttribute(k){return this.attributes[k]??null;}
  querySelector(selector){const matches=n=>selector.startsWith('.')?n.classList.contains(selector.slice(1)):n.tagName===selector.toUpperCase();return descendants(this).slice(1).find(matches)??null;}
  querySelectorAll(selector){return descendants(this).slice(1).filter(n=>n.tagName===selector.toUpperCase());}
  closest(selector){for(let n=this;n;n=n.parent){if(selector.startsWith('.')?n.classList.contains(selector.slice(1)):n.tagName===selector.toUpperCase())return n;}return null;}
  contains(other){return descendants(this).includes(other);}
  getBoundingClientRect(){return {left:20,right:320,top:80,width:300,height:250};}
  focus(){document.activeElement=this;}
  setSelectionRange(start,end){this.selectionStart=start;this.selectionEnd=end;}
  showModal(){this.open=true;}
  close(){this.open=false;}
  click(){if(!this.disabled)this.dispatchEvent(new Event('click'));}
}
const nodes=new Map();const el=id=>{if(!nodes.has(id)){const n=new Element();n.connected=true;nodes.set(id,n);}return nodes.get(id);};
globalThis.document={getElementById:el,createElement:tag=>new Element(tag),querySelectorAll:()=>[],activeElement:null,body:el('body'),documentElement:{clientWidth:1280}};
// Match the real motion bar's help anchor around the precise RPM input.
const motionControls=new Element();motionControls.className='motion-bar input-controls';
motionControls.append(el('motion-rpm'));document.body.append(motionControls);
globalThis.window={innerHeight:800};
globalThis.fetch=async path=>{assert.equal(path,'./help-illustrations.json');return {ok:true,json:async()=>JSON.parse(fs.readFileSync(root+'webapp/help-illustrations.json','utf8'))};};
globalThis.requestAnimationFrame=()=>0;globalThis.cancelAnimationFrame=()=>{};
globalThis.localStorage={getItem:()=>null};
const dm=new vm.SourceTextModule(fs.readFileSync(root+'webapp/document.js','utf8'));
await dm.link(()=>{throw Error('Unexpected dependency');});await dm.evaluate();
const preferencesModule=new vm.SourceTextModule(fs.readFileSync(root+'webapp/preferences.js','utf8'));
await preferencesModule.link(()=>{throw Error('Unexpected preference dependency');});await preferencesModule.evaluate();
const exp={...dm.namespace,storage:{readRecovery:()=>null,writeRecovery:()=>true,recent:()=>[]}};
const di=new vm.SyntheticModule(Object.keys(exp),function(){for(const[k,v]of Object.entries(exp))this.setExport(k,v);});
const dependency=(key,value)=>new vm.SyntheticModule([key],function(){this.setExport(key,value);});
const deps={'./preferences.js':preferencesModule,'./document.js':di,'./engine-client.js':dependency('EngineClient',class{}),'./viewer.js':dependency('ModelViewer',class{}),'./tools.js':dependency('initTools',()=>{})};
const languageModule = new vm.SourceTextModule('export const LANGUAGES={}; export async function initLanguage(){return {setLanguage(){}};}');
await languageModule.link(()=>{}); await languageModule.evaluate();
deps['./ui-language.js']=languageModule;

deps['./model-catalog.js']=new vm.SyntheticModule(['initModelCatalog','selectionSummary'],function(){
  this.setExport('initModelCatalog',()=>{});this.setExport('selectionSummary',()=>'');
});
deps['./choice-menu.js']=dependency('initChoiceMenus',()=>({close(){}}));

let source=fs.readFileSync(root+'webapp/app.js','utf8').replace(/setup\(\);\s*$/,'');
source+=`\nexport {doc,renderFields,makeDriveConnections,syncMotionControl,currentValid,generateCurrent,openProject,scrubPreviewPhase};
export function initialize(testSchema,testDesign,transport) {
  startup=true; schema=structuredClone(testSchema); catalog={project_format:'solidcraft-riduttori/1',families:[{key:'wolfrom',...schema}]};
  doc.replace('wolfrom',schema,testDesign.values); engine=transport; design=structuredClone(testDesign); design.parts=[];
  viewer={render(){},clear(){},selected:new Set()}; fatal=false; busy=false; schemaPending=false; generationRunning=false; actionConfirmation=false;
  analysisActive=false; validToken=doc.token(); previousRevision=doc.revision; phase=1.25; rememberSourceParameters(); startup=false;
}
export function previewDimensions(family,nextSchema){startup=true; schema=structuredClone(nextSchema);catalog={families:[{key:family,label:family,...schema}]};doc.replace(family,schema,{});design=null;validToken=null;startup=false;renderFields();}
let previewCalls=[]; export function phaseCalls(){return previewCalls;}
export async function acceptDimensionGeneration(){
  previewCalls=[]; engine={failure:null,async request(method,payload){previewCalls.push(method);if(method==='generate')return {family:doc.family,design_id:99,values:payload.parameters,triangle_count:0,motion:{supported:true,message:'Fixture generated'},parts:[]};if(method==='pose')return {frames:[{parts:[]}]};throw Error('Unexpected fixture request '+method);}};
  viewer.setDesign=next=>{viewer.design=next;};viewer.applyFrame=frame=>{viewer.frame=frame;};await generateCurrent();
}
export function snapshot(){return {design,phase,sourceParameters,validToken};}
export function setTestSchema(next){schema=structuredClone(next);}
renderMetrics=()=>{};renderInspection=()=>{};
let scheduled=[]; scheduleGeneration=delay=>scheduled.push(delay); export function scheduledGenerations(){return scheduled;}
`;
const app=new vm.SourceTextModule(source);await app.link(path=>deps[path]);await app.evaluate();const a=app.namespace;
const descendants=e=>[e,...e.children.flatMap(descendants)];
const texts=e=>descendants(e).map(n=>n.textContent??'').join(' ');
const settle=()=>new Promise(resolve=>setImmediate(resolve));
function openMotionHelp(expectedTitle){
  const trigger=el('motion-rpm');
  assert.equal(trigger.getAttribute('aria-keyshortcuts'),'F1');
  assert.equal(trigger.getAttribute('aria-controls'),'parameter-help-pane');
  const event=new Event('keydown',{cancelable:true});event.key='F1';motionControls.dispatchEvent(event);
  assert.equal(event.defaultPrevented,true);
  const pane=document.body.children.find(n=>n.id==='parameter-help-pane');
  assert.ok(pane && !pane.hidden,'The actual shared guide is visible');
  assert.ok(texts(pane).includes(expectedTitle));
  assert.equal(trigger.getAttribute('aria-expanded'),'true');
  const close=pane.querySelector('button');assert.equal(document.activeElement,close);
  close.click();assert.equal(trigger.getAttribute('aria-expanded'),'false');
  assert.equal(document.activeElement,trigger,'Closing keyboard help restores the precise RPM field');
  return pane;
}
let calls=[];const transport={failure:null,async request(method){calls.push(method);if(method==='project')return {};throw Error('Rejected Wolfrom '+method);}};
a.initialize(fixture.schema,fixture.design,transport);
// Family edits can render controls before the async schema reply arrives.
// An old spec cached under the new family must be replaced when its help changes.
a.setTestSchema(fixture.previous_schema);a.syncMotionControl();
const previousHelp=openMotionHelp('Input speed · rpm');
assert.ok(texts(previousHelp).includes('Input speed · rpm'));
assert.ok(texts(previousHelp).includes(fixture.previous_schema.fields.find(f=>f.key==='input_rpm').help.meaning));
a.doc.editNumber('input_rpm','-600,000000000123');document.activeElement=el('motion-rpm');
const focused=document.activeElement,transitionDraft=structuredClone(a.doc.state),transitionHistory=structuredClone(a.doc.past);
a.setTestSchema(fixture.schema);a.syncMotionControl();
const currentHelp=openMotionHelp('Sun input speed · rpm');
assert.equal(currentHelp,previousHelp,'Parameter guides reuse one shared pane');
for(const expected of ['Sun input speed · rpm','+Z','first ring stays fixed'])assert.ok(texts(currentHelp).includes(expected),expected);
assert.ok(texts(currentHelp).includes(fixture.schema.fields.find(f=>f.key==='input_rpm').help.meaning));
assert.equal(document.activeElement,focused);assert.equal(el('motion-rpm').value,'-600,000000000123');
assert.deepEqual(a.doc.state,transitionDraft);assert.deepEqual(a.doc.past,transitionHistory);
document.activeElement=null;a.initialize(fixture.schema,fixture.design,transport);
const io=fixture.schema.options.find(f=>f.key==='io_scheme');
assert.deepEqual(io.choices.map(c=>c.value),['sun_output_ring']);assert.ok(io.help.meaning);
const connections=a.makeDriveConnections(io);const labels=texts(connections);
const nominal=connections.children.find(n=>n.className==='drive-result');
assert.ok(nominal,'The nominal output stays outside the collapsed motion details');
assert.equal(nominal.children[0].textContent,'Nominal output');
assert.equal(Number(nominal.children[1].textContent),fixture.design.analysis.kinematics.stage_results[0].rates_rpm.output);
const motionDetails=connections.children.find(n=>n.tagName==='DETAILS');assert.ok(motionDetails);
assert.equal(motionDetails.open,false);assert.equal(motionDetails.children[0].textContent,'Motion details');
for(const expected of ['sun 600 rpm','carrier 60 rpm','compound spin -75 rpm','output ring 1 rpm','fixed first ring 0 rpm'])assert.ok(texts(motionDetails).includes(expected),expected+' remains in the motion details');
for(const expected of ['Sun','First ring','Second ring · exposed annulus','carrier 60 rpm','compound spin -75 rpm','output ring 1 rpm','fixed first ring 0 rpm','+Z'])assert.ok(labels.includes(expected),expected);
assert.equal(descendants(connections).filter(n=>['SELECT','INPUT'].includes(n.tagName)).length,0,'The fixed Wolfrom arrangement has no editable controls');
const connectionButtons=descendants(connections).filter(n=>n.tagName==='BUTTON');
assert.equal(connectionButtons.length,0,'The fixed arrangement uses contextual help on its body');
assert.equal(connections.getAttribute('aria-keyshortcuts'),'F1');
document.body.append(connections);
const connectionHelp=new Event('keydown',{cancelable:true});connectionHelp.key='F1';connections.dispatchEvent(connectionHelp);
const connectionPane=document.body.children.find(n=>n.id==='parameter-help-pane');
assert.ok(!connectionPane.hidden && texts(connectionPane).includes(io.help.title));
assert.equal(connections.getAttribute('aria-expanded'),'true');connectionPane.querySelector('button').click();
a.renderFields();const rows=descendants(el('parameters'));
const keys=rows.filter(n=>n.dataset.field).map(n=>n.dataset.field);
assert.ok(keys.indexOf('planet')<keys.indexOf('planet2'));assert.ok(keys.indexOf('planet2')<keys.indexOf('output_ring'));
assert.ok(keys.indexOf('width2')<keys.indexOf('layer_gap'));
const derived=rows.filter(n=>n.className==='derived-row');
assert.ok(derived.some(n=>texts(n).includes('First ring teeth · fixed · derived 162')));
const module2=derived.find(n=>texts(n).includes('Second layer module'));
assert.ok(texts(module2).includes('0.592105263158'));assert.ok(module2.title.includes('0.5921052631578947'));
assert.ok(module2.parent.classList.contains('primary-geometry'),'Derived module remains a full-width sibling of pairs');
assert.ok(module2.parent.children.some(n=>n.className==='parameter-pair'),'Actual parameter cards retain their shared pair wrapper');
assert.equal(el('motion-caption').textContent,'Sun input speed');assert.ok(el('motion-rpm').title.includes('Signed sun'));assert.ok(Number(el('rpm-slider').min)<0);

// Rejected geometry leaves the accepted viewer stale, preserves exact raw text,
// and keeps the document history/recovery reversible. No stale RPC succeeds.
const accepted=a.snapshot().design;a.doc.editNumber('planet2','60');a.doc.editNumber('width2','6,000000000123');
const history=structuredClone(a.doc.past);const draft=structuredClone(a.doc.state);await a.generateCurrent();
assert.equal(a.snapshot().design,accepted);assert.equal(a.currentValid(),false);assert.equal(el('stale-banner').hidden,false);
assert.deepEqual(a.doc.past,history);assert.deepEqual(a.doc.state,draft);assert.equal(a.doc.entries.width2.text,'6,000000000123');
assert.equal(el('save-document').disabled,true);assert.equal(el('export-document').disabled,true);
const recovery=a.doc.recovery();assert.ok(JSON.stringify(recovery).includes('6,000000000123'));
a.doc.undo();assert.equal(a.doc.entries.width2.text,'6');a.doc.redo();assert.equal(a.doc.entries.width2.text,'6,000000000123');

// A rejected project cannot replace a valid user's document or source snapshot.
a.initialize(fixture.schema,fixture.design,transport);const before=structuredClone(a.doc.state),past=structuredClone(a.doc.past),saved=a.snapshot();
const opening=a.openProject({format:'solidcraft-riduttori/1',family:'wolfrom',parameters:{planet2:60}},'invalid.json');await settle();
assert.equal(el('app-dialog').open,true);const close=el('dialog-actions').children.find(b=>b.textContent==='Close');assert.ok(close);close.click();
assert.equal(await opening,false);assert.equal(a.currentValid(),true);assert.equal(a.snapshot().phase,saved.phase);assert.deepEqual(a.scheduledGenerations(),[]);assert.deepEqual(a.doc.state,before);assert.deepEqual(a.doc.past,past);assert.equal(a.snapshot().design,saved.design);assert.deepEqual(a.snapshot().sourceParameters,saved.sourceParameters);
// A previously invalid draft cannot become valid after rejecting a project.
a.doc.editNumber('planet2','60');await a.generateCurrent();const invalid=structuredClone(a.doc.state),invalidHistory=structuredClone(a.doc.past);assert.equal(a.currentValid(),false);
const failed=a.openProject({format:'solidcraft-riduttori/1',family:'wolfrom',parameters:{profile_shift:0}},'unsupported.json');await settle();
el('dialog-actions').children.find(b=>b.textContent==='Discard changes').click();await settle();
el('dialog-actions').children.find(b=>b.textContent==='Close').click();assert.equal(await failed,false);
assert.equal(a.currentValid(),false);assert.equal(el('stale-banner').hidden,false);assert.deepEqual(a.doc.state,invalid);assert.deepEqual(a.doc.past,invalidHistory);assert.deepEqual(a.scheduledGenerations(),[]);
// Approved compact presentation keeps the four common dimensions visible
// and preserves every remaining geometry field behind real disclosures.
a.previewDimensions('parallel',fixture.previous_schema);
const compact=descendants(el('parameters'));
const primary=compact.find(n=>n.classList.contains('primary-geometry'));
assert.ok(primary);assert.deepEqual(descendants(primary).filter(n=>n.dataset.field).map(n=>n.dataset.field),['pinion','wheel','module','width']);
assert.deepEqual(primary.children.map(pair=>pair.children.map(field=>field.dataset.field)),[['pinion','wheel'],['module','width']]);
for(const [key,caption]of [['module','Module · mm'],['width','Face width · mm']]){
  const row=descendants(primary).find(n=>n.dataset.field===key);
  assert.ok(descendants(row).some(n=>n.tagName==='LABEL' && n.textContent===caption),caption);
  const inputBox=descendants(row).find(n=>n.className==='field-input');
  const input=descendants(inputBox).find(n=>n.tagName==='INPUT');
  assert.equal(input.getAttribute('aria-keyshortcuts'),'F1','Contextual help is accessible from the precise input');
  assert.equal(input.getAttribute('aria-controls'),'parameter-help-pane');
  const help=new Event('keydown',{cancelable:true});help.key='F1';row.dispatchEvent(help);
  const pane=document.body.children.find(n=>n.id==='parameter-help-pane');
  assert.ok(!pane.hidden && texts(pane).includes(fixture.previous_schema.fields.find(f=>f.key===key).help.meaning));
  pane.querySelector('button').click();assert.equal(document.activeElement,input);
  assert.equal(descendants(inputBox).some(n=>n.className==='unit'),false,'Units stay in the label, outside the precise input');
}

const allParameters=compact.find(n=>n.className==='all-model-parameters');assert.ok(allParameters);
for(const key of ['bore','output_bore','center_extra'])assert.ok(descendants(allParameters).some(n=>n.dataset.field===key),key+' stays available');
const advanced=compact.find(n=>n.tagName==='DETAILS' && texts(n.children[0])==='Advanced tooth geometry');assert.ok(advanced);
for(const key of ['pressure','profile_shift','backlash'])assert.ok(descendants(advanced).some(n=>n.dataset.field===key),key+' stays available');
// An accepted edit behind the compact disclosure keeps that disclosure open,
// the exact typed spelling, and the user's caret/selection through rebuilding.
allParameters.open=true;allParameters.dispatchEvent(new Event('toggle'));
const centreRow=descendants(allParameters).find(n=>n.dataset.field==='center_extra');
const centreInput=descendants(centreRow).find(n=>n.tagName==='INPUT');
centreInput.value='0,1234567890123';centreInput.focus();centreInput.setSelectionRange(2,8);centreInput.dispatchEvent(new Event('input'));
const editedHistory=structuredClone(a.doc.past);await a.acceptDimensionGeneration();
assert.equal(a.currentValid(),true);const rebuilt=descendants(el('parameters')).find(n=>n.className==='all-model-parameters');
assert.equal(rebuilt.open,true);assert.equal(document.activeElement.dataset.key,'center_extra');
assert.equal(document.activeElement.value,'0,1234567890123');assert.equal(document.activeElement.selectionStart,2);assert.equal(document.activeElement.selectionEnd,8);
assert.equal(a.doc.entries.center_extra.text,'0,1234567890123');assert.deepEqual(a.doc.past,editedHistory);
// Preview phase uses only the existing pose RPC: no regeneration, document
// history entry, or normalization of the currently typed geometry spelling.
const phaseDesign=a.snapshot().design,phaseDraft=structuredClone(a.doc.state),phaseHistory=structuredClone(a.doc.past),phaseCallCount=a.phaseCalls().length;
el('phase-range').value='1.234';await a.scrubPreviewPhase();
assert.equal(a.snapshot().phase,1.234);assert.equal(a.snapshot().design,phaseDesign);
assert.deepEqual(a.phaseCalls().slice(phaseCallCount),['pose']);assert.deepEqual(a.doc.state,phaseDraft);assert.deepEqual(a.doc.past,phaseHistory);
assert.equal(el('motion-phase').textContent,'1.23 rad');
console.log('Wolfrom browser state checks passed');
