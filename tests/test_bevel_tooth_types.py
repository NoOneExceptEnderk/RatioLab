# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Curved bevel traces: independent circles, normals, phase and mesh oracles."""
from dataclasses import replace
from math import acos, atan2, cos, sin, sqrt, pi, hypot, tan, radians, log
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sys
import unittest

from geometry import generate, validate, get_specs
from bevel_pair import dimensions, CircularProfile, TRACE_TOLERANCE
from motion import build_plan, update_operating_rates, rotation, transform
from collision_geometry import Surface, relation, cross, dot
from solid_geometry import signature, faces
from stl_export import triangles
from test_bevel_geometry import rx, rz, frame_a, normal


def contact_errors(a, b):
    """Solve n.V=0 using finite-difference runtime normals and literal positions."""
    for distance in (.86*a.outer_distance, .94*a.outer_distance, a.outer_distance):
        for side in (-1, 1):
            for fraction in (.1, .3, .5, .7, .9):
                theta=max(a.root,a.base)+(a.tip-max(a.root,a.base))*fraction
                phase=pi/2-pi/a.teeth
                point=frame_a(a.point(theta,distance,side,phase))
                n=frame_a(normal(a,theta,distance,side,phase))
                def residual(turn):
                    return dot(rx(n,turn),cross((1,0,a.teeth/b.teeth),rx(point,turn)))
                c=(residual(0)+residual(pi))/2
                aa=residual(0)-c;bb=residual(pi/2)-c;amplitude=hypot(aa,bb)
                if abs(c)>amplitude:continue
                offset=atan2(bb,aa);arc=acos(max(-1,min(1,-c/amplitude)))
                for turn in (offset+arc,offset-arc):
                    mate=rz(rx(point,turn),a.teeth/b.teeth*turn)
                    polar=atan2(hypot(mate[0],mate[1]),mate[2])
                    if not max(b.root,b.base)+1e-6<polar<b.tip-1e-6:continue
                    angle=atan2(mate[1],mate[0])-b.trace(distance)
                    angle=(angle+pi/b.teeth)%(2*pi/b.teeth)-pi/b.teeth
                    sign=1 if angle>=0 else -1
                    error=abs(abs(angle)-b.half_angle(polar))*distance*sin(polar)
                    centre=atan2(mate[1],mate[0])-b.trace(distance)-sign*b.half_angle(polar)
                    other=normal(b,polar,distance,sign,centre)
                    yield error,abs(dot(rz(rx(n,turn),a.teeth/b.teeth*turn),other)),abs(residual(turn))


