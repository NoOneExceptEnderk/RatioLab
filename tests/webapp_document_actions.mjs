// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
// Actual document and app actions with DOM/transport doubles; no browser claim.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {webModules} from './webapp_modules.mjs';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const fixture=JSON.parse(fs.readFileSync(0,'utf8'));
class Custom extends Event {constructor(type,{detail}={}){super(type);this.detail=detail;}}
globalThis.CustomEvent=Custom;
class Element extends EventTarget {
  constructor(tag='div'){super();this.tagName=tag.toUpperCase();this.type='text';this.children=[];this.dataset={};this.attributes={};this.value='';this.style={setProperty(key,value){this[key]=value;}};this.hidden=false;this.disabled=false;this.open=false;}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=nodes;}
  setAttribute(k,v){this.attributes[k]=v;}
  getAnimations(){return [];}
  querySelector(){return new Element();}
  querySelectorAll(){return [];}
  showModal(){this.open=true;}
  close(){this.open=false;}
  click(){if(!this.disabled)this.dispatchEvent(new Event('click'));}
}
const nodes=new Map();
const el=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);};
globalThis.document=Object.assign(new EventTarget(),{getElementById:el,createElement:tag=>new Element(tag),querySelectorAll:()=>[],activeElement:el('motion-rpm')});
globalThis.requestAnimationFrame=()=>{throw Error('Document confirmation must not wait on animation frames');};
globalThis.cancelAnimationFrame=()=>{};
globalThis.localStorage={getItem:()=>null};
const documentModule=new vm.SourceTextModule(fs.readFileSync(root+'webapp/document.js','utf8'));
await documentModule.link(()=>{throw Error('Unexpected document dependency');});await documentModule.evaluate();
const graph=webModules(root);
const preferencesModule=await graph.load('./preferences.js');
for(const name of ['settings','controls','themes'])await graph.load('./'+name+'.js');
const downloads=[],remembered=[];
let recoveryClears=0,recoveryWrites=0;
const exports={...documentModule.namespace,storage:{readRecovery:()=>null,writeRecovery:()=>{++recoveryWrites;return true;},clearRecovery(){++recoveryClears;},recent:()=>[],remember:(...v)=>remembered.push(v)},downloadBlob:(blob,name)=>downloads.push({blob,name})};
const documentImport=new vm.SyntheticModule(Object.keys(exports),function(){for(const [k,v]of Object.entries(exports))this.setExport(k,v);});
const dependency=(name,value)=>new vm.SyntheticModule([name],function(){this.setExport(name,value);});
const dependencies={'./preferences.js':preferencesModule,'./document.js':documentImport,'./engine-client.js':dependency('EngineClient',class{}),'./viewer.js':dependency('ModelViewer',class{}),'./tools.js':dependency('initTools',()=>{})};
const languageModule = new vm.SourceTextModule('export const LANGUAGES={}; export async function initLanguage(){return {setLanguage(){}};}');
await languageModule.link(()=>{}); await languageModule.evaluate();
dependencies['./ui-language.js']=languageModule;

dependencies['./model-catalog.js']=new vm.SyntheticModule(['initModelCatalog','selectionSummary'],function(){this.setExport('initModelCatalog',()=>{});this.setExport('selectionSummary',()=> '');});
dependencies['./choice-menu.js']=dependency('initChoiceMenus',()=>({close(){}}));

