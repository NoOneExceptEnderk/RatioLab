// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
import assert from 'node:assert/strict';
import {BrowserDocument,SOURCE_KEY} from '../webapp/document.js';
const schema={fields:[{key:'module',type:'number',minimum:.1,maximum:10,default:2}],options:[],defaults:{module:2}};
const doc=new BrowserDocument();doc.ensure(schema);
doc.editNumber('module','2.00000000000000000001');
let values=doc.values(schema).values;
assert.equal(values.module,2);assert.equal(values[SOURCE_KEY].module,'2.00000000000000000001');
const saved=JSON.parse(JSON.stringify(values));
const other=new BrowserDocument();other.replace('spur',schema,saved);
assert.deepEqual(other.values(schema).values,values);
doc.checkpoint(); // A separate committed operation, outside typing coalescence.
doc.editNumber('module','2.00000000000000000002');
assert.equal(doc.values(schema).values[SOURCE_KEY].module,'2.00000000000000000002');
doc.undo();assert.equal(doc.values(schema).values[SOURCE_KEY].module,'2.00000000000000000001');
doc.editNumber('module','0002.000');assert.equal(doc.values(schema).values[SOURCE_KEY],undefined);
other.normalize({module:2,[SOURCE_KEY]:{module:'2.00000000000000000002'}},schema);
assert.equal(other.values(schema).values[SOURCE_KEY].module,'2.00000000000000000002');
console.log('Browser precise numeric sources, project restore and undo passed');
