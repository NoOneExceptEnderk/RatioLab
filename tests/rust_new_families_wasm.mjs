// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
import {readFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const [root,manifestPath]=process.argv.slice(2);
const manifest=JSON.parse(await readFile(manifestPath,'utf8'));
const {loadRustGeometry}=await import(pathToFileURL(root+'/webapp/rust-engine.js'));
const owner=await loadRustGeometry(await readFile(root+'/target/wasm32-unknown-unknown/release/ratiolab_geometry.wasm'));
let coordinates=0,metadataNumbers=0,maxDelta=0;
function equal(a,b,path='metadata'){
 if(typeof a==='number'&&typeof b==='number'){
  assert.ok(Number.isFinite(a)&&Number.isFinite(b),path);const d=Math.abs(a-b);
  assert.ok(d<=1e-9,path+': '+a+' != '+b);maxDelta=Math.max(maxDelta,d);metadataNumbers++;
 }else if(Array.isArray(a)&&Array.isArray(b)){
  assert.equal(a.length,b.length,path);a.forEach((x,i)=>equal(x,b[i],path+'/'+i));
 }else if(a&&b&&typeof a==='object'&&typeof b==='object'){
  assert.deepEqual(Object.keys(a).sort(),Object.keys(b).sort(),path);
  for(const k of Object.keys(a))equal(a[k],b[k],path+'/'+k);
 }else assert.equal(a,b,path);
}
for(const row of manifest){
 const result=owner.buffer(JSON.stringify(row.request));
 if(result[0]!==0)throw Error(new TextDecoder().decode(result.subarray(1)));
 const native=await readFile(row.native);const wasm=result.subarray(1);
 const view=new DataView(wasm.buffer,wasm.byteOffset,wasm.byteLength);const m=view.getUint32(0,true);
 const nm=native.readUInt32LE(0);assert.ok(m<=16*1024*1024&&nm<=16*1024*1024);
 const decode=new TextDecoder();equal(JSON.parse(native.subarray(4,4+nm).toString()),JSON.parse(decode.decode(wasm.subarray(4,4+m))));
 const start=4+m,nstart=4+nm;assert.equal(wasm.length-start,native.length-nstart);assert.equal((wasm.length-start)%8,0);
 for(let i=0;i<wasm.length-start;i+=8){
  const a=native.readDoubleLE(nstart+i),b=view.getFloat64(start+i,true);const d=Math.abs(a-b);
  assert.ok(Number.isFinite(a)&&Number.isFinite(b)&&d<=1e-9,row.key+' coordinate '+i/8+': '+a+' != '+b);
  maxDelta=Math.max(maxDelta,d);coordinates++;
 }
}
console.log(JSON.stringify({models:manifest.length,coordinates,metadataNumbers,maxDelta,allCoordinates:true}));
