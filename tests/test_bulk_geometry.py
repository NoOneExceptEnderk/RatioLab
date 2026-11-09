# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Lossless construction transport and batched exact-source regressions."""
import json
import math
import struct
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from geometry import generate,validate,circle,batch_circles,CircleProfile
from precise_numbers import from_text,symbolic,evaluate_sources,select_source,PreciseFloat
from rust_geometry import call,call_geometry,_decode_geometry


class BulkGeometryTests(unittest.TestCase):
    def test_native_wasm_geometry_packets_and_exact_batch(self):
        node=os.environ.get('RATIOLAB_NODE') or shutil.which('node')
        if not node:self.skipTest('Node.js required to execute Wasm')
        root=Path(__file__).resolve().parents[1]
        requests=[dict(operation='planar_circles',parameters=dict(circles=[dict(radius=2.,count=12,center=[0.,0.])]),binary=True),
                  dict(operation='bevel_spiral_stations',parameters=dict(outer=[[1.,0.],[0.,2.],[-3.,0.]],distances=[9.,10.],cone_distance=10.,cone_angle=math.pi/4,heel=7.,toe=6.,beta=35,hand=-1),binary=True),
                  dict(operation='numeric_batch',parameters=dict(values=[{'expression':['sub',{'expression':['add','1e200','2.00000000000000000001']},'1e200']},{'choose':['max',.6,'0.60000000000000000001']}]))]
        with tempfile.TemporaryDirectory() as folder:
            inputs=Path(folder)/'requests.json';inputs.write_text(json.dumps(requests))
            result=subprocess.run([node,str(root/'tests/rust_wasm_protocol.mjs'),str(root),str(inputs)],check=True,capture_output=True,text=True,timeout=60)
        actual=json.loads(result.stdout)
        def equivalent(a,b):
            if isinstance(a,dict):
                self.assertEqual(set(a),set(b))
                for k in a:equivalent(a[k],b[k])
            elif isinstance(a,(list,tuple)):
                self.assertEqual(len(a),len(b))
                for x,y in zip(a,b):equivalent(x,y)
            elif isinstance(a,float):self.assertTrue(math.isclose(a,b,rel_tol=1e-13,abs_tol=1e-13),(a,b))
            else:self.assertEqual(a,b)
        for request,result in zip(requests,actual):
            if request.get('binary'):
                self.assertEqual(result[0],0)
                equivalent(call_geometry(request['operation'],request['parameters']),_decode_geometry(memoryview(bytes(result))[1:]))
            else:
                self.assertTrue(result['ok'],result)
                equivalent(call(request['operation'],request['parameters']),result['result'])

    def tree_equal(self,a,b):
        if isinstance(a,dict):
            self.assertEqual(set(a),set(b))
            for key in a:self.tree_equal(a[key],b[key])
        elif isinstance(a,(tuple,list)):
            self.assertEqual(len(a),len(b))
            for x,y in zip(a,b):self.tree_equal(x,y)
        elif isinstance(a,(int,float)) and not isinstance(a,bool):
            self.assertEqual(struct.pack('<d',a),struct.pack('<d',b),(a,b))
        else:self.assertEqual(a,b)

    def test_typed_constructions_preserve_every_coordinate_and_metadata(self):
        cases=[('worm',dict(variant=variant,worm_hand=hand)) for variant in ('za','zi') for hand in (-1,1)]
        cases += [('harmonic',dict(variant=v)) for v in ('cup','flat_cup','hat')]
        cases.append(('harmonic',dict(module=from_text('2.00000000000000000001'))))
        cases.append(('harmonic',dict(module=PreciseFloat(2.,{'expression':['sub',{'expression':['add','1e200','2.00000000000000000001']},'1e200']}))))
        for family,parameters in cases:
            args=dict(values=validate(family,parameters));op='construction_'+family
            with self.subTest(family=family,parameters=parameters):
                self.tree_equal(call(op,args),call_geometry(op,args))

    def test_spiral_stations_and_circles_match_legacy_json(self):
        args=dict(outer=[[1.,0.],[0.,2.],[-3.,0.]],distances=[9.,10.],cone_distance=10.,cone_angle=math.pi/4,heel=7.,toe=6.,beta=35,hand=-1)
        self.tree_equal(call('bevel_spiral_stations',args),call_geometry('bevel_spiral_stations',args))
        specs=[dict(radius=r,count=n,center=[.3,-.2]) for r,n in [(2.,96),(3.5,48),(0.,3)]]
        self.tree_equal([call('planar_circle',spec) for spec in specs],call_geometry('planar_circles',dict(circles=specs)))

    def test_malformed_geometry_packets_are_bounded(self):
        def packet(result,raw=b'',format='ratiolab.geometry-buffer/1'):
            meta=json.dumps(dict(format=format,result=result)).encode()
            return memoryview(struct.pack('<I',len(meta))+meta+raw)
        tag=lambda desc:{'$ratiolab.f64/1':desc}
        for data in [memoryview(b''),memoryview(struct.pack('<I',2**32-1)),packet({},b'x'),
            packet(tag([-1,1,2]),bytes(16)),packet(tag([0,1,4]),bytes(32)),packet(tag([False,1,2]),bytes(16)),
            packet(tag([0,1000000000,2]),bytes(16)),packet([tag([0,1,2]),tag([0,1,2])],bytes(32)),
            packet({},bytes(16)),packet({},format='unknown')]:
            with self.assertRaises(RuntimeError):_decode_geometry(data)

    def test_owned_output_and_cooperative_cancellation(self):
        class Stopped(Exception):pass
        args=dict(values=validate('worm',{}));calls=[]
        def stop():
            calls.append(1)
            if len(calls)>5:raise Stopped('original exception')
        with self.assertRaisesRegex(Stopped,'original exception'):call_geometry('construction_worm',args,check=stop)
        result=call_geometry('construction_worm',args)
        saved=struct.pack('<2d',*result['parts'][0]['outer'][0])
        call_geometry('construction_harmonic',dict(values=validate('harmonic',{})))
        self.assertEqual(struct.pack('<2d',*result['parts'][0]['outer'][0]),saved)

    def test_explicit_cancellation_reaches_decode_after_native_buffer_is_freed(self):
        import rust_geometry as kernel
        library=kernel._library();inside=[];checks=[];decode=kernel._decode_geometry
        class Stopped(Exception):pass
        def stop():
            if inside:
                checks.append(True)
                if len(checks)==4:raise Stopped('explicit decode cancellation')
        def observe(*args,**kwargs):
            inside.append(True)
            try:return decode(*args,**kwargs)
            finally:inside.clear()
        with patch.object(kernel,'_decode_geometry',observe),patch.object(
                library,'ratiolab_buffer_free',wraps=library.ratiolab_buffer_free) as released:
            with self.assertRaisesRegex(Stopped,'explicit decode cancellation'):
                kernel.call_geometry('planar_circles',dict(circles=[
                    dict(radius=2,count=4097,center=[0,0])]),check=stop)
            self.assertEqual(released.call_count,1)
        self.assertEqual(len(checks),4)
        self.assertEqual(len(kernel.call_geometry('planar_circles',dict(circles=[
            dict(radius=2,count=12,center=[0,0])]))[0]),12)

    def test_circle_batch_preserves_provenance_and_unwinds(self):
        expected=circle(2.,48,(3.,-1.))
        with batch_circles():
            a=circle(2.,48,(3.,-1.))
            with batch_circles():b=circle(2.,48,(3.,-1.))
        self.assertEqual(a,expected);self.assertEqual(b,expected)
        self.assertTrue(a.intact());self.assertTrue(b.intact())
        a[0]=(0.,0.);self.assertFalse(a.intact());self.assertTrue(b.intact())
        with self.assertRaises(ValueError):
            with batch_circles():circle(-1.)
        self.assertEqual(circle(2.,48,(3.,-1.)),expected)

    def test_planetary_batches_exact_dimensions_and_circles(self):
        import rust_geometry
        from precise_numbers import SOURCE_KEY
        original=rust_geometry.call;operations=[]
        def observe(op,*args,**kwargs):operations.append(op);return original(op,*args,**kwargs)
        with patch.object(rust_geometry,'call',side_effect=observe),patch('geometry.rust_call',side_effect=observe),patch.object(rust_geometry,'call_geometry',wraps=rust_geometry.call_geometry) as bulk:
            d=generate('planetary',dict(variant='two_stage_double',module=from_text('2.00000000000000000001')))
        self.assertEqual(operations.count('numeric_batch'),1)
        # The previous precise two-stage layout needed 72 scalar requests.
        # Validation and unrelated finalization retain their independent calls.
        self.assertLess(operations.count('numeric_compatibility'),24)
        self.assertEqual(sum(row.args[0]=='planar_circles' for row in bulk.call_args_list),1)
        self.assertEqual(d.values[SOURCE_KEY]['module'],'2.00000000000000000001')
        self.assertTrue(all(p.outer for p in d.parts))


