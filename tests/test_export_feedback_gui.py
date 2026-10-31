# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Real export completion and persistent GTK feedback; no file manager launches."""
from concurrent.futures import CancelledError
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import time
import unittest
from unittest.mock import patch
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk,Gio,GLib
import app as module
from geometry import generate
import stl_export


def wait_until(predicate,seconds=20):
    until=time.monotonic()+seconds;context=GLib.MainContext.default()
    while time.monotonic()<until:
        while context.pending() and time.monotonic()<until:context.iteration(False)
        if predicate():return
        time.sleep(.003)
    raise AssertionError('Timed out waiting for export feedback')


class ExportFeedbackGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            raise unittest.SkipTest('GTK display required')
        cls.temp=TemporaryDirectory(prefix='ratiolab-export-feedback-');cls.root=Path(cls.temp.name)
        cls.env=patch.dict(os.environ,dict(RATIOLAB_UPDATE_CHECK='0',
            XDG_CONFIG_HOME=str(cls.root/'config'),XDG_DATA_HOME=str(cls.root/'data'),
            XDG_CACHE_HOME=str(cls.root/'cache'),APPDATA=str(cls.root/'roaming'),LOCALAPPDATA=str(cls.root/'local')))
        cls.env.start()
        cls.folder_patch=patch('external_programs.open_folder',return_value=True)
        cls.opener=cls.folder_patch.start()
        cls.app=module.ReducerApp()
        cls.app.set_application_id(f'local.solidcraft.reducers.exportfeedback.p{os.getpid()}')
        cls.app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        cls.app.register(None);cls.app.activate()
        wait_until(lambda:cls.app.canvas.gl is not None and not cls.app.pending)

    @classmethod
    def tearDownClass(cls):
        for window in list(cls.app.get_windows()):window.destroy()
        cls.folder_patch.stop();cls.env.stop();cls.temp.cleanup()

    def setUp(self):
        a=self.app;a.components.restore();a.canvas.reset_motion()
        a.export_feedback.dismiss();self.opener.reset_mock();self.opener.side_effect=None
        a.output_dir=self.root/self._testMethodName;a.output_dir.mkdir()
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='parallel',
                               parameters=generate('parallel').values))
        wait_until(lambda:not a.pending and not a.busy)
        self.feedback=a.export_feedback

    def finish(self):
        wait_until(lambda:not self.app.busy)
        self.assertTrue(self.feedback.box.get_visible())

    def test_real_stl_keeps_job_destination_after_preference_change_and_refresh(self):
        a=self.app;destination=a.output_dir;started=Event();release=Event();writer=stl_export.export
        def delayed(design,stem):
            started.set()
            if not release.wait(5):raise TimeoutError('Test worker was not released')
            return writer(design,stem)
        with patch('stl_export.export',side_effect=delayed):
            a.export_stl();self.assertTrue(started.wait(2))
            self.assertIn('Export in progress',self.feedback.description.get_text())
            a.output_dir=self.root/'new preferred destination';a.output_dir.mkdir()
            release.set();self.finish()
        result=self.feedback.result
        self.assertEqual(result.kind,'STL');self.assertEqual(result.folder,destination)
        self.assertTrue(result.outputs[0].is_file());self.assertTrue(result.outputs[1].is_dir())
        self.assertEqual(len(list(result.outputs[1].glob('*.stl'))),len(a.design.parts))
        self.assertIn(result.outputs[0].name,self.feedback.description.get_text())
        self.assertEqual(self.feedback.destination.get_text(),str(destination))
        self.opener.assert_not_called()
        self.feedback.open_button.emit('clicked');self.opener.assert_called_once()
        self.assertEqual(self.opener.call_args.args[0],destination)
        old_width=a.design.values['width']
        a.inputs['width'].set_text(str(old_width+1));a.inputs['width'].emit('activate')
        wait_until(lambda:not a.pending and a.design and a.design.values['width']==old_width+1)
        self.assertIs(self.feedback.result,result);self.assertTrue(self.feedback.box.get_visible())
        self.feedback.dismiss_button.emit('clicked');self.assertFalse(self.feedback.box.get_visible())
        a.refresh();self.assertFalse(self.feedback.box.get_visible())
        self.assertIsNone(self.feedback.result)

    def test_real_bom_lists_published_outputs_and_uses_its_original_folder(self):
        a=self.app;destination=a.output_dir;a.export_bom();self.finish()
        result=self.feedback.result
        self.assertEqual(result.kind,'BOM and calculations');self.assertEqual(result.folder,destination)
        self.assertTrue(all(path.is_file() for path in result.outputs))
        self.assertIn('.bom.txt',result.outputs[0].name)
        document=json.loads(next(path for path in result.outputs if path.name.endswith('.bom.json')).read_text())
        self.assertEqual(document['family'],'parallel');self.assertTrue(document['rows'])
        self.assertTrue(any(path.name.endswith('.calculations.json') for path in result.outputs))
        a.output_dir=self.root/'another preferred folder'
        self.feedback.open_button.emit('clicked')
        self.assertEqual(self.opener.call_args.args[0],destination)

    def test_step_profiles_and_package_share_real_completion(self):
        a=self.app
        for action,kind,required in ((a.export_step,'STEP','assembly.step'),
                                     (a.export_profiles,'SVG / DXF profiles','profiles.json'),
                                     (a.export,'Package','manifest.json')):
            with self.subTest(kind=kind):
                action();self.finish();result=self.feedback.result
                self.assertEqual(result.kind,kind);self.assertTrue(result.outputs[0].is_dir())
                self.assertTrue((result.outputs[0]/required).is_file())
                self.assertIn('Export complete',self.feedback.description.get_text())
                self.assertIn(result.outputs[0].name,self.feedback.description.get_text())
                self.assertFalse(self.feedback.notice.get_visible())
        self.opener.assert_not_called()

    def test_selected_stl_reports_actual_subset_folder(self):
        a=self.app;a.components.open()
        a.components.list.select_row(a.components.list.get_row_at_index(0))
        a.components.export('stl');self.finish();result=self.feedback.result
        self.assertEqual(result.kind,'Selected STL');folder=result.outputs[0]
        selection=json.loads((folder/'selection.json').read_text())
        self.assertEqual(selection['source_indices'],[1])
        self.assertEqual(len(list((folder/'selected.stl-parts').glob('*.stl'))),1)
        self.assertEqual(result.folder,a.output_dir);self.opener.assert_not_called()

    def test_failure_retains_only_clearly_labelled_last_success(self):
        a=self.app;a.export_bom();self.finish();previous=self.feedback.result
        with patch('stl_export.export',side_effect=OSError('Injected disk failure')):
            a.export_stl();self.finish()
        self.assertIs(self.feedback.result,previous)
        self.assertTrue(self.feedback.description.get_text().startswith('Last export'))
        self.assertIn('Export failed',self.feedback.notice.get_text())
        self.assertIn('Injected disk failure',self.feedback.notice.get_text())
        self.assertFalse(list(a.output_dir.glob('*.stl')))
        a.refresh();self.assertIn('Export failed',self.feedback.notice.get_text())
        self.opener.assert_not_called()

    def test_cancelled_job_and_failure_without_success_never_create_success_feedback(self):
        a=self.app;a.export_bom();self.finish();previous=self.feedback.result
        with patch('stl_export.export',side_effect=CancelledError):
            a.export_stl();self.finish()
        self.assertIs(self.feedback.result,previous)
        self.assertTrue(self.feedback.description.get_text().startswith('Last export'))
        self.assertIn('Export cancelled',self.feedback.notice.get_text())
        self.feedback.dismiss()
        with patch('stl_export.export',side_effect=OSError('No writable output')):
            a.export_stl();self.finish()
        self.assertIsNone(self.feedback.result)
        self.assertEqual(self.feedback.description.get_text(),'Export failed')
        self.assertFalse(self.feedback.open_button.get_visible())

    def test_open_folder_failure_is_inline_and_missing_folder_is_not_recreated(self):
        a=self.app;a.export_bom();self.finish();result=self.feedback.result
        self.opener.side_effect=RuntimeError('No file manager available')
        self.feedback.open_button.emit('clicked')
        self.assertIn('Could not open the folder',self.feedback.notice.get_text())
        self.assertIn('No file manager available',self.feedback.notice.get_text())
        self.assertIs(self.feedback.result,result)
        for path in result.folder.iterdir():path.unlink()
        result.folder.rmdir();self.opener.reset_mock()
        self.feedback.open_button.emit('clicked')
        self.assertIn('no longer available',self.feedback.notice.get_text())
        self.assertFalse(result.folder.exists());self.opener.assert_not_called()

    def test_other_background_operations_and_invalid_configuration_do_not_claim_export(self):
        a=self.app;a.background(lambda:'CAD operation completed. Export saved elsewhere.');wait_until(lambda:not a.busy)
        self.assertIsNone(self.feedback.result);self.assertFalse(self.feedback.box.get_visible())
        a.export_bom();self.finish();previous=self.feedback.result
        a.inputs['module'].set_text('-');a.export_stl()
        self.assertIs(self.feedback.result,previous)
        self.assertTrue(self.feedback.description.get_text().startswith('Last export'))
        self.assertIn('Complete a valid configuration',self.feedback.notice.get_text())
        self.assertFalse(list(a.output_dir.glob('*.stl')))


if __name__=='__main__':unittest.main()
