# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Real GTK search/apply/history/lifecycle integration; isolated user profiles."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import time
import unittest
from unittest.mock import patch
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk,Gio,GLib
import app as module
import combination_search_ui as ui
from combination_search import Settings
from geometry import generate
from project_document import equivalent


def pump(duration=.04):
    until=time.monotonic()+duration
    context=GLib.MainContext.default()
    while time.monotonic()<until:
        while context.pending():context.iteration(False)
        time.sleep(.002)


def wait_until(predicate,seconds=15):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        pump(.02)
        if predicate():return True
    return False


class CombinationSearchGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Gtk.init_check() or Gdk.Display.get_default() is None:raise unittest.SkipTest('GTK display required')
        cls.temp=TemporaryDirectory(prefix='ratiolab-search-gui-')
        root=Path(cls.temp.name)
        cls.env=patch.dict(os.environ,dict(XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'),APPDATA=str(root/'roaming'),LOCALAPPDATA=str(root/'local')));cls.env.start()
        cls.app=module.ReducerApp();cls.app.set_application_id(f'local.solidcraft.reducers.searchtests.p{os.getpid()}');cls.app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        cls.app.register(None);cls.app.activate();pump(.15)

    @classmethod
    def tearDownClass(cls):
        for w in cls.app.get_windows():w.destroy()
        pump();cls.env.stop();cls.temp.cleanup()

    def setUp(self):
        a=self.app;c=a.combination_search
        c.invalidate()
        if c.thread:c.thread.join(3)
        self.assertTrue(c.thread is None or not c.thread.is_alive())
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='parallel',parameters=generate('parallel').values))
        c.open();c.populate();pump()
        self.c=c

    def run_search(self,settings=None,axes=None):
        self.c.start(settings or Settings(target=3,tolerance_percent=0),axes if axes is not None else {'pinion':(20,21),'wheel':(60,63)})
        self.assertTrue(wait_until(lambda:self.c.cancel is None,20))
        self.assertIsNotNone(self.c.result,self.c.summary.get_text())
        return self.c.result

    def changed_proposal(self):
        return next(p for p in self.c.result.proposals if p.changes)

    def test_apply_one_undo_redo_same_document_path_other_families_and_save(self):
        a=self.app;c=self.c
        a.values['spur']=generate('spur',{'teeth':28}).values
        a.raw_edits['spur']={'teeth':'28','bore':'-'}
        a.project_changed();a.reset_defaults();self.assertTrue(a.undo_reset.get_visible())
        path=Path(self.temp.name)/'saved.json';self.assertTrue(a.save_project(path=path))
        doc=a.document;before=a.project_snapshot();clean=doc.clean;oldindex=doc.index
        r=self.run_search();p=self.changed_proposal()
        self.assertEqual(a.document.index,oldindex)
        c.list.select_row(next(row for row in self.rows() if row.proposal is p))
        self.assertTrue(c.apply_button.get_sensitive());self.assertTrue(c.apply_selected())
        self.assertIs(a.document,doc);self.assertEqual(doc.path,path);self.assertEqual(doc.clean,clean)
        self.assertEqual(doc.index,oldindex+1);self.assertTrue(doc.dirty);self.assertFalse(a.undo_reset.get_visible())
        self.assertEqual(a.design.values,p.values);self.assertEqual(a.values['spur'],before['values']['spur']);self.assertEqual(a.raw_edits['spur'],before['raw']['spur'])
        self.assertIsNone(c.result);self.assertIsNone(a.interference.result)
        a.undo_project();self.assertTrue(equivalent(a.project_snapshot(),before));self.assertFalse(doc.dirty);self.assertIs(a.document,doc)
        a.redo_project();self.assertEqual(a.design.values,p.values);self.assertTrue(doc.dirty)
        self.assertTrue(a.save_project());self.assertFalse(doc.dirty)
        import json
        self.assertEqual(json.loads(path.read_text())['parameters'],p.values)
        self.assertEqual(a.document.path,path)
        self.assertFalse(c.apply(p))

    def rows(self):
        row=self.c.list.get_first_child()
        while row is not None:
            yield row
            row=row.get_next_sibling()

    def test_preserve_hidden_current_family_values_and_no_phantom_reconcile(self):
        a=self.app;c=self.c
        # Cached fields from a two-stage variant must survive applying a single-stage proposal.
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='planetary',parameters=generate('planetary').values))
        a.values['planetary']['sun2']=33;a.raw_edits['planetary']['sun2']='33'
        a.project_changed();a.save_project(path=Path(self.temp.name)/'hidden.json');c.populate()
        before=a.project_snapshot();index=a.document.index
        self.run_search(Settings(target=4,tolerance_percent=10),{'sun':(18,21),'planet':(18,21)})
        p=self.changed_proposal();self.assertTrue(c.apply(p));self.assertEqual(a.values['planetary']['sun2'],33);self.assertEqual(a.raw_edits['planetary']['sun2'],'33')
        self.assertEqual(a.document.index,index+1);token=a.document.token
        a.refresh();a.project_changed();self.assertEqual(a.document.token,token)
        a.undo_project();self.assertTrue(equivalent(a.project_snapshot(),before));a.redo_project();self.assertEqual(a.design.values,p.values)

    def test_raw_edit_invalidates_before_debounce_and_blocks_search(self):
        a=self.app;c=self.c;self.run_search();p=self.changed_proposal()
        a.inputs['module'].set_text('-')
        self.assertIsNone(c.result);self.assertFalse(c.apply_button.get_sensitive());self.assertFalse(c.apply(p))
        pump(.12);self.assertIsNone(a.design);c.start();self.assertIsNone(c.result);self.assertIn('Invalid',c.summary.get_text())

    def test_identical_document_replacement_undo_and_stale_callback(self):
        a=self.app;c=self.c;r=self.run_search();p=self.changed_proposal();serial=c.serial;token=a.document.token
        a.load_config_data(a.config());self.assertNotEqual(a.document.identity,token[0]);self.assertIsNone(c.result)
        c.finished(serial,r,None);self.assertIsNone(c.result);self.assertFalse(c.apply(p));self.assertIsNone(c.list.get_first_child())
        c.populate();self.run_search();snapshot=a.project_snapshot();a.restore_project_snapshot(snapshot);self.assertIsNone(c.result)

    def test_real_cancel_retains_partial_and_no_worker_duplication_after_edit(self):
        a=self.app;c=self.c
        c.start(Settings(target=3,tolerance_percent=99,max_seconds=30),{'pinion':tuple(range(12,101)),'wheel':tuple(range(22,201))})
        first=c.thread;c.stop()
        self.assertTrue(wait_until(lambda:c.cancel is None,5));self.assertIsNotNone(c.result);self.assertFalse(c.result.complete);self.assertIn('cancelled',c.result.reason)
        self.assertIs(c.thread,first)
        # Gate only the call boundary, then execute the real search. A new worker
        # cannot overlap the invalidated old one, even before its callback arrives.
        entered=Event();release=Event();real=ui.search
        def gated(*args,**kwargs):
            entered.set();release.wait(3);return real(*args,**kwargs)
        with patch.object(ui,'search',gated):
            c.start(Settings(target=3,tolerance_percent=0),{'pinion':(20,21),'wheel':(60,63)})
            self.assertTrue(entered.wait(2));first=c.thread
            a.inputs['module'].set_text('2.1');self.assertIsNone(c.cancel);self.assertIsNone(c.result)
            c.start();self.assertIs(c.thread,first);self.assertIn('stopping',c.status.get_text())
            release.set();self.assertTrue(wait_until(lambda:not first.is_alive(),5));pump();self.assertIsNone(c.result)

    def test_request_change_close_and_single_gear_inapplicable(self):
        a=self.app;c=self.c;self.run_search();c.fields['target'].set_text('nan');self.assertIsNone(c.result)
        c.start();self.assertIn('Invalid search request',c.summary.get_text());self.assertIsNone(c.cancel)
        c.fields['target'].set_text('3');self.run_search();r=c.result;serial=c.serial;c.window.close();pump()
        self.assertIsNone(c.window);self.assertIsNone(c.result);c.finished(serial,r,None);self.assertIsNone(c.result)
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='spur',parameters=generate('spur').values))
        c.open();self.assertIn('single gear',c.scope.get_text());self.assertFalse(c.run_button.get_sensitive());c.start();self.assertIsNone(c.result)

    def test_refresh_save_without_edit_keeps_results_and_document_clean(self):
        a=self.app;c=self.c;r=self.run_search();token=a.document.token;index=a.document.index
        a.refresh();a.project_changed();self.assertIs(c.result,r);self.assertEqual(a.document.token,token);self.assertEqual(a.document.index,index)
        a.save_project(path=Path(self.temp.name)/'same.json');self.assertIs(c.result,r);self.assertFalse(a.document.dirty)
        self.assertTrue(c.current(c.serial))

    def test_apply_invalidates_actual_interference_result_and_inspection(self):
        a=self.app;c=self.c
        a.load_config_data(dict(format='solidcraft-riduttori/1',family='parallel',parameters=generate('parallel',{'input_rpm':0}).values))
        from interference import Settings as CheckSettings
        check=a.interference;check.open();check.start(CheckSettings(step_degrees=180,max_seconds=20))
        self.assertTrue(wait_until(lambda:check.cancel is None,25));self.assertIsNotNone(check.result)
        check.list.select_row(check.list.get_row_at_index(0));self.assertIsNotNone(a.canvas.inspection_phase)
        c.populate();self.run_search();self.assertIsNotNone(check.result)
        self.assertTrue(c.apply(self.changed_proposal()));self.assertIsNone(check.result);self.assertIsNone(a.canvas.inspection_phase)

    def test_main_window_destroy_cancels_worker_and_rejects_callbacks(self):
        a=module.ReducerApp();a.set_application_id(f'local.solidcraft.reducers.searchclose.p{os.getpid()}');a.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        a.register(None);a.activate();pump();c=a.combination_search;c.open()
        c.start(Settings(target=3,tolerance_percent=99,max_seconds=30),{'pinion':tuple(range(12,101)),'wheel':tuple(range(22,201))})
        event=c.cancel;thread=c.thread;self.assertIsNotNone(event)
        a.win.destroy();pump();self.assertFalse(c.alive);self.assertTrue(event.is_set())
        self.assertTrue(wait_until(lambda:not thread.is_alive(),5));self.assertIsNone(c.result)
        for window in a.get_windows():window.destroy()

    def test_form_lock_grids_and_invalid_integer_do_not_change_model(self):
        a=self.app;c=self.c;before=a.config();token=a.document.token
        for key,(locked,entry,_) in c.axes.items():locked.set_active(True)
        self.assertEqual(c.read_axes(),{})
        locked,entry,_=c.axes['module'];locked.set_active(False);entry.set_text('1.8,2')
        self.assertEqual(c.read_axes(),{'module':(1.8,2.)})
        r=self.run_search(Settings(target=3,tolerance_percent=0),c.read_axes())
        self.assertEqual(len(r.proposals),2);self.assertTrue(all(p.values['pinion']==20 and p.values['wheel']==60 for p in r.proposals))
        self.assertEqual(a.config(),before);self.assertEqual(a.document.token,token)
        c.start(Settings(target=3),{'pinion':(20.5,)})
        self.assertTrue(wait_until(lambda:c.cancel is None,5));self.assertIsNone(c.result);self.assertIn('integer',c.summary.get_text())

if __name__=='__main__':unittest.main()
