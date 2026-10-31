#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""CI-only upgrade from a published native release to a newly built installer.

Uses a disposable profile, verifies the public baseline download, installs into
one controlled location, and exercises the production update helper against the
new CI package. The new package's locally calculated hash is test evidence, not
an assertion that a public release with those bytes exists. Project-close guards
and GUI restart behavior have separate display-backed tests; this check leaves
restart disabled so it can validate the resulting runtime without a GUI session.
"""
import argparse
import hashlib
import json
from itertools import islice
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from urllib.request import build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
import update_download
import update_install
import update_receipt
import updates
import app_paths
from release_version import RELEASE_VERSION, Version


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()



class MetadataOpener:
    """Confine the disposable CI token to one non-redirecting metadata request."""
    def __init__(self, token):
        self._token = token
        self._opener = build_opener(updates.NoRedirect())

    def open(self, request, **kwargs):
        if request.full_url != updates.API_URL or request.get_method() != 'GET':
            raise ValueError('CI authentication is restricted to release metadata')
        request.add_unredirected_header('Authorization', 'Bearer '+self._token)
        return self._opener.open(request, **kwargs)


def fetch_baseline_releases():
    # Remove the step-scoped token before any native app or helper can inherit it.
    # Downloads/checksums continue through the production anonymous verifier.
    token = os.environ.pop('RATIOLAB_CI_GITHUB_TOKEN', '')
    if not token:
        return updates.fetch_releases()
    return updates.fetch_releases(opener=MetadataOpener(token))



def diagnostic_file(path, *, result_text=False):
    """Read only a bounded ordinary result file; other evidence is referenced."""
    record = dict(path=str(path), present=False)
    try:
        info = path.lstat()
        record.update(present=True, bytes=info.st_size,
                      regular=stat.S_ISREG(info.st_mode))
        if result_text and record['regular']:
            flags = (os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
                     | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_BINARY', 0))
            with os.fdopen(os.open(path, flags), 'rb') as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    return record
                raw = stream.read(4097)
            record.update(text=raw[:4096].decode('utf-8', errors='replace'),
                          truncated=len(raw) > 4096)
    except FileNotFoundError:
        pass
    except OSError as error:
        record['read_error'] = type(error).__name__
    return record


def write_failure_report(work, prepared, parent, phase, error):
    """Data-only CI evidence: no exception arguments, command lines or environment."""
    handoffs = work/'cache/ratiolab/updates/install-handoffs'
    jobs = ([prepared.directory] if prepared is not None else
            list(islice(handoffs.glob('ratiolab-install-*'), 4)))
    report = dict(format='ratiolab-native-update-failure/1', phase=phase,
                  error_type=type(error).__name__,
                  parent_returncode=parent.poll() if parent is not None else None,
                  helper_returncode=prepared._process.poll() if prepared is not None else None,
                  helper_status=prepared.status() if prepared is not None else None,
                  work=str(work), jobs=[], runtime_reports={
                      label:diagnostic_file(work/(label+'-version.txt'))
                      for label in ('old', 'waiting', 'new')})
    for job in jobs:
        if job.is_symlink() or not job.is_dir():
            continue
        report['jobs'].append(dict(directory=str(job), files={
            name:diagnostic_file(job/name, result_text=name == 'result')
            for name in ('ready', 'armed', 'cancel', 'result', 'status',
                         'helper.log', 'setup.log', 'runtime-version.txt', 'runtime-check.json')}))
    (work/'update-failure.json').write_text(json.dumps(report, indent=2)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--new-installer', type=Path, required=True)
    parser.add_argument('--baseline', default='0.1.12')
    parser.add_argument('--work-dir', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('CI', '').lower() not in ('1', 'true'):
        parser.error('Run this check only with a disposable CI user profile')
    if not Version(RELEASE_VERSION) > Version(args.baseline):
        parser.error('The built version must be newer than the baseline')
    if not args.new_installer.is_file():
        parser.error('The new native installer is missing')
    args.new_installer = args.new_installer.resolve()
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=False, mode=0o700)
    os.environ.update(RATIOLAB_UPDATE_CHECK='0',
                      XDG_CONFIG_HOME=str(work/'config'),
                      XDG_DATA_HOME=str(work/'data'),
                      XDG_CACHE_HOME=str(work/'cache'))
    system = sys.platform
    machine = {'amd64':'x86_64', 'aarch64':'arm64'}.get(platform.machine().lower(), platform.machine().lower())
    suffix = 'setup.exe' if system == 'win32' else '.dmg' if system == 'darwin' else '.run'
    destination = work/'installed RatioLab Ω'
    applications_created = False
    mac_profile_created = False
    if system == 'win32':
        os.environ.update(APPDATA=str(work/'roaming'), LOCALAPPDATA=str(work/'local'))
        import winreg
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, update_install.UNINSTALL_KEY, 0,
                                 winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
        except FileNotFoundError:
            pass
        else:
            key.Close()
            raise RuntimeError('Preserve the existing RatioLab installation; use a fresh CI profile')
    elif system == 'darwin':
        if app_paths.config_dir().exists() or app_paths.config_dir().is_symlink():
            raise RuntimeError('Preserve the existing RatioLab profile; use a fresh CI user')
        applications = Path.home()/'Applications'
        destination = applications/'RatioLab.app'
        if destination.exists() or destination.is_symlink():
            raise RuntimeError('Preserve the existing RatioLab.app; use a fresh CI profile')
        applications_created = not applications.exists()
        applications.mkdir(mode=0o700, exist_ok=True)
    elif not system.startswith('linux'):
        parser.error('Unsupported native update platform')
    executable = (destination/'Contents/MacOS/RatioLab' if system == 'darwin' else
                  destination/('RatioLab.exe' if system == 'win32' else 'RatioLab'))

    def run(argv, name, timeout=180):
        with (work/name).open('wb') as stream:
            subprocess.run(list(map(str, argv)), stdin=subprocess.DEVNULL,
                           stdout=stream, stderr=subprocess.STDOUT,
                           check=True, timeout=timeout)

    def version(label):
        report = work/(label+'-version.txt')
        run([executable, '--version', '--report', report], label+'-version.log', 60)
        return report.read_text(encoding='utf-8').strip()

    old = None
    prepared = None
    parent = None
    completed = False
    phase = 'baseline-discovery'
    try:
        records = [record for record in fetch_baseline_releases()
                   if record.get('tag_name') == 'v'+args.baseline]
        release = updates.select_release(records, current='0.0.0', channel='stable',
                    system=system, machine=machine, executable=executable, package_format=suffix)
        if release is None or release.version != args.baseline:
            raise RuntimeError('The exact published native baseline is unavailable')
        phase = 'baseline-download-and-install'
        old = update_download.download_release(release, work/'downloads')
        if system == 'win32':
            run([old.path, '/VERYSILENT', '/SUPPRESSMSGBOXES', '/SP-', '/NORESTART',
                 '/DIR='+str(destination), '/LOG='+str(work/'old-setup.log')], 'old-install.log')
        elif system == 'darwin':
            mount = work/'old-image';mount.mkdir()
            mounted = False
            try:
                run(['/usr/bin/hdiutil', 'attach', '-readonly', '-nobrowse', '-mountpoint', mount, old.path], 'old-mount.log')
                mounted = True
                run(['/usr/bin/ditto', mount/'RatioLab.app', destination], 'old-copy.log')
            finally:
                if mounted:
                    run(['/usr/bin/hdiutil', 'detach', mount], 'old-detach.log')
        else:
            run(['/bin/sh', old.path, '--destination', destination, '--no-desktop', '--yes'], 'old-install.log')
            # Preserve the immutable baseline package while creating the same
            # protected marker its installer gets with a standard private umask.
            (destination/'.ratiolab-installation').chmod(0o600)
        phase = 'baseline-runtime-version'
        if version('old') != 'RatioLab '+args.baseline:
            raise RuntimeError('The baseline runtime identity does not match')
        personal = app_paths.default_output_dir()/'user-project.config.json'
        personal.parent.mkdir(parents=True, exist_ok=True)
        mac_profile_created = system == 'darwin'
        personal.write_text('Preserve this user-owned project.\n')
        preference = app_paths.config_dir()/app_paths.PREFERENCES_FILENAME
        preference.parent.mkdir(parents=True, exist_ok=True)
        preference.write_text('{"theme":"light"}\n')
        inside = destination/'user-project.config.json' if system.startswith('linux') else None
        if inside is not None:
            inside.write_text('Preserve an unlisted file inside the Linux application.\n')
        preserved = {path:sha256(path) for path in (personal, preference, inside) if path is not None}
        installation = update_install.detect_installation(system=system, machine=machine,
                        executable=executable, frozen=True, current=args.baseline)
        if not installation.can_install:
            raise RuntimeError(installation.explanation)
        directory = Path(tempfile.mkdtemp(prefix='verified-ci-', dir=work))
        directory.chmod(0o700)
        package = directory/args.new_installer.name
        shutil.copyfile(args.new_installer, package)
        package.chmod(0o600)
        url = updates.RELEASES_URL+'/download/v'+RELEASE_VERSION+'/'
        target_release = updates.Release(RELEASE_VERSION,
            updates.RELEASES_URL+'/tag/v'+RELEASE_VERSION, 'Private native CI acceptance',
            url+package.name, package.name, package.stat().st_size, url+'SHA256SUMS')
        info = directory.stat()
        verified = update_download.VerifiedDownload(package, sha256(package), target_release,
                                                    directory, (info.st_dev, info.st_ino))
        parent = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])
        phase = 'prepare-helper'
        prepared = update_install.prepare_install(verified, installation,
                    directory=work/'cache/ratiolab/updates', parent_pid=parent.pid,
                    restart=False, timeout=120)
        phase = 'arm-helper'
        prepared.launch()
        time.sleep(0.3)
        phase = 'original-process-wait-gate'
        if parent.poll() is not None or prepared.result_path.exists():
            raise RuntimeError('The installer did not wait for the original process')
        phase = 'waiting-runtime-version'
        if version('waiting') != 'RatioLab '+args.baseline:
            raise RuntimeError('The running baseline was replaced before the original process exited')
        parent.terminate();parent.wait(timeout=15)
        phase = 'helper-completion'
        prepared._process.wait(timeout=300)
        phase = 'helper-terminal-status'
        if prepared.status() != 'installed':
            raise RuntimeError('Native update failed: '+prepared.status()+'; '+str(prepared.log_path))
        phase = 'new-runtime-version'
        if version('new') != 'RatioLab '+RELEASE_VERSION:
            raise RuntimeError('The updated native runtime has the wrong version')
        phase = 'next-update-eligibility'
        updated = update_install.detect_installation(system=system, machine=machine,
                    executable=executable, frozen=True, current=RELEASE_VERSION)
        if not updated.can_install or updated.destination != destination:
            raise RuntimeError('The updated application is not eligible for its next native update')
        phase = 'user-data-preservation'
        for path, expected in preserved.items():
            if sha256(path) != expected:
                raise RuntimeError('User data changed during the update: '+str(path))
        phase = 'update-receipt'
        outcome = update_receipt.consume(prepared.directory.parent, current=RELEASE_VERSION,
                                         executable=executable, system=system)
        if outcome is None or not outcome.success:
            raise RuntimeError('The actual native success receipt was not accepted')
        if update_receipt.consume(prepared.directory.parent, current=RELEASE_VERSION,
                                   executable=executable, system=system) is not None:
            raise RuntimeError('The update result was not consumed exactly once')
        phase = 'updated-runtime-self-test'
        run([executable, '--self-test', '--report', work/'updated-runtime.json'], 'updated-runtime.log')
        completed = True
        result = dict(status='passed', baseline=args.baseline, target=RELEASE_VERSION,
            system=system, machine=machine, baseline_sha256=old.sha256,
            target_sha256=sha256(args.new_installer), same_installation=True,
            user_data_preserved=True, future_native_updates_eligible=True,
            terminal_result='installed', receipt_consumed_once=True,
            scope='Actual native installer upgrade; GUI restart and document guards tested separately')
        (work/'update-result.json').write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps(result))
    except Exception as error:
        try:
            write_failure_report(work, prepared, parent, phase, error)
        except OSError:
            print('Could not write native update failure evidence.', file=sys.stderr)
        raise
    finally:
        if parent and parent.poll() is None:
            parent.terminate();parent.wait(timeout=15)
        helper_stopped = prepared is None or prepared._process.poll() is not None
        if helper_stopped:
            if system == 'win32' and (destination/'unins000.exe').is_file():
                run([destination/'unins000.exe', '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'], 'cleanup.log')
            elif system == 'darwin' and destination.is_dir():
                shutil.rmtree(destination)
                if applications_created:
                    destination.parent.rmdir()
            if mac_profile_created:
                shutil.rmtree(app_paths.config_dir())
            if old:
                old.cleanup()
        if not completed:
            print('Native update did not complete. Evidence retained in '+str(work), file=sys.stderr)


if __name__ == '__main__':
    main()
