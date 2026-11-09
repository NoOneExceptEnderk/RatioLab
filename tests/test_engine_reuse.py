# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Exact reuse, backend ownership, negative controls and cooperative aborts."""
import ast
from copy import deepcopy
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

from geometry import generate,profile_sections
from internal_mesh import validate_axial_pair
from solid_geometry import kernel_part,rings,point
import rust_geometry as kernel
from rust_surfaces import surface,clear_surface_cache


class ConstructionReuseTests(unittest.TestCase):
    def setUp(self):kernel.clear_construction_cache()
    def tearDown(self):kernel.clear_construction_cache()

    def test_detached_results_and_exact_decimal_keys(self):
        from precise_numbers import SOURCE_KEY
        for source in ('2.00000000000000000001','2.00000000000000000002'):
            values={'module':2,SOURCE_KEY:{'module':source}}
            first=generate('internal',values)
            original=deepcopy(first.parts)
            first.parts[0].outer[0]=(999,999)
            first.parts[0].profile_metadata['analytic_values'].clear()
            second=generate('internal',values)
            self.assertEqual(second.parts,original)
            self.assertEqual(second.values[SOURCE_KEY]['module'],source)
        self.assertGreater(kernel.construction_cache_info()['hits'],0)

    def test_complete_keys_mutations_backend_and_bounded_eviction(self):
        args=dict(name='cache',z=22,m=2,pressure=20,backlash=.15,width=10,bore=6,center=(0,0),
            phase=0,helix=0,internal=False,rim=5,zoff=0,shift=0,ha=1,hf=1.25,
            rack_tip_radius_mm=.2,safe_pair_sampling=True)
        owner,identity=kernel.backend()
        with patch.object(kernel,'call',wraps=kernel.call) as spy:
            a=kernel.cached_call('gear_part',args)
            self.assertEqual(a,kernel.cached_call('gear_part',args));self.assertEqual(spy.call_count,1)
            args['center']=(1,0)
            b=kernel.cached_call('gear_part',args);self.assertNotEqual(a['center'],b['center'])
            with patch.object(kernel,'backend',return_value=(owner,('test-new-epoch',identity))):
                kernel.cached_call('gear_part',args)
            self.assertEqual(spy.call_count,3)
        kernel.clear_construction_cache()
        with patch.object(kernel,'CONSTRUCTION_ENTRIES',2):
            for z in (22,23,24):kernel.cached_call('gear_part',dict(args,z=z))
            self.assertEqual(kernel.construction_cache_info()['entries'],2)
        with patch.object(kernel,'CONSTRUCTION_BYTES',1):
            kernel.clear_construction_cache();kernel.cached_call('gear_part',args)
            self.assertEqual(kernel.construction_cache_info()['bytes'],0)

    def test_no_cached_errors_handles_or_cancelled_result(self):
        with self.assertRaises(ValueError):kernel.cached_call('surface_create',{})
        bad=dict(z=3,m=2,pressure=20,width=10)
        with patch.object(kernel,'call',wraps=kernel.call) as spy:
            for _ in range(2):
                with self.assertRaises(ValueError):kernel.cached_call('gear_part',bad)
            self.assertEqual(spy.call_count,2)
        generate('internal')
        class Stop(Exception):pass
        def stop():raise Stop('cache hit must still stop')
        with kernel.control_scope(stop):
            with self.assertRaises(Stop):generate('internal')
            with patch('precise_numbers.transport',side_effect=AssertionError('Must stop before encoding')):
                with self.assertRaises(Stop):kernel.call('planar_polar',dict(radius=2,angle=0))
        self.assertTrue(generate('internal').parts)

    def test_compact_axial_matches_literal_legacy_sections_and_mutations(self):
        d=generate('planetary',dict(variant='double'))
        original=next(p for p in d.parts if p.name=='S1_Planet_1')
        original_ring=next(p for p in d.parts if p.name=='S1_Ring')
        for change in ('none','twist','gap','core','ring-core','stations'):
            p=deepcopy(original);r=deepcopy(original_ring)
            if change=='twist':p.twist+=.01
            if change=='gap':p.gap+=.1
            if change=='core':p.core_radius*=1.1
            if change=='ring-core':r.core_radius*=.95
            if change=='stations':p.stations=[dict(z=0,outer=p.outer,holes=p.holes)]
            args=dict(planet=kernel_part(p),ring=kernel_part(r),zp=18,zr=54)
            rows=[dict(outer=o,base=False) for _,_,o in profile_sections(p) if o is not p.outer] if not p.stations else []
            def outcome(fn):
                try:return ('result',fn())
                except ValueError as e:return ('error',str(e))
            a=outcome(lambda:kernel.call('internal_axial',dict(args,planet_sections=rows)))
            b=outcome(lambda:validate_axial_pair(p,r,18,54))
            self.assertEqual(a,b,change)

    def test_cap_cache_retains_identical_records_and_charges_memory(self):
        clear_surface_cache()
        p=generate('internal').parts[0];s=surface(p)
        # Handle-backed section reuse must retain the complete legacy records.
        expected=kernel.call('solid_sections',dict(part=kernel_part(p)))
        self.assertEqual(s.call('solid_sections'),expected)
        self.assertEqual(s.call('solid_sections'),expected)
        before=kernel.call('surface_stats',{})['bytes'];counts=[];packets=[]
        for _ in range(2):
            calls=[0]
            def check():calls[0]+=1
            packets.append(b''.join(s.records('solid_stl_chunk',50,check)))
            counts.append(calls[0])
        self.assertEqual(packets[0],packets[1])
        self.assertGreater(counts[0],counts[1])
        stats=kernel.call('surface_stats',{})
        self.assertGreater(stats['bytes'],before)
        self.assertLessEqual(stats['bytes'],stats['max_bytes'])
        self.assertEqual(stats['cursors'],0)


