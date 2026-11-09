# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Owned snapshots, mutation invalidation, exact transport and bounded cursors."""
from dataclasses import replace
import gc
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from geometry import Part,Design,generate,circle
from precise_numbers import from_text
import rust_geometry as kernel
import rust_surfaces as snapshots
from solid_geometry import kernel_part,faces,rings,signature
from stl_export import triangles,write_stl


def fixture():return Part('Fixture',[(0.,0.),(2.,0.),(2.,2.),(0.,2.)],width=3.,center=(2.,-1.),z=.5)


class SurfaceSnapshotsTests(unittest.TestCase):
    def setUp(self):snapshots.clear_surface_cache();gc.collect()
    def tearDown(self):snapshots.clear_surface_cache();gc.collect()

    def test_nested_mutations_and_copies_never_reuse_a_stale_surface(self):
        p=fixture();old=snapshots.surface(p);old_volume=old.call('solid_signature')['volume_mm3']
        self.assertIs(snapshots.surface(p),old)
        p.outer[0]=(.125,0.);new=snapshots.surface(p)
        self.assertIsNot(new,old)
        self.assertNotEqual(new.call('solid_signature')['volume_mm3'],old_volume)
        self.assertEqual(old.call('solid_signature')['volume_mm3'],old_volume)
        p.holes.append(circle(.2,32,(1.,1.)));third=snapshots.surface(p)
        self.assertIsNot(third,new)
        self.assertLess(third.call('solid_signature')['volume_mm3'],new.call('solid_signature')['volume_mm3'])
        moved=replace(p,width=4.,center=(5.,6.))
        self.assertNotEqual(signature(moved)['max'],signature(p)['max'])

    def test_signed_zero_and_adjacent_decimal_sources_have_distinct_keys(self):
        p=fixture();p.center=(0.,0.);positive=snapshots.surface(p)
        p.center=(-0.,0.);negative=snapshots.surface(p);self.assertIsNot(positive,negative)
        p.width=from_text('3.00000000000000000001');a=snapshots.surface(p)
        p.width.expression='3.00000000000000000002';b=snapshots.surface(p)
        self.assertIsNot(a,b)
        self.assertEqual(a.call('solid_signature'),b.call('solid_signature'))

    def test_direct_decimal_dimensions_reach_sampled_geometry_without_serde_errors(self):
        p=replace(fixture(),width=from_text('3.00000000000000000001'))
        sampled=faces(p)
        self.assertEqual(min(q[2] for f in sampled for l in f for q in l),.5)
        self.assertEqual(max(q[2] for f in sampled for l in f for q in l),3.5)
        self.assertEqual(p.width.expression,'3.00000000000000000001')

    def test_released_snapshot_is_not_reused_and_cache_eviction_keeps_live_owners(self):
        with patch.object(snapshots,'MAX_ENTRIES',3):
            held=[snapshots.surface(replace(fixture(),center=(i,0))) for i in range(6)]
            self.assertLessEqual(snapshots.surface_cache_info()['entries'],3)
            self.assertEqual(held[0].call('solid_signature')['min'][0],0.)
            held[-1].close()
            with self.assertRaisesRegex(ValueError,'closed'):held[-1].call('solid_signature')
            rebuilt=snapshots.surface(replace(fixture(),center=(5,0)))
            self.assertFalse(rebuilt._closed)
            snapshots.clear_surface_cache()
            self.assertEqual(held[0].call('solid_signature')['max'][0],2.)
            for s in held:s.close()
            rebuilt.close()

    def test_faces_rings_triangles_and_stl_preserve_the_legacy_protocol(self):
        p=generate('double',dict(gap=1.25)).parts[0]
        args=dict(part=kernel_part(p))
        expected=kernel.call('solid_faces',args)
        actual=faces(p)
        def encoded(v):
            if isinstance(v,(list,tuple)):return [encoded(x) for x in v]
            return struct.pack('<d',v) if isinstance(v,(int,float)) else v
        self.assertEqual(encoded(actual),encoded(expected))
        self.assertEqual(encoded(rings(p)),encoded(kernel.call('solid_rings',args)))
        legacy=kernel.call_buffer('solid_triangles',args,72)
        flat=b''.join(struct.pack('<9d',*(q for point in triangle for q in point)) for triangle in triangles(p))
        self.assertEqual(flat,legacy)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'part.stl';write_stl(path,[p]);data=path.read_bytes()
        self.assertEqual(data[84:],kernel.call_buffer('solid_stl',args,50))
        self.assertEqual(len(data),84+50*struct.unpack_from('<I',data,80)[0])

    def test_part_mutation_during_a_cursor_does_not_change_its_snapshot(self):
        p=fixture();surface=snapshots.surface(p);iterator=surface.faces()
        first=next(iterator);p.width=4.;p.outer[0]=(.25,0.)
        old_faces=[first,*iterator]
        self.assertEqual(max(q[2] for face in old_faces for loop in face for q in loop),3.5)
        self.assertEqual(max(q[2] for face in faces(p) for loop in face for q in loop),4.5)
        self.assertEqual(kernel.call('surface_stats')['cursors'],0)

    def test_early_close_and_cancellation_release_cursors_with_original_exception(self):
        p=generate('worm').parts[1]
        iterator=triangles(p);next(iterator)
        self.assertEqual(kernel.call('surface_stats')['cursors'],1)
        iterator.close();self.assertEqual(kernel.call('surface_stats')['cursors'],0)
        class Stopped(Exception):pass
        calls=[]
        def stop():
            calls.append(1)
            if len(calls)>10:raise Stopped('original surface cancellation')
        with self.assertRaisesRegex(Stopped,'original surface cancellation'):list(triangles(p,stop))
        self.assertEqual(kernel.call('surface_stats')['cursors'],0)

    def test_reentrant_release_does_not_deadlock_or_destroy_an_active_cursor(self):
        s=snapshots.surface(fixture());cursor=s.call('surface_cursor_create',kind='faces')['handle']
        def release():s.close();snapshots.clear_surface_cache()
        page=kernel.call_geometry('solid_faces_chunk',dict(handle=cursor,limit=3),check=release,_backend=s._backend)
        self.assertEqual(len(page['faces']),3)
        kernel.call('surface_cursor_release',dict(handle=cursor),_backend=s._backend)
        self.assertEqual(kernel.call('surface_stats')['cursors'],0)

    def test_cursor_kinds_limits_and_stale_handles_are_rejected_without_leaks(self):
        s=snapshots.surface(fixture())
        for op,args in [('solid_faces_chunk',dict(limit=4097)),('solid_stl_chunk',dict(limit=1))]:
            cursor=s.call('surface_cursor_create',kind='faces')['handle']
            with self.subTest(op=op),self.assertRaises(ValueError):
                kernel.call_geometry(op,dict(handle=cursor,**args))
            self.assertEqual(kernel.call('surface_stats')['cursors'],0)
        old=s._handle;s.close()
        with self.assertRaises(ValueError):kernel.call('solid_signature',dict(handle=old))

    def test_owned_resources_remain_bound_to_their_original_library(self):
        if sys.platform in ('emscripten','win32'):
            self.skipTest('requires native libraries that can be unlinked while loaded')
        original=kernel._library();name=Path(original._name).name
        with tempfile.TemporaryDirectory() as folder:
            libraries=[]
            for index in (1,2):
                path=Path(folder)/(str(index)+'-'+name);shutil.copyfile(original._name,path)
                with patch.dict(os.environ,RATIOLAB_GEOMETRY_LIBRARY=str(path)):
                    kernel._library.cache_clear();libraries.append(kernel._library())
            try:
                with patch.object(kernel,'_library',return_value=libraries[0]):a=snapshots.surface(fixture())
                with patch.object(kernel,'_library',return_value=libraries[1]):
                    b=snapshots.surface(replace(fixture(),z=10.))
                    self.assertEqual(a.call('solid_signature')['min'][2],.5)
                    self.assertEqual(b.call('solid_signature')['min'][2],10.)
                    a.close();self.assertEqual(b.call('solid_signature')['min'][2],10.)
                b.close()
            finally:snapshots.clear_surface_cache();kernel._library.cache_clear()

    def test_cursor_capacity_is_recoverable_after_release(self):
        s=snapshots.surface(fixture());handles=[]
        try:
            for _ in range(kernel.call('surface_stats')['max_cursors']):
                handles.append(s.call('surface_cursor_create',kind='faces')['handle'])
            with self.assertRaisesRegex(ValueError,'resource limit'):
                s.call('surface_cursor_create',kind='faces')
            kernel.call('surface_cursor_release',dict(handle=handles.pop()))
            handles.append(s.call('surface_cursor_create',kind='faces')['handle'])
        finally:
            for h in handles:kernel.call('surface_cursor_release',dict(handle=h))
        self.assertEqual(kernel.call('surface_stats')['cursors'],0)

    def test_wasm_instances_and_streamed_triangles_have_independent_ownership(self):
        node=os.environ.get('RATIOLAB_NODE') or shutil.which('node')
        if not node:self.skipTest('Node.js required')
        root=Path(__file__).resolve().parents[1]
        result=subprocess.run([node,str(root/'tests/rust_surface_wasm.mjs'),str(root)],check=True,capture_output=True,text=True,timeout=60)
        self.assertTrue(json.loads(result.stdout)['owned_instances'])


