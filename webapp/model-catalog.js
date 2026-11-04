// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
const node = (tag,text,cls) => {const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
export function selectionSummary(family, options={}) {
  const variant=family.options.find(o=>o.key==='variant');
  const value=options.variant??variant?.default??'';
  const parts=[];
  if(family.key==='parallel') {
    const count=value.startsWith('three_stage')?3:value.startsWith('two_stage')?2:1;
    parts.push(`${count} ${count===1?'stage':'stages'}`,value.endsWith('helical')?'Helical':value.endsWith('double')?'Double helical':'Spur');
  } else if(variant) parts.push(variant.choices.find(c=>c.value===value)?.label??'Standard');
  for(const key of ['configuration','double_style']) {
    if(key==='double_style'&&(family.key==='double'||!['double','two_stage_double','three_stage_double','double_helical'].includes(value)))continue;
    const spec=family.options.find(o=>o.key===key);
    if(spec)parts.push(spec.choices.find(c=>c.value===(options[key]??spec.default))?.label);
  }
  return parts.filter(Boolean).join(' · ')||'Standard';
}
export function variantControls(family, value) {
  const variant=family.options.find(option=>option.key==='variant');
  if (!variant) return [];
  if (family.key!=='parallel') return [{...variant,value,option_key:'variant'}];
  const stages=value.startsWith('three_stage')?3:value.startsWith('two_stage')?2:1;
  const teeth=value.endsWith('helical')?'helical':value.endsWith('double')?'double':'spur';
  const key=(n,t)=>n===1?t:(n===2?'two_stage':'three_stage')+(t==='spur'?'':'_'+t);
  return [{key:'stage_count',option_key:'variant',label:'Number of stages',value,choices:[1,2,3].map(n=>({value:key(n,teeth),label:String(n)}))},
    {key:'tooth_type',option_key:'variant',label:'Tooth type',value,choices:[['spur','Spur'],['helical','Helical'],['double','Double helical']].map(([t,label])=>({value:key(stages,t),label}))}];
}

export function initModelCatalog({getCatalog,getSelection,onApply,onClose=()=>{}}) {
  const opener=document.getElementById('model-catalog-open');
  const dialog=node('dialog',null,'model-catalog');dialog.id='model-catalog';
  dialog.setAttribute('aria-labelledby','catalog-title');
  const header=node('header'),title=node('h2','Model catalog');title.id='catalog-title';header.append(title);
  const close=node('button','×','catalog-close');close.setAttribute('aria-label','Close');close.addEventListener('click',()=>dialog.close());header.append(close);dialog.append(header);
  const search=node('input');search.type='search';search.placeholder='Search models…';search.setAttribute('aria-label','Search models');dialog.append(search);
  const body=node('div',null,'catalog-body'),grid=node('div',null,'catalog-grid'),detail=node('section',null,'catalog-detail');
  grid.setAttribute('aria-label','Models');body.append(grid,detail);dialog.append(body);
  const empty=node('p','No matching models.','catalog-empty');grid.append(empty);
  const footer=node('footer'),hint=node('span','Choose a model, then its variants.');footer.append(hint);
  const cancel=node('button','Cancel');cancel.addEventListener('click',()=>dialog.close());footer.append(cancel);
  const apply=node('button','Use model','primary');footer.append(apply);dialog.append(footer);document.body.append(dialog);
  let selected,options={},cards=new Map();
  const image=key=>{const frame=node('div',null,'catalog-image'),img=node('img');img.src='./model-catalog/'+key+'.png';img.alt='';img.width=480;img.height=320;frame.append(img);return frame;};
  function renderDetail() {
    detail.replaceChildren(image(selected.key),node('h3',selected.label),node('p',selected.description,'muted'));
    const variant=selected.options.find(o=>o.key==='variant');
    const specs=variantControls(selected,options.variant??variant?.default??'');
    specs.push(...selected.options.filter(o=>['configuration','double_style'].includes(o.key)&&!(o.key==='double_style'&&selected.key==='double')&&o.type==='choice'&&
      (o.key!=='double_style'||['double','two_stage_double','three_stage_double','double_helical'].includes(options.variant))).map(o=>({...o,value:options[o.key]??o.default})));
    for(const spec of specs) {
      const label=node('label',spec.label??'Variant'),select=node('select');select.setAttribute('aria-label',spec.label??'Variant');
      for(const choice of spec.choices){const option=node('option',choice.label);option.value=choice.value;select.append(option);}
      select.value=spec.value;
      select.dataset.catalogOption=spec.key;
      select.addEventListener('change',()=>{options[spec.option_key??spec.key]=select.value;renderDetail();queueMicrotask(()=>detail.querySelector('select[data-catalog-option="'+spec.key+'"]')?.nextElementSibling?.focus());});
      label.append(select);detail.append(label);
    }
    if(!specs.length)detail.append(node('p','Standard','muted'));
    for(const [key,card] of cards)card.setAttribute('aria-pressed',String(key===selected.key));
  }
  function choose(family) {
    selected=family;
    const current=getSelection(family.key);
    options={...Object.fromEntries(family.options.filter(o=>o.type==='choice').map(o=>[o.key,o.default])),...current};
    renderDetail();
  }
  function filter() {
    const query=search.value.trim().toLocaleLowerCase();let count=0;
    for(const [key,card] of cards){const family=getCatalog().families.find(f=>f.key===key);card.hidden=!(card.textContent+' '+family.label+' '+key).toLocaleLowerCase().includes(query);if(!card.hidden)++count;}
    empty.hidden=!!count;
  }
  opener.addEventListener('click',()=>{
    const catalog=getCatalog();if(!catalog)return;
    grid.replaceChildren(empty);cards=new Map();search.value='';
    for(const family of catalog.families){const card=node('button',null,'catalog-card');card.type='button';card.dataset.family=family.key;card.append(image(family.key),node('span',family.label));card.addEventListener('click',()=>choose(family));cards.set(family.key,card);grid.append(card);}
    choose(catalog.families.find(f=>f.key===document.getElementById('family').value)??catalog.families[0]);filter();dialog.showModal();search.focus();
  });
  dialog.addEventListener('close',onClose);
  search.addEventListener('input',filter);
  apply.addEventListener('click',()=>{onApply(selected,options);dialog.close();});
  dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}});
  return {dialog};
}
