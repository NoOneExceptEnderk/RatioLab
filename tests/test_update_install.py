# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Headless adapters; only harmless installers in isolated temporary trees run."""
import base64
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import update_install as install
import update_receipt
from update_download import VerifiedDownload
from updates import Release, RELEASES_URL, select_release


class InstallTests(unittest.TestCase):
    def test_update_actions_describe_the_actual_platform_steps(self):
        from types import SimpleNamespace
        for suffix, label, phrase in (
            ('.run', 'Update now', 'reopen automatically'),
            ('setup.exe', 'Update now', 'reopen automatically'),
            ('.dmg', 'Update now', 'reopen automatically'),
            ('.deb', 'Update now', 'approve the system authorization')):
            action, detail = install.update_action(SimpleNamespace(package_format=suffix))
            self.assertEqual(action, label)
            self.assertIn(phrase, detail)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='ratiolab-adapter-test-')
        self.root = Path(self.temporary.name)
        self.bundle = self.root/"user's app with spaces"
        self.bundle.mkdir()
        self.bundle.chmod(0o700)
        self.children = []
        self.prepared = []
        self.executable = self.bundle/'RatioLab'
        self.executable.write_text('#!/bin/sh\nexit 0\n')
        self.executable.chmod(0o700)
        self.marker = self.bundle/'.ratiolab-installation'
        self.marker.write_text(install.MARKER+'\n')
        self.marker.chmod(0o600)
        self.manifest()

    def tearDown(self):
        for prepared in self.prepared:
            prepared.cancel()
        for prepared in self.prepared:
            try:
                prepared._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                prepared._process.kill()
                prepared._process.wait(timeout=3)
        for child in self.children:
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=3)
        self.temporary.cleanup()

    def manifest(self, *, system='linux', arch='x86_64', current='0.1.11', **changes):
        data = dict(format='ratiolab-bundle/1', application_id='local.solidcraft.reducers',
                    version='0.1.11', release={'release': current}, system=system,
                    arch=arch, executable=self.executable.name,
                    files=[dict(path=self.executable.name, kind='file',
                                size=self.executable.stat().st_size,
                                sha256=hashlib.sha256(self.executable.read_bytes()).hexdigest())])
        data.update(changes)
        path = self.bundle/'bundle-manifest.json'
        path.write_text(json.dumps(data))
        path.chmod(0o600)
        return path

    def detection(self, **kwargs):
        return install.detect_installation(**(dict(system='linux', machine='x86_64',
                        executable=self.executable, frozen=True, current='0.1.11') | kwargs))

    def package(self, data=b'#!/bin/sh\nexit 0\n', *, suffix='.run', version='0.1.12', system='linux', arch='x86_64'):
        job = Path(tempfile.mkdtemp(prefix='verified-', dir=self.root))
        job.chmod(0o700)
        name = f'ratiolab_{version}_amd64.deb' if suffix == '.deb' else f'RatioLab-{version}-{system}-{arch}'+('-setup.exe' if suffix == 'setup.exe' else suffix)
        path = job/name
        path.write_bytes(data)
        path.chmod(0o600)
        url = RELEASES_URL+'/download/v'+version+'/'
        release = Release(version, RELEASES_URL+'/tag/v'+version, '', url+name,
                          name, len(data), url+'SHA256SUMS')
        info = job.stat()
        return VerifiedDownload(path, hashlib.sha256(data).hexdigest(), release,
                                job, (info.st_dev, info.st_ino))

    def parent(self):
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
        self.children.append(child)
        return child

    def prepare(self, package=None, installation=None, **kwargs):
        prepared = install.prepare_install(package or self.package(), installation or self.detection(),
                                           directory=kwargs.pop('directory', self.root/'helpers'), **kwargs)
        self.prepared.append(prepared)
        return prepared

    def wait_result(self, prepared, expected):
        prepared._process.wait(timeout=5)
        self.assertEqual(prepared.result_path.read_text().strip(), expected,
                         prepared.log_path.read_text())

    def test_source_and_wheel_never_native(self):
        for executable in (self.executable, self.root/'venv/bin/python'):
            found = self.detection(frozen=False, executable=executable)
            self.assertFalse(found.can_install)
            self.assertEqual(found.kind, 'manual')
            self.assertIsNone(found.package_format)
            with self.assertRaises(ValueError):
                self.prepare(installation=found)

    def test_marked_bundle_exact_target_and_explicit_selection(self):
        found = self.detection(machine='AMD64')
        self.assertTrue(found.can_install, found.explanation)
        self.assertTrue(found.requires_exit)
        self.assertEqual(found.destination, self.bundle)
        self.assertEqual(found.package_format, '.run')
        package = self.package()
        release = package.release
        assets = [dict(name=release.asset_name, state='uploaded', size=release.asset_size,
                       browser_download_url=release.download),
                  dict(name='SHA256SUMS', state='uploaded', browser_download_url=release.checksums_url)]
        record = dict(tag_name='v0.1.12', html_url=release.url, draft=False, prerelease=False,
                      body='', assets=assets)
        selected = select_release([record], current='0.1.11', **found.selection_target())
        self.assertEqual(selected.asset_name, release.asset_name)

    def test_unmarked_portable_is_manual_tar(self):
        self.marker.unlink()
        found = self.detection()
        self.assertFalse(found.can_install)
        self.assertEqual(found.package_format, '.tar.gz')

    def test_wrong_marker_manifest_and_current_identity(self):
        self.marker.write_text(install.MARKER+' extra')
        self.assertFalse(self.detection().can_install)
        self.marker.write_text(install.MARKER)
        self.marker.chmod(0o600)
        for change in ({'system': 'windows'}, {'arch': 'arm64'}, {'version': '0.1.10'},
                       {'executable': 'Other'}, {'release': {'release': '0.1.10'}},
                       {'files': []}, {'application_id': 'other'}):
            self.manifest(**change)
            self.assertFalse(self.detection().can_install, change)

    def test_links_wrong_types_and_permissions_are_not_owned(self):
        found = self.detection()
        self.executable.chmod(0o722)
        self.assertFalse(self.detection().can_install)
        self.executable.chmod(0o700)
        self.bundle.chmod(0o777)
        self.assertFalse(self.detection().can_install)
        self.bundle.chmod(0o700)
        linked = self.root/'linked'
        linked.symlink_to(self.bundle, target_is_directory=True)
        self.assertFalse(self.detection(executable=linked/'RatioLab').can_install)
        self.marker.unlink()
        self.marker.symlink_to(self.manifest())
        self.assertFalse(self.detection().can_install)
        self.assertTrue(found.can_install)

    def test_wrong_owner_is_manual(self):
        with patch.object(install.os, 'getuid', return_value=os.getuid()+1):
            self.assertFalse(self.detection().can_install)

    def test_unsupported_architecture(self):
        self.assertFalse(self.detection(machine='arm64').can_install)

    def test_windows_requires_exact_hkcu_record_and_manifest(self):
        self.executable.rename(self.bundle/'RatioLab.exe')
        self.executable = self.bundle/'RatioLab.exe'
        self.manifest(system='windows')
        self.marker.unlink()
        missing = self.detection(system='win32', registry_reader=lambda: '')
        guessed = self.detection(system='win32', registry_reader=lambda: str(self.bundle.parent))
        owned = self.detection(system='win32', registry_reader=lambda: str(self.bundle))
        self.assertFalse(missing.can_install)
        self.assertFalse(guessed.can_install)
        self.assertEqual(owned.kind, 'windows-setup')
        self.assertTrue(owned.requires_exit)
        self.assertEqual(owned.package_format, 'setup.exe')
        self.assertEqual(owned.selection_target()['package_format'], 'setup.exe')

    def test_windows_registry_probe_requests_64bit_user_key(self):
        class Key:
            def __enter__(self): return self
            def __exit__(self, *args): pass
        class Registry:
            HKEY_CURRENT_USER = 'HKCU'
            KEY_READ = 1
            KEY_WOW64_64KEY = 256
            REG_SZ = 1
            def OpenKey(self, hive, key, reserved, flags):
                self.call = hive, key, reserved, flags
                return Key()
            def QueryValueEx(self, key, value): return str(self.bundle), self.REG_SZ
        registry = Registry()
        registry.bundle = self.bundle
        with patch.dict(sys.modules, {'winreg': registry}):
            self.assertEqual(install._registry_location(), str(self.bundle))
        self.assertEqual(registry.call, ('HKCU', install.UNINSTALL_KEY, 0, 257))

    def test_windows_silent_setup_is_pinned_gated_and_never_reboots_or_closes_other_apps(self):
        self.executable.rename(self.bundle/'RatioLab.exe')
        self.executable = self.bundle/'RatioLab.exe'
        self.manifest(system='windows')
        found = self.detection(system='win32', registry_reader=lambda: str(self.bundle))
        package = self.package(suffix='setup.exe', system='windows')
        script = install._powershell_script(self.root, found, package.path, package.sha256, 123, '456', 120,
                                            target=package.release.version)
        self.assertIn("user''s app with spaces", script)
        self.assertIn('StartTime.ToFileTimeUtc()', script)
        self.assertIn('Get-FileHash -LiteralPath', script)
        self.assertNotIn('Add-Content -LiteralPath', script)
        self.assertIn('RegistryView]::Registry64', script)
        for flag in ('/SILENT','/SUPPRESSMSGBOXES','/SP-','/NORESTART','/RESTARTEXITCODE=3010',
                     '/NOCLOSEAPPLICATIONS','/NORESTARTAPPLICATIONS','/DIR="','/LOG="'):
            self.assertIn(flag,script)
        self.assertNotIn('/VERYSILENT',script)
        self.assertNotIn('Stop-Process', script)
        self.assertLess(script.index('while ($true)'), script.index('Start-Process -FilePath $package'))
        self.assertLess(script.index("RegistryView]::Registry64"),script.index('Start-Process -FilePath $package'))
        self.assertIn("$sourceVersion = '0.1.11'",script)
        self.assertIn("$targetVersion = '0.1.12'",script)
        self.assertIn("$status = 'reboot-required'",script)
        self.assertLess(script.index('Runtime-Valid $targetVersion'),script.index('$restartPath = $executable'))
        self.assertLess(script.index('  Finish\n'),script.index('Start-Process -FilePath $restartPath'))
        for required in ('16777216','50000','Duplicate or external runtime path',"LinkType -eq 'HardLink'",
                         'Runtime-Valid $sourceVersion $sourceBase','Get-FileHash -LiteralPath $old.FullName'):
            self.assertIn(required,script)
        with self.assertRaises(ValueError):
            install._powershell_script(self.root,found,package.path,package.sha256,123,'456',120,target='0.1.11')
        self.assertEqual(base64.b64decode(base64.b64encode(script.encode('utf-16-le'))).decode('utf-16-le'), script)

    def test_windows_helper_failure_reaches_inherited_log_and_keeps_boolean_result(self):
        powershell = (os.environ.get('RATIOLAB_TEST_POWERSHELL') or shutil.which('pwsh')
                      or shutil.which('powershell.exe'))
        if not powershell:
            self.skipTest('PowerShell is needed to execute the generated helper diagnostic fixture')
        self.executable.rename(self.bundle/'RatioLab.exe')
        self.executable = self.bundle/'RatioLab.exe'
        self.manifest(system='windows')
        found = self.detection(system='win32', registry_reader=lambda: str(self.bundle))
        package = self.package(suffix='setup.exe', system='windows')
        job = self.root/'ratiolab-install-diagnostic'
        job.mkdir(mode=0o700)
        (job/'armed').touch()
        script = install._powershell_script(job, found, package.path, package.sha256, 123, '456', 120,
                                            target=package.release.version, restart=False)
        # Exercise the generated catch/finally and Runtime-Valid catch with real
        # PowerShell, but no Windows process, registry, Setup or installation.
        # Reopening helper.log is forbidden even on hosts without Windows file
        # sharing restrictions. All diagnostics must use the inherited handle.
        fixture = """function Get-Process { param($Id, $ErrorAction) return $null }
function Ordinary-Item { throw 'injected package probe failure' }
function Add-Content { throw 'unexpected diagnostic file reopen' }
$valid = Runtime-Valid '0.1.12' '0.1.12'
[Console]::Out.WriteLine('runtime-valid=' + $valid)
"""
        script = script.replace("$status = 'failed'\n", fixture+"$status = 'failed'\n", 1)
        encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
        log = job/'helper.log'
        with log.open('wb') as stream:
            result = subprocess.run([powershell, '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                                    stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT,
                                    timeout=30, check=False)
        diagnostics = log.read_text(encoding='utf-8')
        self.assertEqual(result.returncode, 0, diagnostics)
        self.assertIn('runtime-valid=False', diagnostics)
        self.assertIn('injected package probe failure', diagnostics)
        self.assertIn('Update helper failed during verifying the update package; status=failed', diagnostics)
        self.assertIn('Update helper terminal result: failed', diagnostics)
        self.assertNotIn('unexpected diagnostic file reopen', diagnostics)
        self.assertNotIn('running Setup', diagnostics)
        self.assertEqual((job/'result').read_text(encoding='ascii'), 'failed')

    def test_macos_unproven_application_location_is_manual_without_source_replacement(self):
        executable = self.root/'RatioLab.app/Contents/MacOS/RatioLab'
        executable.parent.mkdir(parents=True)
        executable.write_text('fake native executable')
        info = executable.parents[1]/'Info.plist'
        info.write_bytes(plistlib.dumps(dict(CFBundleIdentifier='local.solidcraft.reducers',
                                            CFBundleExecutable='RatioLab',CFBundleShortVersionString='0.1.11')))
        found = self.detection(system='darwin', machine='arm64', executable=executable)
        self.assertEqual(found.kind, 'macos-dmg')
        self.assertFalse(found.can_install)
        self.assertFalse(found.requires_exit)
        self.assertEqual(found.package_format, '.dmg')
        self.assertIn('Download manually',found.explanation)

    def test_debian_database_probe_requires_exact_installed_package(self):
        executable = Path('/opt/ratiolab/RatioLab')
        def read(path, limit):
            return (b'/opt/ratiolab/RatioLab\n' if str(path).endswith('.list') else
                    b'Package: ratiolab\nStatus: install ok installed\n\nPackage: another\n')
        with patch.object(install, '_bounded', side_effect=read):
            self.assertTrue(install._debian_owns(executable))
            self.assertFalse(install._debian_owns(Path('/opt/ratiolab/Other')))
        with patch.object(install, '_bounded', return_value=b'Package: ratiolab\nStatus: deinstall ok config-files\n'):
            self.assertFalse(install._debian_owns(executable))

    def test_debian_is_not_guessed_from_opt(self):
        # The real /opt installation is never opened or changed by this test.
        self.assertFalse(self.detection(executable='/opt/ratiolab/not-ratiolab',
                                        debian_owner=lambda path: True).can_install)
        found = self.detection(debian_owner=lambda path: True)
        self.assertEqual(found.kind, 'linux-bundle')

    def test_debian_exact_managed_opt_target_can_update_only_with_system_tools(self):
        # Inject filesystem reads for /opt; do not inspect/run/change the user's
        # real application. Native package handlers are not launched.
        executable = Path('/opt/ratiolab/RatioLab')
        info = self.executable.stat()
        manifest = (self.bundle/'bundle-manifest.json').read_bytes()
        identity = install._identity
        with (patch.object(install, '_ordinary', return_value=info),
              patch.object(install, '_bounded', return_value=manifest),
              patch.object(install, '_identity', side_effect=lambda path: identity(self.executable)),
              patch.object(install.os,'access',return_value=True)):
            found = self.detection(executable=executable, debian_owner=lambda path: path == executable)
        self.assertEqual(found.kind, 'debian')
        self.assertEqual(found.package_format, '.deb')
        self.assertTrue(found.requires_exit)
        self.assertTrue(found.can_install)
        with (patch.object(install, '_ordinary', return_value=info),
              patch.object(install, '_bounded', return_value=manifest),
              patch.object(install, '_identity', side_effect=lambda path: identity(self.executable)),
              patch.object(install.os,'access',return_value=False)):
            manual=self.detection(executable=executable,debian_owner=lambda path:True)
        self.assertFalse(manual.can_install)
        self.assertFalse(manual.requires_exit)
        self.assertEqual(manual.package_format,'.deb')
        self.assertIn('Download manually',manual.explanation)

    def test_debian_rejects_nonpackage_archive_before_preparing_a_helper(self):
        parent = self.parent()
        package = self.package(suffix='.deb')
        found = replace(self.detection(),kind='debian',package_format='.deb',requires_exit=True)
        with (patch.object(install,'_revalidate'),patch.object(install.os,'access',return_value=True)):
            with self.assertRaises(subprocess.CalledProcessError):
                self.prepare(package=package,installation=found,parent_pid=parent.pid)
        self.assertFalse((self.root/'helpers').exists())
        self.assertIsNone(parent.poll())

    def debian_fixture(self, *, package_name='ratiolab', package_version='0.1.12', arch='amd64',
                       runtime_version='0.1.12', authorization=0, apt_code=0):
        """A tiny real .deb plus nonprivileged replacements for fixed commands."""
        marker=self.root/'reopened-runtime'
        def runtime(version):
            return ('#!/bin/sh\ncase "${1:-}" in\n'
                +f'--version) printf "%s\\n" {shlex.quote("RatioLab "+version)} ;;\n'
                +'--diagnose) exit 0 ;;\n'
                +f'*) printf "%s" {shlex.quote(version)} > {shlex.quote(str(marker))} ;;\nesac\n')
        self.executable.write_text(runtime('0.1.11'))
        self.manifest()
        installation=replace(self.detection(),kind='debian',package_format='.deb',requires_exit=True)
        tree=self.root/'debian-package';(tree/'DEBIAN').mkdir(parents=True)
        (tree/'DEBIAN/control').write_text(f'Package: {package_name}\nVersion: {package_version}\n'
            +f'Architecture: {arch}\nMaintainer: Test <test@example.invalid>\nDescription: harmless updater fixture\n')
        app=tree/'opt/ratiolab';app.mkdir(parents=True)
        (app/'RatioLab').write_text(runtime(runtime_version));(app/'RatioLab').chmod(0o700)
        manifest=json.loads((self.bundle/'bundle-manifest.json').read_text())
        manifest.update(version='0.1.12',release={'release':'0.1.12'},files=[dict(path='RatioLab',kind='file',
            size=(app/'RatioLab').stat().st_size,sha256=hashlib.sha256((app/'RatioLab').read_bytes()).hexdigest())])
        (app/'bundle-manifest.json').write_text(json.dumps(manifest))
        archive=self.root/'fixture.deb'
        subprocess.run(['/usr/bin/dpkg-deb','--build',str(tree),str(archive)],check=True,
                       stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        package=self.package(archive.read_bytes(),suffix='.deb')
        state=self.root/'installed-version';state.write_text('0.1.11')
        calls=self.root/'authorization-arguments'
        tools={name:self.root/('fixture-'+Path(name).name) for name in install.DEBIAN_TOOLS}
        tools['/usr/bin/dpkg-deb'].write_text('#!/bin/sh\nexec /usr/bin/dpkg-deb "$@"\n')
        tools['/usr/bin/dpkg-query'].write_text('#!/bin/sh\nprintf "install ok installed\\n%s\\namd64" '
                                              +f'"$(cat {shlex.quote(str(state))})"\n')
        tools['/usr/bin/pkexec'].write_text('#!/bin/sh\nprintf "%s\\n" "$@" > '+shlex.quote(str(calls))+'\n'
            +f'if [ {authorization} -ne 0 ]; then exit {authorization}; fi\nshift\nexec "$@"\n')
        tools['/usr/bin/apt-get'].write_text('#!/bin/sh\n'
            +(f'printf partial > {shlex.quote(str(self.executable))}\nexit {apt_code}\n' if apt_code else
              f'cp {shlex.quote(str(app/"RatioLab"))} {shlex.quote(str(self.executable))}\n'
              +f'cp {shlex.quote(str(app/"bundle-manifest.json"))} {shlex.quote(str(self.bundle/"bundle-manifest.json"))}\n'
              +f'printf 0.1.12 > {shlex.quote(str(state))}\n'))
        for tool in tools.values():tool.chmod(0o700)
        return dict(package=package,installation=installation,tools=tools,marker=marker,calls=calls,state=state)

    def prepare_debian_fixture(self, fixture, parent):
        spawn=install._spawn
        access=install.os.access
        def harmless_spawn(argv,**kwargs):
            helper=Path(argv[1]);text=helper.read_text()
            for original,replacement in fixture['tools'].items():
                text=text.replace(original,shlex.quote(str(replacement)))
            helper.write_text(text)
            return spawn(argv,**kwargs)
        def availability(path,mode):
            return True if path in install.DEBIAN_TOOLS else access(path,mode)
        with (patch.object(install,'_revalidate'),patch.object(install,'_spawn',side_effect=harmless_spawn),
              patch.object(install.os,'access',side_effect=availability)):
            return self.prepare(package=fixture['package'],installation=fixture['installation'],parent_pid=parent.pid)

    def arm_fixture(self, prepared, parent):
        with patch.object(install,'_revalidate'):prepared.launch()
        parent.terminate();parent.wait(timeout=3)

    def test_debian_package_identity_version_and_architecture_checked_before_close(self):
        for change in ({'package_name':'another-app'},{'package_version':'0.1.99'},{'arch':'arm64'}):
            with tempfile.TemporaryDirectory() as temporary:
                tree=Path(temporary);(tree/'DEBIAN').mkdir()
                fields=dict(package_name='ratiolab',package_version='0.1.12',arch='amd64')|change
                (tree/'DEBIAN/control').write_text('Package: '+fields['package_name']+'\nVersion: '
                    +fields['package_version']+'\nArchitecture: '+fields['arch']
                    +'\nMaintainer: Test <test@example.invalid>\nDescription: harmless\n')
                archive=self.root/'identity.deb'
                subprocess.run(['/usr/bin/dpkg-deb','--build',str(tree),str(archive)],check=True,
                               stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
                with self.assertRaises(ValueError):install._debian_package_identity(archive,'0.1.12','x86_64')

    def test_debian_update_waits_for_parent_authorizes_only_fixed_apt_and_restarts_exact_target(self):
        fixture=self.debian_fixture();parent=self.parent()
        prepared=self.prepare_debian_fixture(fixture,parent)
        self.assertFalse(fixture['calls'].exists())
        with patch.object(install,'_revalidate'):prepared.launch()
        time.sleep(.15)
        self.assertFalse(fixture['calls'].exists())
        parent.terminate();parent.wait(timeout=3)
        self.wait_result(prepared,'installed-restart-requested')
        deadline=time.monotonic()+3
        while not fixture['marker'].exists() and time.monotonic()<deadline:time.sleep(.02)
        self.assertEqual(fixture['marker'].read_text(),'0.1.12')
        self.assertEqual(fixture['calls'].read_text().splitlines(),['--disable-internal-agent',
            str(fixture['tools']['/usr/bin/apt-get']),'--yes','--no-remove','install',str(prepared.package)])
        outcome=update_receipt.consume(prepared.directory.parent,current='0.1.12',executable=self.executable)
        self.assertTrue(outcome.success)

    def test_debian_authentication_cancel_reopens_unchanged_source_and_retains_cancel_result(self):
        fixture=self.debian_fixture(authorization=126);parent=self.parent()
        prepared=self.prepare_debian_fixture(fixture,parent);self.arm_fixture(prepared,parent)
        self.wait_result(prepared,'cancelled')
        deadline=time.monotonic()+3
        while not fixture['marker'].exists() and time.monotonic()<deadline:time.sleep(.02)
        self.assertEqual(fixture['marker'].read_text(),'0.1.11')
        self.assertEqual(fixture['state'].read_text(),'0.1.11')
        outcome=update_receipt.consume(prepared.directory.parent,current='0.1.11',executable=self.executable)
        self.assertFalse(outcome.success);self.assertIn('cancelled',outcome.message)

    def test_debian_failed_authorization_is_distinct_from_installer_failure(self):
        fixture=self.debian_fixture(authorization=127);parent=self.parent()
        prepared=self.prepare_debian_fixture(fixture,parent);self.arm_fixture(prepared,parent)
        self.wait_result(prepared,'authorization-failed')
        outcome=update_receipt.consume(prepared.directory.parent,current='0.1.11',executable=self.executable)
        self.assertIn('authorization was not granted',outcome.message)

    def test_debian_partial_install_or_wrong_runtime_never_restarts_unverified_program(self):
        fixture=self.debian_fixture(apt_code=100);parent=self.parent()
        prepared=self.prepare_debian_fixture(fixture,parent);self.arm_fixture(prepared,parent)
        self.wait_result(prepared,'installer-failed')
        self.assertFalse(fixture['marker'].exists())

    def test_debian_success_exit_with_wrong_target_runtime_is_not_success(self):
        fixture=self.debian_fixture(runtime_version='0.1.99');parent=self.parent()
        prepared=self.prepare_debian_fixture(fixture,parent);self.arm_fixture(prepared,parent)
        self.wait_result(prepared,'runtime-invalid')
        self.assertFalse(fixture['marker'].exists())
        outcome=update_receipt.consume(prepared.directory.parent,current='0.1.99',executable=self.executable)
        self.assertFalse(outcome.success)

    def test_debian_identity_change_after_preparation_never_requests_authorization(self):
        fixture=self.debian_fixture();parent=self.parent()
        prepared=self.prepare_debian_fixture(fixture,parent)
        fixture['state'].write_text('0.1.99')
        self.arm_fixture(prepared,parent);self.wait_result(prepared,'installation-changed')
        self.assertFalse(fixture['calls'].exists());self.assertFalse(fixture['marker'].exists())

    def test_windows_spawn_is_hidden_detached_and_never_shell(self):
        with (patch.object(install.sys, 'platform', 'win32'),
              patch.object(install.subprocess, 'CREATE_NO_WINDOW', 0x08000000, create=True),
              patch.object(install.subprocess, 'CREATE_NEW_PROCESS_GROUP', 0x200, create=True),
              patch.object(install.subprocess, 'Popen') as popen):
            install._spawn(['powershell.exe', '-EncodedCommand', 'literal'], environment={}, log=None)
        kwargs = popen.call_args.kwargs
        self.assertFalse(kwargs['shell'])
        self.assertEqual(kwargs['creationflags'], 0x08000200)
        self.assertNotIn('start_new_session', kwargs)

    def test_nonverified_and_wrong_package_rejected_before_helper(self):
        with self.assertRaises(ValueError):
            self.prepare(package=object())
        for package in (self.package(suffix='.tar.gz'), self.package(system='windows', suffix='setup.exe'),
                        self.package(version='0.1.11'), self.package(version='0.1.10'),
                        self.package(arch='arm64')):
            with self.assertRaises(ValueError):
                self.prepare(package=package)
        self.assertFalse((self.root/'helpers').exists())

    def test_changed_download_or_unowned_download_rejected(self):
        package = self.package()
        package.path.write_bytes(b'changed')
        with self.assertRaises(ValueError):
            self.prepare(package=package)
        package = self.package()
        with self.assertRaises(ValueError):
            self.prepare(package=replace(package, _identity=(0, 0)))

    def test_prepared_helper_no_execution_until_arm_and_original_parent_exit(self):
        parent = self.parent()
        marker = self.root/'installer-ran'
        package = self.package(f'#!/bin/sh\nprintf ran > {shlex.quote(str(marker))}\n'.encode())
        prepared = self.prepare(package=package, parent_pid=parent.pid, restart=False)
        self.assertTrue((prepared.directory/'ready').is_file())
        self.assertFalse(marker.exists())
        prepared.launch()
        time.sleep(0.2)
        self.assertFalse(marker.exists())
        parent.terminate()
        parent.wait(timeout=3)
        self.wait_result(prepared, 'installed')
        self.assertEqual(marker.read_text(), 'ran')

    def test_parent_exit_without_arm_never_executes(self):
        parent = self.parent()
        marker = self.root/'installer-ran'
        prepared = self.prepare(package=self.package(f'echo ran > {shlex.quote(str(marker))}\n'.encode()),
                                parent_pid=parent.pid, timeout=0.4, restart=False)
        parent.terminate()
        parent.wait(timeout=3)
        self.wait_result(prepared, 'timeout')
        self.assertFalse(marker.exists())

    def test_cancel_before_arm_and_after_arm_preserve_application(self):
        for armed in (False, True):
            parent = self.parent()
            prepared = self.prepare(parent_pid=parent.pid)
            if armed:
                prepared.launch()
            prepared.cancel()
            self.wait_result(prepared, 'cancelled')
            self.assertIsNone(parent.poll())
            with self.assertRaises(ValueError):
                prepared.launch()

    def test_parent_timeout_does_not_install(self):
        parent = self.parent()
        marker = self.root/'installer-ran'
        prepared = self.prepare(package=self.package(f'echo ran > {shlex.quote(str(marker))}\n'.encode()),
                                parent_pid=parent.pid, timeout=0.4, restart=False)
        prepared.launch()
        self.wait_result(prepared, 'timeout')
        self.assertFalse(marker.exists())
        self.assertIsNone(parent.poll())

    def test_launch_rechecks_installation_identity_and_cache_stat(self):
        parent = self.parent()
        prepared = self.prepare(parent_pid=parent.pid)
        self.marker.write_text('wrong')
        with self.assertRaises(ValueError):
            prepared.launch()
        self.wait_result(prepared, 'cancelled')
        self.marker.write_text(install.MARKER)
        prepared = self.prepare(parent_pid=parent.pid)
        prepared.package.write_bytes(b'changed')
        with self.assertRaises(ValueError):
            prepared.launch()
        self.wait_result(prepared, 'cancelled')

    def test_helper_checks_hash_again_after_application_exit(self):
        parent = self.parent()
        marker = self.root/'installer-ran'
        prepared = self.prepare(package=self.package(f'echo ran > {shlex.quote(str(marker))}\n'.encode()),
                                parent_pid=parent.pid, restart=False)
        prepared.launch()
        prepared.package.write_bytes(b'echo changed\n')
        parent.terminate()
        parent.wait(timeout=3)
        self.wait_result(prepared, 'checksum-mismatch')
        self.assertFalse(marker.exists())

    def test_unrelated_sibling_cache_does_not_change_directory_identity(self):
        found = self.detection()
        (self.root/'new-cache').mkdir()
        (self.bundle/'unrelated-export.stl').write_text('unlisted data')
        parent = self.parent()
        prepared = self.prepare(installation=found, parent_pid=parent.pid, restart=False)
        (self.root/'second-cache').mkdir()
        prepared.launch()
        prepared.cancel()
        self.wait_result(prepared, 'cancelled')

    def test_replaced_parent_directory_is_rejected(self):
        found = self.detection()
        replacement = self.root/'replacement'
        replacement.mkdir()
        original = install._identity
        with patch.object(install, '_identity', wraps=install._identity) as identity:
            identity.side_effect = lambda path: original(replacement) if Path(path) == self.root else original(path)
            with self.assertRaises(ValueError):
                install._revalidate(found)

    def test_helper_rechecks_target_after_application_exit(self):
        parent = self.parent()
        prepared = self.prepare(parent_pid=parent.pid, restart=False)
        prepared.launch()
        self.marker.unlink()
        self.marker.write_text(install.MARKER)
        parent.terminate()
        parent.wait(timeout=3)
        self.wait_result(prepared, 'installation-changed')

    def test_expired_or_duplicate_handoff_cannot_arm(self):
        parent = self.parent()
        prepared = self.prepare(parent_pid=parent.pid, restart=False)
        prepared._deadline = time.monotonic()-1
        with self.assertRaises(ValueError):
            prepared.launch()
        self.wait_result(prepared, 'cancelled')
        prepared = self.prepare(parent_pid=parent.pid, restart=False)
        prepared.launch()
        with self.assertRaises(ValueError):
            prepared.launch()
        prepared.cancel()
        self.wait_result(prepared, 'cancelled')

    def test_public_status_ready_expired_running_and_cancelled_without_actions(self):
        parent = self.parent()
        prepared = self.prepare(parent_pid=parent.pid, restart=False)
        with (patch.object(prepared._process, 'wait', side_effect=AssertionError('must not wait')),
              patch.object(install, '_spawn', side_effect=AssertionError('must not spawn')),
              patch.object(install, '_sha256', side_effect=AssertionError('must not hash')),
              patch.object(prepared, 'cancel', side_effect=AssertionError('must not cancel'))):
            self.assertEqual(prepared.status(), 'ready')
            prepared._deadline = time.monotonic()-1
            self.assertEqual(prepared.status(), 'expired')
            self.assertEqual(prepared._state, 'prepared')
            self.assertFalse((prepared.directory/'cancel').exists())
            prepared._deadline = time.monotonic()+60
            prepared.launch()
            self.assertEqual(prepared.status(), 'running')
            # The deadline bounds the parent wait, not an interactive installer.
            prepared._deadline = time.monotonic()-1
            self.assertEqual(prepared.status(), 'running')
        prepared.cancel()
        self.assertEqual(prepared.status(), 'cancelled')
        self.wait_result(prepared, 'cancelled')
        self.assertEqual(prepared.status(), 'cancelled')

    def test_public_status_terminal_result_from_actual_harmless_helper(self):
        parent = self.parent()
        prepared = self.prepare(parent_pid=parent.pid, restart=False)
        prepared.launch()
        parent.terminate()
        parent.wait(timeout=3)
        self.wait_result(prepared, 'installed')
        self.assertEqual(prepared.status(), 'installed')

    def test_public_status_completed_result_is_bounded_regular_and_whitelisted(self):
        parent = self.parent()
        prepared = self.prepare(parent_pid=parent.pid, restart=False)
        prepared.cancel()
        self.wait_result(prepared, 'cancelled')
        for value in (b'opened\n', b'installed-restart-requested\n', b'setup-completed\n',
                      b'checksum-mismatch\n', b'timeout\n', b'installer-failed\n'):
            prepared.result_path.write_bytes(value)
            self.assertEqual(prepared.status(), value.decode().strip())
        for value in (b'not-a-status\n', b'opened\n'+b' '*257, b'\xff', b''):
            prepared.result_path.write_bytes(value)
            self.assertEqual(prepared.status(), 'failed')
        prepared.result_path.unlink()
        self.assertEqual(prepared.status(), 'failed')
        another = self.root/'another-result'
        another.write_text('opened')
        prepared.result_path.symlink_to(another)
        self.assertEqual(prepared.status(), 'failed')
        prepared.result_path.unlink()
        if hasattr(os, 'mkfifo'):
            os.mkfifo(prepared.result_path)
            self.assertEqual(prepared.status(), 'failed')

    def test_missing_system_utility_fails_before_app_close(self):
        found = self.detection()
        with patch.object(install.os, 'access', return_value=False):
            # Detection itself rejects unwritable files; supply its previous
            # accepted snapshot, then isolate the system-utility preflight.
            with patch.object(install, '_revalidate'):
                with self.assertRaises(RuntimeError):
                    self.prepare(installation=found, restart=False)

    def test_helper_lives_outside_bundle_and_owns_package_copy(self):
        package = self.package()
        parent = self.parent()
        with self.assertRaises(ValueError):
            self.prepare(package=package, directory=self.bundle/'helper', parent_pid=parent.pid)
        self.assertFalse((self.bundle/'helper').exists())
        found = self.detection()
        prepared = self.prepare(package=package, installation=found, parent_pid=parent.pid)
        package.cleanup()
        self.assertTrue(prepared.package.is_file())
        self.assertEqual(prepared.directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual(prepared.package.stat().st_mode & 0o777, 0o600)

    def test_private_handoff_directory_preserves_caller_cache_permissions(self):
        cache=self.root/'shared-cache'
        cache.mkdir();cache.chmod(0o775)
        parent=self.parent()
        prepared=self.prepare(directory=cache,parent_pid=parent.pid)
        self.assertEqual(cache.stat().st_mode & 0o777,0o775)
        self.assertEqual(prepared.directory.parent,cache/update_receipt.HANDOFF_DIRECTORY)
        self.assertEqual(prepared.directory.parent.stat().st_mode & 0o777,0o700)
        self.assertIn('umask 077',(prepared.directory/'helper.sh').read_text())

    def test_lexical_parent_components_reject_before_any_directory_creation(self):
        parent = self.parent()
        cache = self.root/'outside'/'..'/self.bundle.name/'helper'
        with self.assertRaises(ValueError):
            self.prepare(directory=cache, parent_pid=parent.pid)
        self.assertFalse((self.root/'outside').exists())
        self.assertFalse((self.bundle/'helper').exists())

    def test_symlink_cache_ancestor_rejects_before_any_directory_creation(self):
        parent = self.parent()
        cache_link = self.root/'cache-link'
        cache_link.symlink_to(self.bundle, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.prepare(directory=cache_link/'nested'/'helper', parent_pid=parent.pid)
        self.assertFalse((self.bundle/'nested').exists())

    def test_system_child_uses_sanitized_environment_and_library_guard(self):
        parent = self.parent()
        original = install._spawn
        calls = []
        def spawn(argv, *, environment, log):
            calls.append((argv, environment))
            return original(argv, environment=environment, log=log)
        environment = dict(os.environ, RATIOLAB_HARMLESS_FIXTURE='1')
        with (patch.object(install, 'child_environment', return_value=environment) as child_env,
             patch.object(install, 'system_library_search', wraps=install.system_library_search) as guard,
             patch.object(install, '_spawn', side_effect=spawn)):
            prepared = self.prepare(parent_pid=parent.pid)
        child_env.assert_called_once_with()
        guard.assert_called_once_with()
        self.assertEqual(calls[0][0], ['/bin/sh', str(prepared.directory/'helper.sh')])
        self.assertEqual(calls[0][1]['RATIOLAB_HARMLESS_FIXTURE'], '1')

    def fixture_installer(self, *, fails=False):
        payload = self.root/'harmless installer payload'
        payload.mkdir()
        scripts = Path(__file__).resolve().parents[1]/'scripts'
        shutil.copyfile(scripts/'install-bundle-linux.sh', payload/'install.sh')
        shutil.copyfile(scripts/'uninstall-bundle-linux.sh', payload/'uninstall.sh')
        runtime = payload/'RatioLab'
        runtime.mkdir()
        marker = self.root/'new-runtime-started'
        code = ('#!/bin/sh\nif [ "${1:-}" = --self-test ]; then exit '+('7' if fails else '0')+'; fi\n'
                +f'printf started > {shlex.quote(str(marker))}\n')
        executable = runtime/'RatioLab'
        executable.write_text(code)
        executable.chmod(0o700)
        (runtime/'bundle-manifest.json').write_text('{}')
        (payload/'installed-files.txt').write_text('RatioLab\nbundle-manifest.json\n')
        (self.bundle/'installed-files.txt').write_text('RatioLab\nbundle-manifest.json\n')
        (self.bundle/'uninstall.sh').write_bytes((payload/'uninstall.sh').read_bytes())
        (self.bundle/'user export with spaces.stl').write_text('preserve me')
        package = self.package(f'#!/bin/sh\nexec /bin/sh {shlex.quote(str(payload/"install.sh"))} "$@"\n'.encode())
        return package, marker

    def test_actual_linux_installer_harmless_fixture_install_and_restart(self):
        package, marker = self.fixture_installer()
        parent = self.parent()
        prepared = self.prepare(package=package, parent_pid=parent.pid)
        (self.bundle/'project saved after preparation.json').write_text('preserve new project')
        prepared.launch()
        self.assertFalse(marker.exists())
        parent.terminate()
        parent.wait(timeout=3)
        self.wait_result(prepared, 'installed-restart-requested')
        deadline = time.monotonic()+3
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(marker.read_text(), 'started')
        self.assertEqual((self.bundle/'user export with spaces.stl').read_text(), 'preserve me')
        self.assertEqual((self.bundle/'project saved after preparation.json').read_text(), 'preserve new project')
        self.assertEqual(self.marker.read_text().strip(), install.MARKER)
        self.assertFalse(list(self.root.glob('.ratiolab-backup.*')))
        outcome = update_receipt.consume(prepared.directory.parent, current=package.release.version,
                                         executable=self.executable)
        self.assertTrue(outcome.success)
        self.assertEqual(outcome.log_path, prepared.log_path)
        self.assertIsNone(update_receipt.consume(prepared.directory.parent, current=package.release.version,
                                                executable=self.executable))

    def test_actual_linux_installer_failed_selftest_preserves_old_runtime(self):
        old = self.executable.read_bytes()
        package, marker = self.fixture_installer(fails=True)
        parent = self.parent()
        prepared = self.prepare(package=package, parent_pid=parent.pid, restart=False)
        prepared.launch()
        parent.terminate()
        parent.wait(timeout=3)
        self.wait_result(prepared, 'installer-failed')
        self.assertEqual(self.executable.read_bytes(), old)
        self.assertFalse(marker.exists())
        self.assertEqual((self.bundle/'user export with spaces.stl').read_text(), 'preserve me')
        self.assertIn('previous installation was preserved', prepared.log_path.read_text())
        outcome = update_receipt.consume(prepared.directory.parent, current='0.1.11', executable=self.executable)
        self.assertFalse(outcome.success)
        self.assertIn('installer could not complete', outcome.message)

    def test_linux_helper_publishes_terminal_result_before_restarted_app_reads_it(self):
        package, marker = self.fixture_installer()
        parent = self.parent()
        prepared = self.prepare(package=package, parent_pid=parent.pid)
        # The restarted fixture checks the receipt synchronously, before the
        # helper's EXIT trap could run. This catches the old spawn-before-result race.
        payload = self.root/'harmless installer payload/RatioLab/RatioLab'
        slot = prepared.directory.parent/update_receipt.receipt_name(self.executable)
        payload.write_text('#!/bin/sh\nif [ "${1:-}" = --self-test ]; then exit 0; fi\n'
            +f'test -f {shlex.quote(str(slot))} && grep -q installed-restart-requested '
            +f'{shlex.quote(str(prepared.result_path))} && printf ready > {shlex.quote(str(marker))}\n')
        prepared.launch()
        parent.terminate();parent.wait(timeout=3)
        self.wait_result(prepared, 'installed-restart-requested')
        deadline=time.monotonic()+3
        while not marker.exists() and time.monotonic()<deadline:time.sleep(.02)
        self.assertEqual(marker.read_text(), 'ready')

    def test_unarmed_cancelled_preparation_never_publishes_an_update_result(self):
        parent = self.parent()
        prepared = self.prepare(parent_pid=parent.pid)
        prepared.cancel()
        self.wait_result(prepared, 'cancelled')
        self.assertIsNone(update_receipt.consume(prepared.directory.parent,
                         current='0.1.11', executable=self.executable))


if __name__ == '__main__':
    unittest.main()
