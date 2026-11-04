// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
async function load(name){const m=new vm.SourceTextModule(fs.readFileSync(new URL('../webapp/'+name,import.meta.url),'utf8'));await m.link(()=>{throw Error('Unexpected dependency');});await m.evaluate();return m.namespace;}
const {BrowserDocument}=await load('document.js'),{variantControls}=await load('model-catalog.js');
const family={key:'parallel',defaults:{module:2},fields:[{key:'module',type:'number',default:2}],options:[{key:'variant',type:'choice',default:'spur',choices:[]}]};
const d=new BrowserDocument();d.replace('parallel',family);d.editNumber('module','2.000000000012345');
const original=structuredClone(d.state),past=d.past.length;
d.selectModel('parallel',family,{variant:'three_stage_helical'});
assert.equal(d.draft.options.variant,'three_stage_helical');assert.equal(d.entries.module.text,'2.000000000012345');assert.equal(d.past.length,past+1);
assert(d.undo());assert.deepEqual(d.state,original);assert(d.redo());assert.equal(d.draft.options.variant,'three_stage_helical');
const revision=d.revision;d.selectModel('parallel',family,{variant:'three_stage_helical'});assert.equal(d.revision,revision);
for(const value of ['spur','helical','double','two_stage','two_stage_helical','two_stage_double','three_stage','three_stage_helical','three_stage_double']){
 const controls=variantControls(family,value);assert.equal(controls.length,2);
 assert(controls.every(c=>c.choices.some(choice=>choice.value===value)));
 assert(controls.every(c=>c.option_key==='variant'));
}
const other={...family,key:'cycloidal',options:[{key:'variant',default:'single',choices:[{value:'single',label:'Single'},{value:'dual',label:'Dual'}]}]};
d.selectModel('cycloidal',other,{variant:'dual'});assert.equal(d.family,'cycloidal');assert.equal(d.draft.options.variant,'dual');assert(d.undo());assert.equal(d.family,'parallel');assert.equal(d.entries.module.text,'2.000000000012345');
d.selectModel('face',other,{variant:'dual'},entries=>{entries.gap={text:'4',exact:4,typed:false};});assert.equal(d.entries.gap.text,'4');assert(d.undo());assert.equal(d.family,'parallel');
console.log('Catalog variants, raw precision, one-step undo/redo and no-op PASS');
