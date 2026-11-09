# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Real GTK/OpenGL entry, history and saved-source precision acceptance."""
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
from precise_numbers import SOURCE_KEY, from_text


def pump(seconds=.1):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
        time.sleep(.005)


class PreciseNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check() or not Gdk.Display.get_default():raise unittest.SkipTest('Real GTK display required')
        cls.folder=TemporaryDirectory(prefix='ratiolab-rust-precision-gui-')
        root=Path(cls.folder.name)
        cls.environment=patch.dict(os.environ,dict(XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'),APPDATA=str(root/'roaming'),LOCALAPPDATA=str(root/'local')))
        cls.environment.start()
        import app
        cls.module=app;cls.previous=(app.BASE,app.GENERATED)
        app.BASE=root;app.GENERATED=root/'exports'
        cls.app=app.ReducerApp();cls.app.set_application_id(f'local.ratiolab.rustprecision.p{os.getpid()}')
        cls.app.set_flags(Gio.ApplicationFlags.NON_UNIQUE);cls.app.register(None);cls.app.activate()
        end=time.monotonic()+25
        while time.monotonic()<end and not cls.app.canvas.gl:pump(.05)
        if not cls.app.canvas.gl:raise RuntimeError('OpenGL initialization failed: '+str(cls.app.canvas.failure))

    @classmethod
    def tearDownClass(cls):
        for window in cls.app.get_windows():window.destroy()
        cls.module.BASE,cls.module.GENERATED=cls.previous
        cls.environment.stop();cls.folder.cleanup()

    def test_automatic_sources_and_expressions_survive_json_snapshot_restore(self):
        a=self.app
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='spur',parameters={
            'module':from_text('2.00000000000000000001')*3/3,
            'input_rpm':from_text('1500.00000000000000000001')}))
        expected=json.loads(json.dumps(a.config()))
        self.assertIsInstance(expected['parameters'][SOURCE_KEY]['module'],dict)
        self.assertEqual(expected['parameters'][SOURCE_KEY]['input_rpm'],'1500.00000000000000000001')
        snapshot=json.loads(json.dumps(a.project_snapshot()))
        self.assertIn('module',snapshot['automatic']['spur'])
        self.assertIn('input_rpm',snapshot['automatic']['spur'])
        for _ in range(3):
            a.restore_project_snapshot(snapshot);pump(.03)
            self.assertTrue(a.refresh())
            self.assertEqual(a.project_snapshot(),snapshot)
            self.assertEqual(a.config(),expected)
            self.assertEqual(a.design.analysis['gear']['analytic_values']['pitch_radius_mm'],
                             '24.00000000000000000012')
        # A real edit, including a distinct decimal with the same float value,
        # replaces the old source. Invalid text remains an invalid draft.
        a.inputs['module'].set_text('2.00000000000000000002')
        self.assertTrue(a.refresh())
        self.assertEqual(a.config()['parameters'][SOURCE_KEY]['module'],'2.00000000000000000002')
        a.inputs['module'].set_text('unfinished')
        invalid=json.loads(json.dumps(a.project_snapshot()))
        a.restore_project_snapshot(invalid)
        self.assertEqual(a.inputs['module'].get_text(),'unfinished')
        self.assertFalse(a.refresh())
        self.assertNotIn('module',a.project_snapshot()['automatic']['spur'])

    def test_exact_input_save_undo_and_real_render(self):
        a=self.app
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='spur',parameters={}))
        pump(.1)
        a.inputs['module'].set_text('2.00000000000000000001')
        self.assertTrue(a.refresh())
        self.assertEqual(a.design.analysis['gear']['analytic_values']['pitch_radius_mm'],'24.00000000000000000012')
        saved=json.loads(json.dumps(a.config()))
        self.assertEqual(saved['parameters'][SOURCE_KEY]['module'],'2.00000000000000000001')
        a.project_changed();a.document._group=None
        a.inputs['module'].set_text('2.00000000000000000002')
        self.assertTrue(a.refresh());a.project_changed()
        self.assertEqual(a.design.analysis['gear']['analytic_values']['pitch_radius_mm'],'24.00000000000000000024')
        a.undo_project();self.assertTrue(a.refresh())
        self.assertEqual(a.config()['parameters'][SOURCE_KEY]['module'],'2.00000000000000000001')
        a.redo_project();self.assertTrue(a.refresh())
        self.assertEqual(a.config()['parameters'][SOURCE_KEY]['module'],'2.00000000000000000002')
        a.load_config_data(saved);self.assertTrue(a.refresh());pump(.15)
        self.assertEqual(a.config()['parameters'][SOURCE_KEY]['module'],'2.00000000000000000001')
        images=[];a.canvas.capture_png(lambda data,error:images.append((data,error)))
        self.assertTrue(images);self.assertIsNone(images[0][1]);self.assertTrue(images[0][0].startswith(b'\x89PNG'))
        if os.environ.get('RATIOLAB_TEST_CAPTURE'):
            Path(os.environ['RATIOLAB_TEST_CAPTURE']).write_bytes(images[0][0])
        self.assertFalse(a.canvas.failure)
