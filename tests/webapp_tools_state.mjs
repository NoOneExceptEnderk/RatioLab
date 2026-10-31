// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
// Real controller/viewer modules under a small DOM/transport test double.
// This checks async ownership and buffer lifecycle, not browser/WebGL visuals.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const viewerModule=new vm.SourceTextModule(fs.readFileSync(root+'webapp/viewer.js','utf8'));
await viewerModule.link(()=>{throw Error('Unexpected viewer import');});await viewerModule.evaluate();
const toolsModule=new vm.SourceTextModule(fs.readFileSync(root+'webapp/tools.js','utf8'));
await toolsModule.link(()=>viewerModule);await toolsModule.evaluate();
const {preciseNumber,axisGrid,QueryState,initTools}=toolsModule.namespace;
const {cameraRay,ModelViewer,identityMatrix}=viewerModule.namespace;
for(const raw of ['','-','+','1e','1e-','NaN','Infinity','1,2,3','4x'])assert.throws(()=>preciseNumber(raw));
assert.equal(preciseNumber('31,1234567890123'),31.1234567890123);
assert.equal(preciseNumber('1.25e-3'),.00125);assert.throws(()=>preciseNumber('1.5','Count',true));
const draft={mode:'range',range:['60','62','2'],custom:'55,57'};
assert.equal(axisGrid(draft),'60:62:2');draft.mode='custom';assert.equal(axisGrid(draft),'55,57');draft.mode='range';assert.equal(axisGrid(draft),'60:62:2');
assert.throws(()=>axisGrid({mode:'range',range:['0','1000','1']}),/1000/);
assert.equal(axisGrid({mode:'locked'}),null);
let token={identity:'A',revision:1,operation:2,designId:3};
const matches=t=>JSON.stringify(t)===JSON.stringify(token),lease=new QueryState(matches);
const old=lease.begin('search','search',token);token.operation++;assert.equal(lease.finish(old,{query_id:'stale'}),false);
const run=lease.begin('search','search',token);assert.equal(lease.finish(run,{query_id:'fresh'}),true);assert.equal(lease.usable(),true);lease.invalidate();assert.equal(lease.usable(),false);

// Independently reproject points along each ray using the shader equations.
for(const [width,height]of [[900,400],[333,800],[720,720]])for(const yaw of [-1.71,0,.98])for(const pitch of [-2.2,0,.7])for(const [x,y]of [[-.9,.7],[0,0],[.85,-.6]]) {
  const state={width,height,yaw,pitch,center:[21,-8,3],radius:73,zoom:1.234};
  const ray=cameraRay(state,x,y);
  for(const distance of [0,73,513]) {
    const p=ray.ray_origin.map((v,i)=>v+distance*ray.ray_direction[i]-state.center[i]);
    const c=Math.cos(yaw),s=Math.sin(yaw),a=Math.cos(pitch),b=Math.sin(pitch),qx=c*p[0]-s*p[1],qy=s*p[0]+c*p[1];
    const camera=[qx,a*qy-b*p[2],b*qy+a*p[2]],scale=.86/state.radius*state.zoom,aspect=width/height;
    assert.ok(Math.abs(camera[0]*scale/Math.max(1,aspect)-x)<2e-14);
    assert.ok(Math.abs(camera[1]*scale*Math.min(1,aspect)-y)<2e-14);
    if(distance===0)assert.ok(Math.abs(-camera[2]/(state.radius*4)+1)<2e-14);
  }
}

