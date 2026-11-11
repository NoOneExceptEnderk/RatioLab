# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Nominal provenance, company edits, invalidation and lossless project exchange."""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import component_sheets as sheets
from geometry import generate, FAMILIES, circle
from geometry_quality import project, with_quality
from project_document import Document, Store, validate_snapshot


def metadata(design, index=0):
    draft = sheets.draft(design, index)
    draft['checks'][0].update(lower='9.9', upper='10.1', instrument='MIC-007', datum='Drawing A')
    return sheets.apply(design, index, {}, {'company':'Officina Ω & Figli', 'order':'C-123'},
        {'code':'GEAR-01', 'revision':'B', 'operations':'Company operation\nInspect & deburr'}, draft['checks'])


class ComponentSheetTests(unittest.TestCase):
    def test_each_component_keeps_its_own_fields_and_company_is_shared(self):
        design=generate('parallel');first=metadata(design);old=deepcopy(first)
        draft=sheets.draft(design,1,first)
        self.assertEqual(draft['fields'],{})
        self.assertEqual(draft['company'],first['company'])
        second=sheets.apply(design,1,first,draft['company'],{'code':'WHEEL-02'},draft['checks'])
        self.assertEqual(second['components'][sheets.component_key(design,0)],old['components'][sheets.component_key(design,0)])
        self.assertEqual(sheets.report(design,1,second)['fields']['code'],'WHEEL-02')
        self.assertEqual(first,old)

    def test_browser_document_keeps_fields_through_edits_recovery_and_new(self):
        node = os.environ.get('RATIOLAB_TEST_NODE') or shutil.which('node')
        if not node:self.skipTest('Node.js required for browser document state')
        root=Path(__file__).resolve().parents[1]
        completed=subprocess.run([node,'--experimental-vm-modules',str(root/'tests/webapp_component_sheets.mjs')],
            input=json.dumps(metadata(generate('spur'))),text=True,capture_output=True,timeout=20)
        self.assertEqual(completed.returncode,0,completed.stdout+completed.stderr)

    def test_nominal_dimensions_are_component_specific_and_only_use_circle_provenance(self):
        design = generate('parallel')
        a, b = (sheets.automatic_checks(p) for p in design.parts[:2])
        tip = lambda rows:next(r['nominal'] for r in rows if r['id']=='auto:tip')
        self.assertNotEqual(tip(a),tip(b))
        part = deepcopy(design.parts[0])
        part.holes = [list(circle(3))]
        self.assertFalse(any(r['id'].startswith('auto:hole') for r in sheets.automatic_checks(part)))
        part.holes = [circle(3)]
        part.holes[0][0] = (99,99)
        self.assertFalse(any(r['id'].startswith('auto:hole') for r in sheets.automatic_checks(part)))

    def test_nominals_and_methods_cannot_be_replaced_by_saved_or_gui_text(self):
        design = generate('spur');saved = metadata(design)
        key = sheets.component_key(design,0)
        row = next(r for r in saved['components'][key]['checks'] if r['id']=='auto:span')
        row.update(nominal='999', method='Wrong span setup')
        report = sheets.report(design,0,saved)
        actual = next(r for r in report['checks'] if r['id']=='auto:span')
        self.assertAlmostEqual(float(actual['nominal']),15.3624461217)
        self.assertIn('k = 3',actual['method'])
        self.assertNotIn('999',actual['nominal'])

    def test_geometry_changes_require_review_but_quality_and_speed_do_not(self):
        design = generate('spur');saved = metadata(design)
        self.assertFalse(sheets.draft(with_quality(design,{'export_mm':.005}),0,saved)['stale'])
        self.assertFalse(sheets.draft(generate('spur',{'input_rpm':777}),0,saved)['stale'])
        changed = generate('spur',{'width':12})
        self.assertTrue(sheets.draft(changed,0,saved)['stale'])
        with self.assertRaises(ValueError):sheets.report(changed,0,saved)
        new = sheets.draft(changed,0,saved)
        self.assertEqual(new['fields']['revision'],'B')
        self.assertEqual(new['checks'][0]['nominal'],'12')
        reviewed = sheets.apply(changed,0,saved,new['company'],new['fields'],new['checks'])
        self.assertEqual(sheets.report(changed,0,reviewed)['checks'][0]['nominal'],'12')

    def test_validation_rejects_unsafe_or_ambiguous_limits_without_mutating_input(self):
        design=generate('spur');saved=metadata(design);before=deepcopy(saved)
        for update in ({'lower':'NaN'}, {'lower':'12','upper':'11'}, {'upper':'Infinity'}, {'label':''}):
            broken=deepcopy(saved)
            broken['components'][sheets.component_key(design,0)]['checks'][0].update(update)
            with self.subTest(update=update),self.assertRaises(ValueError):sheets.normalize(broken)
        self.assertEqual(saved,before)
        draft=sheets.draft(design,0,saved)
        draft['checks'].append(dict(draft['checks'][0]))
        with self.assertRaises(ValueError):sheets.apply(design,0,saved,{},draft['fields'],draft['checks'])

    def test_history_recovery_and_legacy_defaults_are_lossless(self):
        design=generate('spur');state=dict(family='spur',values={'spur':design.values},raw={})
        doc=Document(state);next_state=dict(state,component_sheets=metadata(design))
        doc.record(next_state)
        self.assertTrue(doc.dirty)
        self.assertNotIn('component_sheets',doc.undo())
        self.assertEqual(doc.redo(),next_state)
        with TemporaryDirectory() as folder:
            store=Store(folder);store.checkpoint(doc)
            restored=store.read_recovery(store.session,FAMILIES)
            self.assertEqual(restored.current,next_state)
            self.assertEqual(restored.undo(),state)
        self.assertEqual(validate_snapshot(state,FAMILIES),state)

    def test_browser_and_agent_open_update_history_and_save_preserve_company_fields(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'webapp'))
        import engine_bridge
        from ratiolab_agent import AgentService
        design=generate('spur');design.component_sheets=metadata(design)
        config=project(design);bridge=engine_bridge.Engine()
        imported=bridge.call('import_project',{'project':config})
        self.assertEqual(imported['component_sheets'],design.component_sheets)
        self.assertEqual(bridge.project()['component_sheets'],design.component_sheets)
        changed=bridge.call('generate',dict(family='spur',parameters={'width':12},component_sheets=design.component_sheets))
        self.assertTrue(sheets.draft(bridge.design,0,changed['component_sheets'])['stale'])
        with TemporaryDirectory() as folder:
            root=Path(folder);(root/'in.json').write_text(json.dumps(config))
            service=AgentService(root)
            try:
                opened=service.project_open('in.json')
                ref=lambda obj:dict(handle=obj['handle'],revision=obj['revision'])
                updated=service.project_update(**ref(opened),parameters={'width':12})
                undone=service.project_history(**ref(updated),action='undo')
                service.project_save(**ref(undone),path='out.json')
                self.assertEqual(json.loads((root/'out.json').read_text())['component_sheets'],config['component_sheets'])
            finally:service.close()

    def test_supported_defaults_do_not_fabricate_measurements_for_other_families(self):
        for family in FAMILIES:
            design=generate(family)
            for part in design.parts:
                rows=sheets.automatic_checks(part)
                self.assertLessEqual(len(rows),sheets.MAX_CHECKS)
                if not part.profile_metadata.get('tooth_profile',{}).get('measurement_geometry'):
                    self.assertFalse(any(r['id'] in ('auto:tip','auto:span','auto:gauges') for r in rows))


