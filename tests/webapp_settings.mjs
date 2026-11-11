// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
import {webModules} from './webapp_modules.mjs';
const root=fileURLToPath(new URL('../',import.meta.url)),graph=webModules(root);
const t=(await graph.load('./themes.js')).namespace,c=(await graph.load('./controls.js')).namespace;
const {palettes,chords}=JSON.parse(fs.readFileSync(0,'utf8'));
for(const f of palettes){assert.deepEqual(t.themePalette(f.mode,f.config),f.colors);assert.deepEqual(t.viewPalette(f.mode,f.config),f.viewport);assert.deepEqual(t.exportTheme(f.mode,f.config),f.exported);const imported=t.importTheme(f.exported,t.themeDefaults());assert.deepEqual(t.themePalette(imported.mode,imported.config),f.colors);}
assert.throws(()=>t.importTheme('{broken',{}));assert.throws(()=>t.importTheme({...palettes[0].exported,unexpected:1},{}));
assert.throws(()=>t.importTheme({...palettes[0].exported,colors:{accent:'red'}},{}));
const unicode={...palettes[0].exported,name:'😀'.repeat(80)};assert.equal(t.importTheme(unicode,{}).config.imported.dark.name,unicode.name);
for(const f of chords)assert.equal(c.dragMode(f.profile,f.bits,f),f.expected,JSON.stringify(f));
for(const preset of Object.keys(c.CONTROL_PRESETS)){const values=c.presetBindings(preset);assert.deepEqual(c.validateBindings(values),values);assert.equal(values.close,undefined);assert.equal(values.new[0],'Alt+n');}
for(const key of ['Ctrl+n','Ctrl+o','Ctrl+r','Ctrl+1','F5','F6','F11','Ctrl+c','Alt+F4','Tab','Meta+Shift+n','Meta+q','Ctrl+Shift+i','Ctrl+PageUp'])assert.throws(()=>c.normalizeSequence(key));
assert.equal(c.shortcutLabel(['Home']),'Home');assert.equal(c.shortcutLabel(['Ctrl+s']),'Ctrl+S');
const bindings=c.presetBindings('freecad');bindings['view-top']=['v'];assert.throws(()=>c.validateBindings(bindings));
const custom=c.presetBindings();custom['view-fit']=['g'];c.validateBindings(custom);custom['view-top']=['g'];assert.throws(()=>c.validateBindings(custom));
globalThis.document=new EventTarget();const p=(await graph.load('./preferences.js')).namespace;
const prefs=structuredClone(p.DEFAULTS),calls=[],target={tagName:'CANVAS'},controller=new c.ShortcutController({preferences:prefs,run:command=>calls.push(command),viewport:t=>t===target,blocked:()=>false,changed(){}});
function key(key,{node=target,ctrl=false,alt=false,shift=false,meta=false}={}){let prevented=false;controller.keydown({key,target:node,ctrlKey:ctrl,altKey:alt,shiftKey:shift,metaKey:meta,preventDefault(){prevented=true;},stopImmediatePropagation(){}});return prevented;}
for(const preset of Object.keys(c.CONTROL_PRESETS)){const zoom=prefs.zoom_speed;controller.applyPreset(preset);assert.equal(prefs.mouse_navigation,preset);assert.equal(prefs.zoom_speed,zoom);}
controller.applyPreset('freecad');key('v');key('f');assert.equal(calls.pop(),'view-fit');
key('v');controller.cancelSequence();key('f');assert.equal(calls.length,0);
assert.equal(key('v',{node:{tagName:'INPUT'}}),false);assert.equal(key('z',{node:{tagName:'INPUT'},ctrl:true}),false);
assert.equal(key('s',{meta:true}),true);assert.equal(calls.pop(),'save');
assert.equal(key('n',{ctrl:true}),false);assert.equal(key('n',{alt:true}),true);assert.equal(calls.pop(),'new');
controller.assign('view-fit',['g']);key('g');assert.equal(calls.pop(),'view-fit');key('f');assert.equal(calls.length,0);
const original=structuredClone(prefs.keyboard_shortcuts);assert.throws(()=>controller.assign('view-top',['g']),error=>error.command==='view-fit');assert.throws(()=>controller.assign('view-fit',['1']),error=>error.command==='view-front');assert.deepEqual(prefs.keyboard_shortcuts,original);
controller.dispose();console.log('Shared palette/import parity, six CAD presets, 768 mouse chords, remaps, browser reservations and input isolation passed.');
