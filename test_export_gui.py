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
        a.output_dir=self.root/self._testMethodName;a.output_dir.mkdir()
        a.output_label.set_text(str(a.output_dir))
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='helical',parameters=generate('helical').values))
        pump_until(lambda:not a.pending and not a.busy)

    def click(self,title):
        choices=[w for w in widgets(self.app.export_menu.get_popover()) if isinstance(w,Gtk.Button) and
                 any(isinstance(child,Gtk.Label) and child.get_text()==title for child in widgets(w))]
        self.assertEqual(len(choices),1)
        with patch.object(module,'Client',side_effect=AssertionError('Standalone export connected to CAD')):
            choices[0].emit('clicked')
            pump_until(lambda:not self.app.busy)

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
        self.click('Complete package')
        folder=next(a.output_dir.glob('*.package'))
        png=(folder/'preview.png').read_bytes()
        self.assertTrue(png.startswith(b'\x89PNG\r\n\x1a\n'))
        self.assertTrue(png.endswith(b'IEND\xaeB`\x82'))
        self.assertGreater(len(png),1000)
        self.assertTrue(json.loads((folder/'manifest.json').read_text())['complete'])
        self.assertFalse(a.canvas.exploded)
        self.assertFalse(a.canvas.section)
        self.assertTrue((folder/'assembly.step').is_file())

    def test_failed_background_export_publishes_nothing_and_restores_actions(self):
        with patch('package_export.bom.export',side_effect=OSError('Injected export failure')):
            self.click('Complete package')
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


if __name__=='__main__':unittest.main()
