# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Source provenance, exact edits and independent CAD/preview boundaries."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch,Mock
from bisect import bisect_right
from math import atan,cos,sin,sqrt,hypot

import cad_contract as cad
from geometry import generate
from solidcraft_recipe import compile,insert


class MathematicalCADTests(unittest.TestCase):
    def test_no_preview_dependency_and_exact_normal_sources(self):
        with patch('geometry.generate',side_effect=AssertionError('preview construction called')),patch('geometry.gear_part',side_effect=AssertionError('sampled profile called')):
            recipe=cad.create('spur',dict(module='2.00000000000000000001'))
            geometry=cad.evaluate_component(recipe,0)
        self.assertEqual(geometry['analytic_values']['pitch_radius_mm'],'24.00000000000000000012')
        self.assertLessEqual(geometry['sweep']['surface_interpolation_bound_mm'],recipe['cad_tolerance_mm'])
        self.assertEqual(cad.validate(json.loads(json.dumps(recipe))),recipe)
        self.assertNotIn('triangles',json.dumps(recipe))

    def test_edit_changes_topology_and_rejects_stale_exact_sources(self):
        recipe=cad.create('spur',dict(module='2.00000000000000000001'))
        changed=cad.edit(recipe,dict(module='2.50000000000000000001',teeth=26))
        self.assertNotEqual(recipe['source_sha256'],changed['source_sha256'])
        self.assertEqual(cad.evaluate_component(changed,0)['analytic_values']['pitch_radius_mm'],'32.50000000000000000013')
        with self.assertRaises(ValueError):cad.edit(recipe,{'unknown_dimension':4})
        for mutate in (lambda r:r.update(schema='future'),lambda r:r['frames'].update(length='inch'),
                       lambda r:r['parameters'].update(module=4),lambda r:r['components'][0]['placement'].update(z_mm=3),
                       lambda r:r.update(source_sha256='0'*64)):
            wrong=deepcopy(recipe);mutate(wrong)
            with self.assertRaises(ValueError):cad.validate(wrong)

    def test_native_curves_and_explicit_unsupported_before_CAD_mutation(self):
        recipe=cad.create('spur',dict(teeth=12,module=1,bore=0))
        result=compile(recipe)
        commands={c['command'] for c in result['commands']}
        self.assertIn('sketch.spline.control_point',commands)
        self.assertIn('solid.extrude',commands)
        self.assertNotIn('file.insert_step',commands)
        self.assertNotIn('sketch.line',commands)
        for family,values in [('helical',{}),('double',{}),('rack',dict(variant='helical'))]:
            client=Mock()
            with self.assertRaisesRegex(ValueError,'qualified'):insert(client,cad.create(family,values))
            self.assertFalse(client.mock_calls)

    def test_multistage_CAD_and_model_share_placements_and_checks(self):
        values=dict(variant='three_stage_helical',layout_angle2=73,layout_angle3=-31,
                    module2='2.00000000000000000001',helix2='-18.1234567890123456789')
        recipe=cad.create('parallel',values);design=generate('parallel',values)
        self.assertEqual(len(recipe['components']),len(design.parts))
        for c,p in zip(recipe['components'],design.parts):
            self.assertEqual(c['name'],p.name)
            self.assertEqual(c['placement']['center_mm'],list(p.center))
            self.assertEqual(c['placement']['z_mm'],p.z)
            self.assertEqual(c['port']['shaft'],p.port['shaft'])
        with self.assertRaisesRegex(ValueError,'swept-envelope'):cad.edit(cad.create('parallel',dict(variant='two_stage')),dict(layout_angle2=180))

    def test_rack_recipe_is_finite_and_no_nonsensical_rotary_ratio(self):
        recipe=cad.create('rack');compiled=compile(recipe)
        self.assertEqual(len(compiled['bodies']),2)
        c=recipe['components'][1]
        self.assertEqual(c['port']['axis'],'World +X')
        geometry=cad.evaluate_component(recipe,1)
        self.assertEqual(geometry['lower'],geometry['upper'])
        self.assertEqual(geometry['interpolation_bound_mm'],0.)
        with self.assertRaises(ValueError):cad.edit(recipe,dict(rack_teeth=8,width=60,variant='helical',helix=35))

    def test_unachievable_or_invalid_CAD_targets_fail_explicitly(self):
        for value in (0,-1,True,float('nan'),float('inf')):
            with self.assertRaises(ValueError):cad.create('spur',tolerance_mm=value)
        recipe=cad.create('spur',tolerance_mm=1e-20)
        with self.assertRaisesRegex(ValueError,'resolution'):cad.evaluate_component(recipe,0)

    def test_mm_units_and_exact_expression_width_survive_native_compilation(self):
        recipe=cad.create('rack',dict(width=10.,_decimal_inputs={'width':{'expression':['div','20.00000000000000000001',2]}}))
        native=compile(recipe)
        for item in native['commands']:
            if item['command']=='solid.extrude':self.assertEqual(item['params']['distance'],'10.0 mm')
            if item['command']=='sketch.spline.control_point':
                self.assertTrue(all(x.endswith(' mm') for point in item['params']['points'] for x in point))
        self.assertIn('width',recipe['parameters']['_decimal_inputs'])

    def test_uniform_native_curves_against_de_boor_and_continuous_source(self):
        def de_boor(points,u):
            count=len(points);spans=count-3
            knots=[0.]*4+[i/spans for i in range(1,spans)]+[1.]*4
            k=min(count-1,max(3,bisect_right(knots,u)-1));d=[list(points[j+k-3]) for j in range(4)]
            for r in range(1,4):
                for j in range(3,r-1,-1):
                    a=(u-knots[j+k-3])/(knots[j+1+k-r]-knots[j+k-3])
                    d[j]=[(1-a)*x+a*y for x,y in zip(d[j-1],d[j])]
            return d[3]
        for values in (dict(teeth=12,module=1,bore=0),dict(teeth=24,module=2),dict(teeth=20,module=2,profile_shift=.2)):
            geometry=cad.evaluate_component(cad.create('spur',values),0,native_uniform_cubic=True)
            profile=geometry['profile'];self.assertLess(len(profile['curves']),512)
            for curve in profile['curves']:
                if curve['kind']!='uniform_cubic':continue
                self.assertLessEqual(len(curve['controls']),500)
                source=profile['reference_sources'][curve['source']]
                a,b=curve['domain'];rot=curve['rotation_rad']
                for u in (0.,.03,.17,.51,.83,.97,1.):
                    t=a+(b-a)*u
                    if source['kind']=='rack_corner':q=cad.call('curve_point',dict(curve=source,t=t))
                    else:
                        r=source['base_radius_mm']*sqrt(1+t*t)
                        angle=source['offset_rad']+source['orientation']*(t-atan(t));q=[r*cos(angle),r*sin(angle)]
                    x,y=q
                    if curve['mirror']:y=-y
                    expected=(x*cos(rot)-y*sin(rot),x*sin(rot)+y*cos(rot))
                    actual=de_boor(curve['controls'],u)
                    self.assertLessEqual(hypot(actual[0]-expected[0],actual[1]-expected[1]),
                        curve['interpolation_bound_mm']+curve['join_displacement_mm']+profile['resolution_guard_mm'])


if __name__=='__main__':unittest.main()
