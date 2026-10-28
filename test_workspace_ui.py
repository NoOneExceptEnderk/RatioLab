"""Technical workspace behavior and calculated results; widget tests need GTK."""
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import os
from unittest.mock import patch
import unittest
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, Gio, GLib
from geometry import FAMILIES, generate
import app as module
import gui_workflow
from result_controls import items


class ResultSummaryTests(unittest.TestCase):
    def test_reducer_results_use_signed_ratio_and_nominal_speed(self):
        for family in FAMILIES:
            d = generate(family)
            values = items(d)
            self.assertEqual(len(values), 3)
            self.assertFalse(any('torque' in v[0].lower() for v in values))
            if 'signed_ratio' in d.analysis:
                self.assertEqual(float(values[0][1]), d.analysis['signed_ratio'])
                self.assertAlmostEqual(float(values[1][1]), d.analysis['output']['rpm'], places=2)
            else:
                self.assertEqual(values[0][0], 'Pitch diameter')
                self.assertAlmostEqual(float(values[0][1]), 2*d.analysis['gear']['pitch_radius'], places=3)

    def test_envelope_is_the_existing_generator_value(self):
        self.assertEqual(items(generate('planetary'))[2][:3], ('Housing diameter','129.40','mm'))
        self.assertEqual(items(generate('cycloidal'))[2][:3], ('Housing diameter','94.00','mm'))
        self.assertEqual(items(generate('parallel'))[2][:3], ('Centre distance','80.000','mm'))


def pump(duration=.1):
    end = time.monotonic()+duration
    context = GLib.MainContext.default()
    while time.monotonic()<end:
        while context.pending():
            context.iteration(False)
        time.sleep(.005)


class WorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            raise unittest.SkipTest('GTK display required')
        cls.folder = TemporaryDirectory()
        cls.environment = patch.dict(os.environ, dict(XDG_CONFIG_HOME=str(Path(cls.folder.name)/'config'), XDG_DATA_HOME=str(Path(cls.folder.name)/'data'), APPDATA=str(Path(cls.folder.name)/'roaming'), LOCALAPPDATA=str(Path(cls.folder.name)/'local')))
        cls.environment.start()
        cls.original_base, cls.original_generated = module.BASE, module.GENERATED
        module.BASE = Path(cls.folder.name)
        module.GENERATED = module.BASE/'exports'
        cls.app = module.ReducerApp()
        cls.app.set_application_id(f'local.solidcraft.reducers.workspacetests.p{os.getpid()}')
        cls.app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        cls.app.register(None)
        cls.app.activate()
        pump(.15)

    @classmethod
    def tearDownClass(cls):
        for window in cls.app.get_windows():
            window.destroy()
        module.BASE, module.GENERATED = cls.original_base, cls.original_generated
        cls.environment.stop()
        cls.folder.cleanup()

    def setUp(self):
        a = self.app
        a.motion_input_invalid = False
        a.load_config_data({'format':'solidcraft-riduttori/1','family':'planetary',
                            'parameters':generate('planetary').values})
        gui_workflow.show_page(a,'geometry')
        pump(.02)

    def test_single_motion_bar_and_separate_cad_menu(self):
        a = self.app
        self.assertIs(a.quick_play, a.motion_play)
        self.assertIs(a.motion_play.get_parent(), a.motion_speed_text.get_parent())
        self.assertTrue(a.send_btn.is_ancestor(a.cad_menu.get_popover()))
        self.assertIs(a.export_menu.get_parent(), a.cad_menu.get_parent())
        self.assertEqual(a.selector.get_model().get_n_items(), 9)
        self.assertEqual(a.geometry_derived['planets'].get_text(),'54')

    def test_bad_assembly_retains_preview_and_highlights_field(self):
        a = self.app
        previous = a.canvas.design
        a.inputs['sun'].set_text('19')
        self.assertFalse(a.export_menu.get_sensitive())
        self.assertFalse(a.refresh())
        self.assertIs(a.canvas.design, previous)
        self.assertEqual(a.inputs['sun'].get_text(),'19')
        self.assertEqual(a.error_field,'sun')
        self.assertTrue(a.field_feedback['sun'].get_visible())
        self.assertFalse(a.send_btn.get_sensitive())
        self.assertIn('Last valid',a.empty.get_text())
        a.inputs['sun'].set_text('18')
        self.assertTrue(a.refresh())
        self.assertTrue(a.export_menu.get_sensitive())
        self.assertFalse(a.field_feedback['sun'].get_visible())

    def test_focus_update_does_not_silently_replace_invalid_text(self):
        a = self.app
        for text in ('0','abc','999'):
            a.inputs['sun'].set_text(text)
            a.inputs['sun'].update()
            self.assertEqual(a.inputs['sun'].get_text(),text)
            self.assertFalse(a.refresh())
            self.assertFalse(a.export_menu.get_sensitive())
        a.inputs['sun'].set_text('18')
        self.assertTrue(a.refresh())

    def test_precise_speed_and_speed_errors_share_validation(self):
        a = self.app
        a.motion_speed_text.set_text('125,375')
        a.motion_speed_text.emit('activate')
        self.assertEqual(a.config()['parameters']['input_rpm'],125.375)
        a.canvas.set_motion_playing(True)
        a.canvas.motion_phase=1.4
        a.motion_speed_text.set_text('72.125')
        a.motion_speed_text.emit('activate')
        self.assertTrue(a.canvas.motion_playing)
        self.assertEqual(a.canvas.motion_phase,1.4)
        a.motion_speed_text.set_text('nan')
        a.motion_speed_text.emit('activate')
        self.assertTrue(a.motion_rate_error.get_visible())
        self.assertFalse(a.export_menu.get_sensitive())
        self.assertFalse(a.canvas.motion_playing)
        self.assertEqual(a.error_field,'input_rpm')
        a.motion_speed_text.set_text('1500')
        a.motion_speed_text.emit('activate')
        self.assertTrue(a.export_menu.get_sensitive())

    def test_linked_dimensions_explain_source_without_changing_page(self):
        a = self.app
        gui_workflow.show_page(a,'assembly')
        a.values['planetary'].update(bearing_mode='shaft',bearing='626')
        a.make_fields()
        self.assertEqual(a.fields.get_visible_child_name(),'assembly')
        self.assertFalse(a.inputs['bore'].get_sensitive())
        box,note = a.linked_notes['bore']
        self.assertTrue(box.get_visible())
        self.assertIn('626',note.get_text())
        gui_workflow.show_page(a,'geometry')
        gui_workflow.reveal_source(a,'bore')
        self.assertEqual(a.fields.get_visible_child_name(),'assembly')
        self.assertTrue(a.sections['bearings'][0].get_expanded())

    def test_panel_rebuild_keeps_scroll_and_advanced_section(self):
        a = self.app
        a.load_config_data({'format':'solidcraft-riduttori/1','family':'cycloidal',
                            'parameters':generate('cycloidal',{'variant':'dual'}).values})
        # Remap to a known size: changing the default on a mapped window is
        # only a WM hint. Verify the resulting actual viewport still overflows.
        a.win.set_visible(False)
        a.win.set_default_size(1280,740)
        a.win.present()
        a.advanced_expander.set_expanded(True)
        pump(.2)
        adj=a.page_scrolls['geometry'].get_vadjustment()
        self.assertGreater(adj.get_upper()-adj.get_page_size(),100)
        adj.set_value(100)
        before=adj.get_value()
        a.make_fields()
        pump(.15)
        self.assertTrue(a.advanced_expander.get_expanded())
        self.assertEqual(a.fields.get_visible_child_name(),'geometry')
        self.assertAlmostEqual(adj.get_value(),before,delta=1)


if __name__=='__main__':
    unittest.main()
