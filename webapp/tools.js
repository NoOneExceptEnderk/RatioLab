// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
import {ModelViewer, identityMatrix} from './viewer.js';
import {ratioParts, significantText} from './ratio-display.js';

const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
const copy=value=>structuredClone(value);
const numberText=value=>typeof value==='number'&&Number.isFinite(value)?Number(value.toPrecision(7)).toString():String(value);
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

export function gridValues(draft) {
  const grid=axisGrid(draft);if(grid==null)return null;
  const numbers=new Set();
  for(const term of grid.split(',')){
    const fields=term.trim().split(':');
    if(fields.length===1)numbers.add(preciseNumber(fields[0]));
    else if(fields.length===3){
      const [low,high,step]=fields.map(v=>preciseNumber(v));
      if(step<=0||high<low||(high-low)/step>=1000)throw Error('Range requires From ≤ To and a positive Step.');
      for(let n=0;n<=Math.floor((high-low)/step+1e-10);n++)numbers.add(low+n*step);
    }else throw Error('Use comma separated values or low:high:step.');
    if(numbers.size>1000)throw Error('At most 1000 values per variable.');
  }
  return [...numbers];
}
export function gridCount(draft) { return gridValues(draft)?.length??null; }

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
  let active=null,recovery=null,recoveryMessage=null,preview=null,savedView=null,inspectionSerial=0,pickSerial=0,samples=[],sampleKey=null,pickMessage='Click a visible sampled surface.',nominalInspection=false;
  const current=()=>api.snapshot();
  function button(text,action,cls='') {const b=el('button',text,cls);b.type='button';b.addEventListener('click',action);return b;}
  function field(panel,key,label,value,{integer=false,select=null}={}) {
    const row=el('label',null,'tool-field'),name=el('span',label),input=el(select?'select':'input');
    input.id=`${panel.key}-${key}`;input.name=key;row.htmlFor=input.id;
    if(select)for(const [value,text] of select){const o=el('option',text);o.value=value;input.append(o);}
    else{input.type='text';input.inputMode=integer?'numeric':'decimal';input.autocomplete='off';input.spellcheck=false;}
    input.value=String(value);row.append(name,input);panel.fields[key]={input,label,integer};return row;
  }
  function value(p,key){const f=p.fields[key];try{const value=preciseNumber(f.input.value,f.label,f.integer);f.input.removeAttribute('aria-invalid');return value;}catch(error){f.input.setAttribute('aria-invalid','true');throw error;}}
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
    for(const finding of panels.get('interference')?.rows.children ?? []){
      if(finding.dataset.sourcePair)finding.setAttribute('aria-pressed','false');
    }
  }
  function rememberView() {
    const snapshot=current();if(!snapshot || !api.viewer.frame)return null;
    if(!savedView)savedView={token:copy(snapshot.token),source:api.viewer.design,frame:copy(api.viewer.frame),phase:snapshot.phase,selection:[...api.viewer.selected],hidden:[...api.viewer.hidden],options:{supports:api.viewer.supports,housing:api.viewer.housing,section:api.viewer.section,explosion:api.viewer.explosion}};
    return savedView;
  }
  function clearResults(message='Settings changed · run again.') {
    state.result=null;disposePreview();restoreView();
    for(const p of panels.values()) {
      p.selected=null;
      p.rows.replaceChildren();
      p.report.textContent='';
      p.reportDetails.hidden=true;
      p.downloadActions.hidden=true;
      p.summary.textContent=message;
      delete p.summary.dataset.queryId;
      p.progress.hidden=state.run?.panel!==p.key;
      p.progress.value=0;
      p.elapsed.textContent='';
      for(const b of p.downloads)b.disabled=true;
      if(p.apply)p.apply.disabled=true;
    }
  }
  function controls() {
    for(const p of panels.values()) {
      const capability=current()?.design.tool_capabilities?.[p.key];
      p.run.disabled=!!state.run || !!recovery || !current() || capability?.available===false || p.key==='search' && !p.searchSchema?.supported;
      p.run.title=capability?.reason??'';
      p.cancel.disabled=state.run?.panel!==p.key;
      if(p.apply)p.apply.disabled=!state.usable() || state.result.panel!==p.key || p.key==='search' && (p.selected==null || !Object.keys(state.result.data.proposals[p.selected]?.changes??{}).length) || p.key==='backlash' && !state.result?.data.applicable;
      for(const b of p.downloads)b.disabled=!state.usable() || state.result.panel!==p.key;
      if(p.key==='search'&&p.searchSchema?.supported)updateSearchDomain(p);
    }
  }
  function drop(message,{source=false}={}) {
    const running=!!state.run;state.invalidate();clearResults(message);controls();
    if(running && !source)hardCancel(message,null);
  }
  async function hardCancel(message='Cancelled · restoring the current model…', settled='Operation cancelled.') {
    state.invalidate();clearResults(message);api.setAnalysisActive(false);
    if(!recovery) {
      // Set a sentinel before cancelOperations synchronously emits invalidate.
      const panel=active;
      recovery=Promise.resolve();
      recoveryMessage=message;
      controls();
      const pending=api.cancelOperations();
      recoveryMessage=null;
      recovery=pending;
      const serial=state.serial;
      try {
        await pending;
        const p=panels.get(panel);
        if(p && panel===active && state.serial===serial && settled && current())p.summary.textContent=settled;
      } finally {
        if(recovery===pending){recovery=null;controls();}
      }
    }
  }
  function edited(p) {
    if(p.populating)return;
    drop('Settings changed · results cleared. Run again with these drafts.');
    if(p.key==='search')updateSearchDomain(p);
  }
  function panel(key,intro) {
    const p={key,fields:{},downloads:[],selected:null,root:el('div',null,'analysis-tool'),form:el(key==='search'?'details':'div',null,'tool-form'),rows:el('div',null,'tool-rows'),report:el('pre',null,'tool-report'),summary:el('p','Choose settings, then run.','tool-summary')};
    if(key==='search'){p.form.append(el('summary','Edit search settings'));p.form.open=true;}
    p.report.dataset.localizeReport='';
    p.context=el('p',null,'tool-summary');
    p.settingsTitle=el('h3','Analysis settings');
    p.root.id=`tool-${key}`;
    p.root.append(el('h3','Model examined'),p.context,el('p',intro,'tool-note'),p.settingsTitle,p.form);
    p.summary.setAttribute('role','status');
    p.form.addEventListener('input',()=>edited(p));p.form.addEventListener('change',()=>edited(p));
    const actions=el('div',null,'tool-actions');p.run=button(key==='search'?'Search':key==='metrology'?'Calculate':key==='backlash'?'Solve':'Check cycle',()=>run(p));p.run.id=`${key}-run`;
    p.cancel=button('Cancel',()=>hardCancel());p.cancel.id=`${key}-cancel`;p.cancel.disabled=true;actions.append(p.run,p.cancel);
    p.progress=el('progress');p.progress.max=1;p.progress.value=0;p.progress.hidden=true;p.elapsed=el('span','','tool-note');
    p.root.append(el('h3','Results'),p.summary,p.progress,p.elapsed,p.rows);
    const downloads=el('div',null,'tool-actions');
    for(const format of ['txt','json']){const b=button('Download '+format.toUpperCase(),()=>download(p,format));b.id=`${key}-download-${format}`;b.disabled=true;p.downloads.push(b);downloads.append(b);}
    p.reportDetails=el('details');
    p.reportDetails.append(el('summary','Full report'),p.report);
    p.reportDetails.hidden=true;
    p.downloadActions=downloads;
    downloads.hidden=true;
    const footer=el('div',null,'tool-run-actions');
    footer.append(actions,downloads);
    p.root.append(p.reportDetails,footer);
    p.actions=actions;
    panels.set(key,p);api.registerTool(key,{label:titles[key]+'…',open:()=>open(p)});return p;
  }
  async function open(p) {
    if(active!==p.key){drop('Tool changed · run a fresh query.');active=p.key;}
    api.setDockPanel(p.key,p.root,{title:titles[p.key]});
    if(p.key==='search')await loadSearch(p);
    if(p.key==='metrology')populateParts(p);
    const contextKey=JSON.stringify([current()?.token.identity,current()?.family,current()?.parameters.variant]);
    if(p.key==='backlash' && p.targetContext!==contextKey) {
      const target=current()?.design.analysis.meshes?.[0]?.working_pair_backlash_mm;
      p.fields.desired_backlash_mm.input.value=String(Number.isFinite(target)?target:.3);p.targetContext=contextKey;
    }
    updateContext(p);
    if(!state.usable())p.summary.textContent=current()?.design.tool_capabilities?.[p.key]?.available===false
      ? current().design.tool_capabilities[p.key].reason : 'Choose settings, then run.';
    if(p.key==='search'&&!state.usable())p.form.open=true;
    controls();
  }
  function updateContext(p) {
    const snapshot=current();
    if(!snapshot){
      p.context.textContent='Generate a valid model first.';
      return;
    }
    const lines=[snapshot.modelLabel ?? snapshot.family];
    if(p.key==='search' && Number.isFinite(snapshot.design.analysis.signed_ratio))
      lines.push('Ratio (input/output): '+ratioParts(snapshot.design.analysis.signed_ratio,10).join(''));
    if(p.key==='backlash'){
      const mesh=snapshot.design.analysis.meshes?.[0], limits=snapshot.design.tool_capabilities?.backlash?.limits;
      if(mesh && limits)lines.push(
        `Current centre ${numberText(mesh.center_distance_mm)} mm · working transverse backlash ${numberText(mesh.working_pair_backlash_mm)} mm`,
        `Nominal target range: ${numberText(limits.minimum_mm)}–${numberText(limits.maximum_mm)} mm. Contact checks still apply.`);
    }
    p.context.textContent=lines.join('\n');
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
      const ranking=p.fields.ranking.input.value,minimum=value(p,'min_profile_contact');
      if((ranking==='contact'||minimum>0)&&!['parallel','internal','planetary'].includes(current()?.family))throw Error('Usable profile contact comparison requires cylindrical parallel, internal or planetary meshes.');
      return {grids,settings:{target:value(p,'target'),tolerance_percent:value(p,'tolerance_percent'),direction:p.fields.direction.input.value,max_xyz:['x','y','z'].map(key=>value(p,key)),max_candidates:value(p,'max_candidates'),max_seconds:value(p,'max_seconds'),max_results:value(p,'max_results'),ranking,min_profile_contact:minimum}};
    }
    const payload={settings:settings(p)};if(p.key==='backlash')payload.desired_backlash_mm=value(p,'desired_backlash_mm');return payload;
  }
  async function run(p) {
    if(state.run || recovery || active!==p.key)return;
    let payload;try{payload=requestPayload(p);}catch(error){drop(error.message);p.form.open=true;for(const details of p.form.querySelectorAll?.('details')??[])details.open=true;return;}
    const snapshot=current();if(!snapshot){p.summary.textContent='Complete the model fields and wait for valid geometry.';return;}
    clearResults('Preparing analysis…');const run=state.begin(p.key,p.key,snapshot.token);api.setAnalysisActive(true);controls();
    p.progress.hidden=false;p.progress.removeAttribute('value');
    const timer=setInterval(()=>{if(state.current(run))p.elapsed.textContent=`${((performance.now()-run.started)/1000).toFixed(1)} s elapsed`;},200);
    try {
      await api.pauseForAnalysis();if(!state.current(run))return;
      const result=await api.request(p.key,payload);
      if(active!==p.key || !state.finish(run,result))return;
      p.progress.hidden=true;
      p.elapsed.textContent='';
      p.report.textContent=result.text;
      p.reportDetails.hidden=false;
      p.downloadActions.hidden=false;
      present(p,state.result);
      p.summary.dataset.queryId=result.query_id;
      p.summary.scrollIntoView?.({block:'nearest'});
    } catch(error) {
      if(state.current(run)){
        if(api.engine.failure)await hardCancel(error.message+' · restoring the current model…',error.message);
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
      if(p.key==='metrology') {
        const r=d.result;
        if(r?.gauge_diameter_mm!=null&&p.fields.gauge_mode.input.value==='default'){
          p.recommendedDiameter=String(r.gauge_diameter_mm);p.fields.gauge_diameter.input.value=p.recommendedDiameter;
        }
        p.summary.textContent=r?.status==='ok'?`${r.dimension_kind}: ${numberText(r.dimension_mm)} mm\nGauge Ø ${numberText(r.gauge_diameter_mm)} mm · contact R ${numberText(r.contact_radius_mm)} mm`:'Measurement unavailable\n'+(r?.reason ?? result.text);
        if(d.span?.usable_spans?.length){
          const group=el('details');group.append(el('summary','Tooth span measurement'));
          for(const row of d.span.usable_spans)group.append(el('p',`W${row.k} = ${numberText(row.span_mm)} mm · contact R ${numberText(row.contact_radius_mm)} mm`,'tool-note'));
          p.rows.append(group);
        }
      }
    if(p.key==='search') {
      p.form.open=false;
      const outcome=d.reason==='cancelled'?'Search cancelled':d.complete?'Complete finite search':'PARTIAL search';
      const lines=[`${outcome}\n${d.visited}/${d.total} candidates · ${d.proposals.length} retained proposals`];
      if(d.reason && d.reason!=='cancelled')lines.push(d.reason);
      if(!d.proposals.length)lines.push(d.complete?'No matching proposals. Review ratio, ranges and size limits.':'No proposals found in the candidates visited so far.');
      if(!d.complete && d.reason!=='cancelled')lines.push('Review ranges or raise Advanced budgets, then Search again for more coverage.');
      p.summary.textContent=lines.join('\n');
      for(const [index,row] of d.proposals.entries()) {
        const labels=new Map((p.searchSchema?.variables??[]).map(s=>[s.key,s.label]));
        const contact = row.comparison?.min_profile_contact;
        const quality = contact == null ? 'Usable contact ratio: unavailable' : `Usable contact ratio: ${significantText(contact, 6)}`;
        const magnitude = ratioParts(row.ratio, 10, {signed:false}).join('');
        const rotation = row.ratio > 0 ? 'Same rotation' : 'Opposite rotation';
        const b=button('',()=>{if(!state.usable(result))return;p.selected=index;for(const r of p.rows.children)r.setAttribute('aria-pressed',String(r===b));controls();},'tool-result');
        b.title = `Signed input/output ratio: ${ratioParts(row.ratio, 12).join('')}. Direction uses the current member axes.`;
        const direction = el('div');
        direction.append(el('span', rotation), el('span', ` · error ${significantText(row.error_percent, 6)}%`));
        b.append(el('div',`Ratio (input/output): ${magnitude}`), direction,
          el('div',`Overall XYZ: ${row.xyz.map(value => significantText(value, 6)).join(' × ')} mm`),el('div',quality));
        if(Object.keys(row.changes).length){b.append(el('div','Current → Proposed'));for(const [key,change] of Object.entries(row.changes)){
          const line=el('div');line.append(el('span',labels.get(key)??key),el('span',`: ${significantText(Array.isArray(change)?change[0]:current()?.parameters[key], 10)} → ${significantText(Array.isArray(change)?change[1]:change, 10)}`));b.append(line);
        }}else b.append(el('div','Current parameters (no change)'));
        b.dataset.proposalIndex=index;b.setAttribute('aria-pressed','false');p.rows.append(b);
      }
    }
    if(p.key==='interference') {
      const outcome=d.cancelled?'Check cancelled\nINCOMPLETE coverage'
        :current()?.design.motion?.supported===false?'Motion check unsupported'
        :d.coverage_complete?'Complete sampled coverage':'INCOMPLETE coverage';
      const lines=[outcome];
      if(d.planned_poses>0)lines.push(`${d.completed_poses}/${d.planned_poses} poses · ${d.completed_pairs} pair checks`);
      if(d.issues?.length)lines.push(d.issues[0]);
      else if(d.coverage_complete && !d.pairs_per_pose)lines.push('No component pairs to check.');
      p.summary.textContent=lines.join('\n');
      if(!d.rows.length)return;
      const count=kind=>d.rows.filter(row=>row.kind===kind).length;
      p.summary.textContent+=`\nPotential interference: ${count('Intersection')+count('Containment')} · unresolved contacts: ${count('Boundary contact / unresolved')} · separated: ${count('Separated')}`;
      const filter=el('select');filter.setAttribute('aria-label','Filter findings');
      for(const [key,label] of [['all','All findings'],['potential','Potential interference'],['unresolved','Unresolved contacts'],['separated','Separated']]){const option=el('option',label);option.value=key;filter.append(option);}
      p.rows.append(filter);
      const findingButtons=[];
      for(const row of d.rows) {
        const b=button(`${row.part_a} ↔ ${row.part_b}\n${row.kind} · ${numberText(row.distance)} mm · phase ${numberText(row.phase_degrees)}°\n${row.expected||'No expected interface identified'}`,()=>inspect(p,result,row,b),'tool-result');
        b.setAttribute('aria-pressed','false');
        b.dataset.sourcePair=`${row.index_a},${row.index_b}`;p.rows.append(b);findingButtons.push([b,row]);
      }
      const empty=el('p','No findings match this filter. Full report retains all classes.','tool-note');empty.hidden=!!findingButtons.length;p.rows.append(empty);
      filter.addEventListener('change',()=>{for(const [b,row] of findingButtons)b.hidden=!(filter.value==='all'||filter.value==='potential'&&['Intersection','Containment'].includes(row.kind)||filter.value==='unresolved'&&row.kind==='Boundary contact / unresolved'||filter.value==='separated'&&row.kind==='Separated');empty.hidden=findingButtons.some(([b])=>!b.hidden);});
      p.rows.append(button('Restore preview',restoreView));
    }
    if(p.key==='backlash') {
      p.summary.textContent=d.interference && !d.interference.coverage_complete && d.status!=='cancelled'
        ? 'INCOMPLETE coverage\n'+(d.interference.issues?.[0] ?? d.reason) : d.reason;
      if(d.center_distance_mm!=null)p.rows.append(el('p',`Current → Proposed\nCentre distance: ${numberText(d.source_center_mm)} → ${numberText(d.center_distance_mm)} mm\nWorking backlash: ${numberText(d.source_backlash_mm)} → ${numberText(d.working_backlash_mm)} mm\nUsable contact ratio: ${numberText(d.usable_contact_total)}`,'tool-summary'));
      if(result.candidate) {
        const canvas=el('canvas');canvas.tabIndex=0;canvas.setAttribute('aria-label','Proposed model · separate nominal preview');p.preview.append(el('p','Proposed model · nominal preview; source unchanged.','tool-note'),canvas);
        try{preview=new ModelViewer(canvas);preview.guides=false;preview.supports=true;preview.housing=true;preview.setDesign({...result.candidate,buffers:result.buffers});}
        catch(error){disposePreview();p.preview.append(el('p','Candidate preview unavailable: '+error.message,'tool-note'));}
      }
    }
  }
  async function inspect(p,result,row,button) {
    if(!state.usable(result) || active!==p.key)return;
    await api.pauseForAnalysis();if(!state.usable(result))return;
    const saved=rememberView();if(!saved)return;const serial=++inspectionSerial;
    api.viewer.hidden.clear();api.viewer.supports=api.viewer.housing=true;api.viewer.section=false;api.viewer.explosion=0;
    for(const id of ['show-supports','show-housing']){const input=document.getElementById(id);if(input)input.checked=true;}
    const section=document.getElementById('section-view');if(section)section.checked=false;const explosion=document.getElementById('explosion');if(explosion)explosion.value='0';
    const ok=await api.requestPose(row.phase_degrees*Math.PI/180);
    if(serial!==inspectionSerial || !state.usable(result) || active!==p.key){applySavedView(saved);return;}
    if(ok){
      for(const finding of p.rows.children){
        if(finding.dataset.sourcePair)finding.setAttribute('aria-pressed',String(finding===button));
      }
      api.viewer.setSelection([row.index_a,row.index_b]);
      api.refreshInspection();
    }
  }
  async function apply(p) {
    const result=state.result;
    if(!state.usable(result) || result.panel!==p.key || recovery || state.run)return;
    const index=p.selected;if(p.key==='search' && (index==null||!Object.keys(result.data.proposals[index]?.changes??{}).length) || p.key==='backlash' && !result.data.applicable)return;
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
    const supported=snapshot?.design.tool_capabilities?.metrology?.components;
    for(const part of snapshot?.design.parts??[]){if(supported&&!supported.includes(part.index))continue;const o=el('option',`${part.index+1} · ${part.name.replaceAll('_',' ')}`);o.value=part.index;select.append(o);}
    const selected=[...api.viewer.selected],preferred=selected.length===1?String(selected[0]):previous;
    if([...select.options].some(o=>String(o.value)===preferred))select.value=preferred;
    if(select.value!==previous){p.recommendedDiameter=undefined;if(p.fields.gauge_mode.input.value==='default')p.fields.gauge_diameter.input.value='';}
  }
  function updateSearchDomain(p) {
    if(!p.scope||!p.axes)return;
    try{
      let count=1,varied=0;
      for(const [key,d] of p.axes){const values=gridValues(d);if(values!=null){
        const spec=p.axisSpecs?.get(key);
        if(spec&&values.some(v=>v<spec.minimum||v>spec.maximum))throw Error(spec.label+`: Values must be within ${spec.minimum}–${spec.maximum}.`);
        if(spec?.integer&&values.some(v=>!Number.isInteger(v)))throw Error(spec.label+': Use whole numbers for this count.');
        count*=values.length;varied++;
      }}
      p.scope.textContent=varied?`${count.toLocaleString('en-US')} finite candidates · ${varied} parameters vary`:'Choose Range or Custom for at least one parameter. Locked parameters stay at the current model.';
      if(!varied)p.run.disabled=true;
    }catch(error){p.scope.textContent=error.message;p.run.disabled=true;}
  }
  async function loadSearch(p) {
    if(recovery || state.run || !current())return;
    const snapshot=current(),serial=++p.schemaSerial;
    try {
      const schema=await api.request('search_schema');
      if(serial!==p.schemaSerial || !api.matches(snapshot.token))return;
      const reverseLabels = new Map([['Input pinion teeth', 'Pinion teeth'], ['Driven wheel teeth', 'Wheel teeth']]);
      p.searchSchema = snapshot.parameters.io_scheme === 'reverse'
        ? {...schema, variables:schema.variables.map(spec => ({...spec, label:reverseLabels.get(spec.label) ?? spec.label}))}
        : schema;
      p.axisSpecs=new Map(p.searchSchema.variables.map(spec=>[spec.key,spec]));
      const key=JSON.stringify([snapshot.token.identity,snapshot.family,snapshot.parameters.variant,snapshot.parameters.double_style,snapshot.parameters.io_scheme,snapshot.parameters.io_scheme2]);
      if(key!==p.formKey){p.axes=new Map();p.formKey=key;p.fields.target.input.value=String(Math.abs(snapshot.design.analysis.signed_ratio)||schema.settings.target);}
      p.axesBox.replaceChildren();
      const more=el('details');more.append(el('summary','More dimensions'));
      const countKey=key=>/^(pinion\d*|wheel\d*|sun\d*|planet\d*|teeth|pins|starts)$/.test(key);
      for(const spec of [...p.searchSchema.variables].sort((a,b)=>Number(countKey(b.key))-Number(countKey(a.key)))) {
        let d=p.axes.get(spec.key);if(!d){const count=/^(pinion\d*|wheel\d*|sun\d*|planet\d*|teeth|pins|starts)$/.test(spec.key),stride=snapshot.family==='harmonic'?2:1;d={mode:count?'range':'locked',range:[String(count?Math.max(spec.minimum,spec.current-4):spec.current),String(count?Math.min(spec.maximum,spec.current+4):spec.current),String(count?stride:spec.step)],custom:String(spec.current)};p.axes.set(spec.key,d);}
        const box=el('fieldset',null,'tool-axis');box.append(el('legend',spec.label),el('p',`Current ${spec.current} · allowed ${spec.minimum}–${spec.maximum}`,'tool-note'));
        const mode=el('select');mode.setAttribute('aria-label',spec.label+' mode');mode.id=`search-axis-${spec.key}`;
        for(const [key,title]of [['locked','Locked'],['range','Range'],['custom','Custom']]){const o=el('option',title);o.value=key;mode.append(o);}mode.value=d.mode;
        const range=el('div',null,'tool-range'),custom=el('input');custom.type='text';custom.value=d.custom;custom.placeholder='20,24,28 or 20:28:2';custom.setAttribute('aria-label',spec.label+' custom grid');
        for(const [i,title] of ['From','To','Step'].entries()){const label=el('label',title),input=el('input');input.type='text';input.inputMode='decimal';input.value=d.range[i];input.setAttribute('aria-label',spec.label+' '+title);input.addEventListener('input',()=>d.range[i]=input.value);label.append(input);range.append(label);}
        const visibility=()=>{range.hidden=d.mode!=='range';custom.hidden=d.mode!=='custom';};mode.addEventListener('change',()=>{d.mode=mode.value;visibility();});custom.addEventListener('input',()=>d.custom=custom.value);visibility();box.append(mode,range,custom);(countKey(spec.key)?p.axesBox:more).append(box);
      }
      p.axesBox.append(more);
      p.gridNote.textContent=schema.supported?'All other dimensions, variants, stages and input/output arrangements stay fixed. Each axis has at most 1000 values.':'This family has no supported single-ratio finite search.';controls();updateSearchDomain(p);
    }catch(error){if(serial===p.schemaSerial && api.matches(snapshot.token))p.summary.textContent=error.message;}
  }

  const m=panel('metrology','Measure involute gear geometry using the selected component. Unsupported profiles and theory limits are reported explicitly.');
  const source=field(m,'source_index','Component',0,{integer:true,select:[]});
  m.root.insertBefore(source,m.settingsTitle);
  source.addEventListener('change',()=>edited(m));
  m.form.append(field(m,'gauge_type','Gauge','ball',{select:[['ball','Ball'],['roller','Roller']]}),field(m,'gauge_mode','Gauge diameter','default',{select:[['default','Recommended diameter'],['explicit','Specify diameter (mm)']]}),field(m,'gauge_diameter','Diameter (mm)','3'));
  m.explicitDiameter='3';m.gaugeMode='default';
  const gauge=()=>{const mode=m.fields.gauge_mode.input.value;if(m.gaugeMode==='explicit')m.explicitDiameter=m.fields.gauge_diameter.input.value;m.fields.gauge_diameter.input.disabled=mode!=='explicit';m.fields.gauge_diameter.input.value=mode==='explicit'?m.explicitDiameter:m.recommendedDiameter??'';m.gaugeMode=mode;};
  m.fields.gauge_mode.input.addEventListener('change',gauge);gauge();
  m.fields.source_index.input.addEventListener('change',()=>{m.recommendedDiameter=undefined;if(m.fields.gauge_mode.input.value==='default')m.fields.gauge_diameter.input.value='';});
  const s=panel('search','Explore explicit finite combinations for a target ratio and nominal overall size. A partial run can retain valid candidates; it does not establish a global optimum.');
  s.axes=new Map();s.schemaSerial=0;
  s.form.append(el('h4','1. Desired ratio'),el('p','Ratio = |input speed / output speed|','tool-note'),field(s,'target','Desired ratio','3'),el('p','For 1:3, enter about 0.333333. Choose the rotation direction separately.','tool-note'),field(s,'tolerance_percent','Allowed error ± (%)','1'),field(s,'direction','Output direction relative to input','either',{select:[['either','Either direction'],['same','Same (+)'],['opposite','Opposite (−)']]}),field(s,'ranking','Compare results by','ratio',{select:[['ratio','Closest ratio'],['compact','Smallest envelope'],['contact','Highest usable contact ratio']]}));
  const size=el('details');size.append(el('summary','Overall size limits (mm)'));s.form.append(size);
  for(const key of ['x','y','z'])size.append(field(s,key,`Maximum ${key.toUpperCase()} (mm)`,'1000'));
  s.form.append(el('p','Size includes all generated components, including supports and housing, in the nominal export pose. It is a sampled envelope, not a motion sweep.','tool-note'));
  s.gridNote=el('p',null,'tool-note');s.axesBox=el('div');s.form.append(el('h4','2. Parameters to explore'),s.gridNote,s.axesBox);
  s.scope=el('p',null,'tool-note');s.form.append(s.scope);
  const advanced=el('details');advanced.append(el('summary','Advanced · budgets & technical details'));s.form.append(advanced);
  for(const [key,label,v,integer]of [['min_profile_contact','Minimum usable contact ratio (0 = no filter)','0',false],['max_candidates','Maximum candidates','50000',true],['max_seconds','Time limit (s)','30',false],['max_results','Retained results (max 100)','100',true]])advanced.append(field(s,key,label,v,{integer}));
  s.apply=button('Apply selected combination',()=>apply(s));s.apply.id='search-apply';s.apply.disabled=true;s.actions.append(s.apply);
  const i=panel('interference','Check every component, including hidden supports and housing, over discrete poses of the labelled kinematic period or finite working stroke. Boundary contact remains unresolved. Samples can miss collisions between poses.');
  const b=panel('backlash','Parallel external spur, helical and double helix pairs. Target transverse tangential working backlash by adjusting centre spacing. The candidate stays separate until Apply.');
  b.form.append(field(b,'desired_backlash_mm','Desired working backlash (mm)','0.1'));
  for(const p of [i,b]){const advanced=el('details');advanced.append(el('summary','Check settings'));p.form.append(advanced);for(const [key,label,v,integer]of checkFields)advanced.append(field(p,key,label,p===b && key==='max_seconds'?'60':v,{integer}));}
  b.preview=el('div',null,'candidate-preview');b.root.insertBefore(b.preview,b.reportDetails);
  b.apply=button('Apply proposed centre spacing',()=>apply(b));b.apply.id='backlash-apply';b.apply.disabled=true;b.actions.append(b.apply);

  api.engine.addEventListener('progress',({detail})=>{const run=state.run;if(!run || !state.current(run) || detail.stage!=='analysis' || detail.method!==run.method)return;const p=panels.get(run.panel);p.summary.textContent=detail.message||detail.detail;if(Number.isFinite(detail.fraction))p.progress.value=Math.max(0,Math.min(1,detail.fraction));});
  api.events.addEventListener('querybegin',()=>{clearResults('A new query superseded the previous report.');controls();});
  api.events.addEventListener('invalidate',()=>{++pickSerial;samples=[];sampleKey=null;pickMessage='Model changed · samples cleared.';state.invalidate();clearResults(recoveryMessage ?? 'Model changed · run a new query.');if(active)updateContext(panels.get(active));controls();});
  api.events.addEventListener('design',()=>{samples=[];sampleKey=null;if(active==='metrology')populateParts(m);if(active==='search')loadSearch(s);if(active)updateContext(panels.get(active));controls();});
  api.events.addEventListener('toolswitch',({detail})=>{if(active && detail.key!==active){drop('Tool changed · run a fresh query.');active=null;}if(detail.key!=='components'){++pickSerial;samples=[];sampleKey=null;}});
  api.events.addEventListener('toolclose',()=>{drop('Tool closed.');active=null;++pickSerial;samples=[];sampleKey=null;restoreView();});
  api.events.addEventListener('playstart',()=>{restoreView();++pickSerial;samples=[];sampleKey=null;});

  function surfaceControls(panel) {
    const body=el('div',null,'surface-tools'),actions=el('div',null,'tool-actions');
    const isolate=button('Isolate selected',()=>{if(!api.viewer.selected.size)return;for(const part of api.viewer.design.parts)api.viewer.hidden[api.viewer.selected.has(part.index)?'delete':'add'](part.index);api.viewer.render();api.refreshInspection();});isolate.disabled=!api.viewer.selected.size;
    actions.append(isolate,button('Show all',()=>{api.viewer.hidden.clear();api.viewer.supports=api.viewer.housing=true;for(const id of ['show-supports','show-housing'])document.getElementById(id).checked=true;api.viewer.render();api.refreshInspection();}));
    const selected=[...api.viewer.selected],gauges=current()?.design.tool_capabilities?.metrology?.components;
    if(selected.length===1&&gauges?.includes(selected[0]))actions.append(button('Gear metrology…',()=>api.openTool('metrology')));
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
        if(samples.length===2){const distance=await api.request('surface_distance',{points:copy(samples)});if(!valid())return;pickMessage=`Point-to-point Euclidean distance: ${distance.distance_mm} mm. B − A · ΔXYZ: ${samples[1].map((v,i)=>v-samples[0][i]).join(', ')} mm. ${distance.basis}`;}
        else pickMessage='First sampled point retained. Choose the second surface point.';
      }
      api.refreshInspection();
    }catch(error){if(serial===pickSerial && api.matches(snapshot.token)){pickMessage=error.message+' Use Nominal surface pose for flexible geometry.';api.refreshInspection();}}
  });
  controls();
  return {state,panels};
}
