# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Cycloidal cams are transmission members, separate from optional supports."""
import json
from math import pi
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from connection import Client
from geometry import Design, generate
from kinematics import options
from motion import build_plan, transform
import selected_export


INPUT_SCHEMES = ('eccentric_output_ring', 'eccentric_ring_output')


def cams(design):
    return [(i, part) for i, part in enumerate(design.parts)
            if part.name in ('Eccentric_1', 'Eccentric_2')]


class CycloidalEccentricVisibilityTests(unittest.TestCase):
    def test_cams_remain_essential_with_correct_motion_in_every_arrangement(self):
        for variant in ('single', 'dual'):
            for scheme in options('cycloidal'):
                with self.subTest(variant=variant, scheme=scheme):
                    design = generate('cycloidal', dict(variant=variant, io_scheme=scheme))
                    found = cams(design)
                    self.assertEqual(len(found), 1 if variant == 'single' else 2)
                    rates = design.analysis['kinematics']['stage_results'][0]['rates_rpm']
                    source, target, fixed = scheme.split('_')
                    expected_role = 'input' if source == 'eccentric' else 'output' if target == 'eccentric' else 'fixed'
                    plan = build_plan(design)
                    for index, part in found:
                        self.assertEqual(part.role, 'gear')
                        self.assertEqual(part.port['member'], 'eccentric')
                        self.assertEqual(part.port['rpm'], rates['eccentric'])
                        self.assertEqual(part.port['role'], expected_role)
                        if scheme in INPUT_SCHEMES:
                            x, y, z = transform(plan.matrix(index, pi/2), (*part.center, part.z))
                            self.assertAlmostEqual(x, -part.center[1])
                            self.assertAlmostEqual(y, part.center[0])
                            self.assertAlmostEqual(z, part.z)
                    supports = [part for part in design.parts if part.name.startswith('Bearing_eccentric_')]
                    self.assertEqual(len(supports), len(found))
                    self.assertTrue(all(part.role == 'support' for part in supports))

    def test_solidcraft_hides_optional_parts_but_keeps_the_input_cams(self):
        for variant in ('single', 'dual'):
            for scheme in INPUT_SCHEMES:
                with self.subTest(variant=variant, scheme=scheme):
                    design = generate('cycloidal', dict(variant=variant, io_scheme=scheme))
                    client = Client()
                    commands = design.commands('/tmp/ratiolab-eccentric-test-assets')
                    def call(method, params=None):
                        if method == 'engine.commands':
                            return [{'id':command['command']} for command in commands]
                        return {}
                    client.call = Mock(side_effect=call)
                    client.execute_commands = Mock(return_value={})
                    client.execute = Mock()
                    with patch.object(Design, 'prepare_assets'):
                        client.insert(design, visible_roles={'gear'},
                                      asset_dir='/tmp/ratiolab-eccentric-test-assets')
                    hidden = next(call.kwargs['items'] for call in client.execute.call_args_list
                                  if call.args[0] == 'browser.visibility')
                    expected = [f'{design.token}_{i}_{part.name}_body'
                                for i, part in enumerate(design.parts) if part.role != 'gear']
                    self.assertEqual(hidden, expected)
                    for index, part in cams(design):
                        self.assertNotIn(f'{design.token}_{index}_{part.name}_body', hidden)
                    self.assertTrue(any('Bearing_eccentric_' in body for body in hidden))

    def test_selected_cam_step_exports_only_that_original_component(self):
        with TemporaryDirectory(prefix='ratiolab-eccentric-exports-') as temporary:
            for variant in ('single', 'dual'):
                design = generate('cycloidal', dict(variant=variant))
                names = [part.name for part in design.parts]
                index, part = cams(design)[-1]
                target = Path(temporary)/variant
                selected_export.export(design, [index], 'step', target, revision='cam-only')
                scope = json.loads((target/'selection.json').read_text())
                self.assertEqual(scope['source_indices'], [index+1])
                self.assertEqual(scope['components'], [dict(source_index=index+1, name=part.name)])
                self.assertEqual(len(list((target/'step-parts').glob('*.step'))), 1)
                self.assertEqual((target/'assembly.step').read_text().count('MANIFOLD_SOLID_BREP('), 1)
                exported = json.loads((target/'selected.bom.json').read_text())
                self.assertEqual(sum(row['quantity'] for row in exported['rows']), 1)
                self.assertEqual([part.name for part in design.parts], names)
                self.assertTrue(any(part.role == 'support' for part in design.parts))

    def test_existing_printed_shaft_members_still_use_the_essential_role(self):
        for variant in ('single', 'dual'):
            for scheme in INPUT_SCHEMES:
                design = generate('cycloidal', dict(variant=variant, io_scheme=scheme,
                                                    eccentric_design='fdm_bolted'))
                names = design.analysis['printed_eccentric_shaft']['printed_parts']
                printed = [part for part in design.parts if part.name in names]
                self.assertEqual(len(printed), 2 if variant == 'single' else 3)
                self.assertTrue(all(part.role == 'gear' for part in printed))
                self.assertTrue(all(part.port['member'] == 'eccentric' for part in printed))


if __name__ == '__main__':
    unittest.main()
