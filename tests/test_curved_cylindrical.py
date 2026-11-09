# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Independent tensor evaluation, whole-surface budgets and source boundaries."""
from collections import Counter
from copy import deepcopy
import importlib.util
import json
from math import atan2,cos,sin,sqrt
import os
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
import unittest
from bisect import bisect_right

from curved_cad import document,export
from curved_cylindrical import _reference
from geometry import generate
from rust_geometry import call

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('cylindrical_reference',ROOT/'scripts/verify-curved-cad.py')
reference=importlib.util.module_from_spec(spec);spec.loader.exec_module(reference)

def geometry(design,tolerance=.001):
    _,_,parameters=_reference(design)
    return call('cad_cylindrical_geometry',dict(parameters,tolerance_mm=tolerance))

def casteljau(points,u):
    while len(points)>1:
        points=[tuple((1-u)*a+u*b for a,b in zip(p,q)) for p,q in zip(points,points[1:])]
    return points[0]

def tensor(patch,piece,axial,u,v):
    def evaluate(points,degree,knots,multiplicities,t):
        expanded=[k for k,m in zip(knots,multiplicities) for _ in range(m)]
        span=min(len(points)-1,bisect_right(expanded,t)-1)
        d=[tuple(p) for p in points[span-degree:span+1]]
        for r in range(1,degree+1):
            for j in range(degree,r-1,-1):
                i=span-degree+j;alpha=(t-expanded[i])/(expanded[i+degree-r+1]-expanded[i])
                d[j]=tuple((1-alpha)*a+alpha*b for a,b in zip(d[j-1],d[j]))
        return d[degree]
    uu=patch['u_knots'][piece]+u*(patch['u_knots'][piece+1]-patch['u_knots'][piece])
    vv=patch['v_knots'][axial]+v*(patch['v_knots'][axial+1]-patch['v_knots'][axial])
    columns=[]
    for i in range(len(patch['poles'])):
        points=[]
        for j in range(len(patch['poles'][i])):
            w=patch['weights'][i][j];point=patch['poles'][i][j]
            points.append((*[x*w for x in point],w))
        columns.append(evaluate(points,3,patch['v_knots'],patch['v_multiplicities'],vv))
    point=evaluate(columns,patch['u_degree'],patch['u_knots'],patch['u_multiplicities'],uu)
    return tuple(x/point[-1] for x in point[:3])


