# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Display-backed cycloidal cam filtering, component selection and CAD parity."""
import io
import json
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
from geometry import generate
from test_cycloidal_eccentric_visibility import INPUT_SCHEMES, cams


def pump(duration=.06):
    context = GLib.MainContext.default()
    until = time.monotonic()+duration
    while time.monotonic()<until:
        while context.pending():
            context.iteration(False)
        time.sleep(.003)


class CycloidalEccentricVisibilityGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            raise unittest.SkipTest('A working GTK display is required')
        cls.temporary = TemporaryDirectory(prefix='ratiolab-eccentric-gui-')
        cls.root = Path(cls.temporary.name)
        cls.environment = patch.dict(os.environ, dict(
            XDG_CONFIG_HOME=str(cls.root/'config'), XDG_DATA_HOME=str(cls.root/'data'),
            APPDATA=str(cls.root/'roaming'), LOCALAPPDATA=str(cls.root/'local')))
        cls.environment.start()
        cls.app = module.ReducerApp()
        cls.app.set_application_id(f'local.ratiolab.eccentricvisibility.p{os.getpid()}')
        cls.app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        cls.app.register(None)
        cls.app.activate()
        pump(.2)
        if cls.app.canvas.failure or not cls.app.canvas.gl:
            raise RuntimeError('OpenGL initialization failed: '+str(cls.app.canvas.failure))

    @classmethod
    def tearDownClass(cls):
        for window in cls.app.get_windows():
            window.destroy()
        cls.environment.stop()
        cls.temporary.cleanup()

    def load(self, variant, scheme):
        a = self.app
        a.components.restore()
        a.load_config_data(dict(format='solidcraft-riduttori/1', family='cycloidal',
            parameters=generate('cycloidal', dict(variant=variant, io_scheme=scheme)).values))
        self.assertIsNotNone(a.design, a.status.get_text())
        for key in ('support', 'housing', 'exploded', 'section'):
            a.view_options[key].set_active(False)
        a.canvas.reset_motion()

    def capture(self, name):
        import cairo
        a = self.app
        a.canvas.make_current()
        self.assertIsNone(a.canvas.get_error())
        images = []
        a.canvas.capture_png(lambda data, error: images.append((data, error)))
        self.assertIsNone(images[0][1])
        surface = cairo.ImageSurface.create_from_png(io.BytesIO(images[0][0]))
        pixels = bytes(surface.get_data())
        # Only the isolated cam is drawn over the dark grid in these captures.
        orange = sum(pixels[i+2] > 1.15*pixels[i+1] and pixels[i+1] > 1.1*pixels[i]
                     for i in range(0, len(pixels), 4))
        self.assertGreater(orange, 100, 'The isolated input cam must actually render')
        if os.environ.get('RATIOLAB_ECCENTRIC_ARTIFACT_DIR'):
            folder = Path(os.environ['RATIOLAB_ECCENTRIC_ARTIFACT_DIR'])
            folder.mkdir(parents=True, exist_ok=True)
            (folder/name).write_bytes(images[0][0])

    def test_support_toggle_keeps_cams_selectable_and_really_rendered(self):
        a = self.app
        for variant in ('single', 'dual'):
            for scheme in INPUT_SCHEMES:
                with self.subTest(variant=variant, scheme=scheme):
                    self.load(variant, scheme)
                    a.components.open()
                    design = a.design
                    indices = {index for index, part in cams(design)}
                    visible = set(a.components.visible_indices())
                    self.assertTrue(indices <= visible)
                    bearings = {i for i, part in enumerate(design.parts)
                                if part.name.startswith('Bearing_eccentric_')}
                    self.assertTrue(bearings)
                    self.assertFalse(bearings & visible)
                    index = min(indices)
                    a.components.select((index,))
                    self.assertEqual(a.components.selected, (index,))
                    self.assertNotIn(' · hidden', a.components.list.get_row_at_index(index).get_child().get_text())
                    a.view_options['support'].set_active(True)
                    self.assertTrue(indices | bearings <= set(a.components.visible_indices()))
                    a.view_options['support'].set_active(False)
                    self.assertTrue(indices <= set(a.components.visible_indices()))
                    self.assertFalse(bearings & set(a.components.visible_indices()))
                    a.components.select(())
                    a.canvas.isolated_indices = (index,)
                    a.canvas.view('top')
                    self.capture(f'{variant}-{scheme}-cam-supports-off.png')
                    a.canvas.isolated_indices = None

    def test_full_fusion_manifest_matches_filtered_preview_without_dropping_supports(self):
        a = self.app
        for variant, scheme in (('single', INPUT_SCHEMES[0]), ('dual', INPUT_SCHEMES[1])):
            with self.subTest(variant=variant, scheme=scheme):
                self.load(variant, scheme)
                design = a.design
                visible = set(a.components.visible_indices())
                manifests = []
                def insert(current, output_dir, visible_roles):
                    manifests.append(module.fusion_connection.prepare_import(
                        current, output_dir, visible_roles))
                    return dict(package_path=str(output_dir))
                a.output_dir = self.root/variant
                with patch.object(module.fusion_connection, 'Client') as factory, \
                        patch.object(a, 'background', side_effect=lambda work: work()):
                    client = factory.return_value.__enter__.return_value
                    client.insert.side_effect = insert
                    client.status.return_value = dict(document=None)
                    a.send_fusion()
                self.assertEqual(len(manifests), 1)
                path = manifests[0]
                manifest = json.loads(path.read_text())
                self.assertEqual(len(manifest['components']), len(design.parts))
                self.assertEqual({part['index']-1 for part in manifest['components'] if part['visible']}, visible)
                records = {part['name']:part for part in manifest['components']}
                for _, part in cams(design):
                    self.assertTrue(records[part.name]['visible'])
                supports = [record for record in records.values() if record['role'] == 'support']
                self.assertTrue(supports)
                self.assertTrue(all(not record['visible'] for record in supports))


if __name__ == '__main__':
    unittest.main()
