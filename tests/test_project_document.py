# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""GTK-free project history, atomic persistence and recovery contracts."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from project_document import Document, Store, atomic_json


def snapshot(text='18'):
    return dict(family='planetary', values={'planetary':dict(sun=18)}, raw={'planetary':dict(sun=text)})


class DocumentTests(unittest.TestCase):
    def test_grouping_checkpoint_branch_and_duplicate_callbacks(self):
        d = Document(snapshot())
        d.record(snapshot('1'), 'sun', now=0)
        d.record(snapshot('19'), 'sun', now=.2)
        self.assertEqual(len(d.states), 2)
        self.assertFalse(d.record(snapshot('19'), 'sun', now=.3))
        d.mark_saved('/tmp/model.json')
        self.assertFalse(d.dirty)
        d.record(snapshot('20'), 'sun', now=.4)
        self.assertEqual(len(d.states), 3)
        self.assertTrue(d.dirty)
        d.undo();self.assertFalse(d.dirty)
        d.redo();self.assertTrue(d.dirty)
        d.undo();d.record(snapshot('21'), 'sun', now=.5)
        self.assertEqual(d.redo(), snapshot('21'))
        self.assertEqual(len(d.states), 3)

    def test_reconcile_normalization_replaces_current_edit_and_keeps_checkpoint(self):
        d=Document(snapshot('10'))
        d.record(snapshot('2'),'width')
        d.reconcile(snapshot('8'))
        self.assertEqual(len(d.states),2)
        d.mark_saved('/tmp/model.json')
        self.assertFalse(d.dirty)
        self.assertEqual(d.undo(),snapshot('10'))
        self.assertEqual(d.redo(),snapshot('8'))
        self.assertFalse(d.dirty)

    def test_numeric_formatting_and_invalid_edits(self):
        d = Document(snapshot())
        self.assertFalse(d.record(snapshot('18.00')))
        self.assertFalse(d.dirty)
        self.assertTrue(d.record(snapshot('abc')))
        self.assertTrue(d.dirty)
        self.assertEqual(d.undo(), snapshot())
        self.assertEqual(d.redo(), snapshot('abc'))

    def test_automatic_display_and_equivalent_explicit_edit_share_checkpoint(self):
        automatic = snapshot()
        automatic['raw']['planetary'].clear()
        d = Document(automatic)
        self.assertFalse(d.record(snapshot('00018.000')))
        self.assertFalse(d.dirty)
        changed = snapshot('18.0000001')
        changed['values']['planetary']['sun'] = 18.0000001
        self.assertTrue(d.record(changed))
        self.assertTrue(d.dirty)
        self.assertEqual(d.undo(), automatic)
        self.assertFalse(d.dirty)
        self.assertTrue(d.record(snapshot('-')))

    def test_automatic_display_provenance_survives_recovery_without_dirtying_format(self):
        automatic = snapshot()
        automatic['automatic'] = {'planetary': ['sun']}
        d = Document(automatic)
        self.assertFalse(d.record(snapshot('18.000')))
        self.assertFalse(d.dirty)
        changed = deepcopy(automatic)
        changed['raw']['planetary']['sun'] = 'unfinished'
        changed['automatic']['planetary'] = []
        self.assertTrue(d.record(changed))
        with TemporaryDirectory() as folder:
            store = Store(folder)
            store.checkpoint(d)
            restored = store.read_recovery(store.session, {'planetary'})
            self.assertEqual(restored.current, changed)
            self.assertEqual(restored.clean, automatic)
            self.assertEqual(restored.undo(), automatic)

    def test_snapshot_is_not_aliased_and_history_is_bounded(self):
        original = snapshot();d = Document(original)
        original['raw']['planetary']['sun'] = 'bad'
        self.assertEqual(d.current, snapshot())
        for n in range(250):d.record(snapshot(str(n)))
        self.assertLessEqual(len(d.states),201)
        self.assertGreaterEqual(d.index,0)
        self.assertTrue(d.dirty)

    def test_atomic_failure_keeps_previous_file_and_removes_staging(self):
        with TemporaryDirectory() as folder:
            target=Path(folder)/'è model.json'
            atomic_json(target,dict(before=True))
            before=target.read_bytes()
            with patch('project_document.os.replace',side_effect=OSError('disk error')):
                with self.assertRaises(OSError):atomic_json(target,dict(after=True))
            self.assertEqual(target.read_bytes(),before)
            self.assertEqual(list(Path(folder).iterdir()),[target])
            with self.assertRaises(ValueError):atomic_json(target,dict(x=float('nan')))
            self.assertEqual(target.read_bytes(),before)

    def test_recovery_preserves_invalid_text_checkpoint_and_unicode_recents(self):
        with TemporaryDirectory() as folder:
            store=Store(folder);d=Document(snapshot(),Path(folder)/'spazi e è.json')
            d.record(snapshot('incomplete-'))
            store.checkpoint(d)
            other=Store(folder)
            self.assertEqual(other.candidates(),[store.session])
            restored=other.read_recovery(store.session, {'planetary'})
            self.assertEqual(restored.current,snapshot('incomplete-'))
            self.assertEqual(restored.clean,snapshot())
            self.assertTrue(restored.dirty)
            for path in [Path(folder)/'è con spazi.json',Path(folder)/'missing.json']:
                store.remember(path)
            store.remember(Path(folder)/'è con spazi.json')
            self.assertEqual(len(store.recent()),2)
            self.assertIn('è con spazi',store.recent()[0])
            restored.mark_saved(restored.path);other.checkpoint(restored)
            self.assertFalse(other.session.exists())

    def test_corrupt_recovery_and_recents_are_preserved_for_explicit_decision(self):
        with TemporaryDirectory() as folder:
            store=Store(folder)
            store.session.parent.mkdir(parents=True)
            store.session.write_text('{bad',encoding='utf-8')
            with self.assertRaises(ValueError):store.read_recovery(store.session,{'planetary'})
            self.assertTrue(store.session.exists())
            (Path(folder)/'recent-projects.json').write_text('{}')
            self.assertEqual(store.recent(),[])
            self.assertTrue(store.recent_error)


if __name__=='__main__':unittest.main()
