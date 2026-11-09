# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Independent involute/contact, full-cycle and source-boundary regressions."""
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from cylindrical_validation import audit_design, audit_pair
from engineering import mesh
from geometry import generate
from internal_mesh import plan_planetary_internal_pair
from rust_geometry import call

ROOT = Path(__file__).resolve().parents[1]


def rotate(p, a):
    return (p[0]*math.cos(a)-p[1]*math.sin(a), p[0]*math.sin(a)+p[1]*math.cos(a))


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


class ContactTests(unittest.TestCase):
    def test_working_backlash_from_actual_tooth_arcs_in_both_mesh_types(self):
        # Independently transport each member's reference tooth arc to its
        # working circle, then subtract both arcs from one working pitch.
        for internal in (False, True):
            for beta in (0, 25, -25):
                for extra in (0, .025, -.025):
                    q = mesh(30, 90, 2, beta=beta, center_extra=extra,
                             backlash=.2, internal=internal)
                    an = math.radians(20); cb = math.cos(math.radians(beta))
                    mt = 2/cb; at = math.atan(math.tan(an)/cb)
                    a0 = mt/2*(90-30 if internal else 90+30)
                    a = a0+extra; aw = math.acos(a0*math.cos(at)/a)
                    inv = lambda x: math.tan(x)-x
                    arcs = []
                    for z, ring in ((30, False), (90, internal)):
                        rp = mt*z/2; rw = rp*a/a0
                        half = math.pi/(2*z)-.2/(4*rp)
                        theta = half+(-1 if ring else 1)*(inv(at)-inv(aw))
                        arcs.append(2*rw*theta)
                    expected = math.pi*mt*a/a0-sum(arcs)
                    self.assertAlmostEqual(q['working_pair_backlash_mm'], expected, delta=8e-14)
                    self.assertAlmostEqual(q['extra_backlash_mm'], expected-.2*a/a0, delta=8e-14)
                    if extra > 0:
                        self.assertLess(q['extra_backlash_mm'], 0) if internal else self.assertGreater(q['extra_backlash_mm'], 0)
        with self.assertRaisesRegex(ValueError, 'Negative working backlash'):
            mesh(30, 90, 2, internal=True, center_extra=1, backlash=.15)
        with self.assertRaisesRegex(ValueError, 'zero profile shift'):
            mesh(30, 90, 2, internal=True, x=.1)

    def test_actual_source_flanks_share_points_normals_and_velocity(self):
        # Evaluate the pre-existing source curve API, not fitted CAD cubics.
        # Check the law of gearing along the ENTIRE available contact interval.
        cases = [(False, 24, 72, 0, 0, 0), (False, 24, 72, 25, .1, .15),
                 (False, 24, 72, -25, -.1, .15), (True, 30, 90, 0, 0, 0),
                 (True, 30, 90, 25, 0, 0), (True, 30, 90, -25, 0, 0)]
        for internal, z1, z2, beta, shift, extra in cases:
            q = audit_pair(z1, z2, 2, internal=internal, helix=beta,
                           profile_shift=shift, center_extra=extra, budget=0)
            inv = q['involute']; m = q['mesh']; aw = math.radians(m['working_pressure_deg'])
            rb1, rb2 = inv['base_radii_mm']; offset1, offset2 = inv['flank_offsets_rad']
            low, high = inv['usable_roll1_interval_mm']; span = m['center_distance_mm']*math.sin(aw)
            n = (math.sin(aw), math.cos(aw)); speed2 = (1 if internal else -1)*z1/z2
            sources = []
            for second, z in ((False, z1), (True, z2)):
                g = m['gear2' if second else 'gear1']
                meta = call('internal_half' if second and internal else 'external_half',
                    dict(z=z, mt=g['mt'], depth=2, pressure=g['alpha_t'],
                         normal_pressure=20, shift=g['x'], backlash=.15, endpoints=True))['metadata']
                sources.append(next(s for s in meta['sampling_curves'] if s['kind'] == 'involute_flank'))
            for i in range(33):
                u = low+(high-low)*i/32; v = u+span if internal else span-u
                t1, t2 = u/rb1, v/rb2
                phi1 = t1-aw-offset1
                phi2 = t2-aw+offset2 if internal else t2+math.pi-aw-offset2
                local = []
                for s, rb, t in zip(sources, (rb1, rb2), (t1, t2)):
                    local.append(call('curve_point', dict(curve=s, t=rb*math.hypot(1, t))))
                if internal:
                    local[1][1] *= -1
                v1 = rotate(local[0], phi1); v2 = rotate(local[1], phi2)
                a = m['center_distance_mm']
                p1 = (v1[0]+(a if internal else 0), v1[1])
                p2 = (v2[0]+(0 if internal else a), v2[1])
                self.assertLess(math.dist(p1, p2), 3e-12)
                for member, (source, base, roll, phase) in enumerate(zip(sources, (rb1, rb2), (t1, t2), (phi1, phi2))):
                    radius = base*math.hypot(1, roll); h = 1e-6
                    minus = call('curve_point', dict(curve=source, t=radius-h))
                    plus = call('curve_point', dict(curve=source, t=radius+h))
                    tangent = (plus[0]-minus[0], plus[1]-minus[1])
                    if internal and member == 1: tangent = (tangent[0], -tangent[1])
                    tangent = rotate(tangent, phase)
                    self.assertAlmostEqual(dot(tangent, n)/math.hypot(*tangent), 0, delta=1e-7)
                # Equal normal velocities; sliding along the common tangent
                # is permitted and must not be mistaken for interference.
                relative = (-v1[1]+speed2*v2[1], v1[0]-speed2*v2[0])
                self.assertAlmostEqual(dot(relative, n), 0, delta=2e-12)
                pitch_point = inv['working_pitch_radii_mm'][1 if internal else 0]
                line_error = (p1[0]-pitch_point)*n[1]-p1[1]*n[0]
                self.assertAlmostEqual(line_error, 0, delta=2e-12)
                neutral = q['phase']['neutral_phase2_rad']
                phase_error = phi2-speed2*phi1-neutral
                period = 2*math.pi/z2
                phase_error = (phase_error+period/2)%period-period/2
                expected = (-1 if internal else 1)*q['phase']['half_backlash_angle_gear2_rad']
                self.assertAlmostEqual(phase_error, expected, delta=2e-14)
                # Reflection verifies the other working flanks and reverse
                # operation with exactly the same conjugate geometry.
                self.assertLess(math.dist((p1[0], -p1[1]), (p2[0], -p2[1])), 3e-12)

    def test_full_cycle_coverage_with_axial_sweep_and_double_half_width(self):
        for internal in (False, True):
            for beta in (0, 30, -30):
                for double in (False, True):
                    q = audit_pair(30, 90, 2, internal=internal, helix=beta,
                        width=20, double_helix=double, gap=2 if double else 0, budget=0)
                    low, high = q['involute']['usable_roll1_interval_mm']
                    rb = q['involute']['base_radii_mm'][0]; pitch = q['involute']['base_pitch_mm']
                    rp = q['mesh']['gear1']['pitch_radius']; active = q['coverage']['active_facewidth_mm']
                    sweep = rb*active*math.tan(math.radians(beta))/rp
                    self.assertAlmostEqual((high-low+abs(sweep))/pitch,
                                           q['coverage']['usable_total'], delta=3e-14)
                    for i in range(401):
                        progress = pitch*i/400
                        first = math.ceil((low-progress-max(sweep, 0))/pitch-1e-12)
                        last = math.floor((high-progress-min(sweep, 0))/pitch+1e-12)
                        self.assertLessEqual(first, last)
                    self.assertEqual(active, 9 if double else 20)

    def test_phase_and_helix_negative_controls(self):
        for internal in (False, True):
            neutral = (0 if internal else math.pi)+math.pi/90
            q = audit_pair(30, 90, 2, internal=internal, phase2_rad=neutral+math.pi/90)
            self.assertEqual(q['status'], 'failed')
            self.assertIn('assembly phases lie outside the available backlash band', q['failures'])
            q = audit_pair(30, 90, 2, internal=internal, helix=25,
                           helix2_deg=-25 if internal else 25)
            self.assertEqual(q['status'], 'failed')
            self.assertIn('helical section phases do not preserve the signed mesh ratio', q['failures'])

    def test_root_risk_is_visible_even_when_contact_ratio_exceeds_one(self):
        q = mesh(30, 90, 2, internal=True, backlash=.15)
        self.assertGreater(q['profile_contact_total'], 1)
        self.assertFalse(q['nominal_contact_within_usable_involutes'])
        self.assertTrue(any('Non-involute root contact may interfere' in s for s in q['warnings']))

    def test_trimmed_profile_can_lose_full_cycle_coverage(self):
        q = audit_pair(12, 22, 2, pressure=14.5, center_extra=1)
        self.assertGreater(q['mesh']['contact_total'], 1)
        self.assertLess(q['mesh']['profile_contact_total'], 1)
        self.assertEqual(q['status'], 'failed')
        self.assertGreater(q['coverage']['uncovered_fraction'], 0)

    def test_independent_internal_root_intrusion_counterexample(self):
        # Fixed witness found by an independent source-curve sweep and then
        # reevaluated at 100 digits. No fitted curve or sampled mesh is used.
        z1, z2 = 30, 90
        meta = call('external_half', dict(z=z1, mt=2, depth=2, pressure=20,
                    normal_pressure=20, backlash=.15, endpoints=True))['metadata']
        curve = meta['sampling_curves'][0]; tool = curve['tool']
        t = -.40633446647993
        u = (tool['tip_center_u']+tool['tip_radius']*math.cos(t))/tool['cos_beta']
        v = tool['tip_center_v']+tool['tip_radius']*math.sin(t)
        du = -tool['tip_radius']*math.sin(t)/tool['cos_beta']
        dv = tool['tip_radius']*math.cos(t)
        phi = (u+v*dv/du)/tool['pitch_radius']
        point = rotate((u-tool['pitch_radius']*phi, tool['pitch_radius']+v), curve['rotation']-phi)
        point = rotate((point[0], -point[1]), .031088677301148993+2*math.pi/z1)
        point = (60+point[0], point[1])
        theta = abs(math.atan2(point[1], point[0])-.046102810806936255)
        alpha = math.radians(20); rb = 90*math.cos(alpha)
        half = math.pi/(2*z2)-.15/(4*90)
        target = theta-half+math.tan(alpha)-alpha
        low, high = 0., 2.
        for _ in range(70):
            mid = (low+high)/2
            if mid-math.atan(mid) < target: low = mid
            else: high = mid
        radius = rb*math.hypot(1, (low+high)/2)
        self.assertGreaterEqual(radius, 88)
        self.assertAlmostEqual(math.hypot(*point)-radius, .008529257148276163, delta=5e-13)


