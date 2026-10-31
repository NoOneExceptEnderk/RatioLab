# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Reset the canonical motion origin after offset-preserving speed changes."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'webapp'))
import engine_bridge as web
import geometry
import motion


class MotionResetTests(unittest.TestCase):
    def test_reset_restores_fresh_plan_without_mesh_work_and_invalidates_queries(self):
        for family, parameters in [('spur', {}), ('differential', {}), ('harmonic', {})]:
            with self.subTest(family=family):
                engine = web.Engine()
                source = engine.design = geometry.generate(family, parameters)
                engine.plan = motion.build_plan(source)
                engine.design_id = 1
                original = source.values.copy()
                fresh = engine.plan
                new_rpm = 31.125 if family == 'differential' else 0.
                engine.call('rates', dict(design_id=1, rpm_patch={'input_rpm':new_rpm}, phase=2.345))
                # The preceding rates update really introduced offsets: phase zero
                # no longer denotes the initial construction pose.
                offset = engine.plan
                self.assertTrue(any(offset.matrix(i, 0) != fresh.matrix(i, 0) or
                                    offset.deformation(i, 0) != fresh.deformation(i, 0)
                                    for i in range(len(source.parts))))
                # A retained completed-query cache entry must be invalidated even
                # though reset leaves the source document untouched.
                query = engine.remember('reset-check', {'basis':'test'}, 'Retained query')
                previous_id = engine.design_id
                retained = engine.design
                expected = motion.build_plan(retained)
                with patch.object(geometry, 'generate', side_effect=AssertionError('regenerated')), \
                        patch.object(engine, 'pack_design', side_effect=AssertionError('packed')):
                    reset = engine.call('motion_reset', dict(design_id=previous_id))
                self.assertEqual(reset['design_id'], previous_id+1)
                self.assertEqual(reset['phase'], 0.)
                self.assertEqual(reset['motion'], engine.motion_metadata())
                self.assertFalse(engine.buffers)
                self.assertIs(engine.design, retained)
                self.assertEqual(engine.design.values, dict(original, input_rpm=new_rpm))
                for phase in (0., .125, 1.25):
                    for index in range(len(source.parts)):
                        self.assertEqual(engine.plan.matrix(index, phase), expected.matrix(index, phase))
                        self.assertEqual(engine.plan.deformation(index, phase), expected.deformation(index, phase))
                for index in range(len(source.parts)):
                    self.assertEqual(engine.plan.matrix(index, 0), fresh.matrix(index, 0))
                    self.assertEqual(engine.plan.deformation(index, 0), fresh.deformation(index, 0))
                with self.assertRaisesRegex(ValueError, 'current'):
                    engine.call('query_export', dict(design_id=engine.design_id, query_id=query['query_id'], format='txt'))
                with self.assertRaises(ValueError):
                    engine.call('motion_reset', dict(design_id=previous_id))

    def test_reset_requires_current_source(self):
        engine = web.Engine()
        with self.assertRaises(ValueError):
            engine.call('motion_reset', dict(design_id=0))


if __name__ == '__main__':
    unittest.main()
