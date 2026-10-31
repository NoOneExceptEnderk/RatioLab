# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Bounded one-time receipts never claim success from version or path guesses."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import update_receipt as receipt


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name)
        self.executable = self.cache/'app/RatioLab'
        self.job = self.cache/'ratiolab-install-fixture1'
        self.job.mkdir(mode=0o700)
        (self.job/'helper.log').write_text('installer output')
        self.slot = self.cache/receipt.receipt_name(self.executable)

    def publish(self, status='installed-restart-requested', **changes):
        data = receipt.metadata(self.job, self.executable, '0.1.13', '0.1.14')
        data.update(changes)
        self.slot.write_text(json.dumps(data))
        (self.job/'result').write_text(status+'\n')

    def consume(self, current='0.1.14'):
        return receipt.consume(self.cache, current=current, executable=self.executable)

    def test_success_requires_actual_terminal_result_and_exact_running_target(self):
        self.publish()
        outcome = self.consume()
        self.assertTrue(outcome.success)
        self.assertIn('updated to 0.1.14', outcome.message)
        self.assertEqual(outcome.log_path, self.job/'helper.log')
        self.assertIsNone(self.consume())
        self.assertFalse(self.slot.exists())
        self.assertEqual((self.job/'helper.log').read_text(), 'installer output')

    def test_old_or_unrelated_running_version_never_claims_success(self):
        for current in ('0.1.13', '0.1.15'):
            self.publish()
            outcome = self.consume(current)
            self.assertFalse(outcome.success)
            self.assertIn('still running version '+current, outcome.message)

    def test_failure_and_cancel_are_visible_even_if_target_happens_to_be_running(self):
        for status in ('installer-failed', 'checksum-mismatch', 'timeout', 'cancelled'):
            self.publish(status)
            outcome = self.consume()
            self.assertFalse(outcome.success)
            self.assertEqual(outcome.log_path, self.job/'helper.log')
            self.assertIn('cancelled' if status == 'cancelled' else 'Could not update', outcome.message)
            self.assertIsNone(self.consume())

    def test_malformed_oversized_unknown_and_foreign_records_are_consumed_without_success(self):
        cases = ['not json', 'x'*(receipt.MAX_RECEIPT+1), '[]']
        for raw in cases:
            self.slot.write_text(raw)
            outcome = self.consume()
            self.assertFalse(outcome.success)
            self.assertIsNone(outcome.log_path)
            self.assertIsNone(self.consume())
        for change in ({'job': '../other'}, {'job': str(self.job)}, {'source': '0.1.15'},
                       {'target': 'not-a-version'}, {'executable': '/other/RatioLab'},
                       {'unexpected': 'field'}, {'format': 'other'}):
            self.publish(**change)
            self.assertFalse(self.consume().success)
            self.assertIsNone(self.consume())
        self.publish('made-up-success')
        self.assertFalse(self.consume().success)

    def test_symlink_receipt_result_job_and_log_never_expose_an_external_path(self):
        external = self.cache/'personal-file'
        external.write_text('keep me')
        self.slot.symlink_to(external)
        self.assertFalse(self.consume().success)
        self.assertEqual(external.read_text(), 'keep me')
        for name in ('result', 'helper.log'):
            self.publish()
            path = self.job/name
            path.unlink()
            path.symlink_to(external)
            outcome = self.consume()
            self.assertFalse(outcome.success)
            self.assertIsNone(outcome.log_path)
            path.unlink()
            path.write_text('installed\n' if name == 'result' else 'log')
        self.publish()
        other = self.cache/'other-job'
        self.job.rename(other)
        self.job.symlink_to(other, target_is_directory=True)
        outcome = self.consume()
        self.assertFalse(outcome.success)
        self.assertIsNone(outcome.log_path)

    def test_missing_result_and_nonprivate_job_are_never_success(self):
        self.publish()
        (self.job/'result').unlink()
        self.assertFalse(self.consume().success)
        self.publish()
        self.job.chmod(0o755)
        self.assertFalse(self.consume().success)

    def test_other_installation_slot_is_untouched(self):
        self.publish()
        self.assertIsNone(receipt.consume(self.cache,current='0.1.14',executable='/other/RatioLab'))
        self.assertTrue(self.slot.exists())
        self.assertTrue(self.consume().success)

    def test_windows_receipt_normalizes_case_and_parent_components_without_posix_ownership(self):
        slot=self.cache/receipt.receipt_name(self.executable,system='win32')
        data=receipt.metadata(self.job,self.executable,'0.1.13','0.1.14',system='win32')
        slot.write_text(json.dumps(data));(self.job/'result').write_text('installed-restart-requested')
        alternate=str(self.executable.parent/'unused/../RatioLab').upper()
        self.assertEqual(slot.name,receipt.receipt_name(alternate,system='win32'))
        self.job.chmod(0o755)
        with patch.object(receipt.os,'getuid',side_effect=AssertionError('POSIX ownership used'),create=True):
            outcome=receipt.consume(self.cache,current='0.1.14',executable=alternate,system='win32')
        self.assertTrue(outcome.success)
        self.assertFalse(slot.exists())

    def test_windows_reparse_directories_are_rejected_before_reading_job_contents(self):
        from types import SimpleNamespace
        slot=self.cache/receipt.receipt_name(self.executable,system='win32')
        data=receipt.metadata(self.job,self.executable,'0.1.13','0.1.14',system='win32')
        slot.write_text(json.dumps(data));(self.job/'result').write_text('installed')
        original=Path.lstat
        def linked(path):
            info=original(path)
            return SimpleNamespace(st_mode=info.st_mode,st_file_attributes=0x400) if path==self.job else info
        with patch.object(Path,'lstat',linked):
            outcome=receipt.consume(self.cache,current='0.1.14',executable=self.executable,system='win32')
        self.assertFalse(outcome.success)
        self.assertIsNone(outcome.log_path)

    def test_restart_required_and_failed_native_checks_remain_failures(self):
        for status,phrase in (('reboot-required','requires a system restart'),
                ('authorization-failed','authorization was not granted'),
                ('runtime-invalid','could not be verified'),
                ('signature-invalid','signature could not be verified'),
                ('mount-failed','disk image could not be opened'),
                ('rollback-failed','previous application could not be restored')):
            self.publish(status)
            outcome=self.consume()
            self.assertFalse(outcome.success)
            self.assertIn(phrase,outcome.message)


if __name__ == '__main__':
    unittest.main()