class PackedPreviewTests(unittest.TestCase):
    def tearDown(self):snapshots.clear_surface_cache()

    def test_static_material_records_stay_positive_zero_and_wave_records_remain_dynamic(self):
        from preview3d import build_scene
        for family,values in [('spur',{}),('internal',dict(variant='double')),('worm',{})]:
            scene=build_scene(generate(family,values))
            self.assertEqual(scene.materials.tobytes(),bytes(len(scene.materials)*4))
        scene=build_scene(generate('harmonic',{}))
        self.assertTrue(any(value!=0 for value in scene.materials))
        from math import isfinite
        self.assertTrue(all(isfinite(value) for value in scene.materials))

    def test_preview_coordinate_overflow_is_rejected_before_publishing_buffers(self):
        from preview3d import build_scene
        part=replace(fixture(),center=(1e40,0.))
        with self.assertRaisesRegex(ValueError,'binary32 range'):
            build_scene(Design('spur',{},[part]))
        self.assertEqual(kernel.call('surface_stats')['cursors'],0)

    @staticmethod
    def packed_preview(n=12):
        meta=dict(format='ratiolab.preview-buffer/1',vertex_floats=n,material_floats=n//2,
                  scene=dict(parts=[],grid=[0,n//6]))
        text=json.dumps(meta).encode()
        # Include signed zero and a small normal float; copy the exact bits.
        floats=struct.pack('<6f',0.,-0.,1e-38,1.,-2.,3.)*(n//4)
        return b'\0'+struct.pack('<I',len(text))+text+floats

    def test_native_preview_owned_arrays_match_old_decoder_after_source_is_overwritten(self):
        import ctypes
        data=self.packed_preview(12)
        source=ctypes.create_string_buffer(data)
        actual=kernel._native_preview(ctypes.addressof(source),len(data),None)
        expected=kernel._decode_preview(memoryview(data)[1:])
        self.assertEqual(actual[0],expected[0])
        self.assertEqual([a.tobytes() for a in actual[1:]],[a.tobytes() for a in expected[1:]])
        before=[a.tobytes() for a in actual[1:]]
        ctypes.memset(ctypes.addressof(source),0xCD,len(data))
        self.assertEqual([a.tobytes() for a in actual[1:]],before)

    def test_large_native_preview_avoids_whole_packet_copy_and_releases_on_decode_errors(self):
        import ctypes
        from types import SimpleNamespace
        data=self.packed_preview(1200000)
        def owner():
            source=ctypes.create_string_buffer(data);released=[]
            def release(pointer):
                released.append(pointer);ctypes.memset(ctypes.addressof(source),0xCD,len(data))
            return SimpleNamespace(ratiolab_buffer_request=lambda p,n:1,
                ratiolab_buffer_request_checked=lambda p,n,callback:1,_check_type=lambda callback:callback,
                ratiolab_buffer_length=lambda p:len(data),
                ratiolab_buffer_data=lambda p:ctypes.addressof(source),
                ratiolab_buffer_free=release),released
        backend,released=owner();sizes=[];copy=ctypes.string_at
        def observe(address,length):sizes.append(length);return copy(address,length)
        with patch.object(ctypes,'string_at',observe):
            actual=kernel.preview_scene({},_backend=backend)
        expected=kernel._decode_preview(memoryview(data)[1:])
        self.assertEqual([a.tobytes() for a in actual[1:]],[a.tobytes() for a in expected[1:]])
        self.assertEqual(released,[1]);self.assertLess(max(sizes),1024)
        backend,released=owner()
        with patch.object(kernel,'_native_floats',side_effect=MemoryError('copy failed')):
            with self.assertRaisesRegex(MemoryError,'copy failed'):kernel.preview_scene({},_backend=backend)
        self.assertEqual(released,[1])
        backend,released=owner();copy_arrays=kernel._native_floats;active=[];blocks=[]
        class Stopped(Exception):pass
        def check():
            if active:
                blocks.append(True)
                if len(blocks)==2:raise Stopped('original copy cancellation')
        def controlled_copy(address,count,checker):
            active.append(True)
            try:return copy_arrays(address,count,checker)
            finally:active.clear()
        with patch.object(kernel,'_native_floats',controlled_copy):
            with self.assertRaisesRegex(Stopped,'original copy cancellation'):
                kernel.preview_scene({},_backend=backend,check=check)
        self.assertEqual(released,[1]);self.assertEqual(len(blocks),2)

    def test_borrowed_copy_view_is_released_even_when_array_copy_raises(self):
        import ctypes
        from types import SimpleNamespace
        source=ctypes.create_string_buffer(struct.pack('<f',1.));views=[]
        class FailingArray:
            itemsize=4
            def frombytes(self,view):
                views.append(view)
                raise MemoryError('copy failed')
        with patch.dict(sys.modules,{'array':SimpleNamespace(array=lambda kind:FailingArray())}):
            with self.assertRaises(MemoryError):kernel._native_floats(ctypes.addressof(source),1,None)
        with self.assertRaises(ValueError):views[0].tobytes()

    def test_native_preview_rejects_corrupt_lengths_and_ranges_before_array_reads(self):
        import ctypes
        def packet(**changes):
            meta=dict(format='ratiolab.preview-buffer/1',vertex_floats=0,material_floats=0,
                      scene=dict(parts=[],grid=[0,0]));meta.update(changes)
            text=json.dumps(meta).encode();return b'\0'+struct.pack('<I',len(text))+text
        bad=[b'',b'\0',b'\0'+struct.pack('<I',2**32-1),packet(vertex_floats=True),
             packet(vertex_floats=6,material_floats=3),packet(scene=dict(parts=[],grid=[0,1])),packet(format='wrong')]
        with patch.object(kernel,'_native_floats',side_effect=AssertionError('invalid read')):
            for data in bad:
                source=ctypes.create_string_buffer(data)
                with self.assertRaises(RuntimeError):kernel._native_preview(ctypes.addressof(source),len(data),None)

    def test_display_buffers_match_the_pre_optimization_fixture_exactly(self):
        from preview3d import build_scene
        p=fixture()
        cases=[('flat',p,'33df17a5818d8c22e0f0b3aa037643ca21241d42d2a81e6e39301ed95f6d4912'),
            ('x',replace(p,axis_x=True),'a8829bad6b4fa4c4414a70615858f1aa743347f157b466db010063f1168fa2e3'),
            ('frame',replace(p,frame=((1.,2.,3.),(0.,1.,0.),(-1.,0.,0.),(0.,0.,1.))),'7fe09ccdbd565583979140acce0c805855469e3095e56f233072608f8d38c5e3')]
        for name,part,expected in cases:
            with self.subTest(name=name):
                scene=build_scene(Design('spur',{},[part]),frame_explosion=True)
                self.assertEqual(hashlib.sha256(scene.vertices.tobytes()).hexdigest(),expected)
                self.assertEqual(hashlib.sha256(scene.materials.tobytes()).hexdigest(),'8aa01aabc92db2f90ff1ad773b41d39fae8e25472e3ca428f60d9bf417089d18')

    def test_preview_parser_rejects_lengths_and_ranges_before_allocating_arrays(self):
        from rust_geometry import _decode_preview
        def packet(**changes):
            meta=dict(format='ratiolab.preview-buffer/1',vertex_floats=0,material_floats=0,
                scene=dict(parts=[],grid=[0,0]));meta.update(changes)
            data=json.dumps(meta).encode();return memoryview(struct.pack('<I',len(data))+data)
        for data in [memoryview(b''),memoryview(struct.pack('<I',2**32-1)),packet(vertex_floats=True),
            packet(vertex_floats=6,material_floats=3),packet(scene=dict(parts=[],grid=[0,1])),packet(format='wrong')]:
            with self.assertRaises(RuntimeError):_decode_preview(data)

    def test_browser_triangle_limit_rejects_partial_output_and_can_be_retried(self):
        s=snapshots.surface(fixture())
        with self.assertRaisesRegex(ValueError,'triangle limit'):
            s.web_mesh(triangle_limit=11,compensated_sum=sys.version_info>=(3,12))
        meta,positions,normals,material=s.web_mesh(triangle_limit=12,compensated_sum=sys.version_info>=(3,12))
        self.assertEqual(meta['triangles'],12)
        self.assertEqual(len(positions),12*9*4);self.assertEqual(len(normals),len(positions))
        self.assertEqual(material,b'')
        self.assertEqual(kernel.call('surface_stats')['cursors'],0)

    def test_browser_parser_rejects_inconsistent_counts_and_formats(self):
        def packet(**changes):
            meta=dict(format='ratiolab.web-mesh-buffer/1',position_floats=0,
                normal_floats=0,material_floats=0,triangles=0);meta.update(changes)
            data=json.dumps(meta).encode();return memoryview(struct.pack('<I',len(data))+data)
        for data in [memoryview(b''),memoryview(struct.pack('<I',2**32-1)),packet(triangles=True),
            packet(triangles=1),packet(material_floats=9),packet(format='wrong')]:
            with patch.object(kernel,'_buffer_result',return_value=data),self.assertRaises(RuntimeError):
                kernel.web_mesh({})


if __name__=='__main__':unittest.main()
