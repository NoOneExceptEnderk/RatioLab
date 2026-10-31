# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Verified native package handoff, without GTK or document lifecycle ownership.

Call ``prepare_install`` on a worker. It stages a private external helper and
waits for readiness, but never arms an installer. Only call ``launch`` after the
UI's Save/Discard guard has accepted closing; then close every application
window. Exit-requiring helpers wait for the original process identity to end.
Call ``cancel`` if closing fails or is cancelled. Logs/results stay in the
private helper directory. Download jobs may be cleaned after preparation.

Linux replacement uses the existing marked-bundle installer and its bounded
transaction, not a new rollback service. Windows Setup remains interactive;
macOS and Debian delegate to the system and require further user action.
"""
from dataclasses import dataclass, field
import base64
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time

from external_programs import child_environment, system_library_search
from release_version import RELEASE_VERSION, Version
from update_download import VerifiedDownload

MARKER = 'ratiolab.bundle.v1'
UNINSTALL_KEY = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\local.solidcraft.reducers_is1'
MAX_MANIFEST = 16 * 1024 * 1024
_RESULT_STATUSES = frozenset({
    'failed', 'cancelled', 'timeout', 'package-changed', 'checksum-mismatch',
    'installation-changed', 'installer-failed', 'installed',
    'installed-restart-requested', 'opened', 'setup-completed',
})


def _arch(machine):
    return {'amd64': 'x86_64', 'aarch64': 'arm64'}.get(machine.lower(), machine.lower())


def _ordinary(path, directory=False):
    """Reject links/reparse points, including linked ancestor directories."""
    path = Path(path).absolute()
    for parent in (*reversed(path.parents), path):
        info = parent.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Installation paths must not contain symbolic links')
    info = path.lstat()
    if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        raise ValueError('Installation path has the wrong file type')
    return info


def _identity(path):
    info = Path(path).lstat()
    if stat.S_ISDIR(info.st_mode):
        return info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _bounded(path, limit=MAX_MANIFEST):
    _ordinary(path)
    with open(path, 'rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('Installation metadata is too large')
    return raw


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(64 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _registry_location():
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY, 0,
                        winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
        value, kind = winreg.QueryValueEx(key, 'InstallLocation')
    return value if kind == winreg.REG_SZ else ''


def _debian_owns(executable):
    """Read dpkg's installed record; do not infer management from /opt alone."""
    try:
        files = _bounded(Path('/var/lib/dpkg/info/ratiolab.list'), 1024 * 1024).decode()
        status = _bounded(Path('/var/lib/dpkg/status'), 64 * 1024 * 1024).decode()
        installed = any('Package: ratiolab' in block.splitlines()
                        and 'Status: install ok installed' in block.splitlines()
                        for block in status.split('\n\n'))
        return installed and str(executable) in files.splitlines()
    except (OSError, ValueError, UnicodeError):
        return False


@dataclass(frozen=True)
class Installation:
    kind: str
    label: str
    package_format: str | None
    destination: Path | None
    executable: Path
    can_install: bool
    requires_exit: bool
    explanation: str
    _target: dict = field(default_factory=dict, repr=False, compare=False)
    _identity: tuple = field(default=(), repr=False, compare=False)

    def selection_target(self):
        """Arguments for updates.select_release (avoid its legacy format guess)."""
        return {key: self._target[key] for key in ('system', 'machine', 'executable')} | {
            'package_format': self.package_format}