class Custom extends Event{constructor(type,{detail}={}){super(type);this.detail=detail;}}
globalThis.CustomEvent=Custom;
const gls=[];
function graphics(){const log={uploads:[],deletes:0};const gl=new Proxy({NO_ERROR:0,COMPILE_STATUS:1,LINK_STATUS:2,getShaderParameter:()=>true,getProgramParameter:()=>true,getError:()=>0,createBuffer:()=>({}),createShader:()=>({}),createProgram:()=>({}),getAttribLocation:()=>0,getUniformLocation:()=>({}),bufferData:(_target,values)=>log.uploads.push([...values]),deleteBuffer:()=>log.deletes++},{get:(o,k)=>k in o?o[k]:()=>{}});gls.push(log);return gl;}
class Element extends EventTarget {
  constructor(tag){super();this.tagName=tag;this.children=[];this.dataset={};this.attributes={};this.disabled=false;this.hidden=false;this._value='';this.textContent='';this.parent=null;this.width=640;this.height=480;}
  get value(){if(this.tagName==='select' && !this.children.some(o=>String(o.value)===String(this._value)))return String(this.children[0]?.value??'');return this._value;}
  set value(v){this._value=String(v);}
  get options(){return this.children;}
  append(...nodes){for(const n of nodes){n.parent=this;this.children.push(n);}}
  prepend(...nodes){for(const n of nodes)n.parent=this;this.children.unshift(...nodes);}
  replaceChildren(...nodes){this.children=[];this.append(...nodes);}
  insertBefore(n,before){n.parent=this;this.children.splice(this.children.indexOf(before),0,n);}
  setAttribute(k,v){this.attributes[k]=String(v);}
  getAttribute(k){return this.attributes[k];}
  removeAttribute(k){delete this.attributes[k];}
  getBoundingClientRect(){return {left:0,top:0,width:640,height:480};}
  getContext(){return this.gl??=graphics();}
  focus(){}
  setPointerCapture(){}
  click(){if(!this.disabled)this.dispatchEvent(new Event('click'));}
}
const documentNodes=new Map(['show-supports','show-housing'].map(k=>[k,new Element('input')]));
let guideAccess=0;
globalThis.document={createElement:tag=>new Element(tag),getElementById:id=>{if(id==='viewport-grid'||id==='viewport-axes')guideAccess++;return documentNodes.get(id)||null;}};
globalThis.ResizeObserver=class{observe(){}disconnect(){}};
const events=new EventTarget(),engine=new EventTarget(),registry=new Map();
let valid=true,analysis=false,paused=0,cancelled=0,transaction=null,downloads=0,workerQuery=0,calls=[],pending=null,delayedApply=null,incompleteBacklash=false,applyError=null;
const rawEntries={module:{text:'2.0000000000000000',exact:2,typed:true},input_rpm:{text:'31.123456789012300',exact:31.1234567890123,typed:true}};
const originalRawEntries=structuredClone(rawEntries);
let snapshot={token:{identity:'doc',revision:1,operation:1,designId:7},phase:0,family:'parallel',parameters:{variant:'double',double_style:'joined',wheel:60,gap:0},design:{design_id:7,analysis:{signed_ratio:-3},parts:[{index:0,name:'Pinion'},{index:1,name:'Wheel'}]}};
let source={frame:{parts:[]},selected:new Set([1]),hidden:new Set([1]),supports:false,housing:false,section:true,explosion:.37,setSelection(indices){this.selected=new Set(indices);},applyFrame(frame){this.frame=frame;},addEventListener(){}};
const emit=(type,detail)=>events.dispatchEvent(new Custom(type,{detail}));
const schema={supported:true,variables:[{key:'wheel',label:'Wheel teeth',current:60,minimum:10,maximum:200,step:1}],settings:{target:3}};
const result=(method,data,text='Canonical report')=>({query_id:'q'+(++workerQuery),design_id:7,method,data,text,buffers:[]});
const searchResult=()=>result('search',{complete:false,partial:true,visited:1,total:2,reason:'candidate budget',proposals:[{ratio:-3.1,error_percent:3.333,xyz:[80,12,20],changes:{wheel:62}}]});
const api={events,engine,viewer:source,pickMode:'navigate',snapshot:()=>valid?structuredClone(snapshot):null,matches:t=>valid && JSON.stringify(t)===JSON.stringify(snapshot.token),registerTool:(key,c)=>registry.set(key,c),setDockPanel(){},setPlaying(){},async pauseForAnalysis(){paused++;},setAnalysisActive(v){analysis=v;},async requestPose(phase){snapshot.phase=phase;source.frame={parts:[],phase};return true;},restoreInspection(frame,phase,selection){source.frame=frame;snapshot.phase=phase;source.setSelection(selection);},refreshInspection(){},applyParameters(values){assert.equal(analysis,false);if(applyError)throw Error(applyError);for(const key of Object.keys(values))if(!['wheel','module','input_rpm','center_extra','variant','double_style'].includes(key))throw Error('Unknown parameter: '+key);for(const [key,value] of Object.entries(values))if(key in rawEntries)rawEntries[key]={text:String(value),exact:value,typed:false};transaction=values;snapshot.token.revision++;valid=false;emit('invalidate');},downloadBlob(){downloads++;},
  cancelOperations(){cancelled++;valid=false;emit('invalidate');if(pending){pending.reject(new DOMException('Cancelled','AbortError'));pending=null;}return new Promise(resolve=>setTimeout(()=>{snapshot.token.operation++;snapshot.token.designId++;snapshot.design.design_id++;valid=true;emit('design');resolve();},0));},
  async request(method,payload){calls.push({method,payload});if(['metrology','search','interference','backlash'].includes(method))emit('querybegin',{method});
    if(method==='search_schema')return structuredClone(schema);
    if(method==='search_apply'){if(delayedApply)return new Promise(resolve=>{delayedApply.resolve=resolve;});return {values:{wheel:62,gap:0,module:2,input_rpm:31.1234567890123,variant:'double',double_style:'joined'},changes:{wheel:62}};}
    if(method==='proposal_apply')return {center_extra:.30000000000000426};
    if(method==='query_export')return {name:'query.txt',mime:'text/plain',buffer:0,buffers:[new Uint8Array([65]).buffer]};
    if(pending)return pending.promise;
    if(method==='search')return searchResult();
    if(method==='metrology')return result(method,{status:'unsupported'},'Unsupported canonical theory');
    if(method==='interference')return result(method,{coverage_complete:false,completed_poses:1,planned_poses:2,completed_pairs:1,issues:['Limit reached'],rows:[{part_a:'Pinion',part_b:'Wheel',index_a:0,index_b:1,kind:'boundary',distance:.01,phase_degrees:30}]});
    if(method==='backlash'){const f=new Float32Array([123,0,0,0,1,0,0,0,1]);return {...result(method,{status:incompleteBacklash?'incomplete':'ready',reason:incompleteBacklash?'Pose limit':'Canonical check complete',applicable:!incompleteBacklash,proposal_id:'proposal',interference:{coverage_complete:!incompleteBacklash}}),candidate:{motion:{},parts:[{index:0,color:[1,1,1],role:'gear',bounds_mm:{minimum:[0,0,0],maximum:[123,1,1]},mesh:{positions:0,normals:1,vertex_count:3}}]},buffers:[f.buffer,new Float32Array(9).buffer]};}
    throw Error('Unexpected method '+method);
  }};
