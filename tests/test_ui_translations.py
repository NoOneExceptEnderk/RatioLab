# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Shared UI catalog integrity and canonical engineering-data boundaries."""
import hashlib
import json
import re
from pathlib import Path
import unittest
from ui_language import catalog, translate


class LanguageCatalogTests(unittest.TestCase):
    def test_documentation_languages_have_the_same_messages_and_safe_placeholders(self):
        data = catalog()
        self.assertEqual(list(data['languages']), ['en','it','es','fr','de','pt','ru','zh-CN','ta'])
        english = data['translations']['en']
        for language, messages in data['translations'].items():
            self.assertEqual(set(messages), set(english), language)
            self.assertTrue(all(isinstance(value, str) and value for value in messages.values()))
            for source, target in messages.items():
                self.assertEqual(sorted(re.findall(r'\{(?:value|arg\d+|message\d+)\}',source)),
                                 sorted(re.findall(r'\{(?:value|arg\d+|message\d+)\}',target)))
            self.assertIn(data['languages'][language], data['languages'].values())

    def test_units_precision_unknown_terms_and_whitespace_remain_exact(self):
        for code in catalog()['languages']:
            for raw in ('2.000000000012345', '−0,000000000003', 'N·m', 'M3×12', 'user-design.json', '  \n'):
                self.assertEqual(translate(raw,code),raw)
            self.assertTrue(translate('Face width\u2009·\u2009mm',code).endswith('\u2009·\u2009mm'))
            self.assertIn('1500.00000000001', translate('At 1500.00000000001 rpm input',code))
        self.assertEqual(translate('A↔ Language','it'),'A↔ Lingua')
        self.assertEqual(translate('☀ Theme','it'),'☀ Tema')
        self.assertEqual(translate('Face width\u2009·\u2009mm','it'),'Larghezza dentatura\u2009·\u2009mm')

    def test_current_family_and_variant_names_have_no_uncatalogued_fragments(self):
        from geometry import FAMILIES, VARIANTS
        import re
        labels = [*FAMILIES.values(), *(label for variants in VARIANTS.values() for label in variants.values())]
        for language, messages in catalog()['translations'].items():
            for label in labels:
                with self.subTest(language=language, label=label):
                    if label in messages:
                        continue
                    for fragment in re.split(r' · | / ', label):
                        self.assertIn(fragment, messages)

    def test_technical_qualifiers_are_not_collapsed_to_generic_terms(self):
        for code in catalog()['languages']:
            for precise, generic in (('Normal module', 'Module'),
                                     ('Profile shift coefficient', 'Profile shift'),
                                     ('Rotation direction', 'Motion'),
                                     ('Bore diameter', 'Bore'),
                                     ('Input pinion teeth', 'Pinion teeth'),
                                     ('Driven wheel teeth', 'Wheel teeth')):
                with self.subTest(language=code, label=precise):
                    # These Chinese short labels already express coefficient
                    # and diameter; identical wording loses no information.
                    if code == 'zh-CN' and precise in ('Profile shift coefficient', 'Bore diameter'):
                        self.assertEqual(translate(precise, code),
                                         '变位系数' if precise == 'Profile shift coefficient' else '孔径')
                        continue
                    self.assertNotEqual(translate(precise, code), translate(generic, code))
        self.assertEqual(translate('Normal module [mm]', 'it'), 'Modulo normale [mm]')
        self.assertEqual(translate('Rotation direction', 'it'), 'Senso di rotazione')

    def test_model_catalog_descriptions_are_available_in_every_language(self):
        import ast
        tree = ast.parse((Path(__file__).resolve().parents[1]/'src/gui_workflow.py').read_text())
        families = {}
        for statement in tree.body:
            if not isinstance(statement, ast.Assign):
                continue
            target = statement.targets[0]
            if isinstance(target, ast.Name) and target.id == 'CATALOG':
                families.update(ast.literal_eval(statement.value))
            elif isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name) and target.value.id == 'CATALOG':
                families[ast.literal_eval(target.slice)] = ast.literal_eval(statement.value)
        from geometry import FAMILIES
        self.assertEqual(set(families), set(FAMILIES))
        for language, messages in catalog()['translations'].items():
            for family, (_, description) in families.items():
                with self.subTest(language=language, family=family):
                    self.assertIn(description, messages)
                    if language != 'en':
                        self.assertNotEqual(translate(description, language), description)

    def test_multilingual_font_payload_matches_recorded_source_hashes_and_notices(self):
        root = Path(__file__).resolve().parents[1]/'packaging/fonts'
        source = json.loads((root/'SOURCE-NOTO.json').read_text())
        for name, digest in source['files'].items():
            self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(), digest)
        for name in ('LICENSE-NotoCJK.txt','LICENSE-NotoTamil.txt'):
            self.assertIn('sil open font license', (root/name).read_text().lower())


if __name__ == '__main__':
    unittest.main()
