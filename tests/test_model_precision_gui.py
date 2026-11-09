# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""The Settings page shares transactional project precision and its real bounds."""
from copy import deepcopy
from decimal import Decimal
from threading import Event
import unittest
from unittest.mock import patch
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk
import test_workspace_theme_preferences as fixtures
from test_interference_gui import pump,wait_until
from precision_ui import millimetres


class ModelPrecisionGuiTests(unittest.TestCase):
    setUpClass=fixtures.WorkspaceThemePreferencesTests.__dict__['setUpClass']
    setUp=fixtures.WorkspaceThemePreferencesTests.setUp
    close_apps=fixtures.WorkspaceThemePreferencesTests.close_apps
    launch=fixtures.WorkspaceThemePreferencesTests.launch

    def ready(self,family='helical'):
        app=self.launch()
        app.load_config_data(dict(format='solidcraft-riduttori/1',family=family,parameters={}))
        self.assertTrue(wait_until(lambda:not app.pending and not app._geometry_waiting and not app.busy))
        return app

    def panel(self,app):
        app.settings.present();app.settings.tabs['precision'].set_active(True)
        comparison=app.quality_comparison
        self.assertTrue(wait_until(lambda:comparison.result is not None,6))
        return comparison

    def test_comparison_does_not_edit_project_and_never_claims_unknown_total(self):
        app=self.ready('parallel');before=deepcopy(app.project_snapshot());token=app.document.token
        design,scene=app.design,app.canvas.scene
        comparison=self.panel(app)
        self.assertIs(comparison.worker,app.quality_worker)
        for name in ('Fast','Standard','Fine','Part default','Preview','Export'):
            self.assertEqual(comparison.cells[name][2].get_text(),'Not bounded')
        comparison.buttons['Fine'].emit('clicked')
        self.assertEqual([entry.get_text() for entry in app.quality_entries.values()],['0.005','0.005'])
        comparison.buttons['Part default'].emit('clicked')
        self.assertTrue(all(not entry.get_text() for entry in app.quality_entries.values()))
        self.assertEqual(app.project_snapshot(),before);self.assertEqual(app.document.token,token)
        self.assertIs(app.design,design);self.assertIs(app.canvas.scene,scene)
        app.settings.dialog.response(Gtk.ResponseType.CLOSE)
        self.assertTrue(comparison.closed.is_set());self.assertIsNone(app.project_dialog)
        self.assertTrue(wait_until(lambda:app.quality_worker.thread is None))

    def test_export_draft_and_apply_preserve_nominal_parts_scene_selection_and_phase(self):
        app=self.ready();comparison=self.panel(app)
        parts=app.design.parts;scene=app.canvas.scene;token=app.document.token
        app.canvas.motion_phase=1.234;app.components.selected=(0,);app.canvas.selected_indices=(0,)
        app.quality_entries['export_mm'].set_text('.005')
        self.assertEqual(app.quality,{})
        self.assertEqual(app.document.token,token)
        with patch('app.generate',side_effect=AssertionError('No nominal regeneration')):
            app.quality_apply_button.emit('clicked')
            self.assertTrue(wait_until(lambda:app.quality=={'export_mm':.005},6))
        self.assertIs(app.design.parts,parts);self.assertIs(app.canvas.scene,scene)
        self.assertEqual(app.components.selected,(0,));self.assertEqual(app.canvas.motion_phase,1.234)
        self.assertIsNotNone(app.settings.dialog)
        self.assertTrue(wait_until(lambda:comparison.result is not None,6))
        self.assertGreater(comparison.result['Fine']['model_mm'],.005)
        app.settings.dialog.response(Gtk.ResponseType.CLOSE)
        path=self.root/'precision.config.json';self.assertTrue(app.save_project(path=path))
        app.undo_project();self.assertEqual(app.quality,{})
        app.redo_project();self.assertEqual(app.quality,{'export_mm':.005})

    def test_preview_apply_changes_mesh_and_invalid_input_keeps_accepted_project(self):
        app=self.ready();self.panel(app);parts=app.design.parts;scene=app.canvas.scene
        app.quality_entries['preview_mm'].set_text('.1');app.quality_apply_button.emit('clicked')
        self.assertTrue(wait_until(lambda:app.quality=={'preview_mm':.1},6))
        self.assertIsNot(app.canvas.scene,scene);self.assertIs(app.design.parts,parts)
        self.assertLess(len(app.canvas.scene.vertices),len(scene.vertices))
        before=deepcopy(app.project_snapshot());token=app.document.token;scene=app.canvas.scene
        for value in ('-1','nan','inf'):
            app.quality_entries['export_mm'].set_text(value);app.quality_apply_button.emit('clicked');pump(.03)
            self.assertEqual(app.project_snapshot(),before);self.assertEqual(app.document.token,token)
            self.assertIs(app.canvas.scene,scene)

    def test_close_cancels_bound_work_without_applying_or_touching_reopened_page(self):
        import geometry_quality
        app=self.ready();before=deepcopy(app.project_snapshot());token=app.document.token
        started=Event();release=Event();original=geometry_quality.deviation
        def delayed(*args):
            started.set();release.wait(3);return original(*args)
        with patch('precision_ui.deviation',side_effect=delayed):
            app.settings.present();app.settings.tabs['precision'].set_active(True)
            old=app.quality_comparison
            self.assertTrue(wait_until(started.is_set))
            app.settings.dialog.response(Gtk.ResponseType.CLOSE)
            self.assertTrue(old.closed.is_set());release.set()
            self.assertTrue(wait_until(lambda:app.quality_worker.thread is None))
        current=self.panel(app)
        self.assertIsNot(old,current);self.assertIs(current.worker,old.worker)
        self.assertEqual(app.project_snapshot(),before);self.assertEqual(app.document.token,token)

    def test_upper_bound_formatting_and_multilingual_large_text_layout(self):
        for number in (0.,.015168126388237613,.004930992258518214,1e-7):
            text=millimetres(number,bound=True)
            shown=Decimal(text.split(' mm')[0].removeprefix('≤ '))
            self.assertGreaterEqual(shown,Decimal.from_float(number))
        self.assertEqual(millimetres(.1),'0.1 mm · 100 µm')
        app=self.ready('spur');comparison=self.panel(app)
        for code in ('en','it','ta'):
            app.language.change(code)
            for scale in (0,1,2):
                app.text_size.set_selected(scale);pump(.14)
                for row in comparison.cells.values():
                    for cell in row:
                        ok,b=cell.compute_bounds(app.settings.dialog);self.assertTrue(ok)
                        self.assertGreaterEqual(b.get_x(),0)
                        self.assertLessEqual(b.get_x()+b.get_width(),app.settings.dialog.get_width()+1)


if __name__=='__main__':unittest.main()
