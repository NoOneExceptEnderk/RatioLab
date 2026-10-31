# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Pinned fetch, portable source and manifest-only loopback HTTP regressions."""
import hashlib
from http.client import HTTPConnection
from io import BytesIO
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT/'scripts'/f'{name}.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


fetcher = module('fetch-web-runtime')
server = module('serve-webapp')
builder = module('build-webapp')


class DistributionTests(unittest.TestCase):
    def test_fetch_fixed_urls_alias_exact_size_hash_and_cache_reuse(self):
        # Small mock payloads exercise all six actual filenames without network.
        config = fetcher.configuration()
        payloads = {name: ('fixture '+name).encode() for name in config['files']}
        config['files'] = {name: dict(size=len(data), sha256=hashlib.sha256(data).hexdigest()) for name, data in payloads.items()}
        expected_urls = {
            'https://cdn.jsdelivr.net/pyodide/v314.0.7/full/'+name: name
            for name in ('pyodide-lock.json', 'pyodide.asm.mjs', 'pyodide.asm.wasm',
                         'pyodide.mjs', 'python_stdlib.zip')
        }
        expected_urls['https://raw.githubusercontent.com/pyodide/pyodide/314.0.7/LICENSE'] = 'PYODIDE-LICENSE'
        calls = []

        def opener(url, timeout):
            self.assertEqual(timeout, 60)
            calls.append(url)
            name = expected_urls[url]
            return BytesIO(payloads[name])

        with tempfile.TemporaryDirectory() as temporary, patch.object(fetcher, 'configuration', return_value=config):
            cache = Path(temporary)/'runtime'
            with self.assertRaisesRegex(ValueError, 'Missing pinned'):
                fetcher.fetch_runtime(cache, check_only=True, opener=opener)
            self.assertFalse(cache.exists())
            fetched = fetcher.fetch_runtime(cache, opener=opener)
            self.assertEqual(set(fetched), set(payloads))
            self.assertEqual(set(calls), set(expected_urls))
            self.assertEqual(len(calls), len(expected_urls))
            (cache/'verification.json').write_text('private metadata retained')
            with patch.object(fetcher.urllib.request, 'build_opener', side_effect=AssertionError('network forbidden')):
                self.assertEqual(fetcher.fetch_runtime(cache), [])
                self.assertEqual(fetcher.fetch_runtime(cache, check_only=True), [])
            self.assertEqual((cache/'verification.json').read_text(), 'private metadata retained')
            self.assertEqual({p.name for p in cache.iterdir()}, set(payloads)|{'verification.json'})

    def test_failed_fetch_is_atomic_preserves_edited_foreign_and_symlink_targets(self):
        config = fetcher.configuration()
        first = sorted(config['files'])[0]
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary)/'runtime'
            with self.assertRaisesRegex(ValueError, 'Downloaded runtime differs'):
                fetcher.fetch_runtime(cache, opener=lambda *a, **k: BytesIO(b'invalid'))
            self.assertEqual(list(cache.iterdir()), [])
            target = cache/first
            target.write_text('keep foreign bytes')
            with patch.object(fetcher.urllib.request, 'build_opener', side_effect=AssertionError('network forbidden')):
                with self.assertRaisesRegex(ValueError, 'Refusing to replace'):
                    fetcher.fetch_runtime(cache)
            self.assertEqual(target.read_text(), 'keep foreign bytes')
            target.unlink(); target.symlink_to(Path(temporary)/'missing')
            with self.assertRaisesRegex(ValueError, 'ordinary file'):
                fetcher.fetch_runtime(cache)
            self.assertTrue(target.is_symlink())
            alias = Path(temporary)/'alias'; alias.symlink_to(cache, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'symlinks'):
                fetcher.fetch_runtime(alias)

    def test_download_transport_failure_and_publish_race_never_replace_target(self):
        config = fetcher.configuration()
        payloads = {name: name.encode() for name in config['files']}
        config['files'] = {name: dict(size=len(data), sha256=hashlib.sha256(data).hexdigest()) for name, data in payloads.items()}
        with tempfile.TemporaryDirectory() as temporary, patch.object(fetcher, 'configuration', return_value=config):
            cache = Path(temporary)/'cache'
            calls = []

            def fail_second(url, **kwargs):
                calls.append(url)
                if len(calls) == 2:
                    raise OSError('transport failed')
                return BytesIO(payloads[sorted(payloads)[0]])

            with self.assertRaisesRegex(OSError, 'transport failed'):
                fetcher.fetch_runtime(cache, opener=fail_second)
            self.assertEqual(list(cache.iterdir()), [])

            def racing_opener(url, **kwargs):
                name = next(n for n, u in fetcher.UPSTREAM_URLS.items() if url == u)
                if name == sorted(payloads)[0]:
                    (cache/name).write_text('new foreign target')
                return BytesIO(payloads[name])

            with self.assertRaises(FileExistsError):
                fetcher.fetch_runtime(cache, opener=racing_opener)
            self.assertEqual((cache/sorted(payloads)[0]).read_text(), 'new foreign target')
            self.assertEqual([p.name for p in cache.iterdir()], [sorted(payloads)[0]])

    def test_pin_change_and_redirect_are_rejected(self):
        config = fetcher.configuration(); config['version'] = 'next'
        with patch.object(fetcher.json, 'loads', return_value=config):
            with self.assertRaisesRegex(ValueError, 'pins changed'):
                fetcher.configuration()
        with self.assertRaisesRegex(ValueError, 'must not redirect'):
            fetcher.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://elsewhere.invalid/')

    def test_loopback_allowlist_head_mime_no_listing_escape_or_changed_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)/'bundle'; builder.build(folder, external_runtime=True)
            # Minimal runtime fixtures permit MIME checks without a download.
            manifest = json.loads((folder/'bundle-manifest.json').read_text())
            for name in ['runtime/probe.mjs', 'runtime/probe.wasm']:
                path = folder/name; path.parent.mkdir(exist_ok=True); path.write_bytes(b'fixture')
                manifest['files'][name] = dict(size=7, sha256=hashlib.sha256(b'fixture').hexdigest())
            (folder/'bundle-manifest.json').write_bytes(builder.encoded(manifest))
            (folder/'private.txt').write_text('must never escape')
            (folder/'unlisted-link').symlink_to(ROOT/'AGENTS.md')
            httpd = server.make_server(folder, 0)
            self.assertEqual(httpd.server_address[0], '127.0.0.1')
            thread = threading.Thread(target=httpd.serve_forever, daemon=True); thread.start()

            def request(path, method='GET'):
                conn = HTTPConnection('127.0.0.1', httpd.server_port, timeout=5)
                try:
                    conn.request(method, path); response = conn.getresponse()
                    return response.status, dict(response.getheaders()), response.read()
                finally:
                    conn.close()

            try:
                status, headers, data = request('/')
                self.assertEqual(status, 200); self.assertEqual(data, (folder/'index.html').read_bytes())
                status, headers, data = request('/runtime/probe.mjs', 'HEAD')
                self.assertEqual(status, 200); self.assertEqual(headers['Content-Type'], 'text/javascript'); self.assertEqual(data, b'')
                self.assertEqual(headers['Content-Length'], '7')
                self.assertEqual(request('/runtime/probe.wasm')[1]['Content-Type'], 'application/wasm')
                for path in ['/runtime/', '/private.txt', '/unlisted-link', '/../AGENTS.md', '/%2e%2e/AGENTS.md', '/%2fetc/passwd', '/.git/config', '/source.zip/anything']:
                    self.assertEqual(request(path)[0], 404, path)
                client = folder/'engine-client.js'; client.write_text('changed')
                self.assertEqual(request('/engine-client.js')[0], 409)
                client.unlink(); client.symlink_to(ROOT/'AGENTS.md')
                status, _, data = request('/engine-client.js')
                self.assertEqual(status, 409); self.assertNotIn(b'Local development workspace', data)
                # Replacing a listed parent with a symlink cannot expose files.
                shutil.rmtree(folder/'runtime'); (folder/'runtime').symlink_to(Path(temporary), target_is_directory=True)
                self.assertEqual(request('/runtime/probe.mjs')[0], 409)
            finally:
                httpd.shutdown(); httpd.server_close(); thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
            with self.assertRaisesRegex(ValueError, 'Symlinks'):
                server.verify_bundle(folder)

    @unittest.skipUnless(os.environ.get('RATIOLAB_TEST_WEB_RUNTIME'), 'Set RATIOLAB_TEST_WEB_RUNTIME to a verified six-file cache.')
    def test_real_pinned_cache_reuse_without_network(self):
        cache = Path(os.environ['RATIOLAB_TEST_WEB_RUNTIME'])
        with patch.object(fetcher.urllib.request, 'build_opener', side_effect=AssertionError('network forbidden')):
            self.assertEqual(fetcher.fetch_runtime(cache, check_only=True), [])
            self.assertEqual(fetcher.fetch_runtime(cache), [])
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)/'output'
            first = builder.build(output, runtime_dir=cache)
            before = (output/'bundle-manifest.json').read_bytes()
            second = builder.build(output, runtime_dir=cache)
            self.assertEqual(first, second)
            self.assertEqual(before, (output/'bundle-manifest.json').read_bytes())
            server.verify_bundle(output)
            self.assertEqual(first['runtime_mode'], 'selfhost')
            for name in fetcher.configuration()['files']:
                self.assertEqual((output/'runtime'/name).read_bytes(), (cache/name).read_bytes())

    def test_notices_provenance_and_sdist_rules(self):
        provenance = json.loads((ROOT/'webapp/notices/provenance.json').read_text())
        self.assertEqual(set(provenance), set(builder.NOTICES)-{'README.txt', 'provenance.json'})
        for name, pin in provenance.items():
            data = (ROOT/'webapp/notices'/name).read_bytes()
            self.assertEqual(len(data), pin['size'])
            self.assertEqual(hashlib.sha256(data).hexdigest(), pin['sha256'])
            self.assertTrue(pin['url'].startswith(('https://raw.githubusercontent.com/', fetcher.PINNED_BASE)))
        self.assertEqual(provenance['PYODIDE-LICENSE']['url'],
                         'https://raw.githubusercontent.com/pyodide/pyodide/314.0.7/LICENSE')
        self.assertEqual(provenance['PYODIDE-LICENSE']['url'], fetcher.UPSTREAM_URLS['PYODIDE-LICENSE'])
        manifest = (ROOT/'MANIFEST.in').read_text()
        self.assertIn('recursive-include tests test_*.py *.mjs', manifest)
        self.assertIn('recursive-include webapp *.py *.js *.css *.html *.json *.txt', manifest)
        self.assertIn('include webapp/notices/*', manifest)
        self.assertIn('prune work', manifest)


if __name__ == '__main__':
    unittest.main()
