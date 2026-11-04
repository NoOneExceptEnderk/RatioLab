// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
// Preserve native select models/events while giving all choices a readable popup.
export function initChoiceMenus(root=document.body) {
  const bound=new WeakMap();let active=null,serial=0;
  const close=()=>{if(!active)return;active.popup.hidePopover();active.button.setAttribute('aria-expanded','false');active=null;};
  function enhance(select) {
    if(bound.has(select)||select.id==='family')return;
    const button=document.createElement('button');button.type='button';button.className='choice-select';button.setAttribute('aria-haspopup','listbox');button.setAttribute('aria-expanded','false');
    const caption=document.createElement('span'),arrow=document.createElement('span');arrow.textContent='⌄';arrow.setAttribute('aria-hidden','true');button.append(caption,arrow);
    const popup=document.createElement('div');popup.className='choice-popup';popup.id='choice-popup-'+(++serial);popup.setAttribute('popover','manual');button.setAttribute('aria-controls',popup.id);
    const search=document.createElement('input');search.type='search';search.placeholder='Search…';search.setAttribute('aria-label','Search');
    const list=document.createElement('div');list.setAttribute('role','listbox');popup.append(search,list);
    // Keep the popup inside its modal dialog when applicable: outside nodes
    // become inert while a modal is open, even in the top layer.
    (select.closest('dialog')??document.body).append(popup);
    select.classList.add('choice-source');select.tabIndex=-1;select.setAttribute('aria-hidden','true');select.after(button);
    const sourceLabel=select.getAttribute('aria-label')??select.labels?.[0]?.textContent;
    if(select.id){button.id=select.id+'-choice';for(const label of select.labels??[])if(label.htmlFor===select.id)label.htmlFor=button.id;}
    const record={button,popup};bound.set(select,record);
    function sync(){caption.textContent=select.selectedOptions[0]?.textContent??'';button.disabled=select.disabled;const title=select.getAttribute('aria-label')??sourceLabel??caption.textContent;button.setAttribute('aria-label',title);list.setAttribute('aria-label',title);}
    function fill(){list.replaceChildren();for(const option of select.options){if(!option.textContent.toLocaleLowerCase().includes(search.value.toLocaleLowerCase()))continue;const row=document.createElement('button');row.type='button';row.setAttribute('role','option');row.setAttribute('aria-selected',String(option.selected));row.disabled=option.disabled;row.textContent=option.textContent;row.addEventListener('click',()=>{select.value=option.value;select.dispatchEvent(new Event('change',{bubbles:true}));sync();close();button.focus();});list.append(row);} }
    function place(){
      const r=button.getBoundingClientRect(),limit=Math.min(360,innerWidth-24);
      // Size from the rendered, translated options. A short
      // choice must not inherit the whole field width or a fixed 280px minimum.
      popup.style.width='max-content';popup.style.minWidth=Math.min(132,limit)+'px';popup.style.maxWidth=limit+'px';
      const width=popup.getBoundingClientRect().width,below=Math.max(0,innerHeight-r.bottom-12);
      popup.style.left=Math.max(12,Math.min(r.left,innerWidth-width-12))+'px';
      // Keep the panel beneath its field; the option list scrolls when needed.
      popup.style.maxHeight=Math.min(360,below)+'px';
      popup.style.top=(r.bottom+5)+'px';popup.style.bottom='auto';
    }
    button.addEventListener('click',()=>{if(active?.button===button){close();return;}close();sync();search.value='';search.hidden=select.options.length<9;fill();popup.showPopover();active=record;button.setAttribute('aria-expanded','true');place();if(!search.hidden)search.focus();else(list.querySelector('[aria-selected=true]')??list.querySelector('button:not(:disabled)'))?.focus();});
    popup.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();close();button.focus();}else if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)){const rows=[...list.querySelectorAll('button:not(:disabled)')];let i=rows.indexOf(document.activeElement);i=event.key==='Home'?0:event.key==='End'?rows.length-1:(i+(event.key==='ArrowDown'?1:-1)+rows.length)%rows.length;event.preventDefault();rows[i]?.focus();}});
    button.addEventListener('keydown',event=>{if(['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();button.click();}});
    search.addEventListener('input',fill);select.addEventListener('change',sync);
    const observer=new MutationObserver(()=>{sync();if(active===record)fill();});observer.observe(select,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['disabled','label','selected','aria-label']});sync();
  }
  function discover(){for(const select of root.querySelectorAll('select'))enhance(select);if(active&&!active.button.isConnected){active.popup.remove();active=null;}for(const popup of root.querySelectorAll('.choice-popup')){if(!root.querySelector('[aria-controls="'+popup.id+'"]'))popup.remove();}}
  discover();const observer=new MutationObserver(discover);observer.observe(root,{subtree:true,childList:true});
  document.addEventListener('pointerdown',event=>{if(active&&!active.popup.contains(event.target)&&!active.button.contains(event.target))close();});
  window.addEventListener('resize',close);window.addEventListener('scroll',event=>{if(active&&!active.popup.contains(event.target))close();},true);
  return {close,disconnect:()=>observer.disconnect()};
}