class ContinuousClearanceTests(unittest.TestCase):
    def test_external_continuous_clearance_and_both_operating_roots(self):
        q = audit_pair(24, 72, 2)
        self.assertEqual(q['status'], 'passed_with_limits')
        self.assertTrue(q['covered_checks_passed'])
        for check in [q['neutral_clearance'], *q['operating_root_clearance']]:
            self.assertEqual(check['status'], 'clear')
            self.assertGreater(check['certified_separation_lower_bound_mm'], check['numeric_guard_mm'])
            self.assertGreater(check['evaluated_intervals'], 1)
        self.assertEqual({(r['root_member'], r['operating_side']) for r in q['operating_root_clearance']},
                         {(1, -1), (1, 1), (2, -1), (2, 1)})
        self.assertEqual(len(q['unqualified']), 4)
        self.assertTrue(all(x <= .0001 for x in q['boundaries']['enclosure_mm']))

    def test_internal_root_interference_and_paired_tip_correction(self):
        for zp, zr in ((22, 66), (24, 72), (30, 90)):
            before = audit_pair(zp, zr, 2, internal=True)
            self.assertFalse(before['covered_checks_passed'])
            self.assertIn(before['status'], ('failed', 'unresolved'))
            self.assertTrue(any(c['status'] != 'clear' and c['root_member'] == 1
                                for c in before['operating_root_clearance']))
            plan = plan_planetary_internal_pair(zp, zr, 2)
            after = audit_pair(zp, zr, 2, internal=True, internal_plan=plan)
            self.assertEqual(after['status'], 'passed_with_limits')
            self.assertTrue(after['mesh']['nominal_contact_within_usable_involutes'])
            self.assertLess(after['mesh']['contact_transverse'], before['mesh']['contact_transverse'])
            self.assertGreater(after['mesh']['contact_transverse'], 1)
            self.assertIn('not a pinion-cutter envelope', after['internal_root'])

    def test_budget_zero_backlash_and_tiny_requests_never_falsely_clear(self):
        for kw in (dict(budget=0), dict(max_depth=0), dict(backlash=0)):
            q = audit_pair(24, 72, 2, **kw)
            self.assertEqual(q['status'], 'unresolved')
            self.assertFalse(q['covered_checks_passed'])
        for kw in (dict(profile_enclosure_mm=0), dict(profile_enclosure_mm=1e-20),
                   dict(budget=16385), dict(max_depth=21), dict(phase1_rad=1e7)):
            with self.assertRaises(ValueError):
                audit_pair(24, 72, 2, **kw)

    def test_cancellation_does_not_contaminate_the_next_call(self):
        class Stopped(Exception): pass
        count = 0
        def stop():
            nonlocal count
            count += 1
            if count > 12: raise Stopped('mechanical deadline')
        with self.assertRaisesRegex(Stopped, 'mechanical deadline'):
            audit_pair(24, 72, 2, check=stop)
        self.assertTrue(audit_pair(24, 72, 2)['covered_checks_passed'])

    def test_actual_design_edits_and_stale_analysis_are_not_qualified(self):
        d = generate('parallel', dict(pinion=24, wheel=72))
        d.analysis['meshes'][0]['contact_total'] = -100
        q = audit_design(d)
        self.assertTrue(q['covered_checks_passed'])
        self.assertTrue(q['source']['unchanged_nominal_pair'])
        d.parts[0].outer[0] = (1000, 1000)
        with self.assertRaisesRegex(ValueError, 'unchanged nominal'):
            audit_design(d)
        with self.assertRaisesRegex(ValueError, 'fixed-axis'):
            audit_design(generate('planetary'))

    def test_application_variants_and_quality_do_not_change_nominal_audit(self):
        for family in ('parallel', 'internal'):
            for variant in ('spur', 'helical', 'double'):
                d = generate(family, dict(pinion=24, wheel=72, variant=variant, gap=0),
                             quality=dict(preview_mm=.1, export_mm=.01))
                q = audit_design(d, budget=0)
                self.assertEqual(q['phase']['status'], 'compatible')
                self.assertTrue(q['source']['unchanged_nominal_pair'])
                self.assertEqual(q['coverage']['double_helix'], variant == 'double')
        d = generate('parallel', dict(pinion=24, wheel=72))
        a = audit_design(d)
        d.quality = dict(preview_mm=.2, export_mm=.000001)
        b = audit_design(d)
        self.assertEqual(a, b)

    def test_cli_preserves_reports_and_reports_nonqualification_as_failure(self):
        script = ROOT/'scripts/validate-cylindrical-mesh.py'
        with TemporaryDirectory() as folder:
            output = Path(folder)/'audit.json'
            run = subprocess.run([sys.executable, str(script), str(output), '--family', 'internal'],
                                 capture_output=True, text=True, timeout=30)
            self.assertEqual(run.returncode, 0, run.stderr)
            report = json.loads(output.read_text())
            self.assertTrue(report['covered_checks_passed'])
            unresolved=Path(folder)/'unresolved.json'
            incomplete=subprocess.run([sys.executable,str(script),str(unresolved),'--family','internal','--budget','0'],
                                      capture_output=True,text=True,timeout=30)
            self.assertEqual(incomplete.returncode,2,incomplete.stderr)
            self.assertFalse(json.loads(unresolved.read_text())['covered_checks_passed'])
            previous = output.read_bytes()
            repeat = subprocess.run([sys.executable, str(script), str(output), '--family', 'parallel'],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(repeat.returncode, 2)
            self.assertIn('Refusing to replace', repeat.stderr)
            self.assertEqual(output.read_bytes(), previous)

    def test_shared_wasm_audit_and_signed_backlash(self):
        node = os.environ.get('RATIOLAB_NODE') or shutil.which('node')
        if not node:
            self.skipTest('Node.js required for actual Wasm execution')
        requests = [dict(operation='cylindrical_pair_audit', parameters=p) for p in (
            dict(z1=24, z2=72, m=2), dict(z1=30, z2=90, m=2, internal=True),
            dict(z1=30, z2=90, m=2, beta=25, helix2_deg=25),
            dict(z1=30, z2=90, m=2, internal=True, center_extra=.025, backlash=.2))]
        native = [call(q['operation'], q['parameters']) for q in requests]
        with TemporaryDirectory() as folder:
            inputs = Path(folder)/'requests.json'; inputs.write_text(json.dumps(requests))
            run = subprocess.run([node, str(ROOT/'tests/rust_wasm_protocol.mjs'), str(ROOT), str(inputs)],
                capture_output=True, text=True, check=True, timeout=60)
            wasm = json.loads(run.stdout)
        for a, b in zip(native, wasm):
            self.assertTrue(b['ok'], b)
            b = b['result']
            self.assertEqual(a['status'], b['status'])
            self.assertEqual(a['failures'], b['failures'])
            self.assertEqual(a['covered_checks_passed'], b['covered_checks_passed'])
            self.assertAlmostEqual(a['mesh']['working_pair_backlash_mm'], b['mesh']['working_pair_backlash_mm'], delta=1e-12)
            if a['neutral_clearance']:
                self.assertEqual(a['neutral_clearance']['status'], b['neutral_clearance']['status'])
                self.assertEqual([x['status'] for x in a['operating_root_clearance']],
                                 [x['status'] for x in b['operating_root_clearance']])


if __name__ == '__main__':
    unittest.main()
