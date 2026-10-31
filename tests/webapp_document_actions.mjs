// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
// Actual document and app actions with DOM/transport doubles; no browser claim.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const fixture=JSON.parse(fs.readFileSync(0,'utf8'));
class Custom extends Event {constructor(type,{detail}={}){super(type);this.detail=detail;}}
globalThis.CustomEvent=Custom;
class Element extends EventTarget {
  constructor(tag='div'){super();this.tagName=tag.toUpperCase();this.type='text';this.children=[];this.dataset={};this.attributes={};this.value='';this.hidden=false;this.disabled=false;this.open=false;}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=nodes;}
  setAttribute(k,v){this.attributes[k]=v;}
  querySelector(){return new Element();}
  querySelectorAll(){return [];}
  showModal(){this.open=true;}
  close(){this.open=false;}
  click(){if(!this.disabled)this.dispatchEvent(new Event('click'));}
}
const nodes=new Map();
const el=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);};
globalThis.document={getElementById:el,createElement:tag=>new Element(tag),querySelectorAll:()=>[],activeElement:el('motion-rpm')};
globalThis.requestAnimationFrame=()=>{throw Error('Document confirmation must not wait on animation frames');};
globalThis.cancelAnimationFrame=()=>{};
globalThis.localStorage={getItem:()=>null};
const documentModule=new vm.SourceTextModule(fs.readFileSync(root+'webapp/document.js','utf8'));
await documentModule.link(()=>{throw Error('Unexpected document dependency');});await documentModule.evaluate();
const downloads=[],remembered=[];
const exports={...documentModule.namespace,storage:{readRecovery:()=>null,writeRecovery:()=>true,clearRecovery(){},recent:()=>[],remember:(...v)=>remembered.push(v)},downloadBlob:(blob,name)=>downloads.push({blob,name})};
const documentImport=new vm.SyntheticModule(Object.keys(exports),function(){for(const [k,v]of Object.entries(exports))this.setExport(k,v);});
const dependency=(name,value)=>new vm.SyntheticModule([name],function(){this.setExport(name,value);});
const dependencies={'./document.js':documentImport,'./engine-client.js':dependency('EngineClient',class{}),'./viewer.js':dependency('ModelViewer',class{}),'./tools.js':dependency('initTools',()=>{})};
let source=fs.readFileSync(root+'webapp/app.js','utf8').replace(/setup\(\);\s*$/,'');
// Avoid renderer/startup work while retaining the actual document action,
// precision/normalization, lease checks, dialogs, and keyboard handlers.
source+=`\nrenderFields=()=>{}; renderMetrics=()=>{}; renderInspection=()=>{}; updateFamilyHeader=()=>{}; applyFieldErrors=()=>{}; syncMotionControl=()=>{};
export {doc,saveProject,runExport,exportDialog,newDocument,openProject,protectChanges,documentShortcut,commitRates,currentValid,documentActionReady};
export function initialize(testSchema,values,transport) {
  startup=true; schema=structuredClone(testSchema); catalog={project_format:'solidcraft-riduttori/1',families:[{key:'parallel',...schema}]};
  doc.replace('parallel',schema,values); engine=transport; fatal=false; busy=false; actionConfirmation=false; analysisActive=false;
  generationRunning=false; schemaPending=false; rateEditing=false; rateSource=null; ratePending=false; rateCompletion=null;
  poseCompletion=Promise.resolve(); phase=1.234; operationSerial=10; previousRevision=doc.revision;
  design={family:'parallel',design_id:7,values:structuredClone(values),motion:{supported:true},parts:[{index:0}],buffers:[new ArrayBuffer(12)]};
  viewer={design,selected:new Set([0]),frame:{parts:[]},render(){},clear(){},setDesign(next){this.design=next;},captureNominal:async()=>new Uint8Array([1])};
  nominalFrame={parts:[]}; playing=true; validToken=doc.token(); rememberSourceParameters(); scheduled=[]; startup=false;
}
doc.addEventListener('change',onDocumentChange);
export function testState(){return {design,phase,playing,ratePending,rateEditing,busy,actionConfirmation,operation:operationSerial};}
export function setPoseWait(promise){poseCompletion=promise;}
export function setAnalysis(value){analysisActive=value;}
export function replaceSource(){design={...design};}
let scheduled=[]; export function scheduledGenerations(){return scheduled;}
refreshSchema=async()=>true; scheduleGeneration=delay=>scheduled.push(delay);
`;
const app=new vm.SourceTextModule(source);await app.link(path=>dependencies[path]);await app.evaluate();const a=app.namespace;
const defer=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
const settle=()=>new Promise(resolve=>setImmediate(resolve));
let calls=[],rateGate=null,exportGate=null,canonical;
const engine={failure:null,async request(method,payload){
  calls.push({method,payload:structuredClone(payload)});
  if(method==='rates'){
    const values={...canonical,...payload.rpm_patch};
    if(rateGate)await rateGate.promise;
    canonical=values;return {design_id:payload.design_id,values,ports:[],buffers:[],motion:{supported:true}};
  }
  if(method==='export'){
    const project={format:'solidcraft-riduttori/1',family:'parallel',parameters:structuredClone(canonical)};
    if(exportGate)await exportGate.promise;
    const bytes=new TextEncoder().encode(JSON.stringify(project));
    return {buffer:0,buffers:[bytes],mime:'application/json',name:'export.json',bytes:bytes.length};
  }
  if(method==='import_project')throw Error('Invalid canonical module');
  throw Error('Unexpected request '+method);
}};
function reset(){calls=[];downloads.length=0;remembered.length=0;rateGate=exportGate=null;canonical=structuredClone(fixture.values);el('app-dialog').close();a.initialize(fixture.schema,fixture.values,engine);}
function edit(text){a.doc.editNumber('input_rpm',text);}
function choose(label){const button=el('dialog-actions').children.find(b=>b.textContent===label);assert.ok(button,`Missing action ${label}`);assert.equal(button.disabled,false);button.click();}
async function downloaded(){assert.equal(downloads.length,1);return JSON.parse(await downloads[0].blob.text());}

