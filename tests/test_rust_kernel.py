# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Native ABI and independent cross-target numerical/protocol checks."""
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from rust_geometry import call

ROOT=Path(__file__).resolve().parents[1]


class KernelTransportTests(unittest.TestCase):
    def test_native_decimal_input_and_constructed_ring_protocol(self):
        q=call('cylindrical_dimensions',dict(teeth=24,module='2.00000000000000000001'))
        self.assertEqual(q['values']['pitch_radius_mm'],'24.00000000000000000012')
        self.assertTrue(q['precision']['agreement'])
        ring=call('internal_half',dict(z=72,mt=2))
        self.assertFalse(ring['metadata']['generated'])
        self.assertGreater(len(ring['points']),4)
        with self.assertRaisesRegex(ValueError,'Unknown geometry operation'):
            call('internal_unknown')

    def test_native_and_wasm_share_the_same_analytic_and_sampled_contract(self):
        node=os.environ.get('RATIOLAB_NODE') or shutil.which('node')
        if not node:self.skipTest('Node.js is required for WebAssembly execution')
        requests=[dict(operation=op,parameters=p) for op,p in [
            ('capabilities',{}),
            ('cylindrical_dimensions',dict(teeth=24,module='2.00000000000000000001')),
            ('cylindrical_dimensions',dict(teeth=12,module='3',helix='30',profile_shift='.09809')),
            ('inverse_involute',dict(involute='1e-48')),
            ('inverse_working_backlash',dict(reference_center_mm='80',transverse_pressure_deg='20',nominal_backlash_mm='.15',desired_backlash_mm='.223414903130557')),
            ('involute_profile',dict(z=18,mt=2)),('internal_half',dict(z=72,mt=2)),
            ('cycloid_profile',dict(n=16,radius=40,eccentricity=1.2,pin=3,clearance=.1)),
            ('bevel_parameters',dict(teeth=24,mate_teeth=24,module=2,pressure=20)),
            ('wave_map',dict(a=61,b=59,rp=60,material=.3,offset=2,weight=1)),
            ('collision_point_triangle',dict(point=[5000,.00001,.02],triangle=[[0,0,0],[10000,0,0],[5000,.0001,0]])),
            ('collision_triangle_distance',dict(a=[[0,0,0],[1,0,0],[0,1,0]],b=[[0,0,2],[1,0,2],[0,1,2]])),
            ('affine_rotation',dict(angle=.71,axis=[1,2,3],pivot=[7,-8,3])),
            ('affine_transform',dict(matrix=[1,0,0,0,0,1,0,0,0,0,1,0,5,7,9,1],points=[[0,0,0],[1,2,3]])),
            ('bevel_spiral_trace',dict(cone_distance=30,outer_distance=34,cone_angle=math.pi/4,beta=25,hand=-1)),
            ('bevel_split_cheek',dict(half_y=10,low=-5,high=5,seat=2,gap=.2,positive=False)),
            ('bevel_split_bridge',dict(span=15,half_y=4,seat=3,gap=.2,bolt_radius=.5,positive=False)),
            ('wolfrom_phases',dict(sun=18,planet=72,planet2=59,output_ring=135,planets=3)),
            ('wolfrom_exact_rates',dict(sun=18,planet=72,planet2=59,output_ring=135,numerator='-137',denominator='19')),
        ]]
        native=[call(q['operation'],q['parameters']) for q in requests]
        with tempfile.TemporaryDirectory() as temporary:
            inputs=Path(temporary)/'requests.json';inputs.write_text(json.dumps(requests))
            completed=subprocess.run([node,str(ROOT/'tests/rust_wasm_protocol.mjs'),str(ROOT),str(inputs)],
                capture_output=True,text=True,check=True,timeout=60)
            wasm=json.loads(completed.stdout)
        def equal(a,b):
            if type(a) is float:
                self.assertTrue(math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-8),(a,b))
            elif isinstance(a,dict):
                self.assertEqual(set(a),set(b))
                for key in a:equal(a[key],b[key])
            elif isinstance(a,list):
                self.assertEqual(len(a),len(b))
                for x,y in zip(a,b):equal(x,y)
            else:self.assertEqual(a,b)
        for a,b in zip(native,wasm):
            self.assertTrue(b['ok'],b)
            equal(a,b['result'])

    def test_native_cooperative_cancellation_preserves_callers_exception(self):
        class Stopped(Exception):pass
        invocations=[]
        def check():
            invocations.append(True)
            if len(invocations)>5:raise Stopped('test deadline')
        face=[[[math.cos(i*math.pi/60)*(2 if i%2 else 3),math.sin(i*math.pi/60)*(2 if i%2 else 3),0] for i in range(120)]]
        with self.assertRaisesRegex(Stopped,'test deadline'):
            call('solid_triangulate',dict(face=face),check=check)
        # Cancellation must not remain attached to later calls on this thread.
        self.assertEqual(call('involute',dict(angle_rad=0))['values']['involute'],'0.00000000000000000000')

    def test_collision_surface_ownership_and_positive_distance(self):
        from collision_geometry import Surface,relation
        mesh=[[[1,0,0],[0,1,0],[0,0,1]],[[0,0,0],[0,0,1],[0,1,0]],
              [[0,0,0],[1,0,0],[0,0,1]],[[0,0,0],[0,1,0],[1,0,0]]]
        first=Surface(mesh)
        second=Surface([[[x+3,y,z] for x,y,z in t] for t in mesh])
        handle=first._handle
        try:
            self.assertEqual(relation(first,second,.000001)['kind'],'Separated')
            self.assertEqual(first.contains((.1,.1,.1),.000001),True)
            self.assertAlmostEqual(relation(first,second,.000001)['distance'],2.)
        finally:
            first.close();second.close()
        with self.assertRaisesRegex(ValueError,'expired'):
            call('collision_nearest',dict(handle=handle,point=[0,0,0]))
