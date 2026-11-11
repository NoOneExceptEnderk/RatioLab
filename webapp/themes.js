// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
import {UI_CATALOG} from './ui-catalog.js';
export const THEME_CATALOG=UI_CATALOG.themes;
const object=value=>!!value&&typeof value==='object'&&!Array.isArray(value);
const modes=['dark','light'];
export const themeDefaults=()=>({version:1,active:{dark:'ratiolab',light:'ratiolab'},overrides:{},imported:{}});
export function color(value) {
  if(typeof value!=='string'||!/^#[0-9a-f]{3}(?:[0-9a-f]{3})?$/i.test(value.trim()))throw Error('Use a color in #RRGGBB format.');
  value=value.trim().toLowerCase();return value.length===4?'#'+[...value.slice(1)].map(c=>c+c).join(''):value;
}
export const rgb=value=>[1,3,5].map(i=>parseInt(color(value).slice(i,i+2),16)/255);
const evenRound=value=>value-Math.floor(value)===.5?2*Math.round(value/2):Math.round(value);
export const hexColor=values=>'#'+values.map(v=>evenRound(Math.min(1,Math.max(0,v))*255).toString(16).padStart(2,'0')).join('');
const mix=(a,b,t)=>hexColor(rgb(a).map((v,i)=>v*(1-t)+rgb(b)[i]*t));
const luminance=c=>rgb(c).reduce((n,v,i)=>n+[.2126,.7152,.0722][i]*(v<=.04045?v/12.92:((v+.055)/1.055)**2.4),0);
const contrast=(a,b)=>(Math.max(luminance(a),luminance(b))+.05)/(Math.min(luminance(a),luminance(b))+.05);
function related(p) {
  const {accent:a,text:t,surface:s}=p;
  return {...p,on_accent:contrast('#000000',a)>=contrast('#ffffff',a)?'#000000':'#ffffff',focus:mix(a,t,.2),
    hover:mix(s,t,.07),active:mix(s,a,.08),selected:mix(s,a,.22),field_label:t,number:t,derived:mix(s,a,.06),
    io_input:a,io_result:mix(a,t,.35),trough:p.line,slider:t,preview_state:s,preview_text:t,preview_line:p.line};
}
function colors(raw,allowed,strict=false) {
  if(!object(raw)){if(strict)throw Error('Invalid theme colors.');return {};}
  const result={};
  for(const [key,value]of Object.entries(raw)) {
    if(!Object.hasOwn(allowed,key)){if(strict)throw Error('Unknown theme color.');continue;}
    try{result[key]=color(value);}catch(e){if(strict)throw e;}
  }
  return result;
}
export function normalizeThemes(raw) {
  const result=themeDefaults();if(!object(raw)||raw.version!==1)return result;
  for(const mode of modes) {
    const item=raw.imported?.[mode];
    if(object(item))result.imported[mode]={name:typeof item.name==='string'&&item.name.trim()&&!/[\x00-\x1f]/.test(item.name)?[...item.name].slice(0,80).join(''):'Imported theme',
      colors:colors(item.colors,THEME_CATALOG.palettes[mode].ratiolab.colors),viewport:colors(item.viewport,THEME_CATALOG.view_roles)};
    for(const preset of [...Object.keys(THEME_CATALOG.presets),'custom']) {
      const entry=raw.overrides?.[mode+':'+preset];
      if(object(entry))result.overrides[mode+':'+preset]={colors:colors(entry.colors,THEME_CATALOG.palettes[mode].ratiolab.colors),viewport:colors(entry.viewport,THEME_CATALOG.view_roles)};
    }
    const active=raw.active?.[mode];
    if(Object.hasOwn(THEME_CATALOG.presets,active)||active==='custom'&&result.imported[mode])result.active[mode]=active;
  }
  return result;
}
export function themePalette(mode,config,preset=null,{customized=true}={}) {
  mode=modes.includes(mode)?mode:'dark';config=normalizeThemes(config);preset??=config.active[mode];
  let result={...THEME_CATALOG.palettes[mode][preset==='custom'?'ratiolab':preset].colors};
  const apply=values=>{if(Object.keys(values).some(k=>Object.hasOwn(THEME_CATALOG.interface_roles,k)))result=related({...result,...Object.fromEntries(Object.entries(values).filter(([k])=>Object.hasOwn(THEME_CATALOG.interface_roles,k)))});Object.assign(result,values);};
  if(preset==='custom')apply(config.imported[mode]?.colors??{});
  if(customized)apply(config.overrides[mode+':'+preset]?.colors??{});
  return result;
}
export function viewPalette(mode,config,preset=null,{customized=true}={}) {
  mode=modes.includes(mode)?mode:'dark';config=normalizeThemes(config);preset??=config.active[mode];
  const result=structuredClone(THEME_CATALOG.palettes[mode][preset==='custom'?'ratiolab':preset].viewport);
  if(preset==='custom')for(const[k,v]of Object.entries(config.imported[mode]?.viewport??{}))result[k]=rgb(v);
  if(customized)for(const[k,v]of Object.entries(config.overrides[mode+':'+preset]?.viewport??{}))result[k]=rgb(v);
  return result;
}
export function changeThemeColor(config,mode,group,key,value) {
  const result=normalizeThemes(config),allowed=group==='colors'?THEME_CATALOG.palettes[mode].ratiolab.colors:group==='viewport'?THEME_CATALOG.view_roles:{};
  if(!Object.hasOwn(allowed,key))throw Error('Unknown theme color.');
  const slot=mode+':'+result.active[mode];result.overrides[slot]??={colors:{},viewport:{}};
  if(value===null)delete result.overrides[slot][group][key];else result.overrides[slot][group][key]=color(value);
  return result;
}
export function exportTheme(mode,config) {
  config=normalizeThemes(config);const preset=config.active[mode];
  return {format:'ratiolab-theme/1',name:preset==='custom'?config.imported[mode].name:THEME_CATALOG.presets[preset],mode,
    colors:themePalette(mode,config),viewport:Object.fromEntries(Object.entries(viewPalette(mode,config)).map(([k,v])=>[k,hexColor(v)]))};
}
export function importTheme(document,config) {
  if(typeof document==='string'){if(new TextEncoder().encode(document).length>128*1024)throw Error('Theme file is too large.');try{document=JSON.parse(document);}catch{throw Error('Not a RatioLab theme file.');}}
  if(!object(document)||document.format!=='ratiolab-theme/1')throw Error('Not a RatioLab theme file.');
  if(Object.keys(document).some(k=>!['format','name','mode','colors','viewport'].includes(k)))throw Error('Unknown theme field.');
  const mode=document.mode;if(!modes.includes(mode))throw Error('Invalid theme mode.');
  const name=document.name??'Imported theme';if(typeof name!=='string'||!name.trim()||[...name].length>80||/[\x00-\x1f]/.test(name))throw Error('Invalid theme name.');
  const c=colors(document.colors??{},THEME_CATALOG.palettes[mode].ratiolab.colors,true),v=colors(document.viewport??{},THEME_CATALOG.view_roles,true);
  if(!Object.keys(c).length&&!Object.keys(v).length)throw Error('Invalid theme colors.');
  const result=normalizeThemes(config);result.imported[mode]={name:name.trim(),colors:c,viewport:v};delete result.overrides[mode+':custom'];result.active[mode]='custom';return {config:result,mode};
}
