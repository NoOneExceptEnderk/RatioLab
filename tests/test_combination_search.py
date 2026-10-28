# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Generator-backed search with brute-force enumeration and shared-surface bounds oracles."""
from copy import deepcopy
from itertools import product
from math import inf
from threading import Event
import unittest
from unittest.mock import patch
from time import sleep
from geometry import generate, defaults
from kinematics import options
from solid_geometry import faces
from combination_search import Settings, search, parse_grid, nominal_bounds


class CombinationSearchTests(unittest.TestCase):
    def brute(self, family, base, axes, settings):
        """No estimator or search matches() call: generate every combination."""
        found = set()
        for numbers in product(*axes.values()):
            values = dict(base, **dict(zip(axes, numbers)))
            try:
                d = generate(family, values)
                if any(d.values.get(k) != v for k, v in base.items() if k not in axes):
                    continue
                if any(d.values.get(k) != v for k, v in zip(axes, numbers)):
                    continue
                i = d.analysis['signed_ratio']
                if settings.direction == 'same' and i <= 0 or settings.direction == 'opposite' and i >= 0:
                    continue
                if abs(abs(i)-settings.target)/settings.target*100 > settings.tolerance_percent+1e-10:
                    continue
                # Read every real shared surface facet; no nominal_bounds().
                vertices = [q for p in d.parts for face in faces(p) for loop in face for q in loop]
                xyz = tuple(max(p[k] for p in vertices)-min(p[k] for p in vertices) for k in range(3))
                if any(a > b for a, b in zip(xyz, settings.max_xyz)):
                    continue
                found.add(tuple(d.values[k] for k in axes))
            except ValueError:
                pass
        return found

    def assert_domain(self, family, supplied, axes, target, direction='either', tolerance=30):
        base = generate(family, supplied).values
        settings = Settings(target=target, tolerance_percent=tolerance, direction=direction, max_results=500, max_seconds=120)
        before = deepcopy((base, axes))
        r = search(family, base, axes, settings)
        self.assertTrue(r.complete, r.text())
        self.assertEqual({tuple(p.values[k] for k in axes) for p in r.proposals}, self.brute(family, base, axes, settings))
        self.assertEqual((base, axes), before)
        self.assertEqual(r.proposals, sorted(r.proposals, key=lambda p:p.sort_key))
        for p in r.proposals:
            self.assertEqual(p.ratio, generate(family, p.values).analysis['signed_ratio'])
            self.assertTrue(all(p.values[k] == v for k, v in base.items() if k not in axes))
        return r

    def test_parallel_internal_bruteforce_direction_reverse_and_locks(self):
        for family in ('parallel', 'internal'):
            for scheme in options(family):
                for direction in ('either', 'same', 'opposite'):
                    self.assert_domain(family, {'io_scheme':scheme}, {'pinion': (20,22), 'wheel': (58,60,66)}, 3 if scheme == 'forward' else 1/3, direction)

    def test_all_coaxial_io_schemes_and_both_worm_hands(self):
        for family, axes in (('planetary', {'sun':(18,21), 'planet':(18,21)}), ('cycloidal', {'pins':(15,16)}), ('harmonic', {'teeth':(58,60)})):
            for scheme in options(family):
                base = generate(family, {'io_scheme':scheme})
                self.assert_domain(family, base.values, axes, abs(base.analysis['signed_ratio']), tolerance=15)
        for hand in (-1,1):
            for scheme in options('worm'):
                d = generate('worm', {'worm_hand':hand, 'io_scheme':scheme})
                self.assert_domain('worm', d.values, {'teeth':(28,30), 'starts':(1,2)}, abs(d.analysis['signed_ratio']), tolerance=10)

    def test_two_stages_mixed_connections_and_variants_fixed(self):
        for variant in ('two_stage', 'two_stage_double'):
            supplied = dict(variant=variant, io_scheme='ring_sun_carrier', io_scheme2='carrier_ring_sun')
            d = generate('planetary', supplied)
            r = self.assert_domain('planetary', d.values, {'sun':(18,21), 'planet':(18,), 'sun2':(18,), 'planet2':(18,21)}, abs(d.analysis['signed_ratio']), tolerance=25)
            self.assertTrue(r.proposals)
            for p in r.proposals:
                self.assertEqual(p.values['io_scheme2'], supplied['io_scheme2'])
                self.assertEqual(p.values['variant'], variant)

    def test_true_nominal_bounds_include_all_facets_and_boundary(self):
        for family in ('parallel','internal','planetary','cycloidal','harmonic','worm'):
            with self.subTest(family=family):
                d = generate(family)
                vertices = [q for p in d.parts for face in faces(p) for loop in face for q in loop]
                expected = (tuple(min(p[k] for p in vertices) for k in range(3)), tuple(max(p[k] for p in vertices) for k in range(3)))
                self.assertEqual(nominal_bounds(d), expected)
                xyz = tuple(b-a for a,b in zip(*expected))
                good = search(family, d.values, {}, Settings(target=abs(d.analysis['signed_ratio']), tolerance_percent=0, max_xyz=xyz))
                self.assertEqual(len(good.proposals),1)
                bad = search(family, d.values, {}, Settings(target=abs(d.analysis['signed_ratio']), max_xyz=(xyz[0]-1e-8,xyz[1],xyz[2])))
                self.assertFalse(bad.proposals)

    def test_locked_automatic_dimensions_are_never_silently_changed(self):
        # Gear-seat bearing mode raises a too-small width. Enumerating width=2
        # must not silently return width=8 outside that enumerated value.
        d = generate('planetary', {'bearing_mode':'gear', 'bearing':'626'})
        r = search('planetary',d.values,{'width':(2,10)},Settings(target=4,tolerance_percent=0))
        self.assertEqual([p.values['width'] for p in r.proposals],[10])
        self.assertEqual(r.rejected,1)
        self.assertTrue(all(p.values['bearing_mode']=='gear' and p.values['bearing']=='626' for p in r.proposals))
        # A smaller module cannot silently change the locked bore to fit.
        d = generate('parallel')
        r = search('parallel',d.values,{'module':(.1,2)},Settings(target=3,tolerance_percent=0))
        self.assertTrue(all(p.values['bore'] == d.values['bore'] for p in r.proposals))
        self.assertTrue(r.rejected)
        # Odd strain-wave counts are rejected by generate, despite their ratio.
        d = generate('harmonic')
        r = search('harmonic',d.values,{'teeth':(59,60)},Settings(target=30,tolerance_percent=10))
        self.assertEqual([p.values['teeth'] for p in r.proposals],[60])
        self.assertEqual(r.rejected,1)

    def test_finite_budgets_cancel_no_results_and_retention(self):
        d = generate('parallel')
        axes = {'pinion':tuple(range(18,24)), 'wheel':tuple(range(55,66))}
        r = search('parallel',d.values,axes,Settings(target=3,tolerance_percent=20,max_candidates=8,max_results=2))
        self.assertFalse(r.complete);self.assertEqual(r.visited,8);self.assertIn('candidate',r.reason);self.assertLessEqual(len(r.proposals),2)
        event=Event();event.set()
        r = search('parallel',d.values,axes,Settings(),event)
        self.assertEqual(r.visited,0);self.assertEqual(r.reason,'cancelled')
        r = search('parallel',d.values,axes,Settings(target=1e308,tolerance_percent=50))
        self.assertTrue(r.complete);self.assertFalse(r.proposals);self.assertEqual(r.generated,0)
        self.assertIn('No results',r.text())
        event=Event()
        def progress(*_):event.set()
        r = search('parallel',d.values,axes,Settings(),event,progress)
        self.assertFalse(r.complete);self.assertEqual(r.reason,'cancelled')
        r = search('parallel',d.values,axes,Settings(max_seconds=1e-12))
        self.assertFalse(r.complete);self.assertEqual(r.reason,'time budget reached')
        updates=[]
        r=search('parallel',d.values,{'module':(2,2.1)},Settings(target=3,tolerance_percent=0),progress=lambda message,fraction:updates.append(message))
        self.assertEqual(r.generated,2);self.assertTrue(any('2 generated' in message for message in updates))

    def test_preparation_counts_toward_time_and_precancel_skips_generation(self):
        d=generate('parallel');real=generate
        def delayed(*args,**kwargs):
            sleep(.02)
            return real(*args,**kwargs)
        with patch('combination_search.generate',delayed):
            r=search('parallel',d.values,{},Settings(max_seconds=.001))
        self.assertFalse(r.complete);self.assertEqual(r.generated,0);self.assertEqual(r.visited,0)
        self.assertGreaterEqual(r.elapsed,.02);self.assertEqual(r.reason,'time budget reached')
        event=Event();event.set()
        with patch('combination_search.generate',side_effect=AssertionError('precancel must skip generation')):
            r=search('parallel',d.values,{},Settings(),event)
        self.assertEqual(r.visited,0);self.assertEqual(r.reason,'cancelled')

    def test_discrete_grid_parsing_and_invalid_inputs(self):
        self.assertEqual(parse_grid('2, 4:8:2, 2'),(2.,4.,6.,8.))
        for text in ('nan','inf','','1:5:0','4:2:1','1:2000:1','1:2','-1e308:1e308:1e-308','-1e308:1e308:1'):
            with self.subTest(text=text), self.assertRaises(ValueError):parse_grid(text)
        d=generate('parallel')
        for kwargs in ({'target':0},{'target':inf},{'target':-3},{'target':True},{'tolerance_percent':100},{'direction':'sideways'},{'max_xyz':(1,0,1)},{'max_candidates':1.5},{'max_seconds':inf}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):search('parallel',d.values,{},Settings(**kwargs))
        for axes in ({'pinion':(20.5,)},{'pinion':(1,)},{'pinion':()},{'width':(inf,)},{'variant':('spur',)},{'io_scheme':('reverse',)}):
            with self.subTest(axes=axes),self.assertRaises(ValueError):search('parallel',d.values,axes)
        with self.assertRaisesRegex(ValueError,'single gear'):search('spur',defaults('spur'),{})

if __name__=='__main__':unittest.main()
