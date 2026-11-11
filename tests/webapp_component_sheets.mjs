// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const metadata=JSON.parse(fs.readFileSync(0,'utf8'));
const module=new vm.SourceTextModule(fs.readFileSync(new URL('../webapp/document.js',import.meta.url),'utf8'));
await module.link(()=>{throw Error('Unexpected import');});await module.evaluate();
const {BrowserDocument}=module.namespace;
const schema={fields:[{key:'width',type:'number',default:10}],options:[],defaults:{width:10}};
const doc=new BrowserDocument();
doc.replace('spur',schema,{width:10},'company.json',{component_sheets:metadata});
assert.deepEqual(doc.state.component_sheets,metadata);assert.equal(doc.dirty,false);
doc.editNumber('width','12');assert.deepEqual(doc.state.component_sheets,metadata);
doc.undo();assert.deepEqual(doc.state.component_sheets,metadata);assert.equal(doc.dirty,false);
doc.redo();assert.deepEqual(doc.state.component_sheets,metadata);
const recovery=doc.recovery();const restored=new BrowserDocument();
restored.replace('spur',schema,{},'recovered',{recovery});
assert.deepEqual(restored.state.component_sheets,metadata);assert.equal(restored.entries.width.text,'12');
restored.replace('spur',schema,{},'new');assert.equal(restored.state.component_sheets,undefined);
console.log('Component sheet browser document checks passed');
