// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
import {UI_CATALOG} from './ui-catalog.js';
export const CONTROL_PRESETS=UI_CATALOG.keyboard.presets;
export const MOUSE_PROFILES=UI_CATALOG.mouse.profiles;
export const MOUSE_SUMMARIES=UI_CATALOG.mouse.summaries;
export const COMMANDS=Object.fromEntries(Object.entries(UI_CATALOG.keyboard.commands).filter(([key])=>key!=='close'));
const object=v=>!!v&&typeof v==='object'&&!Array.isArray(v);
const projectStroke=value=>{const parts=value.split('+');if(!parts.includes('Meta')||parts.includes('Ctrl'))return value;const key=parts.pop();return ['Ctrl','Alt','Shift'].filter(m=>m==='Ctrl'||parts.includes(m)).concat(key).join('+');};
const projectFallback={new:'Alt+n',open:'Alt+o',export:'Alt+e'};
const keyNames={comma:',',Home:'Home',Return:'Enter',space:'Space'};
function fromNative(value) {
  return value.split(' ').map(part=>part.replaceAll('<Control>','Ctrl+').replaceAll('<Shift>','Shift+').replaceAll('<Alt>','Alt+').replaceAll('<Super>','Meta+').replaceAll('<Meta>','Meta+').replace(/comma$/,',')).join(' ');
}
export function presetBindings(preset='ratiolab') {
  const native=UI_CATALOG.keyboard.bindings[preset]??UI_CATALOG.keyboard.bindings.ratiolab,result={};
  for(const [command,values]of Object.entries(native)) {
    if(!Object.hasOwn(COMMANDS,command))continue;
    result[command]=values.map(fromNative);
    if(Object.hasOwn(projectFallback,command))result[command]=[projectFallback[command]];
    if(command.startsWith('view-'))result[command]=result[command].map(key=>/^Ctrl\+[1-9]$/.test(key)?key.slice(5):key==='F6'?(command==='view-fit'?'f':'0'):key);
  }
  return result;
}
export const shortcutLabel=values=>values.length?values.map(s=>s.split(' ').map(p=>p.split('+').map(k=>k.length===1?k.toUpperCase():k).join('+')).join(', ')).join(' / '):'Unassigned';
export function stroke(event) {
  let key=event.key;
  if(['Shift','Control','Alt','Meta','AltGraph','CapsLock','Unidentified'].includes(key))return null;
  key=key.length===1?key.toLowerCase():keyNames[key]??key;
  return [event.ctrlKey?'Ctrl':null,event.altKey?'Alt':null,event.shiftKey?'Shift':null,event.metaKey?'Meta':null,key].filter(Boolean).join('+');
}
export function normalizeSequence(value) {
  if(typeof value!=='string'||!value||value.length>100)throw Error('Choose a valid shortcut.');
  const parts=value.split(' ');if(!parts.length||parts.length>2||parts.some(p=>!p))throw Error('Use one key combination or a sequence of two keys.');
  return parts.map(part=>{
    const pieces=part.split('+'),key=pieces.pop(),mods=pieces;
    if(!key||mods.some(m=>!['Ctrl','Alt','Shift','Meta'].includes(m))||new Set(mods).size!==mods.length||!/^(?:[a-z0-9,.;/\-\[\]`]|F(?:[1-9]|[12][0-9]|3[0-5])|Home|End|PageUp|PageDown)$/.test(key))throw Error('This shortcut is reserved for text editing or navigation.');
    const normalized=['Ctrl','Alt','Shift','Meta'].filter(m=>mods.includes(m)).concat(key).join('+');
    const common=projectStroke(normalized),browserReserved=/^(?:Ctrl\+(?:Shift\+)?(?:[1-9nortwlpkeq]|Tab)|Ctrl\+Shift\+[cij]|Ctrl\+Page(?:Up|Down)|F[156]|F11|F12|Alt\+F4)$/i;
    if(browserReserved.test(common)||/^Ctrl\+[cxva]$/.test(common)||/^(?:Shift\+)?Meta\+[hmq]$/.test(normalized)||/^Alt\+[123]$/.test(normalized))throw Error('This shortcut is reserved by the browser.');
    return normalized;
  }).join(' ');
}
export function validateBindings(bindings) {
  if(!object(bindings)||Object.keys(bindings).length!==Object.keys(COMMANDS).length)throw Error('Choose a valid shortcut.');
  const result={},used=[];
  for(const command of Object.keys(COMMANDS)) {
    const values=bindings[command];if(!Array.isArray(values)||values.length>2)throw Error('Choose a valid shortcut.');
    result[command]=values.map(value=>{
      const sequence=normalizeSequence(value),parts=sequence.split(' ');
      if(!command.startsWith('view-')&&(parts.length!==1||!/(?:Ctrl|Alt|Meta)\+|^F\d/.test(sequence)))throw Error('Use Ctrl, Alt or a function key for project commands.');
      const canonical=command.startsWith('view-')?parts:parts.map(projectStroke);
      for(const [other,keys]of used)if(canonical.every((p,i)=>keys[i]===p)||keys.every((p,i)=>canonical[i]===p)){const error=Error('This shortcut conflicts with {message0}.');error.command=other;error.conflicts=[other,command];throw error;}
      used.push([command,canonical]);return sequence;
    });
  }
  return result;
}
export function normalizeShortcuts(data) {
  const fallback={version:1,preset:'ratiolab',bindings:presetBindings()};
  if(!object(data)||data.version!==1||!Object.hasOwn(CONTROL_PRESETS,data.preset))return fallback;
  try{return {version:1,preset:data.preset,bindings:validateBindings(data.bindings)};}catch{return fallback;}
}
export function dragMode(profile,buttons,{shift=false,control=false,alt=false,panMode=false}={}) {
  if(!Object.hasOwn(MOUSE_PROFILES,profile))profile='ratiolab';
  // DOM: left=1,right=2,middle=4. Desktop catalog: left=1,middle=2,right=4.
  const bits=(buttons&1?1:0)|(buttons&4?2:0)|(buttons&2?4:0);
  if(panMode&&bits===1)return 'pan';
  if(profile==='ratiolab')return bits===4?'pan':bits===1?'orbit':null;
  if(profile==='freecad')return bits&2?(bits&5?'orbit':'pan'):null;
  if(alt)return null;
  if(profile==='solidworks')return bits!==2||shift&&control?null:shift?'zoom':control?'pan':'orbit';
  if(profile==='solidcraft'&&bits===4)return 'orbit';
  if(bits===2){if(control)return profile==='inventor'&&!shift?'pan':null;return shift?'orbit':'pan';}
  return null;
}
export class ShortcutController {
  constructor({preferences,run,viewport,blocked,changed}) {
    Object.assign(this,{preferences,run,viewport,blocked,changed});this.pending=[];this.timer=0;this.recorder=null;
    this.listener=e=>this.keydown(e);document.addEventListener('keydown',this.listener,true);
    this.focus=()=>this.cancelSequence();document.addEventListener('focusin',this.focus);
  }
  get config(){return this.preferences.keyboard_shortcuts;}
  applyPreset(preset) {
    this.preferences.keyboard_shortcuts={version:1,preset,bindings:validateBindings(presetBindings(preset))};
    this.preferences.mouse_navigation=preset;this.cancelSequence();this.changed();
  }
  assign(command,values){const candidate=structuredClone(this.config.bindings);candidate[command]=values;let bindings;try{bindings=validateBindings(candidate);}catch(error){if(error.conflicts)error.command=error.conflicts.find(key=>key!==command)??command;throw error;}this.preferences.keyboard_shortcuts={...this.config,bindings};this.cancelSequence();this.changed();}
  cancelSequence(){this.pending=[];clearTimeout(this.timer);}
  keydown(event) {
    const key=stroke(event);if(!key||event.repeat||event.isComposing)return;
    if(this.recorder){if(event.key==='Tab'||event.target?.closest?.('.shortcut-recorder button')&&['Enter',' '].includes(event.key))return;event.preventDefault();event.stopImmediatePropagation();this.recorder(event,key);return;}
    if(this.blocked()){this.cancelSequence();return;}
    const target=event.target,editable=target?.isContentEditable||['INPUT','SELECT','TEXTAREA'].includes(target?.tagName);
    const inViewport=!editable&&this.viewport(target);
    const sequence=[...this.pending,key];let prefix=false;
    for(const [command,values]of Object.entries(this.config.bindings)) {
      if(command.startsWith('view-')&&!inViewport||editable&&['undo','redo'].includes(command))continue;
      for(const value of values) {
        const parts=value.split(' ');
        if(sequence.length<=parts.length&&sequence.every((s,i)=>s===parts[i]||!command.startsWith('view-')&&projectStroke(s)===projectStroke(parts[i]))) {
          event.preventDefault();event.stopImmediatePropagation();
          if(sequence.length===parts.length){this.cancelSequence();this.run(command);return;}
          prefix=true;
        }
      }
    }
    if(prefix){this.pending=sequence;clearTimeout(this.timer);this.timer=setTimeout(()=>this.cancelSequence(),1200);}
    else this.cancelSequence();
  }
  dispose(){this.cancelSequence();document.removeEventListener('keydown',this.listener,true);document.removeEventListener('focusin',this.focus);}
}
