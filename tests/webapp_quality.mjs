// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {BrowserDocument} from '../webapp/document.js';
const schema=JSON.parse(readFileSync(0,'utf8'));
const doc=new BrowserDocument();doc.replace('helical',schema);
doc.editNumber('module','2.00000000000000000001');
const raw=structuredClone(doc.entries),values=doc.values(schema).values;
const old=doc.token();
assert(doc.setQuality({preview_mm:.1,export_mm:1e-7}));
assert(!doc.matches(old));assert.deepEqual(doc.entries,raw);assert.deepEqual(doc.values(schema).values,values);
assert.equal(doc.state.quality.export_mm,1e-7);
assert(doc.undo());assert.equal(doc.state.quality,undefined);
assert(doc.redo());assert.equal(doc.state.quality.preview_mm,.1);
const saved=doc.recovery();const recovered=new BrowserDocument();recovered.replace('helical',schema,{},'quality',{recovery:saved});
assert.deepEqual(recovered.state.quality,doc.state.quality);
const current=doc.token();
for(const quality of [{preview_mm:0},{export_mm:Infinity},{preview_mm:'0.1'},{unknown:1}]) assert.throws(()=>doc.setQuality(quality));
assert(doc.matches(current));
const imported=new BrowserDocument();imported.replace('helical',schema,values,'import',{quality:doc.state.quality});
assert.deepEqual(imported.state.quality,doc.state.quality);assert.equal(imported.dirty,false);
imported.replace('helical',schema);assert.equal(imported.state.quality,undefined);
console.log(JSON.stringify({quality_history:true,recovery:true,import:true,raw_precision:true,invalid_requests_rejected:true}));
