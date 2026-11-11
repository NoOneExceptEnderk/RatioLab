# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Actual GTK editing, project lifecycle, stale dialogs and PDF action."""
from copy import deepcopy
import json
from unittest.mock import patch
import unittest
from gi.repository import Gtk
import test_workspace_theme_preferences as fixtures
from test_interference_gui import wait_until
import component_sheets as sheets
from component_sheets_ui import Editor


class ComponentSheetsGuiTests(unittest.TestCase):
    setUpClass=fixtures.WorkspaceThemePreferencesTests.__dict__['setUpClass']
    setUp=fixtures.WorkspaceThemePreferencesTests.setUp
    close_apps=fixtures.WorkspaceThemePreferencesTests.close_apps
    launch=fixtures.WorkspaceThemePreferencesTests.launch

    def test_initial_workspace_button_opens_without_rebuilding_or_losing_selection(self):
        app=self.launch()
        self.assertTrue(wait_until(lambda:not app.pending and not app._geometry_waiting and not app.busy))
        app.components.open()
        app.components.list.select_row(app.components.list.get_row_at_index(0))
        self.assertEqual(app.components.selected,(0,))
        design,scene=app.design,app.canvas.scene
        with patch.object(app,'refresh',side_effect=AssertionError('Opening the editor must not refresh geometry')):
            app.components.sheets_button.emit('clicked')
        self.assertIsNotNone(app.project_dialog)
        self.assertEqual(app.project_dialog.get_title(),'Component production / inspection sheets')
        self.assertEqual(app.components.selected,(0,))
        self.assertIs(app.design,design);self.assertIs(app.canvas.scene,scene)
        app.project_dialog.response(Gtk.ResponseType.CANCEL)

    def ready(self):
        app=self.launch()
        app.load_config_data(dict(format='solidcraft-riduttori/1',family='spur',parameters={}))
        self.assertTrue(wait_until(lambda:not app.pending and not app._geometry_waiting and not app.busy))
        app.components.open();app.components.select((0,))
        self.assertTrue(app.components.sheets_button.get_sensitive())
        return app

    def test_apply_preserves_geometry_and_part_selection_and_undo_redo_roundtrips(self):
        app=self.ready();design=app.design;parts=design.parts
        editor=app.components.open_sheets()
        self.assertIsInstance(editor,Editor)
        editor.company_entries['company'].set_text('Officina Ω')
        editor.part_entries['code'].set_text('G-001')
        with patch('app.generate',side_effect=AssertionError('Metadata must not regenerate geometry')):
            editor.dialog.response(Gtk.ResponseType.APPLY)
        self.assertIsNone(app.project_dialog)
        self.assertIs(app.design,design);self.assertIs(app.design.parts,parts)
        self.assertEqual(app.components.selected,(0,))
        self.assertTrue(app.document.dirty)
        saved=deepcopy(app.component_sheets)
        app.undo_project()
        self.assertEqual(app.component_sheets,{})
        app.redo_project()
        self.assertEqual(app.component_sheets,saved)

    def test_cancel_and_invalid_limits_leave_project_unchanged(self):
        app=self.ready();before=app.project_snapshot()
        editor=app.components.open_sheets()
        editor.company_entries['company'].set_text('Unsaved')
        row=editor.checks[0][1]
        row['lower'].set_text('20');row['upper'].set_text('10')
        editor.dialog.response(Gtk.ResponseType.APPLY)
        self.assertIn('lower',editor.error.get_text())
        self.assertEqual(app.project_snapshot(),before)
        editor.dialog.response(Gtk.ResponseType.CANCEL)
        self.assertIsNone(app.project_dialog)
        self.assertFalse(app.document.dirty)

    def test_save_open_new_project_and_stale_geometry_review(self):
        app=self.ready();editor=app.components.open_sheets()
        editor.company_entries['company'].set_text('Workshop A')
        editor.dialog.response(Gtk.ResponseType.APPLY)
        app.document.path=self.root/'company.json'
        self.assertTrue(app.save_project())
        saved=json.loads(app.document.path.read_text())
        app.load_config_data(saved,app.document.path)
        self.assertEqual(app.component_sheets,saved['component_sheets'])
        self.assertFalse(app.document.dirty)
        app.inputs['width'].set_text('12')
        self.assertTrue(wait_until(lambda:app.design.values['width']==12 and not app._geometry_waiting and not app.pending))
        app.components.select((0,));editor=app.components.open_sheets()
        self.assertTrue(editor.draft['stale'])
        self.assertEqual(editor.company_entries['company'].get_text(),'Workshop A')
        editor.dialog.response(Gtk.ResponseType.APPLY)
        self.assertFalse(sheets.draft(app.design,0,app.component_sheets)['stale'])
        app.load_config_data(dict(format='solidcraft-riduttori/1',family='spur',parameters={}))
        self.assertEqual(app.component_sheets,{})

    def test_replaced_document_cannot_receive_old_dialog_fields(self):
        app=self.ready();editor=app.components.open_sheets()
        editor.company_entries['company'].set_text('Wrong document')
        app.load_config_data(dict(format='solidcraft-riduttori/1',family='spur',parameters={}))
        with self.assertRaisesRegex(ValueError,'document changed'):editor.commit()
        self.assertEqual(app.component_sheets,{})
        editor.close()

    def test_language_changes_translate_captions_without_rewriting_company_data(self):
        app=self.ready();editor=app.components.open_sheets()
        editor.company_entries['company'].set_text('Save Ω - company text')
        editor.checks[0][2].set_expanded(True)
        app.language.change('it')
        self.assertEqual(editor.dialog.get_widget_for_response(Gtk.ResponseType.ACCEPT).get_label(),'Esporta PDF')
        self.assertEqual(editor.value(editor.checks[0][1]['label']),'Lunghezza assiale (Z locale)')
        self.assertEqual(editor.company_entries['company'].get_text(),'Save Ω - company text')
        editor.dialog.response(Gtk.ResponseType.APPLY)
        key=sheets.component_key(app.design,0)
        self.assertEqual(app.component_sheets['components'][key]['checks'][0]['label'],'Axial length (local Z)')
        self.assertEqual(app.component_sheets['company']['company'],'Save Ω - company text')

    def test_export_action_writes_both_pdfs_and_snapshot(self):
        app=self.ready();app.output_dir=self.root/'exports';editor=app.components.open_sheets()
        editor.company_entries['company'].set_text('Company for PDF')
        app.language.change('it')
        editor.dialog.response(Gtk.ResponseType.ACCEPT)
        self.assertTrue(wait_until(lambda:not app.busy,15))
        folders=list(app.output_dir.iterdir())
        self.assertEqual(len(folders),1)
        self.assertEqual({p.name for p in folders[0].iterdir()},{'production.pdf','inspection.pdf','sheet-data.json'})
        snapshot=json.loads((folders[0]/'sheet-data.json').read_text())
        self.assertEqual(snapshot['language'],'it')
        self.assertEqual(snapshot['company']['company'],'Company for PDF')
        self.assertTrue(app.export_feedback.latest)
        self.assertEqual(len(app.export_feedback.result.outputs),2)

    def test_export_language_is_captured_before_the_background_job(self):
        app=self.ready();app.output_dir=self.root/'language-snapshot';editor=app.components.open_sheets()
        app.language.change('it');jobs=[]
        with patch.object(app,'background',side_effect=lambda work,**_:jobs.append(work)):
            editor.dialog.response(Gtk.ResponseType.ACCEPT)
        self.assertEqual(len(jobs),1)
        app.language.change('de')
        result=jobs[0]()
        snapshot=json.loads((result.folder/'sheet-data.json').read_text())
        self.assertEqual(snapshot['language'],'it')


if __name__=='__main__':unittest.main()
