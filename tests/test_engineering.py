# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Controprove numeriche, cinematiche e di integrazione del calcolo nominale."""
import json, math, tempfile, unittest
from pathlib import Path
from geometry import generate, VARIANTS, profile_sections, section_holes, transformed, circle_info, cycloid
from engineering import gear_dimensions, mesh, force_components, report_text
from solid_geometry import signature
from bom import export, build
from test_geometry import inside, distance

class EngineeringTests(unittest.TestCase):

    def test_industrial_helical_example_and_real_tooth_heights(self):
        d = generate('helical', {'module': 4, 'teeth': 30, 'helix': 15})
        p = d.parts[0]
        self.assertAlmostEqual(2 * d.analysis['gear']['pitch_radius'], 124.2331416492, places=8)
        radii = [math.hypot(x, y) for x, y in p.outer]
        self.assertAlmostEqual(max(radii), 66.1165708246, places=7)
        self.assertAlmostEqual(min(radii), 57.1165708246, places=7)
        self.assertGreater(signature(p)['volume_mm3'], 0)

    def test_contact_ratio_and_published_force_example(self):
        self.assertAlmostEqual(mesh(20, 40, 2)['contact_transverse'], 1.63518596357, places=9)
        f = force_components(100, 40, 21.515)
        self.assertEqual(f['tangential_N'], 5000)
        self.assertAlmostEqual(f['radial_N'], 1971.1, delta=0.1)
        self.assertEqual(f['axial_N'], 0)

    def test_shift_changes_thickness_and_geometry_without_changing_reference_diameter(self):
        plain = generate('spur')
        shifted = generate('spur', {'profile_shift': 0.3, 'addendum': 1.1, 'dedendum': 1.3})
        g = shifted.analysis['gear']
        self.assertEqual(g['pitch_radius'], plain.analysis['gear']['pitch_radius'])
        self.assertAlmostEqual(g['normal_thickness'], 3.5783569347, places=8)
        self.assertAlmostEqual(max((math.hypot(*p) for p in shifted.parts[0].outer)), 26.8, places=7)
        with self.assertRaises(ValueError):
            generate('parallel', {'pinion': 12})
        self.assertGreater(generate('parallel', {'pinion': 12, 'profile_shift': 0.3}).analysis['meshes'][0]['contact_total'], 1)

    def test_all_new_variants_at_heights_and_during_motion(self):
        for family in ('parallel', 'internal'):
            for variant in VARIANTS[family]:
                with self.subTest(f=family, v=variant):
                    d = generate(family, {'variant': variant})
                    gears = [p for p in d.parts if p.role == 'gear']
                    for k, (a, b) in enumerate(zip(gears[::2], gears[1::2])):
                        z1 = d.values['pinion' if k == 0 else 'pinion2']
                        z2 = d.values['wheel' if k == 0 else 'wheel2']
                        for height in (0, 0.2, 0.8, 1):
                            aa = a.twist * (min(height, 1 - height) if a.double else height)
                            ab = b.twist * (min(height, 1 - height) if b.double else height)
                            oa = a.outer
                            ob = b.holes[0] if b.internal else b.outer
                            for theta in (0, 0.13, 0.31, 0.57):
                                qa = transformed(oa, a.center, math.radians(aa) + theta)
                                qb = transformed(ob, b.center, math.radians(ab) + (1 if b.internal else -1) * theta * z1 / z2)
                                self.assertFalse(any((not inside(q, qb) if b.internal else inside(q, qb) for q in qa)))
                                if not b.internal:
                                    self.assertFalse(any((inside(q, qa) for q in qb)))
                    json.dumps(d.commands(), allow_nan=False)
                    for p in gears:
                        if p.double or p.twist:
                            self.assertEqual(signature(p)['volume_mm3'] > 0, True)

    def test_internal_interference_and_external_center_distance(self):
        with self.assertRaises(ValueError):
            generate('internal', {'pinion': 40, 'wheel': 48})
        with self.assertRaises(ValueError):
            generate('internal', {'pinion': 18, 'wheel': 54})
        q = generate('parallel', {'center_extra': 0.3}).analysis['meshes'][0]
        self.assertGreater(q['extra_backlash_mm'], 0)
        self.assertGreater(q['working_pressure_deg'], 20)
        with self.assertRaises(ValueError):
            generate('parallel', {'center_extra': 5})

    def test_double_overlap_and_helical_axial_load(self):
        v = {'variant': 'double', 'width': 20, 'gap': 0, 'input_torque': 4}
        d = generate('parallel', v)
        q = d.analysis['meshes'][0]
        self.assertAlmostEqual(q['contact_overlap'], 10 * math.sin(math.radians(20)) / (math.pi * 2))
        self.assertGreater(q['forces']['axial_N'], 0)
        left = generate('parallel', dict(v, helix=-20)).analysis['meshes'][0]
        self.assertAlmostEqual(q['forces']['axial_N'], -left['forces']['axial_N'])

    def test_cycloidal_independent_clearances_and_adaptive_sampling(self):
        a = generate('cycloidal', {'variant': 'dual', 'output_clearance': 0.3, 'clearance': 0.02, 'disc_gap': 1})
        b = generate('cycloidal', {'variant': 'dual', 'output_clearance': 0.1, 'clearance': 0.02, 'disc_gap': 0.2})
        pa, pb = (a.parts[0], b.parts[0])
        self.assertEqual(pa.outer, pb.outer)
        self.assertAlmostEqual(circle_info(pa.holes[1])[2] - circle_info(pb.holes[1])[2], 0.2)
        self.assertAlmostEqual(a.parts[3].z - b.parts[3].z, 0.8)
        coarse = cycloid(16, 40, 1.2, 3, 0.1, tolerance=0.03)
        fine = cycloid(16, 40, 1.2, 3, 0.1, tolerance=0.002)
        self.assertGreater(len(fine), len(coarse))
        dense = cycloid(16, 40, 1.2, 3, 0.1, samples=3072)
        self.assertLess(max((distance(p, fine) for p in dense)), 0.0021)
        legacy = generate('cycloidal', {'clearance': 0.3, 'assembly_clearance': 0.4, 'variant': 'dual'})
        self.assertEqual(legacy.values['output_clearance'], 0.3)
        self.assertEqual(legacy.values['disc_gap'], 0.4)

    def test_worm_axial_normal_conversion_and_hand(self):
        d = generate('worm')
        r = d.analysis
        self.assertAlmostEqual(r['lead_mm'], 2 * math.pi)
        self.assertAlmostEqual(r['normal_module_mm'], 2 / math.sqrt(1 + 0.1 ** 2))
        wheel = next((p for p in d.parts if p.name == 'Wheel_generated'))
        expected_tip = 30 + 2
        self.assertAlmostEqual(max((math.hypot(*q) for q in wheel.outer)), expected_tip, places=7)
        left = generate('worm', {'worm_hand': -1})
        self.assertLess(left.parts[0].twist, 0)
        with self.assertRaises(ValueError):
            generate('worm', {'worm_hand': 0})

    def test_reports_exports_and_planetary_warning(self):
        d = generate('planetary')
        self.assertTrue(any(('Internal involute interference' in n for n in d.notes)))
        self.assertTrue(all(('forces' not in q for q in d.analysis['meshes'])))
        d = generate('parallel')
        with tempfile.TemporaryDirectory() as folder:
            stem = Path(folder) / 'parallel'
            export(d, stem)
            self.assertEqual(json.loads(Path(str(stem) + '.calculations.json').read_text())['signed_ratio'], -3)
            self.assertIn('ASSUMPTIONS AND LIMITATIONS', Path(str(stem) + '.calculations.txt').read_text())
        meta = next((c for c in d.commands() if c['command'] == 'component.metadata.set'))
        self.assertEqual(meta['params']['values']['local.solidcraft.riduttori']['analysis']['signed_ratio'], -3)
        for f in ('parallel', 'internal'):
            for key in ('input_rpm', 'input_torque', 'efficiency'):
                with self.subTest(f=f, k=key), self.assertRaises(ValueError):
                    generate(f, {key: float('nan')})
if __name__ == '__main__':
    unittest.main()
