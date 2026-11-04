# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Actual GTK/OpenGL hypoid selection, project edits and standalone export."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk,Gio
import app as module
from geometry import generate
from test_parallel_multistage_gui import wait_until


class HypoidGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check() or Gdk.Display.get_default() is None:raise unittest.SkipTest('GTK display required')
        cls.temporary=TemporaryDirectory(prefix='ratiolab-hypoid-gui-');cls.root=Path(cls.temporary.name)
        cls.environment=patch.dict(os.environ,dict(XDG_CONFIG_HOME=str(cls.root/'config'),XDG_DATA_HOME=str(cls.root/'data'),
            APPDATA=str(cls.root/'roaming'),LOCALAPPDATA=str(cls.root/'local')))
        cls.environment.start();cls.app=module.ReducerApp()
        cls.app.set_application_id(f'local.ratiolab.hypoidtests.p{os.getpid()}')
        cls.app.set_flags(Gio.ApplicationFlags.NON_UNIQUE);cls.app.register(None);cls.app.activate()
        wait_until(lambda:cls.app.canvas.gl is not None or cls.app.canvas.failure)
        if cls.app.canvas.failure:raise AssertionError(cls.app.canvas.failure)

    @classmethod
    def tearDownClass(cls):
        cls.app.canvas.set_motion_playing(False)
        for window in cls.app.get_windows():window.destroy()
        cls.environment.stop();cls.temporary.cleanup()

    def setUp(self):
        a=self.app;a.canvas.set_motion_playing(False)
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='hypoid',parameters=generate('hypoid').values))
        a.output_dir=self.root/self._testMethodName;a.output_dir.mkdir()
        wait_until(lambda:not a.pending and a.canvas.get_mapped())

    def test_select_family_ports_result_cards_and_precise_save(self):
        a=self.app
        self.assertEqual(a.selector.get_selected_item().get_string(),'Hypoid gear pair')
        self.assertEqual(a.design.values['variant'],'generated')
        self.assertFalse(a.stage_box.get_visible())
        self.assertEqual(len(a.design.parts),2)
        self.assertTrue(a.canvas.motion_plan.supported)
        a.canvas.set_motion_playing(True)
        self.assertTrue(a.canvas.motion_playing)
        before=a.canvas.motion_phase
        wait_until(lambda:a.canvas.motion_phase!=before)
        a.canvas.set_motion_playing(False)
        self.assertIn('output_bore',a.inputs)
        from result_controls import items
        self.assertEqual(items(a.design)[2][0],'Shaft offset')
        a.inputs['offset'].set_text('-1.1234567890123');self.assertTrue(a.refresh())
        a.io_mode_buttons['reverse'].set_active(True)
        self.assertEqual(a.design.analysis['signed_ratio'],-.5)
        self.assertEqual(a.design.values['offset'],-1.1234567890123)
        path=a.output_dir/'hypoid.config.json';self.assertTrue(a.save_project(path=path))
        config=json.loads(path.read_text());a.load_config_data(config)
        self.assertEqual(a.config(),config)
        self.assertEqual(a.design.parts[0].port['role'],'output')

    def test_invalid_draft_undo_and_speed_only_gpu_retention(self):
        a=self.app
        a.inputs['offset'].set_text('1.1234567890123');self.assertTrue(a.refresh());a.project_changed()
        a.document.barrier()
        accepted=a.canvas.design
        a.inputs['offset'].set_text('4');self.assertFalse(a.refresh());a.project_changed()
        self.assertIs(a.canvas.design,accepted)
        self.assertFalse(a.export_menu.get_sensitive())
        a.undo_project();wait_until(lambda:not a.pending)
        self.assertTrue(a.export_menu.get_sensitive())
        self.assertEqual(a.design.values['offset'],1.1234567890123)
        parts=list(a.design.parts)
        a.motion_speed_text.set_text('-31.1234567890123');a.motion_speed_text.emit('activate')
        wait_until(lambda:not a.pending)
        self.assertEqual(a.design.parts[1].port['rpm'],15.56172839450615)
        self.assertTrue(all(x.outer is y.outer for x,y in zip(parts,a.design.parts)))

    def test_real_standalone_step_and_package_keep_two_parts(self):
        a=self.app
        with patch.object(module,'Client',side_effect=AssertionError('Standalone export connected to CAD')):
            for action in (a.export_step,a.export):
                action();wait_until(lambda:not a.busy)
        step=next(a.output_dir.glob('*.step-export'))
        self.assertEqual(len(list((step/'step-parts').glob('*.step'))),2)
        package=next(a.output_dir.glob('*.package'))
        self.assertTrue(json.loads((package/'manifest.json').read_text())['complete'])
        self.assertTrue((package/'preview.png').read_bytes().startswith(b'\x89PNG'))
        evidence=os.environ.get('RATIOLAB_HYPOID_EVIDENCE')
        if evidence:
            import shutil
            target=Path(evidence);target.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(package/'preview.png',target/'native-hypoid-preview.png')



if __name__=='__main__':unittest.main()
