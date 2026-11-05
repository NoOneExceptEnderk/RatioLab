# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Solid eccentric blanks, explicit bored-cam choice and CAD export parity."""
import json
from math import pi
from pathlib import Path
import sys
import unittest

from geometry import circle_info, defaults, generate
from kinematics import options
from solid_geometry import signature, step


class EccentricConnectionTests(unittest.TestCase):
    def test_integral_blank_is_one_closed_solid_without_bore_or_duplicate_cams(self):
        for variant in ('single', 'dual'):
            with self.subTest(variant=variant):
                d = generate('cycloidal', dict(variant=variant))
                self.assertEqual(defaults('cycloidal')['eccentric_design'], 'integral')
                shaft = next(p for p in d.parts if p.name == 'Shaft_input')
                self.assertEqual(shaft.role, 'gear')
                self.assertFalse(any(p.name.startswith('Eccentric_') for p in d.parts))
                self.assertTrue(all(not s['holes'] for s in shaft.stations))
                shape = signature(shaft)
                count = 1 if variant == 'single' else 2
                r = .72*d.values['bore']/2
                rin = d.values['input_shaft']/2
                expected = pi*rin**2*(shaft.width-count*d.values['width']) + pi*r**2*count*d.values['width']
                self.assertAlmostEqual(shape['volume_mm3']/expected, 1, delta=.0002)
                self.assertEqual(step(shaft, shaft.name).count('FACETED_BREP('), 1)
                self.assertEqual(d.analysis['eccentric_connection']['cam_count'], count)

    def test_disc_profiles_seats_and_rates_match_explicit_bored_construction(self):
        for variant in ('single', 'dual'):
            for scheme in options('cycloidal'):
                with self.subTest(variant=variant, scheme=scheme):
                    args = dict(variant=variant, io_scheme=scheme)
                    integral = generate('cycloidal', args)
                    bored = generate('cycloidal', dict(args, eccentric_design='standard'))
                    discs = lambda d: [p for p in d.parts if p.name.startswith('Disc_cycloidal_')]
                    self.assertEqual(discs(integral), discs(bored))
                    self.assertEqual(integral.analysis['kinematics'], bored.analysis['kinematics'])
                    shaft = next(p for p in integral.parts if p.name == integral.analysis['eccentric_connection']['part'])
                    self.assertEqual(shaft.port['member'], 'eccentric')
                    signature(shaft)
                    for cam in (p for p in bored.parts if p.name in ('Eccentric_1', 'Eccentric_2')):
                        self.assertEqual(len(cam.holes), 1)
                        x,y,r = circle_info(cam.holes[0])
                        self.assertAlmostEqual(x+cam.center[0], 0)
                        self.assertAlmostEqual(y+cam.center[1], 0)
                        for z in (cam.z, cam.z+cam.width):
                            matches = [s for s in shaft.stations
                                       if abs(s['z']+shaft.z-z)<1e-8
                                       and all(abs(a-b)<1e-8 for a,b in
                                               zip(circle_info(s['outer'])[:2], cam.center))]
                            self.assertTrue(matches)
                            self.assertAlmostEqual(circle_info(matches[0]['outer'])[2], circle_info(cam.outer)[2])
                    self.assertTrue(any('circular bore alone is not a fixing' in x for x in bored.requirements))
                    names = {p.name for p in integral.parts}
                    for interface in integral.analysis.get('mount_interfaces', []):
                        self.assertIn(interface['anchor'], names)

    def test_catalog_journal_and_saved_construction_are_preserved(self):
        for construction in ('integral', 'standard'):
            for mode in ('manual', 'gear', 'shaft'):
                with self.subTest(construction=construction, mode=mode):
                    d = generate('cycloidal', dict(variant='dual', eccentric_design=construction,
                                                  bearing_mode=mode))
                    again = generate('cycloidal', json.loads(json.dumps(d.values)))
                    self.assertEqual(d.values, again.values)
                    self.assertEqual(d.parts, again.parts)
                    if construction == 'integral':
                        shaft = next(p for p in d.parts if p.name == 'Shaft_input')
                        signature(shaft)
                        if mode == 'gear':
                            from catalog import selected
                            expected = (selected(d.values).d+d.values['shaft_allowance'])/2
                            self.assertTrue(any(abs(circle_info(s['outer'])[2]-expected)<1e-8 for s in shaft.stations))

    def test_browser_schema_exposes_solid_default_and_bored_option(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'webapp'))
        import engine_bridge as web
        schema = web.schema('cycloidal')
        field = next(f for f in schema['options'] if f['key'] == 'eccentric_design')
        self.assertEqual(field['default'], 'integral')
        self.assertIn('standard', json.dumps(field))
        engine = web.Engine()
        for construction in ('integral', 'standard'):
            result = engine.call('generate', dict(family='cycloidal', parameters=dict(eccentric_design=construction)))
            self.assertEqual(result['values']['eccentric_design'], construction)


if __name__ == '__main__':
    unittest.main()
