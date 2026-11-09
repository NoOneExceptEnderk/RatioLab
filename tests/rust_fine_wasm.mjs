// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
// Exercise the real Wasm sampler, mesh packet and large static preview packet.
import {readFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';

const [root,input]=process.argv.slice(2);
const fixture=JSON.parse(await readFile(input,'utf8'));
const {loadRustGeometry}=await import(pathToFileURL(root+'/webapp/rust-engine.js'));
const api=await loadRustGeometry(await readFile(root+'/target/wasm32-unknown-unknown/release/ratiolab_geometry.wasm'));
const call=(operation,parameters={})=>{
 const result=JSON.parse(api(JSON.stringify({protocol:1,operation,parameters})));
 assert.equal(result.ok,true,JSON.stringify(result));return result.result;
};
const packet=(operation,parameters)=>{
 const bytes=api.buffer(JSON.stringify({protocol:1,operation,parameters}));
 assert.equal(bytes[0],0,new TextDecoder().decode(bytes.subarray(1)));
 assert.ok(bytes.length<=128*1024**2);
 const size=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength).getUint32(1,true);
 const meta=JSON.parse(new TextDecoder().decode(bytes.subarray(5,5+size)));
 const view=new DataView(bytes.buffer,bytes.byteOffset+5+size,bytes.byteLength-5-size);
 for(let i=0;i<view.byteLength;i+=4)assert.ok(Number.isFinite(view.getFloat32(i,true)));
 return {bytes:bytes.length,meta,arrayBytes:view.byteLength};
};
const handles=[],items=[];let triangles=0,refined=0,browserLimitRejected=false;
try{
 for(const part of fixture.parts){
  const handle=call('surface_create',{part:part.source}).handle;
  assert.ok(Number.isSafeInteger(handle)&&handle>0);handles.push(handle);
  const sampling=call('solid_sampling',{handle});
  if(sampling.status==='bounded'){
   assert.ok(sampling.interpolation_bound_mm<=.005);
   assert.ok(sampling.side_faces_upper_bound<=250000);
   assert.equal(sampling.side_faces_upper_bound,part.faces);
   if(sampling.collinear_edge_refinement)refined++;
  }
  const mesh=packet('web_mesh',{handle,triangle_limit:250000,compensated_sum:true});
  assert.equal(mesh.meta.format,'ratiolab.web-mesh-buffer/1');
  assert.ok(mesh.meta.triangles<=250000);
  const remaining=1000000-triangles;
  if(!browserLimitRejected&&mesh.meta.triangles>remaining){
   const refused=api.buffer(JSON.stringify({protocol:1,operation:'web_mesh',
    parameters:{handle,triangle_limit:Math.max(0,remaining),compensated_sum:true}}));
   assert.equal(refused[0],1);
   assert.match(new TextDecoder().decode(refused.subarray(1)),/triangle limit/i);
   browserLimitRejected=true;
  }
  triangles+=mesh.meta.triangles;
  const {position_floats:n,normal_floats:q,material_floats:m}=mesh.meta;
  assert.equal(n,9*mesh.meta.triangles);assert.equal(q,n);assert.ok(m===0||m===n);
  assert.equal(mesh.arrayBytes,4*(n+q+m));
  items.push({...part.meta,handle});
 }
 assert.ok(refined>0);
 const preview=packet('preview_scene',{parts:items,frame_explosion:false,compensated_sum:true,fallback_parts:[]});
 const meta=preview.meta;
 assert.equal(meta.format,'ratiolab.preview-buffer/1');
 assert.equal(meta.vertex_floats,fixture.vertex_floats);
 assert.equal(meta.material_floats,fixture.material_floats);
 assert.equal(preview.arrayBytes,4*(meta.vertex_floats+meta.material_floats));
 if(fixture.variant==='two_stage_double'){
  assert.equal(meta.material_fill,'zero');assert.equal(meta.material_floats,0);
  assert.ok(4*(meta.vertex_floats+meta.vertex_floats/2)>128*1024**2);
  assert.ok(browserLimitRejected);
 }else assert.equal(meta.material_fill,undefined);
 // This packet is also used by the desktop renderer. The browser's separate
 // one-million-triangle assembly ceiling is retained, including Fine requests.
 console.log(JSON.stringify({family:fixture.family,variant:fixture.variant,
  parts:items.length,refined,triangles,browser_assembly_within_limit:triangles<=1000000,
  browser_limit_rejected:browserLimitRejected,
  preview_bytes:preview.bytes,material_fill:meta.material_fill??'dense',actual_wasm:true}));
}finally{
 for(const handle of handles)call('surface_release',{handle});
 const stats=call('surface_stats');
 assert.equal(stats.surfaces,0);assert.equal(stats.cursors,0);assert.equal(stats.bytes,0);
}
