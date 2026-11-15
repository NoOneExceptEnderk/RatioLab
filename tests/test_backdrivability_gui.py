# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Display-backed checks for the fixed worm drive and legacy projects."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, Gio, GLib
import app as module


def pump(duration=.04):
    until = time.monotonic()+duration
    context = GLib.MainContext.default()
    while time.monotonic() < until:
        while context.pending() and time.monotonic() < until:
            context.iteration(False)
        time.sleep(.002)


class WormDriveGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            raise unittest.SkipTest('GTK display required')
        cls.temp = TemporaryDirectory(prefix='ratiolab-backdrivability-tests-')
        cls.root = Path(cls.temp.name)
        cls.env = patch.dict(os.environ, dict(XDG_CONFIG_HOME=str(cls.root/'config'),
                                             XDG_DATA_HOME=str(cls.root/'data')))
        cls.env.start()
        cls.app = module.ReducerApp()
        cls.app.set_application_id(f'local.solidcraft.reducers.backdrivetests.p{os.getpid()}')
        cls.app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        cls.app.register(None)
        cls.app.activate()
        pump(.15)
        assert cls.app.canvas.gl is not None and cls.app.canvas.failure is None

    @classmethod
    def tearDownClass(cls):
        for window in cls.app.get_windows():
            window.destroy()
        cls.env.stop()
        cls.temp.cleanup()

    def test_legacy_project_shows_fixed_worm_input_and_wheel_output(self):
        app = self.app
        app.load_config_data(dict(format='solidcraft-riduttori/1', family='worm',
                                  parameters=dict(io_scheme='reverse', worm_static_friction=.1,
                                                  input_rpm=120)))
        app.motion_connections.emit('clicked')
        pump(.1)
        self.assertEqual(app.fields.get_visible_child_name(), 'motion')
        self.assertEqual(app.design.values['io_scheme'], 'forward')
        self.assertEqual(app.design.values['input_rpm'], 120)
        self.assertNotIn('worm_static_friction', app.config()['parameters'])
        self.assertFalse(app.io_mode_buttons)
        self.assertFalse(app.io_role_selectors)
        self.assertFalse(hasattr(app, 'io_friction_entry'))
        row = app.io_box.get_first_child()
        self.assertEqual(row.get_last_child().get_text(), 'Worm')
        self.assertEqual(row.get_next_sibling().get_last_child().get_text(), 'Wheel')
        self.assertTrue(app.io_results[0][1].get_text())
