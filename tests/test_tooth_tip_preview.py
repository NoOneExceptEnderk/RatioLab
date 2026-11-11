# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Removed head topology and actual member routing, independent area checks."""
from math import hypot, pi, radians, tan, isclose
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

from geometry import generate, gear_part
from rust_geometry import call
from tooth_tips import members
from tooth_tip_preview import component_index


def area(poly):
    return abs(sum(a[0]*b[1]-b[0]*a[1] for a, b in zip(poly, poly[1:]+poly[:1]))/2)


def head(part):
    return call('tooth_tip_preview', dict(source=part.profile_metadata['tip_preview_source'],
                profile=part.profile_metadata.get('tooth_profile', {})))


class ToothTipPreviewTests(unittest.TestCase):
    def test_native_wasm_removed_head_sections_match(self):
        requests = []
        for family, values in [('helical', dict(topping_mm=.2, semitopping_mm=.25)),
                ('internal', dict(ring_semitopping_mm=.25)),
                ('rack', dict(variant='double', rack_topping_mm=.15, rack_semitopping_mm=.2))]:
            design = generate(family, values)
            name = {'internal':'Ring_output', 'rack':'Rack'}.get(family, 'Gear')
            part = next(p for p in design.parts if p.name == name)
            requests.append(dict(operation='tooth_tip_preview', parameters=dict(
                source=part.profile_metadata['tip_preview_source'],
                profile=part.profile_metadata.get('tooth_profile', {}))))
        root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as temporary:
            path = Path(temporary)/'requests.json'
            path.write_text(json.dumps(requests))
            result = subprocess.run([os.environ.get('RATIOLAB_NODE', 'node'),
                str(root/'tests/rust_wasm_protocol.mjs'), str(root), str(path)],
                capture_output=True, text=True, check=True, timeout=60)
        def same(a, b):
            if isinstance(a, dict):
                self.assertEqual(set(a), set(b))
                for key in a: same(a[key], b[key])
            elif isinstance(a, list):
                self.assertEqual(len(a), len(b))
                for x,y in zip(a,b): same(x,y)
            elif isinstance(a, (int, float)):
                self.assertTrue(isclose(a, b, rel_tol=1e-12, abs_tol=1e-8), (a,b))
            else: self.assertEqual(a, b)
        for request, wasm in zip(requests, json.loads(result.stdout)):
            self.assertTrue(wasm['ok'])
            same(call(request['operation'], request['parameters']), wasm['result'])

    def test_preview_rejects_invalid_or_unbounded_construction_sources(self):
        for source in ({}, {'kind':'linear', 'parameters':{'module':-1}},
                {'kind':'linear', 'parameters':{'rack_teeth':1e100}},
                {'kind':'linear', 'parameters':{'rack_teeth':24.5}}):
            with self.assertRaises(ValueError):
                call('tooth_tip_preview', dict(source=source))

    def test_zero_and_modified_heads_use_actual_tip_and_leave_working_flanks(self):
        for internal in (False, True):
            for topping, semi in ((0, 0), (.2, 0), (0, .25), (.15, .2)):
                with self.subTest(internal=internal, topping=topping, semi=semi):
                    part = gear_part('Gear', 66 if internal else 24, 2, 20, .15, 10,
                        internal=internal, topping_mm=topping, semitopping_mm=semi)
                    preview = head(part)
                    profile = part.profile_metadata['tooth_profile']
                    self.assertAlmostEqual(hypot(*preview['target_xy']), profile['tip_radius_mm'])
                    self.assertEqual(len(preview['polygons']), 0 if not topping+semi else 3 if topping else 6)
                    nominal = profile.get('tip_treatment', {}).get('nominal_tip_radius_mm', profile['tip_radius_mm'])
                    join = profile['tip_radius_mm'] + semi if internal else profile['tip_radius_mm']-semi
                    for polygon in preview['polygons']:
                        self.assertGreater(area(polygon), 1e-8)
                        for q in polygon:
                            self.assertGreaterEqual(hypot(*q), min(nominal, join)-1e-7)
                            self.assertLessEqual(hypot(*q), max(nominal, join)+1e-7)
                    d = preview['direction_xy']
                    dot = sum(a*b for a,b in zip(d,preview['target_xy']))
                    if internal:
                        self.assertLess(dot, 0)
                    else:
                        self.assertGreater(dot, 0)

    def test_head_areas_agree_with_independent_whole_profile_area_difference(self):
        for internal in (False, True):
            for t, h in ((.2, 0), (0, .25), (.15, .2)):
                with self.subTest(internal=internal, topping=t, semi=h):
                    part = gear_part('Gear', 66 if internal else 24, 2, 20, .15, 10,
                        internal=internal, topping_mm=t, semitopping_mm=h)
                    args = dict(z=66 if internal else 24, mt=2, depth=2,
                        pressure=20, normal_pressure=20, backlash=.15,
                        internal=internal, topping_mm=t, semitopping_mm=h,
                        semitopping_angle_deg=45, tolerance=1e-6)
                    after = call('involute_profile', args)['points']
                    before = call('involute_profile', dict(args, topping_mm=0, semitopping_mm=0))['points']
                    expected = abs(area(before)-area(after))*3/(66 if internal else 24)
                    observed = sum(map(area, head(part)['polygons']))
                    self.assertAlmostEqual(observed, expected, delta=.0008)

    def test_rack_removed_area_matches_independent_straight_flank_integration(self):
        for t, h in ((.2, 0), (0, .25), (.15, .2)):
            design = generate('rack', dict(rack_topping_mm=t, rack_semitopping_mm=h))
            rack = next(p for p in design.parts if p.name == 'Rack')
            v = design.values
            m = v['module']; alpha = radians(v['pressure']); ramp = radians(v['rack_semitopping_angle_deg'])
            half = pi*m/4-v['backlash']/4
            per_tooth = t*(2*half-(2*m-t)*tan(alpha))+h*h*(tan(ramp)-tan(alpha))
            preview = head(rack)
            self.assertEqual(len(preview['polygons']), 3 if t else 6)
            self.assertAlmostEqual(sum(map(area, preview['polygons'])), 3*per_tooth, delta=1e-7)

    def test_all_supported_member_controls_find_the_real_component(self):
        for family, variant in (('spur', None), ('helical', None), ('double', 'separated'),
                ('parallel', 'three_stage_helical'), ('internal', 'double'),
                ('planetary', 'two_stage_double'), ('wolfrom', 'helical'), ('rack', 'double')):
            design = generate(family, dict(variant=variant) if variant else {})
            for role, _ in members(family, variant):
                field = (role+'_' if role else '')+'topping_mm'
                part = design.parts[component_index(design, field)]
                self.assertIn('tip_preview_source', part.profile_metadata)
                preview = head(part)
                self.assertEqual(len(preview['polygons']), 0)
                target = preview['target_xy']
                contour = part.holes[0] if part.internal else part.outer
                def distance(a, b):
                    dx,dy = b[0]-a[0],b[1]-a[1]
                    u = max(0.,min(1.,((target[0]-a[0])*dx+(target[1]-a[1])*dy)/(dx*dx+dy*dy)))
                    return hypot(target[0]-a[0]-u*dx,target[1]-a[1]-u*dy)
                # Placement phase is checked against the actual generated
                # boundary, including planet rims and the rack pinion phase.
                self.assertLess(min(distance(a,b) for a,b in zip(contour,contour[1:]+contour[:1])), .02)


if __name__ == '__main__':
    unittest.main()
