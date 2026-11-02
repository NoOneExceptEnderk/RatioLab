// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';
const root = fileURLToPath(new URL('../',import.meta.url));
const data = new Map([['ratiolab.web.recovery.v1','draft'],['ratiolab.web.recent.v1','projects']]);
globalThis.localStorage = {getItem:key=>data.get(key) ?? null, setItem:(key,value)=>data.set(key,value)};
const module = new vm.SourceTextModule(fs.readFileSync(root+'webapp/preferences.js','utf8'));
await module.link(()=>{throw Error('Unexpected preference dependency');}); await module.evaluate();
const {DEFAULTS,PREFERENCES_KEY,normalizePreferences,readPreferences,savePreferences} = module.namespace;
assert.deepEqual(readPreferences(),DEFAULTS);
for (const invalid of [null,[],true,'bad',{theme:[],language:'xx',text_scale:true,hover_help:1,zoom_speed:Infinity,rotation_speed:0,invert_zoom:'yes'}]) assert.deepEqual(normalizePreferences(invalid),DEFAULTS);
data.set(PREFERENCES_KEY,JSON.stringify({custom:{keep:7}}));
const chosen = {theme:'light',language:'it',text_scale:1.5,hover_help:false,zoom_speed:.5,rotation_speed:2,invert_zoom:true};
assert.equal(savePreferences(chosen),true);
assert.deepEqual(readPreferences(),chosen);
assert.deepEqual(JSON.parse(data.get(PREFERENCES_KEY)).custom,{keep:7});
assert.equal(data.get('ratiolab.web.recovery.v1'),'draft');
assert.equal(data.get('ratiolab.web.recent.v1'),'projects');
data.set(PREFERENCES_KEY,'{broken');assert.deepEqual(readPreferences(),DEFAULTS);
assert.equal(savePreferences(chosen),true);assert.deepEqual(readPreferences(),chosen);
localStorage.setItem=()=>{throw Error('Quota exceeded');};
assert.equal(savePreferences(DEFAULTS),false);assert.deepEqual(readPreferences(),chosen);
localStorage.getItem=()=>{throw Error('Storage disabled');};
assert.deepEqual(readPreferences(),DEFAULTS);assert.equal(savePreferences(DEFAULTS),false);
console.log('Browser preference validation, persistence, failure and project isolation checks passed.');
