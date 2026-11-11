# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Real GTK export actions; never connects to the user's CAD document."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk,Gio,GLib
import app as module
import gui_workflow
from geometry import generate


def pump_until(predicate,timeout=20):
    deadline=time.monotonic()+timeout
    context=GLib.MainContext.default()
    while time.monotonic()<deadline:
        while context.pending():context.iteration(False)
        if predicate():return
        time.sleep(.01)
    raise AssertionError('Timed out waiting for the GUI export')


def widgets(widget):
    yield widget
    child=widget.get_first_child()
    while child:
        yield from widgets(child)
        child=child.get_next_sibling()


class ExportGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            raise unittest.SkipTest('GTK display required')
        cls.temporary=TemporaryDirectory(prefix='ratiolab-export-gui-')
        cls.root=Path(cls.temporary.name)
        cls.environment=patch.dict(os.environ,dict(XDG_CONFIG_HOME=str(cls.root/'config'),XDG_DATA_HOME=str(cls.root/'data'),APPDATA=str(cls.root/'roaming'),LOCALAPPDATA=str(cls.root/'local')))
        cls.environment.start()
        cls.app=module.ReducerApp()
        cls.app.set_application_id(f'local.solidcraft.reducers.exporttests.p{os.getpid()}')
        cls.app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        cls.app.register(None);cls.app.activate()
        pump_until(lambda:cls.app.canvas.gl and not cls.app.pending)

    @classmethod
    def tearDownClass(cls):
        for window in cls.app.get_windows():window.destroy()
        cls.environment.stop();cls.temporary.cleanup()

    def setUp(self):
        a=self.app
        a.export_scope.set_selected(0)
        a.output_dir=self.root/self._testMethodName;a.output_dir.mkdir()
        a.output_label.set_text(str(a.output_dir))
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='helical',parameters=generate('helical').values))
        pump_until(lambda:not a.pending and not a.busy)

    def click(self,title):
        titles=['STEP for CAD','STL for 3D printing','SVG / DXF profiles','Export package','BOM and calculations']
        self.app.export_format.set_selected(titles.index(title))
        self.app.update_export_scope()
        self.assertTrue(self.app.export_confirm.get_sensitive())
        with patch.object(module,'Client',side_effect=AssertionError('Standalone export connected to CAD')):
            self.app.export_confirm.emit('clicked')
            pump_until(lambda:not self.app.busy)

    def test_background_completion_runs_with_continuously_ready_default_sources(self):
        from ratiolab_checks import _wait_for_context
        a=self.app
        context=GLib.MainContext.default()
        message='Background operation completed'
        source=GLib.idle_add(lambda:True,priority=GLib.PRIORITY_DEFAULT)
        try:
            a.background(lambda:message)
            _wait_for_context(context,
                              lambda:not a.busy and a.status.get_text()==message,
                              timeout=2)
            self.assertFalse(a.busy)
            self.assertEqual(a.status.get_text(),message)
        finally:
            GLib.source_remove(source)

    def test_step_menu_action_runs_without_cad_and_keeps_bodies(self):
        self.click('STEP for CAD')
        folders=list(self.app.output_dir.glob('*.step-export'));self.assertEqual(len(folders),1)
        self.assertTrue((folders[0]/'assembly.step').is_file())
        self.assertEqual(len(list((folders[0]/'step-parts').glob('*.step'))),len(self.app.design.parts))
        self.assertTrue(self.app.export_menu.get_sensitive())

    def test_profiles_menu_labels_helical_sections(self):
        self.click('SVG / DXF profiles')
        folder=next(self.app.output_dir.glob('*.profiles-export'))
        info=json.loads((folder/'profiles.json').read_text())
        self.assertFalse(info['components'][0]['extrudible'])
        self.assertTrue(list((folder/'profiles').glob('*.svg')))
        self.assertTrue(list((folder/'profiles').glob('*.dxf')))

    def test_complete_package_waits_for_real_png_and_manifest(self):
        a=self.app
        a.view_options['exploded'].set_active(True)
        a.view_options['section'].set_active(True)
        self.click('Export package')
        folder=next(a.output_dir.glob('*.package'))
        png=(folder/'preview.png').read_bytes()
        self.assertTrue(png.startswith(b'\x89PNG\r\n\x1a\n'))
        self.assertTrue(png.endswith(b'IEND\xaeB`\x82'))
        self.assertGreater(len(png),1000)
        self.assertTrue(json.loads((folder/'manifest.json').read_text())['complete'])
        self.assertTrue(a.canvas.exploded)
        self.assertTrue(a.canvas.section)
        self.assertTrue((folder/'assembly.step').is_file())

    def test_failed_background_export_publishes_nothing_and_restores_actions(self):
        with patch('package_export.bom.export',side_effect=OSError('Injected export failure')):
            self.click('Export package')
        self.assertFalse(list(self.app.output_dir.iterdir()))
        self.assertTrue(self.app.export_menu.get_sensitive())
        self.assertFalse(self.app.busy)

    def test_cancelled_or_empty_destination_selection_preserves_current_folder(self):
        a=self.app;previous=a.output_dir
        # Exercise the actual signal handler with a minimal chooser provider;
        # no desktop portal window is opened by an automated cancellation test.
        class EmptyChooser:
            response=Gtk.ResponseType.CANCEL
            def __init__(self,**kwargs):pass
            def get_property(self,key):return ''
            def set_current_folder(self,*args):pass
            def connect(self,event,callback):self.callback=callback
            def show(self):self.callback(self,self.response)
            def get_file(self):return None
            def destroy(self):pass
        with patch.object(gui_workflow.Gtk,'FileChooserNative',EmptyChooser):gui_workflow.choose_output(a)
        self.assertEqual(a.output_dir,previous)
        EmptyChooser.response=Gtk.ResponseType.ACCEPT
        with patch.object(gui_workflow.Gtk,'FileChooserNative',EmptyChooser):gui_workflow.choose_output(a)
        self.assertEqual(a.output_dir,previous)
        self.assertFalse(list(previous.iterdir()))

    def test_explicit_subset_matches_displayed_source_names_and_empty_never_falls_back(self):
        a=self.app;c=a.components
        self.assertEqual(a.export_scope.get_selected(),0)
        a.export_scope.set_selected(1);a.update_export_scope()
        self.assertFalse(a.export_confirm.get_sensitive())
        with patch.object(a,'export_step') as complete:
            a.export_confirm.emit('clicked');complete.assert_not_called()
        self.assertFalse(list(a.output_dir.iterdir()))
        c.select((0,));a.update_export_scope()
        self.assertIn('001 · '+a.design.parts[0].name,a.export_names.get_text())
        self.click('STEP for CAD')
        folder=next(a.output_dir.glob('*.selected-step'))
        selection=json.loads((folder/'selection.json').read_text())
        self.assertEqual(selection['components'],[dict(source_index=1,name=a.design.parts[0].name)])
        self.assertEqual(len(list((folder/'step-parts').glob('*.step'))),1)
        c.invalidate();a.update_export_scope()
        self.assertFalse(a.export_confirm.get_sensitive())
        a.export_confirm.emit('clicked')
        self.assertEqual(len(list(a.output_dir.iterdir())),1)

    def test_selected_bom_is_explained_and_component_shortcut_opens_same_flow(self):
        a=self.app;c=a.components;c.open();c.select((0,))
        with patch.object(a,'open_export') as open_export:
            c.export_buttons[0].emit('clicked')
            open_export.assert_called_once_with('step',selected=True)
        a.export_scope.set_selected(1);a.export_format.set_selected(4);a.update_export_scope()
        self.assertFalse(a.export_confirm.get_sensitive())
        self.assertIn('Selected BOM',a.export_description.get_text())
        a.export_format.set_selected(0);a.update_export_scope()
        self.assertTrue(a.export_confirm.get_sensitive())

    def test_package_capture_uses_all_hidden_parts_and_restores_view_even_on_failure(self):
        a=self.app
        d=generate('parallel',dict(bearing_mode='shaft',hardware_mode='standard'))
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='parallel',parameters=d.values))
        pump_until(lambda:not a.pending and not a.busy)
        a.view_options['support'].set_active(False);a.view_options['housing'].set_active(False)
        a.canvas.isolated_indices=(0,);a.set_explosion(.5);a.view_options['section'].set_active(True)
        a.canvas.motion_phase=.7
        scene=a.canvas.scene;token=a.document.token;capture=a.canvas.capture_png;observed=[]
        def check(callback):
            observed.append(tuple(p.source_index for p in a.canvas.scene.parts))
            self.assertIsNone(a.canvas.isolated_indices)
            self.assertFalse(a.canvas.section);self.assertFalse(a.canvas.exploded)
            self.assertFalse(a.canvas.motion_enabled);self.assertIsNone(a.canvas.inspection_phase)
            capture(callback)
        with patch.object(a.canvas,'capture_png',check):png=a.components.capture_export_preview()
        self.assertTrue(png.startswith(b'\x89PNG'))
        self.assertEqual(set(observed[0]),set(range(len(d.parts))))
        self.assertIs(a.canvas.scene,scene);self.assertEqual(a.canvas.isolated_indices,(0,))
        self.assertEqual(a.canvas.motion_phase,.7);self.assertEqual(a.canvas.exploded,.5)
        self.assertTrue(a.canvas.section);self.assertEqual(a.document.token,token)
        with patch.object(a.canvas,'capture_png',side_effect=RuntimeError('Injected capture failure')):
            with self.assertRaisesRegex(RuntimeError,'Injected'):a.components.capture_export_preview()
        self.assertIs(a.canvas.scene,scene);self.assertEqual(a.canvas.isolated_indices,(0,))
        self.assertTrue(a.canvas.section);self.assertEqual(a.canvas.exploded,.5)


if __name__=='__main__':unittest.main()
