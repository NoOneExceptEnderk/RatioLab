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
            elif family == 'rack':
                from math import pi
                travel = 2*pi*d.analysis['rack']['pitch_radius_mm']
                self.assertEqual([v[0] for v in values],
                                 ['Travel per revolution','Linear speed','Working stroke'])
                self.assertEqual([v[2] for v in values], ['mm/rev','mm/s','mm'])
                self.assertAlmostEqual(float(values[0][1]), travel, places=4)
                self.assertAlmostEqual(float(values[1][1]), travel*d.values['input_rpm']/60, places=4)
                self.assertAlmostEqual(float(values[2][1].removeprefix('±')),
                                       d.analysis['rack']['travel_limits_mm'][1], places=4)
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
        # Dispatch one event per turn so the budget and other threads stay live.
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

    def test_family_roundtrip_keeps_default_and_explicit_sidebar_width(self):
        from test_interference_gui import wait_until
        a=self.app
        def allocated(width):
            ready=wait_until(lambda:a.parameter_panel.get_width()==width,3)
            detail=(f'position={a.workspace_paned.get_position()}, '
                    f'max={a.workspace_paned.get_property("max-position")}, '
                    f'width={a.workspace_paned.get_width()}, '
                    f'right_min={a.workspace_paned.get_end_child().measure(Gtk.Orientation.HORIZONTAL,-1)[0]}')
            self.assertTrue(ready,detail)
            self.assertEqual(a.parameter_panel.get_width(),width)
            self.assertTrue(a.canvas.gl)
            self.assertFalse(a.canvas.failure)
        for width in (230,330):
            a.workspace_paned.set_position(width);allocated(width)
            for family in FAMILIES:
                with self.subTest(width=width,family=family):
                    a.load_config_data(dict(format='solidcraft-riduttori/1',family=family,
                                            parameters=generate(family).values))
                    pump(.1);allocated(width)
            a.load_config_data(dict(format='solidcraft-riduttori/1',family='parallel',
                                    parameters=generate('parallel').values))
            pump(.1);allocated(width)
        a.workspace_paned.set_position(230);allocated(230)

    def test_worm_motion_actions_fit_default_and_manual_sidebar_at_all_text_sizes(self):
        from test_interference_gui import wait_until
        a=self.app
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='worm',
                                parameters=generate('worm',dict(worm_static_friction=.2)).values))
        a.motion_connections.emit('clicked')
        self.assertEqual(a.fields.get_visible_child_name(),'motion')
        # Finish focus-loss commits and any accepted geometry request before
        # checking that presentation-only changes preserve object identity.
        a.io_friction_apply.grab_focus()
        self.assertTrue(wait_until(lambda:not a.pending and not a._geometry_waiting
                                  and a.design is not None and a.design.family=='worm',3))
        before=a.project_snapshot(),a.document.token,a.design
        try:
            for scale in (0,1,2):
                a.text_size.set_selected(scale)
                for width in (230,330):
                    with self.subTest(scale=scale,width=width):
                        a.workspace_paned.set_position(width)
                        self.assertTrue(wait_until(lambda:a.parameter_panel.get_width()==width,3),
                                        f'actual={a.parameter_panel.get_width()} position={a.workspace_paned.get_position()}')
                        for button,caption in ((a.io_friction_apply,'Apply coefficient'),
                                               (a.io_friction_clear,'Clear coefficient · unknown')):
                            self.assertEqual(button.get_label(),caption)
                            self.assertTrue(button.get_child().get_wrap())
                            button.grab_focus()
                            self.assertTrue(wait_until(lambda:button.has_focus(),1))
                            pump(.03)
                            self.assertEqual(a.parameter_panel.get_width(),width)
                            ok,bounds=button.compute_bounds(a.parameter_panel)
                            self.assertTrue(ok)
                            self.assertGreaterEqual(bounds.get_x(),0)
                            self.assertLessEqual(bounds.get_x()+bounds.get_width(),width)
                            self.assertFalse(button.get_child().get_layout().is_ellipsized())
                        for button in a.page_buttons.values():
                            self.assertTrue(button.get_visible())
                            self.assertTrue(button.get_parent().get_visible())
                            ok,bounds=button.compute_bounds(a.parameter_panel)
                            self.assertTrue(ok)
                            self.assertGreaterEqual(bounds.get_x(),0)
                            self.assertLessEqual(bounds.get_x()+bounds.get_width(),width)
                            self.assertFalse(button.get_child().get_layout().is_ellipsized())
            self.assertEqual(a.project_snapshot(),before[0])
            self.assertEqual(a.document.token,before[1])
            self.assertIs(a.design,before[2])
            self.assertTrue(a.canvas.gl)
            self.assertFalse(a.canvas.failure)
        finally:
            a.text_size.set_selected(0)
            a.workspace_paned.set_position(230)
            pump(.1)

    def test_preview_fidelity_sidebar_pairs_header_and_visible_rate_slider(self):
        a=self.app
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='parallel',parameters=generate('parallel').values))
        pump(.15)
        self.assertEqual(a.parameter_panel.get_width(),230)
        for first,second in [('pinion','wheel'),('module','width')]:
            self.assertIs(a.field_containers[first].get_parent(),a.field_containers[second].get_parent())
            self.assertTrue(a.field_containers[first].get_parent().has_css_class('parameter-pair'))
        self.assertEqual(a.advanced_expander.get_label(),'Advanced tooth geometry')
        self.assertEqual(a.extra_geometry_expander.get_label(),'All model parameters')
        self.assertTrue(a.undo_button.is_ancestor(a.secondary_toolbar))
        self.assertTrue(a.motion_speed.get_mapped())
        self.assertTrue(a.page_buttons['geometry'].get_visible())
        self.assertEqual(a.project_menu.get_label(),'File')
        a.extra_geometry_expander.set_expanded(True)
        a.geometry_group_boxes['shafts']._section.set_expanded(False)
        a.rebuild_options({});pump(.1)
        self.assertTrue(a.extra_geometry_expander.get_expanded())
        self.assertFalse(a.geometry_group_boxes['shafts']._section.get_expanded())
        a.error_field='bore';gui_workflow.reveal_error(a);pump(.1)
        self.assertTrue(a.extra_geometry_expander.get_expanded())
        self.assertTrue(a.geometry_group_boxes['shafts']._section.get_expanded())
        self.assertTrue(a.inputs['bore'].get_mapped())

    def test_compact_inputs_keep_hover_help_units_and_native_stepping(self):
        from gi.repository import Gtk
        a=self.app
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='parallel',parameters=generate('parallel').values))
        # Verify the unfocused appearance before exercising focused stepping.
        a.appearance_button.grab_focus();pump(.2)
        for key in ('pinion','wheel','module','width'):
            with self.subTest(key=key):
                spin=a.inputs[key];binding=a.parameter_help.bindings[key]
                self.assertEqual(binding.label.get_layout().get_line_count(),1)
                self.assertEqual(spin.get_alignment(),0)
                self.assertFalse(binding.button.get_visible())
                self.assertFalse(binding.button.get_mapped())
                child=spin.get_first_child()
                while child:
                    if isinstance(child,Gtk.Button):self.assertFalse(child.get_visible())
                    child=child.get_next_sibling()
        spin=a.inputs['pinion'];spin.grab_focus();pump(.05)
        buttons=[];child=spin.get_first_child()
        while child:
            if isinstance(child,Gtk.Button):buttons.append(child)
            child=child.get_next_sibling()
        self.assertTrue(buttons and all(button.get_visible() for button in buttons))
        binding=a.parameter_help.bindings['pinion']
        self.assertFalse(binding.button.get_mapped())
        for button in buttons:
            ok,step_bounds=button.compute_bounds(spin);self.assertTrue(ok)
            self.assertGreaterEqual(step_bounds.get_x(),0)
            self.assertLessEqual(step_bounds.get_x()+step_bounds.get_width(),spin.get_width())
        self.assertEqual(a.parameter_panel.get_width(),230)
        before=spin.get_value()
        spin.spin(Gtk.SpinType.STEP_FORWARD,1)
        self.assertEqual(spin.get_value(),before+1)
        a.appearance_button.grab_focus();pump(.3)
        binding=a.parameter_help.bindings['module'];binding.open();pump(.15)
        popup=a.parameter_help.popover
        ok,sidebar=a.parameter_panel.compute_bounds(a.win);self.assertTrue(ok)
        ok,card=popup.get_child().compute_bounds(popup);self.assertTrue(ok)
        # The popup surface includes its large native shadow; the actual card
        # starts beyond the entire sidebar, including both paired controls.
        self.assertGreaterEqual(popup.get_surface().get_position_x()+card.get_x(),sidebar.get_x()+sidebar.get_width()+10)
        a.parameter_help.close()
        self.assertLessEqual(a.motion_speed.get_height(),32)

    def test_sidebar_captions_align_at_all_text_sizes_and_history_icons_are_local(self):
        from gi.repository import Gtk, Pango
        a=self.app
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='parallel',parameters=generate('parallel').values))
        a.workspace_paned.set_position(230)
        # Expanded settings must retain the same usable sidebar minimum too.
        a.advanced_expander.set_expanded(True)
        a.extra_geometry_expander.set_expanded(True)
        a.geometry_group_boxes['shafts']._section.set_expanded(True)
        a.inputs['pinion'].grab_focus()
        restore=a.advanced_fields.get_last_child()
        self.assertEqual(restore.get_label(),'Restore model defaults')
        self.assertTrue(restore.get_child().get_wrap())
        try:
            for scale in (0,1,2):
                with self.subTest(scale=scale):
                    a.text_size.set_selected(scale)
                    from ratiolab_checks import _wait_for_frame
                    _wait_for_frame(a.canvas,GLib.MainContext.default())
                    self.assertEqual(a.parameter_panel.get_width(),230)
                    self.assertTrue(a.advanced_expander.get_expanded())
                    self.assertTrue(a.extra_geometry_expander.get_expanded())
                    self.assertTrue(a.geometry_group_boxes['shafts']._section.get_expanded())
                    focused=a.inputs['pinion'];binding=a.parameter_help.bindings['pinion']
                    ok,help_bounds=binding.button.compute_bounds(focused);self.assertTrue(ok)
                    child=focused.get_first_child()
                    while child:
                        if isinstance(child,Gtk.Button):
                            self.assertTrue(child.get_visible())
                            ok,step_bounds=child.compute_bounds(focused);self.assertTrue(ok)
                            self.assertLessEqual(help_bounds.get_x()+help_bounds.get_width(),step_bounds.get_x())
                        child=child.get_next_sibling()
                    for first,second in (('pinion','wheel'),('module','width')):
                        one,two=a.inputs[first],a.inputs[second]
                        ok,before=one.compute_bounds(a.parameter_panel);self.assertTrue(ok)
                        ok,after=two.compute_bounds(a.parameter_panel);self.assertTrue(ok)
                        self.assertEqual(round(before.get_y()),round(after.get_y()))
                        self.assertAlmostEqual(one.get_pango_context().get_font_description().get_size()/Pango.SCALE,
                                               12*(1,1.25,1.5)[scale],delta=.01)
                        if scale==0:
                            self.assertEqual(round(before.get_height()),34)
                            for key in (first,second):
                                label=a.parameter_help.bindings[key].label
                                self.assertEqual(label.get_layout().get_line_count(),1)
                                self.assertEqual(label.get_ellipsize(),0)
            for button,name in ((a.undo_button,'undo'),(a.redo_button,'redo'),
                                (a.cad_action,'cad-link'),(a.export_menu,'download')):
                self.assertIsInstance(button.workspace_icon,Gtk.DrawingArea)
                self.assertEqual(button.workspace_icon.glyph_name,name)
                self.assertEqual(button.workspace_icon.get_sensitive(),button.get_sensitive())
            a.text_size.set_selected(0)
            _wait_for_frame(a.canvas,GLib.MainContext.default())
            ok,chip=a.family_chip.compute_bounds(a.secondary_toolbar);self.assertTrue(ok)
            self.assertEqual(round(chip.get_height()),24)
            self.assertFalse(a.selector.get_mapped())
            self.assertTrue(a.catalog_button.get_mapped())
            self.assertIsNotNone(a.catalog_picture.get_paintable())
            ok,choice=a.catalog_button.compute_bounds(a.parameter_panel);self.assertTrue(ok)
            self.assertEqual(round(choice.get_height()),a.catalog_button.get_child().get_height()+12)
            thumbnail=a.catalog_picture.get_parent()
            self.assertEqual((thumbnail.get_width(),thumbnail.get_height()),(50,44))
            self.assertGreaterEqual(choice.get_x(),0)
            self.assertLessEqual(choice.get_x()+choice.get_width(),a.parameter_panel.get_width())
            self.assertEqual(a.catalog_caption.get_text(),'Parallel shaft reducer')
            self.assertEqual(a.catalog_summary.get_text(),'1 stage · Spur')
            self.assertTrue(a.advanced_expander.has_css_class('geometry-disclosure'))
            self.assertTrue(a.extra_geometry_expander.has_css_class('geometry-disclosure'))
        finally:
            a.text_size.set_selected(0)
            from ratiolab_checks import _wait_for_frame
            _wait_for_frame(a.canvas,GLib.MainContext.default())

    def test_reference_phase_counter_tracks_actual_motion_without_document_edits(self):
        from math import degrees
        a=self.app;token=a.document.token;configuration=a.config()
        a.canvas.set_motion_playing(True);pump(.08)
        a.canvas.set_motion_playing(False);pump(.02)
        self.assertEqual(a.motion_phase_label.get_text(),f'Reference phase · {degrees(a.canvas.motion_phase)%360:.1f}°')
        self.assertEqual(a.document.token,token)
        self.assertEqual(a.config(),configuration)

    def test_results_precede_motion_and_section_heading_exists(self):
        a=self.app
        self.assertIs(a.metric_cards.get_next_sibling(),a.motion_bar)
        self.assertIs(a.model_dimensions_heading,a.catalog_caption)
        self.assertTrue(a.catalog_caption.get_mapped())
        self.assertEqual(a.catalog_caption.get_text(),gui_workflow.CATALOG[a.family][0])
        self.assertFalse(a.selector.get_mapped())
        self.assertTrue(a.catalog_button.get_mapped())
        self.assertEqual([a.page_buttons[k].get_label() for k in ('geometry','motion','assembly')],['Dimensions','Motion','Assembly'])
        self.assertIs(a.model_picker.get_next_sibling(),a.section_nav)

    def test_reference_details_header_metrics_and_transport_layout(self):
        from ratiolab_checks import _wait_for_frame
        from gi.repository import Pango
        a=self.app
        a.text_size.set_selected(0)
        _wait_for_frame(a.canvas,GLib.MainContext.default())
        self.assertEqual(a.metric_cards.get_column_spacing(),0)
        ok,metrics=a.metric_cards.compute_bounds(a.win);self.assertTrue(ok)
        ok,transport=a.motion_bar.compute_bounds(a.win);self.assertTrue(ok)
        self.assertGreaterEqual(metrics.get_height()+transport.get_height(),175)
        self.assertLessEqual(metrics.get_height()+transport.get_height(),190)
        number=a.metric_cards.get_child_at_index(0).get_child().get_first_child().get_next_sibling().get_first_child()
        self.assertEqual(number.get_pango_context().get_font_description().get_size()/Pango.SCALE,28)
        self.assertEqual(a.export_menu.get_label(),'Export')
        for action in (a.project_menu,a.cad_split,a.export_menu):
            ok,rect=action.compute_bounds(a.win);self.assertTrue(ok)
            self.assertLessEqual(rect.get_height(),36)
        ok,main=a.cad_action.compute_bounds(a.cad_split);self.assertTrue(ok)
        ok,arrow=a.cad_menu.compute_bounds(a.cad_split);self.assertTrue(ok)
        self.assertEqual(round(main.get_height()),round(arrow.get_height()))
        self.assertFalse(a.workspace_paned.get_wide_handle())
        self.assertEqual(a.motion_speed_text.get_width_chars(),7)
        self.assertEqual(a.motion_speed_text.get_max_width_chars(),7)
        self.assertEqual(a.motion_speed_text.get_max_length(),0)
        row=a.motion_bar.get_first_child();rate=row.get_next_sibling()
        self.assertTrue(a.motion_play.is_ancestor(row))
        display=a.motion_rate_display
        self.assertIs(a.motion_speed_text.get_parent(),display)
        self.assertIs(display.get_parent(),rate)
        self.assertIs(display.get_child_by_name('value'),a.motion_speed_text)
        self.assertIs(display.get_child_by_name('preview'),a.motion_rate_preview)
        self.assertEqual(display.get_visible_child_name(),'value')
        self.assertTrue(display.get_hhomogeneous());self.assertTrue(display.get_vhomogeneous())
        self.assertEqual(a.motion_speed_text.get_accessible_role(),Gtk.AccessibleRole.TEXT_BOX)
        self.assertEqual(a.motion_speed.get_accessible_role(),Gtk.AccessibleRole.SLIDER)
        self.assertIs(a.motion_phase_label.get_parent(),row)
        self.assertTrue(a.motion_connections.is_ancestor(row))
        self.assertTrue(a.motion_reset.has_css_class('flat'))
        self.assertFalse(a.motion_play.has_css_class('flat'))
        self.assertEqual(a.motion_play.get_pango_context().get_font_description().get_size()/Pango.SCALE,14)
        a.canvas.set_motion_playing(False)
        self.assertEqual(a.motion_play.workspace_icon.glyph_name,'play')
        a.motion_play.emit('clicked')
        self.assertEqual(a.motion_play.workspace_icon.glyph_name,'pause')
        a.motion_play.emit('clicked')
        self.assertEqual(a.motion_play.workspace_icon.glyph_name,'play')
        a.motion_reset.emit('clicked')
        children=[];child=rate.get_first_child()
        while child:
            if child is display or isinstance(child,Gtk.Button) and child.get_label() in ('−1','+1'):
                children.append(child)
            child=child.get_next_sibling()
        self.assertEqual([w.get_label() if isinstance(w,Gtk.Button) else 'entry' for w in children],['−1','entry','+1'])
        self.assertTrue(children[0].has_css_class('flat'));self.assertTrue(children[2].has_css_class('flat'))
        original=a.motion_speed_text.get_text();raw='12.3456789012345'
        try:
            from motion_controls import scale_rpm
            token=a.document.token;rpm=a.motion_rpm
            ok,normal=display.compute_bounds(a.win);self.assertTrue(ok)
            a.begin_motion_rate_drag();a.motion_speed.set_value(scale_rpm(137))
            _wait_for_frame(a.canvas,GLib.MainContext.default())
            self.assertEqual(display.get_visible_child_name(),'preview')
            self.assertEqual(a.motion_rate_preview.get_text(),'137')
            self.assertEqual(a.motion_speed_text.get_text(),original)
            self.assertEqual(a.motion_rpm,rpm);self.assertEqual(a.document.token,token)
            ok,preview=display.compute_bounds(a.win);self.assertTrue(ok)
            self.assertEqual((preview.get_width(),preview.get_height()),(normal.get_width(),normal.get_height()))
            a.cancel_motion_rate_drag()
            self.assertEqual(display.get_visible_child_name(),'value')
            self.assertTrue(a.motion_speed_text.grab_focus())
            focus=a.win.get_focus()
            self.assertTrue(focus is a.motion_speed_text or focus.is_ancestor(a.motion_speed_text))
            a.motion_speed_text.set_text(raw);a.motion_speed_text.emit('activate')
            self.assertEqual(a.motion_speed_text.get_text(),raw)
            self.assertEqual(a.motion_rpm,float(raw))
        finally:
            a.cancel_motion_rate_drag()
            a.motion_speed_text.set_text(original);a.motion_speed_text.emit('activate')

    def test_status_tooltip_only_repeats_ellipsized_text(self):
        from unittest.mock import Mock
        from test_interference_gui import wait_until
        from workspace_ui import StatusLabel
        a=self.app;label=a.status;original=label.get_text()
        self.assertIsInstance(label,StatusLabel)
        tooltip=Mock()
        try:
            a.status_text('Ready');pump(.05)
            self.assertFalse(label.get_layout().is_ellipsized())
            self.assertFalse(label.do_query_tooltip(0,0,False,tooltip))
            tooltip.set_text.assert_not_called()
            full='Detailed status retained for accessibility and export diagnostics. '*40
            a.status_text(full)
            self.assertTrue(wait_until(lambda:label.get_layout().is_ellipsized(),3))
            self.assertTrue(label.do_query_tooltip(0,0,False,tooltip))
            tooltip.set_text.assert_called_once_with(full)
            self.assertEqual(label.get_text(),full)
            self.assertEqual(label.get_tooltip_text(),full)
        finally:a.status_text(original)

    def test_single_motion_bar_and_separate_cad_menu(self):
        a = self.app
        self.assertIs(a.quick_play, a.motion_play)
        self.assertTrue(a.motion_play.is_ancestor(a.motion_bar))
        self.assertTrue(a.motion_speed_text.is_ancestor(a.motion_bar))
        self.assertTrue(a.send_btn.is_ancestor(a.cad_menu.get_popover()))
        self.assertTrue(a.export_menu.is_ancestor(a.cad_split.get_parent()))
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
        with patch('preview3d.GLib.get_monotonic_time',return_value=10000000):
            a.canvas.set_motion_playing(True)
            a.canvas.on_motion_tick(a.canvas,Clock(10000000))
            a.canvas.on_motion_tick(a.canvas,Clock(11000000))
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
        from copy import deepcopy
        from test_interference_gui import wait_until
        a=self.app
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='differential',
                               parameters=generate('differential',dict(variant='spiral',spiral_angle=27.5,spiral_hand=-1)).values))
        self.assertIsNotNone(a.design,a.status.get_text())
        self.assertFalse(a.variant_box.get_mapped())
        self.assertTrue(a.catalog_button.get_mapped())
        self.assertIn('Spiral',a.catalog_summary.get_text())
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
        def choose_variant(index):
            before=deepcopy(a.project_snapshot());token=a.document.token
            a.catalog_button.emit('clicked');pump()
            picker=a.model_catalog
            self.assertTrue(picker.window.get_mapped())
            self.assertTrue(picker.selectors[0].get_mapped())
            picker.selectors[0].set_selected(index);pump()
            self.assertEqual(a.project_snapshot(),before)
            self.assertEqual(a.document.token,token)
            picker.commit()
            self.assertTrue(wait_until(lambda:not a.pending and not a._geometry_waiting))
        choose_variant(0)
        self.assertIsNotNone(a.design,a.status.get_text())
        self.assertIn('Straight',a.catalog_summary.get_text())
        self.assertNotIn('spiral_angle',a.inputs)
        self.assertNotIn('spiral_hand',a.differential_selectors)
        self.assertEqual(len(a.design.parts[0].stations),2)
        choose_variant(1)
        self.assertIn('Spiral',a.catalog_summary.get_text())
        self.assertEqual(a.design.values['spiral_angle'],12.75)
        self.assertEqual(a.design.values['spiral_hand'],1)
        spiral=deepcopy(a.project_snapshot())
        a.undo_project()
        self.assertTrue(wait_until(lambda:not a.pending and not a._geometry_waiting))
        self.assertNotIn('spiral_angle',a.inputs)
        a.redo_project()
        self.assertTrue(wait_until(lambda:not a.pending and not a._geometry_waiting))
        self.assertEqual(a.project_snapshot(),spiral)

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
        a.canvas.reset_motion()
        with patch('preview3d.GLib.get_monotonic_time',return_value=10000000):
            a.canvas.set_motion_playing(True)
            a.canvas.on_motion_tick(a.canvas,Clock(10000000));a.canvas.on_motion_tick(a.canvas,Clock(11000000))
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
        a.canvas.reset_motion()
        with patch('preview3d.GLib.get_monotonic_time',return_value=20000000):
            a.canvas.set_motion_playing(True)
            a.canvas.on_motion_tick(a.canvas,Clock(20000000));a.canvas.on_motion_tick(a.canvas,Clock(21000000))
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
        from math import pi
        a = self.app
        a.motion_speed_text.set_text('125,375')
        a.motion_speed_text.emit('activate')
        self.assertEqual(a.config()['parameters']['input_rpm'],125.375)
        with patch('preview3d.GLib.get_monotonic_time',return_value=10000000) as clock:
            a.canvas.set_motion_playing(True)
            a.canvas.motion_phase=1.4
            previous=a.canvas.motion_plan
            clock.return_value=10250000
            a.motion_speed_text.set_text('72.125')
            a.motion_speed_text.emit('activate')
            self.assertTrue(a.canvas.motion_playing)
            phase=1.4+.25*125.375*2*pi/60
            self.assertAlmostEqual(a.canvas.motion_phase,phase)
            for i in range(len(a.design.parts)):
                for x,y in zip(previous.matrix(i,phase),a.canvas.motion_plan.matrix(i,phase)):
                    self.assertAlmostEqual(x,y,places=10)
            a.motion_speed_text.set_text('nan')
            a.motion_speed_text.emit('activate')
            self.assertTrue(a.motion_rate_error.get_visible())
            self.assertFalse(a.export_menu.get_sensitive())
            self.assertFalse(a.send_btn.get_sensitive())
            self.assertFalse(a.fusion_send_btn.get_sensitive())
            self.assertTrue(a.canvas.motion_playing)
            self.assertEqual(a.motion_rpm,72.125)
            self.assertEqual(a.design.values['input_rpm'],72.125)
            self.assertEqual(a.error_field,'input_rpm')
            self.assertFalse(a.refresh())
            self.assertTrue(a.canvas.motion_playing)
            with self.assertRaises(ValueError):a.config()
            invalid_path=Path(self.folder.name)/'invalid-rpm.json'
            a.save_project(path=invalid_path)
            self.assertFalse(invalid_path.exists())
            with patch.object(a,'background') as worker:
                a.export_step();a.send();a.send_fusion()
            self.assertFalse(worker.called)
            self.assertTrue(a.canvas.motion_playing)
            self.assertEqual(a.error_field,'input_rpm')
            a.motion_speed_text.set_text('1500')
            a.motion_speed_text.emit('activate')
            self.assertTrue(a.export_menu.get_sensitive())
            self.assertTrue(a.send_btn.get_sensitive())
            self.assertTrue(a.fusion_send_btn.get_sensitive())
            self.assertTrue(a.canvas.motion_playing)

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
