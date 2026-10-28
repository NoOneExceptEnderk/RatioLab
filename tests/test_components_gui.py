# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Real GTK/GL integration: surface clicks, list, view state and snapshot export."""
import os,json,math,time,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk,Gio
import app as module
from geometry import generate
from component_geometry import project
from test_interference_gui import pump,wait_until


class ComponentGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check() or Gdk.Display.get_default() is None:raise unittest.SkipTest('GTK display required')
        cls.temp=TemporaryDirectory(prefix='ratiolab-components-gui-');root=Path(cls.temp.name)
        cls.env=patch.dict(os.environ,dict(XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'),APPDATA=str(root/'roaming'),LOCALAPPDATA=str(root/'local')));cls.env.start()
        cls.app=module.ReducerApp();cls.app.set_application_id(f'local.solidcraft.reducers.componenttests.p{os.getpid()}');cls.app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        cls.app.register(None);cls.app.activate();pump(.2)

    @classmethod
    def tearDownClass(cls):
        for w in cls.app.get_windows():w.destroy()
        pump();cls.env.stop();cls.temp.cleanup()

    def setUp(self):
        a=self.app;a.components.restore();a.interference.restore_view();a.canvas.reset_motion()
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='parallel',parameters=generate('parallel',dict(input_rpm=60)).values));pump(.08)
        for key in ('support','housing','exploded','section'):a.view_options[key].set_active(False)
        a.components.open();self.c=a.components;self.c.measure.set_active(False);a.canvas.view('top');pump(.08)
        a.output_dir=Path(self.temp.name)/f'exports-{self.id().split(".")[-1]}'

    def xy(self,q):
        c=self.app.canvas;s=c.scene
        return project(q,s.center,s.radius,c.zoom,c.yaw,c.tilt,c.get_width(),c.get_height())

    def click(self,q,multi=False):self.app.canvas.emit('component-click',*self.xy(q),multi);pump(.02)

    def test_pick_list_multiselect_empty_drag_and_document_unchanged(self):
        a=self.app;c=self.c;token=a.document.token;states=len(a.document.states);config=a.config()
        self.click((10,0,10));self.assertEqual(c.selected,(0,))
        a.canvas.emit('component-click',*self.xy((90,0,10)),True);self.assertEqual(c.selected,(0,1))
        c.list.unselect_all();c.list.select_row(c.list.get_row_at_index(2));self.assertEqual(c.selected,(2,))
        class Gesture:
            def get_current_event_state(self):return Gdk.ModifierType(0)
        a.canvas.drag_begin(None,0,0);a.canvas.drag_update(None,20,0);a.canvas.component_click(Gesture(),1,0,0);self.assertEqual(c.selected,(2,))
        a.canvas.drag_begin(None,0,0);a.canvas.component_click(Gesture(),1,0,0);self.assertEqual(c.selected,())
        self.assertEqual(a.document.token,token);self.assertEqual(len(a.document.states),states);self.assertEqual(a.config(),config)
        self.assertIsNotNone(a.canvas.gl);self.assertIsNone(a.canvas.failure)

    def test_measure_coordinates_visible_markers_and_filter_clear(self):
        a=self.app;c=self.c;c.measure.set_active(True)
        self.click((10,0,10));self.click((0,10,10));self.assertEqual(len(c.points),2)
        for got,expected in zip(c.points[0][1],(10,0,10)):self.assertAlmostEqual(got,expected,places=7)
        self.assertIn('14.142136 mm',c.measure_text.get_text());self.assertIn('Nominal assembly pose',c.measure_text.get_text())
        oldpoints=list(c.points);oldxy=self.xy(c.points[0][1]);events=[]
        handler=a.canvas.connect('view-changed',lambda _,name:events.append(name))
        a.canvas.scroll(None,0,-1);pump();a.canvas.disconnect(handler)
        self.assertTrue(events);self.assertEqual(c.points,oldpoints);self.assertNotEqual(self.xy(c.points[0][1]),oldxy)
        data=[];a.canvas.capture_png(lambda image,error:data.append((image,error)));self.assertIsNone(data[0][1])
        c.window.present();pump(.05)
        if os.environ.get('RATIOLAB_COMPONENT_ARTIFACT'):Path(os.environ['RATIOLAB_COMPONENT_ARTIFACT']).write_bytes(data[0][0])
        a.view_options['section'].set_active(True);self.assertFalse(c.points)
        a.view_options['section'].set_active(False);a.view_options['support'].set_active(True)
        c.measure.set_active(False);c.select((2,));c.isolate();c.measure.set_active(True)
        shaft=a.design.parts[2];self.click((shaft.center[0]+2,shaft.center[1],shaft.z+shaft.width));self.assertTrue(c.points)
        c.restore();self.assertTrue(c.points)
        a.view_options['support'].set_active(False);self.assertFalse(c.points)

    def test_isolate_restore_hidden_source_and_interference_continuity(self):
        a=self.app;c=self.c;c.select((2,));c.isolate();self.assertEqual(c.visible_indices(),(2,));self.assertTrue(a.canvas.show_support)
        c.restore();self.assertFalse(a.canvas.show_support);self.assertIsNone(a.canvas.isolated_indices)
        a.view_options['exploded'].set_active(True);c.isolate();self.assertTrue(a.canvas.exploded)
        a.canvas.show_inspection(.4,(0,1));self.assertIsNone(c.saved_filters);self.assertIsNone(a.canvas.isolated_indices)
        a.interference.restore_view();self.assertIsNone(a.canvas.inspection_phase)

    def test_rigid_motion_freeze_measure_clear_and_nonrigid_reason(self):
        a=self.app;c=self.c;a.canvas.motion_enabled=True;a.canvas.motion_phase=.4;a.canvas.queue_render();pump(.08)
        a.canvas.set_motion_playing(True);pump(.08);self.click((10,0,10));self.assertFalse(a.canvas.motion_playing);self.assertTrue(c.selected)
        c.measure.set_active(True);self.click((10,0,10));self.assertTrue(c.points)
        a.canvas.set_motion_playing(True);self.assertFalse(c.points);a.canvas.reset_motion()
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='harmonic',parameters=generate('harmonic').values));pump(.08)
        a.canvas.motion_enabled=True;a.canvas.motion_phase=.5;c.clicked(a.canvas,100,100)
        self.assertIn('flex/warp',c.summary.get_text());self.assertFalse(c.selected)
        c.nominal();self.assertFalse(a.canvas.motion_enabled)
        # The nominal flexspline remains inspectable from the identified list.
        c.select((0,));self.assertEqual(c.selected,(0,));self.assertIn('XYZ bounds',c.detail.get_text())

    def test_revision_identity_raw_invalid_refresh_and_undo(self):
        a=self.app;c=self.c;c.select((0,));token=a.document.token;a.refresh();self.assertEqual(c.selected,(0,));self.assertEqual(a.document.token,token)
        a.inputs['module'].set_text('-');self.assertFalse(c.selected);self.assertIsNone(c.revision)
        pump(.15);self.assertIsNone(a.design);self.assertFalse(c.export_buttons[0].get_sensitive())
        a.undo_project();pump(.08);self.assertIsNotNone(a.design);self.assertFalse(c.selected)
        c.select((0,));old=a.document.token;a.load_config_data(a.config());self.assertNotEqual(a.document.token[0],old[0]);self.assertFalse(c.selected)

    def test_selected_package_real_worker_nominal_scope_and_measure_restore(self):
        a=self.app;c=self.c;c.select((0,1));a.view_options['exploded'].set_active(True);a.view_options['section'].set_active(True)
        # Set a visible measurement in the exploded view; export must restore it.
        c.points=[(0,(10,-5,10)),(1,(80,-5,10))];c.pose=c.pose_key();c.measure_text.set_text('Saved displayed measurement')
        points=list(c.points);pose=c.pose;token=a.document.token
        c.export('package');self.assertTrue(wait_until(lambda:not a.busy,15));self.assertTrue(a.canvas.exploded);self.assertTrue(a.canvas.section)
        self.assertEqual(c.points,points);self.assertEqual(c.pose,pose);self.assertEqual(c.measure_text.get_text(),'Saved displayed measurement');self.assertEqual(a.document.token,token)
        targets=list(a.output_dir.glob('*.selected-package'));self.assertEqual(len(targets),1)
        target=targets[0];manifest=json.loads((target/'manifest.json').read_text());self.assertEqual(manifest['scope']['source_indices'],[1,2]);self.assertFalse(manifest['complete_assembly'])
        self.assertEqual(len(list((target/'step-parts').glob('*.step'))),2);self.assertEqual(len(list((target/'model.stl-parts').glob('*.stl'))),2)
        info=json.loads((target/'step-info.json').read_text());self.assertEqual([p['index'] for p in info['components']],[1,2])
        self.assertTrue((target/'preview.png').stat().st_size>1000)

    def test_applicability_visible_disabled_and_linked_fields(self):
        a=self.app
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='internal',parameters=generate('internal',dict(bearing_mode='shaft',hardware_mode='standard')).values));pump(.08)
        self.assertTrue(a.sections['bearings'][0].get_visible());self.assertTrue(a.sections['hardware'][0].get_visible());self.assertFalse(a.inputs['bore'].get_sensitive())
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='worm',parameters=generate('worm').values));pump(.08)
        self.assertIn('unavailable',a.mount_help.get_text())
        for key in ('bearings','hardware'):
            expander,body=a.sections[key];self.assertTrue(expander.get_visible());widgets=[];child=body.get_first_child()
            while child:widgets.append(child);child=child.get_next_sibling()
            self.assertTrue(any(isinstance(w,Gtk.Button) and not w.get_sensitive() for w in widgets));self.assertTrue(any(isinstance(w,Gtk.Label) and 'unavailable' in w.get_text() for w in widgets))

    def test_option_rebuild_legacy_bolts_catalog_warnings_history_and_invalid(self):
        a=self.app;c=self.c
        values=generate('parallel').values;values['hardware_bolts']=True
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='parallel',parameters=values))
        c.select((0,));oldindex=a.document.index
        # Exercise the actual dropdown callback, which normalizes ONLY the
        # unavailable bolts field on legacy configs.
        dropdown=a.sections['hardware'][1].get_first_child().get_next_sibling()
        self.assertIsInstance(dropdown,Gtk.DropDown);dropdown.set_selected(1)
        self.assertTrue(c.current());self.assertEqual(c.revision,a.document.token);self.assertFalse(c.selected)
        self.assertFalse(a.design.values['hardware_bolts']);self.assertEqual(a.document.index,oldindex+1)
        c.select((0,));self.assertEqual(c.selected,(0,));a.undo_project();self.assertTrue(c.current());self.assertTrue(a.design.values['hardware_bolts']);a.redo_project();self.assertTrue(c.current());self.assertFalse(a.design.values['hardware_bolts'])
        a.rebuild_options(dict(bearing_mode='shaft',bearing='624'));self.assertTrue(c.current())
        self.assertIn('unavailable',a.hardware_warning_labels['keys'].get_text());self.assertIn('Internal bearing',a.hardware_warning_labels['retaining'].get_text())
        a.inputs['module'].set_text('-');a.rebuild_options(dict(fit='custom'))
        self.assertIsNone(a.design);self.assertFalse(c.current());self.assertIsNone(c.revision)

    def test_search_apply_rebind_busy_sensitivity_and_long_selection(self):
        a=self.app;c=self.c;search=a.combination_search
        from combination_search import Settings
        search.open();search.start(Settings(target=3,tolerance_percent=0),{'pinion':(21,),'wheel':(63,)})
        self.assertTrue(wait_until(lambda:search.cancel is None,10));proposal=next(p for p in search.result.proposals if p.changes)
        self.assertTrue(search.apply(proposal));self.assertTrue(c.current());self.assertEqual(c.revision,a.document.token)
        c.select((0,));self.assertTrue(c.export_buttons[0].get_sensitive())
        from threading import Event
        release=Event();a.background(lambda:release.wait(5) or 'done')
        self.assertFalse(c.export_buttons[0].get_sensitive());release.set();self.assertTrue(wait_until(lambda:not a.busy,10));self.assertTrue(c.export_buttons[0].get_sensitive())
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='parallel',parameters=generate('parallel',dict(bearing_mode='shaft',hardware_mode='standard')).values))
        c.select(range(len(a.design.parts)));pump(.1)
        self.assertLessEqual(c.window.get_height(),760);self.assertTrue(c.export_buttons[0].is_visible())
        search.window.close();pump()

if __name__=='__main__':unittest.main()
