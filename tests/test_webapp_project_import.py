# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Project import preserves direct-generator geometry across tooth constructions."""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'webapp'))
import engine_bridge as web
from geometry import FAMILIES, generate


class ProjectImportTests(unittest.TestCase):
    def assert_roundtrip(self, project, ignored=()):
        # The oracle receives the ORIGINAL input, independently of either bridge.
        # Comparing two imports alone would let the same field loss pass twice.
        expected = generate(project['family'], project['parameters'])
        engine = web.Engine()
        imported = engine.call('import_project', dict(project=project))
        self.assertEqual(imported['ignored_parameters'], list(ignored))
        self.assertEqual(imported['values'], expected.values)
        self.assertEqual(engine.design.parts, expected.parts)
        saved = engine.call('project', dict(design_id=imported['design_id']))['project']
        with TemporaryDirectory(prefix='ratiolab-project-import-') as directory:
            path = Path(directory)/'saved.json'
            path.write_text(json.dumps(saved, ensure_ascii=False, allow_nan=False), encoding='utf-8')
            reopened = web.Engine()
            result = reopened.call('import_project', dict(project=json.loads(path.read_text(encoding='utf-8'))))
        self.assertEqual(result['ignored_parameters'], [])
        self.assertEqual(result['values'], expected.values)
        self.assertEqual(reopened.design.parts, expected.parts)
        return engine, imported

    def test_legacy_face_groove_and_original_example_remain_separated(self):
        example = json.loads((ROOT/'examples/face-double_helical.config.json').read_text())
        for project in (dict(format=web.PROJECT_FORMAT, family='face',
                             parameters=dict(variant='double_helical', gap=4)), example):
            with self.subTest(parameters=project['parameters']):
                engine, imported = self.assert_roundtrip(project)
                self.assertEqual(imported['values']['double_style'], 'separated')
                self.assertEqual(imported['values']['gap'], project['parameters']['gap'])
                self.assertEqual(engine.design.analysis['face_gear']['tooth_band_count'], 2)

    def test_precise_separated_face_groove_survives_save_and_reimport(self):
        precise = 6.1234567890123
        project = dict(format=web.PROJECT_FORMAT, family='face', parameters=dict(
            variant='double_helical', double_style='separated', width=12, gap=precise))
        engine, imported = self.assert_roundtrip(project)
        self.assertEqual(imported['values']['gap'], precise)
        self.assertEqual(imported['values']['double_style'], 'separated')
        self.assertEqual(engine.design.analysis['face_gear']['tooth_band_count'], 2)

    def test_joined_face_canonical_zero_is_recognized_even_when_editor_hides_it(self):
        canonical = generate('face', dict(variant='double_helical', double_style='joined')).values
        engine, imported = self.assert_roundtrip(dict(format=web.PROJECT_FORMAT,
                                                     family='face', parameters=canonical))
        self.assertEqual(imported['values']['gap'], 0)
        self.assertEqual(engine.design.analysis['face_gear']['tooth_band_count'], 1)

    def test_import_ignores_unknown_fields_but_live_validation_and_grooves_stay_strict(self):
        parameters = dict(variant='double_helical', gap=4, retired_setting=123)
        self.assert_roundtrip(dict(format=web.PROJECT_FORMAT, family='face', parameters=parameters),
                              ignored=('retired_setting',))
        with self.assertRaises(web.BridgeError):
            web.parameters_check('face', parameters)
        for gap in (True, '4', None, float('nan'), float('inf'), -1):
            project = dict(format=web.PROJECT_FORMAT, family='face',
                           parameters=dict(variant='double_helical', gap=gap))
            with self.subTest(gap=gap), self.assertRaises(ValueError):
                web.Engine().call('import_project', dict(project=project))

    def test_all_other_families_keep_canonical_values_and_actual_parts(self):
        for family in FAMILIES:
            if family == 'face':
                continue  # Its style-sensitive cases are covered explicitly above.
            with self.subTest(family=family):
                canonical = generate(family).values
                self.assert_roundtrip(dict(format=web.PROJECT_FORMAT, family=family,
                                           parameters=canonical))


if __name__ == '__main__':
    unittest.main()