// Complete exact text commits before project snapshot, with no mesh replacement,
// phase change, extra undo checkpoint or second blur-triggered rates request.
reset();const initial=a.testState().design,mesh=initial.buffers;edit('31,1234567890123');const history=a.doc.past.length;
assert.equal(a.documentActionReady(),true);const blur=a.commitRates();const save=a.saveProject();
assert.equal(await save,true);await blur;
assert.deepEqual(calls.map(c=>c.method),['rates','export']);assert.equal(calls[0].payload.phase,1.234);
assert.equal((await downloaded()).parameters.input_rpm,31.1234567890123);
assert.equal(a.doc.entries.input_rpm.text,'31,1234567890123');assert.equal(a.doc.past.length,history);
assert.equal(a.testState().design,initial);assert.equal(initial.buffers,mesh);assert.equal(a.doc.dirty,false);
assert.equal(a.testState().phase,1.234);assert.equal(a.testState().playing,true);

// Incomplete text stays visible and blocks every source download path.
reset();edit('-');const validRate=a.testState().design.values.input_rpm;
assert.equal(await a.saveProject(),false);assert.equal(await a.runExport('stl'),false);await a.exportDialog();
assert.equal(a.doc.entries.input_rpm.text,'-');assert.equal(a.testState().design.values.input_rpm,validRate);
assert.equal(a.testState().playing,true);assert.equal(a.testState().phase,1.234);
assert.equal(a.doc.dirty,true);assert.equal(downloads.length,0);assert.deepEqual(calls,[]);assert.equal(el('app-dialog').open,false);

// Export dialog itself confirms RPM, and selected geometry uses that snapshot.
reset();edit('45,1234567890123');const dialog=a.exportDialog();await settle();assert.equal(calls[0].method,'rates');
const body=el('dialog-body').children[0];const format=body.children[0].children[1];format.value='stl';
choose('Download export');await dialog;assert.deepEqual(calls.map(c=>c.method),['rates','export']);
assert.deepEqual(calls[1].payload.indices,[0]);assert.equal((await downloaded()).parameters.input_rpm,45.1234567890123);

// A second edit while the old pose drains cannot bless the earlier parsed rate
// under the new revision. A later explicit Save retries the retained text.
reset();edit('12');const pose=defer();a.setPoseWait(pose.promise);const pending=a.saveProject();await settle();edit('34,1234567890123');pose.resolve();
assert.equal(await pending,false);assert.deepEqual(calls,[]);assert.equal(downloads.length,0);
assert.equal(a.doc.entries.input_rpm.text,'34,1234567890123');assert.equal(a.testState().ratePending,false);
assert.equal(await a.saveProject(),true);assert.equal((await downloaded()).parameters.input_rpm,34.1234567890123);

