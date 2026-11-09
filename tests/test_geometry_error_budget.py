# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Independent 120-digit boundary witnesses, placements and negative controls."""
from dataclasses import replace
import json,os,shutil,subprocess,tempfile,unittest
from pathlib import Path
import mpmath as mp
from geometry import generate
from geometry_error_budget import audit,available_report,UnsupportedBudget
from geometry_quality import report,with_quality
from rust_geometry import call


def oracle(curve,t):
    t=mp.mpf(t)
    def rotate(x,y,a):return x*mp.cos(a)-y*mp.sin(a),x*mp.sin(a)+y*mp.cos(a)
    if curve['kind']=='rack_corner':
        q={k:mp.mpf(v) for k,v in curve['tool'].items()}
        u=(q['tip_center_u']+q['tip_radius']*mp.cos(t))/q['cos_beta']
        v=q['tip_center_v']+q['tip_radius']*mp.sin(t)
        dx=-q['tip_radius']*mp.sin(t)/q['cos_beta'];dy=q['tip_radius']*mp.cos(t)
        phi=(u+v*dy/dx)/q['pitch_radius']
        return rotate(u-q['pitch_radius']*phi,q['pitch_radius']+v,mp.mpf(curve['rotation'])-phi)
    if curve['kind']=='involute_flank':
        rb=mp.mpf(curve['rb']);rp=mp.mpf(curve['rp'])
        def involute(r):
            if r<=rb:return mp.mpf(0)
            angle=mp.acos(rb/r);return mp.tan(angle)-angle
        angle=mp.mpf(curve['half'])+involute(rp)-involute(t)
        return t*mp.cos(angle),t*mp.sin(angle)
    return tuple(mp.mpf(curve['radius'])*f(t) for f in (mp.cos,mp.sin))


def distance(p,a,b):
    d=[b[i]-a[i] for i in range(2)];den=sum(x*x for x in d)
    t=max(mp.mpf(0),min(mp.mpf(1),sum((p[i]-a[i])*d[i] for i in range(2))/den)) if den else mp.mpf(0)
    return mp.sqrt(sum((p[i]-a[i]-t*d[i])**2 for i in range(2)))


class GeometricErrorBudgetTests(unittest.TestCase):
    def test_independent_high_precision_curves_stay_inside_each_reported_interval(self):
        maximum=mp.mpf(0)
        with mp.workdps(120):
            for teeth,module,shift in [(12,1.,0.),(18,2.,0.),(24,2.,0.),(73,4.,.2)]:
                design=generate('spur',dict(teeth=teeth,module=module,profile_shift=shift))
                result=audit(design,details=True)
                for row in result['source_profile']['curves']:
                    curve=row['curve']
                    for interval in row['intervals']:
                        a=mp.mpf(interval['start']);b=mp.mpf(interval['end']);p=oracle(curve,a);q=oracle(curve,b)
                        for fraction in ('0.11','0.29','0.53','0.79','0.93'):
                            value=distance(oracle(curve,a+(b-a)*mp.mpf(fraction)),p,q)
                            self.assertLessEqual(value,mp.mpf(interval['chord_bound_mm'])+mp.mpf('1e-10'))
                            maximum=max(maximum,value)
                self.assertLess(result['components']['transverse_profile_mm'],.1)
        # A zero extrusion residual must not hide the actual profile deviation.
        self.assertGreater(maximum,mp.mpf('.001'))

    def test_fine_does_not_claim_a_complete_five_micrometre_tooth(self):
        d=with_quality(generate('spur'),{'export_mm':.005});r=report(d,'export')['geometric_error_budget']
        self.assertEqual(r['components']['sweep_interpolation_mm'],0.)
        self.assertGreater(r['components']['transverse_profile_mm'],0.)
        self.assertEqual(r['status'],'bounded_complete_surface')
        self.assertGreater(r['total_error_bound_mm'],.005);self.assertTrue(r['unquantified'])
        self.assertGreater(r['conditional_stl_boundary_bound_mm'],r['components']['transverse_profile_mm'])

    def test_large_translation_float32_error_and_tiny_frames_are_explicit(self):
        d=generate('spur');p=d.parts[0]
        moved=replace(d,parts=[replace(p,center=(1e8+.125,-1e8+.25),z=.1)])
        r=audit(moved)
        self.assertGreater(r['components']['binary32_coordinate_quantization_mm'],.1)
        self.assertGreater(r['components']['placement_roundoff_mm'],0.)
        tiny=replace(d,parts=[replace(p,frame=((0.,0.,0.),(1e-200,0.,0.),(0.,1e-200,0.),(0.,0.,1.)))])
        t=audit(tiny)
        self.assertGreater(t['components']['placement_error_scale'],0.)
        self.assertGreater(t['components']['binary32_coordinate_quantization_mm'],0.)

    def test_modified_contours_bore_provenance_and_singular_frames_are_not_certified(self):
        d=generate('spur');d.parts[0].outer[0]=(999.,999.)
        with self.assertRaises(UnsupportedBudget):audit(d)
        self.assertEqual(available_report(d,'export')['status'],'not_evaluated')
        d=generate('spur');d.parts[0].holes[0].radius+=.1
        with self.assertRaises(UnsupportedBudget):audit(d)
        d=generate('spur');d.parts[0].frame=((0.,0.,0.),(0.,0.,0.),(0.,1.,0.),(0.,0.,1.))
        with self.assertRaises(UnsupportedBudget):audit(d)
        with self.assertRaises(UnsupportedBudget):audit(generate('planetary'))

    def test_unachievable_audit_resolution_is_refused(self):
        with self.assertRaisesRegex(ValueError,'budget|resolution'):
            call('spur_profile_error',dict(z=24,mt=2,pressure=20,budget_refinement_mm=1e-300))

    def test_real_wasm_runs_the_same_profile_audit(self):
        root=Path(__file__).resolve().parents[1]
        request=dict(operation='spur_profile_error',parameters=dict(z=24,mt=2,pressure=20))
        native=call(request['operation'],request['parameters'])
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'input.json';path.write_text(json.dumps([request]))
            node=os.environ.get('RATIOLAB_NODE') or shutil.which('node')
            self.assertTrue(node,'Node.js is required for actual profile-audit Wasm coverage')
            child=subprocess.run([node,str(root/'tests/rust_wasm_protocol.mjs'),str(root),str(path)],check=True,capture_output=True,text=True,timeout=60)
        wasm=json.loads(child.stdout)[0];self.assertTrue(wasm['ok'])
        self.assertEqual(native['audit_cells'],wasm['result']['audit_cells'])
        self.assertAlmostEqual(native['profile_bound_mm'],wasm['result']['profile_bound_mm'],places=10)
