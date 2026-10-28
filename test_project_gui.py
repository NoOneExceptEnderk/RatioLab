"""Real GTK project transitions with temporary user data and no CAD connection."""
import json
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
from geometry import generate,VARIANTS
from project_document import Store,Document,atomic_json


def pump(duration=.06):
    until=time.monotonic()+duration
    context=GLib.MainContext.default()
    while time.monotonic()<until:
        while context.pending():context.iteration(False)
        time.sleep(.003)


class ProjectGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            raise unittest.SkipTest('GTK display required')
        cls.temporary=TemporaryDirectory(prefix='ratiolab-project-tests-')
        cls.root=Path(cls.temporary.name)
        cls.environment=patch.dict(os.environ, dict(XDG_CONFIG_HOME=str(cls.root/'config'),XDG_DATA_HOME=str(cls.root/'data'),APPDATA=str(cls.root/'roaming'),LOCALAPPDATA=str(cls.root/'local')))
        cls.environment.start()
        cls.app=module.ReducerApp()
        cls.app.set_application_id(f'local.solidcraft.reducers.projecttests.p{os.getpid()}')
        cls.app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        cls.app.register(None);cls.app.activate();pump(.15)

    @classmethod
    def tearDownClass(cls):
        for win in cls.app.get_windows():win.destroy()
        cls.environment.stop();cls.temporary.cleanup()

    def setUp(self):
        a=self.app
        if a.project_dialog:
            a.project_dialog.emit('response',Gtk.ResponseType.CANCEL)
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='helical',parameters=generate('helical').values))
        a.output_dir=self.root
        self.path=self.root/(self._testMethodName+' è con spazi.json')
        a.document.path=self.path
        a.update_document()
        pump(.02)

    def answer(self, code):
        dialog=self.app.project_dialog
        self.assertIsInstance(dialog,Gtk.MessageDialog)
        dialog.response(code)
        pump(.02)

    def test_every_family_variant_opens_exactly_without_spontaneous_dirty_history(self):
        a=self.app
        for family in a.families:
            for variant in (list(VARIANTS.get(family,{})) or [None]):
                with self.subTest(family=family,variant=variant):
                    values=generate(family,{'variant':variant} if variant else {}).values
                    obj=dict(format='solidcraft-riduttori/1',family=family,parameters=values)
                    a.load_config_data(obj)
                    self.assertEqual(a.design.values,values)
                    self.assertEqual(a.config()['parameters'],values)
                    a.refresh();a.make_fields();a.project_changed()
                    self.assertFalse(a.document.dirty)
                    self.assertEqual(len(a.document.states),1)
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='helical',parameters={'input_rpm':1234.123456789123}))
        self.assertEqual(a.design.values['input_rpm'],1234.123456789123)
        self.assertEqual(a.config()['parameters']['input_rpm'],1234.123456789123)
        self.assertFalse(a.document.dirty)

    def test_tiny_values_roundtrip_initial_programmatic_and_derived_refresh(self):
        a=self.app
        for mode in ('manual','shaft'):
            with self.subTest(mode=mode):
                values=generate('helical',dict(input_torque=1e-30,bearing_mode=mode,fit='custom',seat_allowance=-1e-30)).values
                a.load_config_data(dict(format='solidcraft-riduttori/1',family='helical',parameters=values),self.path)
                self.assertEqual(float(a.inputs['input_torque'].get_text()),1e-30)
                self.assertEqual(a.config()['parameters'],values)
                for _ in range(2):a.refresh();a.project_changed()
                self.assertEqual(float(a.inputs['input_torque'].get_text()),1e-30)
                self.assertEqual(a.config()['parameters'],values)
                self.assertFalse(a.document.dirty)
                a.save_project()
                self.assertEqual(json.loads(self.path.read_text())['parameters'],values)

    def test_open_current_file_save_reloads_the_saved_contents(self):
        a=self.app;a.save_project()
        a.inputs['module'].set_text('2.75')
        a.open_project_path(self.path);self.answer(Gtk.ResponseType.ACCEPT)
        self.assertEqual(a.config()['parameters']['module'],2.75)
        self.assertEqual(json.loads(self.path.read_text())['parameters']['module'],2.75)
        self.assertFalse(a.document.dirty)

    def test_open_target_changed_while_prompt_open_is_revalidated(self):
        a=self.app;a.inputs['module'].set_text('2.75')
        self.path.write_text(json.dumps(dict(format='solidcraft-riduttori/1',family='spur',parameters={})))
        identity=a.document.identity
        a.open_project_path(self.path)
        self.path.write_text('{corrupt')
        self.answer(Gtk.ResponseType.REJECT)
        self.assertEqual(a.document.identity,identity)
        self.assertEqual(a.config()['parameters']['module'],2.75)
        self.assertTrue(a.document.dirty)
        pump(.15)
        self.assertIn('could not be loaded',a.status.get_text())

    def test_pending_derived_refresh_does_not_dirty_saved_checkpoint_or_add_history(self):
        a=self.app
        values=generate('helical',dict(bearing_mode='shaft',fit='custom')).values
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='helical',parameters=values),self.path)
        a.inputs['shaft_allowance'].set_text('0.01')
        self.assertEqual(len(a.document.states),2)
        a.save_project()
        self.assertFalse(a.document.dirty)
        pump(.15);a.project_changed()
        self.assertFalse(a.document.dirty)
        self.assertEqual(len(a.document.states),2)
        self.assertEqual(float(a.inputs['bore'].get_text()),6.01)
        self.assertEqual(json.loads(self.path.read_text())['parameters']['bore'],6.01)
        a.undo_project()
        self.assertEqual(a.config()['parameters']['bore'],6)
        a.redo_project();self.assertFalse(a.document.dirty)
        self.assertEqual(a.config()['parameters']['bore'],6.01)

    def test_save_normalizes_valid_width_edit_without_extra_undo_step(self):
        a=self.app
        values=generate('helical',dict(bearing_mode='gear')).values
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='helical',parameters=values),self.path)
        self.assertEqual(a.config()['parameters']['width'],10)
        a.inputs['width'].set_text('2')
        self.assertTrue(a.save_project())
        self.assertEqual(a.config()['parameters']['width'],8)
        self.assertEqual(float(a.inputs['width'].get_text()),8)
        self.assertEqual(json.loads(self.path.read_text())['parameters']['width'],8)
        self.assertFalse(a.document.dirty)
        pump(.15);a.project_changed();self.assertFalse(a.document.dirty)
        self.assertEqual(len(a.document.states),2)
        a.undo_project();self.assertEqual(a.config()['parameters']['width'],10)
        a.redo_project();self.assertEqual(a.config()['parameters']['width'],8)
        self.assertFalse(a.document.dirty)

    def test_immediate_undo_redo_grouping_invalid_input_and_clean_checkpoint(self):
        a=self.app
        a.inputs['module'].set_text('2.25')
        a.inputs['module'].set_text('2.5')
        self.assertEqual(len(a.document.states),2)
        self.assertTrue(a.document.dirty)
        a.undo_project()
        self.assertFalse(a.document.dirty)
        self.assertEqual(a.config()['parameters']['module'],2)
        a.redo_project()
        self.assertEqual(a.inputs['module'].get_text(),'2.5')
        a.save_project()
        self.assertFalse(a.document.dirty)
        a.inputs['module'].set_text('bad-')
        self.assertTrue(a.document.dirty)
        recovery=json.loads(a.project_store.session.read_text())
        self.assertEqual(recovery['snapshot']['raw']['helical']['module'],'bad-')
        a.save_project()
        self.assertTrue(a.document.dirty)
        self.assertEqual(json.loads(self.path.read_text())['parameters']['module'],2.5)
        a.undo_project();self.assertFalse(a.document.dirty)
        a.redo_project();self.assertEqual(a.inputs['module'].get_text(),'bad-')
        a.undo_project();a.inputs['module'].set_text('2.75');a.redo_project()
        self.assertEqual(a.inputs['module'].get_text(),'2.75')

    def test_new_and_open_cancel_discard_save_paths(self):
        a=self.app
        a.inputs['module'].set_text('2.25')
        original=a.document.identity
        a.new_project();self.answer(Gtk.ResponseType.CANCEL)
        self.assertEqual(a.document.identity,original)
        self.assertEqual(a.inputs['module'].get_text(),'2.25')
        a.new_project();self.answer(Gtk.ResponseType.ACCEPT)
        self.assertEqual(json.loads(self.path.read_text())['parameters']['module'],2.25)
        self.assertEqual(a.family,'parallel');self.assertFalse(a.document.dirty)
        a.inputs['module'].set_text('3.0')
        a.open_project_path(self.path);self.answer(Gtk.ResponseType.REJECT)
        self.assertEqual(a.family,'helical');self.assertFalse(a.document.dirty)
        self.assertEqual(a.document.path,self.path)
        self.assertIn(str(self.path),a.document_label.get_text())

    def test_failed_save_during_replacement_keeps_document_and_old_file(self):
        a=self.app;a.save_project();before=self.path.read_bytes()
        a.inputs['module'].set_text('2.25');identity=a.document.identity
        a.new_project()
        with patch('project_document.os.replace',side_effect=OSError('Injected disk failure')):
            self.answer(Gtk.ResponseType.ACCEPT)
        self.assertEqual(a.document.identity,identity)
        self.assertEqual(a.inputs['module'].get_text(),'2.25')
        self.assertTrue(a.document.dirty)
        self.assertEqual(self.path.read_bytes(),before)
        self.assertIn('could not be saved',a.status.get_text())

    def test_load_errors_and_missing_recent_do_not_replace_dirty_document(self):
        a=self.app;a.inputs['module'].set_text('invalid')
        identity=a.document.identity
        for obj in ({'format':'unknown'}, {'format':'solidcraft-riduttori/1','family':'other','parameters':{}}, [], {'format':'solidcraft-riduttori/1','family':'helical','parameters':{'module':-1}}):
            self.path.write_text(json.dumps(obj))
            a.open_project_path(self.path)
            self.assertEqual(a.document.identity,identity)
            self.assertIsNone(a.project_dialog)
        a.project_store.remember(self.path)
        self.path.unlink();a.open_project_path(self.path)
        self.assertEqual(a.document.identity,identity)
        self.assertEqual(a.inputs['module'].get_text(),'invalid')
        self.assertTrue(a.document.dirty)

    def test_precision_legacy_keys_and_equivalent_numeric_formatting_stay_clean(self):
        a=self.app
        obj=dict(format='solidcraft-riduttori/1',family='helical',parameters=dict(module=1.23456789123,material='obsolete',production='old'))
        a.load_config_data(obj,self.path)
        self.assertEqual(a.design.values['module'],1.23456789123)
        self.assertEqual(a.config()['parameters']['module'],1.23456789123)
        a.inputs['teeth'].set_text(str(int(a.config()['parameters']['teeth']))+'.0')
        a.refresh();a.project_changed()
        self.assertFalse(a.document.dirty)
        a.save_project()
        saved=json.loads(self.path.read_text())
        self.assertEqual(saved['parameters']['module'],1.23456789123)
        self.assertNotIn('material',saved['parameters'])
        self.assertFalse(a.document.dirty)

    def test_full_precision_typed_values_survive_spin_update_and_speed_commit(self):
        a=self.app
        module=2.123456789123
        rpm=1234.123456789123
        a.inputs['module'].set_text(repr(module))
        before=len(a.document.states)
        a.inputs['module'].update()
        self.assertEqual(float(a.inputs['module'].get_text()),module)
        self.assertEqual(len(a.document.states),before)
        a.motion_speed_text.set_text(repr(rpm))
        a.motion_speed_text.emit('activate')
        self.assertEqual(float(a.motion_speed_text.get_text()),rpm)
        self.assertEqual(a.config()['parameters']['input_rpm'],rpm)
        a.save_project()
        obj=json.loads(self.path.read_text())
        self.assertEqual(obj['parameters']['module'],module)
        self.assertEqual(obj['parameters']['input_rpm'],rpm)
        a.load_config_data(obj,self.path)
        self.assertEqual(a.design.values['module'],module)
        self.assertEqual(a.config()['parameters']['input_rpm'],rpm)
        self.assertFalse(a.document.dirty)
        a.inputs['module'].spin(Gtk.SpinType.STEP_FORWARD,1)
        self.assertGreater(float(a.inputs['module'].get_text()),module)
        self.assertTrue(a.document.dirty)
        a.undo_project()
        self.assertEqual(a.config()['parameters']['module'],module)
        self.assertFalse(a.document.dirty)

    def test_fractional_integer_is_not_rounded_and_failed_rebuild_rolls_back(self):
        a=self.app
        a.inputs['teeth'].set_text('30.5');a.inputs['teeth'].update()
        self.assertEqual(a.inputs['teeth'].get_text(),'30.5')
        self.assertFalse(a.refresh())
        self.assertTrue(a.document.dirty)
        identity=a.document.identity
        snapshot=a.project_snapshot()
        self.path.write_text(json.dumps(dict(format='solidcraft-riduttori/1',family='spur',parameters=generate('spur').values)))
        original=a.make_fields
        first=True
        def fail_once():
            nonlocal first
            if first:
                first=False
                raise ValueError('Injected rebuild failure')
            return original()
        a.open_project_path(self.path)
        with patch.object(a,'make_fields',side_effect=fail_once):
            self.answer(Gtk.ResponseType.REJECT)
        self.assertEqual(a.document.identity,identity)
        self.assertEqual(a.project_snapshot(),snapshot)
        self.assertFalse(a.building)
        self.assertFalse(a.project_restoring)
        self.assertTrue(a.document.dirty)
        self.assertIn('Injected rebuild failure',a.status.get_text())

    def test_options_family_and_variant_preserve_invalid_text_and_history(self):
        a=self.app
        a.inputs['module'].set_text('unfinished')
        a.rebuild_options({'bearing_mode':'shaft'})
        self.assertEqual(a.inputs['module'].get_text(),'unfinished')
        a.undo_project()
        self.assertEqual(a.option_values['bearing_mode'],'manual')
        self.assertEqual(a.inputs['module'].get_text(),'unfinished')
        a.redo_project()
        self.assertEqual(a.option_values['bearing_mode'],'shaft')
        a.selector.set_selected(list(a.families).index('cycloidal'))
        self.assertEqual(a.family,'cycloidal')
        a.undo_project()
        self.assertEqual(a.family,'helical')
        self.assertEqual(a.inputs['module'].get_text(),'unfinished')
        a.redo_project()
        a.variant_selector.set_selected(list(VARIANTS['cycloidal']).index('dual'))
        self.assertEqual(a.config()['parameters']['variant'],'dual')
        a.undo_project()
        self.assertEqual(a.config()['parameters']['variant'],'single')

    def test_motion_edit_is_recoverable_before_activation_and_animation_does_not_add_history(self):
        a=self.app
        a.motion_speed_text.set_text('incomplete')
        self.assertTrue(a.document.dirty)
        self.assertEqual(json.loads(a.project_store.session.read_text())['snapshot']['raw']['helical']['input_rpm'],'incomplete')
        a.undo_project();self.assertFalse(a.document.dirty)
        count=len(a.document.states)
        a.canvas.set_motion_playing(True);pump(.12);a.canvas.set_motion_playing(False)
        self.assertEqual(len(a.document.states),count)
        self.assertFalse(a.document.dirty)

    def test_history_shortcut_action_from_focused_numeric_entry(self):
        a=self.app
        a.inputs['module'].grab_focus()
        self.assertFalse(a.inputs['module'].get_enable_undo())
        self.assertFalse(a.motion_speed_text.get_enable_undo())
        a.inputs['module'].set_text('2.25')
        self.assertTrue(a.document.dirty)
        action=a.history_shortcuts[0].get_action()
        self.assertTrue(action.activate(Gtk.ShortcutActionFlags.EXCLUSIVE,a.inputs['module'],None))
        self.assertFalse(a.document.dirty)
        action=a.history_shortcuts[1].get_action()
        self.assertTrue(action.activate(Gtk.ShortcutActionFlags.EXCLUSIVE,a.inputs['module'],None))
        self.assertTrue(a.document.dirty)
        self.assertEqual(a.inputs['module'].get_text(),'2.25')

    def test_stale_dialog_answers_and_no_local_paths_do_not_replace_or_save(self):
        a=self.app
        a.document.path=None
        a.inputs['module'].set_text('2.25')
        a.save_as_dialog();pump(.2);dialog=a.project_dialog
        a.inputs['module'].set_text('2.5')
        # A real native chooser can be cancelled without selecting a path.
        dialog.emit('response',Gtk.ResponseType.CANCEL)
        self.assertIsNone(a.document.path)
        self.assertTrue(a.document.dirty)
        a.load_dialog();pump(.2);dialog=a.project_dialog
        dialog.emit('response',Gtk.ResponseType.ACCEPT)
        self.assertEqual(a.inputs['module'].get_text(),'2.5')
        a.new_project();a.inputs['module'].set_text('2.75')
        self.answer(Gtk.ResponseType.REJECT)
        self.assertEqual(a.family,'helical')
        self.assertEqual(a.inputs['module'].get_text(),'2.75')

    def test_busy_close_and_shortcuts_keep_the_document(self):
        a=self.app;a.inputs['module'].set_text('2.25')
        a.busy=True
        self.assertTrue(a.close_project())
        a.activate_action('new',None);a.activate_action('close',None);a.activate_action('save',None)
        self.assertIsNone(a.project_dialog)
        self.assertTrue(a.win.get_visible())
        self.assertTrue(a.document.dirty)
        a.busy=False
        a.close_project();self.answer(Gtk.ResponseType.CANCEL)
        self.assertTrue(a.win.get_visible());self.assertTrue(a.document.dirty)

    def test_recovery_choice_restores_invalid_edits_and_retains_corrupt_records(self):
        a=self.app
        old=Store(self.root/'old-session')
        previous=Document(a.project_snapshot(),self.path)
        damaged=previous.current;damaged['raw']['helical']['module']='unfinished'
        previous.record(damaged);old.checkpoint(previous)
        destination=a.project_store.folder/'recovery'/'previous-session.json'
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_bytes(old.session.read_bytes())
        a.offer_recovery();self.answer(Gtk.ResponseType.CANCEL)
        self.assertTrue(destination.exists());self.assertFalse(a.document.dirty)
        a.offer_recovery();self.answer(Gtk.ResponseType.ACCEPT)
        self.assertFalse(destination.exists())
        self.assertEqual(a.inputs['module'].get_text(),'unfinished')
        self.assertTrue(a.document.dirty)
        self.assertTrue(a.project_store.session.exists())
        a.undo_project();self.assertFalse(a.document.dirty)
        a.redo_project();self.assertEqual(a.inputs['module'].get_text(),'unfinished')
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='helical',parameters=generate('helical').values))
        destination.write_text('{corrupt')
        a.offer_recovery();self.answer(Gtk.ResponseType.CANCEL)
        self.assertTrue(destination.exists())
        a.offer_recovery();self.answer(Gtk.ResponseType.REJECT)
        self.assertFalse(destination.exists())
        self.assertFalse(a.document.dirty)

    def test_save_as_stale_answer_and_missing_local_path_are_safe(self):
        a=self.app
        a.inputs['module'].set_text('2.25')
        a.save_as_dialog();pump(.15);dialog=a.project_dialog
        a.inputs['module'].set_text('2.5')
        with patch.object(dialog,'get_file',return_value=Gio.File.new_for_path(str(self.path))):
            dialog.emit('response',Gtk.ResponseType.ACCEPT)
        pump(.1)
        self.assertFalse(self.path.exists())
        self.assertTrue(a.document.dirty)
        self.assertEqual(a.inputs['module'].get_text(),'2.5')
        a.save_as_dialog();pump(.15);dialog=a.project_dialog
        with patch.object(dialog,'get_file',return_value=None):
            dialog.emit('response',Gtk.ResponseType.ACCEPT)
        pump(.1)
        self.assertTrue(a.document.dirty)
        self.assertFalse(self.path.exists())

    def test_recovery_filesystem_failure_keeps_visible_edits_and_source_record(self):
        a=self.app
        with patch('project_document.os.replace',side_effect=OSError('Recovery volume full')):
            a.inputs['module'].set_text('unfinished')
        self.assertTrue(a.document.dirty)
        self.assertEqual(a.inputs['module'].get_text(),'unfinished')
        self.assertIn('Recovery unavailable',a.document_label.get_text())
        self.assertEqual(a.recovery_error,'Recovery volume full')
        a.undo_project()
        old=Store(self.root/'restore-failure')
        previous=Document(a.project_snapshot(),self.path)
        damaged=previous.current;damaged['raw']['helical']['module']='invalid'
        previous.record(damaged);old.checkpoint(previous)
        destination=a.project_store.folder/'recovery'/'restore-failure.json'
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_bytes(old.session.read_bytes())
        a.offer_recovery()
        with patch('project_document.os.replace',side_effect=OSError('disk full')):
            self.answer(Gtk.ResponseType.ACCEPT)
        self.assertTrue(destination.exists())
        self.assertFalse(a.document.dirty)
        self.assertEqual(a.config()['parameters']['module'],2)
        destination.unlink()

    def test_zz_real_window_close_save_discard_and_cancel(self):
        for index, code in enumerate((Gtk.ResponseType.CANCEL,Gtk.ResponseType.ACCEPT,Gtk.ResponseType.REJECT)):
            other=module.ReducerApp()
            other.set_application_id(f'local.solidcraft.reducers.closetests.p{os.getpid()}.n{index}')
            other.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
            other.register(None);other.activate();pump(.08)
            target=self.root/f'close-{index}.json'
            other.document.path=target
            other.inputs['module'].set_text('2.25')
            other.win.close();pump(.02)
            self.assertTrue(other.win.get_visible())
            self.assertIsInstance(other.project_dialog,Gtk.MessageDialog)
            other.project_dialog.response(code);pump(.04)
            if code==Gtk.ResponseType.CANCEL:
                self.assertTrue(other.win.get_visible())
                self.assertTrue(other.document.dirty)
                other.win.close();other.project_dialog.response(Gtk.ResponseType.REJECT);pump(.02)
            else:
                self.assertFalse(other.win.get_visible())
            self.assertEqual(target.exists(),code==Gtk.ResponseType.ACCEPT)
            self.assertFalse(other.project_store.session.exists())
            self.assertFalse(other.project_alive)


if __name__=='__main__':unittest.main()