def detect_installation(*, system=None, machine=None, executable=None, frozen=None,
                        current=RELEASE_VERSION, registry_reader=None, debian_owner=None):
    """Detect a proven target; injectable host/registry probes support headless tests.

    No native replacement is allowed from source/wheel or an unmarked portable
    tree. Explicit target arguments describe the running process, not a proposed
    destination. Detection errors produce a manual-update explanation.
    """
    system = sys.platform if system is None else system
    machine = _arch(machine or platform.machine())
    executable = Path(sys.executable if executable is None else executable).absolute()
    frozen = bool(getattr(sys, 'frozen', False)) if frozen is None else bool(frozen)
    target = dict(system=system, machine=machine, executable=executable,
                  frozen=frozen, current=current, registry_reader=registry_reader,
                  debian_owner=debian_owner)

    def result(kind, label, suffix, destination, install, exit_required, explanation, paths=()):
        identities = tuple((str(path), _identity(path)) for path in paths)
        return Installation(kind, label, suffix, destination, executable, install,
                            exit_required, explanation, target, identities)

    manual_format = '.tar.gz' if frozen and system.startswith('linux') else None
    try:
        Version(current)
        if not frozen:
            return result('manual', 'Source or Python installation', None, None, False, False,
                          'Update this source checkout or Python environment using its existing installation method.')
        if machine not in ('x86_64', 'arm64') or (system != 'darwin' and machine != 'x86_64'):
            raise ValueError('No supported native package for this architecture')
        executable_info = _ordinary(executable)
        if system == 'darwin':
            if executable.parts[-3:] != ('Contents', 'MacOS', 'RatioLab'):
                raise ValueError('The running executable is not a RatioLab.app bundle')
            bundle = executable.parents[2]
            if bundle.name != 'RatioLab.app':
                raise ValueError('The application bundle name is not RatioLab.app')
            info_path = bundle/'Contents/Info.plist'
            info = plistlib.loads(_bounded(info_path, 1024 * 1024))
            if (info.get('CFBundleIdentifier') != 'local.solidcraft.reducers'
                    or Version(info.get('CFBundleShortVersionString')) != Version(current)):
                raise ValueError('The application identity does not match the running release')
            return result('macos-dmg', 'macOS application', '.dmg', bundle, True, False,
                          'Open the verified disk image, then quit RatioLab and drag RatioLab.app to Applications to replace it.',
                          (bundle, executable, info_path))
        destination = executable.parent
        expected = 'RatioLab.exe' if system == 'win32' else 'RatioLab'
        if executable.name != expected:
            raise ValueError('The running executable is not the native RatioLab program')
        manifest_path = destination/'bundle-manifest.json'
        manifest = json.loads(_bounded(manifest_path))
        system_name = 'windows' if system == 'win32' else 'linux' if system.startswith('linux') else ''
        if (manifest.get('format') != 'ratiolab-bundle/1'
                or manifest.get('application_id') != 'local.solidcraft.reducers'
                or manifest.get('system') != system_name or manifest.get('arch') != machine
                or Version(manifest.get('version')).core != Version(current).core
                or manifest.get('executable') != expected
                or manifest.get('release', {}).get('release') != current):
            raise ValueError('The native bundle manifest does not match this running release and target')
        records = [item for item in manifest.get('files', []) if isinstance(item, dict)
                   and item.get('path') == expected]
        if (len(records) != 1 or records[0].get('kind') != 'file'
                or records[0].get('size') != executable_info.st_size):
            raise ValueError('The bundle inventory does not identify the running executable')
        paths = (destination, executable, manifest_path)
        if system == 'win32':
            location = (registry_reader or _registry_location)()
            if not isinstance(location, str) or os.path.normcase(os.path.normpath(location)) != os.path.normcase(str(destination)):
                raise ValueError('No matching per-user Inno Setup installation record')
            return result('windows-setup', 'Windows per-user installation', 'setup.exe', destination,
                          True, True, 'Close RatioLab, then run the verified interactive Setup in this installation folder. Setup controls installation and restart.', paths)
        if system.startswith('linux'):
            if executable == Path('/opt/ratiolab/RatioLab') and (debian_owner or _debian_owns)(executable):
                return result('debian', 'Debian/Ubuntu package', '.deb', destination, True, False,
                              'Open the verified package in the system installer. The system installer handles privileges and completion.', paths)
            marker = destination/'.ratiolab-installation'
            if _bounded(marker, 128) not in (MARKER.encode(), (MARKER+'\n').encode()):
                raise ValueError('The folder is not marked as an installed RatioLab bundle')
            for path in (*paths, marker, destination.parent):
                info = _ordinary(path, path in (destination, destination.parent))
                if info.st_uid != os.getuid() or info.st_mode & 0o022 or not os.access(path, os.W_OK):
                    raise ValueError('The installation and its parent must be owned and writable only by this user')
            return result('linux-bundle', 'Linux per-user bundle', '.run', destination, True, True,
                          'Close RatioLab, install in this folder, and restart. The installer preserves files outside its runtime inventory; rollback ends when installation succeeds.', (*paths, marker, destination.parent))
        raise ValueError('No native update adapter is available on this platform')
    except (OSError, ValueError, TypeError, KeyError, AttributeError, UnicodeError, ImportError) as error:
        return result('manual', 'Manual installation', manual_format, None, False, False,
                      'Update manually: '+str(error))