const tools=initTools(api),p=tools.panels;
const settle=async()=>{await new Promise(resolve=>setTimeout(resolve,5));};
const formEdit=panel=>panel.form.dispatchEvent(new Event('input'));
const defer=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};

await registry.get('search').open();const search=p.get('search');
assert.equal(search.axes.get('wheel').mode,'locked');
search.axes.get('wheel').mode='range';search.axes.get('wheel').range=['60','62','2'];
search.run.click();await settle();assert.match(search.summary.textContent,/PARTIAL/);assert.match(search.summary.textContent,/1\/2/);assert.equal(search.apply.disabled,true);
search.rows.children[0].click();assert.equal(search.apply.disabled,false);search.downloads[0].click();await settle();assert.equal(downloads,1);
// A failed editor transaction preserves the valid query and selected proposal,
// reports the error, and permits retry rather than displaying success.
const retainedResult=tools.state.result,retainedRow=search.rows.children[0],retainedQueryId=search.summary.dataset.queryId;
applyError='Editor validation failed';search.apply.click();await settle();
assert.equal(transaction,null);assert.equal(tools.state.result,retainedResult);assert.equal(search.rows.children[0],retainedRow);assert.equal(search.selected,0);assert.equal(search.summary.dataset.queryId,retainedQueryId);assert.equal(search.summary.textContent,applyError);assert.equal(search.apply.disabled,false);assert.equal(search.downloads[0].disabled,false);assert.equal(tools.state.run,null);assert.equal(analysis,false);
applyError=null;search.apply.click();await settle();assert.deepEqual(transaction,{wheel:62});assert.deepEqual(rawEntries,originalRawEntries);assert.ok(calls.some(c=>c.method==='search_apply'&&c.payload.query_id));assert.equal(search.apply.disabled,true);assert.match(search.summary.textContent,/Proposal applied/);
valid=true;emit('design');await settle();
// Any raw form edit invalidates all query/download/apply capabilities at once.
search.run.click();await settle();search.rows.children[0].click();search.fields.target.input.value='-';formEdit(search);assert.equal(search.apply.disabled,true);assert.ok(search.downloads.every(b=>b.disabled));
const before=calls.length;search.run.click();await settle();assert.equal(calls.length,before);assert.match(search.summary.textContent,/complete number/);
search.fields.target.input.value='3,1234567890123';formEdit(search);search.run.click();await settle();assert.equal(calls.findLast(c=>c.method==='search').payload.settings.target,3.1234567890123);
// Range/Custom drafts survive switches and source refresh in the same context.
search.axes.get('wheel').custom='61,63';search.axes.get('wheel').mode='custom';formEdit(search);await registry.get('metrology').open();await registry.get('search').open();assert.deepEqual(search.axes.get('wheel').range,['60','62','2']);assert.equal(search.axes.get('wheel').custom,'61,63');
// Cancel hard-terminates, rebuilds current drafts and permits retry, with no Apply.
pending=defer();search.run.click();await settle();assert.equal(analysis,true);assert.equal(search.cancel.disabled,false);search.fields.x.input.value='999';formEdit(search);await settle();assert.equal(cancelled,1);assert.equal(analysis,false);assert.equal(search.apply.disabled,true);assert.equal(search.run.disabled,false);assert.equal(transaction.wheel,62);
search.run.click();await settle();assert.equal(search.downloads[0].disabled,false);
// A result arriving after source invalidation cannot reinstall stale UI.
pending=defer();const late=pending;search.run.click();await settle();valid=false;emit('invalidate');late.resolve(searchResult());pending=null;await settle();assert.equal(tools.state.result,null);assert.equal(search.apply.disabled,true);assert.ok(search.downloads.every(b=>b.disabled));valid=true;emit('design');await settle();
// Revalidation returning after form edit cannot make a document transaction.
search.run.click();await settle();search.rows.children[0].click();delayedApply={};search.apply.click();await settle();const originalTransaction=transaction;formEdit(search);delayedApply.resolve({values:{wheel:999},changes:{wheel:999}});delayedApply=null;await settle();assert.equal(transaction,originalTransaction);
// Canonical unsupported metrology is shown and remains downloadable.
await registry.get('metrology').open();const metrology=p.get('metrology');assert.equal(metrology.fields.source_index.input.options.length,2);metrology.run.click();await settle();assert.match(metrology.summary.textContent,/Unsupported canonical theory/);assert.equal(metrology.downloads[0].disabled,false);
// Starting a different query immediately revokes the previous query's downloads.
emit('querybegin',{method:'documents'});assert.ok(metrology.downloads.every(b=>b.disabled));
await registry.get('interference').open();const check=p.get('interference');check.run.click();await settle();assert.match(check.summary.textContent,/INCOMPLETE/);assert.equal(check.rows.children[0].dataset.sourcePair,'0,1');
const priorFrame=structuredClone(source.frame);check.rows.children[0].click();await settle();assert.equal(snapshot.phase,Math.PI/6);assert.deepEqual([...source.selected],[0,1]);assert.equal(source.section,false);assert.equal(source.explosion,0);assert.equal(source.supports,true);assert.equal(source.hidden.size,0);
check.rows.children.at(-1).click();assert.equal(snapshot.phase,0);assert.deepEqual(source.frame,priorFrame);assert.deepEqual([...source.selected],[1]);assert.deepEqual([...source.hidden],[1]);assert.equal(source.section,true);assert.equal(source.explosion,.37);
// Candidate uses its own transferred channels, never replaces source, and frees
// every uploaded buffer on invalidation. Its render never touches global guides.
await registry.get('backlash').open();const backlash=p.get('backlash'),originalSource=api.viewer;backlash.run.click();await settle();assert.equal(backlash.apply.disabled,false);assert.equal(api.viewer,originalSource);assert.equal(guideAccess,0);const candidateGL=gls.at(-1);assert.equal(candidateGL.uploads[0][0],123);assert.equal(candidateGL.deletes,0);formEdit(backlash);assert.equal(candidateGL.deletes,2);assert.equal(backlash.preview.children.length,0);assert.equal(backlash.apply.disabled,true);
incompleteBacklash=true;backlash.run.click();await settle();assert.equal(backlash.apply.disabled,true);assert.match(backlash.summary.textContent,/INCOMPLETE/);assert.equal(backlash.downloads[0].disabled,false);formEdit(backlash);incompleteBacklash=false;
backlash.run.click();await settle();backlash.apply.click();await settle();assert.deepEqual(transaction,{center_extra:.30000000000000426});
assert.ok(paused>=8);assert.equal(analysis,false);