let source=fs.readFileSync(root+'webapp/app.js','utf8').replace(/setup\(\);\s*$/,'');
// Avoid renderer/startup work while retaining the actual document action,
// precision/normalization, lease checks, dialogs, and keyboard handlers.
source+=`\nrenderFields=()=>{}; renderMetrics=()=>{}; renderInspection=()=>{}; updateFamilyHeader=()=>{}; syncMotionControl=()=>{};
export {doc,saveProject,runExport,exportDialog,newDocument,openProject,protectChanges,commitRates,currentValid,documentActionReady,previewSpeed,applyEccentricPreset,schemaParameters,recoverDocument,boot,generateCurrent};
export function initialize(testSchema,values,transport,testFamily='parallel') {
  startup=true; recovery=null; errors={};fields.clear();schema=structuredClone(testSchema); catalog={project_format:'solidcraft-riduttori/1',families:[{key:testFamily,...schema}]};
  doc.replace(testFamily,schema,values); engine=transport; fatal=false; busy=false; actionConfirmation=false; analysisActive=false;
  generationRunning=false; schemaPending=false; rateEditing=false; rateSource=null; ratePending=false; rateCompletion=null;
  speedSliderPreview=null; speedSliderActive=false; speedSliderKeyActive=false;
  poseCompletion=Promise.resolve(); phase=1.234; operationSerial=10; previousRevision=doc.revision;
  design={family:testFamily,design_id:7,values:structuredClone(values),motion:{supported:true},parts:[{index:0}],triangle_count:1,buffers:[new ArrayBuffer(12)]};
  viewer={design,selected:new Set([0]),hidden:new Set(),frame:{parts:[]},render(){},clear(){},setSelection(indices){this.selected=new Set(indices);},setDesign(next){this.design=next;},captureNominal:async()=>new Uint8Array([1])};
  nominalFrame={parts:[]}; playing=true; validToken=doc.token(); rememberSourceParameters(); scheduled=[]; startup=false;
}
doc.addEventListener('change',onDocumentChange);
export function testState(){return {design,phase,playing,ratePending,rateEditing,busy,actionConfirmation,operation:operationSerial};}
export function setPoseWait(promise){poseCompletion=promise;}
export function setRecovery(value){recovery=value;updateActions();}
export function pendingRecovery(){return recovery;}
export function setAnalysis(value){analysisActive=value;}
export function replaceSource(){design={...design};}
export function observeNumericField(key){
  const field={input:document.createElement('input'),feedback:document.createElement('div'),spec:schema.fields.find(f=>f.key===key)};
  fields.set(key,field);return field;
}
let scheduled=[]; export function scheduledGenerations(){return scheduled;}
refreshSchema=async()=>true; scheduleGeneration=delay=>scheduled.push(delay);
`;
const app=new vm.SourceTextModule(source);await app.link(path=>dependencies[path]??graph.resolve(path));await app.evaluate();const a=app.namespace;
const defer=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
const settle=()=>new Promise(resolve=>setImmediate(resolve));
let calls=[],rateGate=null,exportGate=null,qualityGate=null,generateGate=null,generateError=null,canonical;
const engine={failure:null,cancel(){},async request(method,payload){
  calls.push({method,payload:structuredClone(payload)});
  if(method==='catalog')return {project_format:'solidcraft-riduttori/1',families:[{...fixture.schema,key:'parallel'}]};
  if(method==='generate'){
    if(generateGate)await generateGate.promise;
    if(generateError)throw generateError;
    return {family:'parallel',design_id:99,values:payload.parameters,triangle_count:1,parts:[],buffers:[],motion:{supported:false,message:'fixture'}};
  }
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
  if(method==='quality'){if(qualityGate)await qualityGate.promise;return {design_id:payload.design_id+1,quality:payload.quality,buffers_retained:true,buffers:[]};}
  if(method==='import_project')throw Error('Invalid canonical module');
  throw Error('Unexpected request '+method);
}};
function reset(){calls=[];downloads.length=0;remembered.length=0;rateGate=exportGate=qualityGate=generateGate=generateError=null;canonical=structuredClone(fixture.values);el('app-dialog').close();a.initialize(fixture.schema,fixture.values,engine);}
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
const body=el('dialog-body').children[0];const format=body.children[0].children[1];format.value='stl';const scope=body.children[1].children[1];assert.equal(scope.value,'all');scope.value='selected';scope.dispatchEvent(new Event('change'));
choose('Download export');await dialog;assert.deepEqual(calls.map(c=>c.method),['rates','export']);
assert.deepEqual(calls[1].payload.indices,[0]);assert.equal((await downloaded()).parameters.input_rpm,45.1234567890123);

