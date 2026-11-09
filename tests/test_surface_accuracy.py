# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Independent sweep/triangle checks, convergence and honest scope reporting."""
from dataclasses import replace
from math import cos, sin, radians, hypot, sqrt, pi
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from geometry import Part, generate, profile_sections, circle
from precise_numbers import from_text
from rust_geometry import call
from rust_surfaces import surface, clear_surface_cache
from solid_geometry import faces, kernel_part, sampling_report, signature


def fixture(**changes):
    return replace(Part('Sweep',[(50.,0.),(50.,8.),(48.,8.),(48.,0.)],
        width=10.,twist=6.),**changes)


def ideal(part, point, z, angle):
    """Separate direct evaluation, without any kernel placement/sampling call."""
    c,s=cos(radians(angle)),sin(radians(angle))
    x,y=point[0]*c-point[1]*s+part.center[0],point[0]*s+point[1]*c+part.center[1]
    zz=z+part.z
    if part.frame:
        return tuple(part.frame[0][i]+x*part.frame[1][i]+y*part.frame[2][i]+zz*part.frame[3][i] for i in range(3))
    if part.axis_x:return zz-part.width/2,y+part.center[1],-x+part.z
    return x,y,zz


def triangle_weights(u,t,alternate=False):
    if alternate:
        return (0,(1-u-t,u,t)) if u+t<=1 else (1,(1-t,u+t-1,1-u))
    return (0,(1-u,u-t,t)) if u>=t else (1,(1-t,u,t-u))


def measured_sweep_error(part):
    """Probe actual output faces against points on the independent ideal sweep."""
    sections=profile_sections(part);fs=faces(part);maximum=0.
    for i,((za,_,_),(zb,_,_)) in enumerate(zip(sections,sections[1:])):
        for edge,a in enumerate(part.outer):
            b=part.outer[(edge+1)%len(part.outer)]
            for t in (.13,.25,.5,.73,.91):
                z=za+t*(zb-za)
                for u in (.11,.25,.37,.5,.79,.93):
                    index,weights=triangle_weights(u,t,part.alternate_diagonal)
                    triangle=fs[2*(i*len(part.outer)+edge)+index][0]
                    actual=tuple(sum(weights[k]*triangle[k][j] for k in range(3)) for j in range(3))
                    xy=tuple(a[j]+u*(b[j]-a[j]) for j in range(2))
                    wanted=ideal(part,xy,z,part.twist*z/part.width)
                    maximum=max(maximum,sqrt(sum((a-b)**2 for a,b in zip(actual,wanted))))
    return maximum


