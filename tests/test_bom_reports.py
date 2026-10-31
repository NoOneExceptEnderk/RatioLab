# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Canonical BOM text and real exports for coupled differential speeds."""
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest
import zlib

import bom
import engineering
import geometry
import motion
import package_export
import selected_export


def png_fixture():
    """A valid encoded 1x1 RGB PNG, solely an export-writer test fixture."""
    def chunk(kind, data):
        return (struct.pack('>I', len(data))+kind+data+
                struct.pack('>I', zlib.crc32(kind+data)))
    return (b'\x89PNG\r\n\x1a\n'+
            chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))+
            chunk(b'IDAT', zlib.compress(b'\0\x20\x80\xc0'))+chunk(b'IEND', b''))


class BomReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.designs = {family: geometry.generate(family, {}) for family in geometry.FAMILIES}
        cls.differentials = {
            'wrist': cls.designs['differential'],
            'classic': geometry.generate('differential', {'configuration': 'classic'}),
        }

    def updated(self, configuration):
        design = self.differentials[configuration]
        return motion.update_operating_rates(design, dict(
            design.values, input_rpm=17.25, input_b_rpm=-4.5, output_difference_rpm=-8.75))

    def assert_differential_text(self, design, text):
        kinematics = design.analysis['kinematics']
        self.assertNotIn('label', kinematics)
        self.assertIn('Kinematic model: '+kinematics['kind'].replace('_', ' '), text)
        for member, rpm in kinematics['rates_rpm'].items():
            self.assertIn(f'  {member.replace("_", " ")}: {rpm:+.6g} rpm\n', text)
        for equation in kinematics['equations']:
            self.assertIn('  '+equation+'\n', text)
        self.assertIn('Speed reference: '+kinematics['reference']+'\n', text)
        self.assertNotIn('Motor:', text)
        self.assertNotIn('ratio +', text)
        if design.values['configuration'] == 'classic':
            self.assertIn('Boundary condition: '+kinematics['boundary_condition'], text)
            self.assertIn('Source: '+kinematics['reference_source'], text)
            self.assertIn('Source section: '+kinematics['reference_section'], text)
            self.assertIn(f'Prescribed side speed difference B−A: {kinematics["prescribed_difference_rpm"]:+.6g} rpm', text)

    def test_all_eleven_families_serialize_without_changing_analysis(self):
        self.assertEqual(len(self.designs), 11)
        for family, design in self.designs.items():
            with self.subTest(family=family):
                analysis = deepcopy(design.analysis)
                text = bom.as_text(bom.build(design))
                self.assertIn('Model: '+family+'\n', text)
                self.assertIn('TO BE COMPLETED\n', text)
                self.assertEqual(design.analysis, analysis)
                if family == 'differential':
                    self.assert_differential_text(design, text)
                elif 'kinematics' in analysis:
                    self.assertIn('INPUTS / OUTPUTS\n'+analysis['kinematics']['label']+'\n\n', text)

    def test_legacy_labeled_text_stays_exact(self):
        report = dict(family='planetary', rows=[], requirements=['Complete assembly.'],
                      analysis=dict(kinematics=dict(label='Sun input · Carrier output · Ring fixed',
                          stage_results=[dict(input='sun', output='carrier', fixed='ring', signed_ratio=4)])))
        self.assertEqual(bom.as_text(report),
            'BILL OF MATERIALS · SOLIDCRAFT REDUCERS\n'
            'Model: planetary\n'
            'Dimensions in mm; strength and service life are not verified.\n\n'
            'PURCHASE\n  No items.\n\n'
            'MANUFACTURE\n  No items.\n\n'
            'TO BE DEFINED\n  No items.\n\n'
            'INPUTS / OUTPUTS\nSun input · Carrier output · Ring fixed\n\n'
            '  Motor: sun; output: carrier; fixed: ring; ratio +4\n\n'
            'TO BE COMPLETED\n• Complete assembly.\n')

    def test_differential_text_tracks_canonical_rates_before_and_after_updates(self):
        expected = {
            'wrist': ('  input a: +17.25 rpm', '  input b: -4.5 rpm',
                      '  carrier: +6.375 rpm', '  output spin: -10.875 rpm'),
            'classic': ('  side a: +21.625 rpm', '  side b: +12.875 rpm',
                        '  carrier: +17.25 rpm', '  spider spin: -4.375 rpm'),
        }
        for configuration, original in self.differentials.items():
            analysis = deepcopy(original.analysis)
            for design in (original, self.updated(configuration)):
                with self.subTest(configuration=configuration, speed=design.values['input_rpm']):
                    text = bom.as_text(bom.build(design))
                    self.assert_differential_text(design, text)
                    if design is not original:
                        for line in expected[configuration]:
                            self.assertIn(line+'\n', text)
            self.assertEqual(original.analysis, analysis)

    def test_differential_bom_export_full_and_selected_preserves_source_analysis(self):
        with TemporaryDirectory() as temporary:
            for configuration, original in self.differentials.items():
                for state, design in (('initial', original), ('updated', self.updated(configuration))):
                    for selected in (False, True):
                        with self.subTest(configuration=configuration, state=state, selected=selected):
                            if selected:
                                design_to_export = selected_export.subset(design, [1, 3], revision=9)
                            else:
                                design_to_export = design
                            stem = Path(temporary)/f'{configuration}-{state}-{selected}'
                            result = bom.export(design_to_export, stem)
                            text = stem.with_suffix('.bom.txt').read_text(encoding='utf-8')
                            self.assert_differential_text(design, text)
                            self.assertEqual(text, bom.as_text(result))
                            saved = json.loads(stem.with_suffix('.bom.json').read_text())
                            self.assertEqual(saved['analysis'], design_to_export.analysis)
                            self.assertEqual(json.loads(stem.with_suffix('.calculations.json').read_text()), design_to_export.analysis)
                            expected = engineering.report_text(design_to_export)
                            if selected:
                                expected = 'SELECTED COMPONENTS ONLY. Calculations below describe the SOURCE configuration.\n\n'+expected
                                self.assertIn('Source indices: 2, 4\n', text)
                                self.assertEqual(saved['export_scope']['source_indices'], [2, 4])
                                self.assertEqual(sorted(i for row in saved['rows'] for i in row['source_indices']), [2, 4])
                            self.assertEqual(stem.with_suffix('.calculations.txt').read_text(), expected)
                            with stem.with_suffix('.bom.csv').open(encoding='utf-8-sig', newline='') as source:
                                self.assertEqual(sum(int(row['quantity']) for row in csv.DictReader(source)), len(design_to_export.parts))

    def test_real_differential_packages_include_bom_and_checked_manifest(self):
        # One full wrist and one selected classic package exercise both canonical
        # configurations and provenance without repeating expensive mesh writers.
        png = png_fixture()
        for configuration, selected in (('wrist', False), ('classic', True)):
            with self.subTest(configuration=configuration), TemporaryDirectory() as temporary:
                design = self.updated(configuration)
                config = dict(format='solidcraft-riduttori/1', family=design.family, parameters=design.values)
                target = Path(temporary)/'package'
                if selected:
                    selected_export.export(design, [1, 3], 'package', target, config=config, png=png, revision=9)
                else:
                    package_export.export(design, config, target, png)
                manifest = json.loads((target/'manifest.json').read_text())
                self.assertTrue(manifest['complete'])
                self.assertEqual(manifest['complete_assembly'], not selected)
                self.assertEqual(manifest['components'], 2 if selected else len(design.parts))
                entries = {entry['path']: entry for entry in manifest['files']}
                actual = {str(path.relative_to(target)) for path in target.rglob('*') if path.is_file()}
                self.assertEqual(set(entries), actual-{'manifest.json'})
                for name, entry in entries.items():
                    self.assertFalse(Path(name).is_absolute())
                    self.assertNotIn('..', Path(name).parts)
                    data = (target/name).read_bytes()
                    self.assertEqual(entry['bytes'], len(data))
                    self.assertEqual(entry['sha256'], hashlib.sha256(data).hexdigest())
                self.assertEqual((target/'preview.png').read_bytes(), png)
                self.assert_differential_text(design, (target/'model.bom.txt').read_text())
                saved = json.loads((target/'model.bom.json').read_text())
                self.assertEqual(saved['analysis']['kinematics'], design.analysis['kinematics'])
                count = manifest['components']
                self.assertEqual(len(list((target/'step-parts').glob('*.step'))), count)
                self.assertEqual(len(list((target/'model.stl-parts').glob('*.stl'))), count)
                self.assertEqual(len(json.loads((target/'profiles.json').read_text())['components']), count)
                commands = json.loads((target/'model.script.json').read_text())['commands']
                for command in commands:
                    if command['command'] == 'file.insert_step':
                        self.assertTrue(command['params']['path'].startswith('assets/'))
                        self.assertIn(command['params']['path'], entries)
                if selected:
                    scope = json.loads((target/'selection.json').read_text())
                    self.assertEqual(scope['source_indices'], [2, 4])
                    self.assertEqual(scope['document_revision'], 9)
                    self.assertEqual(manifest['scope'], scope)
                    self.assertEqual(saved['export_scope'], scope)
                    self.assertEqual(json.loads((target/'model.config.json').read_text())['selected_export'], scope)
                    self.assertIn('SELECTED COMPONENTS ONLY', (target/'model.bom.txt').read_text())


if __name__ == '__main__':
    unittest.main()
