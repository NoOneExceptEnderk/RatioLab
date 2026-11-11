// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
import {THEME_CATALOG,normalizeThemes,themePalette,viewPalette,hexColor,changeThemeColor,exportTheme,importTheme} from './themes.js';
import {COMMANDS,CONTROL_PRESETS,MOUSE_PROFILES,MOUSE_SUMMARIES,presetBindings,shortcutLabel,normalizeSequence} from './controls.js';
const make=(tag,text=null,cls='')=>{const n=document.createElement(tag);if(text!==null)n.textContent=text;if(cls)n.className=cls;return n;};
const technical=n=>{n.dataset.noI18n='';return n;};

export class SettingsPanel {
  constructor(api) {
    this.api=api;this.modal=document.getElementById('settings-dialog');this.capture=null;this.boundsSerial=0;this.session=0;
    this.modal.addEventListener('cancel',event=>{event.preventDefault();this.close();});
    this.modal.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();if(this.capture)this.cancelCapture();else this.close();}});
    document.getElementById('settings-close').addEventListener('click',()=>this.close());
    document.getElementById('settings-done').addEventListener('click',()=>this.close());
    document.getElementById('settings-apply').addEventListener('click',()=>this.applyPrecision());
    this.pages={};this.tabs={};
    for(const [key,title]of Object.entries({appearance:'Appearance',controls:'Controls',precision:'Model precision',general:'General'})) {
      const tab=make('button',title);tab.type='button';tab.id='settings-tab-'+key;tab.setAttribute('role','tab');tab.setAttribute('aria-controls','settings-page-'+key);tab.addEventListener('click',()=>this.select(key));
      document.getElementById('settings-tabs').append(tab);this.tabs[key]=tab;
      const page=make('section',null,'settings-page');page.id='settings-page-'+key;page.setAttribute('role','tabpanel');page.setAttribute('aria-labelledby',tab.id);page.append(make('h2',title));document.getElementById('settings-pages').append(page);this.pages[key]=page;
    }
    document.getElementById('settings-tabs').addEventListener('keydown',event=>{
      if(!['ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
      event.preventDefault();const keys=Object.keys(this.tabs),i=keys.indexOf(this.page),next=event.key==='Home'?0:event.key==='End'?keys.length-1:(i+(['ArrowUp','ArrowLeft'].includes(event.key)?-1:1)+keys.length)%keys.length;this.select(keys[next]);this.tabs[keys[next]].focus();
    });
  }
  get prefs(){return this.api.preferences;}
  row(page,title,control){const label=make('label',null,'settings-row');label.append(make('span',title),control);control.setAttribute('aria-label',title);page.append(label);return control;}
  choice(values,selected,change,{translate=true}={}) {
    const select=make('select');if(!translate)technical(select);
    for(const [key,title]of Object.entries(values)){const option=make('option',title);option.value=key;select.append(option);}select.value=String(selected);select.addEventListener('change',()=>change(select.value));return select;
  }
  note(page,text){page.append(make('p',text,'muted'));}
  refresh(){this.appearance();this.controls();this.general();this.api.translate?.();}
  open(page='appearance') {
    if(this.modal.open){this.select(page);return;}
    ++this.session;this.message('Preferences apply immediately. Model precision uses Apply.');this.refresh();this.select(page);this.modal.showModal();this.tabs[page].focus();this.api.translate?.();
  }
  close(){this.cancelCapture();clearTimeout(this.boundsTimer);++this.boundsSerial;++this.session;this.precisionInputs=null;this.modal.close();document.getElementById('open-settings').focus();}
  select(key) {
    if(this.page!==key)this.cancelCapture();if(key!=='precision'){clearTimeout(this.boundsTimer);++this.boundsSerial;}this.page=key;
    for(const [name,page]of Object.entries(this.pages)){const active=name===key;page.hidden=!active;this.tabs[name].setAttribute('aria-selected',String(active));this.tabs[name].tabIndex=active?0:-1;}
    document.getElementById('settings-apply').hidden=key!=='precision';
    if(key==='precision'&&!this.precisionInputs)this.precision();
    else if(key==='precision')this.scheduleBounds();
    this.api.translate?.();
  }
  appearance() {
    const page=this.pages.appearance;page.replaceChildren(make('h2','Appearance'));
    this.row(page,'Color mode',this.choice({dark:'Dark',light:'Light'},this.prefs.theme,value=>{this.api.change('theme',value);this.appearance();this.api.translate?.();}));
    const mode=this.prefs.theme,config=normalizeThemes(this.prefs.theme_customizations),cards=make('div',null,'theme-cards');
    const names={...THEME_CATALOG.presets,...(config.imported[mode]?{custom:config.imported[mode].name}:{})};
    for(const [key,name]of Object.entries(names)) {
      const button=make('button',null,'theme-card');button.type='button';button.setAttribute('aria-pressed',String(config.active[mode]===key));button.setAttribute('aria-label',name);
      const p=themePalette(mode,config,key),swatch=make('span',null,'theme-swatch');swatch.style.background=p.window;
      for(const role of ['surface','accent','input','text']){const stripe=make('i');stripe.style.background=p[role];swatch.append(stripe);}button.append(swatch,technical(make('span',name)));
      button.addEventListener('click',()=>{const next=normalizeThemes(this.prefs.theme_customizations);next.active[mode]=key;this.api.change('theme_customizations',next);this.appearance();this.api.translate?.();});cards.append(button);
    }
    page.append(cards);
    for(const [group,title,roles]of [['colors','Interface colors',THEME_CATALOG.interface_roles],['viewport','3D view colors',THEME_CATALOG.view_roles]]) {
      const details=make('details',null,'theme-colors'),summary=make('summary',title);details.append(summary);
      for(const [role,label]of Object.entries(roles)) {
        const value=group==='colors'?themePalette(mode,config)[role]:hexColor(viewPalette(mode,config)[role]);
        const controls=make('span',null,'theme-color-controls'),picker=make('input'),hex=make('input'),reset=make('button','↶','flat');
        picker.type='color';picker.value=value;picker.setAttribute('aria-label',label);hex.type='text';hex.value=value;hex.className='theme-hex';hex.setAttribute('aria-label',label+' · #RRGGBB');hex.maxLength=7;
        reset.type='button';reset.title='Restore preset color';reset.setAttribute('aria-label','Restore preset color');
        const apply=value=>{try{const next=changeThemeColor(this.prefs.theme_customizations,mode,group,role,value);this.api.change('theme_customizations',next);const current=group==='colors'?themePalette(mode,next)[role]:hexColor(viewPalette(mode,next)[role]);picker.value=hex.value=current;hex.setAttribute('aria-invalid','false');}catch(error){hex.setAttribute('aria-invalid','true');this.message(error.message);}};
        picker.addEventListener('input',()=>apply(picker.value));hex.addEventListener('change',()=>apply(hex.value));hex.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();apply(hex.value);}});reset.addEventListener('click',()=>apply(null));controls.append(picker,hex,reset);this.row(details,label,controls);
      }
      page.append(details);
    }
    const actions=make('div',null,'settings-buttons'),reset=make('button','Restore preset colors'),exportButton=make('button','Export theme…'),importButton=make('button','Import theme…'),file=make('input');file.type='file';file.accept='.json,application/json';file.hidden=true;file.id='theme-file';
    reset.addEventListener('click',()=>{const next=normalizeThemes(this.prefs.theme_customizations);delete next.overrides[mode+':'+next.active[mode]];this.api.change('theme_customizations',next);this.appearance();this.api.translate?.();});
    exportButton.addEventListener('click',()=>{const theme=exportTheme(this.prefs.theme,this.prefs.theme_customizations);this.api.download(new Blob([JSON.stringify(theme,null,2)+'\n'],{type:'application/json'}),'RatioLab-theme.json');});
    importButton.addEventListener('click',()=>file.click());file.addEventListener('change',async()=>{const chosen=file.files[0],session=this.session;file.value='';if(!chosen)return;try{if(chosen.size>128*1024)throw Error('Theme file is too large.');const document=await chosen.text();if(!this.modal.open||session!==this.session)return;const imported=importTheme(document,this.prefs.theme_customizations);this.prefs.theme=imported.mode;this.api.change('theme_customizations',imported.config);this.appearance();this.api.translate?.();}catch(error){this.message(error.message);}});
    actions.append(reset,exportButton,importButton,file);page.append(actions);
    this.row(page,'Text size',this.choice({'1':'100%','1.25':'125%','1.5':'150%'},this.prefs.text_scale,value=>this.api.change('text_scale',Number(value))));
  }
  controls() {
    this.cancelCapture();const page=this.pages.controls;page.replaceChildren(make('h2','Controls'));
    const presetRow=make('div',null,'settings-buttons'),preset=this.choice(CONTROL_PRESETS,this.prefs.keyboard_shortcuts.preset,()=>{},{translate:false}),apply=make('button','Apply preset');preset.setAttribute('aria-label','Control preset');
    apply.addEventListener('click',()=>{this.api.shortcuts.applyPreset(preset.value);this.controls();this.api.translate?.();});presetRow.append(preset,apply);page.append(presetRow);
    this.note(page,'Apply a CAD preset to set keyboard and mouse controls. Sensitivity and zoom direction stay unchanged.');
    this.note(page,'Browser-reserved shortcuts use the available equivalents shown below. Closing windows remains a browser action.');
    this.row(page,'Mouse navigation',this.choice(MOUSE_PROFILES,this.prefs.mouse_navigation,value=>{this.api.change('mouse_navigation',value);this.controls();this.api.translate?.();},{translate:false}));
    this.note(page,MOUSE_SUMMARIES[this.prefs.mouse_navigation]);
    for(const [key,title]of [['zoom_speed','Zoom sensitivity'],['rotation_speed','Orbit sensitivity']])this.row(page,title,this.choice({'.5':'0.5×','1':'1×','2':'2×'},this.prefs[key]===.5?'.5':this.prefs[key],value=>this.api.change(key,Number(value))));
    const invert=make('input');invert.type='checkbox';invert.checked=this.prefs.invert_zoom;invert.addEventListener('change',()=>this.api.change('invert_zoom',invert.checked));this.row(page,'Invert zoom direction',invert);
    page.append(make('h3','Keyboard shortcuts'));this.note(page,'View shortcuts apply when the 3D view has keyboard focus. Text editing keeps its own shortcuts.');
    for(const [key,label]of Object.entries(COMMANDS)) {
      const controls=make('span',null,'shortcut-controls'),binding=make('button',null,'shortcut-binding'),reset=make('button','↶','flat');binding.type=reset.type='button';binding.append(this.prefs.keyboard_shortcuts.bindings[key].length?technical(make('span',shortcutLabel(this.prefs.keyboard_shortcuts.bindings[key]))):make('span','Unassigned'));reset.title='Restore preset binding';reset.setAttribute('aria-label','Restore preset binding');
      binding.addEventListener('click',()=>this.record(key,binding));reset.addEventListener('click',()=>{try{this.api.shortcuts.assign(key,presetBindings(this.prefs.keyboard_shortcuts.preset)[key]);this.controls();}catch(error){this.message(error.message.replace('{message0}',COMMANDS[error.command]??''));}this.api.translate?.();});controls.append(binding,reset);this.row(page,label,controls);controls.previousElementSibling.id='shortcut-command-'+key;binding.firstChild.id='shortcut-value-'+key;binding.setAttribute('aria-labelledby','shortcut-command-'+key+' shortcut-value-'+key);
    }
    const restore=make('button','Restore RatioLab controls');restore.addEventListener('click',()=>{this.api.shortcuts.applyPreset('ratiolab');this.controls();this.api.translate?.();});page.append(restore);
  }
  cancelCapture(){if(this.capture){this.capture.remove();this.capture=null;}if(this.api.shortcuts)this.api.shortcuts.recorder=null;}
  record(command,button) {
    this.cancelCapture();const panel=this.capture=make('div',null,'shortcut-recorder'),output=technical(make('output','…')),sequence=make('input');sequence.type='checkbox';sequence.disabled=!command.startsWith('view-');
    panel.append(make('h3',COMMANDS[command]));this.row(panel,'Two-key sequence',sequence);panel.append(output);const error=make('p',null,'error'),actions=make('div',null,'settings-buttons');panel.append(error,actions);let keys=[];
    this.api.shortcuts.recorder=(event,key)=>{if(event.key==='Escape'){this.cancelCapture();return;}keys=sequence.checked?[...keys,key].slice(-2):[key];output.textContent=keys.join(', ');};
    const save=make('button','Apply'),clear=make('button','Clear shortcut'),cancel=make('button','Cancel');
    save.addEventListener('click',()=>{try{if(!keys.length)throw Error('Choose a valid shortcut.');if(sequence.checked&&keys.length!==2)throw Error('Use one key combination or a sequence of two keys.');this.api.shortcuts.assign(command,[normalizeSequence(keys.join(' '))]);this.cancelCapture();this.controls();this.api.translate?.();}catch(e){error.textContent=e.command?e.message.replace('{message0}',COMMANDS[e.command]):e.message;this.api.translate?.();}});
    clear.addEventListener('click',()=>{this.api.shortcuts.assign(command,[]);this.cancelCapture();this.controls();this.api.translate?.();});cancel.addEventListener('click',()=>this.cancelCapture());actions.append(save,clear,cancel);button.closest('.settings-row').after(panel);panel.tabIndex=-1;panel.focus();this.api.translate?.();
  }
  general() {
    const page=this.pages.general;page.replaceChildren(make('h2','General'));
    this.row(page,'Language',this.choice(this.api.languages,this.prefs.language,value=>{this.api.change('language',value);this.api.translate?.();},{translate:false}));
    const hover=make('input');hover.type='checkbox';hover.checked=this.prefs.hover_help;hover.addEventListener('change',()=>this.api.change('hover_help',hover.checked));this.row(page,'Show parameter help on hover',hover);
    this.note(page,'Parameter guides remain available with F1 or the information button.');
    this.note(page,'CAD connections and automatic application updates are available in the desktop program.');
    const release=make('a','Release notes');release.href='https://github.com/NoOneExceptEnderk/RatioLab/releases';release.target='_blank';release.rel='noopener noreferrer';page.append(release);
  }
  message(text){document.getElementById('settings-message').textContent=text;this.api.translate?.();}
  precision() {
    const page=this.pages.precision;page.replaceChildren(make('h2','Model precision'));this.note(page,'Saved with the current project. Preview and export can use different precision.');
    const table=make('table',null,'precision-table'),thead=make('thead'),head=make('tr');for(const name of ['Setting','Requested interpolation','Sweep error bound','Complete model bound'])head.append(make('th',name));thead.append(head);table.append(thead);const body=make('tbody');table.append(body);page.append(table);this.precisionCells={};this.precisionInputs={};
    for(const [name,value]of [['Fast',.1],['Standard',.02],['Fine',.005],['Part default',null],['Preview',null],['Export',null]]) {
      const row=make('tr'),heading=make('th');heading.scope='row';
      if(!['Preview','Export'].includes(name)){const button=make('button',name);button.addEventListener('click',()=>{for(const input of Object.values(this.precisionInputs))input.value=value===null?'':String(value);this.scheduleBounds();});heading.append(button);}else heading.textContent=name;
      row.append(heading);const cells=[make('td',value===null?'—':`${value} mm · ${value*1000} µm`),make('td','Calculating…'),make('td','Calculating…')];row.append(...cells);body.append(row);this.precisionCells[name]=cells;
    }
    const details=make('details'),summary=make('summary','Precision limits');details.append(summary);
    for(const text of ['Bounds are calculated for this model, in millimetres and micrometres. They describe geometric approximation, not elastic deformation.','Sweep error is relative to sampled contours. Fixed tooth profiles and explicit meshes can limit accuracy even with Fine selected.','Complete model bounds exclude screen rendering, file conversion and manufacturing. Not bounded means no verified complete bound is available; it does not mean zero error.'])this.note(details,text);page.append(details);
    for(const [key,title]of [['preview_mm','Preview'],['export_mm','Export']]) {
      const input=make('input');input.type='text';input.inputMode='decimal';input.id='quality-'+key;input.value=String(this.api.quality()?.[key]??'');input.placeholder='Part default (normally 0.02 mm)';input.addEventListener('input',()=>this.scheduleBounds());this.row(page,title,input);this.precisionInputs[key]=input;
    }
    this.scheduleBounds();
  }
  draftQuality() {
    const quality={};for(const[key,input]of Object.entries(this.precisionInputs)){const text=input.value.trim();if(text){const number=Number(text.replace(',','.'));if(!Number.isFinite(number)||number<=0)throw Error('Enter positive interpolation values to calculate bounds.');quality[key]=number;}}return quality;
  }
  scheduleBounds(){clearTimeout(this.boundsTimer);++this.boundsSerial;this.boundsTimer=setTimeout(()=>this.calculateBounds(),250);}
  async calculateBounds() {
    if(!this.modal.open||this.page!=='precision')return;
    if(this.boundsPending){this.boundsAgain=true;return;}
    let quality;try{quality=this.draftQuality();}catch(error){for(const name of ['Preview','Export'])for(const cell of this.precisionCells[name])cell.textContent='—';this.message(error.message);return;}
    const serial=this.boundsSerial;this.boundsPending=true;this.boundsAgain=false;this.message('Calculating…');
    try {
      const results=await this.api.bounds(quality);if(!this.modal.open||serial!==this.boundsSerial)return;
      for(const [name,row]of Object.entries(results)) {
        const cells=this.precisionCells[name];if(!cells)continue;
        if(['Preview','Export'].includes(name)){const value=quality[name==='Preview'?'preview_mm':'export_mm'];cells[0].textContent=value===undefined?'Part default':`${value} mm · ${Number((value*1000).toPrecision(8))} µm`;}
        for(const [i,key]of [[1,'interpolation_text'],[2,'model_text']]){cells[i].textContent=row[key]??'Not bounded';cells[i].title=row.error??row.reason??'';}
      }
      this.message('Bounds updated.');this.api.translate?.();
    }catch(error){if(this.modal.open&&serial===this.boundsSerial)this.message(error.message);}
    finally{this.boundsPending=false;if(this.boundsAgain&&this.modal.open&&this.page==='precision')this.calculateBounds();}
  }
  async applyPrecision() {
    const button=document.getElementById('settings-apply'),session=this.session;let quality;try{quality=this.draftQuality();}catch(error){this.message(error.message);return;}
    button.disabled=true;clearTimeout(this.boundsTimer);++this.boundsSerial;this.message('Preparing preview…');
    try{await this.api.applyQuality(quality);if(this.modal.open&&session===this.session){this.message('Surface detail updated · nominal construction retained');this.scheduleBounds();}}catch(error){if(this.modal.open&&session===this.session)this.message(error.message);}finally{button.disabled=false;}
  }
}
