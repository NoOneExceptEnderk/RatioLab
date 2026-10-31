// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
import {ModelViewer, identityMatrix} from './viewer.js';

const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
const copy=value=>structuredClone(value);
const abort=()=>new DOMException('This operation is no longer current.','AbortError');
const titles={metrology:'Gear metrology',search:'Find combinations',interference:'Check interference',backlash:'Solve working backlash'};
const checkFields=[['step_degrees','Phase step (°)','30'],['tolerance_mm','Boundary tolerance (mm)','0.01'],['max_poses','Maximum poses','721',true],['max_seconds','Time limit (s)','120'],['max_triangles','Maximum triangles','300000',true],['max_parts','Maximum parts','128',true]];

// Do not let Number(''), parseFloat('1e') or formatting silently accept drafts.
export function preciseNumber(text,label='Value',integer=false) {
  const raw=String(text).trim().replace(',','.');
  if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(raw)) throw Error(label+': enter a complete number.');
  const number=Number(raw);
  if (!Number.isFinite(number) || integer && !Number.isInteger(number)) throw Error(label+': enter a finite '+(integer?'integer.':'number.'));
  return number;
}
export function axisGrid(draft) {
  if (draft.mode==='locked') return null;
  if (draft.mode==='custom') {
    if (!draft.custom.trim()) throw Error('Enter a finite custom grid.');
    // Commas here separate values; the engine owns canonical finite-grid parsing.
    return draft.custom;
  }
  const values=draft.range.map((value,i)=>preciseNumber(value,['From','To','Step'][i]));
  if (values[2]<=0 || values[1]<values[0]) throw Error('Range requires From ≤ To and a positive Step.');
  if ((values[1]-values[0])/values[2]>=1000) throw Error('At most 1000 values per variable.');
  return values.join(':');
}

/** One latest-query lease, bound to the entire document/operation/source token. */
export class QueryState {
  constructor(matches){this.matches=matches;this.serial=0;this.run=null;this.result=null;}
  invalidate(){++this.serial;this.run=null;this.result=null;}
  begin(panel,method,token){this.invalidate();return this.run={serial:this.serial,panel,method,token:copy(token),started:performance.now()};}
  current(run){return this.run===run && run.serial===this.serial && this.matches(run.token);}
  finish(run,response){if(!this.current(run))return false;this.run=null;this.result={...response,panel:run.panel,token:run.token,serial:run.serial};return true;}
  usable(result=this.result){return !!result && result===this.result && result.serial===this.serial && this.matches(result.token);}
}

