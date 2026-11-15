# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Independent contact, section geometry, and export checks for opposed bevel traces."""
from collections import Counter
from math import acos, atan2, cos, exp, log, pi, radians, sin, tan, tau
from pathlib import Path
import json
import struct
import sys
from tempfile import TemporaryDirectory
import unittest

import cad_export
import profile_export
import stl_export
from bevel_pair import dimensions
from collision_geometry import Surface, cross, dot, relation
from geometry import generate, get_specs, validate
from motion import build_plan, rotation
from solid_geometry import faces, signature
from test_bevel_geometry import frame_a, normal, rx, rz


def trace(r, center, e):
    u = abs(log(r / center))
    return (e + u*u/e) / 2 if u < e else u


def check_contact(a, b, distance, direction, backlash):
    """Find a contact pose from the spherical action plane, then measure the mate."""
    pa = radians(20)
    action = (-sin(a.delta) * sin(pa), -cos(pa), cos(a.delta) * sin(pa))
    pitch = (cos(a.delta), 0., sin(a.delta))
    results = []
    for s in (-.025, -.01, 0., .01, .025):
        x, y, z = (p*cos(s) + q*sin(s) for p, q in zip(pitch, action))
        y *= direction
        polar_a, polar_b = acos(x), acos(z)
        az_a = atan2(z, y)
        phase = pi/2 - pi/a.teeth
        side = direction
        turn = az_a - phase - a.trace(distance) - side*a.half_angle(polar_a)
        local_a = a.point(polar_a, distance, side, phase)
        world = rx(frame_a(local_a), turn)
        mate = rz(world, a.teeth/b.teeth*turn)
        az_b = atan2(mate[1], mate[0]) - b.trace(distance)
        az_b = (az_b + pi/b.teeth) % (tau/b.teeth) - pi/b.teeth
        side_b = 1 if az_b >= 0 else -1
        gap = (abs(az_b)-b.half_angle(polar_b))*distance*sin(b.delta)
        expected_gap = backlash*distance/(2*a.outer_distance)
        # Symmetric thinning gives half the total lost motion on each side.
        assert abs(gap-expected_gap) < 1e-9, (direction, s, gap, expected_gap)
        if backlash == 0:
            na = rx(frame_a(normal(a, polar_a, distance, side, phase)), turn)
            nb = normal(b, polar_b, distance, side_b, atan2(mate[1], mate[0])
                        - b.trace(distance)-side_b*b.half_angle(polar_b))
            common = abs(dot(rz(na, a.teeth/b.teeth*turn), nb))
            residual = abs(dot(na, cross((1., 0., a.teeth/b.teeth), world)))
            results.append((abs(common-1), residual))
    return results


