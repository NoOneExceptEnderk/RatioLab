# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Manufacturer benchmarks and independent geometric gauge contact checks."""
import json
import math
from pathlib import Path
import tempfile
import unittest
from copy import deepcopy
from geometry import generate
from tooth_profiles import external_half, internal_half
from gear_measurement import over_gauges, default_gauge, measurement_query, export_measurement
from engineering import report_text
from bom import export


def profile(z=20, m=1, internal=False, backlash=0):
    sample = lambda f, a, b: [f(a), f(b)]
    args = (z,m,20,backlash,m,1,1.25,sample) if internal else (z,m,20,backlash,m,0,20,1,1.25,sample)
    return (internal_half if internal else external_half)(*args)[1]['measurement_geometry']


class GaugeTests(unittest.TestCase):
    def test_khk_tables_5_14_and_5_18_and_scaling(self):
        for internal, z, expected in ((False,20,22.29409294937739),(True,40,37.595115183247216)):
            g = profile(z=z,internal=internal)
            result = over_gauges(g,1.7)
            self.assertEqual(result['status'],'ok')
            self.assertAlmostEqual(result['dimension_mm'],expected)
            roller = over_gauges(g,1.7,'roller')
            self.assertEqual(roller['dimension_mm'],result['dimension_mm'])
            self.assertIn('axial line',roller['contact_type'])
            scaled = over_gauges(profile(z=z,m=3,internal=internal),5.1)
            self.assertAlmostEqual(scaled['dimension_mm'],expected*3)
            default = default_gauge(g)
            self.assertEqual(default['status'],'ok')
            self.assertAlmostEqual(default['contact_radius_mm'],g['reference_radius_mm'])

    def test_even_odd_independent_circle_tangency_and_plane_dimension(self):
        for internal,z in ((False,20),(False,21),(True,40),(True,41)):
            for backlash in (0,.15):
                g = profile(z=z,internal=internal,backlash=backlash)
                q = over_gauges(g,1.7)
                self.assertEqual(q['status'],'ok')
                rb,half,at = g['base_radius_mm'],g['reference_half_angle_rad'],g['transverse_pressure_angle_rad']
                # Independent flank in the tooth-space frame. Gauge centre is
                # on the x axis; verify distance, normal and local nonpenetration.
                def flank(r):
                    a=math.acos(rb/r)
                    inv=math.tan(a)-a
                    tooth=half+(inv-(math.tan(at)-at) if internal else math.tan(at)-at-inv)
                    angle=math.pi/z-tooth
                    return r*math.cos(angle),r*math.sin(angle)
                r=q['contact_radius_mm'];centre=(q['centre_circle_diameter_mm']/2,0)
                p=flank(r);radius=.85
                self.assertAlmostEqual(math.dist(p,centre),radius,places=10)
                delta=r*1e-6
                before,after=flank(r-delta),flank(r+delta)
                tangent=tuple((b-a)/(2*delta) for a,b in zip(before,after))
                self.assertAlmostEqual(sum((v-c)*t for v,c,t in zip(p,centre,tangent)),0,places=8)
                for offset in (-.001,.001):
                    self.assertGreater(math.dist(flank(r+offset),centre),radius)
                # Direct two centre coordinates in opposite/nearest-opposite spaces.
                theta=2*math.pi*(z//2)/z
                other=(centre[0]*math.cos(theta),centre[0]*math.sin(theta))
                distance=math.dist(centre,other)
                self.assertAlmostEqual(q['dimension_mm'],distance+(-1.7 if internal else 1.7))

    def test_no_solution_root_tip_reverse_curvature_and_access(self):
        for internal,z in ((False,20),(True,40)):
            g=profile(z=z,internal=internal)
            self.assertEqual(over_gauges(g,100 if internal else .01)['status'],'no_solution')
            good=over_gauges(g,1.7)
            r=good['contact_radius_mm']
            lower=deepcopy(g);lower['involute_start_radius_mm']=r+.01
            upper=deepcopy(g);upper['involute_end_radius_mm']=r-.01
            self.assertEqual(over_gauges(lower,1.7)['status'],'beyond_tip' if internal else 'root_or_fillet_contact')
            self.assertEqual(over_gauges(upper,1.7)['status'],'root_or_fillet_contact' if internal else 'beyond_tip')
            hidden=deepcopy(g)
            hidden['tip_radius_mm']=1 if internal else 100
            self.assertEqual(over_gauges(hidden,1.7)['status'],'hidden_gauge')
            intersect=deepcopy(g)
            intersect['root_radius_mm']=good['centre_circle_diameter_mm']/2
            self.assertEqual(over_gauges(intersect,1.7)['status'],'root_intersection')
        # A formal negative centre-pressure internal inverse at near-base
        # contact locally penetrates the concave flank: independently measure it.
        g=profile(z=34,internal=True);rb=g['base_radius_mm'];r=16.
        eta=math.pi/34-g['reference_half_angle_rad']+math.tan(g['transverse_pressure_angle_rad'])-g['transverse_pressure_angle_rad']
        roll=math.sqrt((r/rb)**2-1);ak=roll-eta
        diameter=2*rb*(eta-(math.tan(ak)-ak))
        centre=(rb/math.cos(ak),0)
        def p(rad):
            a=math.acos(rb/rad);angle=eta-(math.tan(a)-a)
            return rad*math.cos(angle),rad*math.sin(angle)
        self.assertLess(ak,0)
        self.assertLess(math.dist(p(r+.001),centre),diameter/2)
        self.assertEqual(over_gauges(g,diameter)['status'],'no_solution')
        for bad in (0,-1,math.nan,math.inf,True):
            with self.assertRaises(ValueError):over_gauges(profile(),bad)
        with self.assertRaises(ValueError):over_gauges(profile(),1.7,'wire')

    def test_actual_allowance_domain_and_exports(self):
        zero=over_gauges(profile(),1.7)['dimension_mm']
        thin=over_gauges(profile(backlash=.15),1.7)['dimension_mm']
        self.assertLess(thin,zero)
        for family in ('helical','double'):
            d=generate(family)
            q=measurement_query(d,0,3.4)
            self.assertFalse(q['result']['supported'])
            self.assertIn('3D contact',report_text(d))
        for family in ('worm','harmonic','cycloidal','differential'):
            with self.assertRaises(ValueError):measurement_query(generate(family),0,1.7)
        d=generate('spur',{'module':1,'teeth':20,'backlash':0})
        before=deepcopy(d.values)
        q=measurement_query(d,0,1.7,'roller','test-revision')
        self.assertEqual(d.values,before)
        self.assertAlmostEqual(q['result']['dimension_mm'],22.29409294937739)
        self.assertIn('Theoretical balls / rollers',report_text(d))
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'query'
            export_measurement(q,target)
            saved=json.loads((target/'measurement.json').read_text())
            self.assertEqual(saved,q)
            self.assertIn('over gauges M = 22.294093 mm',(target/'measurement.txt').read_text())
            with self.assertRaises(FileExistsError):export_measurement(q,target)
            stem=Path(folder)/'standard'
            export(d,stem)
            self.assertIn('over_gauges',json.loads(stem.with_suffix('.calculations.json').read_text())['tooth_profiles'][0])
            self.assertIn('Theoretical balls / rollers',stem.with_suffix('.calculations.txt').read_text())