// Actual viewer pick payload follows rendered transforms, exploded placement,
// world section and explicit visible indices; camera/pose/visibility changes
// alter the key used to reject asynchronous stale samples.
const canvas=new Element('canvas'),viewer=new ModelViewer(canvas);viewer.guides=false;
const part=(index,role)=>({index,role,color:[1,1,1],bounds_mm:{minimum:[0,0,0],maximum:[3,4,5]},mesh:{positions:index*2,normals:index*2+1,vertex_count:3}});
const buffers=Array.from({length:4},()=>new Float32Array([0,0,0,3,0,0,0,4,5]).buffer);
viewer.setDesign({motion:{},parts:[part(0,'gear'),part(1,'support')],buffers});
const matrix=identityMatrix();matrix[12]=12.3456789012345;
viewer.applyFrame({parts:[{index:0,matrix},{index:1,matrix:identityMatrix()}]});viewer.section=true;viewer.explosion=.37;
const picked=viewer.pickState(200,150);assert.deepEqual(picked.payload.visible_indices,[0]);assert.deepEqual(picked.payload.matrices,[{index:0,matrix}]);assert.equal(picked.payload.section_y,viewer.center[1]);assert.equal(picked.payload.animated,true);assert.deepEqual(picked.payload.explosion_offsets[0].offset,viewer.explosionOffset(viewer.design.parts[0]));
viewer.yaw+=.1;assert.notEqual(viewer.pickState(200,150).key,picked.key);viewer.yaw-=.1;viewer.setVisibility(0,false);assert.deepEqual(viewer.pickState(200,150).payload.visible_indices,[]);viewer.dispose();
console.log('Tools state, cancellation, canonical Apply gates, candidate resources and inverse-camera checks passed.');
