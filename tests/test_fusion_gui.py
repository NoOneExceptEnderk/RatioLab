# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""GTK integration preserves SolidCraft and blocks concurrent/stale transfers."""
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk, Gdk, Gio, GLib
import app as module
from geometry import generate


def pump(duration=.05):
    until=time.monotonic()+duration
    context=GLib.MainContext.default()
    while time.monotonic()<until:
        while context.pending():context.iteration(False)
        time.sleep(.002)


class FusionGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            raise unittest.SkipTest('GTK display required')
        cls.folder=tempfile.TemporaryDirectory(prefix='ratiolab-fusion-gui-')
        cls.root=Path(cls.folder.name)
        cls.environment=patch.dict(os.environ,dict(XDG_CONFIG_HOME=str(cls.root/'config'),XDG_DATA_HOME=str(cls.root/'data'),APPDATA=str(cls.root/'roaming'),LOCALAPPDATA=str(cls.root/'local')))
        cls.environment.start()
        cls.app=module.ReducerApp()
        cls.app.set_application_id(f'local.solidcraft.reducers.fusiontests.p{os.getpid()}')
        cls.app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        cls.app.register(None);cls.app.activate();pump(.15)

    @classmethod
    def tearDownClass(cls):
        for window in cls.app.get_windows():window.destroy()
        cls.environment.stop();cls.folder.cleanup()

    def setUp(self):
        self.app.busy=False
        self.app.load_config_data(dict(format='solidcraft-riduttori/1',family='spur',parameters=generate('spur').values))
        self.app.output_dir=self.root
        self.app.set_fusion_connection(None)
        pump(.02)

    def status(self):
        return dict(application='Fusion',version='2600',document={'id':'doc1','name':'Test Design'},bridge_session='session')

    def test_new_section_preserves_original_solidcraft_controls(self):
        a=self.app
        self.assertEqual(a.connect_btn.get_label(),'Connect SolidCraft')
        self.assertEqual(a.send_btn.get_label(),'Create in SolidCraft')
        self.assertEqual(a.fusion_send_btn.get_label(),'Create in Fusion')
        for widget in (a.connect_btn,a.send_btn,a.fusion_install_btn,a.fusion_connect_btn,a.fusion_send_btn):
            self.assertTrue(widget.is_ancestor(a.cad_menu.get_popover()))
        self.assertIn('RatioLabBridge',a.fusion_hint.get_text())
        self.assertIn('STEP solids',a.fusion_hint.get_text())

    def test_parameter_edits_immediately_block_send_and_invalid_geometry_never_calls_client(self):
        a=self.app
        self.assertTrue(a.fusion_send_btn.get_sensitive())
        a.inputs['module'].set_text('unfinished')
        self.assertFalse(a.fusion_send_btn.get_sensitive())
        self.assertFalse(a.refresh())
        with patch.object(module.fusion_connection,'Client') as client:
            a.send_fusion()
        client.assert_not_called()
        a.inputs['module'].set_text('2.5');a.refresh()
        self.assertTrue(a.fusion_send_btn.get_sensitive())

    def test_background_blocks_all_cad_mutations_and_restores_after_completion(self):
        a=self.app
        release=threading.Event()
        def work():
            release.wait(5)
            return 'test complete'
        a.background(work)
        try:
            self.assertTrue(a.busy)
            for widget in (a.send_btn,a.connect_btn,a.fusion_send_btn,a.fusion_connect_btn,a.fusion_install_btn,a.export_menu,a.selector,a.fields):
                self.assertFalse(widget.get_sensitive())
            with patch.object(module.fusion_connection,'Client') as client:
                a.send_fusion()
            client.assert_not_called()
        finally:
            release.set()
        deadline=time.monotonic()+3
        while a.busy and time.monotonic()<deadline:pump(.02)
        self.assertFalse(a.busy)
        self.assertTrue(a.fusion_send_btn.get_sensitive())
        self.assertTrue(a.fusion_install_btn.get_sensitive())
        self.assertTrue(a.export_menu.get_sensitive())

    def test_connect_failure_clears_previous_connected_label(self):
        a=self.app;a.set_fusion_connection(self.status())
        self.assertTrue(a.fusion_connected)
        with patch.object(module.fusion_connection,'Client') as client:
            client.return_value.__enter__.side_effect=module.fusion_connection.FusionError('offline')
            with self.assertRaises(module.fusion_connection.FusionError):a.connect_fusion()
        pump(.02)
        self.assertFalse(a.fusion_connected)
        self.assertIn('Disconnected',a.fusion_connection_label.get_text())

    def test_send_snapshots_validated_design_output_and_visibility(self):
        a=self.app
        a.canvas.show_support=True;a.canvas.show_housing=False
        with patch.object(a,'background') as background:
            a.send_fusion()
        worker=background.call_args.args[0]
        design=a.design
        with patch.object(module.fusion_connection,'Client') as client:
            active=client.return_value.__enter__.return_value
            active.insert.return_value={'package_path':str(self.root/'package')}
            active.status.return_value=self.status()
            message=worker()
            active.insert.assert_called_once_with(design,self.root,{'gear','support'})
        pump(.02)
        self.assertIn('STEP solids',message)
        self.assertIn('Test Design',a.fusion_connection_label.get_text())
        self.assertTrue(a.fusion_connected)

    def test_failed_import_clears_status_and_never_repeats(self):
        a=self.app;a.set_fusion_connection(self.status())
        with patch.object(a,'background') as background:a.send_fusion()
        worker=background.call_args.args[0]
        with patch.object(module.fusion_connection,'Client') as client:
            active=client.return_value.__enter__.return_value
            active.insert.side_effect=module.fusion_connection.FusionError('may still be running; do not resend')
            with self.assertRaises(module.fusion_connection.FusionError):worker()
            active.insert.assert_called_once()
        pump(.02)
        self.assertFalse(a.fusion_connected)


if __name__=='__main__':unittest.main()
