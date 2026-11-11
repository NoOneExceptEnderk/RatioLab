# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Real query decision criteria and construction-based capabilities."""
import unittest
from geometry import generate
from combination_search import search, Settings
from gear_measurement import measurement_query, measurement_query_text, default_gauge
from tool_capabilities import capabilities, gauge_components


class QueryDecisionTests(unittest.TestCase):
    def test_ranking_and_contact_filter_use_regenerated_meshes(self):
        design = generate('parallel')
        axes = {'pinion': (18, 20), 'wheel': (54, 60)}
        compact = search('parallel', design.values, axes, Settings(target=3, tolerance_percent=0, ranking='compact'))
        contact = search('parallel', design.values, axes, Settings(target=3, tolerance_percent=0, ranking='contact'))
        self.assertEqual(len(compact.proposals), 2)
        self.assertEqual(len(contact.proposals), 2)
        self.assertEqual(compact.proposals[0].values['pinion'], 18)
        self.assertEqual(contact.proposals[0].values['pinion'], 20)
        self.assertGreater(contact.proposals[0].comparison['min_profile_contact'], contact.proposals[1].comparison['min_profile_contact'])
        for row in contact.proposals:
            fresh = generate('parallel', row.values)
            self.assertEqual(row.comparison['min_profile_contact'], min(m['profile_contact_total'] for m in fresh.analysis['meshes']))
        filtered = search('parallel', design.values, axes, Settings(target=3, tolerance_percent=0, min_profile_contact=100))
        self.assertFalse(filtered.proposals)
        self.assertEqual(filtered.exclusions['usable contact ratio'], 2)
        self.assertEqual(filtered.exclusions['ratio'], 2)
        self.assertEqual(sum(filtered.exclusions.values()), filtered.visited)

    def test_unknown_contact_cannot_be_ranked_as_verified(self):
        design = generate('cycloidal')
        for options in (dict(ranking='contact'), dict(min_profile_contact=1)):
            with self.assertRaisesRegex(ValueError, 'cylindrical'):
                search('cycloidal', design.values, {'pins': (design.values['pins'],)}, Settings(**options))
        for value in (-1, float('nan'), True, '1'):
            with self.assertRaises(ValueError):
                Settings(min_profile_contact=value).validate()

    def test_existing_geometry_parameters_can_be_explored_without_unlocking_other_values(self):
        design = generate('parallel', {'variant': 'helical', 'helix': 20})
        result = search('parallel', design.values,
                        {'pressure': (20, 22), 'helix': (20, 25), 'profile_shift': (0, .1), 'center_extra': (0, .1)},
                        Settings(target=3, tolerance_percent=0))
        self.assertTrue(result.complete)
        self.assertTrue(result.proposals)
        self.assertEqual(result.total, 16)
        for row in result.proposals:
            for key in ('pinion', 'wheel', 'module', 'width', 'bore', 'variant'):
                self.assertEqual(row.values[key], design.values[key])
            self.assertEqual(generate('parallel', row.values).values, row.values)

    def test_capabilities_follow_construction_not_family_alone(self):
        spur = generate('spur')
        self.assertFalse(capabilities(spur)['search']['available'])
        self.assertTrue(capabilities(spur)['metrology']['available'])
        self.assertFalse(capabilities(generate('helical'))['metrology']['available'])
        self.assertFalse(capabilities(generate('parallel', {'variant': 'two_stage'}))['backlash']['available'])
        self.assertTrue(capabilities(generate('parallel'))['backlash']['available'])
        self.assertFalse(any(value['available'] for value in capabilities(None).values()))

    def test_compound_cylindrical_member_uses_its_own_profile_and_spans(self):
        design = generate('wolfrom')
        index = gauge_components(design)[0]
        profile = design.parts[index].profile_metadata['tooth_profile']
        diameter = default_gauge(profile['measurement_geometry'])['gauge_diameter_mm']
        query = measurement_query(design, index, diameter)
        self.assertEqual(query['source_position'], index+1)
        self.assertEqual(query['span'], profile['wildhaber_span'])
        self.assertEqual(query['result']['status'], 'ok')
        self.assertIn('W_k', measurement_query_text(query))
