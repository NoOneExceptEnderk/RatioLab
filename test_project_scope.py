# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Retired material/process settings must not affect the reducer generator."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from geometry import FAMILIES, generate, get_specs
from engineering import report_text
import bom


LEGACY=dict(material='al_6061_t6',manufacturing_technology='fdm',
            manufacturing_settings={'fdm':{'infill':999,'pattern':'obsolete'}},
            stress_name='Previous material',stress_material_form='stock',
            stress_E=-1,stress_nu=2,stress_yield=-1,stress_axial=1000,
            stress_bending=50,stress_safety_factor=8)


def obsolete(key):
    return key=='material' or key.startswith(('stress_','manufacturing_'))


class ProjectScopeTests(unittest.TestCase):
    def test_legacy_settings_are_ignored_for_every_supported_family(self):
        for family in FAMILIES:
            with self.subTest(family=family):
                base=generate(family)
                restored=generate(family,dict(base.values,**LEGACY))
                self.assertEqual(restored.parts,base.parts)
                self.assertEqual(restored.analysis,base.analysis)
                self.assertEqual(restored.metrics,base.metrics)
                self.assertFalse(any(obsolete(k) for k in restored.values))
                self.assertFalse(any(obsolete(s[0]) for s in get_specs(family)))

    def test_bolted_shaft_and_housing_output_keep_geometry_and_nominal_loads(self):
        for variant in ('single','dual'):
            for scheme,ratio in [('eccentric_output_ring',-15),('eccentric_ring_output',16)]:
                with self.subTest(variant=variant,scheme=scheme):
                    base=generate('cycloidal',dict(variant=variant,eccentric_design='fdm_bolted',io_scheme=scheme))
                    legacy=generate('cycloidal',dict(base.values,**LEGACY))
                    self.assertEqual(base.parts,legacy.parts)
                    self.assertEqual(base.analysis,legacy.analysis)
                    self.assertEqual(legacy.analysis['signed_ratio'],ratio)
                    self.assertEqual(legacy.analysis['output']['rpm'],1500/ratio)
                    self.assertEqual(sum(p.name.startswith('Eccentric_tie_bolt_') for p in legacy.parts),2)

    def test_reports_bom_and_saved_parameters_exclude_removed_features(self):
        d=generate('cycloidal',LEGACY)
        with TemporaryDirectory() as folder:
            stem=Path(folder)/'reducer';bom.export(d,stem)
            data=json.loads(Path(str(stem)+'.calculations.json').read_text())
            assembly=json.loads(Path(str(stem)+'.bom.json').read_text())
            self.assertNotIn('material_stress',data)
            self.assertNotIn('manufacturing_process',data)
            self.assertFalse(any(obsolete(k) for k in assembly['parameters']))
            self.assertTrue(assembly['rows'])
            report=report_text(d)
            self.assertNotIn('MATERIAL AND THEORETICAL SECTION STRESSES',report)
            self.assertNotIn('MANUFACTURING TECHNOLOGY',report)
            self.assertIn('Input:',report)
            self.assertIn('signed_ratio',data)
            saved=json.loads(json.dumps(d.values))
            self.assertEqual(generate(d.family,saved).parts,d.parts)

    def test_retired_implementations_are_not_shipped(self):
        root=Path(__file__).resolve().parent
        for name in ('material_stress','material_controls','material_library','manufacturing','process_settings','process_controls'):
            self.assertFalse((root/(name+'.py')).exists(),name)


if __name__=='__main__':unittest.main()
