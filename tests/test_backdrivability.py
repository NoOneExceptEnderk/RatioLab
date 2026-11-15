# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Fixed worm drive, legacy project imports and strain-wave assessment."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from geometry import generate
from kinematics import options
from project_document import validate_snapshot
from ratiolab_agent import AgentError, AgentService


class BackdrivabilityTests(unittest.TestCase):
    def test_worm_uses_fixed_roles_and_rejects_wheel_input(self):
        self.assertEqual(options('worm'), {'forward': 'Worm → Wheel'})
        for variant in ('za', 'zi'):
            with self.subTest(variant=variant):
                design = generate('worm', dict(variant=variant, input_rpm=60))
                self.assertEqual(design.values['io_scheme'], 'forward')
                self.assertNotIn('backdrivability', design.analysis)
                self.assertEqual([p.port['role'] for p in design.parts], ['input', 'output'])
                with self.assertRaisesRegex(ValueError, 'worm input and wheel output only'):
                    generate('worm', dict(variant=variant, io_scheme='reverse'))
        with self.assertRaises(ValueError):
            generate('worm', dict(worm_static_friction=0))

    def test_saved_api_project_migrates_and_live_requests_reject_reverse(self):
        with TemporaryDirectory() as folder:
            service = AgentService(folder)
            self.addCleanup(service.close)
            discovery = service.discover('worm')
            self.assertNotIn('worm_static_friction', discovery['options'])
            project = Path(folder)/'old.json'
            old = dict(format='solidcraft-riduttori/1', family='worm',
                       parameters=dict(io_scheme='reverse', worm_static_friction=.05, input_rpm=123))
            project.write_text(json.dumps(old))
            opened = service.project_open('old.json')
            self.assertEqual(opened['parameters']['io_scheme'], 'forward')
            self.assertEqual(opened['parameters']['input_rpm'], 123)
            self.assertNotIn('worm_static_friction', opened['parameters'])
            self.assertEqual(json.loads(project.read_text()), old)
            with self.assertRaises(AgentError):
                service.project_create('worm', dict(io_scheme='reverse'))
            with self.assertRaises(AgentError):
                service.project_update(opened['handle'], opened['revision'], dict(io_scheme='reverse'))

    def test_browser_import_migrates_and_live_requests_reject_reverse(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'webapp'))
        self.addCleanup(sys.path.pop, 0)
        from engine_bridge import dispatch
        parameters = dict(io_scheme='reverse', worm_static_friction=.05, input_rpm=123)
        def call(method, args):
            return json.loads(dispatch(method, json.dumps(args)))
        self.assertFalse(call('generate', dict(family='worm', parameters=parameters))['ok'])
        result = call('import_project', dict(project=dict(format='solidcraft-riduttori/1',
                      family='worm', parameters=parameters)))
        self.assertTrue(result['ok'], result)
        self.assertTrue(result['result']['migrated_worm_drive'])
        self.assertEqual(result['result']['values']['io_scheme'], 'forward')
        self.assertNotIn('worm_static_friction', result['result']['values'])

    def test_desktop_recovery_migrates_an_inactive_worm_draft(self):
        snapshot = dict(family='parallel', values={'parallel': {}, 'worm': {
                        'io_scheme': 'reverse', 'worm_static_friction': .05}},
                        raw={'worm': {'width': '10.00', 'worm_static_friction': '0.05'}},
                        automatic={'worm': ['worm_static_friction']})
        migrated = validate_snapshot(snapshot, {'worm', 'parallel'})
        self.assertEqual(migrated['values']['worm'], {'io_scheme': 'forward'})
        self.assertEqual(migrated['raw']['worm'], {'width': '10.00'})
        self.assertEqual(migrated['automatic']['worm'], [])
        self.assertEqual(snapshot['values']['worm']['io_scheme'], 'reverse')

    def test_no_harmonic_family_ban_or_invented_friction(self):
        for scheme in ('wave_flex_circular', 'wave_circular_flex', 'flex_wave_circular',
                       'circular_wave_flex', 'flex_circular_wave', 'circular_flex_wave'):
            d = generate('harmonic', dict(io_scheme=scheme))
            q = d.analysis['backdrivability']
            self.assertTrue(q['allowed'])
            self.assertEqual(q['status'], 'not_evaluated' if scheme.startswith('wave_') else 'indeterminate')
            if q['reverse_requested']:
                self.assertIn('breakaway torque', q['message'])
