# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
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
            elif family == 'differential':
                self.assertEqual(values[0][0], 'Carrier tilt')
                self.assertEqual(values[1][0], 'Output spin')
                self.assertEqual(float(values[0][1]), d.analysis['kinematics']['rates_rpm']['carrier'])
                self.assertEqual(float(values[1][1]), d.analysis['kinematics']['rates_rpm']['output_spin'])
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
        self.assertEqual(a.selector.get_model().get_n_items(), len(FAMILIES))
        self.assertEqual(a.geometry_derived['planets'].get_text(),'54')

    def test_differential_independent_signed_speeds_demo_modes_and_actual_tick(self):
        from math import pi
        a=self.app
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='differential',
                               parameters=generate('differential',dict(input_rpm=-7.5,input_b_rpm=17.25)).values))
        self.assertIsNotNone(a.design,a.status.get_text())
        self.assertEqual(a.motion_caption.get_text(),'Input A speed')
        self.assertTrue(a.io_frame.get_visible())
        self.assertEqual(a.read_values()['input_rpm'],-7.5)
        self.assertEqual(a.read_values()['input_b_rpm'],17.25)
        self.assertFalse(a.study.get_visible())
        for mode,expected in [('tilt',(12,0)),('spin',(0,-12)),('combined',(6,-6))]:
            a.io_mode_buttons[mode].emit('clicked')
            q=a.design.analysis['kinematics']['rates_rpm']
            self.assertEqual((q['carrier'],q['output_spin']),expected)
        a.rebuild_options(dict(input_rpm=0,input_b_rpm=12))
        class Clock:
            def __init__(self,t):self.t=t
            def get_frame_time(self):return self.t
        a.canvas.reset_motion()
        a.canvas.set_motion_playing(True)
        a.canvas.on_motion_tick(a.canvas,Clock(0))
        a.canvas.on_motion_tick(a.canvas,Clock(1000000))
        a.canvas.set_motion_playing(False)
        self.assertAlmostEqual(a.canvas.motion_phase,12*2*pi/60)
        # Either speed can change without jumping back to the initial pose.
        phase=a.canvas.motion_phase
        matrices=[a.canvas.motion_plan.matrix(i,phase) for i in range(len(a.design.parts))]
        a.inputs['input_b_rpm'].set_text('7.125')
        self.assertTrue(a.refresh())
        self.assertEqual(a.design.values['input_b_rpm'],7.125)
        self.assertEqual(a.canvas.motion_phase,phase)
        for i,before in enumerate(matrices):
            for x,y in zip(before,a.canvas.motion_plan.matrix(i,phase)):self.assertAlmostEqual(x,y,places=10)
        matrices=[a.canvas.motion_plan.matrix(i,phase) for i in range(len(a.design.parts))]
        a.motion_speed_text.set_text('-19.25')
        a.motion_speed_text.emit('activate')
        self.assertEqual(a.design.values['input_rpm'],-19.25)
        for i,before in enumerate(matrices):
            for x,y in zip(before,a.canvas.motion_plan.matrix(i,phase)):self.assertAlmostEqual(x,y,places=10)
        # Interference phases use the nominal rate plan, then restore live angles.
        from motion import build_plan, IDENTITY
        live=a.canvas.motion_plan
        a.canvas.show_inspection(.9,(0,2))
        nominal=build_plan(a.design)
        for i in range(len(a.design.parts)):
            self.assertEqual(a.canvas.motion_plan.matrix(i,.9),nominal.matrix(i,.9))
        a.canvas.clear_inspection()
        self.assertIs(a.canvas.motion_plan,live)
        # A selected-package nominal snapshot restores the same live angle plan.
        a.components.select((0,2))
        for inspecting in (False,True):
            if inspecting:a.canvas.show_inspection(.9,(0,2))
            with patch.object(a,'refresh',return_value=True),patch.object(a,'background') as worker:
                a.components.export('package')
            self.assertTrue(worker.called,a.status.get_text())
            self.assertEqual(a.canvas.inspection_phase,.9 if inspecting else None)
            a.canvas.clear_inspection()
            self.assertIs(a.canvas.motion_plan,live)
            self.assertEqual(a.canvas.motion_phase,phase)
        for i,before in enumerate(matrices):
            for x,y in zip(before,a.canvas.motion_plan.matrix(i,phase)):self.assertAlmostEqual(x,y,places=10)
        a.canvas.reset_motion()
        for i in range(len(a.design.parts)):self.assertEqual(a.canvas.motion_plan.matrix(i,0),IDENTITY)
        a.combination_search.open()
        self.assertFalse(a.combination_search.run_button.get_sensitive())
        self.assertIn('single fixed input/output ratio',a.combination_search.unavailable)
        a.combination_search.window.close()
        self.assertNotIn('input_torque',a.inputs)
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='planetary',parameters=generate('planetary').values))
        self.assertNotEqual(a.io_frame.get_label(),'Two independent inputs')

    def test_differential_construction_selectors_visibility_derived_counts_and_config(self):
        from differential_wrist import OUTPUT_INTERFACES,CARRIER_STYLES,RATIO_MODES
        a=self.app
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='differential',
                               parameters=generate('differential',dict(output_teeth=31)).values))
        def choose(key,value,choices):
            a.differential_selectors[key].set_selected(list(choices).index(value))
            self.assertIsNotNone(a.design,a.status.get_text())
        choose('output_interface','hollow',OUTPUT_INTERFACES)
        for key in ('flange_radius','bolt_count','bolt_diameter'):self.assertNotIn(key,a.inputs)
        for key in ('passage_diameter','output_extension'):self.assertIn(key,a.inputs)
        self.assertNotIn('carrier_bolt_diameter',a.inputs)

        a.inputs['passage_diameter'].set_text('6')
        a.inputs['output_extension'].set_text('19')
        self.assertTrue(a.refresh())
        choose('carrier_style','split',CARRIER_STYLES)
        self.assertIn('carrier_bolt_diameter',a.inputs)
        choose('ratio_mode','spin_2_1',RATIO_MODES)
        self.assertEqual(a.design.values['output_teeth'],48)
        self.assertFalse(a.inputs['output_teeth'].get_sensitive())
        self.assertTrue(a.linked_notes['output_teeth'][0].get_visible())
        self.assertIn('Custom tooth counts',a.linked_notes['output_teeth'][1].get_text())
        gui_workflow.reveal_source(a,'output_teeth')
        self.assertEqual(a.fields.get_visible_child_name(),'geometry')
        choose('ratio_mode','custom',RATIO_MODES)
        self.assertTrue(a.inputs['output_teeth'].get_sensitive())
        self.assertEqual(a.design.values['output_teeth'],31,'The earlier custom count must survive preset exploration')
        saved=a.config()
        for key,wanted in (('output_interface','hollow'),('carrier_style','split'),('ratio_mode','custom')):
            self.assertEqual(saved['parameters'][key],wanted)
            self.assertEqual(a.option_values[key],wanted)
            self.assertEqual(a.read_values()[key],wanted)
        a.load_config_data(saved)
        self.assertEqual(a.config(),saved)
        self.assertEqual(a.design.values['passage_diameter'],6)
        self.assertEqual(a.design.analysis['wrist_construction']['output_extension_mm'],19)
        choose('output_interface','solid',OUTPUT_INTERFACES)
        self.assertNotIn('passage_diameter',a.inputs)
        self.assertFalse(next(p for p in a.design.parts if p.name=='Shaft_output').holes)
        choose('output_interface','flange',OUTPUT_INTERFACES)
        for key in ('passage_diameter','output_extension'):self.assertNotIn(key,a.inputs)
        for key in ('flange_radius','bolt_count','bolt_diameter'):self.assertIn(key,a.inputs)
        choose('carrier_style','open',CARRIER_STYLES)
        self.assertNotIn('carrier_bolt_diameter',a.inputs)

    def test_differential_spiral_controls_visibility_editing_and_saved_hand(self):
        a=self.app
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='differential',
                               parameters=generate('differential',dict(variant='spiral',spiral_angle=27.5,spiral_hand=-1)).values))
        self.assertIsNotNone(a.design,a.status.get_text())
        self.assertTrue(a.variant_box.get_visible())
        self.assertIn('spiral_angle',a.inputs)
        self.assertTrue(a.inputs['spiral_angle'].get_sensitive())
        self.assertEqual(a.differential_selectors['spiral_hand'].get_selected(),0)
        a.inputs['spiral_angle'].set_text('12.75')
        self.assertTrue(a.refresh())
        a.differential_selectors['spiral_hand'].set_selected(1)
        self.assertEqual(a.design.values['spiral_angle'],12.75)
        self.assertEqual(a.design.values['spiral_hand'],1)
        saved=a.config()
        a.load_config_data(saved)
        self.assertEqual(a.config(),saved)
        self.assertGreater(len(a.design.parts[0].stations),2)
        a.variant_selector.set_selected(0)
        self.assertIsNotNone(a.design,a.status.get_text())
        self.assertNotIn('spiral_angle',a.inputs)
        self.assertNotIn('spiral_hand',a.differential_selectors)
        self.assertEqual(len(a.design.parts[0].stations),2)
        a.variant_selector.set_selected(1)
        self.assertEqual(a.design.values['spiral_angle'],12.75)
        self.assertEqual(a.design.values['spiral_hand'],1)

    def test_classic_differential_carrier_boundary_controls_motion_continuity_and_config(self):
        from differential_wrist import CONFIGURATIONS
        from motion import IDENTITY
        from math import pi
        a=self.app
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='differential',
                               parameters=generate('differential',dict(configuration='classic',output_interface='hollow')).values))
        self.assertIsNotNone(a.design,a.status.get_text())
        self.assertEqual(a.motion_caption.get_text(),'Carrier input speed')
        self.assertIn('output_difference_rpm',a.inputs)
        self.assertNotIn('input_b_rpm',a.inputs)
        self.assertNotIn('output_shaft',a.inputs)
        self.assertNotIn('output_extension',a.inputs)
        self.assertIn('spider_pin_diameter',a.inputs)
        self.assertIn('spider_clearance',a.inputs)
        self.assertIn('carrier_bolt_diameter',a.inputs)
        self.assertIn('Side output',a.input_labels['input_shaft'])
        for mode,wanted in (('equal',(12,12)),('a_held',(0,24)),('counterrotate',(-12,12))):
            a.io_mode_buttons[mode].emit('clicked')
            q=a.design.analysis['kinematics']['rates_rpm']
            self.assertEqual((q['side_a'],q['side_b']),wanted)
        class Clock:
            def __init__(self,t):self.t=t
            def get_frame_time(self):return self.t
        a.canvas.reset_motion();a.canvas.set_motion_playing(True)
        a.canvas.on_motion_tick(a.canvas,Clock(0));a.canvas.on_motion_tick(a.canvas,Clock(1000000))
        a.canvas.set_motion_playing(False)
        self.assertAlmostEqual(a.canvas.motion_phase,12*2*pi/60)
        carrier=next(i for i,p in enumerate(a.design.parts) if p.name=='Pin_spider')
        self.assertEqual(a.canvas.motion_plan.matrix(carrier,a.canvas.motion_phase),IDENTITY)
        phase=a.canvas.motion_phase
        before=[a.canvas.motion_plan.matrix(i,phase) for i in range(len(a.design.parts))]
        a.inputs['output_difference_rpm'].set_text('7.125');self.assertTrue(a.refresh())
        a.motion_speed_text.set_text('-19.25');a.motion_speed_text.emit('activate')
        self.assertEqual(a.design.values['input_rpm'],-19.25)
        for i,old in enumerate(before):
            for x,y in zip(old,a.canvas.motion_plan.matrix(i,phase)):self.assertAlmostEqual(x,y,places=10)
        saved=a.config();a.load_config_data(saved);self.assertEqual(a.config(),saved)
        a.rebuild_options(dict(input_rpm=0,output_difference_rpm=0,input_b_rpm=99))
        a.canvas.reset_motion();a.canvas.set_motion_playing(True)
        a.canvas.on_motion_tick(a.canvas,Clock(0));a.canvas.on_motion_tick(a.canvas,Clock(1000000))
        a.canvas.set_motion_playing(False)
        self.assertEqual(a.canvas.motion_phase,0,'The inactive legacy B speed must not drive classic playback')
        a.differential_selectors['configuration'].set_selected(list(CONFIGURATIONS).index('wrist'))
        self.assertEqual(a.motion_caption.get_text(),'Input A speed')
        self.assertIn('input_b_rpm',a.inputs)
        self.assertNotIn('output_difference_rpm',a.inputs)
        self.assertNotIn('spider_pin_diameter',a.inputs)

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
