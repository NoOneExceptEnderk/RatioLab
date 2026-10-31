# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""GTK regression: keep component identity through rate-only operating edits."""
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
import preview3d
from geometry import generate
from motion_controls import scale_rpm
from project_document import equivalent


def pump(seconds=.05):
    until=time.monotonic()+seconds;context=GLib.MainContext.default()
    while time.monotonic()<until:
        while context.pending() and time.monotonic()<until:context.iteration(False)
        time.sleep(.002)


class RpmSelectionGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            raise unittest.SkipTest('GTK display required')
        cls.temp=TemporaryDirectory(prefix='ratiolab-rpm-selection-');root=Path(cls.temp.name)
        cls.env=patch.dict(os.environ,dict(RATIOLAB_UPDATE_CHECK='0',
            XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'),
            XDG_CACHE_HOME=str(root/'cache'),APPDATA=str(root/'roaming'),LOCALAPPDATA=str(root/'local')))
        cls.env.start()
        cls.app=module.ReducerApp()
        cls.app.set_application_id(f'local.solidcraft.reducers.rpmselection.p{os.getpid()}')
        cls.app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        cls.app.register(None);cls.app.activate();pump(.2)

    @classmethod
    def tearDownClass(cls):
        for window in list(cls.app.get_windows()):window.destroy()
        pump();cls.env.stop();cls.temp.cleanup()

    def setUp(self):
        a=self.app;a.canvas.reset_motion();a.components.restore();a.interference.restore_view()
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='parallel',
                               parameters=generate('parallel',dict(input_rpm=60)).values))
        for key in ('support','housing','exploded','section'):a.view_options[key].set_active(False)
        a.components.open();a.components.measure.set_active(False);pump(.08)
        self.c=a.components

    def select_rows(self,*indices):
        self.c.list.unselect_all()
        for index in indices:self.c.list.select_row(self.c.list.get_row_at_index(index))
        self.assertEqual(self.c.selected,indices)

    def assert_selected(self,indices):
        a=self.app;c=self.c
        self.assertEqual(c.selected,indices);self.assertEqual(a.canvas.selected_indices,indices)
        self.assertEqual(tuple(row.source_index for row in c.list.get_selected_rows()),indices)
        self.assertTrue(c.current());self.assertEqual(c.revision,a.document.token)
        self.assertTrue(equivalent(c.snapshot,a.project_snapshot()))

    def test_entry_commit_preserves_selection_and_geometry_but_clears_measurement(self):
        a=self.app;c=self.c;self.select_rows(0,1)
        previous=a.design;scene=a.canvas.scene;token=a.document.token
        # A completed measurement belongs to the previous operating revision.
        c.points=[(0,(10.,0.,10.)),(1,(90.,0.,10.))];c.pose=c.pose_key()
        c.measure_text.set_text('Previous displayed measurement');c.cache[(0,0.)]=object()
        a.motion_speed_text.set_text('1200');a.motion_speed_text.emit('activate');pump(.1)
        self.assert_selected((0,1));self.assertNotEqual(a.document.token,token)
        self.assertIs(a.canvas.scene,scene)
        # Parts are copied for new port speeds; sampled surfaces retain identity.
        self.assertIsNot(a.design.parts,previous.parts)
        for old,new in zip(previous.parts,a.design.parts):
            self.assertIs(old.outer,new.outer);self.assertIs(old.mesh,new.mesh)
        self.assertEqual(a.design.values['input_rpm'],1200)
        self.assertEqual(a.design.analysis['output']['rpm'],1200/a.design.analysis['signed_ratio'])
        self.assertNotEqual(a.design.analysis['output']['rpm'],previous.analysis['output']['rpm'])
        self.assertFalse(c.points);self.assertIsNone(c.pose);self.assertFalse(c.cache)
        self.assertIn('No measurement',c.measure_text.get_text())
        self.assertTrue(c.export_buttons[0].get_sensitive())
        self.assertIsNotNone(a.canvas.gl);self.assertIsNone(a.canvas.failure)

    def test_slider_keeps_isolated_selection_without_scene_or_gpu_rebuild(self):
        a=self.app;c=self.c;self.select_rows(0);c.isolate()
        scene=a.canvas.scene;previous=a.design
        a.canvas.set_motion_playing(True);pump(.04)
        with patch('app.generate',wraps=module.generate) as generation, \
             patch('preview3d.build_scene',wraps=preview3d.build_scene) as builds, \
             patch.object(a.canvas.gl,'BufferData',wraps=a.canvas.gl.BufferData) as uploads:
            a.begin_motion_rate_drag()
            for rpm in (75,90,120):a.motion_speed.set_value(scale_rpm(rpm))
            a.end_motion_rate_drag();pump(.1)
            self.assertEqual((generation.call_count,builds.call_count,uploads.call_count),(0,0,0))
        self.assert_selected((0,));self.assertIs(a.canvas.scene,scene)
        self.assertIs(a.design.parts[0].outer,previous.parts[0].outer)
        self.assertEqual(a.canvas.isolated_indices,(0,));self.assertIsNotNone(c.saved_filters)
        self.assertTrue(a.canvas.motion_playing);self.assertEqual(a.design.values['input_rpm'],120)
        a.canvas.set_motion_playing(False)

    def test_geometry_edit_and_family_change_clear_selection(self):
        a=self.app;c=self.c;self.select_rows(0);previous=a.design;scene=a.canvas.scene
        a.inputs['width'].set_text(str(previous.values['width']+1));a.inputs['width'].emit('activate')
        deadline=time.monotonic()+5
        while a.pending and time.monotonic()<deadline:pump(.02)
        self.assertFalse(a.pending,'Geometry edit did not finish preparing')
        self.assert_selected(());self.assertIsNot(a.canvas.scene,scene)
        self.assertIsNot(a.design.parts[0].outer,previous.parts[0].outer)
        self.assertEqual(a.design.values['width'],previous.values['width']+1)
        self.select_rows(0)
        a.selector.set_selected(list(module.FAMILIES).index('spur'));pump(.08)
        self.assertEqual(a.design.family,'spur');self.assert_selected(())

    def test_rebuilt_geometry_and_obsolete_indices_are_never_reused(self):
        a=self.app;c=self.c;self.select_rows(0)
        rebuilt=generate(a.family,a.design.values)
        a.canvas.set_design(rebuilt);a.design=rebuilt;c.refreshed(rebuilt)
        self.assert_selected(())
        self.select_rows(0);c.select((len(a.design.parts),))
        self.assertEqual(c.selected,());self.assertEqual(a.canvas.selected_indices,())
        self.assertFalse(c.current());self.assertIsNone(c.revision)


if __name__=='__main__':unittest.main()
