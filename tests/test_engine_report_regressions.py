# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Independent regressions from the Python/Rust engine comparison."""
from decimal import Decimal, localcontext
from fractions import Fraction
import json
import math
from pathlib import Path
import random
import os
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from geometry import generate, Part, section_holes
from precise_numbers import from_text, transport
from rust_geometry import call, call_buffer

TIES = [
    (20,'0.3000000000000000001',False,'2.62500000000000000088'),
    (144,'1.2000000000000000001',True,'87.90000000000000000732'),
    (132,'2.6000000000000000001',True,'174.85000000000000000672'),
    (152,'1.9000000000000000001',False,'142.02500000000000000748'),
    (96,'5.0000000000000000001',True,'246.25000000000000000492'),
    (38,'0.2000000000000000001',True,'4.05000000000000000202'),
    (134,'1.1000000000000000001',False,'72.32500000000000000658'),
]


def rounded(q):
    with localcontext() as c:
        c.prec=200
        return format((Decimal(q.numerator)/Decimal(q.denominator)).quantize(Decimal('1e-20')),'.20f')


class PrecisionReportTests(unittest.TestCase):
    def test_all_seven_reported_ties_and_neighbours(self):
        for z,m,internal,expected in TIES:
            for delta in (Fraction(-1,10**25),Fraction(0),Fraction(1,10**25)):
                with localcontext() as c:
                    c.prec=100
                    module=str(Decimal(m)+Decimal(delta.numerator)/Decimal(delta.denominator))
                q=call('cylindrical_dimensions',dict(teeth=z,module=module,internal=internal))
                oracle=rounded(Fraction(module)*(Fraction(z,2)+(Fraction(5,4) if internal else -Fraction(5,4))))
                with self.subTest(z=z,module=module,internal=internal):
                    self.assertEqual(q['values']['root_radius_mm'],oracle)
                    self.assertTrue(q['precision']['agreement'])
                    if not delta:self.assertEqual(oracle,expected)
        design=generate('spur',dict(teeth=20,module=from_text(TIES[0][1]),bore=0))
        self.assertEqual(design.parts[0].profile_metadata['analytic_values']['root_radius_mm'],TIES[0][3])

    def test_rational_fields_and_exact_cache_key_beyond_binary64(self):
        rng=random.Random(20261102)
        for _ in range(32):
            z=rng.randrange(20,161)
            m=f'{rng.randrange(1,10)}.{rng.randrange(10**20):020d}5'
            internal=bool(rng.randrange(2));mn=Fraction(m);rp=mn*z/2
            q=call('cylindrical_dimensions',dict(teeth=z,module=m,internal=internal))['values']
            expected=dict(normal_module_mm=mn,transverse_module_mm=mn,pitch_radius_mm=rp,
                tip_radius_mm=rp+(-mn if internal else mn),
                root_radius_mm=rp+(mn*Fraction(5,4) if internal else -mn*Fraction(5,4)),
                virtual_teeth=Fraction(z),transverse_pressure_angle_deg=Fraction(20),twist_deg=Fraction(0))
            for key,value in expected.items():self.assertEqual(q[key],rounded(value),(m,key))
        for m in ('2.00000000000000000001','2.00000000000000000002'):
            result=call('cylindrical_dimensions',dict(teeth=24,module=m))
            self.assertEqual(result['values']['pitch_radius_mm'],rounded(Fraction(m)*12))
            result['values']['pitch_radius_mm']='caller changed this'
            self.assertEqual(call('cylindrical_dimensions',dict(teeth=24,module=m))['values']['pitch_radius_mm'],rounded(Fraction(m)*12))
        bad=dict(teeth=24,module=2,internal='false')
        with self.assertRaisesRegex(ValueError,'boolean'):call('cylindrical_dimensions',bad)

    def test_exact_source_cancellation_bounds_and_rational_rates(self):
        tree={'expression':['sub',{'expression':['add','1e200','2.00000000000000000001']},'1e200']}
        q=call('cylindrical_dimensions',dict(teeth=24,module=tree))['values']
        self.assertEqual(q['pitch_radius_mm'],'24.00000000000000000012')
        for integer in (False,True):
            with self.assertRaises(ValueError):
                call('validate_number',dict(value={'expression':['add',1,'1e-800']},lower=0,upper=1,integer=integer))
        sqrt={'expression':['pow',{'expression':['sub',{'expression':['add','1e200',4]},'1e200']},'0.5']}
        self.assertEqual(call('numeric_compatibility',dict(value=sqrt)),2.)
        rates=call('differential_rates',dict(a='0.00000000000000000001',b=0,side_teeth=20,output_teeth=20))['values']
        self.assertEqual(rates['carrier'],'0.00000000000000000000')
        self.assertEqual(rates['output_spin'],'0.00000000000000000000')
        sampled=[[1.,2.,3.],[4.,5.,6.]]
        self.assertIs(transport(sampled),sampled)
        exact=dict(points=sampled,module=from_text('2.00000000000000000001'))
        converted=transport(exact)
        self.assertEqual(converted['module'],'2.00000000000000000001')
        self.assertIs(converted['points'],sampled)
        self.assertIsInstance(exact['module'],float)


