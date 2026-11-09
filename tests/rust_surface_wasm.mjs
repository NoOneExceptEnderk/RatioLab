// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
import {readFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const root=process.argv[2];
const {loadRustGeometry}=await import(pathToFileURL(root+'/webapp/rust-engine.js'));
const bytes=new Uint8Array(await readFile(root+'/target/wasm32-unknown-unknown/release/ratiolab_geometry.wasm'));
const first=await loadRustGeometry(bytes),second=await loadRustGeometry(bytes);
assert.notEqual(first.epoch,second.epoch);
const call=(owner,operation,parameters={})=>{
 const response=JSON.parse(owner(JSON.stringify({protocol:1,operation,parameters})));
 assert.equal(response.ok,true,JSON.stringify(response));return response.result;
};
const part=z=>({outer:[[0,0],[2,0],[2,2],[0,2]],holes:[],width:3,z,center:[0,0]});
const a=call(first,'surface_create',{part:part(.5)}).handle;
const b=call(second,'surface_create',{part:part(10)}).handle;
assert.equal(a,b); // Equal IDs belong to independent instances.
assert.equal(call(first,'solid_signature',{handle:a}).min[2],.5);
assert.equal(call(second,'solid_signature',{handle:b}).min[2],10);
const cursor=call(second,'surface_cursor_create',{handle:b,kind:'triangles'}).handle;
let triangles=0;
for(;;){
 const data=second.buffer(JSON.stringify({protocol:1,operation:'solid_triangles_chunk',parameters:{handle:cursor,limit:5}}));
 assert.equal(data[0],0);
 const count=new DataView(data.buffer,data.byteOffset,data.byteLength).getUint32(1,true);
 assert.equal(data.length,5+count*72);triangles+=count;
 if(count<5)break;
}
assert.equal(triangles,12);
call(second,'surface_cursor_release',{handle:cursor});
call(first,'surface_release',{handle:a});
assert.equal(call(second,'solid_signature',{handle:b}).min[2],10);
call(second,'surface_release',{handle:b});
assert.equal(call(first,'surface_stats').surfaces,0);
assert.equal(call(second,'surface_stats').cursors,0);
assert.equal(call(second,'surface_stats').bytes,0);
console.log(JSON.stringify({epochs:[first.epoch,second.epoch],triangles,owned_instances:true}));