class SurfaceAccuracyTests(unittest.TestCase):
    def tearDown(self):clear_surface_cache()

    def test_vertex_trace_criterion_alone_misses_the_triangle_interior(self):
        p=fixture(twist=1.)
        # A single interval has accurate endpoint trajectories, but at the
        # middle of the first side its diagonal is over 20 micrometres away.
        c0=ideal(p,p.outer[0],0,0);c1=ideal(p,p.outer[1],p.width,p.twist)
        diagonal=tuple((a+b)/2 for a,b in zip(c0,c1))
        wanted=ideal(p,(50.,4.),p.width/2,p.twist/2)
        coarse=sqrt(sum((a-b)**2 for a,b in zip(diagonal,wanted)))
        trace=hypot(*p.outer[1])*(1-cos(radians(p.twist/2)))
        self.assertLess(trace,.002)
        self.assertGreater(coarse,.02)
        report=sampling_report(p)
        self.assertGreater(report['section_count'],2)
        self.assertLessEqual(measured_sweep_error(p),p.surface_tolerance_mm)
        self.assertGreater(report['triangle_interior_bound_mm'],report['vertex_trace_bound_mm'])

    def test_whole_side_triangles_converge_for_both_diagonals_and_hands(self):
        for hand in (-1,1):
            for alternate in (False,True):
                previous=float('inf');counts=[]
                for tolerance in (.04,.01,.002):
                    p=fixture(twist=6*hand,alternate_diagonal=alternate,surface_tolerance_mm=tolerance)
                    with self.subTest(hand=hand,alternate=alternate,tolerance=tolerance):
                        report=sampling_report(p);error=measured_sweep_error(p)
                        self.assertLessEqual(error,report['interpolation_bound_mm']+1e-11)
                        self.assertLessEqual(report['interpolation_bound_mm'],tolerance)
                        self.assertLess(error,previous);previous=error
                        self.assertTrue(report['target_met'])
                        self.assertFalse(report['profile_error_globally_bounded'])
                        counts.append(report['section_count'])
                self.assertTrue(all(a<b for a,b in zip(counts,counts[1:])))

    def test_world_scale_frames_axis_x_and_offsets_keep_the_mm_contract(self):
        frame=((10.,-20.,3.),(2.,.2,.5),(.4,1.5,.1),(.1,0.,1.))
        for p in [fixture(frame=frame),fixture(axis_x=True,center=(3.,-2.),z=4.)]:
            with self.subTest(frame=p.frame,axis_x=p.axis_x):
                report=sampling_report(p)
                self.assertLessEqual(measured_sweep_error(p),report['interpolation_bound_mm']+1e-10)
                self.assertLessEqual(report['interpolation_bound_mm'],p.surface_tolerance_mm)
        self.assertGreater(sampling_report(fixture(frame=frame))['placement_error_scale'],2.)

    def test_constant_extrusion_is_exact_relative_to_its_input_polygon(self):
        p=fixture(twist=0.)
        r=sampling_report(p)
        self.assertEqual(r['section_count'],2)
        self.assertEqual(r['interpolation_bound_mm'],0.)
        self.assertAlmostEqual(signature(p)['volume_mm3'],160.,places=11)

    def test_small_frame_scale_does_not_underflow_to_a_false_zero_bound(self):
        p=fixture(frame=((0.,0.,0.),(1e-200,0.,0.),(0.,1e-200,0.),(0.,0.,1.)),
            surface_tolerance_mm=1e-202)
        r=sampling_report(p)
        self.assertEqual(r['placement_error_scale'],1e-200)
        self.assertGreater(r['interpolation_bound_mm'],0.)
        self.assertLessEqual(r['interpolation_bound_mm'],p.surface_tolerance_mm)

    def test_larger_radius_requires_more_sections_at_the_same_angular_step(self):
        a=fixture();b=replace(a,outer=[(x*10,y*10) for x,y in a.outer])
        self.assertGreater(sampling_report(b)['section_count'],sampling_report(a)['section_count'])
        self.assertLessEqual(measured_sweep_error(b),b.surface_tolerance_mm)

    def test_cache_keys_keep_the_requested_tolerance_and_exact_decimal_source(self):
        a=fixture();old=surface(a)
        a.surface_tolerance_mm=.001;new=surface(a)
        self.assertIsNot(new,old)
        self.assertGreater(new.call('solid_sampling')['section_count'],old.call('solid_sampling')['section_count'])
        a.surface_tolerance_mm=from_text('.00100000000000000001');x=surface(a)
        a.surface_tolerance_mm=from_text('.00100000000000000002')
        self.assertIsNot(x,surface(a))
        report=sampling_report(a);report['intervals'][0]['intervals']=-1
        self.assertGreater(sampling_report(a)['intervals'][0]['intervals'],0)

    def test_explicit_station_and_mesh_sources_do_not_get_a_sweep_accuracy_claim(self):
        p=fixture(stations=[dict(z=0.,outer=[(50.,0.),(50.,8.),(48.,8.),(48.,0.)],holes=[]),
            dict(z=10.,outer=[(50.,0.),(50.,8.),(48.,8.),(48.,0.)],holes=[])])
        for q in (p,fixture(mesh=[[[(0.,0.,0.),(1.,0.,0.),(0.,1.,0.)]]])):
            r=sampling_report(q)
            self.assertEqual(r['status'],'not_evaluated')
            self.assertIsNone(r['interpolation_bound_mm']);self.assertIsNone(r['target_met'])

    def test_invalid_targets_and_exhausted_budgets_never_silently_coarsen(self):
        for tolerance in (0.,-1.,True,'bad'):
            with self.subTest(tolerance=tolerance),self.assertRaises(ValueError):
                sampling_report(fixture(surface_tolerance_mm=tolerance))
        with self.assertRaisesRegex(ValueError,'section budget'):
            sampling_report(fixture(twist=360000.,surface_tolerance_mm=1e-12))
        p=Part('Face budget',circle(100.,1024),width=10.,twist=60.,surface_tolerance_mm=.002)
        with self.assertRaisesRegex(ValueError,'250000 faces'):sampling_report(p)

    def test_double_helix_landmarks_holes_and_closed_topology_survive_refinement(self):
        for family,parameters in [('double',dict(gap=2.,helix=-35)),
            ('planetary',dict(variant='double'))]:
            design=generate(family,parameters)
            for p in design.parts:
                if not p.double:continue
                with self.subTest(family=family,part=p.name):
                    r=sampling_report(p);sections=profile_sections(p)
                    self.assertTrue(r['target_met'])
                    self.assertLessEqual(r['interpolation_bound_mm'],p.surface_tolerance_mm)
                    h=(p.width-p.gap)/2
                    self.assertIn(h,[z for z,_,_ in sections]);self.assertIn(h+p.gap,[z for z,_,_ in sections])
                    self.assertGreater(signature(p)['volume_mm3'],0)

    def test_double_shoulders_and_internal_voids_match_independent_continuous_sweeps(self):
        for internal in (False,True):
            for hand in (-1,1):
                for alternate in (False,True):
                    p=fixture(twist=6*hand,double=True,gap=2.,core_radius=46.,
                        alternate_diagonal=alternate,internal=internal,surface_tolerance_mm=.005)
                    if internal:
                        p.holes=[list(reversed(p.outer))]
                        p.outer=[(60*cos(k*pi/4),60*sin(k*pi/4)) for k in range(8)]
                    h=(p.width-p.gap)/2;shoulder=min(.15,h*.08,p.gap*.2)
                    loops=[p.outer,*p.holes]
                    def local(q,z,hole):
                        r=hypot(*q)
                        if internal and hole:
                            root=max(hypot(*x) for x in loops[hole])
                            groove=min(root+.3,min(hypot(*x) for x in p.outer)-.5)
                            f=max(0.,min(1.,(z-h+shoulder)/shoulder,(h+p.gap+shoulder-z)/shoulder))
                            radius=(1-f)*r+f*(groove+.001*(r-root))
                        elif not internal and not hole:
                            root=min(hypot(*x) for x in p.outer)
                            f=max(0.,min(1.,(z-h+shoulder)/shoulder,(h+p.gap+shoulder-z)/shoulder))
                            radius=(1-f)*r+f*(p.core_radius+.001*(r-root))
                        else:return q
                        return tuple(radius*x/r for x in q)
                    sections=profile_sections(p);fs=faces(p);offset=0;maximum=0.
                    for (za,_,_),(zb,_,_) in zip(sections,sections[1:]):
                        for hole,loop in enumerate(loops):
                            for edge,a in enumerate(loop):
                                b=loop[(edge+1)%len(loop)]
                                for t in (.17,.5,.83):
                                    z=za+t*(zb-za);angle=p.twist*min(z,p.width-z,h)/p.width
                                    aa,bb=local(a,z,hole),local(b,z,hole)
                                    for u in (.23,.5,.77):
                                        index,weights=triangle_weights(u,t,alternate)
                                        triangle=fs[offset+2*edge+index][0]
                                        actual=tuple(sum(weights[k]*triangle[k][j] for k in range(3)) for j in range(3))
                                        wanted=ideal(p,tuple(aa[j]+u*(bb[j]-aa[j]) for j in range(2)),z,angle)
                                        maximum=max(maximum,sqrt(sum((a-b)**2 for a,b in zip(actual,wanted))))
                            offset+=2*len(loop)
                    with self.subTest(internal=internal,hand=hand,alternate=alternate):
                        self.assertLessEqual(maximum,sampling_report(p)['interpolation_bound_mm']+1e-10)
                        self.assertLessEqual(maximum,p.surface_tolerance_mm)

    def test_generated_reports_keep_profile_and_interpolation_accuracy_separate(self):
        from engineering import report_text
        d=generate('helical')
        r=d.analysis['surface_sampling'][0]
        self.assertEqual(r,d.parts[0].profile_metadata['surface_sampling']|dict(part=d.parts[0].name))
        self.assertEqual(r['profile_chord_threshold_mm'],.015)
        self.assertFalse(r['profile_error_globally_bounded'])
        self.assertIn('binary32',r['scope'])
        self.assertIn('Surface interpolation relative to sampled 2D contours:',report_text(d))
        self.assertIn('No total-model error or manufacturing grade certified.',report_text(d))

    def test_native_wasm_share_bounds_and_refinement_decisions(self):
        node=os.environ.get('RATIOLAB_NODE') or shutil.which('node')
        if not node:self.skipTest('Node.js required')
        root=Path(__file__).resolve().parents[1]
        parts=[fixture(twist=t,surface_tolerance_mm=e) for t,e in [(0.,.02),(1.,.02),(6.,.01),(-6.,.002)]]
        requests=[dict(operation='solid_sampling',parameters=dict(part=kernel_part(p))) for p in parts]
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'requests.json';path.write_text(json.dumps(requests))
            result=subprocess.run([node,str(root/'tests/rust_wasm_protocol.mjs'),str(root),str(path)],
                capture_output=True,text=True,check=True,timeout=60)
        actual=json.loads(result.stdout)
        for p,response in zip(parts,actual):
            self.assertTrue(response['ok'],response)
            native=call('solid_sampling',dict(part=kernel_part(p)));wasm=response['result']
            self.assertEqual(native['section_count'],wasm['section_count'])
            self.assertAlmostEqual(native['interpolation_bound_mm'],wasm['interpolation_bound_mm'],places=12)


if __name__=='__main__':unittest.main()
