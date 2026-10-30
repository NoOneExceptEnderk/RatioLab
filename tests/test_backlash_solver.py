# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Independent forward benchmarks and generated-domain/collision inverse checks."""
from copy import deepcopy
from math import acos, atan, cos, radians, tan
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import json
import unittest
from unittest.mock import patch
from geometry import generate
from interference import Analysis, Settings
from backlash_solver import working_backlash, inverse_distance, solve, revalidate, export_proposal, interference_blocker


def independent(values, extra):
    beta = radians(values.get('helix', 0))
    at = atan(tan(radians(values['pressure']))/cos(beta))
    a0 = values['module']*(values['pinion']+values['wheel'])/(2*cos(beta))
    a = a0+extra
    aw = acos(a0*cos(at)/a)
    return values['backlash']*a/a0 + 2*a*(tan(aw)-aw-tan(at)+at)


def complete(**kwargs):
    return Analysis(dict(step_degrees=180,tolerance_mm=.01,max_poses=721,max_seconds=30,
                         max_parts=128,max_triangles=300000),coverage_complete=True,
                    planned_poses=7,completed_poses=7,**kwargs)


class BacklashSolverTests(unittest.TestCase):
    def test_fixed_independent_roots_scaling_and_boundary(self):
        for extra, target in ((.1,.223414903130557),(.3,.372826053062876),(1,.922262444591769)):
            self.assertAlmostEqual(inverse_distance(80,20,.15,target),extra,places=11)
            self.assertAlmostEqual(working_backlash(80,20,.15,extra),target,places=12)
            self.assertAlmostEqual(inverse_distance(160,20,.3,target*2),extra*2,places=11)
        self.assertEqual(inverse_distance(80,20,.15,.15),0)
        self.assertEqual(inverse_distance(80,20,0,0),0)
        limit=working_backlash(80,20,.15,5)
        self.assertEqual(inverse_distance(80,20,.15,limit),5)
        # Only floating roundoff can be clamped at a bracket endpoint.
        self.assertEqual(inverse_distance(80,20,.15,.15-1e-14),0)
        for target in (.149999,limit+.001,float('nan'),float('inf'),-.1,True):
            with self.subTest(target=target),self.assertRaises(ValueError):inverse_distance(80,20,.15,target)
        for arguments in ((0,20,.15,.3),(80,90,.15,.3),(80,0,.15,.3),(80,20,-.1,.3),
                          (80,20,.15,.3,1,0),(float('inf'),20,.15,.3)):
            with self.assertRaises(ValueError):inverse_distance(*arguments)
        with self.assertRaises(ValueError):working_backlash(1e308,20,.15,1e308)

    def test_generated_variants_hands_double_width_and_normalization(self):
        for variant, hand, gap in (('spur',0,0),('helical',25,0),('helical',-25,0),
                                   ('double',25,1),('double',-25,0)):
            with self.subTest(variant=variant,hand=hand,gap=gap):
                d=generate('parallel',dict(variant=variant,helix=hand,gap=gap,width=12,center_extra=.1))
                original=deepcopy(d.values)
                target=independent(d.values,.3)
                with patch('backlash_solver.analyze',return_value=complete()):
                    p=solve(d,target)
                self.assertTrue(p.applicable,p.reason)
                self.assertAlmostEqual(p.values['center_extra'],.3,places=11)
                actual=generate('parallel',p.values).analysis['meshes'][0]
                self.assertAlmostEqual(actual['working_pair_backlash_mm'],target,places=11)
                self.assertGreaterEqual(actual['profile_contact_total'],1)
                self.assertEqual(d.values,original)
                self.assertEqual(revalidate(p).values,p.values)
                if variant=='double':
                    expected=((12-d.values['gap'])/2)*abs(__import__('math').sin(radians(hand)))/(3.141592653589793*d.values['module'])
                    self.assertAlmostEqual(actual['contact_overlap'],expected)
                p.values['width']+=1
                with self.assertRaisesRegex(ValueError,'other than'):revalidate(p)
        malformed=generate('parallel',dict(variant='double',gap=0))
        malformed.values['gap']=1
        with self.assertRaisesRegex(ValueError,'normalized'):solve(malformed,.3)

    def test_reference_pair_need_not_be_usable_and_generated_limits(self):
        with self.assertRaisesRegex(ValueError,'Interference'):generate('parallel',dict(pinion=12,center_extra=0))
        d=generate('parallel',dict(pinion=12,center_extra=.5))
        with patch('backlash_solver.analyze',return_value=complete()):
            p=solve(d,independent(d.values,.6))
        self.assertTrue(p.applicable,p.reason)
        with patch('backlash_solver.analyze') as analysis:
            rejected=solve(d,independent(d.values,0))
            self.assertIn('Interference',rejected.reason)
            self.assertFalse(rejected.applicable);analysis.assert_not_called()
        # A real generator case whose nominal ratio passes while usable flanks fail.
        source=generate('parallel',dict(pinion=12,wheel=22,pressure=14.5,center_extra=1))
        mesh=source.analysis['meshes'][0]
        self.assertGreater(mesh['contact_total'],1);self.assertLess(mesh['profile_contact_total'],1)
        with patch('backlash_solver.analyze') as analysis:
            p=solve(source,mesh['working_pair_backlash_mm'])
            self.assertIn('Usable involute',p.reason);analysis.assert_not_called()
        with patch('backlash_solver.analyze') as analysis:
            d=generate('parallel')
            p=solve(d,independent(d.values,5))
            self.assertFalse(p.applicable);self.assertIn('contact',p.reason.lower());analysis.assert_not_called()
        for family in ('spur','internal','planetary'):
            with self.assertRaisesRegex(ValueError,'parallel external'):solve(generate(family),.3)

    def test_real_complete_check_query_export_and_revalidation(self):
        d=generate('parallel')
        p=solve(d,.372826053062876,Settings(step_degrees=180,max_seconds=30))
        self.assertTrue(p.applicable,p.text())
        self.assertEqual(p.interference['completed_poses'],7)
        self.assertTrue(p.interference['coverage_complete'])
        self.assertEqual(p.interference['settings']['step_degrees'],180)
        boundaries=[r for r in p.interference['rows'] if r['kind']=='Boundary contact / unresolved']
        self.assertTrue(boundaries)
        self.assertTrue(all(r['expected'].startswith('Same kinematic member') for r in boundaries))
        self.assertIn('no continuous',p.text().lower())
        with TemporaryDirectory() as folder:
            path=Path(folder)/'query';export_proposal(p,path)
            data=json.loads((path/'backlash.json').read_text())
            self.assertEqual(data['source_values'],d.values)
            self.assertAlmostEqual(data['values']['center_extra'],.3,places=11)
            self.assertIn('Complete sampled coverage',(path/'backlash.txt').read_text())
            with self.assertRaises(FileExistsError):export_proposal(p,path)
        self.assertAlmostEqual(revalidate(p).values['center_extra'],.3,places=11)

    def test_cancel_incomplete_and_collision_policy(self):
        event=Event();event.set()
        p=solve(generate('parallel'),.3,cancel=event)
        self.assertEqual(p.status,'cancelled');self.assertFalse(p.applicable)
        incomplete=solve(generate('parallel'),.3,Settings(step_degrees=180,max_poses=1,max_seconds=30))
        self.assertFalse(incomplete.applicable)
        self.assertFalse(incomplete.interference['coverage_complete'])
        self.assertIn('Incomplete',incomplete.reason)
        def row(kind,expected=''):
            return dict(kind=kind,expected=expected)
        for rows,blocked in (([row('Separated')],False),
                             ([row('Boundary contact / unresolved','Same kinematic member · candidate')],False),
                             ([row('Boundary contact / unresolved','Constructed gear mesh')],True),
                             ([row('Intersection','Same kinematic member')],True),
                             ([row('Containment')],True)):
            data=dict(coverage_complete=True,issues=[],cancelled=False,rows=rows)
            self.assertEqual(interference_blocker(data) is not None,blocked)
        collision=complete(rows=[row('Intersection','Same kinematic member')])
        with patch('backlash_solver.analyze',return_value=collision):
            p=solve(generate('parallel'),.3)
        self.assertFalse(p.applicable)
        self.assertIn('intersection',p.reason)
        with self.assertRaises(ValueError):revalidate(p)

    def test_exact_current_mesh_baseline_target(self):
        for beta in (0,25,-25):
            d=generate('parallel',dict(variant='helical' if beta else 'spur',helix=beta))
            with patch('backlash_solver.analyze',return_value=complete()):
                p=solve(d,d.analysis['meshes'][0]['working_pair_backlash_mm'])
            self.assertTrue(p.applicable,p.reason)
            self.assertAlmostEqual(p.values['center_extra'],0,places=11)