def _revalidate(installation):
    if not isinstance(installation, Installation) or not installation.can_install or not installation._target:
        raise ValueError('This installation requires a manual update')
    actual = detect_installation(**installation._target)
    if (not actual.can_install or actual.kind != installation.kind
            or actual._identity != installation._identity or actual.destination != installation.destination):
        raise ValueError('The running installation changed; check for updates again')


def _release_matches(download, installation):
    if not isinstance(download, VerifiedDownload):
        raise ValueError('A verified update download is required')
    current = installation._target['current']
    if not Version(download.release.version) > Version(current):
        raise ValueError('The update must be newer than the running release')
    target = installation._target
    versions = {download.release.version, '.'.join(map(str, Version(download.release.version).core))}
    arch = target['machine']
    suffix = installation.package_format
    system = 'windows' if target['system'] == 'win32' else 'macos' if target['system'] == 'darwin' else 'linux'
    expected = {f'ratiolab_{version}_amd64.deb' if suffix == '.deb' else
                f'RatioLab-{version}-{system}-{arch}'+('-setup.exe' if suffix == 'setup.exe' else suffix)
                for version in versions}
    if download.release.asset_name not in expected:
        raise ValueError('The verified package format or target does not match this installation')


def _parent_identity(pid, system):
    if system == 'win32':
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.GetProcessTimes.argtypes = [ctypes.c_void_p] + [ctypes.POINTER(ctypes.c_ulonglong)] * 4
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            raise OSError('Cannot identify the running RatioLab process')
        try:
            values = [ctypes.c_ulonglong() for _ in range(4)]
            if not kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in values)):
                raise OSError('Cannot identify the running RatioLab process')
            return str(values[0].value)
        finally:
            kernel.CloseHandle(handle)
    if system.startswith('linux'):
        parts = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        if parts[0] == 'Z':
            raise ValueError('The parent process already exited')
        return parts[19]
    return ''  # macOS never gates a replacement on parent exit.