class BevelToothTypesTests(unittest.TestCase):
    def test_active_specs_and_unsupported_hypoid_or_invalid_hand(self):
        for variant,key in [('straight',None),('spiral','spiral_angle'),('zerol','trace_radius')]:
            names={s[0] for s in get_specs('bevel',variant)}
            self.assertEqual('spiral_angle' in names,key=='spiral_angle')
            self.assertEqual('trace_radius' in names,key=='trace_radius')
            self.assertEqual('spiral_hand' in names,key is not None)
        for variant in ('spiral','zerol'):
            for hand in (0,1.5,True):
                with self.assertRaises(ValueError):validate('bevel',dict(variant=variant,spiral_hand=hand))
        for values in (dict(variant='hypoid'),dict(variant='spiral',spiral_angle=46),
                       dict(variant='zerol',trace_radius=1),dict(variant='zerol',trace_radius=float('nan'))):
            with self.assertRaises(ValueError):generate('bevel',values)

    def test_spiral_reference_equation_and_exact_zero_surface_limit(self):
        straight=generate('bevel')
        for hand in (-1,1):
            d=generate('bevel',dict(variant='spiral',spiral_hand=hand))
            a,b,_=dimensions(d.values)
            for fraction in (.8,.93,1):
                r=a.outer_distance*fraction
                expected=hand*tan(radians(35))/sin(a.delta)*log(fraction)
                self.assertAlmostEqual(a.trace(r),expected,places=14)
                self.assertAlmostEqual(a.teeth*a.trace(r)+b.teeth*b.trace(r),0,places=12)
            zero=generate('bevel',dict(variant='spiral',spiral_angle=0,spiral_hand=hand))
            self.assertEqual([signature(p) for p in zero.parts],[signature(p) for p in straight.parts])
            self.assertEqual([faces(p) for p in zero.parts],[faces(p) for p in straight.parts])

    def test_zerol_literal_developed_circle_zero_mean_angle_and_mirroring(self):
        profiles=[]
        for hand in (-1,1):
            d=generate('bevel',dict(variant='zerol',spiral_hand=hand));a,b,_=dimensions(d.values)
            profiles.append(a)
            self.assertIsInstance(a,CircularProfile)
            for distance in (a.outer_distance-8,a.mean_distance,a.outer_distance):
                # Undo only the heel indexing offset, then test the literal
                # Cartesian circle stated by the reference, not the acos formula.
                angle=a.trace(distance)*sin(a.delta)+hand*a.developed_angle(a.outer_distance)
                x,y=distance*cos(angle),distance*sin(angle)
                self.assertAlmostEqual((x-a.mean_distance)**2+(y-hand*50)**2,2500,places=9)
                self.assertAlmostEqual(a.teeth*a.trace(distance)+b.teeth*b.trace(distance),0,places=12)
            step=.0001
            derivative=(a.trace(a.mean_distance+step)-a.trace(a.mean_distance-step))/(2*step)
            self.assertAlmostEqual(derivative,0,delta=1e-9)
            self.assertNotEqual(a.trace(a.mean_distance),a.trace(a.outer_distance))
        for distance in (profiles[0].mean_distance,profiles[0].outer_distance-8):
            self.assertAlmostEqual(profiles[0].trace(distance),-profiles[1].trace(distance),places=14)
        straight=generate('bevel')
        self.assertNotEqual(signature(d.parts[0]),signature(straight.parts[0]))

    def test_independent_common_normals_both_types_hands_and_odd_counts(self):
        for variant in ('spiral','zerol'):
            for hand in (-1,1):
                for z,w in ((20,40),(21,41),(24,24)):
                    a,b,_=dimensions(validate('bevel',dict(variant=variant,spiral_hand=hand,pinion=z,wheel=w,backlash=0)))
                    rows=list(contact_errors(a,b));self.assertGreater(len(rows),10)
                    self.assertLess(max(x[0] for x in rows),2e-7)
                    self.assertLess(max(abs(1-x[1]) for x in rows),2e-8)
                    self.assertLess(max(x[2] for x in rows),2e-12)
                wrong=replace(b,trace_hand=-b.trace_hand) if variant=='zerol' else replace(b,k=-b.k)
                self.assertGreater(max(x[0] for x in contact_errors(a,wrong)),.01)

    def test_circular_engagement_lower_bound_against_independent_dense_profile_angles(self):
        for hand in (-1,1):
            v=validate('bevel',dict(variant='zerol',spiral_hand=hand))
            a,b,info=dimensions(v);inner=a.outer_distance-v['width'];dense=[[],[]]
            self.assertTrue(info['is_lower_bound'])
            for j in range(10001):
                s=-.35+.7*j/10000
                x=cos(a.delta)*cos(s)-sin(radians(20))*sin(a.delta)*sin(s)
                y=-cos(radians(20))*sin(s)
                z=sin(a.delta)*cos(s)+sin(radians(20))*cos(a.delta)*sin(s)
                theta=atan2(hypot(y,z),x);mate=atan2(hypot(x,y),z)
                if not max(a.base,a.root)<=theta<=a.tip or not max(b.base,b.root)<=mate<=b.tip:continue
                lo=max(inner*cos(a.delta)/x,inner*cos(b.delta)/z)
                hi=min(a.outer_distance*cos(a.delta)/x,a.outer_distance*cos(b.delta)/z)
                if lo>hi:continue
                for sign,values in zip((-1,1),dense):
                    for r in (lo,hi,max(lo,min(hi,a.mean_distance))):
                        values.append(atan2(z,y)-a.half_angle(theta)-sign*a.trace(r))
            spans=[(max(values)-min(values))/(2*pi/a.teeth) for values in dense]
            for bound,actual in zip(info['flank_contact_phase_spans_teeth'],spans):
                self.assertLessEqual(bound,actual+.0015)
                self.assertAlmostEqual(bound,actual,delta=.003)

    def test_axial_vertex_chords_respect_stated_bound_and_bores_remain_cylindrical(self):
        for variant in ('spiral','zerol'):
            d=generate('bevel',dict(variant=variant));a,b,_=dimensions(d.values)
            distances=d.analysis['bevel_pair']['cone_stations_mm']
            for q,p in zip((a,b),d.parts):
                self.assertGreater(len(p.stations),2)
                self.assertGreater(signature(p)['volume_mm3'],0)
                heel=q.outer_distance*cos(q.delta)
                for station in p.stations:
                    self.assertEqual(station['holes'],p.holes)
                for index in range(0,len(p.outer),max(1,len(p.outer)//30)):
                    x,y=p.outer[index];polar=atan2(hypot(x,y),heel)
                    actual=hypot(hypot(x,y),heel)
                    phase=atan2(y,x)-q.trace(actual)-q.half_angle(polar)
                    for j,(low,high) in enumerate(zip(distances,distances[1:])):
                        for f in (.25,.5,.75):
                            r=low+(high-low)*f
                            expected=q.point(polar,actual*r/q.outer_distance,1,phase)
                            start=p.stations[j]['outer'][index];end=p.stations[j+1]['outer'][index]
                            error=hypot(*(expected[k]-(start[k]+(end[k]-start[k])*f) for k in (0,1)))
                            self.assertLessEqual(error,TRACE_TOLERANCE*1.00001)

    def test_actual_mesh_cycle_positions_and_half_tooth_error_control(self):
        for variant in ('spiral','zerol'):
            for hand in (-1,1):
                d=generate('bevel',dict(variant=variant,spiral_hand=hand,pinion=21,wheel=41))
                plan=build_plan(d);self.assertTrue(plan.supported)
                meshes=[list(triangles(p)) for p in d.parts]
                for fraction in (0,.31,.73):
                    phase=2*pi/21*fraction
                    surfaces=[Surface([tuple(transform(plan.matrix(i,phase),v) for v in t) for t in mesh]) for i,mesh in enumerate(meshes)]
                    self.assertEqual(relation(*surfaces,1e-6)['kind'],'Separated',(variant,hand,fraction))
                wrong=rotation(pi/41)
                shifted=Surface([tuple(transform(wrong,v) for v in t) for t in meshes[1]])
                self.assertEqual(relation(Surface(meshes[0]),shifted,1e-6)['kind'],'Intersection')

    def test_projects_reverse_rates_worker_and_canonical_exports_for_both_types(self):
        import cad_export,stl_export,profile_export
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'webapp'))
        import engine_bridge as web
        for variant in ('spiral','zerol'):
            values=dict(variant=variant,spiral_angle=27.1234567890123,trace_radius=47.1234567890123,spiral_hand=-1,io_scheme='reverse')
            d=generate('bevel',values);restored=generate('bevel',json.loads(json.dumps(d.values)))
            self.assertEqual(d.parts,restored.parts)
            plan=build_plan(d)
            for rpm in (-37.1234567890123,0,123):
                changed=update_operating_rates(d,dict(d.values,input_rpm=rpm))
                updated=build_plan(changed,plan,.7)
                self.assertEqual(changed.parts[0].port['rpm'],-2*rpm)
                self.assertIs(changed.parts[0].stations,d.parts[0].stations)
                for i in (0,1):
                    for a,b in zip(plan.matrix(i,.7),updated.matrix(i,.7)):self.assertAlmostEqual(a,b,places=12)
                d,plan=changed,updated
            engine=web.Engine();result=engine.call('generate',dict(family='bevel',parameters=d.values))
            self.assertEqual(result['analysis'],d.analysis)
            self.assertTrue(result['motion']['supported'])
            fields={f['key'] for f in web.schema('bevel',d.values)['fields']}
            self.assertEqual('trace_radius' in fields,variant=='zerol')
            self.assertEqual('spiral_angle' in fields,variant=='spiral')
            with TemporaryDirectory() as td:
                _,info=cad_export.export(d,Path(td)/'step')
                self.assertEqual(len(info),2)
                stl_export.export(d,Path(td)/'stl');profile_export.export(d,Path(td)/'profiles')
                self.assertTrue(any(Path(td).rglob('*.dxf')))


if __name__=='__main__':unittest.main()
