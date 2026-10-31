# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""The supported catalog is a generator boundary, not just a menu filter."""
from pathlib import Path
import unittest
from geometry import FAMILIES,SPECS,VARIANTS,generate,get_specs
from gui_workflow import CATALOG

KEPT=('spur','helical','double','planetary','cycloidal','harmonic','worm','parallel','internal','differential','wolfrom')
REMOVED=('compound','wave_roller','three_ring','angular_roller','diff_bevel','diff_planetary','diff_spur','diff_pulley','cable_hoist','diff_cable','diff_lock','rv','qdd','sea','joint_support')

class ReducerCatalogTests(unittest.TestCase):
    def test_catalog_specs_and_labels_agree(self):
        self.assertEqual(tuple(FAMILIES),KEPT)
        self.assertEqual(set(SPECS),set(KEPT))
        self.assertEqual(set(CATALOG),set(KEPT))
        self.assertLessEqual(set(VARIANTS),set(KEPT))

    def test_removed_families_are_rejected_by_generator_and_parameters(self):
        for family in REMOVED:
            with self.subTest(family=family):
                with self.assertRaises(ValueError):generate(family)
                with self.assertRaises(ValueError):get_specs(family)

    def test_removed_implementations_are_not_shipped(self):
        import geometry
        root=Path(geometry.__file__).resolve().parent
        for name in ('easy_controls','easy_design','robot_drives','robot_specs','cable_drives','mishin_drives','mishin_specs'):
            self.assertFalse((root/(name+'.py')).exists(),name)

if __name__=='__main__':unittest.main()
