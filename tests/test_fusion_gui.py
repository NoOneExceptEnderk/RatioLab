# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""GTK integration preserves SolidCraft and blocks concurrent/stale transfers."""
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk, Gdk, Gio, GLib
import app as module
from geometry import generate


def pump(duration=.05):
    until=time.monotonic()+duration
    context=GLib.MainContext.default()
    while time.monotonic()<until:
        # Dispatch one event per turn so the budget and other threads stay live.
        context.iteration(False)
        time.sleep(.002)


class FusionGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            raise unittest.SkipTest('GTK display required')
        cls.folder=tempfile.TemporaryDirectory(prefix='ratiolab-fusion-gui-')
        cls.root=Path(cls.folder.name)
        cls.environment=patch.dict(os.environ,dict(XDG_CONFIG_HOME=str(cls.root/'config'),XDG_DATA_HOME=str(cls.root/'data'),APPDATA=str(cls.root/'roaming'),LOCALAPPDATA=str(cls.root/'local')))
        cls.environment.start()
        cls.app=module.ReducerApp()
        cls.app.set_application_id(f'local.solidcraft.reducers.fusiontests.p{os.getpid()}')
        cls.app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        cls.app.register(None);cls.app.activate();pump(.15)

    @classmethod
    def tearDownClass(cls):
        for window in cls.app.get_windows():window.destroy()
        cls.environment.stop();cls.folder.cleanup()

    def setUp(self):
        self.app.busy=False
        self.app.load_config_data(dict(format='solidcraft-riduttori/1',family='spur',parameters=generate('spur').values))
        self.app.output_dir=self.root
        self.app.set_fusion_connection(None)
        pump(.02)

    def status(self):
        return dict(application='Fusion',version='2600',document={'id':'doc1','name':'Test Design'},bridge_session='session')

    def test_compact_menu_geometry_setup_back_and_reopen_at_all_text_sizes(self):
        from test_interference_gui import wait_until
        from ratiolab_checks import _wait_for_frame
        a=self.app;a.set_connection(False);a.set_fusion_connection(None)
        popup=a.cad_menu.get_popover()
        def card():
            ok,rect=popup.get_child().get_parent().compute_bounds(popup)
            self.assertTrue(ok)
            return rect
        try:
            self.assertEqual(list(a.cad_compact_buttons),['fusion','solidcraft'])
            self.assertFalse(popup.get_has_arrow())
            for scale in (0,1,2):
                with self.subTest(scale=scale):
                    a.text_size.set_selected(scale)
                    _wait_for_frame(a.canvas,GLib.MainContext.default())
                    size=(a.canvas.get_width(),a.canvas.get_height());scene=a.canvas.scene
                    a.cad_menu.popup()
                    def footer_inside():
                        if not popup.get_mapped():return False
                        # A reopened surface can still expose its allocation
                        # from the previous text scale. Compare heights only
                        # after fit_card's current request has been allocated.
                        if a.cad_card_view.get_height()!=a.cad_card_view.get_size_request().height:return False
                        ok,bounds=a.cad_setup_caption.compute_bounds(popup)
                        return ok and bounds.get_height()>0 and bounds.get_y()+bounds.get_height()<=card().get_y()+card().get_height()-12
                    self.assertTrue(wait_until(footer_inside,3))
                    self.assertEqual(a.cad_stack.get_visible_child_name(),'compact')
                    from gi.repository import Pango
                    factor=(1,1.25,1.5)[scale]
                    self.assertEqual(a.cad_setup_button.get_pango_context().get_font_description().get_size()/Pango.SCALE,12*factor)
                    self.assertEqual(a.cad_compact_buttons['fusion'].get_pango_context().get_font_description().get_size()/Pango.SCALE,14*factor)
                    self.assertEqual(round(card().get_width()),292)
                    self.assertGreater(a.cad_setup_caption.get_height(),0)
                    self.assertGreaterEqual(a.cad_setup_caption.get_height(),a.cad_setup_caption.get_layout().get_pixel_size().height)
                    ok,caption=a.cad_setup_caption.compute_bounds(popup);self.assertTrue(ok)
                    self.assertLessEqual(caption.get_y()+caption.get_height(),card().get_y()+card().get_height()-12)
                    ok,anchor=a.cad_split.compute_bounds(a.win);self.assertTrue(ok)
                    surface=popup.get_surface();rect=card()
                    # GTK 4.14/X11 places the native popup content four pixels
                    # beyond this CSS border; newer GTK/Wayland differs by one.
                    # Check close anchoring without assuming identical native
                    # surface rounding. Width/footer/scroll checks stay exact.
                    self.assertAlmostEqual(surface.get_position_x()+rect.get_x()+rect.get_width(),anchor.get_x()+anchor.get_width(),delta=6)
                    self.assertGreaterEqual(surface.get_position_y()+rect.get_y(),anchor.get_y()+anchor.get_height()+7)
                    adjustment=a.cad_card_view.get_hadjustment()
                    self.assertLessEqual(adjustment.get_upper(),adjustment.get_page_size()+.5)
                    compact_height=round(card().get_height())
                    a.set_fusion_connection(self.status());pump(.03)
                    self.assertEqual(round(card().get_width()),292)
                    a.set_fusion_connection(dict(document=None));pump(.03)
                    self.assertEqual(round(card().get_width()),292)
                    a.set_fusion_connection(None);pump(.03)
                    a.cad_setup_button.emit('clicked')
                    self.assertTrue(wait_until(lambda:a.cad_stack.get_visible_child_name()=='setup',3))
                    self.assertTrue(a.fusion_install_btn.get_mapped())
                    self.assertEqual(round(card().get_width()),292)
                    a.cad_back_button.emit('clicked')
                    self.assertTrue(wait_until(lambda:a.cad_stack.get_visible_child_name()=='compact' and round(card().get_height())==compact_height,3))
                    self.assertEqual(round(card().get_width()),292)
                    self.assertEqual((a.canvas.get_width(),a.canvas.get_height()),size)
                    self.assertIs(a.canvas.scene,scene)
                    popup.popdown();pump(.04);a.cad_menu.popup()
                    self.assertTrue(wait_until(lambda:footer_inside() and a.cad_stack.get_visible_child_name()=='compact' and round(card().get_height())==compact_height,3))
                    self.assertEqual(round(card().get_width()),292)
                    a.cad_setup_button.emit('clicked');pump(.03)
                    popup.popdown()
                    self.assertTrue(wait_until(lambda:not popup.get_mapped(),3))
                    a.cad_menu.popup()
                    self.assertTrue(wait_until(lambda:footer_inside() and a.cad_stack.get_visible_child_name()=='compact' and round(card().get_height())==compact_height,3))
                    self.assertEqual(round(card().get_height()),compact_height)
                    popup.popdown();pump(.04)
        finally:
            popup.popdown();a.text_size.set_selected(0)
            _wait_for_frame(a.canvas,GLib.MainContext.default())

    def test_compact_connect_delegates_without_import_and_selects_only_real_known_connections(self):
        a=self.app;a.set_connection(False);a.set_fusion_connection(None)
        with patch.object(a,'background') as background,patch.object(a,'send_fusion') as send:
            a.cad_compact_buttons['fusion'].emit('clicked')
            background.assert_called_once_with(a.connect_fusion)
            send.assert_not_called()
            self.assertFalse(a.fusion_connected)
            self.assertEqual(a.cad_action.get_label(),'CAD Connections')
        a.set_fusion_connection(self.status())
        self.assertEqual(a.cad_compact_status['fusion'].get_text(),'Connected · selected')
        self.assertFalse(a.cad_compact_buttons['fusion'].get_sensitive())
        a.set_connection(True)
        self.assertEqual(a.cad_compact_buttons['fusion'].get_label(),'Select')
        with patch.object(a,'background') as background,patch.object(a,'send_fusion') as send:
            a.cad_compact_buttons['fusion'].emit('clicked')
            background.assert_not_called();send.assert_not_called()
        self.assertEqual(a.cad_action.get_label(),'Import in Fusion')
        a.set_fusion_connection(dict(document=None))
        self.assertIn('no active document',a.cad_compact_status['fusion'].get_text())
        self.assertEqual(a.cad_compact_buttons['fusion'].get_label(),'Check')
        self.assertFalse(a.cad_action.get_sensitive())
        a.set_connection(True)
        with patch.object(a,'background') as background:
            a.cad_compact_buttons['fusion'].emit('clicked')
            background.assert_called_once_with(a.connect_fusion)
            self.assertEqual(a.active_cad,'solidcraft')
        a.set_fusion_connection(None)
        self.assertEqual(a.cad_compact_status['fusion'].get_text(),'Not connected')
        self.assertEqual(a.cad_compact_buttons['fusion'].get_label(),'Connect')
        a.set_connection(False)

    def test_compact_connect_busy_success_and_error_preserve_actual_readiness(self):
        from test_interference_gui import wait_until
        a=self.app;a.set_connection(False);a.set_fusion_connection(None)
        release=threading.Event()
        def connect():
            release.wait(3)
            GLib.idle_add(a.set_fusion_connection,self.status())
            return 'Connected to test CAD'
        with patch.object(a,'connect_fusion',side_effect=connect),patch.object(a,'send_fusion') as send:
            a.cad_compact_buttons['fusion'].emit('clicked')
            try:
                self.assertTrue(a.busy)
                self.assertEqual(a.cad_compact_status['fusion'].get_text(),'Connecting…')
                self.assertFalse(a.fusion_connected)
                self.assertTrue(all(not b.get_sensitive() for b in a.cad_compact_buttons.values()))
            finally:release.set()
            self.assertTrue(wait_until(lambda:not a.busy and a.fusion_connected,3))
            self.assertEqual(a.cad_compact_status['fusion'].get_text(),'Connected · selected')
            self.assertEqual(a.cad_action.get_label(),'Import in Fusion')
            send.assert_not_called()
        a.set_fusion_connection(None)
        with patch.object(module.fusion_connection,'Client') as client:
            client.return_value.__enter__.side_effect=module.fusion_connection.FusionError('test offline')
            a.cad_compact_buttons['fusion'].emit('clicked')
            self.assertTrue(wait_until(lambda:not a.busy,3))
            self.assertFalse(a.fusion_connected)
            self.assertEqual(a.cad_compact_status['fusion'].get_text(),'Not connected')
            self.assertEqual(a.cad_action.get_label(),'CAD Connections')
            self.assertTrue(a.cad_compact_buttons['fusion'].get_sensitive())
            self.assertIn('test offline',a.status.get_text())

    def test_primary_action_tracks_only_successful_connection_and_readiness(self):
        a=self.app;a.set_connection(False)
        self.assertEqual(a.cad_action.get_label(),'CAD Connections')
        with patch.object(a,'send_fusion') as send:
            a.set_fusion_connection(self.status())
            send.assert_not_called()
            self.assertEqual(a.cad_action.get_label(),'Import in Fusion')
            self.assertTrue(a.cad_action.get_sensitive())
            a.cad_action.emit('clicked');send.assert_called_once()
        a.set_fusion_connection(dict(document=None))
        self.assertFalse(a.cad_action.get_sensitive())
        a.set_connection(True)
        self.assertEqual(a.cad_action.get_label(),'Import in SolidCraft')
        a.set_connection(False)
        self.assertEqual(a.cad_action.get_label(),'CAD Connections')
        self.assertTrue(a.cad_menu.get_sensitive())

    def test_new_section_preserves_original_solidcraft_controls(self):
        a=self.app
        self.assertEqual(a.connect_btn.get_label(),'Connect SolidCraft')
        self.assertEqual(a.send_btn.get_label(),'Create in SolidCraft')
        self.assertEqual(a.fusion_send_btn.get_label(),'Create in Fusion')
        for widget in (a.connect_btn,a.send_btn,a.fusion_install_btn,a.fusion_connect_btn,a.fusion_send_btn):
            self.assertTrue(widget.is_ancestor(a.cad_menu.get_popover()))
        self.assertIn('RatioLabBridge',a.fusion_hint.get_text())
        self.assertIn('STEP solids',a.fusion_hint.get_text())

    def test_parameter_edits_immediately_block_send_and_invalid_geometry_never_calls_client(self):
        a=self.app
        self.assertTrue(a.fusion_send_btn.get_sensitive())
        a.inputs['module'].set_text('unfinished')
        self.assertFalse(a.fusion_send_btn.get_sensitive())
        self.assertFalse(a.refresh())
        with patch.object(module.fusion_connection,'Client') as client:
            a.send_fusion()
        client.assert_not_called()
        a.inputs['module'].set_text('2.5');a.refresh()
        self.assertTrue(a.fusion_send_btn.get_sensitive())

    def test_background_blocks_all_cad_mutations_and_restores_after_completion(self):
        a=self.app
        release=threading.Event()
        def work():
            release.wait(5)
            return 'test complete'
        a.background(work)
        try:
            self.assertTrue(a.busy)
            for widget in (a.send_btn,a.connect_btn,a.fusion_send_btn,a.fusion_connect_btn,a.fusion_install_btn,a.export_menu,a.selector,a.fields):
                self.assertFalse(widget.get_sensitive())
            with patch.object(module.fusion_connection,'Client') as client:
                a.send_fusion()
            client.assert_not_called()
        finally:
            release.set()
        deadline=time.monotonic()+3
        while a.busy and time.monotonic()<deadline:pump(.02)
        self.assertFalse(a.busy)
        self.assertTrue(a.fusion_send_btn.get_sensitive())
        self.assertTrue(a.fusion_install_btn.get_sensitive())
        self.assertTrue(a.export_menu.get_sensitive())

    def test_connect_failure_clears_previous_connected_label(self):
        a=self.app;a.set_fusion_connection(self.status())
        self.assertTrue(a.fusion_connected)
        with patch.object(module.fusion_connection,'Client') as client:
            client.return_value.__enter__.side_effect=module.fusion_connection.FusionError('offline')
            with self.assertRaises(module.fusion_connection.FusionError):a.connect_fusion()
        pump(.02)
        self.assertFalse(a.fusion_connected)
        self.assertIn('Disconnected',a.fusion_connection_label.get_text())

    def test_send_snapshots_validated_design_output_and_visibility(self):
        a=self.app
        a.canvas.show_support=True;a.canvas.show_housing=False
        with patch.object(a,'background') as background:
            a.send_fusion()
        worker=background.call_args.args[0]
        design=a.design
        with patch.object(module.fusion_connection,'Client') as client:
            active=client.return_value.__enter__.return_value
            active.insert.return_value={'package_path':str(self.root/'package')}
            active.status.return_value=self.status()
            message=worker()
            active.insert.assert_called_once_with(design,self.root,{'gear','support'})
        pump(.02)
        self.assertIn('STEP solids',message)
        self.assertIn('Test Design',a.fusion_connection_label.get_text())
        self.assertTrue(a.fusion_connected)

    def test_failed_import_clears_status_and_never_repeats(self):
        a=self.app;a.set_fusion_connection(self.status())
        with patch.object(a,'background') as background:a.send_fusion()
        worker=background.call_args.args[0]
        with patch.object(module.fusion_connection,'Client') as client:
            active=client.return_value.__enter__.return_value
            active.insert.side_effect=module.fusion_connection.FusionError('may still be running; do not resend')
            with self.assertRaises(module.fusion_connection.FusionError):worker()
            active.insert.assert_called_once()
        pump(.02)
        self.assertFalse(a.fusion_connected)


if __name__=='__main__':unittest.main()
