// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
import {exportSheetArchive} from './sheet-pdf.js';

const node=(tag,text)=>{const element=document.createElement(tag);if(text!=null)element.textContent=text;return element;};
const button=(label,action)=>{
  const control=node('button',label); control.type='button'; control.addEventListener('click',action); return control;
};
const checkFields={
  label:'Characteristic',nominal:'Nominal',unit:'Unit',lower:'Minimum (absolute)',upper:'Maximum (absolute)',
  method:'Method / contact setup',instrument:'Instrument / ID',datum:'Datum / drawing reference'
};
let editor=null;

function field(parent,title,value='',{multiline=false,fixed=false}={}) {
  const row=node('label'), caption=node('span',title);
  row.className='sheet-field';
  const input=node(fixed ? 'output' : multiline ? 'textarea' : 'input',fixed ? value : null);
  if (!fixed) {
    input.value=value; input.maxLength=4000;
    input.dataset.noI18n='';
    if (multiline) input.rows=4;
  }
  row.append(caption,input); parent.append(row);
  return ()=>fixed ? value : input.value;
}

export async function openComponentSheet(api,index) {
  if (editor) return;
  const snapshot=api.snapshot();
  const part=snapshot?.design.parts[index];
  if (!part || api.viewer.selected.size!==1 || !api.viewer.selected.has(index)) return;
  const trigger=document.activeElement;
  const metadata=structuredClone(api.document.state.component_sheets || {});
  const dialog=node('dialog'); editor=dialog;
  let source;
  const close=()=>{
    if (editor===dialog) editor=null;
    dialog.remove();
    (trigger?.isConnected ? trigger : document.getElementById('open-tools-panel'))?.focus({preventScroll:true});
  };
  try { source=await api.request('component_sheet',{action:'draft',index,metadata}); }
  catch (error) {
    close();
    if (error.name!=='AbortError') api.reportStatus(error.message,'error');
    return;
  }
  if (!api.matches(snapshot.token) || !api.viewer.selected.has(index) || api.viewer.selected.size!==1) { close(); return; }
  const {draft}=source;
  dialog.className='component-sheet-dialog';
  dialog.setAttribute('aria-labelledby','component-sheet-title');
  dialog.id='component-sheet-dialog';
  const title=node('h2','Component production / inspection sheets');
  title.id='component-sheet-title';
  const header=node('header'), caption=node('p',String(index+1).padStart(3,'0')+' · '+part.name);
  caption.dataset.noI18n='';
  header.append(title,caption,node('p',draft.stale
    ? 'Geometry changed. Review the retained fields and limits, then Apply to bind them to this model.'
    : 'Company fields are saved in this project. Operations and acceptance limits are defined by your company.'));
  const tabs=node('div'), pages=node('div'), controls=node('footer'), error=node('p');
  tabs.className='component-tabs';tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','Component production / inspection sheets');
  pages.className='sheet-pages';
  error.className='note-warning';error.setAttribute('role','alert');error.hidden=true;
  const sections={}, tabButtons={};
  const select=mode=>{
    for (const key of Object.keys(sections)) {
      sections[key].hidden=key!==mode;
      tabButtons[key].setAttribute('aria-selected',String(key===mode));tabButtons[key].tabIndex=key===mode?0:-1;
    }
    pages.scrollTop=0;
  };
  for (const [mode,label] of [['production','Production'],['inspection','Inspection']]) {
    const page=sections[mode]=node('section'), tab=tabButtons[mode]=button(label,()=>select(mode));
    page.id='component-sheet-'+mode;page.setAttribute('role','tabpanel');page.setAttribute('aria-labelledby',page.id+'-tab');
    tab.id=page.id+'-tab';tab.setAttribute('role','tab');tab.setAttribute('aria-controls',page.id);
    tab.addEventListener('keydown',event=>{
      if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
      event.preventDefault();
      const next=event.key==='Home'?'production':event.key==='End'?'inspection':mode==='production'?'inspection':'production';
      select(next);tabButtons[next].focus();
    });
    tabs.append(tab);pages.append(page);
  }
  select('production');
  const company={}, fields={}, checks=new Map();
  const produce=sections.production, inspect=sections.inspection;
  for (const [key,label] of Object.entries(source.company_fields)) company[key]=field(produce,label,draft.company[key]);
  produce.append(node('hr'));
  for (const [key,label] of Object.entries(source.part_fields)) {
    fields[key]=field(produce,label,draft.fields[key],{multiline:['notes','operations'].includes(key)});
  }
  inspect.append(node('p','Limits are absolute minimum / maximum values, not deviations. Leave them blank when undefined. PDF result cells are left blank for recording.'),
    node('p','Automatic gauge dimensions use the theoretical default diameter. Instrument access and contact setup must be approved by the company.'));
  const rows=node('div'); rows.className='sheet-checks';inspect.append(rows);
  const showError=message=>{error.hidden=false;error.textContent=message;};
  function addCheck(row) {
    const automatic=row.id.startsWith('auto:'), section=node('details');
    section.append(node('summary',automatic ? row.label : 'Company characteristic'));
    const values={};
    for (const [key,label] of Object.entries(checkFields)) {
      const fixed=automatic && (['label','nominal','unit'].includes(key) || key==='method' && !!row.method);
      values[key]=field(section,label,row[key],{fixed});
    }
    if (!automatic) section.append(button('Remove characteristic',()=>{checks.delete(row.id);section.remove();}));
    checks.set(row.id,values);rows.append(section);
    return section;
  }
  for (const row of draft.checks) addCheck(row);
  inspect.append(button('Add company characteristic',()=>{
    if (checks.size>=source.max_checks) {showError('A sheet supports at most 40 inspection characteristics.');return;}
    const row=addCheck({id:'custom:'+crypto.randomUUID().replaceAll('-',''),unit:'mm'});
    row.open=true;row.querySelector('input')?.focus();
  }));
  const read=values=>Object.fromEntries(Object.entries(values).map(([key,value])=>[key,value()]));
  let pending=false;
  async function apply(pdf) {
    if (pending || !api.matches(snapshot.token)) {
      if (!pending) showError('The document changed. Close this editor and select the component again.');
      return;
    }
    pending=true;applyButton.disabled=exportButton.disabled=true;error.hidden=true;
    try {
      const result=await api.request('component_sheet',{action:'apply',index,metadata,company:read(company),fields:read(fields),
        checks:[...checks].map(([id,row])=>({id,...read(row)})),pdf,language:api.language,
        project:api.document.name==='Untitled design'?'':api.document.name,revision:snapshot.token.revision});
      if (editor!==dialog || !dialog.open) return;
      if (!api.matches(snapshot.token)) throw Error('The document changed. Close this editor and select the component again.');
      api.document.setComponentSheets(result.metadata);
      dialog.close();
      if (pdf) {
        api.reportStatus('Preparing PDF export…','warning');
        const download=await exportSheetArchive(result.pages,result.report);
        api.downloadBlob(download,'ratiolab-component-'+String(index+1).padStart(3,'0')+'-sheets.zip');
        api.reportStatus('Component PDFs');
      }
    } catch (failure) {
      if (dialog.open) showError(failure.message);
      else if (failure.name!=='AbortError') api.reportStatus(failure.message,'error');
    } finally {pending=false;applyButton.disabled=exportButton.disabled=false;}
  }
  const applyButton=button('Apply to project',()=>apply(false));
  const exportButton=button('Export PDFs',()=>apply(true));exportButton.className='primary';
  controls.append(error,button('Cancel',()=>dialog.close()),applyButton,exportButton);
  dialog.append(header,tabs,pages,controls);
  dialog.addEventListener('close',close,{once:true});
  dialog.addEventListener('keydown',event=>{if(event.key==='Escape')event.stopPropagation();});
  document.body.append(dialog);dialog.showModal();tabButtons.production.focus({preventScroll:true});
}
