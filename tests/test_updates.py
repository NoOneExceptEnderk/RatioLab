# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Version precedence, release trust boundary and bounded anonymous discovery."""
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
import unittest
from urllib.error import HTTPError
import updates as u
from release_version import BASE_VERSION, RELEASE_VERSION, CHANNEL,validate_identity


def release(tag='v0.1.0-preview.3',**extra):
    result=dict(tag_name=tag,draft=False,prerelease='-' in tag,
                html_url=u.RELEASES_URL+'/tag/'+tag,body='## Published changes',assets=[])
    result.update(extra);return result


def asset(name,tag='v0.1.0-preview.3'):
    return dict(name=name,state='uploaded',browser_download_url=u.RELEASES_URL+'/download/'+tag+'/'+name)


def select_fixture(records,**target):
    """Historical preview fixture independent of the installed release identity."""
    options=dict(current='0.1.0-preview.2',channel='preview')
    options.update(target)
    return u.select_release(records,**options)


class UpdateTests(unittest.TestCase):
    def test_semver_precedence_and_release_identity(self):
        sequence=['0.1.0-alpha','0.1.0-alpha.1','0.1.0-preview.2','0.1.0-preview.3',
                  '0.1.0-preview.10','0.1.0-rc.1','0.1.0','0.1.1','1.0.0']
        self.assertEqual(sorted(sequence,key=u.Version),sequence)
        self.assertEqual(u.Version('v0.1.0+build.2'),u.Version('0.1.0'))
        for invalid in ['1.0','01.0.0','1.0.0-preview.03','1.0.0/evil','1٢.0.0',None,'v'*1000]:
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):u.Version(invalid)
        self.assertEqual(u.Version(BASE_VERSION).core,u.Version(RELEASE_VERSION).core)
        self.assertEqual(CHANNEL,'preview' if u.Version(RELEASE_VERSION).pre else 'stable')
        for bad in [None,{},dict(base='0.1.0',release='0.2.0-preview.1',channel='preview'),
                    dict(base='0.1.0',release='0.1.0-preview.1',channel='stable')]:
            with self.assertRaises(ValueError):validate_identity(bad)

    def test_current_stable_identity_rejects_preview_equal_and_older_releases(self):
        self.assertEqual(CHANNEL,'stable')
        self.assertEqual(BASE_VERSION,RELEASE_VERSION)
        major,minor,patch=u.Version(RELEASE_VERSION).core
        newer=f'{major}.{minor}.{patch+1}'
        records=[release('v'+RELEASE_VERSION),release('v0.1.0'),
                 release('v'+newer+'-preview.1'),release('v'+newer+'-rc.1')]
        self.assertIsNone(u.select_release(records))
        records.append(release('v'+newer))
        self.assertEqual(u.select_release(records).version,newer)

    def test_unsorted_list_channel_drafts_equal_older_and_final(self):
        records=[release('v0.1.0-preview.10'),release(),release('v0.1.0-preview.1'),
                 release('v99.0.0',draft=True),release('v0.1.0-preview.2')]
        self.assertEqual(select_fixture(records).version,'0.1.0-preview.10')
        self.assertIsNone(select_fixture(records,current='0.1.0',channel='stable'))
        self.assertIsNone(select_fixture([release('v0.1.0-preview.2'),release('v0.1.0-preview.1')]))
        records.append(release('v0.1.0',prerelease=False))
        self.assertEqual(select_fixture(records).version,'0.1.0')
        self.assertEqual(select_fixture(records,current='0.0.9',channel='stable').version,'0.1.0')
        self.assertIsNone(select_fixture([release('v0.1.1',prerelease=True)],current='0.1.0',channel='stable'))
        self.assertIsNone(select_fixture([release('v10.0.0-nightly.4')]))

    def test_untrusted_urls_and_malformed_records_are_never_opened(self):
        self.assertIsNone(select_fixture([release(html_url='https://evil.test/release'),None,release('invalid')]))
        for bad in ['http://github.com/a','https://github.com/attacker/repo/x',
                    'https://github.com.evil.test/'+u.REPOSITORY,'javascript:alert(1)']:
            record=release(assets=[dict(asset('RatioLab-0.1.0-linux-x86_64.run'),browser_download_url=bad)])
            result=select_fixture([record],system='linux',machine='x86_64')
            self.assertEqual(result.download,result.url)
        self.assertIsNone(select_fixture([release(draft=None)]))
        with self.assertRaises(ValueError):select_fixture({})

    def test_platform_download_formats_and_architecture(self):
        assets=[asset(name) for name in ['RatioLab-0.1.0-linux-x86_64.run',
                'ratiolab_0.1.0_amd64.deb','RatioLab-0.1.0-windows-x86_64-setup.exe',
                'RatioLab-0.1.0-macos-arm64.dmg','RatioLab-0.1.0-macos-x86_64.dmg']]
        for system,machine,exe,suffix in [('linux','x86_64','/home/a/RatioLab','.run'),
                ('linux','x86_64','/opt/ratiolab/RatioLab','.deb'),
                ('win32','AMD64','x','.exe'),('darwin','aarch64','x','arm64.dmg')]:
            result=select_fixture([release(assets=assets)],system=system,machine=machine,executable=exe)
            self.assertTrue(result.download.endswith(suffix),result)
        result=select_fixture([release(assets=assets)],system='win32',machine='arm64')
        self.assertEqual(result.download,result.url)

    def test_request_is_anonymous_bounded_and_rejects_redirects_errors(self):
        response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        response.geturl.return_value=u.API_URL;response.read.return_value=b'[]'
        opener=Mock();opener.open.return_value=response
        self.assertEqual(u.fetch_releases(opener),[])
        request=opener.open.call_args.args[0]
        self.assertEqual(request.full_url,u.API_URL)
        self.assertEqual(opener.open.call_args.kwargs,dict(timeout=15))
        self.assertNotIn('Authorization',request.headers)
        self.assertNotIn('Cookie',request.headers)
        self.assertEqual(request.headers['User-agent'],'RatioLab-update-check')
        response.read.assert_called_with(u.MAX_RESPONSE+1)
        response.read.return_value=b'x'*(u.MAX_RESPONSE+1)
        with self.assertRaises(ValueError):u.fetch_releases(opener)
        response.read.return_value=b'not json'
        with self.assertRaises(ValueError):u.fetch_releases(opener)
        response.geturl.return_value='https://evil.test'
        with self.assertRaises(ValueError):u.fetch_releases(opener)
        self.assertIsNone(u.NoRedirect().redirect_request(None,None,None,None,None,None))
        opener.open.side_effect=HTTPError(u.API_URL,429,'limited',{'Retry-After':'7200'},io.BytesIO())
        with self.assertRaises(u.RetryAfter) as error:u.fetch_releases(opener)
        self.assertEqual(error.exception.seconds,7200)
        opener.open.side_effect=OSError('offline')
        with self.assertRaises(OSError):u.fetch_releases(opener)

    def test_source_policy_skip_reminder_and_isolated_persistence(self):
        self.assertFalse(u.automatic_enabled({}))
        self.assertFalse(u.automatic_enabled({'RATIOLAB_UPDATE_CHECK':'0'}))
        self.assertTrue(u.automatic_enabled({'RATIOLAB_UPDATE_CHECK':'1'}))
        with patch.object(u,'SOURCE_ROOT',Path('/not-a-checkout')):self.assertTrue(u.automatic_enabled({}))
        with TemporaryDirectory() as temporary:
            path=Path(temporary)/'profile'/'updates.json';prefs=u.Preferences(path)
            current=select_fixture([release()]);newer=select_fixture([release('v0.1.0-preview.4')])
            self.assertTrue(prefs.visible(current,now=0));prefs.skip(current)
            self.assertFalse(u.Preferences(path).visible(current,now=0));self.assertTrue(prefs.visible(newer,now=0))
            prefs.remind(newer,now=100)
            self.assertFalse(prefs.visible(newer,now=100));self.assertTrue(prefs.visible(newer,now=100+3*u.DAY))
            path.write_text('invalid');self.assertEqual(u.Preferences(path).state,{})
            path.write_text('{"next_allowed": Infinity, "remind_until": NaN}')
            cleaned=u.Preferences(path)
            self.assertEqual(cleaned.state['next_allowed'],0)
            self.assertTrue(cleaned.visible(current,now=0))
            path.write_text(json.dumps({'next_allowed':10**30,'remind_until':10**30}))
            self.assertEqual(u.Preferences(path).state['next_allowed'],0)


if __name__=='__main__':unittest.main()
