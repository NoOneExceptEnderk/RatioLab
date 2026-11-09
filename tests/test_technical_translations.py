# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Technical message coverage, substitutions and unchanged engineering data."""
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest
from ui_language import catalog, translate

ROOT = Path(__file__).resolve().parents[1]


class TechnicalTranslationTests(unittest.TestCase):
    def test_source_message_inventory_has_every_language(self):
        spec = importlib.util.spec_from_file_location('ui_translation_audit',ROOT/'scripts/check-ui-translations.py')
        audit = importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
        inventory = audit.inventory()
        for language,messages in catalog()['translations'].items():
            self.assertFalse(set(inventory)-messages.keys(),language)

    def test_dynamic_values_and_embedded_placeholder_text_remain_literal(self):
        source = 'Configuration saved: {arg0}'
        filename = '/tmp/Tools/{arg1}/progetto α −0,000000000003.json'
        reason = 'Centre distance bounds are reversed.'
        for language,messages in catalog()['translations'].items():
            expected = source if language=='en' else messages[source]
            self.assertEqual(translate(source.replace('{arg0}',filename),language),expected.replace('{arg0}',filename))
            outer = 'Proposal not applied: {message0}'
            expected = outer if language=='en' else messages[outer]
            self.assertEqual(translate(outer.replace('{message0}',reason),language),expected.replace('{message0}',translate(reason,language)))
        self.assertEqual(translate('Triangolo STL degenere: −2.5e+12','en'),
                         'Degenerate STL triangle: −2.5e+12')

    def test_static_friction_explanation_keeps_equations_and_limit_qualifiers(self):
        from parameter_help import COMMON
        source = COMMON['worm_static_friction'].effect
        for code in catalog()['languages']:
            text = translate(source,code)
            for formula in ('μcritical = cos(αn) tan(γ)','γ = atan(mx × starts / d)','αn = atan(tan(αx) cos(γ))'):
                self.assertIn(formula,text)
        self.assertIn('solo potenzialmente reversibile',translate(source,'it'))
        self.assertIn('仅表示可能',translate(source,'zh-CN'))

    def test_file_references_and_named_engineering_symbols_remain_canonical(self):
        for language,messages in catalog()['translations'].items():
            for source,target in messages.items():
                names = set(re.findall(r'\b[\w.-]+\.(?:json|step|stl|svg|dxf|py|png|csv|txt)\b',source))
                names.update(re.findall(r'\b(?:m[123]|P[12]|R[of]|mn|mx|mt|dref|cos|sin|tan|atan|atan2|sqrt|x_mm|pinion_angle_rad|pitch_radius_mm)\b',source))
                for name in names:
                    with self.subTest(language=language,source=source,name=name):
                        self.assertIn(name,target)

    def test_python_and_browser_match_on_rendered_technical_templates(self):
        node = os.environ.get('RATIOLAB_TEST_NODE') or shutil.which('node')
        if not node:
            self.skipTest('Node.js required for cross-runtime translation check')
        cases = []
        fields = re.compile(r'\{(value|arg\d+|message\d+)\}')
        for source in catalog()['translations']['en']:
            if not fields.search(source):
                continue
            raw = fields.sub(lambda match: '−0,000000000003' if match[1]=='value'
                             else 'Centre distance bounds are reversed.' if match[1].startswith('message')
                             else '/tmp/value{arg9} α' if match[1]=='arg0' else '-2.50000000001e+12',source)
            cases.append([raw,{code:translate(raw,code) for code in catalog()['languages']}])
        with TemporaryDirectory() as folder:
            path = Path(folder)/'cases.json';path.write_text(json.dumps(cases,ensure_ascii=False))
            result = subprocess.run([node,'--experimental-vm-modules',str(ROOT/'tests/webapp_technical_translations.mjs'),str(path)],
                capture_output=True,text=True,timeout=40)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)


if __name__ == '__main__':
    unittest.main()