class BoundsAndCancellationTests(unittest.TestCase):
    def test_world_bounds_equal_literal_vertex_walk(self):
        from combination_search import nominal_bounds
        for family,values in [('internal',{}),('internal',dict(variant='double')),
            ('planetary',dict(variant='two_stage_double')),('worm',{}),('differential',dict(configuration='classic')),('harmonic',{})]:
            d=generate(family,values);low=[float('inf')]*3;high=[-float('inf')]*3
            for p in d.parts:
                levels=([[[point(p,q[:2],q[2],0) for q in loop] for loop in face] for face in p.mesh] if p.mesh else rings(p))
                for level in levels:
                    for loop in level:
                        for v in loop:
                            for i,x in enumerate(v):low[i]=min(low[i],x);high[i]=max(high[i],x)
            actual=nominal_bounds(d)
            self.assertEqual(struct.pack('<6d',*low,*high),struct.pack('<6d',*actual[0],*actual[1]),family)

    def test_superseded_generation_stops_inside_a_phase_and_clears_control(self):
        import preview3d
        from types import SimpleNamespace
        path=Path(__file__).resolve().parents[1]/'src/app.py'
        tree=ast.parse(path.read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='prepare_geometry')
        scope=dict(generate=generate,deepcopy=deepcopy,preview3d=preview3d)
        exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),scope)
        prepare=scope['prepare_geometry'];counter=[0]
        def current():counter[0]+=1;return counter[0]<20
        request=SimpleNamespace(family='planetary',values=dict(variant='two_stage_double'),quality=None,view_flags=(False,False,False))
        clear_surface_cache();kernel.clear_construction_cache()
        self.assertIsNone(prepare(request,current))
        self.assertGreaterEqual(counter[0],20)
        self.assertTrue(generate('spur').parts)

    def test_control_scope_is_nested_and_explicit_checks_are_preserved(self):
        seen=[]
        with kernel.control_scope(lambda:seen.append('outer')):
            with kernel.control_scope(lambda:seen.append('inner')):
                kernel.call('planar_polar',dict(radius=2,angle=0),lambda:seen.append('explicit'))
        self.assertIn('outer',seen);self.assertIn('inner',seen);self.assertIn('explicit',seen)
        old=len(seen);kernel.call('planar_polar',dict(radius=2,angle=0));self.assertEqual(len(seen),old)

    def test_cancelled_scope_still_releases_owned_cursors_and_surfaces(self):
        clear_surface_cache();s=surface(generate('spur').parts[0])
        class Stop(Exception):pass
        counter=[0]
        def check():
            counter[0]+=1
            if counter[0]>8:raise Stop()
        with kernel.control_scope(check):
            with self.assertRaises(Stop):list(s.records('solid_stl_chunk',50))
            s.close()
        self.assertEqual(kernel.call('surface_stats',{})['cursors'],0)
        self.assertTrue(s._closed)


if __name__=='__main__':unittest.main()
