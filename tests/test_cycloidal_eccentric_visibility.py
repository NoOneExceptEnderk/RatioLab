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
from geometry import Design, circle_info, generate
from kinematics import options
from motion import build_plan, transform
import selected_export


INPUT_SCHEMES = ('eccentric_output_ring', 'eccentric_ring_output')


def cams(design):
    integral = design.analysis.get('eccentric_connection', {}).get('part')
    return [(i, part) for i, part in enumerate(design.parts)
            if part.name in ('Eccentric_1', 'Eccentric_2', integral)]


class CycloidalEccentricVisibilityTests(unittest.TestCase):

    def test_ring_carrier_and_roller_bearings_follow_the_selected_members(self):
        from bom import build
        from catalog import RING_ROLLER_BEARINGS
        from collision_geometry import Surface, relation

        bearing = RING_ROLLER_BEARINGS['693']
        for variant in ('single', 'dual'):
            reference = generate('cycloidal', dict(variant=variant))
            reference_ring = next(p for p in reference.parts if p.name == 'Ring_pin_carrier')
            for scheme in options('cycloidal'):
                with self.subTest(variant=variant, scheme=scheme):
                    d = generate('cycloidal', dict(variant=variant, io_scheme=scheme))
                    self.assertEqual(d.values['ring_roller_bearing'], 'none')
                    plain_ring = next(p for p in d.parts if p.name == 'Ring_pin_carrier')
                    self.assertEqual((plain_ring.outer, plain_ring.holes), (reference_ring.outer, reference_ring.holes))
                    self.assertFalse(any(p.name.startswith(('Pin_ring_', 'Roller_ring_')) for p in d.parts))
                    b = generate('cycloidal', dict(d.values, ring_roller_bearing=bearing.code))
                    names = {p.name: p for p in b.parts}
                    q = b.analysis['kinematics']['stage_results'][0]
                    ring = names['Ring_pin_carrier']
                    pins = [p for p in b.parts if p.name.startswith('Pin_ring_')]
                    rollers = [p for p in b.parts if p.name.startswith('Roller_ring_')]
                    discs = [p for p in b.parts if p.name.startswith('Disc_cycloidal_')]
                    integrated = q['output'] == 'ring'
                    self.assertEqual(len(pins), 0 if integrated else b.values['pins'])
                    self.assertEqual(len(rollers), len(pins) * len(discs))
                    self.assertEqual(len(ring.holes), 1)
                    self.assertEqual(ring.z, discs[0].z)
                    self.assertAlmostEqual(ring.width, discs[-1].z + discs[-1].width)
                    self.assertFalse(any(name.startswith(('Cover_', 'Housing_tubular',
                                                          'Bearing_ring_output_', 'Ring_output_bearing_'))
                                         for name in names))
                    self.assertEqual(ring.port['rpm'], q['rates_rpm']['ring'])
                    self.assertEqual(b.analysis['signed_ratio'], d.analysis['signed_ratio'])
                    self.assertEqual(d.parts[0].outer == discs[0].outer, integrated)
                    for pin in pins:
                        self.assertEqual(pin.port, ring.port)
                    for roller in rollers:
                        self.assertEqual(circle_info(roller.outer)[2], bearing.D / 2)
                        self.assertEqual(roller.port, ring.port)
                        self.assertTrue(any(disc.z <= roller.z and roller.z+roller.width <= disc.z+disc.width
                                            for disc in discs))
                    purchases = [row for row in build(b)['rows'] if row['code'] == 'NSK 693']
                    self.assertEqual(sum(row['quantity'] for row in purchases), len(rollers))
                    if integrated:
                        self.assertNotIn('ring_output_support', b.analysis)
                        self.assertFalse(any(name.startswith('Attachment_') for name in names))
                        plan = build_plan(b)
                        matrix = plan.matrix(b.parts.index(ring), pi / 2)
                        self.assertNotEqual(transform(matrix, (40, 0, 0)), (40, 0, 0))
                    carrier_surface = Surface.from_part(ring)
                    disc_surface = Surface.from_part(discs[0])
                    try:
                        self.assertEqual(relation(carrier_surface, disc_surface, .001)['kind'], 'Separated')
                    finally:
                        carrier_surface.close()
                        disc_surface.close()

    def test_roller_bearing_choice_is_saved_and_width_is_validated(self):
        from parameter_errors import ParameterError
        from test_webapp_project_import import web

        values = dict(variant='dual', pin_radius=3.125, ring_roller_bearing='692', io_scheme=INPUT_SCHEMES[0])
        project = {'format':'solidcraft-riduttori/1', 'family':'cycloidal', 'parameters':values}
        engine = web.Engine()
        loaded = engine.call('import_project', {'project': project})
        saved = engine.call('project', {'design_id': loaded['design_id']})['project']
        restored = engine.call('import_project', {'project': json.loads(json.dumps(saved))})
        self.assertEqual(restored['ignored_parameters'], [])
        self.assertEqual(restored['values']['ring_roller_bearing'], '692')
        self.assertEqual(restored['values']['pin_radius'], 3.125)
        self.assertEqual(restored['analysis']['ring_rollers']['contact_diameter_mm'], 6)
        with self.assertRaises(ParameterError) as caught:
            generate('cycloidal', dict(values, width=2))
        self.assertIn('ring_roller_bearing', caught.exception.fields)
        self.assertEqual(caught.exception.limits['width']['lower'], 2.3)

    def test_bushed_rollers_keep_the_contact_profile_and_export_separate_parts(self):
        from bom import build
        from collision_geometry import Surface, relation
        from test_webapp_project_import import web

        code = 'GSM-0304-05'
        values = dict(variant='dual', ring_roller_bearing=code)
        plain = generate('cycloidal', {'variant': 'dual'})
        d = generate('cycloidal', values)
        found = {p.name: p for p in d.parts}
        for ref in plain.parts:
            if ref.name.startswith('Disc_cycloidal_'):
                self.assertEqual(found[ref.name].outer, ref.outer)
        shell = found['Roller_ring_1_shell_2']
        sleeve = found['Bushing_ring_1_2']
        pin = found['Pin_ring_1']
        carrier = found['Ring_pin_carrier']
        self.assertEqual((shell.center, shell.z, shell.width), (sleeve.center, sleeve.z, sleeve.width))
        self.assertEqual(shell.center, pin.center)
        self.assertEqual(shell.z, found['Disc_cycloidal_2'].z + 1.5)
        self.assertEqual(circle_info(shell.outer)[2], 3)
        self.assertEqual(circle_info(shell.holes[0])[2], 2.25)
        self.assertEqual(circle_info(sleeve.outer)[2], 2.25)
        self.assertAlmostEqual(circle_info(sleeve.holes[0])[2], 1.507)
        self.assertEqual(circle_info(pin.outer)[2], 1.5)
        self.assertEqual(pin.width, carrier.width)
        self.assertEqual(shell.port, sleeve.port)
        surfaces = [Surface.from_part(p) for p in (sleeve, pin)]
        try:
            self.assertEqual(relation(*surfaces, .001)['kind'], 'Separated')
        finally:
            for surface in surfaces:
                surface.close()
        rows = {row['description']: row for row in build(d)['rows']}
        self.assertEqual((rows['iglide G cylindrical bushing']['category'],
                          rows['iglide G cylindrical bushing']['quantity']), ('PURCHASE', 32))
        self.assertEqual((rows['Cycloidal roller shell']['category'],
                          rows['Cycloidal roller shell']['quantity']), ('MANUFACTURE', 32))
        with TemporaryDirectory() as folder:
            for kind in ('step', 'stl'):
                destination = Path(folder) / kind
                selected_export.export(d, [d.parts.index(p) for p in (shell, sleeve)], kind, destination)
                manifest = json.loads((destination/'manifest.json').read_text())
                self.assertEqual(len(manifest['scope']['components']), 2)
                self.assertTrue(any(row['path'].endswith('.'+kind) for row in manifest['files']))

        project = {'format':'solidcraft-riduttori/1', 'family':'cycloidal', 'parameters':values}
        engine = web.Engine()
        loaded = engine.call('import_project', {'project': project})
        saved = engine.call('project', {'design_id': loaded['design_id']})['project']
        restored = engine.call('import_project', {'project': json.loads(json.dumps(saved))})
        self.assertEqual(restored['ignored_parameters'], [])
        self.assertEqual(restored['values']['ring_roller_bearing'], code)
        self.assertEqual(restored['analysis']['ring_rollers']['bushing_count'], 32)

    def test_bushed_rollers_validate_fit_and_keep_integral_ring_output(self):
        from parameter_errors import ParameterError

        code = 'GSM-0405-06'
        with self.assertRaises(ParameterError) as caught:
            generate('cycloidal', {'ring_roller_bearing': code})
        self.assertEqual(caught.exception.limits['pin_radius']['lower'], 3.25)
        with self.assertRaises(ParameterError) as caught:
            generate('cycloidal', {'ring_roller_bearing': code, 'pin_radius': 3.25, 'width': 5})
        self.assertEqual(caught.exception.limits['width']['lower'], 6)
        d = generate('cycloidal', {'ring_roller_bearing': code, 'io_scheme': INPUT_SCHEMES[1]})
        self.assertEqual(d.values['ring_roller_bearing'], code)
        self.assertFalse(any(p.name.startswith(('Bushing_ring_', 'Roller_ring_', 'Pin_ring_'))
                             for p in d.parts))

    def test_shaft_support_catalog_is_independent_of_ring_rollers(self):
        d = generate('cycloidal', dict(bearing_mode='shaft', hardware_mode='standard', ring_roller_bearing='692'))
        blocks = [p for p in d.parts if p.name in ('Bearing_block_input', 'Bearing_block_output')]
        self.assertEqual(len(blocks), 2)
        self.assertTrue(all(p.port['role'] == 'fixed' and len(p.machining) == 2 for p in blocks))
        self.assertEqual(sum(p.catalog_code == '608' for p in d.parts), 2)
        self.assertEqual(sum(p.procurement.get('code') == 'NSK 692' for p in d.parts), 16)
        self.assertFalse(any(p.name.startswith(('Cover_', 'Mounting_')) for p in d.parts))

    def test_shaft_bearings_use_the_same_color_as_ring_roller_bearings(self):
        for values in ({}, {'bearing_mode': 'shaft'}, {'bearing_mode': 'gear', 'bearing': '6001'},
                       {'eccentric_design': 'fdm_bolted'}):
            with self.subTest(values=values):
                d = generate('cycloidal', dict(values, ring_roller_bearing='692'))
                roller = next(p for p in d.parts if p.name.startswith('Roller_ring_'))
                bearings = [p for p in d.parts if p.name.startswith('Bearing_eccentric_') or p.catalog_code]
                self.assertTrue(bearings)
                self.assertTrue(all(p.color == roller.color for p in bearings))

    def test_cams_remain_essential_with_correct_motion_in_every_arrangement(self):
        for variant in ('single', 'dual'):
            for scheme in options('cycloidal'):
                with self.subTest(variant=variant, scheme=scheme):
                    design = generate('cycloidal', dict(variant=variant, io_scheme=scheme))
                    found = cams(design)
                    self.assertEqual(len(found), 1)
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
                    self.assertEqual(len(supports), 1 if variant == 'single' else 2)
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
                self.assertEqual((target/'assembly.step').read_text().count('CLOSED_SHELL('), 1)
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