class ExactBatchTests(unittest.TestCase):
    def test_full_source_survives_cancellation_and_selectors(self):
        m=symbolic(from_text('2.00000000000000000001'))
        source=(m+1e200)-1e200
        result=evaluate_sources(dict(value=source,scaled=source*12,selected=select_source('max',[.6,m*.65])))
        self.assertEqual(result['value'].expression,{'expression':['sub',{'expression':['add','2.00000000000000000001',1e200]},1e200]})
        self.assertEqual(call('cylindrical_dimensions',dict(teeth=24,module=result['value']))['values']['pitch_radius_mm'],'24.00000000000000000012')
        self.assertEqual(result['scaled'],24.)
        self.assertIsInstance(result['selected'],PreciseFloat)

    def test_selector_plain_branches_keep_ordinary_binary_arithmetic(self):
        m=symbolic(from_text('0.30000000000000000001'))
        selected=select_source('max',[.6,m*.65])
        data=evaluate_sources(dict(radius=(3.+selected)*.7))
        self.assertEqual(struct.pack('<d',data['radius']),struct.pack('<d',(3.+.6)*.7))
        self.assertNotIsInstance(data['radius'],PreciseFloat)

    def test_ties_keep_the_original_selected_source(self):
        a=from_text('2.00000000000000000001');b=from_text('2.00000000000000000002')
        result=evaluate_sources([select_source('min',[symbolic(a),symbolic(b)]),select_source('max',[symbolic(b),symbolic(a)])])
        self.assertEqual(result[0].expression,a.expression)
        self.assertEqual(result[1].expression,b.expression)

    def test_invalid_batch_has_no_partial_success_or_lingering_state(self):
        for args in [dict(values=[1,{'expression':['div',1,0]}]),dict(values=[{'choose':['unknown',1,2]}]),dict(values=[0]*513)]:
            with self.assertRaises(ValueError):call('numeric_batch',args)
        self.assertEqual(call('numeric_batch',dict(values=['2.00000000000000000001']))[0]['value'],2.)


if __name__=='__main__':unittest.main()
