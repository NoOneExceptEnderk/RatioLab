# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Readable component labels retain source identity and reachable export actions."""
from copy import deepcopy
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk,Gio,GLib
import app as module
import bom
from components_ui import component_title
from geometry import generate


def wait_until(predicate,seconds=3):
    end=time.monotonic()+seconds;context=GLib.MainContext.default()
    while time.monotonic()<end:
        if predicate():return True
        if context.pending():context.iteration(False)
        else:time.sleep(.002)
    return bool(predicate())


def pump(seconds=.05):
    end=time.monotonic()+seconds;context=GLib.MainContext.default()
    while time.monotonic()<end:
        if context.pending():context.iteration(False)
        else:time.sleep(.002)


class ComponentTitleTests(unittest.TestCase):
    def test_stage_number_variant_and_acronym_are_preserved(self):
        cases={
            'S1_Pinion':'Stage 1 · Pinion',
            'S2_PlanetCarrier_lower':'Stage 2 · Lower planet carrier',
            'Disc_cycloidal_2':'Cycloidal disc 2',
            'Bearing_eccentric_1_envelope':'Eccentric bearing 1 · envelope',
            'Generator_wave_prescribed':'Wave generator · prescribed',
            'Circular_spline_generated':'Circular spline · generated',
            'Shaft_input_A':'Input shaft A',
            'Screw_ZA':'Screw ZA',
            'Retainer_ring_upper':'Upper retainer ring',
        }
        for name,expected in cases.items():
            with self.subTest(name=name):
                part=SimpleNamespace(name=name,port={'label':'Do not substitute this generic label'})
                before=deepcopy(part.__dict__)
                self.assertEqual(component_title(part),expected)
                self.assertEqual(part.__dict__,before)

    def test_compound_planets_keep_distinct_numbers_rims_hubs_and_layers(self):
        parts=[SimpleNamespace(name=name,port=dict(label='Compound planet',**port)) for name,port in (
            ('Compound_1_rim1',{'layer':1}),('Compound_1_rim2',{'layer':2}),
            ('Compound_1_hub',{}),('Compound_2_rim1',{'layer':1}))]
        self.assertEqual([component_title(p) for p in parts],[
            'Compound planet 1 · rim 1 · layer 1','Compound planet 1 · rim 2 · layer 2',
            'Compound planet 1 · hub','Compound planet 2 · rim 1 · layer 1'])


class ComponentLabelGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            raise unittest.SkipTest('GTK display required')
        cls.temp=TemporaryDirectory(prefix='ratiolab-component-labels-');root=Path(cls.temp.name)
        cls.env=patch.dict(os.environ,dict(RATIOLAB_UPDATE_CHECK='0',
            XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'),
            XDG_CACHE_HOME=str(root/'cache'),APPDATA=str(root/'roaming'),LOCALAPPDATA=str(root/'local')))
        cls.env.start();cls.app=module.ReducerApp()
        cls.app.set_application_id(f'local.ratiolab.componentlabels.p{os.getpid()}')
        cls.app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        cls.app.register(None);cls.app.activate();pump(.15)

    @classmethod
    def tearDownClass(cls):
        cls.app.text_size.set_selected(0)
        for window in list(cls.app.get_windows()):window.destroy()
        pump();cls.env.stop();cls.temp.cleanup()

    def setUp(self):
        a=self.app
        if a.tools.expanded:a.tools.restore_workspace()
        if a.components.window:a.components.window.close()
        a.text_size.set_selected(0);a.pick_mode.set_selected(1)
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='parallel',parameters=generate('parallel').values))
        a.components.open();self.c=a.components;self.c.select(());pump(.05)

    def test_real_list_summary_and_details_retain_source_identity(self):
        a=self.app;c=self.c;names=[p.name for p in a.design.parts];token=a.document.token
        row=c.list.get_row_at_index(0);code=bom.part_info(a.design.parts[0])['code']
        self.assertEqual(row.source_index,0)
        self.assertEqual(row.get_child().get_text(),'001 · Stage 1 · Pinion')
        self.assertIn('Source name: S1_Pinion',row.get_tooltip_text())
        self.assertIn('Role: '+a.design.parts[0].role,row.get_tooltip_text())
        self.assertNotIn(code,row.get_child().get_text())
        hidden=c.list.get_row_at_index(2)
        self.assertEqual(hidden.source_index,2);self.assertIn('Input shaft',hidden.get_child().get_text())
        self.assertIn(' · hidden',hidden.get_child().get_text())
        c.list.select_row(row)
        self.assertEqual(c.selected,(0,));self.assertIn('001 Stage 1 · Pinion',c.summary.get_text())
        self.assertNotIn('S1_Pinion',c.summary.get_text())
        detail=c.detail.get_text()
        for text in ('001 Stage 1 · Pinion','Source name: S1_Pinion','role: '+a.design.parts[0].role,
                     'BOM code: '+code,'Nominal sampled XYZ bounds:'):
            self.assertIn(text,detail)
        self.assertEqual([p.name for p in a.design.parts],names);self.assertEqual(a.document.token,token)
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='wolfrom',parameters=generate('wolfrom').values))
        titles={p.name:c.list.get_row_at_index(i).get_child().get_text() for i,p in enumerate(a.design.parts)}
        self.assertIn('Compound planet 1 · rim 1 · layer 1',titles['Compound_1_rim1'])
        self.assertIn('Compound planet 1 · rim 2 · layer 2',titles['Compound_1_rim2'])
        self.assertIn('Compound planet 1 · hub',titles['Compound_1_hub'])
        self.assertEqual(len(set(titles.values())),len(titles))

    def test_bom_code_is_only_computed_for_selected_details(self):
        c=self.c;part=self.app.design.parts[0]
        with patch('bom.part_info',wraps=bom.part_info) as info:
            c.populate();c.update();self.assertEqual(info.call_count,0)
            c.select((0,));self.assertGreater(info.call_count,0)
            self.assertTrue(all(call.args==(part,) for call in info.call_args_list))

    def test_all_selected_export_actions_focus_and_scroll_inside_real_viewport(self):
        a=self.app;c=self.c;a.text_size.set_selected(2)
        monitor=Gdk.Display.get_default().get_monitor_at_surface(a.win.get_surface())
        area=monitor.get_workarea() if hasattr(monitor,'get_workarea') else monitor.get_geometry()
        limit=(min(1280,area.width),min(768,area.height))
        a.win.unfullscreen();a.win.unmaximize();pump(.1);a.win.set_visible(False)
        a.win.set_default_size(*limit);a.win.present();pump(.15);a.win.unmaximize()
        self.assertTrue(wait_until(lambda:not a.win.is_maximized()))
        self.assertTrue(wait_until(lambda:a.win.get_width()<=limit[0] and a.win.get_height()<=limit[1]))
        c.select((0,));token=a.document.token;scene=a.canvas.scene
        self.assertEqual([b.get_label() for b in c.export_buttons],['STEP','STL','DXF / SVG','Package'])
        for expanded in (False,True):
            with self.subTest(expanded=expanded):
                if expanded:
                    a.tools.expand_button.emit('clicked')
                    # The expanded tool fills the preview inside its floating
                    # panel margins, rather than extending to the window edge.
                    self.assertTrue(wait_until(lambda:a.tools.box.get_width()>=a.win.get_width()-32))
                    ok,panel=a.tools.box.compute_bounds(a.preview_overlay)
                    self.assertTrue(ok)
                    self.assertGreaterEqual(panel.get_x(),a.tools.box.get_margin_start()-1)
                    self.assertLessEqual(panel.get_x()+panel.get_width(),
                                         a.preview_overlay.get_width()-a.tools.box.get_margin_end()+1)
                self.assertLessEqual(a.win.get_width(),limit[0]);self.assertLessEqual(a.win.get_height(),limit[1])
                scroll=c.window.scroll;clip=scroll.get_child();adjustment=scroll.get_vadjustment()
                scrolled=False
                for target in c.export_buttons:
                    c.list.grab_focus();adjustment.set_value(0);pump(.03)
                    ok,before=target.compute_bounds(clip);self.assertTrue(ok)
                    below=before.get_y()+before.get_height()>clip.get_height()+1
                    self.assertTrue(target.get_sensitive());self.assertTrue(target.grab_focus())
                    def visible_and_focused():
                        ok,bounds=target.compute_bounds(clip)
                        return (ok and target.has_focus() and bounds.get_x()>=-1 and bounds.get_y()>=-1
                            and bounds.get_x()+bounds.get_width()<=clip.get_width()+1
                            and bounds.get_y()+bounds.get_height()<=clip.get_height()+1)
                    reachable=wait_until(visible_and_focused)
                    ok,bounds=target.compute_bounds(clip)
                    bounds_tuple=(bounds.get_x(),bounds.get_y(),bounds.get_width(),bounds.get_height()) if ok else None
                    self.assertTrue(reachable,
                        f'{target.get_label()} clipped in tool viewport: expanded={expanded}, '
                        f'focused={target.has_focus()}, focus={a.win.get_focus()}, '
                        f'button={bounds_tuple}, clip={clip.get_width()}x{clip.get_height()}, '
                        f'scroll={scroll.get_width()}x{scroll.get_height()}, '
                        f'adjustment={adjustment.get_value()}/{adjustment.get_upper()}/{adjustment.get_page_size()}')
                    self.assertTrue(target.get_mapped())
                    if below:self.assertGreater(adjustment.get_value(),0);scrolled=True
                # At enlarged text in the narrow dock, the real parent scroll
                # must bring its lower actions into view rather than clip them.
                if not expanded:self.assertTrue(scrolled)
                self.assertEqual(c.selected,(0,));self.assertEqual(a.document.token,token);self.assertIs(a.canvas.scene,scene)


if __name__=='__main__':unittest.main()
