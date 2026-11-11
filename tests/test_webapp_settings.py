# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Shared browser settings, read-only error budgets and native UI catalog parity."""
from copy import deepcopy
import itertools
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'webapp'))
import engine_bridge
from geometry_quality import PRESETS,deviation,with_quality
import theme_preferences as themes
import mouse_navigation as mouse

class WebSettingsTests(unittest.TestCase):
    def test_browser_settings_notes_are_available_in_all_nine_languages(self):
        catalog=json.loads((ROOT/'src/ratiolab_resources/ui-translations.json').read_text())
        self.assertEqual(len(catalog['translations']),9)
        messages=['Browser-reserved shortcuts use the available equivalents shown below. Closing windows remains a browser action.',
            'CAD connections and automatic application updates are available in the desktop program.',
            'View shortcuts apply when the 3D view has keyboard focus. Text editing keeps its own shortcuts.',
            'Release notes','Restore preset binding','Restore preset color','Two-key sequence','Unassigned']
        for language,values in catalog['translations'].items():
            for message in messages:self.assertTrue(values.get(message),(language,message))

    def test_generated_catalog_matches_reviewed_desktop_catalogs(self):
        result=subprocess.run([sys.executable,str(ROOT/'scripts/sync-web-settings.py'),'--check'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_bounds_keep_nominal_design_motion_lease_buffers_and_metadata(self):
        for family in ('spur','helical','double','parallel','rack','harmonic'):
            with self.subTest(family=family):
                engine=engine_bridge.Engine();result=engine.call('generate',dict(family=family,parameters={}))
                source,parts,plan=engine.design,engine.design.parts,engine.plan
                values=deepcopy(source.values);buffers=tuple(engine.buffers);lease=engine.design_id
                before=deepcopy(engine.project())
                quality=dict(preview_mm=.1,export_mm=.005)
                response=engine.call('precision_bounds',dict(design_id=lease,quality=quality))
                self.assertIs(engine.design,source);self.assertIs(source.parts,parts);self.assertIs(engine.plan,plan)
                self.assertEqual(source.values,values);self.assertEqual(engine.design_id,lease)
                self.assertEqual(tuple(engine.buffers),buffers);self.assertEqual(engine.project(),before)
                self.assertEqual(response['design_id'],result['design_id'])
                for name,value in PRESETS:
                    expected=deviation(with_quality(source,dict(preview_mm=value,export_mm=value)),'export')
                    for key in ('interpolation_mm','model_mm','reason','scope','output_bounds'):
                        self.assertEqual(response['rows'][name].get(key),expected.get(key))
                    if expected['interpolation_mm'] is None:self.assertIsNone(response['rows'][name]['interpolation_text'])
                    else:self.assertTrue(response['rows'][name]['interpolation_text'].startswith('≤ '))
                if family in ('spur','helical','double'):
                    self.assertGreater(response['rows']['Fine']['model_mm'],.005)
                else:
                    self.assertIsNone(response['rows']['Fine']['model_mm'])
                    self.assertIsNone(response['rows']['Fine']['model_text'])
                self.assertEqual(response['rows']['Preview']['interpolation_mm'],deviation(with_quality(source,quality),'preview')['interpolation_mm'])
                self.assertEqual(response['rows']['Export']['model_mm'],deviation(with_quality(source,quality),'export')['model_mm'])

    def test_invalid_or_stale_bounds_cannot_replace_or_clear_the_current_model(self):
        engine=engine_bridge.Engine();result=engine.call('generate',dict(family='helical',parameters={}))
        source=engine.design;buffers=tuple(engine.buffers)
        for args in (dict(design_id=-1),dict(design_id=result['design_id'],quality=dict(preview_mm=-1))):
            with self.assertRaises((ValueError,engine_bridge.BridgeError)):engine.call('precision_bounds',args)
            self.assertIs(engine.design,source);self.assertEqual(tuple(engine.buffers),buffers)

    def test_browser_theme_keyboard_and_every_mouse_chord_match_shared_controls(self):
        node=os.environ.get('RATIOLAB_TEST_NODE') or shutil.which('node') or shutil.which('nodejs')
        if not node:self.skipTest('Node.js is required for browser settings checks')
        config=themes.defaults();palettes=[]
        for mode in ('dark','light'):
            for preset in themes.PRESETS:
                config['active'][mode]=preset
                for group,role,value in (('colors','accent','#abcdef'),('colors','surface','#123456'),('viewport','grid','#445566')):
                    config=themes.change_color(config,mode,group,role,value)
                palettes.append(dict(mode=mode,config=deepcopy(config),colors=themes.palette(mode,config),viewport=themes.viewport(mode,config),exported=themes.export_theme(mode,config)))
        chords=[]
        for profile,bits,shift,control,alt,pan in itertools.product(mouse.PROFILES,range(8),[False,True],[False,True],[False,True],[False,True]):
            dom=(bits&1)|(4 if bits&2 else 0)|(2 if bits&4 else 0)
            chords.append(dict(profile=profile,bits=dom,shift=shift,control=control,alt=alt,panMode=pan,expected=mouse.drag_mode(profile,bits,shift=shift,control=control,alt=alt,pan_mode=pan)))
        result=subprocess.run([node,'--experimental-vm-modules',str(ROOT/'tests/webapp_settings.mjs')],input=json.dumps(dict(palettes=palettes,chords=chords)),capture_output=True,text=True,timeout=45)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
