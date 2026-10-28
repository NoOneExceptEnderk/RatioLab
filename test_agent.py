# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Headless contract, geometry, persistence and publication safety regressions."""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Event, Thread
import unittest
from unittest.mock import patch
from xml.etree import ElementTree

import ratiolab_agent as agent
from geometry import FAMILIES, VARIANTS, generate


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='RatioLab agent Ω ')
        self.root = Path(self.folder.name)
        self.service = agent.AgentService(self.root)
        self.addCleanup(self.folder.cleanup)
        self.addCleanup(self.service.close)

    def create(self, family='spur', **parameters):
        return self.service.project_create(family, parameters)

    @staticmethod
    def ref(project):
        return dict(handle=project['handle'], revision=project['revision'])

    def assertCode(self, code, function, *args, **kwargs):
        with self.assertRaises(agent.AgentError) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_discovery_all_families_and_variant_canonical_roundtrip(self):
        self.assertEqual({r['id'] for r in self.service.discover()['families']}, set(FAMILIES))
        for family in FAMILIES:
            for variant in VARIANTS.get(family, {None: None}):
                with self.subTest(family=family, variant=variant):
                    params = dict(variant=variant) if variant else {}
                    details = self.service.discover(family, variant)
                    project = self.create(family, **params)
                    unchanged = self.service.project_update(**self.ref(project), parameters={})
                    self.assertEqual(unchanged['parameters'],project['parameters'])
                    self.assertEqual(unchanged['revision'],0)
                    self.assertEqual(details['defaults'],project['parameters'])
                    self.assertIn('bearing_mode',details['options'])
                    if family not in ('spur','helical','double'):
                        self.assertTrue(details['io_schemes'])
                    self.service.project_close(**self.ref(unchanged))

    def test_unknown_nonfinite_wrong_types_and_bad_geometry_are_atomic(self):
        project = self.create()
        for parameters in [dict(typo_width=12),dict(width=float('nan')),dict(width=float('inf')),
                           dict(width=True),dict(width='12'),dict(width=10**1000),dict(width=-1),
                           dict(hardware_bolts='true'),dict(teeth=24.5),dict(bore=99)]:
            with self.subTest(parameters=str(parameters)[:100]):
                with self.assertRaises(agent.AgentError):
                    self.service.project_update(**self.ref(project),parameters=parameters)
                self.assertEqual(self.service.project_list()['projects'],[project])
        self.assertCode('invalid_arguments',self.service.project_create,'not-a-family')

    def test_discovery_fdm_preset_and_linked_defaults_match_the_generator(self):
        discovery = self.service.discover('cycloidal',parameters=dict(eccentric_design='fdm_bolted'))
        values = discovery['defaults']
        self.assertEqual(values['input_shaft'],17)
        self.assertEqual(values['width'],16)
        self.assertAlmostEqual(values['bore'],32.2)
        fields = {field['name']:field for field in discovery['fields']}
        self.assertEqual(fields['input_shaft']['default'],17)
        self.assertEqual(fields['input_shaft']['nominal_default'],4)
        project = self.create('cycloidal',eccentric_design='fdm_bolted')
        self.assertEqual(project['parameters'],values)
        self.assertEqual(discovery['named_presets']['fdm_bolted']['canonical_defaults'],values)

    def test_document_history_revision_and_external_file_conflicts(self):
        project = self.create()
        changed = self.service.project_update(**self.ref(project),parameters=dict(width=12))
        self.assertEqual(changed['revision'],1)
        self.assertTrue(changed['dirty'])
        self.assertCode('stale_revision',self.service.bom,**self.ref(project))
        undone = self.service.project_history(**self.ref(changed),action='undo')
        self.assertEqual(undone['parameters']['width'],10)
        redone = self.service.project_history(**self.ref(undone),action='redo')
        self.assertEqual(redone['parameters']['width'],12)
        saved = self.service.project_save(**self.ref(redone),path='progetti qualità/ruota.json')
        self.assertFalse(saved['dirty'])
        data = json.loads((self.root/saved['path']).read_text(encoding='utf-8'))
        self.assertEqual(data['format'],'solidcraft-riduttori/1')
        reopened = self.service.project_open(saved['path'])
        self.assertEqual(reopened['parameters'],saved['parameters'])
        self.assertCode('already_exists',self.service.project_save,**self.ref(saved),path=saved['path'])
        (self.root/saved['path']).write_text('{}',encoding='utf-8')
        self.assertCode('conflict',self.service.project_save,**self.ref(saved),path=saved['path'],overwrite=True)
        self.assertEqual((self.root/saved['path']).read_text(),'{}')
        self.assertCode('conflict',self.service.project_save,**self.ref(saved),path='missing.json',overwrite=True)
        self.service.project_close(**self.ref(saved))
        self.assertCode('unknown_project',self.service.bom,**self.ref(saved))

    def test_explicit_overwrite_requires_owned_unchanged_path(self):
        project = self.create()
        saved = self.service.project_save(**self.ref(project),path='gear.json')
        changed = self.service.project_update(**self.ref(saved),parameters=dict(width=11))
        final = self.service.project_save(**self.ref(changed),path='gear.json',overwrite=True)
        self.assertEqual(json.loads((self.root/'gear.json').read_text())['parameters']['width'],11)
        (self.root/'unowned.json').write_text('{}')
        self.assertCode('conflict',self.service.project_save,**self.ref(final),path='unowned.json',overwrite=True)
        self.assertEqual((self.root/'unowned.json').read_text(),'{}')

    def test_paths_reject_traversal_absolute_windows_devices_symlinks_and_hardlinks(self):
        project = self.create()
        for name in ['../escape.json','folder/../escape.json','/absolute.json','C:/escape.json',
                     'folder\\escape.json','folder//escape.json','./escape.json','CON.json','nul/a.json',
                     'trailing./file.json','.ratiolab-agent-private/config.json','a:stream.json']:
            with self.subTest(name=name):
                self.assertCode('unsafe_path',self.service.project_save,**self.ref(project),path=name)
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__('shutil').rmtree(outside))
        try:
            (self.root/'linked').symlink_to(outside,target_is_directory=True)
        except (OSError,NotImplementedError):
            pass
        else:
            self.assertCode('unsafe_path',self.service.project_save,**self.ref(project),path='linked/escape.json')
            self.assertEqual(list(outside.iterdir()),[])
        saved = self.service.project_save(**self.ref(project),path='original.json')
        try:
            os.link(self.root/'original.json',self.root/'alias.json')
        except OSError:
            pass
        else:
            self.assertCode('unsafe_path',self.service.project_open,'alias.json')

    @unittest.skipUnless(hasattr(os,'mkfifo'),'POSIX FIFO safety')
    def test_fifo_is_rejected_without_open_or_waiting(self):
        os.mkfifo(self.root/'special.json')
        with patch.object(agent.os,'open',side_effect=AssertionError('FIFO must never be opened')):
            self.assertCode('unsafe_path',self.service.project_open,'special.json')

    def test_import_only_bounded_utf8_complete_json(self):
        for index, data in enumerate([b'not json',b'\xff',b'[]',b'{"format":"evil"}',
            b'{"format":"solidcraft-riduttori/1","family":"spur","parameters":{"width":NaN}}',
            agent.json_bytes(dict(format=agent.CONFIG_FORMAT,family='spur',parameters={},selected_export={'source_indices':[2]}))]):
            path=f'invalid{index}.json';(self.root/path).write_bytes(data)
            with self.subTest(index=index),self.assertRaises(agent.AgentError):self.service.project_open(path)
        self.assertCode('invalid_format',self.service.project_open,'model.step')
        (self.root/'huge.json').write_bytes(b' '*(self.service.limits.input_bytes+1))
        self.assertCode('resource_limit',self.service.project_open,'huge.json')
        self.assertEqual(self.service.project_list()['projects'],[])

    def test_selected_second_component_has_exact_name_index_and_scope_in_every_output(self):
        project = self.create('parallel')
        expected = generate('parallel').parts[1].name
        description = self.service.project_describe(**self.ref(project),components=[2])
        self.assertEqual([p['index'] for p in description['components']],[2])
        self.assertEqual([p['name'] for p in description['components']],[expected])
        self.assertEqual(description['export_scope']['index_base'],1)
        result = self.service.export(**self.ref(project),path='selected Ω',kind='package',components=[2])
        folder = self.root/result['path']
        scope = json.loads((folder/'selection.json').read_text())
        self.assertEqual(scope['source_indices'],[2]);self.assertEqual(scope['index_base'],1)
        manifest = json.loads((folder/'manifest.json').read_text())
        self.assertEqual(manifest['index_base'],1);self.assertFalse(manifest['complete_assembly'])
        self.assertEqual(manifest['scope']['components'],[dict(source_index=2,name=expected)])
        self.assertFalse((folder/'preview.png').exists())
        self.assertEqual(json.loads((folder/'model.config.json').read_text())['selected_export']['index_base'],1)
        stepinfo=json.loads((folder/'step-info.json').read_text())
        self.assertEqual(stepinfo['scope']['source_indices'],[2])
        profile=json.loads((folder/'profiles.json').read_text())
        self.assertEqual([p['index'] for p in profile['components']],[2])
        bom=json.loads((folder/'model.bom.json').read_text())
        self.assertEqual([i for row in bom['rows'] for i in row['source_indices']],[2])
        self.verify_manifest(folder)
        commands = json.loads((folder/'model.script.json').read_text())['commands']
        for command in commands:
            if command['command']=='file.insert_step':
                self.assertFalse(Path(command['params']['path']).is_absolute())
                self.assertTrue((folder/command['params']['path']).is_file())

    def verify_manifest(self, folder):
        manifest=json.loads((folder/'manifest.json').read_text())
        self.assertTrue(manifest['complete'])
        for record in manifest['files']:
            data=(folder/record['path']).read_bytes()
            self.assertEqual(len(data),record['bytes'])
            self.assertEqual(hashlib.sha256(data).hexdigest(),record['sha256'])

    def test_real_formats_and_existing_exports_untouched(self):
        project=self.create()
        for kind in ('step','stl','svg','dxf','profiles'):
            with self.subTest(kind=kind):
                result=self.service.export(**self.ref(project),path=kind,kind=kind)
                folder=self.root/result['path'];self.verify_manifest(folder)
                if kind=='step':self.assertTrue((folder/'assembly.step').read_text().startswith('ISO-10303-21;'))
                elif kind=='stl':self.assertGreater((folder/'model.stl').stat().st_size,84)
                else:
                    svg=list((folder/'profiles').glob('*.svg'));self.assertTrue(svg)
                    for path in svg:ElementTree.parse(path)
                    self.assertTrue(list((folder/'profiles').glob('*.dxf')))
                (folder/'sentinel').write_text('keep')
                self.assertCode('already_exists',self.service.export,**self.ref(project),path=kind,kind=kind)
                self.assertEqual((folder/'sentinel').read_text(),'keep')

    def test_cancelled_generation_save_and_export_publish_nothing(self):
        cancelled=Event();real_generate=agent.generate
        def stop_generation(*args):
            result=real_generate(*args);cancelled.set();return result
        with patch.object(agent,'generate',side_effect=stop_generation):
            self.assertCode('cancelled',self.service.project_create,'spur',cancel=cancelled)
        self.assertEqual(self.service.project_list()['projects'],[])
        project=self.create();cancelled.clear();real_fsync=os.fsync
        def stop_save(fd):real_fsync(fd);cancelled.set()
        with patch.object(agent.os,'fsync',side_effect=stop_save):
            self.assertCode('cancelled',self.service.project_save,**self.ref(project),path='cancel.json',cancel=cancelled)
        self.assertFalse((self.root/'cancel.json').exists())
        import cad_export
        real_write=cad_export.write_files;cancelled.clear()
        def stop_export(*args):result=real_write(*args);cancelled.set();return result
        with patch.object(cad_export,'write_files',side_effect=stop_export):
            self.assertCode('cancelled',self.service.export,**self.ref(project),path='cancelled',kind='step',cancel=cancelled)
        self.assertFalse((self.root/'cancelled').exists())
        self.assertFalse(list(self.root.glob('.*.export-lock')))
        self.assertEqual(self.service.project_list()['projects'],[project])

    def test_failed_export_removes_staging_and_budget_excess_is_not_published(self):
        project=self.create()
        import cad_export
        with patch.object(cad_export,'write_files',side_effect=ValueError('fixture failure')):
            with self.assertRaises(ValueError):self.service.export(**self.ref(project),path='failed',kind='step')
        self.assertFalse((self.root/'failed').exists())
        self.service.limits=replace(self.service.limits,export_bytes=1)
        self.assertCode('resource_limit',self.service.export,**self.ref(project),path='too large',kind='stl')
        self.assertFalse((self.root/'too large').exists())

    def test_concurrent_update_detects_revision_change_after_generation(self):
        project=self.create();started=Event();release=Event();real=agent.generate;errors=[]
        def controlled(family,values):
            if values['width']==11:started.set();release.wait(5)
            return real(family,values)
        def edit():
            try:self.service.project_update(**self.ref(project),parameters=dict(width=11))
            except agent.AgentError as error:errors.append(error.code)
        with patch.object(agent,'generate',side_effect=controlled):
            worker=Thread(target=edit);worker.start();self.assertTrue(started.wait(3))
            changed=self.service.project_update(**self.ref(project),parameters=dict(width=12))
            release.set();worker.join(5)
        self.assertEqual(errors,['stale_revision']);self.assertEqual(changed['parameters']['width'],12)
        self.assertEqual(self.service.project_list()['projects'],[changed])

    def test_real_search_and_cancelled_or_bounded_interference(self):
        project=self.create('parallel')
        report=self.service.search(**self.ref(project),axes=dict(wheel=[60,66]),settings=dict(target=3,tolerance_percent=0))
        self.assertTrue(report['complete']);self.assertEqual(len(report['search']['proposals']),1)
        self.assertEqual(report['search']['proposals'][0]['ratio'],-3)
        partial=self.service.search(**self.ref(project),axes=dict(wheel=[60,66]),settings=dict(max_candidates=1))
        self.assertFalse(partial['complete']);self.assertIn('budget',partial['search']['reason'])
        stop=Event();stop.set()
        checked=self.service.interference(**self.ref(project),cancel=stop)
        self.assertFalse(checked['complete']);self.assertTrue(checked['analysis']['cancelled'])
        single=self.create()
        checked=self.service.interference(**self.ref(single),settings=dict(max_poses=1,max_seconds=1))
        self.assertEqual(checked['revision'],0)
        self.assertIn('coverage_complete',checked['analysis'])
        for settings in [dict(max_seconds=31),dict(max_poses=49),dict(max_triangles=120001),dict(step_degrees=True)]:
            with self.subTest(settings=settings),self.assertRaises(agent.AgentError):
                self.service.interference(**self.ref(project),settings=settings)
        for settings in [dict(max_candidates=1001),dict(max_results=51),dict(max_seconds=31),dict(tolerance_percent=True)]:
            with self.subTest(settings=settings),self.assertRaises(agent.AgentError):
                self.service.search(**self.ref(project),axes=dict(wheel=[60]),settings=settings)

    def test_project_limit_and_no_gtk_preferences_or_network_import(self):
        self.service.limits=replace(self.service.limits,projects=1)
        self.create()
        self.assertCode('resource_limit',self.service.project_create,'spur')
        code='import sys; import ratiolab_agent,ratiolab_mcp; assert not any(x in sys.modules for x in ("gi","cairo","app","workspace_ui","connection","app_paths"))'
        subprocess.run([sys.executable,'-c',code],check=True,cwd=self.root,
                       env=dict(os.environ,PYTHONPATH=str(Path(agent.__file__).resolve().parent)))


if __name__=='__main__':unittest.main()
