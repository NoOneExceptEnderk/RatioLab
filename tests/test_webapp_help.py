# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Static canonical help coverage; runtime/build tests do not require Cairo."""
import ast
import base64
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('web_help_generator', ROOT/'scripts/generate-web-help.py')
generator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generator)
bridge = generator.bridge


class WebHelpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.asset = json.loads((ROOT/'webapp/help-illustrations.json').read_text())

    def test_every_family_field_option_and_structural_context_has_canonical_help(self):
        self.assertEqual(self.asset['format'], 'ratiolab-help-illustrations/1')
        expected = set()
        for family in generator.geometry.FAMILIES:
            for values in generator.contexts(family):
                schema = bridge.schema(family, values)
                for field in schema['fields']+schema['options']:
                    if not field['help']:
                        continue
                    key = field['help']['diagram_context']; expected.add(key)
                    digest = self.asset['entries'][key]
                    kind = generator.diagrams.diagram_kind(family, field['key'])
                    self.assertEqual(digest is None, kind == 'text', (family, field['key'], values))
                    if digest:
                        self.assertIn(digest, self.asset['images'])
        self.assertEqual(expected, set(self.asset['entries']))
        self.assertGreater(len(expected), 700)

    def test_assets_are_original_lossless_images_with_current_source_provenance(self):
        for name, digest in self.asset['sources'].items():
            self.assertEqual(sha256((ROOT/name).read_bytes()).hexdigest(), digest)
        used = set(self.asset['entries'].values())-{None}
        self.assertEqual(used, set(self.asset['images']))
        for digest, uri in self.asset['images'].items():
            self.assertTrue(uri.startswith('data:image/png;base64,'))
            image = base64.b64decode(uri.split(',', 1)[1], validate=True)
            self.assertEqual(sha256(image).hexdigest(), digest)
            self.assertEqual(image[:8], b'\x89PNG\r\n\x1a\n')
            self.assertEqual(struct.unpack('>II', image[16:24]), (720, 480))

    def test_structurally_distinct_diagrams_remain_distinct(self):
        def image(family, key, **values):
            return self.asset['entries'][bridge.help_diagram_context(family, key, values)]
        self.assertNotEqual(image('worm', 'pressure', variant='za'), image('worm', 'pressure', variant='zi'))
        self.assertNotEqual(image('worm', 'module', worm_hand=-1), image('worm', 'module', worm_hand=1))
        self.assertNotEqual(image('double', 'helix', variant='joined'), image('double', 'helix', variant='separated'))
        self.assertNotEqual(image('parallel', 'helix', variant='helical'), image('parallel', 'helix', variant='double'))
        self.assertNotEqual(image('differential', 'module'), image('spur', 'module'))
        self.assertNotEqual(image('wolfrom', 'module'), image('planetary', 'module'))

    def test_renderer_new_context_dependencies_require_asset_review(self):
        tree = ast.parse((ROOT/'src/parameter_help_diagrams.py').read_text())
        keys = {node.args[0].value for node in ast.walk(tree) if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
                and node.func.value.id == 'values' and node.func.attr == 'get'
                and node.args and isinstance(node.args[0], ast.Constant)}
        self.assertEqual(keys, {'variant', 'double_style', 'worm_hand'})
        self.assertFalse(any(isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
                             and node.value.id == 'values' for node in ast.walk(tree)))


if __name__ == '__main__':
    unittest.main()
