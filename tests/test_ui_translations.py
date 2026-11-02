# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Shared UI catalog integrity and canonical engineering-data boundaries."""
import hashlib
import json
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
                self.assertEqual(source.count('{value}'), target.count('{value}'))
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

    def test_multilingual_font_payload_matches_recorded_source_hashes_and_notices(self):
        root = Path(__file__).resolve().parents[1]/'packaging/fonts'
        source = json.loads((root/'SOURCE-NOTO.json').read_text())
        for name, digest in source['files'].items():
            self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(), digest)
        for name in ('LICENSE-NotoCJK.txt','LICENSE-NotoTamil.txt'):
            self.assertIn('sil open font license', (root/name).read_text().lower())


if __name__ == '__main__':
    unittest.main()