class PdfSheetTests(unittest.TestCase):
    def test_all_app_languages_translate_messages_but_preserve_company_data(self):
        import sheet_pdf
        from ui_language import catalog,translate
        design=generate('spur');saved=metadata(design)
        draft=sheets.draft(design,0,saved)
        draft['company']['company']='Company - Ω workshop'
        draft['fields'].update(code='Material',operations='Inspection',notes='Company specifications')
        draft['checks'][0].update(method='Review',instrument='Value',datum='Project')
        draft['checks'].append(dict(id='custom:literal',label='Review',nominal='1.25',unit='mm',lower='1.2',upper='1.3',method='Symmetric flat jaws; k = 3',instrument='Company',datum='Minimum'))
        saved=sheets.apply(design,0,saved,draft['company'],draft['fields'],draft['checks'])
        report=sheets.report(design,0,saved,'Company.json',7);before=deepcopy(report)
        with TemporaryDirectory() as folder:
            for language in catalog()['languages']:
                with self.subTest(language=language):
                    path=sheet_pdf.export(report,Path(folder)/language,language=language)
                    snapshot=json.loads((path/'sheet-data.json').read_text())
                    self.assertEqual(snapshot['language'],language)
                    self.assertEqual(snapshot['company'],report['company'])
                    self.assertEqual(snapshot['fields'],report['fields'])
                    self.assertEqual(snapshot['checks'],report['checks'])
                    document=sheet_pdf.Document(Path(folder)/f'{language}.pdf','Component inspection sheet',snapshot)
                    try:
                        self.assertEqual(document.title,translate('Component inspection sheet',language))
                        self.assertEqual(document.characteristic(snapshot['checks'][-1]),'Review')
                        self.assertEqual(document.method(snapshot['checks'][-1]),'Symmetric flat jaws; k = 3')
                        self.assertEqual(document.method(snapshot['checks'][0]),'Review')
                        automatic=next(row for row in snapshot['checks'] if row['id']=='auto:span')
                        self.assertEqual(document.method(automatic),translate(automatic['method'],language))
                        self.assertEqual(document.characteristic(snapshot['checks'][0]),translate('Axial length (local Z)',language))
                    finally:document.finish()
            self.assertEqual(report,before)
            for language in ('xx','ITALIAN',None):
                with self.subTest(invalid_language=language),self.assertRaises(ValueError):
                    sheet_pdf.export(report,Path(folder)/'invalid',language=language)
            self.assertFalse((Path(folder)/'invalid').exists())

    def test_packaged_fonts_do_not_paint_wrapped_words_over_the_following_line(self):
        if not shutil.which('pdftotext'):self.skipTest('Poppler required for PDF text-position verification')
        from xml.etree import ElementTree as ET
        from xml.sax.saxutils import escape
        root=Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as folder:
            folder=Path(folder);config=folder/'fonts.conf';pdf=folder/'paragraph.pdf'
            config.write_text('<fontconfig><dir>'+escape(str(root/'packaging/fonts'))+'</dir><cachedir>'+escape(str(folder/'cache'))+'</cachedir><alias><family>sans</family><prefer><family>DejaVu Sans</family></prefer></alias></fontconfig>')
            script="""from sheet_pdf import Document
import sys
doc=Document(sys.argv[1],'Inspection',{'fields':{},'source_name':'Part'})
doc.paragraph('Absolute limits in the indicated unit. Blank limits mean acceptance is undefined. Results and disposition are recorded by the inspector; no automatic pass/fail or certificate is generated.')
doc.finish()
"""
            completed=subprocess.run([sys.executable,'-c',script,str(pdf)],env=dict(os.environ,FONTCONFIG_FILE=str(config)),text=True,capture_output=True,timeout=20)
            self.assertEqual(completed.returncode,0,completed.stdout+completed.stderr)
            tree=ET.fromstring(subprocess.check_output(['pdftotext','-bbox',str(pdf),'-']))
            ns={'x':'http://www.w3.org/1999/xhtml'}
            words=tree.findall('.//x:word',ns)
            self.assertIn('recorded',[word.text for word in words])
            for i,a in enumerate(words):
                for b in words[i+1:]:
                    overlap_x=min(float(a.get('xMax')),float(b.get('xMax')))-max(float(a.get('xMin')),float(b.get('xMin')))
                    overlap_y=min(float(a.get('yMax')),float(b.get('yMax')))-max(float(a.get('yMin')),float(b.get('yMin')))
                    self.assertFalse(overlap_x>1 and overlap_y>1, f'Overlapping PDF words: {a.text} / {b.text}')

    def test_pdf_pair_is_transactional_and_records_exact_inputs(self):
        import sheet_pdf
        design=generate('spur');report=sheets.report(design,0,metadata(design),'Example.json',4)
        with TemporaryDirectory() as folder:
            target=Path(folder)/'sheets'
            with patch('sheet_pdf.inspection',side_effect=OSError('disk full')):
                with self.assertRaises(OSError):sheet_pdf.export(report,target)
            self.assertFalse(target.exists())
            self.assertEqual(list(Path(folder).iterdir()),[])
            sheet_pdf.export(report,target)
            for name in ('production','inspection'):
                self.assertTrue((target/(name+'.pdf')).read_bytes().startswith(b'%PDF-'))
            self.assertEqual(json.loads((target/'sheet-data.json').read_text())['company'],report['company'])
            with self.assertRaises(FileExistsError):sheet_pdf.export(report,target)


if __name__=='__main__':unittest.main()