class BufferAndMotionReportTests(unittest.TestCase):
    def test_wasm_binary_buffers_and_all_seven_decimal_ties(self):
        from solid_geometry import kernel_part
        node=os.environ.get('RATIOLAB_NODE') or shutil.which('node')
        if not node:self.skipTest('Node.js required to execute WebAssembly')
        root=Path(__file__).resolve().parents[1]
        p=Part('cube',[(-1,-1),(1,-1),(1,1),(-1,1)],width=3)
        requests=[dict(operation=op,parameters=dict(part=kernel_part(p)),binary=True)
                  for op in ('solid_triangles','solid_stl')]
        poses=[dict(kind='rotation',rate=1,offset=0,axis=[0,0,1],pivot=[1,2,3]),
               dict(kind='orbital',spin_rate=1,spin_offset=0,orbit_rate=2,orbit_offset=0,center=[1,2])]
        requests.append(dict(operation='affine_poses',parameters=dict(phase=0,poses=poses),binary=True))
        requests.extend(dict(operation='cylindrical_dimensions',parameters=dict(teeth=z,module=m,internal=internal))
                        for z,m,internal,_ in TIES)
        with tempfile.TemporaryDirectory() as folder:
            inputs=Path(folder)/'requests.json';inputs.write_text(json.dumps(requests))
            process=subprocess.run([node,str(root/'tests/rust_wasm_protocol.mjs'),str(root),str(inputs)],
                check=True,capture_output=True,text=True,timeout=60)
        results=json.loads(process.stdout)
        for request,result in zip(requests,results):
            if request.get('binary'):
                size={'solid_triangles':72,'solid_stl':50,'affine_poses':128}[request['operation']]
                records=call_buffer(request['operation'],request['parameters'],size)
                expected=b'\0'+struct.pack('<I',len(records)//size)+records
                self.assertEqual(bytes(result),expected)
            else:
                self.assertTrue(result['ok'],result)
                self.assertEqual(result['result'],call(request['operation'],request['parameters']))

    def test_binary_triangles_and_stl_are_identical_to_shared_json_surface(self):
        from solid_geometry import kernel_part
        from stl_export import write_stl
        from motion import rotation
        p=Part('offset cube',[(-1,-1),(1,-1),(1,1),(-1,1)],width=3,center=(7,-8),z=2)
        args=dict(part=kernel_part(p));expected=call('solid_triangles',args)
        packed=call_buffer('solid_triangles',args,72)
        self.assertEqual(list(struct.iter_unpack('<9d',packed)),[tuple(x for q in t for x in q) for t in expected])
        data=bytearray()
        for a,b,c in expected:
            u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
            n=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
            length=math.sqrt(sum(x*x for x in n))
            data.extend(struct.pack('<12fH',*(x/length for x in n),*a,*b,*c,0))
        with tempfile.TemporaryDirectory() as folder:
            target=write_stl(Path(folder)/'cube.stl',[p])
            self.assertEqual(target.read_bytes()[84:],data)
        # Owned output remains valid across later calls/frees.
        before=bytes(packed);rotation(.7)
        self.assertEqual(bytes(packed),before)

    def test_binary_cancellation_and_failure_cleanup(self):
        from stl_export import write_stl
        class Stopped(Exception):pass
        p=generate('spur').parts[0];calls=[]
        def stop():
            calls.append(True)
            if len(calls)>5:raise Stopped('original caller exception')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'cancel.stl'
            with self.assertRaisesRegex(Stopped,'original caller exception'):write_stl(path,[p],check=stop)
            self.assertEqual(list(Path(folder).iterdir()),[])
        with self.assertRaisesRegex(ValueError,'Unknown binary operation'):
            call_buffer('unknown',{},72)
        self.assertEqual(call('involute',dict(angle_rad=0))['values']['involute'],'0.00000000000000000000')

    def test_one_motion_batch_per_phase_and_continuous_differential_coordinates(self):
        import rust_geometry
        from motion import build_plan, rotation, multiply
        d=generate('differential',dict(input_rpm=13,input_b_rpm=-7))
        plan=build_plan(d);phase=.37
        with patch.object(rust_geometry,'pose_matrices',wraps=rust_geometry.pose_matrices) as bulk:
            before=[plan.matrix(i,phase) for i in range(len(d.parts))]
            self.assertEqual(bulk.call_count,1)
            for i in range(len(d.parts)):plan.matrix(i,phase+.1)
            self.assertEqual(bulk.call_count,2)
        rates=plan.angular_rates
        for i,p in enumerate(d.parts):
            member=p.port.get('member')
            if member in ('output','spider'):
                expected=multiply(rotation(rates['carrier']*phase,(1,0,0)),rotation(rates['output_spin']*phase,(0,0,1)))
                self.assertEqual(before[i],expected)
        from motion import update_operating_rates
        changed=update_operating_rates(d,dict(d.values,input_rpm=-19,input_b_rpm=2))
        after=build_plan(changed,plan,phase)
        for i in range(len(d.parts)):
            for x,y in zip(before[i],after.matrix(i,phase)):self.assertAlmostEqual(x,y,places=12)


class StationReportTests(unittest.TestCase):
    def test_shared_contour_cannot_choose_the_wrong_bore(self):
        from solid_geometry import section_loops
        outer=[(-3,-3),(3,-3),(3,3),(-3,3)]
        small=[(-1,-1),(-1,1),(1,1),(1,-1)]
        large=[(-2,-2),(-2,2),(2,2),(2,-2)]
        p=Part('shared contour',outer,width=2,stations=[dict(z=0,outer=outer,holes=[small]),
            dict(z=1,outer=outer,holes=[small]),dict(z=1,outer=outer,holes=[large]),dict(z=2,outer=outer,holes=[large])])
        for i,s in enumerate(p.stations):
            self.assertIs(section_holes(p,s['z'],s['outer'],i),s['holes'])
            self.assertEqual(len(section_loops(p,s['outer'],s['z'],i)[1]),4)
        self.assertEqual(section_holes(p,2,outer),[large])
        with self.assertRaisesRegex(ValueError,'Ambiguous'):section_holes(p,1,outer)

    def test_flexspline_volumes_retain_the_correct_station_holes(self):
        from solid_geometry import signature
        # Independent station-by-station integration from the comparison report.
        for variant,volume in [('cup',41023.35738362486),('flat_cup',34930.03413867845),('hat',25628.851657548785)]:
            p=generate('harmonic',dict(variant=variant)).parts[0]
            self.assertAlmostEqual(signature(p)['volume_mm3'],volume,places=7)
            for i,s in enumerate(p.stations):self.assertIs(section_holes(p,s['z'],station_index=i),s['holes'])


if __name__=='__main__':unittest.main()
