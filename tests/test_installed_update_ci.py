# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""CI metadata credentials never reach package requests or native children."""
import importlib.util
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import HTTPSHandler, Request, build_opener
from urllib.response import addinfourl

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'installed_update_ci', ROOT/'scripts/check-installed-update.py')
ci = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ci)
TOKEN_KEY = 'RATIOLAB_CI_GITHUB_TOKEN'
TOKEN = 'disposable-test-fixture-not-a-secret'


class MetadataAuthenticationTests(unittest.TestCase):
    def test_metadata_request_authenticated_and_native_child_environment_clean(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.geturl.return_value = ci.updates.API_URL
        response.read.return_value = b'[]'
        transport = Mock()

        def opened(request, **kwargs):
            self.assertEqual(request.full_url, ci.updates.API_URL)
            self.assertEqual(request.get_header('Authorization'), 'Bearer '+TOKEN)
            self.assertNotIn('Authorization', request.headers)
            self.assertEqual(kwargs, {'timeout': 15})
            self.assertNotIn(TOKEN_KEY, os.environ)
            return response

        transport.open.side_effect = opened
        with patch.dict(os.environ, {TOKEN_KEY:TOKEN}), \
                patch.object(ci, 'build_opener', return_value=transport) as build:
            self.assertEqual(ci.fetch_baseline_releases(), [])
            self.assertNotIn(TOKEN_KEY, os.environ)
            child = subprocess.run(
                [sys.executable, '-c',
                 'import os; assert "RATIOLAB_CI_GITHUB_TOKEN" not in os.environ'],
                capture_output=True, check=True, timeout=10)
            self.assertEqual(child.stdout, b'')
        self.assertIsInstance(build.call_args.args[0], ci.updates.NoRedirect)
        response.read.assert_called_once_with(ci.updates.MAX_RESPONSE+1)

    def test_without_token_keeps_existing_anonymous_metadata_path(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(ci.updates, 'fetch_releases', return_value=[]) as fetch, \
                patch.object(ci, 'build_opener') as build:
            self.assertEqual(ci.fetch_baseline_releases(), [])
        fetch.assert_called_once_with()
        build.assert_not_called()

    def test_authentication_rejects_artifacts_other_endpoints_and_methods(self):
        transport = Mock()
        with patch.object(ci, 'build_opener', return_value=transport):
            opener = ci.MetadataOpener(TOKEN)
        for url in (ci.updates.RELEASES_URL+'/download/v0.1.12/SHA256SUMS',
                    ci.updates.RELEASES_URL+'/download/v0.1.12/RatioLab.run',
                    'https://example.org/releases', ci.updates.API_URL+'&extra=1',
                    ci.updates.API_URL.replace('https:', 'http:')):
            with self.subTest(url=url), self.assertRaises(ValueError):
                opener.open(Request(url), timeout=15)
        with self.assertRaises(ValueError):
            opener.open(Request(ci.updates.API_URL, method='POST'), timeout=15)
        transport.open.assert_not_called()

    def test_redirects_cannot_forward_metadata_authorization(self):
        for status in (301, 302, 303, 307, 308):
            seen = []

            class RedirectResponse(HTTPSHandler):
                def https_open(self, request):
                    seen.append(request)
                    response = addinfourl(BytesIO(b''),
                        {'Location':'https://example.org/collect'}, request.full_url, status)
                    response.msg = 'Redirect'
                    return response

            transport = build_opener(ci.updates.NoRedirect(), RedirectResponse())
            with self.subTest(status=status), \
                    patch.object(ci, 'build_opener', return_value=transport), \
                    patch.dict(os.environ, {TOKEN_KEY:TOKEN}):
                with self.assertRaises(HTTPError) as error:
                    ci.fetch_baseline_releases()
                self.assertEqual(error.exception.code, status)
                error.exception.close()
                self.assertNotIn(TOKEN_KEY, os.environ)
            self.assertEqual(len(seen), 1)
            self.assertEqual(seen[0].full_url, ci.updates.API_URL)
            self.assertEqual(seen[0].get_header('Authorization'), 'Bearer '+TOKEN)

    def test_metadata_failure_still_removes_token(self):
        with patch.dict(os.environ, {TOKEN_KEY:TOKEN}), \
                patch.object(ci.updates, 'fetch_releases', side_effect=ValueError('invalid metadata')):
            with self.assertRaisesRegex(ValueError, 'invalid metadata'):
                ci.fetch_baseline_releases()
            self.assertNotIn(TOKEN_KEY, os.environ)


class FailureDiagnosticsTests(unittest.TestCase):
    def test_failed_helper_report_is_bounded_data_and_retains_gate_state(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            job = work/'cache/ratiolab/updates/install-handoffs/ratiolab-install-test'
            job.mkdir(parents=True)
            for name in ('ready', 'armed'):
                (job/name).touch()
            (job/'result').write_bytes(b'failed\n'+b'x'*5000)
            (job/'helper.log').write_text('Referenced log body must not enter the JSON.')
            process = Mock()
            process.poll.return_value = 1
            prepared = SimpleNamespace(directory=job, _process=process,
                                       status=lambda:'failed')
            parent = Mock()
            parent.poll.return_value = 0
            error = RuntimeError('exception argv/token details must not enter the JSON')
            ci.write_failure_report(work, prepared, parent, 'helper-terminal-status', error)
            serialized = (work/'update-failure.json').read_text()
            report = json.loads(serialized)
            self.assertEqual(report['helper_returncode'], 1)
            self.assertEqual(report['parent_returncode'], 0)
            self.assertEqual(report['helper_status'], 'failed')
            self.assertEqual(report['error_type'], 'RuntimeError')
            self.assertEqual(report['phase'], 'helper-terminal-status')
            files = report['jobs'][0]['files']
            self.assertTrue(files['ready']['present'])
            self.assertTrue(files['armed']['present'])
            self.assertFalse(files['cancel']['present'])
            self.assertEqual(len(files['result']['text']), 4096)
            self.assertTrue(files['result']['truncated'])
            self.assertEqual(files['result']['bytes'], 5007)
            self.assertEqual(files['helper.log']['path'], str(job/'helper.log'))
            self.assertNotIn('log body', serialized)
            self.assertNotIn('argv/token', serialized)
            self.assertLess(len(serialized), 12000)

    def test_preparation_failure_reports_at_most_four_controlled_jobs(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            handoffs = work/'cache/ratiolab/updates/install-handoffs'
            for index in range(7):
                (handoffs/('ratiolab-install-'+str(index))).mkdir(parents=True)
            ci.write_failure_report(work, None, None, 'prepare-helper', RuntimeError('failure'))
            report = json.loads((work/'update-failure.json').read_text())
            self.assertEqual(len(report['jobs']), 4)
            self.assertIsNone(report['helper_returncode'])
            self.assertIsNone(report['helper_status'])
            self.assertIsNone(report['parent_returncode'])

    @unittest.skipUnless(hasattr(os, 'symlink'), 'symlinks unavailable')
    def test_result_symlink_is_referenced_without_reading_its_target(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root/'outside'
            target.write_text('Do not read this target')
            link = root/'result'
            try:
                link.symlink_to(target)
            except OSError as error:
                self.skipTest('Symlink creation unavailable: '+type(error).__name__)
            record = ci.diagnostic_file(link, result_text=True)
            self.assertTrue(record['present'])
            self.assertFalse(record['regular'])
            self.assertNotIn('text', record)


if __name__ == '__main__':
    unittest.main()