def _spawn(argv, *, environment, log):
    options = ({'creationflags': subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
               if sys.platform == 'win32' else {'start_new_session': True})
    with system_library_search():
        return subprocess.Popen(argv, env=environment, stdin=subprocess.DEVNULL,
                                stdout=log, stderr=subprocess.STDOUT,
                                shell=False, **options)


def _shell_script(job, installation, package, digest, parent_pid, parent_identity,
                  timeout, checker, opener, restart):
    # All substitutions are shell-quoted literals. Runtime metadata is data.
    q = shlex.quote
    values = dict(job=job, package=package, digest=digest, destination=installation.destination,
                  executable=installation.executable, pid=parent_pid, birth=parent_identity,
                  count=int(timeout * 10), checker=checker)
    lines = ['#!/bin/sh', 'set -eu']
    lines += [f'{key}={q(str(value))}' for key, value in values.items()]
    lines += ['cd "$job"', 'status=failed',
              'finish() { printf "%s\\n" "$status" > result; }', 'trap finish EXIT',
              'trap \'status=cancelled; exit 1\' HUP INT TERM',
              'parent_token() {', '  [ -r "/proc/$pid/stat" ] || return 0',
              '  IFS= read -r record < "/proc/$pid/stat" || return 0',
              '  rest=${record##*) }; set -- $rest',
              '  [ "$#" -ge 20 ] || return 0', '  [ "$1" != Z ] || return 0',
              '  shift 19; printf "%s" "$1"', '}',
              'printf ready > ready',
              'while :; do', '  if [ -e cancel ]; then status=cancelled; exit 1; fi']
    if installation.requires_exit:
        lines += ['  token=$(parent_token)',
                  '  if [ -e armed ] && [ "$token" != "$birth" ]; then break; fi']
    else:
        lines += ['  if [ -e armed ]; then break; fi']
    lines += ['  count=$((count-1))',
              '  if [ "$count" -le 0 ]; then status=timeout; exit 1; fi',
              '  sleep 0.1', 'done',
              '[ ! -e cancel ] || { status=cancelled; exit 1; }',
              '[ -f "$package" ] && [ ! -L "$package" ] || { status=package-changed; exit 1; }']
    if installation.kind == 'macos-dmg':
        lines += ['actual=$("$checker" -a 256 "$package")']
    else:
        lines += ['actual=$("$checker" -- "$package")']
    lines += ['actual=${actual%% *}',
              '[ "$actual" = "$digest" ] || { status=checksum-mismatch; exit 1; }']
    if installation.kind == 'linux-bundle':
        # Recheck the exact destination directory and marker after parent exit.
        # stat format and binaries are fixed system programs, never downloaded.
        for name, path in [('destination', installation.destination), ('executable', installation.executable),
                           ('marker', installation.destination/'.ratiolab-installation'),
                           ('manifest', installation.destination/'bundle-manifest.json')]:
            info = path.stat()
            if stat.S_ISDIR(info.st_mode):
                pattern = '%d:%i:%f:%u:%g'
                expected = f'{info.st_dev}:{info.st_ino}:{info.st_mode:x}:{info.st_uid}:{info.st_gid}'
            else:
                pattern = '%d:%i:%s:%Y'
                expected = f'{info.st_dev}:{info.st_ino}:{info.st_size}:{info.st_mtime_ns // 1000000000}'
            lines += [f'{name}_path={q(str(path))}',
                      f'{name}_id={q(expected)}',
                      f'[ ! -L "${name}_path" ] && [ "$(/usr/bin/stat -c {pattern} -- "${name}_path")" = "${name}_id" ] || {{ status=installation-changed; exit 1; }}']
        lines += [f'[ "$(cat "$marker_path")" = {q(MARKER)} ] || {{ status=installation-changed; exit 1; }}',
                  'status=installer-failed',
                  'if /bin/sh "$package" --destination "$destination" --no-desktop --yes; then',
                  '  status=installed', 'else']
        if restart:
            lines += ['  if [ -x "$executable" ]; then "$executable" </dev/null >> helper.log 2>&1 & fi']
        lines += ['  exit 1', 'fi']
        if restart:
            lines += ['"$executable" </dev/null >> helper.log 2>&1 &', 'status=installed-restart-requested']
    else:
        lines += [f'{q(str(opener))} "$package"', 'status=opened']
    return '\n'.join(lines)+'\n'


def _powershell_script(job, installation, package, digest, parent_pid, parent_identity, timeout):
    def q(value):
        return "'"+str(value).replace("'", "''")+"'"
    values = dict(job=job, package=package, expected=digest, destination=installation.destination,
                  parentId=parent_pid, birth=parent_identity)
    lines = ["$ErrorActionPreference = 'Stop'"]
    lines += [f'${key} = {q(value)}' for key, value in values.items()]
    lines += ["$status = 'failed'", 'try {',
              f'  $deadline = [DateTime]::UtcNow.AddSeconds({int(timeout)})',
              "  Set-Content -LiteralPath (Join-Path $job 'ready') -Value 'ready'",
              '  while ($true) {',
              "    if (Test-Path -LiteralPath (Join-Path $job 'cancel')) { $status = 'cancelled'; throw 'Cancelled' }",
              '    $parent = Get-Process -Id $parentId -ErrorAction SilentlyContinue',
              '    $alive = $parent -and ($parent.StartTime.ToFileTimeUtc().ToString() -eq $birth)',
              "    if ((Test-Path -LiteralPath (Join-Path $job 'armed')) -and -not $alive) { break }",
              "    if ([DateTime]::UtcNow -ge $deadline) { $status = 'timeout'; throw 'RatioLab did not exit in time' }",
              '    Start-Sleep -Milliseconds 100', '  }',
              "  if (Test-Path -LiteralPath (Join-Path $job 'cancel')) { $status = 'cancelled'; throw 'Cancelled' }",
              "  $item = Get-Item -LiteralPath $package",
              "  if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Unsafe package' }",
              "  if ((Get-FileHash -LiteralPath $package -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { $status = 'checksum-mismatch'; throw 'Package changed' }",
              # Inno parses one quoted /DIR argument. Windows filenames cannot
              # contain double quotes; the destination has already been validated.
              '  $arguments = \'/DIR="\' + $destination + \'"\'',
              "  $status = 'installer-failed'",
              '  $process = Start-Process -FilePath $package -ArgumentList $arguments -PassThru -Wait',
              "  if ($process.ExitCode -ne 0) { throw ('Setup exited with code ' + $process.ExitCode) }",
              "  $status = 'setup-completed'", '} catch {',
              "  $_ | Out-String | Add-Content -LiteralPath (Join-Path $job 'helper.log')",
              '} finally {',
              "  Set-Content -LiteralPath (Join-Path $job 'result') -Value $status", '}']
    checks = [
        "  $key = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::CurrentUser, [Microsoft.Win32.RegistryView]::Registry64).OpenSubKey("+q(UNINSTALL_KEY)+')',
        "  if (-not $key -or $key.GetValue('InstallLocation').TrimEnd('\\') -ne $destination.TrimEnd('\\')) { throw 'Installation record changed' }",
        '  $key.Close()',
        '  $folder = Get-Item -LiteralPath $destination',
        "  if (-not $folder.PSIsContainer -or ($folder.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Installation directory changed' }",
    ]
    for path in (installation.executable, installation.destination/'bundle-manifest.json'):
        expected = _sha256(path)
        checks += [f'  $target = Get-Item -LiteralPath {q(path)}',
                   "  if ($target.PSIsContainer -or ($target.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Installation file changed' }",
                   f"  if ((Get-FileHash -LiteralPath {q(path)} -Algorithm SHA256).Hash.ToLowerInvariant() -ne {q(expected)}) {{ throw 'Installation identity changed' }}"]
    index = lines.index('  $arguments = \'/DIR="\' + $destination + \'"\'')
    lines[index:index] = checks
    return '\n'.join(lines)


@dataclass
class PreparedInstall:
    installation: Installation
    directory: Path
    package: Path
    action_label: str
    command: str
    log_path: Path
    result_path: Path
    _process: object = field(repr=False)
    _package_identity: tuple = field(repr=False)
    _deadline: float = field(repr=False)
    _state: str = field(default='prepared', repr=False)

    def status(self):
        """Return a read-only, nonblocking handoff status; never advance it.

        ``ready`` means the disarmed helper is alive; ``expired`` means its
        preparation deadline passed. ``running`` covers an armed helper both
        waiting for parent exit and executing its installer/opener. ``cancelled``
        means cancellation was requested or completed. After helper exit, return
        its exact whitelisted terminal result (including ``timeout``, ``opened``,
        ``installed``, ``installed-restart-requested`` or ``setup-completed``).
        Missing, oversized, unsafe or unknown completed results return ``failed``.
        Installer/opener completion does not establish a ready restarted GUI.
        """
        try:
            if self._process.poll() is None:
                if self._state == 'cancelled':
                    return 'cancelled'
                if self._state == 'prepared':
                    return 'expired' if time.monotonic() >= self._deadline else 'ready'
                return 'running' if self._state == 'armed' else 'failed'
            if not stat.S_ISREG(self.result_path.lstat().st_mode):
                return 'failed'
            flags = (os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
                     | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_BINARY', 0))
            with os.fdopen(os.open(self.result_path, flags), 'rb') as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    return 'failed'
                raw = stream.read(257)
            if len(raw) > 256:
                return 'failed'
            value = raw.decode('ascii').strip()
            return value if value in _RESULT_STATUSES else 'failed'
        except (OSError, ValueError, UnicodeError):
            return 'failed'

    def launch(self):
        """Fast arm only. The caller must first accept Save/Discard, then close.

        No hashing or installer spawn happens on this thread. A cancellation or
        close failure must disarm this object with ``cancel`` while still alive.
        """
        if self._state != 'prepared':
            raise ValueError('This installation handoff is no longer prepared')
        try:
            if time.monotonic() >= self._deadline or self._process.poll() is not None:
                raise ValueError('The prepared update helper expired or stopped')
            _revalidate(self.installation)
            if _identity(self.package) != self._package_identity:
                raise ValueError('The staged update package changed')
            descriptor = os.open(self.directory/'armed', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(descriptor)
            self._state = 'armed'
        except BaseException:
            self.cancel()
            raise

    def cancel(self):
        """Disarm while the app is alive; retain the log/result for diagnosis."""
        if self._state == 'cancelled':
            return
        (self.directory/'cancel').touch(mode=0o600, exist_ok=True)
        self._state = 'cancelled'


def prepare_install(download, installation, *, directory=None, parent_pid=None,
                    timeout=120, ready_timeout=5, restart=True):
    """Worker-only: reverify, stage and start a disarmed ready helper.

    ``directory`` is a writable cache parent outside the installation. The
    returned private job owns a separate package copy and is retained for logs;
    never remove it while a helper is pending/running. ``timeout`` bounds the
    whole arm/parent-exit wait. Injected parent PIDs support isolated fixtures.
    """
    if not 0.1 <= timeout <= 600 or not 0.1 <= ready_timeout <= 30:
        raise ValueError('Invalid update helper deadline')
    _revalidate(installation)
    _release_matches(download, installation)
    download.reverify()
    environment = child_environment()
    system = installation._target['system']
    parent_pid = os.getpid() if parent_pid is None else parent_pid
    if type(parent_pid) is not int or parent_pid <= 0:
        raise ValueError('Invalid parent process')
    birth = _parent_identity(parent_pid, system) if installation.requires_exit else ''
    parent = Path(directory if directory is not None else download.path.parent.parent).absolute()
    if '..' in parent.parts:
        raise ValueError('The update cache parent must not contain parent-directory components')
    if parent.is_relative_to(installation.destination):
        raise ValueError('The update helper must live outside the installation')
    ancestor = parent
    while not ancestor.exists() and not ancestor.is_symlink():
        ancestor = ancestor.parent
    _ordinary(ancestor, True)
    parent.mkdir(parents=True, exist_ok=True)
    _ordinary(parent, True)
    job = Path(tempfile.mkdtemp(prefix='ratiolab-install-', dir=parent))
    os.chmod(job, 0o700)
    process = None
    try:
        package = job/download.path.name
        with open(download.path, 'rb') as source, open(package, 'xb') as target:
            os.chmod(package, 0o600)
            shutil.copyfileobj(source, target, 64 * 1024)
            target.flush()
            os.fsync(target.fileno())
        if _sha256(package) != download.sha256:
            raise ValueError('The update changed while staging')
        log_path, result_path = job/'helper.log', job/'result'
        if installation.kind == 'windows-setup':
            powershell = shutil.which('powershell.exe', path=environment.get('PATH', os.defpath))
            if not powershell:
                raise RuntimeError('Windows PowerShell is needed to start the installer after RatioLab exits')
            script = _powershell_script(job, installation, package, download.sha256, parent_pid, birth, timeout)
            encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
            argv = [powershell, '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded]
            label = 'Close and run Setup'
        else:
            checker = '/usr/bin/shasum' if installation.kind == 'macos-dmg' else '/usr/bin/sha256sum'
            opener = '/usr/bin/open' if installation.kind == 'macos-dmg' else shutil.which('xdg-open', path=environment.get('PATH', os.defpath))
            for required in ('/bin/sh', checker, '/usr/bin/stat') if installation.kind == 'linux-bundle' else ('/bin/sh', checker, opener):
                if not required or not os.access(required, os.X_OK):
                    raise RuntimeError('The system package opener or checksum utility is unavailable')
            script = _shell_script(job, installation, package, download.sha256, parent_pid, birth, timeout, checker, opener, restart)
            helper = job/'helper.sh'
            helper.write_text(script, encoding='utf-8')
            os.chmod(helper, 0o600)
            argv = ['/bin/sh', str(helper)]
            label = 'Close, install and restart' if installation.requires_exit and restart else 'Close and install' if installation.requires_exit else 'Open disk image' if installation.kind == 'macos-dmg' else 'Open package installer'
        command = 'sudo apt install '+shlex.quote(str(package)) if installation.kind == 'debian' else ''
        wait_deadline = time.monotonic()+timeout
        with open(log_path, 'xb') as log:
            os.chmod(log_path, 0o600)
            process = _spawn(argv, environment=environment, log=log)
        deadline = time.monotonic()+ready_timeout
        while not (job/'ready').is_file():
            if process.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError(f'The update helper could not become ready; see {log_path}')
            time.sleep(0.02)
        return PreparedInstall(installation, job, package, label, command, log_path,
                               result_path, process, _identity(package), wait_deadline)
    except BaseException:
        (job/'cancel').touch(mode=0o600, exist_ok=True)
        # Do not delete a running helper or its package. A failed pre-spawn
        # staging job has no diagnostic process and can be safely removed.
        if process is None:
            shutil.rmtree(job)
        raise
