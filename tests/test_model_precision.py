# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""A requested sweep threshold must never masquerade as total model accuracy."""
import unittest
from geometry import generate
from geometry_quality import PRESETS, deviation, with_quality


class ModelPrecisionTests(unittest.TestCase):
    def test_straight_gear_retains_its_profile_error_at_every_preset(self):
        source=generate('spur');parts=source.parts
        bounds=[]
        for _,value in PRESETS:
            configured=with_quality(source,dict(preview_mm=value,export_mm=value))
            report=deviation(configured,'export')
            self.assertEqual(report['interpolation_mm'],0)
            self.assertGreater(report['model_mm'],.005)
            bounds.append(report['model_mm'])
            self.assertIs(configured.parts,parts)
        self.assertEqual(bounds,[bounds[0]]*3)
        self.assertFalse(hasattr(source,'quality') and source.quality)

    def test_helical_sweep_refines_but_total_remains_separate(self):
        source=generate('helical');local=[];complete=[]
        for _,value in PRESETS:
            report=deviation(with_quality(source,dict(export_mm=value)),'export')
            self.assertLessEqual(report['interpolation_mm'],value)
            self.assertGreater(report['model_mm'],report['interpolation_mm'])
            local.append(report['interpolation_mm']);complete.append(report['model_mm'])
        self.assertEqual(local,sorted(local,reverse=True))
        self.assertEqual(complete,sorted(complete,reverse=True))
        self.assertGreater(complete[-1],PRESETS[-1][1])

    def test_assembly_never_gets_a_fabricated_complete_bound(self):
        source=generate('parallel')
        for _,value in PRESETS:
            report=deviation(with_quality(source,dict(export_mm=value)),'export')
            self.assertIsNone(report['model_mm'])
            self.assertIsNotNone(report['reason'])
            self.assertIsNotNone(report['interpolation_mm'])

    def test_invalid_purpose_and_threshold_are_rejected(self):
        source=generate('spur')
        with self.assertRaises(ValueError):deviation(source,'step')
        for value in (-1,float('inf'),0):
            with self.assertRaises(ValueError):with_quality(source,dict(export_mm=value))


if __name__=='__main__':unittest.main()
