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
  constructor(tag='div'){super();this.tagName=tag.toUpperCase();this.children=[];this.dataset={};this.attributes={};this.value='';this.hidden=false;this.disabled=false;this.open=false;this.className='';this.scrollTop=0;this.classList={contains:value=>this.className.split(' ').includes(value)};}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
  insertBefore(child,before){const i=this.children.indexOf(before);this.children.splice(i<0?this.children.length:i,0,child);}
  setAttribute(k,v){this.attributes[k]=v;}
  querySelector(){return new Element();}
  querySelectorAll(){return [];}
  showModal(){this.open=true;}
  close(){this.open=false;}
  click(){if(!this.disabled)this.dispatchEvent(new Event('click'));}
}
const nodes=new Map();const el=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);};
globalThis.document={getElementById:el,createElement:tag=>new Element(tag),querySelectorAll:()=>[],activeElement:null};
globalThis.requestAnimationFrame=()=>0;globalThis.cancelAnimationFrame=()=>{};
globalThis.localStorage={getItem:()=>null};
const dm=new vm.SourceTextModule(fs.readFileSync(root+'webapp/document.js','utf8'));
await dm.link(()=>{throw Error('Unexpected dependency');});await dm.evaluate();
const exp={...dm.namespace,storage:{readRecovery:()=>null,writeRecovery:()=>true,recent:()=>[]}};
const di=new vm.SyntheticModule(Object.keys(exp),function(){for(const[k,v]of Object.entries(exp))this.setExport(k,v);});
const dependency=(key,value)=>new vm.SyntheticModule([key],function(){this.setExport(key,value);});
const deps={'./document.js':di,'./engine-client.js':dependency('EngineClient',class{}),'./viewer.js':dependency('ModelViewer',class{}),'./tools.js':dependency('initTools',()=>{})};
let source=fs.readFileSync(root+'webapp/app.js','utf8').replace(/setup\(\);\s*$/,'');
source+=`\nexport {doc,renderFields,makeDriveConnections,syncMotionControl,currentValid,generateCurrent,openProject};
export function initialize(testSchema,testDesign,transport) {
  startup=true; schema=structuredClone(testSchema); catalog={project_format:'solidcraft-riduttori/1',families:[{key:'wolfrom',...schema}]};
  doc.replace('wolfrom',schema,testDesign.values); engine=transport; design=structuredClone(testDesign); design.parts=[];
  viewer={render(){},clear(){},selected:new Set()}; fatal=false; busy=false; schemaPending=false; generationRunning=false; actionConfirmation=false;
  analysisActive=false; validToken=doc.token(); previousRevision=doc.revision; phase=1.25; sourceParameters=structuredClone(testDesign.values); startup=false;
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
let calls=[];const transport={failure:null,async request(method){calls.push(method);if(method==='project')return {};throw Error('Rejected Wolfrom '+method);}};
a.initialize(fixture.schema,fixture.design,transport);
// Family edits can render controls before the async schema reply arrives.
// An old spec cached under the new family must be replaced when its help changes.
a.setTestSchema(fixture.previous_schema);a.syncMotionControl();
assert.ok(texts(el('motion-help')).includes('Input speed · rpm'));
a.doc.editNumber('input_rpm','-600,000000000123');document.activeElement=el('motion-rpm');
const focused=document.activeElement,transitionDraft=structuredClone(a.doc.state),transitionHistory=structuredClone(a.doc.past);
a.setTestSchema(fixture.schema);a.syncMotionControl();
for(const expected of ['Sun input speed · rpm','+Z','first ring stays fixed'])assert.ok(texts(el('motion-help')).includes(expected),expected);
assert.equal(document.activeElement,focused);assert.equal(el('motion-rpm').value,'-600,000000000123');
assert.deepEqual(a.doc.state,transitionDraft);assert.deepEqual(a.doc.past,transitionHistory);
document.activeElement=null;a.initialize(fixture.schema,fixture.design,transport);
const io=fixture.schema.options.find(f=>f.key==='io_scheme');
assert.deepEqual(io.choices.map(c=>c.value),['sun_output_ring']);assert.ok(io.help.meaning);
const connections=a.makeDriveConnections(io);const labels=texts(connections);
for(const expected of ['Sun','First ring','Second ring · exposed annulus','carrier 60 rpm','compound spin -75 rpm','output ring 1 rpm','fixed first ring 0 rpm','+Z'])assert.ok(labels.includes(expected),expected);
assert.equal(descendants(connections).filter(n=>['BUTTON','SELECT','INPUT'].includes(n.tagName)).length,0);
a.renderFields();const rows=descendants(el('parameters'));
const keys=rows.filter(n=>n.dataset.field).map(n=>n.dataset.field);
assert.ok(keys.indexOf('planet')<keys.indexOf('planet2'));assert.ok(keys.indexOf('planet2')<keys.indexOf('output_ring'));
assert.ok(keys.indexOf('width2')<keys.indexOf('layer_gap'));
const derived=rows.filter(n=>n.className==='derived-row');
assert.ok(derived.some(n=>texts(n).includes('First ring teeth · fixed · derived 162')));
const module2=derived.find(n=>texts(n).includes('Second layer module'));
assert.ok(texts(module2).includes('0.592105263158'));assert.ok(module2.title.includes('0.5921052631578947'));
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
const failed=a.openProject({format:'solidcraft-riduttori/1',family:'wolfrom',parameters:{helix:0}},'unsupported.json');await settle();
el('dialog-actions').children.find(b=>b.textContent==='Discard changes').click();await settle();
el('dialog-actions').children.find(b=>b.textContent==='Close').click();assert.equal(await failed,false);
assert.equal(a.currentValid(),false);assert.equal(el('stale-banner').hidden,false);assert.deepEqual(a.doc.state,invalid);assert.deepEqual(a.doc.past,invalidHistory);assert.deepEqual(a.scheduledGenerations(),[]);
console.log('Wolfrom browser state checks passed');