// Edits during rates RPC cannot download or overwrite newer typed drafts.
reset();edit('12');rateGate=defer();const pendingRateSave=a.saveProject();await settle();edit('56,1234567890123');rateGate.resolve();
assert.equal(await pendingRateSave,false);assert.equal(downloads.length,0);assert.equal(a.doc.entries.input_rpm.text,'56,1234567890123');
rateGate=null;assert.equal(await a.saveProject(),true);assert.equal((await downloaded()).parameters.input_rpm,56.1234567890123);

// A stale export must not mark a newer document/revision or source as saved.
for(const mutate of [()=>edit('77'),()=>a.doc.replace('parallel',fixture.schema,fixture.values,'Another document'),()=>a.replaceSource()]){
  reset();edit('42');exportGate=defer();const save=a.saveProject();await settle();assert.equal(a.testState().busy,true);mutate();exportGate.resolve();
  assert.equal(await save,false);assert.equal(downloads.length,0);assert.equal(a.testState().busy,false);
}
reset();a.setAnalysis(true);assert.equal(await a.saveProject(),false);assert.equal(await a.runExport('stl'),false);assert.deepEqual(calls,[]);
reset();exportGate=defer();const firstSave=a.saveProject(),duplicateSave=a.saveProject();await settle();
assert.equal(await duplicateSave,false);assert.deepEqual(calls.map(c=>c.method),['export']);exportGate.resolve();assert.equal(await firstSave,true);assert.equal(downloads.length,1);
reset();edit('38');rateGate=defer();const analyzedSave=a.saveProject();await settle();a.setAnalysis(true);rateGate.resolve();assert.equal(await analyzedSave,false);assert.equal(downloads.length,0);

// New uses the same dirty Cancel/Discard/Save flow, including complete pending
// rates. Ctrl/Cmd keyboard commands never invoke OS new-window behavior.
function key(key,{shift=false,meta=false,target=new Element()}={}){let prevented=false;a.documentShortcut({key,ctrlKey:!meta,metaKey:meta,shiftKey:shift,target,preventDefault(){prevented=true;}});return prevented;}
reset();edit('23');const identity=a.doc.identity;assert.equal(key('n'),true);await settle();choose('Cancel');await settle();assert.equal(a.doc.identity,identity);assert.equal(a.doc.entries.input_rpm.text,'23');
assert.equal(key('n',{meta:true}),true);await settle();choose('Discard changes');await settle();assert.notEqual(a.doc.identity,identity);assert.equal(downloads.length,0);
reset();edit('24,1234567890123');const beforeSaveNew=a.doc.identity;key('n');await settle();choose('Save project');await settle();assert.notEqual(a.doc.identity,beforeSaveNew);assert.equal((await downloaded()).parameters.input_rpm,24.1234567890123);
reset();edit('25');key('s',{shift:true,meta:true});await settle();assert.equal(el('dialog-title').textContent,'Save project as');
el('dialog-body').children[0].children[1].value='Exact speed';choose('Save');await settle();assert.equal(downloads[0].name,'Exact speed.config.json');assert.equal((await downloaded()).parameters.input_rpm,25);
reset();edit('27');const cancelledSave=a.saveProject({saveAs:true});await settle();choose('Cancel');assert.equal(await cancelledSave,false);
assert.equal(downloads.length,0);assert.equal(a.doc.dirty,true);assert.equal(a.doc.entries.input_rpm.text,'27');
reset();edit('-');const blockedNew=a.newDocument();await settle();assert.equal(el('dialog-actions').children.find(b=>b.textContent==='Save project').disabled,true);choose('Cancel');await blockedNew;
reset();edit('26');const undoRevision=a.doc.revision;const input=new Element('input');assert.equal(key('z',{target:input}),false);assert.equal(a.doc.revision,undoRevision);
assert.equal(key('z'),true);assert.equal(a.doc.revision,undoRevision+1);
el('app-dialog').showModal();assert.equal(key('n'),false);assert.equal(key('s'),false);el('app-dialog').close();

// Failed Open preserves raw draft/history and requests retained-source recovery.
reset();edit('-');const beforeOpen={identity:a.doc.identity,state:structuredClone(a.doc.state),past:structuredClone(a.doc.past)};
const opening=a.openProject({format:'solidcraft-riduttori/1',family:'parallel',parameters:{module:-1}},'Bad.json');await settle();choose('Discard changes');await settle();
assert.equal(el('dialog-title').textContent,'Project could not be opened');choose('Close');assert.equal(await opening,false);
assert.equal(a.doc.identity,beforeOpen.identity);assert.deepEqual(a.doc.state,beforeOpen.state);assert.deepEqual(a.doc.past,beforeOpen.past);
assert.deepEqual(a.scheduledGenerations(),[0]);
console.log('document action checks passed');