class CurvedCylindricalTests(unittest.TestCase):
    def test_entire_tensor_interior_respects_combined_profile_axial_budget(self):
        for family,parameters in [('helical',{}),('helical',dict(helix=-35,width=30)),
            ('internal',dict(variant='spur')),('internal',dict(variant='helical',helix=-30,width=25))]:
            with self.subTest(family=family,parameters=parameters):
                g=geometry(generate(family,parameters));profile=g['profile'];sweep=g['sweep'];sources=profile['reference_sources']
                limit=sweep['surface_interpolation_bound_mm']+sweep['resolution_guard_mm']*8
                self.assertLess(sweep['surface_interpolation_bound_mm']+sweep['resolution_guard_mm'],.001)
                # One complete tooth contains all surface constructions; the
                # remaining teeth are rigidly rotated copies of these patches.
                for patch in g['patches'][:7]:
                    rows=profile['curves'][patch['first_curve']:patch['first_curve']+patch['curve_count']]
                    for piece,row in enumerate(rows):
                        for u in (.137,.5,.863):
                            if row['kind']=='cubic':xy=reference.expected(row,u,sources,True)
                            else:
                                base=tensor(patch,piece,0,u,0);cx,cy=row['center_mm']
                                angle=atan2(base[1]-cy,base[0]-cx)
                                xy=(cx+row['radius_mm']*cos(angle),cy+row['radius_mm']*sin(angle))
                            for axial in range(sweep['intervals']):
                                for v in (.19,.5,.87):
                                    t=(axial+v)/sweep['intervals']
                                    actual=tensor(patch,piece,axial,u,v)
                                    ideal=reference.sweep_point(xy,t,sweep)
                                    self.assertLessEqual(sqrt(sum((a-b)**2 for a,b in zip(actual,ideal))),limit)

    def test_helical_volume_uses_the_rotation_polynomial_not_constant_section_area(self):
        g=geometry(generate('helical',dict(width=30,helix=35)),.01)
        factor=reference.rotation_volume_factor(g['sweep'])
        self.assertLess(factor,1.)
        self.assertGreater(factor,.999)
        self.assertGreater(g['sweep']['axial_bound_mm'],0)

    def test_fine_requests_refine_both_directions_without_changing_face_count(self):
        counts=[]
        for tolerance in (.01,.001,.000001):
            g=geometry(generate('helical',dict(teeth=30,width=8)),tolerance)
            self.assertLess(g['sweep']['surface_interpolation_bound_mm']+g['sweep']['resolution_guard_mm'],tolerance)
            self.assertEqual(len(g['patches']),7*30)
            self.assertTrue(all(w>0 for p in g['patches'] for row in p['weights'] for w in row))
            counts.append((sum(len(p['poles']) for p in g['patches']),g['sweep']['intervals']))
        self.assertTrue(all(a[0]<b[0] and a[1]<=b[1] for a,b in zip(counts,counts[1:])))

    def test_both_hands_retain_the_same_profile_and_reverse_the_helix(self):
        for family,base in [('helical',{}),('internal',dict(variant='helical'))]:
            a=geometry(generate(family,dict(base,helix=25)))
            b=geometry(generate(family,dict(base,helix=-25)))
            self.assertEqual(a['profile'],b['profile'])
            self.assertEqual(a['sweep']['twist_rad'],-b['sweep']['twist_rad'])
            for x,y in zip(a['sweep']['rotation_controls'],b['sweep']['rotation_controls']):
                self.assertEqual(x[0],y[0]);self.assertEqual(x[1],-y[1])

    def test_zero_helix_limit_retains_analytic_extrusion(self):
        g=geometry(generate('helical',dict(helix=0)))
        self.assertEqual(g['sweep']['axial_bound_mm'],0)
        self.assertEqual(g['sweep']['intervals'],1)
        self.assertEqual(set(p['surface_type'] for p in g['patches']),{'extrusion','cylinder'})

    def test_shared_edges_have_opposite_winding_for_outer_and_inner_surfaces(self):
        for family,parameters in [('helical',{}),('internal',{}),('internal',dict(variant='helical'))]:
            text,info=document(generate(family,parameters))
            entities=dict(re.findall(r'^#(\d+)=(.*);$',text,re.M));counts=Counter()
            for value in entities.values():
                m=re.fullmatch(r"ORIENTED_EDGE\('',\*,\*,#(\d+),(\.[TF]\.)\)",value)
                if m:counts[m.groups()]+=1
            for edge,value in entities.items():
                if value.startswith('EDGE_CURVE('):
                    self.assertEqual(counts[edge,'.T.'],1,(family,edge))
                    self.assertEqual(counts[edge,'.F.'],1,(family,edge))
            self.assertEqual(text.count('MANIFOLD_SOLID_BREP('),1)
            self.assertNotIn('FACETED_BREP',text)

    def test_ring_export_is_explicitly_selected_and_preserves_project_and_motion(self):
        d=generate('internal',dict(variant='helical',module=2,_decimal_inputs={'module':'2.00000000000000000001'}),
            quality=dict(preview_mm=.1,export_mm=.005));before=deepcopy(d)
        with TemporaryDirectory() as temporary:
            folder,info=export(d,Path(temporary)/'ring')
            self.assertEqual(info['source_component_index'],2)
            self.assertEqual(info['component'],d.parts[1].name)
            self.assertEqual(info['source_components'],len(d.parts))
            data=json.loads((folder/'project.config.json').read_text())
            self.assertEqual(data['parameters']['_decimal_inputs']['module'],'2.00000000000000000001')
            self.assertEqual(data['quality'],d.quality)
            self.assertEqual(d,before)

    def test_modified_ring_provenance_twist_or_profile_is_rejected(self):
        for field in ('radius','twist','hole','plain_outer'):
            d=generate('internal');part=d.parts[1]
            if field=='radius':part.outer.radius+=.01
            if field=='twist':part.twist+=.01
            if field=='hole':part.holes[0][1]=(0.,0.)
            if field=='plain_outer':part.outer=list(part.outer)
            with self.subTest(field=field),self.assertRaises(ValueError):document(d)
        with self.assertRaisesRegex(ValueError,'prototype'):document(generate('internal',dict(variant='double')))

    def test_surface_resource_limits_and_cancellation_never_accept_coarser_output(self):
        _,_,parameters=_reference(generate('helical'))
        for changes in (dict(tolerance_mm=1e-30),dict(tolerance_mm=1e-6,twist_deg=180),dict(width=-1)):
            with self.subTest(changes=changes),self.assertRaises(ValueError):call('cad_cylindrical_geometry',dict(parameters,**changes))
        class Stopped(Exception):pass
        visits=[]
        def check():
            visits.append(1)
            if len(visits)>10:raise Stopped('surface deadline')
        with self.assertRaisesRegex(Stopped,'surface deadline'):
            call('cad_cylindrical_geometry',dict(parameters,tolerance_mm=1e-6),check=check)

    def test_native_wasm_surface_contract(self):
        node=os.environ.get('RATIOLAB_NODE')
        if not node:self.skipTest('Node is required for the real Wasm kernel.')
        requests=[]
        for family,parameters in [('helical',{}),('internal',dict(variant='helical'))]:
            _,_,p=_reference(generate(family,parameters))
            requests.append(dict(operation='cad_cylindrical_geometry',parameters=dict(p,tolerance_mm=.01)))
        with TemporaryDirectory() as temporary:
            source=Path(temporary)/'requests.json';source.write_text(json.dumps(requests))
            result=subprocess.run([node,str(ROOT/'tests/rust_wasm_protocol.mjs'),str(ROOT),str(source)],
                capture_output=True,text=True,check=True,timeout=60)
            answers=json.loads(result.stdout)
        def compare(a,b):
            if isinstance(a,float):self.assertAlmostEqual(a,b,delta=max(1e-10,abs(a)*1e-12))
            elif isinstance(a,dict):
                self.assertEqual(set(a),set(b))
                for key in a:compare(a[key],b[key])
            elif isinstance(a,list):
                self.assertEqual(len(a),len(b))
                for x,y in zip(a,b):compare(x,y)
            else:self.assertEqual(a,b)
        for request,answer in zip(requests,answers):
            self.assertTrue(answer['ok'],answer)
            compare(call(request['operation'],request['parameters']),answer['result'])


if __name__=='__main__':unittest.main()
