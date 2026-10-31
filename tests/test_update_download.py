# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Headless package integrity, resource limits and download trust boundaries."""
from dataclasses import replace
import hashlib
import io
import os
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import update_download as d
import updates as u

TAG = 'v0.1.12'
NAME = 'RatioLab-0.1.12-linux-x86_64.run'
PREFIX = u.RELEASES_URL + '/download/' + TAG + '/'
PACKAGE = b'#!/bin/sh\nthis must never execute\n'
SHA = hashlib.sha256(PACKAGE).hexdigest()
RELEASE = u.Release('0.1.12', u.RELEASES_URL+'/tag/'+TAG, 'Notes', PREFIX+NAME,
                    NAME, len(PACKAGE), PREFIX+'SHA256SUMS')


class Response(io.BytesIO):
    def __init__(self, url, data=b'', status=200, headers=None):
        super().__init__(data)
        self.url = url
        self.status = status
        self.headers = {} if headers is None else headers
    def geturl(self):return self.url
    def getcode(self):return self.status


class Opener:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []
    def open(self, request, timeout):
        self.calls.append((request, timeout))
        value = self.routes[request.full_url]
        if isinstance(value, BaseException):raise value
        return value() if callable(value) else value


def fixture(checksums=None, package=PACKAGE, headers=None):
    checksums = (SHA+'  '+NAME+'\n').encode() if checksums is None else checksums
    return Opener({RELEASE.checksums_url:Response(RELEASE.checksums_url, checksums),
                   RELEASE.download:Response(RELEASE.download, package, headers=headers)})


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name)/'cache'

    def assert_clean(self):
        self.assertEqual(list(self.parent.iterdir()) if self.parent.exists() else [], [])

    def test_good_download_permissions_progress_reverify_and_owned_cleanup(self):
        opener = fixture(headers={'Content-Length':str(len(PACKAGE))})
        progress = []
        with patch('subprocess.Popen', side_effect=AssertionError('No execution')):
            result = d.download_release(RELEASE, self.parent, opener=opener,
                                        progress=lambda *args:progress.append(args))
        self.assertEqual(result.path.read_bytes(), PACKAGE)
        self.assertEqual(result.sha256, SHA)
        self.assertTrue(result.reverify())
        self.assertEqual(stat.S_IMODE(result.path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(result.path.parent.stat().st_mode), 0o700)
        self.assertEqual(progress, [(0,len(PACKAGE)), (len(PACKAGE),len(PACKAGE))])
        self.assertEqual([call[0].full_url for call in opener.calls],
                         [RELEASE.checksums_url,RELEASE.download])
        for request, timeout in opener.calls:
            self.assertTrue(0 < timeout <= 15)
            self.assertNotIn('Authorization',request.headers)
            self.assertNotIn('Cookie',request.headers)
        result.cleanup()
        result.cleanup()
        self.assert_clean()

    def test_cleanup_cannot_target_caller_files_or_replaced_jobs(self):
        source = Path(self.temporary.name)/'source'
        source.write_bytes(b'preserve')
        forged = d.VerifiedDownload(source, SHA, RELEASE)
        with self.assertRaises(ValueError):forged.cleanup()
        self.assertEqual(source.read_bytes(), b'preserve')
        result = d.download_release(RELEASE,self.parent,opener=fixture())
        old = result.path.parent.with_name('preserved-job')
        result.path.parent.rename(old)
        result.path.parent.symlink_to(Path(self.temporary.name),target_is_directory=True)
        with self.assertRaises(ValueError):result.cleanup()
        self.assertTrue(source.exists())

    def test_independent_random_jobs_do_not_overwrite_parent_files(self):
        self.parent.mkdir()
        original = self.parent/NAME
        original.write_bytes(b'original')
        first = d.download_release(RELEASE,self.parent,opener=fixture())
        second = d.download_release(RELEASE,self.parent,opener=fixture())
        self.assertNotEqual(first.path,second.path)
        first.cleanup(); second.cleanup()
        self.assertEqual(original.read_bytes(),b'original')

    def test_checksum_failures_remove_job_without_reading_package(self):
        cases = [b'', (SHA+'  '+NAME+'.other\n').encode(),
                 (SHA+'  '+NAME+'\n'+SHA+' *'+NAME+'\n').encode(),
                 (SHA+'  ../'+NAME+'\n').encode(),
                 (SHA+'  ./'+NAME+'\n').encode(),
                 (SHA+'  folder/'+NAME+'\n').encode(),
                 (SHA+'  '+NAME+'\n'+SHA+'  '+NAME.lower()+'\n').encode(),
                 b'not a checksum\n', b'\xff']
        for raw in cases:
            with self.subTest(raw=raw):
                opener=fixture(checksums=raw)
                with self.assertRaises(ValueError):d.download_release(RELEASE,self.parent,opener=opener)
                self.assertEqual(len(opener.calls),1)
                self.assert_clean()

    def test_binary_checksum_style_and_unrelated_entries(self):
        raw = (SHA.upper()+' *'+NAME+'\n'+'0'*64+'  ratiolab_0.1.12_amd64.deb\n').encode()
        result=d.download_release(RELEASE,self.parent,opener=fixture(checksums=raw))
        self.assertEqual(result.sha256,SHA)

    def test_checksum_mismatch_and_reverification_detect_changes(self):
        with self.assertRaisesRegex(ValueError,'checksum mismatch'):
            d.download_release(RELEASE,self.parent,opener=fixture(package=b'x'*len(PACKAGE)))
        self.assert_clean()
        result=d.download_release(RELEASE,self.parent,opener=fixture())
        result.path.write_bytes(b'x'*len(PACKAGE))
        with self.assertRaisesRegex(ValueError,'changed'):result.reverify()
        result.path.unlink()
        other=Path(self.temporary.name)/'other';other.write_bytes(PACKAGE)
        result.path.symlink_to(other)
        with self.assertRaises(ValueError):result.reverify()
        result.cleanup()
        self.assertTrue(other.exists())

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'FIFO needs POSIX')
    def test_reverify_rejects_fifo_before_opening_it(self):
        result=d.download_release(RELEASE,self.parent,opener=fixture())
        result.path.unlink()
        os.mkfifo(result.path)
        with patch.object(d.os,'open',side_effect=AssertionError('FIFO must not be opened')):
            with self.assertRaisesRegex(ValueError,'regular file'):result.reverify()
        result.cleanup()

    def test_manually_constructed_untrusted_metadata_is_rejected_before_io(self):
        changes=[dict(url='https://evil.test/tag/'+TAG),dict(version='0.1.13'),
                 dict(url=RELEASE.url+'?query'),dict(download=RELEASE.download+'?q'),
                 dict(download=RELEASE.download+'#fragment'),
                 dict(download=RELEASE.download.replace('https:','http:')),
                 dict(download=RELEASE.download.replace('github.com','github.com.evil.test')),
                 dict(download=RELEASE.download.replace('github.com','user:pass@github.com')),
                 dict(download=RELEASE.download.replace('github.com','github.com:443')),
                 dict(asset_name='../'+NAME),dict(asset_name='other.run'),
                 dict(checksums_url=PREFIX+'SHA256SUMS.txt'),dict(checksums_url=''),
                 dict(asset_size=0),dict(asset_size=True),dict(asset_size=d.MAX_PACKAGE+1)]
        for change in changes:
            with self.subTest(change=change),self.assertRaises(ValueError):
                d.download_release(replace(RELEASE,**change),self.parent,opener=fixture())
        with self.assertRaises(ValueError):
            d.download_release(u.Release('0.1.12',RELEASE.url,'',RELEASE.download),self.parent)
        self.assert_clean()

    def test_limits_declared_size_and_truncated_http_body(self):
        for package,headers in [(PACKAGE[:-1],{}),(PACKAGE+b'x',{}),
                                (PACKAGE,{'Content-Length':'999999999999'}),
                                (PACKAGE,{'Content-Length':'invalid'}),
                                (PACKAGE,{'Content-Length':str(len(PACKAGE)-1)})]:
            with self.subTest(headers=headers),self.assertRaises(ValueError):
                d.download_release(RELEASE,self.parent,opener=fixture(package=package,headers=headers))
            self.assert_clean()
        with patch.object(d,'MAX_CHECKSUMS',8),self.assertRaises(ValueError):
            d.download_release(RELEASE,self.parent,opener=fixture())
        self.assert_clean()
        unknown=replace(RELEASE,asset_size=None)
        with patch.object(d,'MAX_PACKAGE',len(PACKAGE)-1),self.assertRaises(ValueError):
            d.download_release(unknown,self.parent,opener=fixture())
        self.assert_clean()
        with self.assertRaisesRegex(ValueError,'Truncated'):
            d.download_release(unknown,self.parent,opener=fixture(package=PACKAGE[:-1],
                                        headers={'Content-Length':str(len(PACKAGE))}))
        self.assert_clean()

    def test_cancellation_before_start_and_during_progress_cleans_partial(self):
        cancel=threading.Event();cancel.set()
        opener=fixture()
        with self.assertRaises(d.DownloadCancelled):
            d.download_release(RELEASE,self.parent,cancel=cancel,opener=opener)
        self.assertEqual(opener.calls,[])
        cancel.clear()
        def progress(received,total):
            if received:cancel.set()
        with self.assertRaises(d.DownloadCancelled):
            d.download_release(RELEASE,self.parent,cancel=cancel,progress=progress,opener=fixture())
        self.assert_clean()
        with self.assertRaises(d.DownloadCancelled):
            d.download_release(RELEASE,self.parent,cancel=lambda:True,opener=fixture())

    def test_callback_error_network_error_and_deadline_clean_job(self):
        def fail(*args):raise RuntimeError('callback')
        with self.assertRaises(RuntimeError):
            d.download_release(RELEASE,self.parent,progress=fail,opener=fixture())
        self.assert_clean()
        opener=fixture();opener.routes[RELEASE.download]=OSError('offline')
        with self.assertRaises(OSError):d.download_release(RELEASE,self.parent,opener=opener)
        self.assert_clean()
        with patch.object(d,'TOTAL_TIMEOUT',-1),self.assertRaises(TimeoutError):
            d.download_release(RELEASE,self.parent,opener=fixture())
        self.assert_clean()

    def test_controlled_https_cdn_redirects_and_http_error_redirect(self):
        for host in sorted(d.CDN_HOSTS):
            with self.subTest(host=host):
                cdn='https://'+host+'/asset?signature=needed'
                opener=fixture()
                opener.routes[RELEASE.download]=HTTPError(RELEASE.download,302,'Found',
                                                          {'Location':cdn},io.BytesIO())
                opener.routes[cdn]=Response(cdn,PACKAGE)
                result=d.download_release(RELEASE,self.parent,opener=opener)
                self.assertTrue(result.reverify());result.cleanup()

    def test_unsafe_redirects_are_rejected_before_destination_request(self):
        urls=['http://release-assets.githubusercontent.com/asset',
              'https://evil.test/asset','https://release-assets.githubusercontent.com.evil.test/a',
              'https://user:password@release-assets.githubusercontent.com/a',
              'https://release-assets.githubusercontent.com:443/a',
              'https://release-assets.githubusercontent.com/a#fragment',
              PREFIX+'other.run',RELEASE.download]
        for url in urls:
            with self.subTest(url=url):
                opener=fixture()
                opener.routes[RELEASE.download]=Response(RELEASE.download,status=302,headers={'Location':url})
                with self.assertRaises(ValueError):d.download_release(RELEASE,self.parent,opener=opener)
                self.assertEqual(len(opener.calls),2)
                self.assert_clean()

    def test_redirect_limit_and_hidden_redirect_are_rejected(self):
        opener=fixture()
        opener.routes[RELEASE.download]=Response(RELEASE.download,status=302,
                  headers={'Location':'https://release-assets.githubusercontent.com/0'})
        for i in range(6):
            url='https://release-assets.githubusercontent.com/'+str(i)
            opener.routes[url]=Response(url,status=302,
                  headers={'Location':'https://release-assets.githubusercontent.com/'+str(i+1)})
        with self.assertRaisesRegex(ValueError,'Too many'):d.download_release(RELEASE,self.parent,opener=opener)
        self.assert_clean()
        opener=fixture()
        opener.routes[RELEASE.download]=Response('https://release-assets.githubusercontent.com/hidden',PACKAGE)
        with self.assertRaisesRegex(ValueError,'automatic'):d.download_release(RELEASE,self.parent,opener=opener)
        self.assert_clean()


if __name__=='__main__':unittest.main()