// Empty/stale subsets are never silently expanded to the whole model.
reset();assert.equal(await a.runExport('stl',[]),false);assert.deepEqual(calls,[]);
assert.equal(await a.runExport('step',[99]),false);assert.deepEqual(calls,[]);
assert.equal(await a.runExport('project',[0]),false);assert.deepEqual(calls,[]);
reset();const allDialog=a.exportDialog();await settle();choose('Download export');await allDialog;
assert.equal(Object.hasOwn(calls.at(-1).payload,'indices'),false);
reset();const staleDialog=a.exportDialog();await settle();
const staleScope=el('dialog-body').children[0].children[1].children[1];staleScope.value='selected';staleScope.dispatchEvent(new Event('change'));
a.testState().design.parts=[];choose('Download export');await staleDialog;assert.equal(downloads.length,0);
reset();const cancelledDialog=a.exportDialog();await settle();choose('Cancel');await cancelledDialog;
assert.equal(downloads.length,0);assert.deepEqual(calls,[]);

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
// rates. Alt+N avoids the browser new-window binding; Save supports Ctrl/Cmd.
const controller=new graph.modules['./controls.js'].namespace.ShortcutController({preferences:structuredClone(preferencesModule.namespace.DEFAULTS),blocked:()=>el('app-dialog').open,viewport:()=>false,changed(){},run:command=>{if(command==='save')a.saveProject();else if(command==='save-as')a.saveProject({saveAs:true});else if(command==='undo')a.doc.undo();else if(command==='redo')a.doc.redo();else if(command==='new')a.newDocument();}});
function key(key,{shift=false,meta=false,target=new Element()}={}){let prevented=false;controller.keydown({key,altKey:key==='n',ctrlKey:key!=='n'&&!meta,metaKey:key!=='n'&&meta,shiftKey:shift,target,preventDefault(){prevented=true;},stopImmediatePropagation(){}});return prevented;}
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
// Explicit Save confirms a pending graphical slider value before choosing the
// export snapshot, even if the pointer has not been released yet.
reset();const previewRevision=a.doc.revision;a.previewSpeed(321);
assert.equal(a.doc.revision,previewRevision);assert.equal(a.testState().design.values.input_rpm,fixture.values.input_rpm);
assert.equal(await a.saveProject(),true);assert.equal((await downloaded()).parameters.input_rpm,321);
// An export-only quality edit retains source buffers for future context restore,
// selection and the exact phase. No mechanical generation/rates RPC is needed.
globalThis.requestAnimationFrame=()=>1;
reset();const qualitySource=a.testState().design,qualityBuffers=qualitySource.buffers;
const qualityRaw=structuredClone(a.doc.entries);
a.doc.setQuality({export_mm:.005});await settle();
assert.equal(a.currentValid(),true);assert.equal(a.testState().design.buffers,qualityBuffers);
assert.equal(a.testState().design.parts,qualitySource.parts);assert.equal(a.testState().phase,1.234);
assert.deepEqual(a.doc.entries,qualityRaw);assert.deepEqual(calls.map(c=>c.method),['quality']);
// Undo back to an accepted precise source reuses its representation. The old
// invalid-field diagnostic must clear; Redo to the incomplete draft must still
// block export and display that diagnostic again.
reset();const preciseValues={...fixture.values,_decimal_inputs:{module:'2.00000000000000000001'}};
a.initialize(fixture.schema,preciseValues,engine);
const preciseSource=a.testState().design,preciseEntries=structuredClone(a.doc.entries);
const moduleField=a.observeNumericField('module');
a.doc.editNumber('module','-');await settle();await a.generateCurrent();
assert.equal(moduleField.input.attributes['aria-invalid'],'true');
assert.equal(moduleField.feedback.hidden,false);assert.equal(a.currentValid(),false);
assert(a.doc.undo());await settle();
assert.equal(a.currentValid(),true);assert.deepEqual(a.doc.entries,preciseEntries);
assert.equal(moduleField.input.attributes['aria-invalid'],'false');
assert.equal(moduleField.feedback.textContent,'');assert.equal(moduleField.feedback.hidden,true);
assert.equal(a.doc.values(fixture.schema).values._decimal_inputs.module,'2.00000000000000000001');
assert.equal(a.testState().design.buffers,preciseSource.buffers);
assert.equal(a.testState().design.parts,preciseSource.parts);
assert.deepEqual(calls.map(c=>c.method),['quality']);
assert(a.doc.redo());await settle();await a.generateCurrent();
assert.equal(moduleField.input.attributes['aria-invalid'],'true');
assert.equal(moduleField.feedback.hidden,false);assert.equal(a.currentValid(),false);
// A late quality reply cannot overwrite a newer mechanical edit.
reset();qualityGate=defer();const beforeQuality=a.testState().design;
a.doc.setQuality({export_mm:.005});await settle();a.doc.editNumber('module','3');qualityGate.resolve();await settle();
assert.equal(a.testState().design,beforeQuality);assert.equal(a.doc.entries.module.text,'3');assert.equal(a.currentValid(),false);
// A preset is an explicit one-step edit; unrelated precision and dimensions
// survive the construction-context switch, and unavailable proposals do nothing.
const presetSchema=structuredClone(fixture.schema);
presetSchema.fields.push(...['input_shaft','bore','width'].map(key=>({key,type:'number',default:10,minimum:0,maximum:100})));
presetSchema.options.push({key:'eccentric_design',type:'choice',default:'integral',choices:[{value:'integral'},{value:'keyed_shaft'}]});
a.initialize(presetSchema,{...fixture.values,input_shaft:4,bore:18,width:10},engine,'cycloidal');
a.doc.editNumber('width','10.1234567890123');
const prior=structuredClone(a.doc.state),presetPast=a.doc.past.length;
a.applyEccentricPreset({available:false,parameters:{eccentric_design:'keyed_shaft',input_shaft:12}});
assert.deepEqual(a.doc.state,prior);assert.equal(a.doc.past.length,presetPast);
a.applyEccentricPreset({available:true,parameters:{eccentric_design:'keyed_shaft',input_shaft:6}});
assert.equal(a.doc.draft.options.eccentric_design,'keyed_shaft');assert.equal(a.doc.entries.input_shaft.exact,6);
assert.equal(a.doc.entries.width.text,'10.1234567890123');assert.equal(a.doc.entries.bore.exact,18);
assert.equal(a.doc.past.length,presetPast+1);assert(a.doc.undo());assert.deepEqual(a.doc.state,prior);
assert.equal(a.schemaParameters().parameters.width,10.1234567890123);
assert.equal(a.schemaParameters().parameters.bore,18);assert.equal(a.schemaParameters().incomplete,false);
a.doc.editNumber('bore','-');assert.equal(a.schemaParameters().incomplete,true);
// Startup opens the actual modal. Deferring through Cancel, Escape or X keeps
// the source record, current document and the Project recovery action intact.
reset();edit('-');const draft=a.doc.recovery();draft.name='Deferred draft';
for(const close of ['Cancel','Escape','Close']) {
  reset();a.setRecovery(draft);const current=structuredClone(a.doc.state);
  const writes=recoveryWrites,clears=recoveryClears;
  const popup=close==='Cancel' ? a.boot() : a.recoverDocument();await settle();
  assert.equal(el('app-dialog').open,true);
  assert.equal(el('dialog-title').textContent,'Recover an unsaved design');
  if(close==='Cancel')choose('Cancel');
  else if(close==='Escape')el('app-dialog').dispatchEvent(new Event('cancel',{cancelable:true}));
  else el('dialog-close').onclick();
  await popup;assert.equal(el('app-dialog').open,false);
  assert.deepEqual(a.doc.state,current);assert.equal(a.pendingRecovery(),draft);
  assert.equal(el('recover-document').hidden,false);
  assert.equal(recoveryClears,clears);assert.equal(recoveryWrites,writes);
}
reset();a.setRecovery(draft);const restoring=a.recoverDocument();choose('Restore draft');await restoring;
assert.equal(a.doc.name,'Deferred draft');assert.equal(a.doc.entries.input_rpm.text,'-');
assert.equal(a.doc.dirty,true);assert.equal(a.pendingRecovery(),null);
assert.equal(el('recover-document').hidden,true);
reset();a.setRecovery(draft);const currentBeforeDismiss=structuredClone(a.doc.state),clears=recoveryClears;
const dismissing=a.recoverDocument();choose('Dismiss');await dismissing;
assert.deepEqual(a.doc.state,currentBeforeDismiss);assert.equal(a.pendingRecovery(),null);
assert.equal(recoveryClears,clears+1);assert.equal(el('recover-document').hidden,true);
reset();await a.boot();assert.equal(el('app-dialog').open,false);
// Actual generation catch and EngineError preserve producer fields regardless
// of prose/language; clearing, undo and late-result ownership remain unchanged.
const client=await graph.load('./engine-client.js');
for(const message of ['unrelated words','eccentric bore: testo italiano','任意文字']) {
  reset();const source=a.testState().design;
  const first=a.observeNumericField('module'),second=a.observeNumericField('width'),other=a.observeNumericField('bore');
  generateError=new client.namespace.EngineError({code:'invalid_geometry',kind:'geometry',constraint:'test.rule',fields:['module','width'],message,remedy:'Change the dimensions.',limits:{}});
  a.doc.editNumber('module','3');await settle();await a.generateCurrent();
  assert.equal(a.testState().design,source);assert.equal(a.currentValid(),false);
  for(const field of [first,second]) {
    assert.equal(field.input.attributes['aria-invalid'],'true');
    assert.equal(field.feedback.textContent,message+'\nChange the dimensions.');
  }
  assert.equal(other.input.attributes['aria-invalid'],'false');
  assert(a.doc.undo());await settle();generateError=null;await a.generateCurrent();assert.equal(a.currentValid(),true);
  for(const field of [first,second])assert.equal(field.feedback.hidden,true);
}
reset();const stale=a.observeNumericField('module');generateGate=defer();
generateError=new client.namespace.EngineError({code:'invalid_geometry',fields:['module'],message:'old error'});
a.doc.editNumber('module','3');await settle();const oldGeneration=a.generateCurrent();
a.doc.editNumber('module','4');generateGate.resolve();await oldGeneration;
assert.equal(stale.feedback.hidden,true);assert.equal(a.doc.entries.module.text,'4');
reset();const unassigned=a.observeNumericField('bore');
generateError=new client.namespace.EngineError({code:'internal_error',kind:'internal',message:'bore: equally spaced eccentric'});
a.doc.editNumber('module','3');await settle();await a.generateCurrent();
assert.equal(unassigned.input.attributes['aria-invalid'],'false');
reset();const shortField=a.observeNumericField('module');
generateError=new client.namespace.EngineError({code:'invalid_geometry',fields:['module'],message:'Full technical message',remedy:'Long explanation',summary:'Short summary',field_messages:{module:'Too large. Maximum: 10.'}});
a.doc.editNumber('module','3');await settle();await a.generateCurrent();
assert.equal(shortField.feedback.textContent,'Too large. Maximum: 10.');
assert.equal(generateError.message,'Short summary');
console.log('document action checks passed');
