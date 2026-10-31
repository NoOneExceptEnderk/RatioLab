# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Native browser RPC checks against canonical analyses, not UI acceptance."""
from copy import deepcopy
from dataclasses import asdict
import json
from math import pi
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'webapp'))
import engine_bridge as web
import backlash_solver
import bom
import combination_search
import component_geometry
import engineering
import gear_measurement
import geometry
import interference
import motion
from selected_export import subset


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.engine = web.Engine()

    def source(self, family='parallel', **parameters):
        # Most RPCs consume a generated canonical design; packing is independently
        # checked by W1 and the candidate test below, so avoid redundant meshes.
        self.engine.design = geometry.generate(family, parameters)
        self.engine.plan = motion.build_plan(self.engine.design)
        self.engine.design_id += 1
        self.engine.invalidate_queries()
        return self.engine.design

    def call(self, method, **args):
        return self.engine.call(method, dict(design_id=self.engine.design_id, **args))

    def test_documents_canonical_grouping_text_and_selection_provenance(self):
        source = self.source()
        original = deepcopy(source)
        for indices in (None, [2, 0]):
            result = self.call('documents', indices=indices)
            expected = subset(source, indices, self.engine.design_id) if indices else source
            self.assertEqual(result['data']['bom'], bom.build(expected))
            self.assertEqual(result['data']['bom_text'], bom.as_text(bom.build(expected)))
            self.assertEqual(result['data']['analysis'], expected.analysis)
            self.assertIn(engineering.report_text(expected), result['text'])
            if indices:
                self.assertEqual(result['data']['scope']['source_indices'], [1, 3])
                self.assertIn('SOURCE configuration', result['data']['report_text'])
        self.assertEqual(source, original)

    def test_metrology_default_explicit_unsupported_and_exact_query_exports(self):
        design = self.source('spur')
        result = self.call('metrology', source_index=0)
        native_default = gear_measurement.default_gauge(design.parts[0].profile_metadata['tooth_profile']['measurement_geometry'])
        self.assertEqual(result['data']['result'], native_default)
        diameter = native_default['gauge_diameter_mm']
        result = self.call('metrology', source_index=0, gauge_diameter=diameter, gauge_type='roller')
        expected = gear_measurement.measurement_query(design, 0, diameter, 'roller', self.engine.design_id)
        self.assertEqual(result['data'], expected)
        self.assertEqual(result['text'], gear_measurement.measurement_query_text(expected))
        for kind in ('json', 'txt'):
            exported = self.call('query_export', query_id=result['query_id'], format=kind)
            content = self.engine.buffers[exported['buffer']].decode()
            self.assertEqual(json.loads(content) if kind == 'json' else content, result if kind == 'json' else result['text'])
        self.source('helical')
        unsupported = self.call('metrology', source_index=0)
        self.assertEqual(unsupported['data']['result']['status'], 'unsupported')
        self.assertIn('3D contact', unsupported['text'])
        with self.assertRaisesRegex(ValueError, 'ball or roller'):
            self.call('metrology', source_index=0, gauge_type='pin')
        for index in (True, -1, 100):
            with self.assertRaises(ValueError):
                self.call('metrology', source_index=index)

    def test_finite_search_matches_canonical_and_apply_revalidates_without_mutation(self):
        design = self.source()
        original = deepcopy(design)
        schema = self.call('search_schema')
        self.assertEqual([v['key'] for v in schema['variables']], [s[0] for s in combination_search.variables(design.family, design.values)])
        settings = dict(target=3., tolerance_percent=10., max_candidates=10, max_results=2)
        result = self.call('search', grids={'wheel':'60,62'}, settings=settings)
        expected = combination_search.search(design.family, design.values, {'wheel':(60,62)}, combination_search.Settings(**settings))
        expected.revision = self.engine.design_id
        actual_data = deepcopy(result['data'])
        actual_data.pop('elapsed')
        expected_data = asdict(expected); expected_data.pop('elapsed')
        expected_data.update(complete=expected.complete, partial=not expected.complete)
        for row, proposal in zip(expected_data['proposals'], expected.proposals): row['xyz'] = proposal.xyz
        self.assertEqual(actual_data, expected_data)
        self.assertTrue(result['data']['complete'])
        self.assertEqual(len(result['data']['proposals']), 2)
        with patch('engine_bridge.geometry.generate', wraps=geometry.generate) as generation:
            application = self.call('search_apply', query_id=result['query_id'], proposal_index=1)
            generation.assert_called_once()
        self.assertEqual(application['values'], result['data']['proposals'][1]['values'])
        self.assertEqual(application['changes'], {'wheel': 62})
        self.assertEqual(design, original)
        partial = self.call('search', grids={'wheel':[62,60]}, settings=dict(settings, max_candidates=1))
        self.assertFalse(partial['data']['complete'])
        self.assertIn('candidate budget', partial['data']['reason'])
        self.assertEqual(partial['data']['visited'],1)
        self.assertEqual(len(partial['data']['proposals']),1)
        with patch('engine_bridge.geometry.generate', wraps=geometry.generate) as generation:
            application = self.call('search_apply', query_id=partial['query_id'], proposal_index=0)
            generation.assert_called_once()
        self.assertEqual(application['values'],partial['data']['proposals'][0]['values'])
        self.assertEqual(application['values']['wheel'],62)
        self.assertEqual(design.values['wheel'],60)
        self.assertFalse(self.engine.query['data']['complete'])
        self.assertIn('PARTIAL search',self.engine.query['text'])
        self.assertEqual(design,original)
        with self.assertRaisesRegex(ValueError, '100 results'):
            self.call('search', grids={'wheel':[60]}, settings=dict(max_results=101))

    def test_joined_search_apply_returns_only_revalidated_editor_changes(self):
        cases = [('parallel', 'double', 'wheel', 62),
                 ('internal', 'double', 'wheel', 68),
                 ('planetary', 'double', 'width', 11),
                 ('planetary', 'two_stage_double', 'width', 11)]
        for family, variant, key, value in cases:
            with self.subTest(family=family, variant=variant):
                design = self.source(family, variant=variant, double_style='joined',
                                     input_rpm=31.1234567890123)
                original = deepcopy(design)
                schema = web.schema(family, design.values)
                known = {field['key'] for field in schema['fields'] + schema['options']}
                self.assertNotIn('gap', known)
                result = self.call('search', grids={key: [value]}, settings=dict(
                    target=abs(design.analysis['signed_ratio']), tolerance_percent=10., max_candidates=1))
                self.assertEqual(len(result['data']['proposals']), 1)
                application = self.call('search_apply', query_id=result['query_id'], proposal_index=0)
                self.assertEqual(application['values']['gap'], 0)
                self.assertEqual(application['changes'], {key: value})
                self.assertLessEqual(set(application['changes']), known)
                regenerated = geometry.generate(family, dict(design.values, **application['changes']))
                self.assertEqual(regenerated.values, application['values'])
                self.assertEqual(regenerated.analysis['signed_ratio'], result['data']['proposals'][0]['ratio'])
                self.assertEqual(design, original)
                # Revalidation must still reject a candidate that no longer
                # matches its stored canonical geometry/ratio.
                self.engine.query['data']['proposals'][0]['ratio'] += 1
                with self.assertRaisesRegex(ValueError, 'Fresh candidate'):
                    self.call('search_apply', query_id=result['query_id'], proposal_index=0)
                self.assertEqual(design, original)

    def test_interference_retains_incomplete_coverage_and_progress(self):
        design = self.source()
        original = deepcopy(design)
        events = []
        self.engine.progress = lambda message, fraction: events.append((message, fraction))
        settings = dict(step_degrees=180., max_poses=1, max_seconds=30.)
        result = self.call('interference', settings=settings)
        expected = interference.analyze(design, interference.Settings(**settings), plan=self.engine.plan)
        expected.revision = self.engine.design_id
        native = asdict(expected); native.pop('elapsed_seconds')
        actual = deepcopy(result['data']); actual.pop('elapsed_seconds')
        self.assertEqual(actual, native)
        self.assertFalse(result['data']['coverage_complete'])
        self.assertTrue(result['data']['issues'])
        self.assertIn('INCOMPLETE', result['text'])
        self.assertTrue(events)
        self.assertTrue(all(0 <= fraction <= 1 for _, fraction in events))
        self.assertEqual(design, original)

    def test_real_backlash_candidate_is_independent_and_apply_is_gated(self):
        design = self.source()
        original = deepcopy(design)
        source_plan = self.engine.plan
        result = self.call('backlash', desired_backlash_mm=.372826053062876,
                           settings=dict(step_degrees=180., max_seconds=30.))
        self.assertTrue(result['data']['applicable'], result['text'])
        self.assertEqual(result['data']['status'], 'ready')
        self.assertTrue(result['data']['interference']['coverage_complete'])
        candidate = result['candidate']
        self.assertTrue(candidate['is_candidate'])
        self.assertAlmostEqual(candidate['values']['center_extra'], .3, places=11)
        expected = geometry.generate('parallel', candidate['values'])
        self.assertEqual(candidate['analysis'], expected.analysis)
        self.assertEqual(len(candidate['parts']), len(expected.parts))
        self.assertGreater(len(self.engine.buffers), 0)
        self.assertIs(self.engine.design, design)
        self.assertIs(self.engine.plan, source_plan)
        self.assertEqual(design, original)
        with patch('backlash_solver.revalidate', wraps=backlash_solver.revalidate) as check:
            ready = self.call('proposal_apply', proposal_id=result['data']['proposal_id'])
            check.assert_called_once()
        self.assertEqual(set(ready), {'design_id','proposal_id','center_extra'})
        self.assertAlmostEqual(ready['center_extra'], .3, places=11)
        self.assertEqual(design, original)
        with self.assertRaisesRegex(ValueError, 'matching current'):
            self.call('proposal_apply', proposal_id='obsolete')
        blocked = self.call('backlash', desired_backlash_mm=.372826053062876,
                            settings=dict(step_degrees=180., max_poses=1, max_seconds=30.))
        self.assertFalse(blocked['data']['applicable'])
        self.assertEqual(blocked['data']['status'], 'rejected')
        self.assertIsNotNone(self.engine.proposal)
        self.assertEqual(self.engine.query['query_id'], blocked['query_id'])
        with self.assertRaisesRegex(ValueError, 'fully checked'):
            self.call('proposal_apply', proposal_id=blocked['data']['proposal_id'])
        with self.assertRaisesRegex(ValueError, 'matching current'):
            self.call('proposal_apply', proposal_id=result['data']['proposal_id'])

    def assert_same_pose(self, a, b, phase, count):
        for index in range(count):
            for name in ('matrix','deformation','warp'):
                first, second = getattr(a,name)(index,phase), getattr(b,name)(index,phase)
                if first is None or second is None: self.assertIs(first, second)
                else:
                    for x,y in zip(first,second): self.assertAlmostEqual(x,y,places=8)

    def test_rates_no_mesh_work_preserves_pose_and_canonical_metadata_all_families(self):
        cases = [(f,{}) for f in geometry.FAMILIES]
        cases += [('parallel',dict(io_scheme='reverse')), ('worm',dict(io_scheme='reverse')),
                  ('planetary',dict(variant='two_stage_double',io_scheme='ring_carrier_sun',io_scheme2='sun_ring_carrier')),
                  ('differential',dict(configuration='classic'))]
        for family, parameters in cases:
            with self.subTest(family=family, parameters=parameters):
                design = self.source(family, **parameters)
                phase = 1.23456
                for speed in (321.125, 0, 7.5):
                    previous, old_id = self.engine.plan, self.engine.design_id
                    old = self.engine.design
                    old_data = deepcopy(old)
                    patch_values = dict(input_rpm=speed)
                    if family == 'differential':
                        patch_values.update(input_rpm=-speed, **{('output_difference_rpm' if parameters.get('configuration') == 'classic' else 'input_b_rpm'): speed*.375})
                    expected = geometry.generate(family, dict(old.values, **patch_values))
                    with patch('stl_export.triangles', side_effect=AssertionError('No mesh construction on rates')), \
                         patch('component_geometry.triangles', side_effect=AssertionError('No pick mesh construction on rates')), \
                         patch('engine_bridge.geometry.generate', side_effect=AssertionError('No regeneration on rates')):
                        result = self.call('rates', rpm_patch=patch_values, phase=phase)
                    self.assertGreater(result['design_id'], old_id)
                    for key in ('values','analysis','metrics','notes','requirements'):
                        self.assertEqual(result[key], getattr(expected,key), key)
                    self.assertEqual([r['port'] for r in result['ports']], [p.port for p in expected.parts])
                    self.assertEqual(self.engine.buffers, [])
                    self.assertNotIn('parts', result)
                    self.assert_same_pose(self.engine.plan, previous, phase, len(design.parts))
                    self.assertEqual(old, old_data)
                    for p,q in zip(self.engine.design.parts, old.parts):
                        self.assertIs(p.outer,q.outer); self.assertIs(p.mesh,q.mesh)
                    phase += (self.engine.plan.reference_rpm if speed else 0)*.19*2*pi/60
                saved = self.call('project')['project']
                self.assertEqual(saved['parameters'], self.engine.design.values)

    def test_rates_validation_and_query_invalidation_are_atomic(self):
        design = self.source('spur')
        query = self.call('documents')
        source_id = self.engine.design_id
        for kwargs in [dict(rpm_patch={'module':2}),dict(rpm_patch={'input_b_rpm':1}),dict(rpm_patch={'input_rpm':True}),
                       dict(rpm_patch={'input_rpm':-1}),dict(parameters=dict(design.values,module=3)),dict(parameters={'input_rpm':3})]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError): self.call('rates',phase=2.,**kwargs)
            self.assertIs(self.engine.design,design)
            self.assertEqual(self.engine.design_id,source_id)
            self.assertEqual(self.engine.query['query_id'],query['query_id'])
        self.call('rates',parameters=dict(design.values,input_rpm=31.1234567890123),phase=2.)
        self.assertIsNone(self.engine.query)
        with self.assertRaisesRegex(ValueError, 'active design_id'):
            self.engine.call('project',dict(design_id=source_id))
        with self.assertRaisesRegex(ValueError, 'no longer current'):
            self.call('query_export',query_id=query['query_id'],format='json')

    def test_pick_real_facets_hole_section_transform_and_surface_distance(self):
        design = self.source('spur')
        original = deepcopy(design)
        triangles = component_geometry.triangles(design.parts[0])
        top = max(q[2] for t in triangles for q in t)
        # Ray through a real facet centroid must hit the same canonical surface;
        # through the central bore it must pass through without an invented cap.
        triangle = next(t for t in triangles if all(abs(q[2]-top)<1e-9 for q in t))
        point = tuple(sum(q[k] for q in triangle)/3 for k in range(3))
        origin = [point[0],point[1],top+10]
        native = component_geometry.pick(origin,(0,0,-1),[(0,triangles)])
        result = self.call('pick',ray_origin=origin,ray_direction=[0,0,-1],visible_indices=[0])
        self.assertEqual(result['hit']['source_index'],native[0])
        self.assertEqual(result['hit']['point'],native[1])
        self.assertEqual(result['hit']['triangle'],native[2])
        hole = self.call('pick',ray_origin=[0,0,top+10],ray_direction=[0,0,-1],visible_indices=[0])
        self.assertIsNone(hole['hit'])
        self.assertIsNone(self.call('pick',ray_origin=origin,ray_direction=[0,0,-1],visible_indices=[])['hit'])
        self.assertIsNone(self.call('pick',ray_origin=origin,ray_direction=[0,0,-1],visible_indices=[0],section_y=point[1]-.01)['hit'])
        matrix = motion.translation(2,3,4)
        offset = (5,6,7)
        moved_origin = [x+y+z for x,y,z in zip(origin,(2,3,4),offset)]
        moved = self.call('pick',ray_origin=moved_origin,ray_direction=[0,0,-1],visible_indices=[0],animated=True,
                          matrices=[dict(index=0,matrix=matrix)],explosion_offsets=[dict(index=0,offset=offset)])
        for a,b in zip(moved['hit']['point'],tuple(x+y+z for x,y,z in zip(native[1],(2,3,4),offset))):
            self.assertAlmostEqual(a,b,places=10)
        distance = self.call('surface_distance',points=[native[1],moved['hit']['point']])
        self.assertAlmostEqual(distance['distance_mm'],component_geometry.distance(native[1],moved['hit']['point']))
        self.assertEqual(set(self.engine.surfaces),{0})
        self.assertEqual(design,original)
        with self.assertRaisesRegex(ValueError,'rigid'):
            self.call('pick',ray_origin=origin,ray_direction=[0,0,-1],visible_indices=[0],matrices=[dict(index=0,matrix=[2 if i in (0,5,10,15) else 0 for i in range(16)])])
        self.source('harmonic')
        self.assertEqual(self.engine.surfaces,{})
        with self.assertRaisesRegex(ValueError,'nonrigid'):
            self.call('pick',ray_origin=[0,0,100],ray_direction=[0,0,-1],visible_indices=[0],animated=True)
        nominal = self.call('pick',ray_origin=[0,0,100],ray_direction=[0,0,-1],visible_indices=[0])
        self.assertIn('hit',nominal)

    def test_latest_query_cache_stale_ids_settings_types_and_generation_clear(self):
        self.source('spur')
        first = self.call('documents')
        second = self.call('metrology',source_index=0)
        self.assertEqual(self.engine.query['query_id'],second['query_id'])
        self.assertIsNone(self.engine.proposal)
        with self.assertRaisesRegex(ValueError,'no longer current'):
            self.call('query_export',query_id=first['query_id'],format='txt')
        for method,args in [('interference',dict(settings={'max_poses':1.2})),('interference',dict(settings={'step_degrees':True})),
                            ('interference',dict(settings={'tolerance_mm':float('nan')})),('interference',dict(settings={'typo':1})),
                            ('search',dict(grids={'module':[2]},settings={'max_xyz':[True,100,100]}))]:
            with self.subTest(method=method,args=args),self.assertRaises(ValueError): self.call(method,**args)
        self.assertEqual(self.engine.query['query_id'],second['query_id'])
        self.call('clear')
        self.assertIsNone(self.engine.query);self.assertEqual(self.engine.surfaces,{})
        self.source('spur');self.call('documents')
        with self.assertRaises(ValueError):self.engine.call('generate',dict(family='spur',parameters={'module':-1}))
        self.assertIsNone(self.engine.design);self.assertIsNone(self.engine.query)


if __name__ == '__main__':
    unittest.main()