class BevelOpposedTraceTests(unittest.TestCase):
    def test_trace_phase_normals_and_backlash_at_the_same_actual_radius(self):
        for hand in (-1, 1):
            for backlash in (0, .15):
                a, b, _ = dimensions(validate('bevel', dict(
                    variant='herringbone', spiral_hand=hand, backlash=backlash)))
                center = a.opposed_trace['reversal_distance']
                e = a.opposed_trace['log_half_width']
                radii = [center*exp(u) for u in (-2*e, -e, -.5*e, 0, .5*e, e, 2*e)]
                for r in radii:
                    expected = hand*tan(radians(35))/sin(a.delta)*(
                        trace(r, center, e)-trace(a.outer_distance, center, e))
                    self.assertAlmostEqual(a.trace(r), expected, places=14)
                    self.assertAlmostEqual(a.teeth*a.trace(r)+b.teeth*b.trace(r), 0, places=12)
                    for direction in (-1, 1):
                        for alignment, residual in check_contact(a, b, r, direction, backlash):
                            self.assertLess(alignment, 1e-10)
                            self.assertLess(residual, 4e-7)
                if e:
                    step = 1e-6
                    self.assertAlmostEqual((a.trace(center+step)-a.trace(center-step))/(2*step),
                                           0, delta=1e-9)
                    for r in (center*exp(-e), center*exp(e)):
                        left = (a.trace(r)-a.trace(r-step))/step
                        right = (a.trace(r+step)-a.trace(r))/step
                        self.assertAlmostEqual(left, right, delta=5e-8)

    def test_zero_angle_matches_straight_bevel(self):
        zero = generate('bevel', dict(variant='herringbone', spiral_angle=0, spiral_hand=-1))
        self.assertEqual([faces(p) for p in zero.parts], [faces(p) for p in generate('bevel').parts])

    def test_herringbone_options_and_retired_variant(self):
        fields = {spec[0] for spec in get_specs('bevel', 'herringbone')}
        self.assertIn('spiral_angle', fields)
        self.assertNotIn('groove_width', fields)
        self.assertNotIn('trace_radius', fields)
        self.assertTrue(generate('bevel', dict(variant='herringbone', spiral_angle=45)).parts)
        for values in (dict(spiral_angle=46), dict(spiral_hand=0)):
            with self.assertRaises(ValueError):
                validate('bevel', dict(variant='herringbone', **values))
        with self.assertRaisesRegex(ValueError, 'variant was removed'):
            generate('bevel', dict(variant='double_spiral', groove_width=6))

    def test_mesh_cycle_and_half_tooth_indexing_negative_control(self):
        d = generate('bevel', dict(variant='herringbone', pinion=21, wheel=41,
                                   spiral_hand=-1, spiral_angle=20))
        plan = build_plan(d)
        self.assertEqual(plan.rates, {0:(1.,), 1:(-21/41,)})
        a, b = (Surface.from_part(p) for p in d.parts)
        try:
            for fraction in (0., .173, .391, .625, .891):
                phase = tau/21*fraction
                ap, bp = a.posed(plan.matrix(0, phase)), b.posed(plan.matrix(1, phase))
                try:
                    result = relation(ap, bp, 1e-6)
                    self.assertEqual(result['kind'], 'Separated', (fraction, result))
                finally:
                    ap.close()
                    bp.close()
            wrong = b.posed(rotation(pi/41))
            try:
                self.assertEqual(relation(a, wrong, 1e-6)['kind'], 'Intersection')
            finally:
                wrong.close()
        finally:
            a.close()
            b.close()

    def test_project_bridge_and_exported_stl_bounds_and_winding(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'webapp'))
        from engine_bridge import Engine, schema
        d = generate('bevel', dict(variant='herringbone', spiral_angle=18, io_scheme='reverse',
                                   input_rpm=-1500))
        self.assertEqual(d.analysis['signed_ratio'], -.5)
        self.assertEqual([p.port['rpm'] for p in d.parts], [3000, -1500])
        values = json.loads(json.dumps(d.values))
        self.assertEqual(generate('bevel', values).parts, d.parts)
        self.assertNotIn('groove_width', values)
        engine = Engine()
        retired = dict(format='solidcraft-riduttori/1', family='bevel',
                       parameters=dict(variant='double_spiral', groove_width=6))
        with self.assertRaisesRegex(ValueError, 'variant was removed'):
            engine.call('import_project', dict(project=retired))
        fields = {f['key'] for f in schema('bevel', values)['fields']}
        self.assertNotIn('groove_width', fields)
        web = engine.call('generate', dict(family='bevel',parameters=values))
        self.assertEqual(web['analysis'], d.analysis)
        with TemporaryDirectory() as folder:
            folder = Path(folder)
            _, info = cad_export.export(d, folder/'cad')
            self.assertEqual(len(info), 2)
            # Exercise the browser policy without producing a 128 MiB fixture.
            fallback = folder/'components-only-step'
            fallback.mkdir()
            part_bytes = sum(p.stat().st_size for p in (folder/'cad'/'step-parts').glob('*.step'))
            bounded = cad_export.write_files(d, fallback, max_step_bytes=part_bytes + 1)
            self.assertEqual(bounded, info)
            self.assertFalse((fallback/'assembly.step').exists())
            self.assertIsNone(json.loads((fallback/'step-info.json').read_text())['assembly_step'])
            for path in (fallback/'step-parts').glob('*.step'):
                self.assertEqual(path.read_bytes(), (folder/'cad'/'step-parts'/path.name).read_bytes())
            _, stl_paths = stl_export.export(d, folder/'stl')
            _, profiles = profile_export.export(d, folder/'profiles')
            self.assertTrue(all(p['profiles'] for p in profiles['components']))
            for p, path in zip(d.parts, stl_paths, strict=True):
                data = path.read_bytes()
                count, = struct.unpack_from('<I', data, 80)
                self.assertEqual(len(data), 84+50*count)
                edges = Counter()
                volume = 0.
                extrema = [[], [], []]
                for row in struct.iter_unpack('<12fH', data[84:]):
                    tri = (row[3:6], row[6:9], row[9:12])
                    volume += dot(tri[0],cross(tri[1],tri[2]))/6
                    for u, v in zip(tri, tri[1:]+tri[:1]):
                        edges[u,v] += 1
                    for axis in range(3):
                        extrema[axis].extend(q[axis] for q in tri)
                self.assertTrue(all(n==1 and edges[v,u]==1 for (u,v),n in edges.items()))
                measured = signature(p)
                self.assertAlmostEqual(volume, measured['volume_mm3'], delta=.02)
                for actual, expected in zip(extrema, zip(measured['min'],measured['max'])):
                    self.assertAlmostEqual(min(actual), expected[0], delta=4e-6)
                    self.assertAlmostEqual(max(actual), expected[1], delta=4e-6)