export function initTools(api) {
  const state=new QueryState(token=>api.matches(token)), panels=new Map();
  let active=null,recovery=null,preview=null,savedView=null,inspectionSerial=0,pickSerial=0,samples=[],sampleKey=null,pickMessage='Click a visible sampled surface.',nominalInspection=false;
  const current=()=>api.snapshot();
  function button(text,action,cls='') {const b=el('button',text,cls);b.type='button';b.addEventListener('click',action);return b;}
  function field(panel,key,label,value,{integer=false,select=null}={}) {
    const row=el('label',null,'tool-field'),name=el('span',label),input=el(select?'select':'input');
    input.id=`${panel.key}-${key}`;input.name=key;row.htmlFor=input.id;
    if(select)for(const [value,text] of select){const o=el('option',text);o.value=value;input.append(o);}
    else{input.type='text';input.inputMode=integer?'numeric':'decimal';input.autocomplete='off';input.spellcheck=false;}
    input.value=String(value);row.append(name,input);panel.fields[key]={input,label,integer};return row;
  }
  function value(p,key){const f=p.fields[key];return preciseNumber(f.input.value,f.label,f.integer);}
  function disposePreview(){if(preview){preview.dispose();preview=null;}for(const p of panels.values())p.preview?.replaceChildren();}
  function applySavedView(saved) {
    // Raw edits can make matches() false while the exact old source remains in
    // the stale preview. Restore that displayed object's transient frame too;
    // never identify a replacement worker/source by a recycled numeric ID.
    if(!api.matches(saved.token) && !(saved.source && api.viewer.design===saved.source))return;
    Object.assign(api.viewer,saved.options);api.viewer.hidden=new Set(saved.hidden);
    for(const [id,key]of [['show-supports','supports'],['show-housing','housing'],['section-view','section']]){const input=document.getElementById(id);if(input)input.checked=saved.options[key];}
    const explosion=document.getElementById('explosion');if(explosion)explosion.value=String(saved.options.explosion);
    api.restoreInspection(saved.frame,saved.phase,saved.selection);
  }
  function restoreView() {
    ++inspectionSerial;
    if(savedView)applySavedView(savedView);
    savedView=null;nominalInspection=false;
  }
  function rememberView() {
    const snapshot=current();if(!snapshot || !api.viewer.frame)return null;
    if(!savedView)savedView={token:copy(snapshot.token),source:api.viewer.design,frame:copy(api.viewer.frame),phase:snapshot.phase,selection:[...api.viewer.selected],hidden:[...api.viewer.hidden],options:{supports:api.viewer.supports,housing:api.viewer.housing,section:api.viewer.section,explosion:api.viewer.explosion}};
    return savedView;
  }
  function clearResults(message='Settings changed · run again.') {
    state.result=null;disposePreview();restoreView();
    for(const p of panels.values()) {p.selected=null;p.rows.replaceChildren();p.report.textContent='';p.summary.textContent=message;delete p.summary.dataset.queryId;p.progress.hidden=state.run?.panel!==p.key;p.progress.value=0;p.elapsed.textContent='';for(const b of p.downloads)b.disabled=true;if(p.apply)p.apply.disabled=true;}
  }
  function controls() {
    for(const p of panels.values()) {
      p.run.disabled=!!state.run || !!recovery || !current() || p.key==='search' && !p.searchSchema?.supported;
      p.cancel.disabled=state.run?.panel!==p.key;
      if(p.apply)p.apply.disabled=!state.usable() || state.result.panel!==p.key || p.key==='search' && p.selected==null || p.key==='backlash' && !state.result?.data.applicable;
      for(const b of p.downloads)b.disabled=!state.usable() || state.result.panel!==p.key;
    }
  }
  function drop(message,{source=false}={}) {
    const running=!!state.run;state.invalidate();clearResults(message);controls();
    if(running && !source)hardCancel(message);
  }
  async function hardCancel(message='Cancelled · restoring the current model…') {
    state.invalidate();clearResults(message);api.setAnalysisActive(false);
    if(!recovery) {
      // Set a sentinel before cancelOperations synchronously emits invalidate.
      recovery=Promise.resolve();controls();
      const pending=api.cancelOperations();recovery=pending;
      try{await pending;}finally{if(recovery===pending){recovery=null;controls();}}
    }
  }
  function edited(p) {
    if(p.populating)return;
    drop('Settings changed · results cleared. Run again with these drafts.');
  }
  function panel(key,intro) {
    const p={key,fields:{},downloads:[],selected:null,root:el('div',null,'analysis-tool'),form:el('div',null,'tool-form'),rows:el('div',null,'tool-rows'),report:el('pre',null,'tool-report'),summary:el('p','Choose settings, then run.','tool-summary')};
    p.root.id=`tool-${key}`;p.root.append(el('h3',titles[key]),el('p',intro,'tool-note'),p.form);
    p.form.addEventListener('input',()=>edited(p));p.form.addEventListener('change',()=>edited(p));
    const actions=el('div',null,'tool-actions');p.run=button(key==='search'?'Search':key==='metrology'?'Calculate':key==='backlash'?'Solve':'Check cycle',()=>run(p));p.run.id=`${key}-run`;
    p.cancel=button('Cancel',()=>hardCancel());p.cancel.id=`${key}-cancel`;p.cancel.disabled=true;actions.append(p.run,p.cancel);
    p.progress=el('progress');p.progress.max=1;p.progress.value=0;p.progress.hidden=true;p.elapsed=el('span','','tool-note');
    p.root.append(actions,p.summary,p.progress,p.elapsed,p.rows);
    const downloads=el('div',null,'tool-actions');
    for(const format of ['txt','json']){const b=button('Download '+format.toUpperCase(),()=>download(p,format));b.id=`${key}-download-${format}`;b.disabled=true;p.downloads.push(b);downloads.append(b);}
    const report=el('details');report.append(el('summary','Full report'),p.report);p.root.append(downloads,report);
    panels.set(key,p);api.registerTool(key,{label:titles[key]+'…',open:()=>open(p)});return p;
  }
  async function open(p) {
    if(active!==p.key){drop('Tool changed · run a fresh query.');active=p.key;}
    api.setDockPanel(p.key,p.root,{title:titles[p.key]});
    if(p.key==='search')await loadSearch(p);
    if(p.key==='metrology')populateParts(p);
    if(p.key==='backlash' && !p.targetInitialized) {
      const target=current()?.design.analysis.meshes?.[0]?.working_pair_backlash_mm;
      p.fields.desired_backlash_mm.input.value=String(Number.isFinite(target)?target:.3);p.targetInitialized=true;
    }
    controls();
  }
  function settings(p){return Object.fromEntries(checkFields.map(([key])=>[key,value(p,key)]));}
  function requestPayload(p) {
    if(p.key==='metrology') {
      const payload={source_index:value(p,'source_index'),gauge_type:p.fields.gauge_type.input.value};
      if(p.fields.gauge_mode.input.value==='explicit')payload.gauge_diameter=value(p,'gauge_diameter');return payload;
    }
    if(p.key==='search') {
      const grids={};for(const [key,d] of p.axes){const grid=axisGrid(d);if(grid!=null)grids[key]=grid;}
      if(!Object.keys(grids).length)throw Error('Choose Range or Custom for at least one parameter. Locked parameters stay at the current model.');
      return {grids,settings:{target:value(p,'target'),tolerance_percent:value(p,'tolerance_percent'),direction:p.fields.direction.input.value,max_xyz:['x','y','z'].map(key=>value(p,key)),max_candidates:value(p,'max_candidates'),max_seconds:value(p,'max_seconds'),max_results:value(p,'max_results')}};
    }
    const payload={settings:settings(p)};if(p.key==='backlash')payload.desired_backlash_mm=value(p,'desired_backlash_mm');return payload;
  }
  async function run(p) {
    if(state.run || recovery || active!==p.key)return;
    let payload;try{payload=requestPayload(p);}catch(error){drop(error.message);return;}
    const snapshot=current();if(!snapshot){p.summary.textContent='Complete the model fields and wait for valid geometry.';return;}
    clearResults('Preparing analysis…');const run=state.begin(p.key,p.key,snapshot.token);api.setAnalysisActive(true);controls();
    p.progress.hidden=false;p.progress.removeAttribute('value');
    const timer=setInterval(()=>{if(state.current(run))p.elapsed.textContent=`${((performance.now()-run.started)/1000).toFixed(1)} s elapsed`;},200);
    try {
      await api.pauseForAnalysis();if(!state.current(run))return;
      const result=await api.request(p.key,payload);
      if(active!==p.key || !state.finish(run,result))return;
      p.progress.value=1;p.report.textContent=result.text;present(p,state.result);p.summary.dataset.queryId=result.query_id;
    } catch(error) {
      if(state.current(run)){
        if(api.engine.failure)await hardCancel(error.message+' · restoring the current model…');
        else{state.invalidate();clearResults(error.name==='AbortError'?'Operation cancelled.':error.message);}
      }
    } finally {
      clearInterval(timer);
      if(state.run===run)state.run=null;
      // An older finally must never unlock a replacement run.
      if(!state.run)api.setAnalysisActive(false);
      controls();
    }
  }
  function present(p,result) {
    const d=result.data;
    if(p.key==='metrology')p.summary.textContent=result.text;
    if(p.key==='search') {
      p.summary.textContent=`${d.complete?'Complete finite domain':'PARTIAL search'} · ${d.visited}/${d.total} visited · ${d.proposals.length} retained. ${d.reason||''} Ranking covers this finite domain only.`;
      for(const [index,row] of d.proposals.entries()) {
        const b=button(`Ratio ${row.ratio} · error ${row.error_percent}%\nXYZ ${row.xyz.join(' × ')} mm\nChanges: ${JSON.stringify(row.changes)}`,()=>{if(!state.usable(result))return;p.selected=index;for(const r of p.rows.children)r.setAttribute('aria-pressed',String(r===b));controls();},'tool-result');
        b.dataset.proposalIndex=index;b.setAttribute('aria-pressed','false');p.rows.append(b);
      }
    }
    if(p.key==='interference') {
      p.summary.textContent=`${d.coverage_complete?'Complete sampled coverage':'INCOMPLETE / unsupported coverage'} · ${d.completed_poses}/${d.planned_poses} poses · ${d.completed_pairs} pair checks. ${d.issues.join(' ')} Discrete samples only.`;
      for(const row of d.rows) {
        const b=button(`${row.part_a} ↔ ${row.part_b}\n${row.kind} · ${row.distance} mm · phase ${row.phase_degrees}°\n${row.expected||'No expected interface identified'}`,()=>inspect(p,result,row),'tool-result');
        b.dataset.sourcePair=`${row.index_a},${row.index_b}`;p.rows.append(b);
      }
      p.rows.append(button('Restore preview',restoreView));
    }
    if(p.key==='backlash') {
      p.summary.textContent=`${d.status.toUpperCase()}: ${d.reason} ${d.interference && !d.interference.coverage_complete?'INCOMPLETE sampled check · Apply unavailable.':''}`;
      if(result.candidate) {
        const canvas=el('canvas');canvas.tabIndex=0;canvas.setAttribute('aria-label','Proposed model · separate nominal preview');p.preview.append(el('p','Proposed model · nominal preview; source unchanged.','tool-note'),canvas);
        try{preview=new ModelViewer(canvas);preview.guides=false;preview.supports=true;preview.housing=true;preview.setDesign({...result.candidate,buffers:result.buffers});}
        catch(error){disposePreview();p.preview.append(el('p','Candidate preview unavailable: '+error.message,'tool-note'));}
      }
    }
  }
  async function inspect(p,result,row) {
    if(!state.usable(result) || active!==p.key)return;
    await api.pauseForAnalysis();if(!state.usable(result))return;
    const saved=rememberView();if(!saved)return;const serial=++inspectionSerial;
    api.viewer.hidden.clear();api.viewer.supports=api.viewer.housing=true;api.viewer.section=false;api.viewer.explosion=0;
    for(const id of ['show-supports','show-housing']){const input=document.getElementById(id);if(input)input.checked=true;}
    const section=document.getElementById('section-view');if(section)section.checked=false;const explosion=document.getElementById('explosion');if(explosion)explosion.value='0';
    const ok=await api.requestPose(row.phase_degrees*Math.PI/180);
    if(serial!==inspectionSerial || !state.usable(result) || active!==p.key){applySavedView(saved);return;}
    if(ok){api.viewer.setSelection([row.index_a,row.index_b]);api.refreshInspection();}
  }
  async function apply(p) {
    const result=state.result;
    if(!state.usable(result) || result.panel!==p.key || recovery || state.run)return;
    const index=p.selected;if(p.key==='search' && index==null || p.key==='backlash' && !result.data.applicable)return;
    p.apply.disabled=true;api.setAnalysisActive(true);
    // Revalidation may regenerate geometry too; it shares the same cancellation
    // lease as queries, while preserving the queried result until it succeeds.
    const run={serial:state.serial,panel:p.key,method:p.key==='search'?'search_apply':'proposal_apply',token:copy(result.token),started:performance.now()};state.run=run;controls();
    try {
      const answer=await api.request(run.method,p.key==='search'?{query_id:result.query_id,proposal_index:index}:{proposal_id:result.data.proposal_id});
      if(!state.current(run) || active!==p.key || !state.usable(result))return;
      api.setAnalysisActive(false);
      api.applyParameters(p.key==='search'?answer.changes:{center_extra:answer.center_extra});
      state.invalidate();clearResults('Proposal applied · regenerate to run a new query.');
    }catch(error){if(state.current(run)){state.run=null;p.summary.textContent=error.message;}}
    finally{if(state.run===run)state.run=null;if(!state.run)api.setAnalysisActive(false);controls();}
  }
  async function download(p,format) {
    const result=state.result;if(!state.usable(result) || result.panel!==p.key || state.run || recovery)return;
    try {
      const answer=await api.request('query_export',{query_id:result.query_id,format});
      if(!state.usable(result) || active!==p.key)return;
      api.downloadBlob(new Blob([answer.buffers[answer.buffer]],{type:answer.mime}),answer.name);
    }catch(error){if(state.usable(result))drop(error.message);}
  }
  function populateParts(p) {
    const select=p.fields.source_index.input,snapshot=current();
    const previous=select.value;select.replaceChildren();
    for(const part of snapshot?.design.parts??[]){const o=el('option',`${part.index+1} · ${part.name}`);o.value=part.index;select.append(o);}
    if([...select.options].some(o=>o.value===previous))select.value=previous;
  }
  async function loadSearch(p) {
    if(recovery || state.run || !current())return;
    const snapshot=current(),serial=++p.schemaSerial;
    try {
      const schema=await api.request('search_schema');
      if(serial!==p.schemaSerial || !api.matches(snapshot.token))return;
      p.searchSchema=schema;
      const key=JSON.stringify([snapshot.family,snapshot.parameters.variant,snapshot.parameters.double_style,snapshot.parameters.io_scheme,snapshot.parameters.io_scheme2]);
      if(key!==p.formKey){p.axes=new Map();p.formKey=key;p.fields.target.input.value=String(Math.abs(snapshot.design.analysis.signed_ratio)||schema.settings.target);}
      p.axesBox.replaceChildren();
      for(const spec of schema.variables) {
        let d=p.axes.get(spec.key);if(!d){d={mode:'locked',range:[String(spec.current),String(spec.current),String(spec.step)],custom:String(spec.current)};p.axes.set(spec.key,d);}
        const box=el('fieldset',null,'tool-axis');box.append(el('legend',spec.label),el('p',`Current ${spec.current} · allowed ${spec.minimum}–${spec.maximum}`,'tool-note'));
        const mode=el('select');mode.setAttribute('aria-label',spec.label+' mode');mode.id=`search-axis-${spec.key}`;
        for(const [key,title]of [['locked','Locked'],['range','Range'],['custom','Custom']]){const o=el('option',title);o.value=key;mode.append(o);}mode.value=d.mode;
        const range=el('div',null,'tool-range'),custom=el('input');custom.type='text';custom.value=d.custom;custom.placeholder='20,24,28 or 20:28:2';custom.setAttribute('aria-label',spec.label+' custom grid');
        for(const [i,title] of ['From','To','Step'].entries()){const label=el('label',title),input=el('input');input.type='text';input.inputMode='decimal';input.value=d.range[i];input.setAttribute('aria-label',spec.label+' '+title);input.addEventListener('input',()=>d.range[i]=input.value);label.append(input);range.append(label);}
        const visibility=()=>{range.hidden=d.mode!=='range';custom.hidden=d.mode!=='custom';};mode.addEventListener('change',()=>{d.mode=mode.value;visibility();});custom.addEventListener('input',()=>d.custom=custom.value);visibility();box.append(mode,range,custom);p.axesBox.append(box);
      }
      p.context.textContent=schema.supported?'All other dimensions, variants, stages and input/output arrangements stay fixed. Each axis has at most 1000 values.':'This family has no supported single-ratio finite search.';controls();
    }catch(error){if(serial===p.schemaSerial && api.matches(snapshot.token))p.summary.textContent=error.message;}
  }

  const m=panel('metrology','Measure involute gear geometry using the selected component. Unsupported profiles and theory limits are reported explicitly.');
  m.form.append(field(m,'source_index','Component',0,{integer:true,select:[]}),field(m,'gauge_type','Gauge','ball',{select:[['ball','Ball'],['roller','Roller']]}),field(m,'gauge_mode','Gauge diameter','default',{select:[['default','Recommended diameter'],['explicit','Specify diameter (mm)']]}),field(m,'gauge_diameter','Diameter (mm)','3'));
  const gauge=()=>{m.fields.gauge_diameter.input.disabled=m.fields.gauge_mode.input.value!=='explicit';};m.fields.gauge_mode.input.addEventListener('change',gauge);gauge();
  const s=panel('search','Explore explicit finite combinations for a target ratio and nominal overall size. A partial run can retain valid candidates; it does not establish a global optimum.');
  s.axes=new Map();s.schemaSerial=0;
  s.form.append(field(s,'target','Desired |input / output|','3'),field(s,'tolerance_percent','Allowed error ± (%)','1'),field(s,'direction','Output direction','either',{select:[['either','Either direction'],['same','Same (+)'],['opposite','Opposite (−)']]}));
  for(const key of ['x','y','z'])s.form.append(field(s,key,`Maximum ${key.toUpperCase()} (mm)`,'1000'));
  s.form.append(el('p','Size includes all generated components, including supports and housing, in the nominal export pose. It is a sampled envelope, not a motion sweep.','tool-note'));
  s.context=el('p',null,'tool-note');s.axesBox=el('div');s.form.append(s.context,s.axesBox);
  for(const [key,label,v,integer]of [['max_candidates','Maximum candidates','50000',true],['max_seconds','Time limit (s)','30',false],['max_results','Retained results (max 100)','100',true]])s.form.append(field(s,key,label,v,{integer}));
  s.apply=button('Apply selected combination',()=>apply(s));s.apply.id='search-apply';s.apply.disabled=true;s.root.append(s.apply);
  const i=panel('interference','Check every component, including hidden supports and housing, over discrete poses of the labelled kinematic period. Boundary contact remains unresolved. Samples can miss collisions between poses.');
  const b=panel('backlash','Parallel external spur, helical and double helix pairs. Target transverse tangential working backlash by adjusting centre spacing. The candidate stays separate until Apply.');
  b.form.append(field(b,'desired_backlash_mm','Desired working backlash (mm)','0.1'));
  for(const p of [i,b])for(const [key,label,v,integer]of checkFields)p.form.append(field(p,key,label,p===b && key==='max_seconds'?'60':v,{integer}));
  b.preview=el('div',null,'candidate-preview');b.root.insertBefore(b.preview,b.rows);
  b.apply=button('Apply proposed centre spacing',()=>apply(b));b.apply.id='backlash-apply';b.apply.disabled=true;b.root.append(b.apply);

  api.engine.addEventListener('progress',({detail})=>{const run=state.run;if(!run || !state.current(run) || detail.stage!=='analysis' || detail.method!==run.method)return;const p=panels.get(run.panel);p.summary.textContent=detail.message||detail.detail;if(Number.isFinite(detail.fraction))p.progress.value=Math.max(0,Math.min(1,detail.fraction));});
  api.events.addEventListener('querybegin',()=>{clearResults('A new query superseded the previous report.');controls();});
  api.events.addEventListener('invalidate',()=>{++pickSerial;samples=[];sampleKey=null;pickMessage='Model changed · samples cleared.';state.invalidate();clearResults('Model changed · run a new query.');controls();});
  api.events.addEventListener('design',()=>{samples=[];sampleKey=null;if(active==='metrology')populateParts(m);if(active==='search')loadSearch(s);controls();});
  api.events.addEventListener('toolswitch',({detail})=>{if(active && detail.key!==active){drop('Tool changed · run a fresh query.');active=null;}if(detail.key!=='components'){++pickSerial;samples=[];sampleKey=null;}});
  api.events.addEventListener('toolclose',()=>{drop('Tool closed.');active=null;++pickSerial;samples=[];sampleKey=null;restoreView();});
  api.events.addEventListener('playstart',()=>{restoreView();++pickSerial;samples=[];sampleKey=null;});

  function surfaceControls(panel) {
    const body=el('div',null,'surface-tools'),actions=el('div',null,'tool-actions');
    const isolate=button('Isolate selected',()=>{if(!api.viewer.selected.size)return;for(const part of api.viewer.design.parts)api.viewer.hidden[api.viewer.selected.has(part.index)?'delete':'add'](part.index);api.viewer.render();api.refreshInspection();});isolate.disabled=!api.viewer.selected.size;
    actions.append(isolate,button('Show all',()=>{api.viewer.hidden.clear();api.viewer.supports=api.viewer.housing=true;for(const id of ['show-supports','show-housing'])document.getElementById(id).checked=true;api.viewer.render();api.refreshInspection();}));
    body.append(actions);
    if(api.pickMode!=='navigate') {
      body.append(el('p',api.pickMode==='measure'?'Choose two surface points. Distance is point-to-point Euclidean distance between sampled facets; it is not the minimum gap.':'Click a visible surface to select its component. Ctrl / Shift adds or removes. Drag to orbit.','tool-note'),el('p',pickMessage,'surface-message'));
      for(const [index,point]of samples.entries())body.append(el('p',`Point ${index+1}: [${point.join(', ')}] mm`,'tool-note'));
      body.append(button('Clear samples',()=>{++pickSerial;samples=[];sampleKey=null;pickMessage='Click a visible sampled surface.';api.refreshInspection();}),button('Nominal surface pose',async()=>{await api.pauseForAnalysis();if(!rememberView())return;api.viewer.applyFrame({parts:api.viewer.meshes.map(mesh=>({index:mesh.part.index,matrix:identityMatrix(),deformation:null}))});nominalInspection=true;++pickSerial;samples=[];sampleKey=null;pickMessage='Nominal construction surfaces · paused. Animated flexible surfaces are unsupported.';api.refreshInspection();}),button('Restore preview',()=>{restoreView();samples=[];sampleKey=null;api.refreshInspection();}));
    }
    panel.prepend(body);
  }
  api.events.addEventListener('components',({detail})=>surfaceControls(detail.panel));
  api.events.addEventListener('pickmode',()=>{samples=[];sampleKey=null;++pickSerial;pickMessage='Click a visible sampled surface.';api.refreshInspection();});
  api.viewer.addEventListener('surfaceclick',async({detail})=>{
    if(api.pickMode==='navigate' || state.run || recovery)return;
    const mode=api.pickMode,snapshot=current();if(!snapshot)return;api.setPlaying(false);const serial=++pickSerial;
    try {
      const clicked=api.viewer.pickState(detail.clientX,detail.clientY);
      await api.pauseForAnalysis();if(serial!==pickSerial || !api.matches(snapshot.token))return;
      const view=api.viewer.pickState(detail.clientX,detail.clientY);
      if(view.key!==clicked.key)return;
      if(mode==='measure' && sampleKey!==view.key){samples=[];sampleKey=view.key;}
      const hit=await api.request('pick',view.payload);
      const valid=()=>serial===pickSerial && api.matches(snapshot.token) && api.pickMode===mode && api.viewer.pickState(detail.clientX,detail.clientY).key===view.key;
      if(!valid())return;
      if(!hit.hit){pickMessage='No visible sampled surface at this point.';api.refreshInspection();return;}
      if(mode==='select') {
        const selected=detail.add?new Set(api.viewer.selected):new Set();if(selected.has(hit.hit.source_index))selected.delete(hit.hit.source_index);else selected.add(hit.hit.source_index);api.viewer.setSelection(selected);pickMessage=`${selected.has(hit.hit.source_index)?'Selected':'Deselected'} ${snapshot.design.parts[hit.hit.source_index].name}.`;
      } else {
        if(samples.length===2)samples=[];samples.push(copy(hit.hit.point));
        if(samples.length===2){const distance=await api.request('surface_distance',{points:copy(samples)});if(!valid())return;pickMessage=`Point-to-point Euclidean distance: ${distance.distance_mm} mm. ${distance.basis}`;}
        else pickMessage='First sampled point retained. Choose the second surface point.';
      }
      api.refreshInspection();
    }catch(error){if(serial===pickSerial && api.matches(snapshot.token)){pickMessage=error.message+' Use Nominal surface pose for flexible geometry.';api.refreshInspection();}}
  });
  controls();
  return {state,panels};
}
