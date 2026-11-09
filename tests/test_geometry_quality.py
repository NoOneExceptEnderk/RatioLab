# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Nominal ownership, independent purposes and transactional quality failures."""
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from geometry import generate
from geometry_quality import normalize, with_quality, representation, part, project, report
from project_document import Document, validate_snapshot
from selected_export import subset
from solid_geometry import sampling_report
from stl_export import export, write_stl

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'webapp'))
from engine_bridge import Engine


class GeometryQualityTests(unittest.TestCase):
    def test_requests_are_positive_finite_lengths_without_a_micrometre_floor(self):
        self.assertEqual(normalize({'preview_mm':.1,'export_mm':1e-8})['export_mm'],1e-8)
        for value in [[],True,{'other':.01}, {'preview_mm':True},{'export_mm':0},
                      {'preview_mm':float('nan')},{'export_mm':float('inf')},{'preview_mm':'0.01'}]:
            with self.subTest(value=value),self.assertRaises(ValueError):normalize(value)

    def test_quality_only_views_share_the_nominal_description_and_exact_sources(self):
        d=generate('helical',{'module':2.,'_decimal_inputs':{'module':'2.00000000000000000001'}})
        old=deepcopy(d)
        with patch('geometry.generate',side_effect=AssertionError('Mechanical construction must not rerun')):
            q=with_quality(d,{'preview_mm':.1,'export_mm':.005})
            a=representation(q,'preview');b=representation(q,'export')
        self.assertIs(q.parts,d.parts);self.assertIs(q.analysis,d.analysis)
        self.assertIs(a.parts[0].outer,d.parts[0].outer);self.assertIs(b.parts[0].holes,d.parts[0].holes)
        self.assertEqual(a.parts[0].surface_tolerance_mm,.1);self.assertEqual(b.parts[0].surface_tolerance_mm,.005)
        self.assertEqual(d.parts,old.parts);self.assertEqual(d.values,old.values);self.assertEqual(d.analysis,old.analysis)
        self.assertEqual(q.values['_decimal_inputs']['module'],'2.00000000000000000001')

    def test_absent_quality_preserves_legacy_per_part_policy(self):
        d=generate('helical');d.parts[0].surface_tolerance_mm=.037
        for purpose in ('preview','export'):
            self.assertIs(part(d,d.parts[0],purpose),d.parts[0])
            self.assertEqual(sampling_report(part(d,d.parts[0],purpose))['requested_interpolation_mm'],.037)
        self.assertNotIn('quality',project(d))

    def test_selected_source_indices_survive_representation_selection(self):
        d=subset(generate('planetary'),[1,3],7)
        q=representation(with_quality(d,{'export_mm':.005}),'export')
        self.assertEqual(q.source_indices,[2,4]);self.assertEqual(q.export_scope,d.export_scope)
        self.assertEqual([p.name for p in q.parts],[p.name for p in d.parts])

    def test_preview_policy_never_changes_exported_stl(self):
        d=generate('helical');outputs=[]
        with tempfile.TemporaryDirectory() as tmp:
            for i,tolerance in enumerate((.1,.005)):
                q=with_quality(d,{'preview_mm':tolerance,'export_mm':.02})
                path,_=export(q,Path(tmp)/str(i));outputs.append(path.read_bytes())
        self.assertEqual(*outputs)

    def test_export_refines_without_changing_the_nominal_model(self):
        d=generate('helical');counts=[]
        with tempfile.TemporaryDirectory() as tmp:
            for i,tolerance in enumerate((.1,.005)):
                q=with_quality(d,{'preview_mm':.1,'export_mm':tolerance})
                path,_=export(q,Path(tmp)/str(i));counts.append(struct.unpack_from('<I',path.read_bytes(),80)[0])
        self.assertLess(*counts);self.assertEqual(d.parts[0].surface_tolerance_mm,.02)

    def test_reports_describe_each_actual_representation_and_explicit_limitations(self):
        d=generate('helical',quality={'preview_mm':.1,'export_mm':.005})
        a,b=report(d,'preview'),report(d,'export')
        self.assertLess(a['components'][0]['section_count'],b['components'][0]['section_count'])
        self.assertEqual(a['components'][0]['requested_interpolation_mm'],.1)
        self.assertEqual(b['components'][0]['requested_interpolation_mm'],.005)
        self.assertFalse(b['components'][0]['profile_error_globally_bounded'])

    def test_recovery_history_and_legacy_snapshots_roundtrip(self):
        d=generate('spur');s=dict(family=d.family,values={d.family:d.values},raw={})
        doc=Document(s);q=dict(s,quality={'preview_mm':.1,'export_mm':1e-7})
        self.assertEqual(validate_snapshot(q,['spur']),q)
        doc.record(q);self.assertEqual(doc.undo(),s);self.assertEqual(doc.redo(),q)
        with self.assertRaises(ValueError):validate_snapshot(dict(s,quality={'preview_mm':-1}),['spur'])

    def test_browser_quality_only_updates_retain_nominal_parts_plan_and_export_buffers(self):
        e=Engine();initial=e.call('generate',{'family':'helical','parameters':{}})
        source=e.design;plan=e.plan
        with patch('geometry.generate',side_effect=AssertionError('No reconstruction for quality')):
            result=e.call('quality',{'design_id':initial['design_id'],'quality':{'export_mm':.005}})
        self.assertTrue(result['buffers_retained']);self.assertFalse(e.buffers)
        self.assertIs(e.design.parts,source.parts);self.assertIs(e.plan,plan)
        q=e.call('quality',{'design_id':result['design_id'],'quality':{'preview_mm':.1,'export_mm':.005}})
        self.assertLess(q['triangle_count'],initial['triangle_count'])
        self.assertEqual(q['parts'][0]['preview_sampling']['requested_interpolation_mm'],.1)

    def test_browser_failed_preview_is_transactional_and_never_claims_a_coarse_success(self):
        e=Engine();initial=e.call('generate',{'family':'helical','parameters':{}})
        source=e.design;plan=e.plan;buffers=list(e.buffers)
        with self.assertRaisesRegex(ValueError,'section budget|250000 faces'):
            e.call('quality',{'design_id':initial['design_id'],'quality':{'preview_mm':1e-12}})
        self.assertIs(e.design,source);self.assertIs(e.plan,plan)
        self.assertEqual(e.design_id,initial['design_id']);self.assertEqual(e.buffers,buffers)

    def test_browser_project_import_and_export_match_native_export_policy(self):
        e=Engine();r=e.call('generate',{'family':'helical','parameters':{},'quality':{'preview_mm':.1,'export_mm':.005}})
        config=e.project();self.assertEqual(config['quality'],{'preview_mm':.1,'export_mm':.005})
        other=Engine();loaded=other.call('import_project',{'project':config})
        self.assertEqual(loaded['quality'],r['quality']);self.assertEqual(loaded['triangle_count'],r['triangle_count'])
        result=e.call('export',{'design_id':r['design_id'],'kind':'stl'})
        with ZipFile(BytesIO(e.buffers[result['buffer']])) as z:
            expected=z.read('model.stl');meta=json.loads(z.read('geometry-quality.json'))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'native.stl';write_stl(path,representation(e.design,'export').parts)
            self.assertEqual(path.read_bytes(),expected)
        self.assertEqual(meta['purpose'],'export');self.assertEqual(meta['components'][0]['requested_interpolation_mm'],.005)

    def test_failed_fine_export_leaves_no_published_files_or_nominal_changes(self):
        d=generate('helical',quality={'preview_mm':.1,'export_mm':1e-12})
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'section budget|250000 faces'):export(d,Path(tmp)/'model')
            self.assertEqual(list(Path(tmp).iterdir()),[])
        self.assertEqual(d.parts[0].surface_tolerance_mm,.02)

    def test_browser_document_quality_history_recovery_and_exact_raw_inputs(self):
        import os,shutil,subprocess
        from engine_bridge import schema
        node=os.environ.get('RATIOLAB_TEST_NODE') or shutil.which('node')
        if not node:self.skipTest('Node.js required')
        script=Path(__file__).with_name('webapp_quality.mjs')
        result=subprocess.run([node,str(script)],input=json.dumps(schema('helical')),text=True,capture_output=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(json.loads(result.stdout)['raw_precision'])

    def test_headless_project_quality_persistence_update_and_history(self):
        from ratiolab_agent import AgentService
        with tempfile.TemporaryDirectory() as tmp:
            service=AgentService(tmp)
            try:
                p=service.project_create('helical',quality={'preview_mm':.1,'export_mm':.005})
                source=service.projects[p['handle']].design
                with patch('ratiolab_agent.generate',side_effect=AssertionError('No reconstruction for quality')):
                    q=service.project_update(p['handle'],p['revision'],quality={'export_mm':.01})
                self.assertIs(service.projects[p['handle']].design.parts,source.parts)
                u=service.project_history(q['handle'],q['revision'],'undo')
                self.assertEqual(u['quality'],p['quality'])
                saved=service.project_save(u['handle'],u['revision'],'quality.json')
                opened=service.project_open('quality.json');self.assertEqual(opened['quality'],p['quality'])
            finally:service.close()


if __name__=='__main__':unittest.main()
