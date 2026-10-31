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
transaction. Windows uses Setup's silent progress mode; Debian uses PolicyKit
to authorize its package manager. macOS replaces writable Applications bundles
from a verified, read-only mounted image, retaining the old copy until checked.
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
import update_receipt
import update_macos

MARKER = 'ratiolab.bundle.v1'
UNINSTALL_KEY = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\local.solidcraft.reducers_is1'
MAX_MANIFEST = 16 * 1024 * 1024
DEBIAN_TOOLS = ('/usr/bin/pkexec', '/usr/bin/apt-get', '/usr/bin/dpkg-deb', '/usr/bin/dpkg-query')
_RESULT_STATUSES = frozenset({
    'failed', 'cancelled', 'timeout', 'package-changed', 'checksum-mismatch',
    'installation-changed', 'installer-failed', 'installed',
    'installed-restart-requested', 'opened', 'setup-completed',
    'authorization-failed', 'package-identity-mismatch', 'runtime-invalid', 'reboot-required',
    'mount-failed', 'signature-invalid', 'rollback-failed',
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


def update_action(installation):
    """User-facing action and its actual completion steps for this package."""
    return {
        '.run': ('Update now', 'Save your work if prompted. RatioLab will install the update in the same folder and reopen automatically.'),
        'setup.exe': ('Update now', 'Save your work if prompted. RatioLab will install the update with a progress window and reopen automatically.'),
        '.dmg': ('Update now', 'Save your work if prompted. RatioLab will verify and replace this application, then reopen automatically.'),
        '.deb': ('Update now', 'Save your work if prompted and approve the system authorization. RatioLab will install the package and reopen automatically.'),
    }.get(installation.package_format, ('Download update', 'Use the original installation method to finish this update.'))


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
                    or info.get('CFBundleExecutable') != 'RatioLab'
                    or info.get('CFBundleShortVersionString') != current):
                raise ValueError('The application identity does not match the running release')
            parent=bundle.parent
            _ordinary(parent,True)
            standard=parent in (Path('/Applications'),Path.home()/'Applications')
            writable=os.access(parent,os.W_OK) and not bool(os.statvfs(parent).f_flag & os.ST_RDONLY)
            eligible=standard and writable
            explanation=('Update this application in the same folder and reopen automatically.' if eligible else
                'Automatic replacement supports writable /Applications or ~/Applications installations. '
                'This location is protected, read-only or not an established Applications installation. '
                'Use Download manually and the normal macOS installation workflow.')
            return result('macos-dmg','macOS application','.dmg',bundle,eligible,eligible,explanation,
                          (bundle,executable,info_path,parent))
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
                          True, True, 'Update in this installation folder and reopen automatically. Setup shows installation progress without a wizard.', paths)
        if system.startswith('linux'):
            if executable == Path('/opt/ratiolab/RatioLab') and (debian_owner or _debian_owns)(executable):
                available = all(os.access(tool, os.X_OK) for tool in DEBIAN_TOOLS)
                return result('debian', 'Debian/Ubuntu package', '.deb', destination, available, available,
                              'Authorize the system package update, then RatioLab reopens automatically.' if available else
                              'Automatic package updating needs PolicyKit (pkexec), apt-get and dpkg tools. Use Download manually and open the package with your system installer.', paths)
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
    if system=='darwin':
        return update_macos.process_identity(pid)
    raise ValueError('No process identity adapter for this platform')


def _spawn(argv, *, environment, log):
    options = ({'creationflags': subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
               if sys.platform == 'win32' else {'start_new_session': True})
    with system_library_search():
        return subprocess.Popen(argv, env=environment, stdin=subprocess.DEVNULL,
                                stdout=log, stderr=subprocess.STDOUT,
                                shell=False, **options)


def _debian_package_identity(package, version, machine):
    """Check the verified archive's identity before any close or authorization."""
    expected = 'ratiolab\n'+version+'\n'+('amd64' if machine == 'x86_64' else 'arm64')+'\n'
    with system_library_search():
        result = subprocess.run(['/usr/bin/dpkg-deb', '--show',
            '--showformat=${Package}\n${Version}\n${Architecture}\n', str(package)],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=child_environment(), timeout=30, check=True, encoding='utf-8')
    if result.stdout != expected:
        raise ValueError('The Debian package identity, version or architecture does not match this update')


def _debian_install_lines(installation, target, restart):
    q = shlex.quote
    source = installation._target['current']
    arch = 'amd64' if installation._target['machine'] == 'x86_64' else 'arm64'
    package_format = '${Package}\n${Version}\n${Architecture}'
    installed_format = '${Status}\n${Version}\n${Architecture}'
    lines = [f'target={q(target)}', f'source={q(source)}',
        f'old_executable_hash={q(_sha256(installation.executable))}',
        f'old_manifest_hash={q(_sha256(installation.destination/"bundle-manifest.json"))}',
        f'expected_package={q("ratiolab"+chr(10)+target+chr(10)+arch)}',
        f'expected_source={q("install ok installed"+chr(10)+source+chr(10)+arch)}',
        f'expected_target={q("install ok installed"+chr(10)+target+chr(10)+arch)}',
        f'actual=$(/usr/bin/dpkg-deb --show --showformat={q(package_format)} "$package")',
        '[ "$actual" = "$expected_package" ] || { status=package-identity-mismatch; exit 1; }',
        f'actual=$(/usr/bin/dpkg-query --show --showformat={q(installed_format)} ratiolab)',
        '[ "$actual" = "$expected_source" ] || { status=installation-changed; exit 1; }',
        'status=installer-failed', 'code=0',
        '/usr/bin/pkexec --disable-internal-agent /usr/bin/apt-get --yes --no-remove install "$package" || code=$?',
        'if [ "$code" -ne 0 ]; then',
        '  case "$code" in 126) status=cancelled ;; 127) status=authorization-failed ;; esac']
    if restart:
        # pkexec 126/127 did not execute apt. Other apt failures may leave a
        # partially replaced runtime: do not claim the old application is safe.
        lines += ['  if [ "$code" = 126 ] || [ "$code" = 127 ]; then',
            '    actual=$(/usr/bin/sha256sum -- "$executable"); actual=${actual%% *}',
            '    manifest=$(/usr/bin/sha256sum -- "$manifest_path"); manifest=${manifest%% *}',
            '    if [ "$actual" = "$old_executable_hash" ] && [ "$manifest" = "$old_manifest_hash" ] &&',
            '       [ "$("$executable" --version)" = "RatioLab $source" ] && "$executable" --diagnose; then',
            '      finish; trap - EXIT',
            '      "$executable" </dev/null >> helper.log 2>&1 &',
            '    fi', '  fi']
    lines += ['  exit 1', 'fi', 'status=runtime-invalid',
        f'actual=$(/usr/bin/dpkg-query --show --showformat={q(installed_format)} ratiolab)',
        '[ "$actual" = "$expected_target" ] || exit 1',
        '[ ! -L "$executable" ] && [ ! -L "$manifest_path" ] || exit 1',
        '[ "$("$executable" --version)" = "RatioLab $target" ] || exit 1',
        '"$executable" --diagnose || exit 1', 'status=installed']
    if restart:
        lines += ['status=installed-restart-requested', 'finish; trap - EXIT',
                  '"$executable" </dev/null >> helper.log 2>&1 &']
    return lines


def _shell_script(job, installation, package, digest, parent_pid, parent_identity,
                  timeout, checker, opener, restart, target=None):
    # All substitutions are shell-quoted literals. Runtime metadata is data.
    q = shlex.quote
    values = dict(job=job, package=package, digest=digest, destination=installation.destination,
                  executable=installation.executable, pid=parent_pid, birth=parent_identity,
                  count=int(timeout * 10), checker=checker)
    lines = ['#!/bin/sh', 'set -eu', 'umask 077']
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
    if installation.kind in ('linux-bundle', 'debian'):
        slot = q(str(Path(job).parent/update_receipt.receipt_name(installation.executable)))
        lines[lines.index('finish() { printf "%s\\n" "$status" > result; }')] = (
            'finish() { printf "%s\\n" "$status" > result; '
            f'if [ -e armed ] && [ -f receipt.pending ]; then /bin/mv -f -- receipt.pending {slot}; fi; }}')
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
    lines += ['actual=$("$checker" -- "$package")']
    lines += ['actual=${actual%% *}',
              '[ "$actual" = "$digest" ] || { status=checksum-mismatch; exit 1; }']
    if installation.kind in ('linux-bundle', 'debian'):
        # Recheck the exact destination directory and marker after parent exit.
        # stat format and binaries are fixed system programs, never downloaded.
        paths = [('destination', installation.destination), ('executable', installation.executable),
                 ('manifest', installation.destination/'bundle-manifest.json')]
        if installation.kind == 'linux-bundle':
            paths.append(('marker', installation.destination/'.ratiolab-installation'))
        for name, path in paths:
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
    if installation.kind == 'debian':
        lines += _debian_install_lines(installation, target, restart)
    elif installation.kind == 'linux-bundle':
        lines += [f'[ "$(cat "$marker_path")" = {q(MARKER)} ] || {{ status=installation-changed; exit 1; }}',
                  'status=installer-failed',
                  'if /bin/sh "$package" --destination "$destination" --no-desktop --yes; then',
                  '  status=installed', 'else']
        if restart:
            lines += ['  finish; trap - EXIT',
                      '  if [ -x "$executable" ]; then "$executable" </dev/null >> helper.log 2>&1 & fi']
        lines += ['  exit 1', 'fi']
        if restart:
            lines += ['status=installed-restart-requested', 'finish; trap - EXIT',
                      '"$executable" </dev/null >> helper.log 2>&1 &']
    else:
        lines += [f'{q(str(opener))} "$package"', 'status=opened']
    return '\n'.join(lines)+'\n'


def _powershell_script(job, installation, package, digest, parent_pid, parent_identity, timeout,
                       target=None, restart=True):
    def q(value):
        return "'"+str(value).replace("'", "''")+"'"
    source = installation._target['current']
    if target is None or not Version(target) > Version(source):
        raise ValueError('A newer Windows update target is required')
    values = dict(job=job, package=package, expected=digest, destination=installation.destination,
                  executable=installation.executable, parentId=parent_pid, birth=parent_identity,
                  sourceVersion=source, targetVersion=target,
                  sourceBase='.'.join(map(str, Version(source).core)),
                  targetBase='.'.join(map(str, Version(target).core)),
                  oldManifestHash=_sha256(installation.destination/'bundle-manifest.json'),
                  slot=Path(job).parent/update_receipt.receipt_name(installation.executable,system='win32'))
    lines = ["$ErrorActionPreference = 'Stop'"]
    lines += [f'${key} = {q(value)}' for key, value in values.items()]
    lines += [r'''
function Log-Message([string]$message) {
  # _spawn already owns helper.log as redirected stdout/stderr. Reopening it
  # with Add-Content can fail under Windows sharing rules, including in catch.
  # stderr also keeps diagnostics out of Runtime-Valid's boolean return stream.
  [Console]::Error.WriteLine($message)
}
function Log-Failure([object]$failure) {
  Log-Message ($failure | Out-String)
  if ($failure.Exception) { Log-Message ($failure.Exception.ToString()) }
  if ($failure.ScriptStackTrace) { Log-Message ([string]$failure.ScriptStackTrace) }
}
function Ordinary-Item([string]$path, [bool]$directory = $false) {
  $item = Get-Item -LiteralPath $path -Force
  if ([bool]$item.PSIsContainer -ne $directory) { throw 'Wrong installation file type' }
  $cursor = $item
  while ($cursor) {
    if (($cursor.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $cursor.LinkType -eq 'HardLink') { throw 'Linked installation path' }
    $parent = [IO.Directory]::GetParent($cursor.FullName)
    $cursor = if ($parent) { Get-Item -LiteralPath $parent.FullName -Force } else { $null }
  }
  return $item
}
function Probe([string]$option, [string]$report) {
  $arguments = $option + ' --report "' + $report + '"'
  $child = Start-Process -FilePath $executable -ArgumentList $arguments -PassThru -WindowStyle Hidden
  if (-not $child.WaitForExit(60000)) { $child.Kill(); throw 'Runtime check timed out' }
  if ($child.ExitCode -ne 0) { throw 'Runtime check failed' }
}
function Runtime-Valid([string]$version, [string]$baseVersion) {
  try {
    $separator = [string][IO.Path]::DirectorySeparatorChar
    $root = (Ordinary-Item $destination $true).FullName.TrimEnd([IO.Path]::DirectorySeparatorChar) + $separator
    $manifestPath = Join-Path $destination 'bundle-manifest.json'
    $manifestFile = Ordinary-Item $manifestPath
    if ($manifestFile.Length -gt 16777216) { throw 'Oversized runtime manifest' }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($manifest.format -ne 'ratiolab-bundle/1' -or $manifest.application_id -ne 'local.solidcraft.reducers' -or
        $manifest.system -ne 'windows' -or $manifest.arch -ne 'x86_64' -or $manifest.version -cne $baseVersion -or
        $manifest.release.release -cne $version -or $manifest.executable -ne 'RatioLab.exe') { throw 'Unexpected runtime identity' }
    $records = @($manifest.files)
    if ($records.Count -lt 1 -or $records.Count -gt 50000) { throw 'Invalid runtime inventory size' }
    $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    $deadline = [DateTime]::UtcNow.AddMinutes(3)
    foreach ($entry in $records) {
      if ([DateTime]::UtcNow -ge $deadline) { throw 'Runtime verification timed out' }
      if ($entry.kind -ne 'file' -or $entry.path -isnot [string] -or $entry.path.Length -gt 4096 -or
          $entry.path -match '(^/|[\\:\x00-\x1F]|(^|/)\.\.?(/|$)|//|[. ](/|$))' -or
          $entry.sha256 -notmatch '^[0-9a-fA-F]{64}$' -or [string]$entry.size -notmatch '^\d+$') { throw 'Unsafe runtime inventory entry' }
      $path = [IO.Path]::GetFullPath((Join-Path $destination $entry.path.Replace('/', $separator)))
      if (-not $path.StartsWith($root, [StringComparison]::OrdinalIgnoreCase) -or -not $seen.Add($path)) { throw 'Duplicate or external runtime path' }
      $file = Ordinary-Item $path
      if ($file.Length -ne [int64]$entry.size -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $entry.sha256) { throw 'Runtime inventory mismatch' }
    }
    if (-not $seen.Contains([IO.Path]::GetFullPath($executable))) { throw 'Missing runtime executable' }
    $report = Join-Path $job 'runtime-version.txt'
    Probe '--version' $report
    if ((Ordinary-Item $report).Length -gt 1024 -or (Get-Content -LiteralPath $report -Raw).Trim() -cne ('RatioLab ' + $version)) { throw 'Unexpected running runtime version' }
    Probe '--diagnose' (Join-Path $job 'runtime-check.json')
    return $true
  } catch {
    Log-Failure $_
    return $false
  }
}
function Finish {
  [IO.File]::WriteAllText((Join-Path $job 'result'), $status, [Text.Encoding]::ASCII)
  $pending = Join-Path $job 'receipt.pending'
  if ((Test-Path -LiteralPath (Join-Path $job 'armed')) -and (Test-Path -LiteralPath $pending)) {
    Move-Item -LiteralPath $pending -Destination $slot -Force
  }
}
''']
    lines += ["$status = 'failed'", "$phase = 'waiting for the original process'",
              '$restartPath = $null', '$mayRestart = $false', 'try {',
              f'  $deadline = [DateTime]::UtcNow.AddSeconds({int(timeout)})',
              "  Log-Message ('Update helper ready: ' + $phase)",
              "  Set-Content -LiteralPath (Join-Path $job 'ready') -Value 'ready'",
              '  while ($true) {',
              "    if (Test-Path -LiteralPath (Join-Path $job 'cancel')) { $status = 'cancelled'; throw 'Cancelled' }",
              '    $parent = Get-Process -Id $parentId -ErrorAction SilentlyContinue',
              '    $alive = $parent -and ($parent.StartTime.ToFileTimeUtc().ToString() -eq $birth)',
              "    if ((Test-Path -LiteralPath (Join-Path $job 'armed')) -and -not $alive) { break }",
              "    if ([DateTime]::UtcNow -ge $deadline) { $status = 'timeout'; throw 'RatioLab did not exit in time' }",
              '    Start-Sleep -Milliseconds 100', '  }',
              "  if (Test-Path -LiteralPath (Join-Path $job 'cancel')) { $status = 'cancelled'; throw 'Cancelled' }",
              "  $phase = 'verifying the update package'; Log-Message $phase",
              "  $item = Ordinary-Item $package",
              "  if ((Get-FileHash -LiteralPath $package -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { $status = 'checksum-mismatch'; throw 'Package changed' }",
              # Inno parses one quoted /DIR argument. Windows filenames cannot
              # contain double quotes; the destination has already been validated.
              '  $arguments = \'/SILENT /SUPPRESSMSGBOXES /SP- /NORESTART /RESTARTEXITCODE=3010 /NOCLOSEAPPLICATIONS /NORESTARTAPPLICATIONS /DIR="\' + $destination + \'" /LOG="\' + (Join-Path $job \'setup.log\') + \'"\'',
              '  $mayRestart = $true',
              "  $status = 'installer-failed'",
              "  $phase = 'running Setup'; Log-Message $phase",
              "  Log-Message ('Setup log: ' + (Join-Path $job 'setup.log'))",
              '  $process = Start-Process -FilePath $package -ArgumentList $arguments -PassThru -Wait',
              "  if ($process.ExitCode -eq 3010) { $status = 'reboot-required'; throw 'A system restart is required; no reboot was requested' }",
              "  if ($process.ExitCode -eq 2) { $status = 'cancelled'; throw 'Setup was cancelled' }",
              "  if ($process.ExitCode -ne 0) { throw ('Setup exited with code ' + $process.ExitCode) }",
              "  $status = 'runtime-invalid'",
              "  $phase = 'verifying the installed runtime'; Log-Message $phase",
              "  if (-not (Runtime-Valid $targetVersion $targetBase)) { throw 'The installed target runtime could not be verified' }",
              "  $status = 'installed'", '  $restartPath = $executable' if restart else '', '} catch {',
              "  Log-Message ('Update helper failed during ' + $phase + '; status=' + $status)",
              '  Log-Failure $_',
              '} finally {',
              # An unsuccessful Setup may have partly replaced its runtime.
              # Reopen the source only if its original manifest AND complete
              # inventory still match, and the source runtime passes checks.
              "  if (-not $restartPath -and $mayRestart -and $status -ne 'reboot-required') {" if restart else '  if ($false) {',
              "    try {",
              "      $old = Ordinary-Item (Join-Path $destination 'bundle-manifest.json')",
              "      if ((Get-FileHash -LiteralPath $old.FullName -Algorithm SHA256).Hash -eq $oldManifestHash -and (Runtime-Valid $sourceVersion $sourceBase)) { $restartPath = $executable }",
              '    } catch { Log-Failure $_ }',
              '  }',
              "  if ($status -eq 'installed' -and $restartPath) { $status = 'installed-restart-requested' }",
              "  Log-Message ('Update helper terminal result: ' + $status)",
              '  Finish',
              "  if ($restartPath) { Start-Process -FilePath $restartPath | Out-Null }", '}']
    checks = [
        "  $phase = 'verifying the current installation'; Log-Message $phase",
        "  $status = 'installation-changed'",
        "  $key = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::CurrentUser, [Microsoft.Win32.RegistryView]::Registry64).OpenSubKey("+q(UNINSTALL_KEY)+')',
        "  if (-not $key -or $key.GetValue('InstallLocation').TrimEnd('\\') -ne $destination.TrimEnd('\\')) { throw 'Installation record changed' }",
        '  $key.Close()',
        '  $folder = Ordinary-Item $destination $true',
    ]
    for path in (installation.executable, installation.destination/'bundle-manifest.json'):
        expected = _sha256(path)
        checks += [f'  $target = Ordinary-Item {q(path)}',
                   f"  if ((Get-FileHash -LiteralPath {q(path)} -Algorithm SHA256).Hash.ToLowerInvariant() -ne {q(expected)}) {{ throw 'Installation identity changed' }}"]
    index = next(index for index, line in enumerate(lines) if line.startswith('  $arguments = \'/SILENT'))
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
    _receipt: dict | None = field(default=None, repr=False)

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
            if self._receipt is not None:
                descriptor = os.open(self.directory/'receipt.pending', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                    json.dump(self._receipt, stream)
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
    if installation.kind == 'debian':
        if not all(os.access(tool, os.X_OK) for tool in DEBIAN_TOOLS):
            raise RuntimeError('Automatic package updating needs PolicyKit (pkexec), apt-get and dpkg tools. Use Download manually instead.')
        _debian_package_identity(download.path, download.release.version, installation._target['machine'])
    if installation.kind == 'macos-dmg':
        update_macos.validate_source(installation)
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
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _ordinary(parent, True)
    if installation.kind in ('linux-bundle','debian','windows-setup','macos-dmg'):
        # Restrict only this application's dedicated handoff directory, never a
        # caller's existing cache root. Older downloads may have created that
        # root with a permissive umask.
        parent = parent/update_receipt.HANDOFF_DIRECTORY
        parent.mkdir(exist_ok=True, mode=0o700)
        _ordinary(parent, True)
        if system != 'win32':
            descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                if os.fstat(descriptor).st_uid != os.getuid():
                    raise ValueError('The update cache must be owned by this user')
                os.fchmod(descriptor, 0o700)
            finally:
                os.close(descriptor)
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
            script = _powershell_script(job, installation, package, download.sha256, parent_pid, birth,
                                        timeout, target=download.release.version, restart=restart)
            encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
            argv = [powershell, '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded]
            label = 'Close, update and restart' if restart else 'Close and update'
        elif installation.kind=='macos-dmg':
            script=update_macos.script(job,installation,package,download.sha256,parent_pid,birth,
                                       timeout,download.release.version,restart)
            helper=job/'helper.sh';helper.write_text(script,encoding='utf-8');os.chmod(helper,0o600)
            argv=['/bin/sh',str(helper)]
            label='Close, update and restart' if restart else 'Close and update'
        else:
            checker = '/usr/bin/sha256sum'
            opener = shutil.which('xdg-open', path=environment.get('PATH', os.defpath))
            required_tools = (('/bin/sh', checker, '/usr/bin/stat', *DEBIAN_TOOLS) if installation.kind == 'debian' else
                              ('/bin/sh', checker, '/usr/bin/stat') if installation.kind == 'linux-bundle' else ('/bin/sh', checker, opener))
            for required in required_tools:
                if not required or not os.access(required, os.X_OK):
                    raise RuntimeError('The system package opener or checksum utility is unavailable')
            script = _shell_script(job, installation, package, download.sha256, parent_pid, birth,
                                  timeout, checker, opener, restart, target=download.release.version)
            helper = job/'helper.sh'
            helper.write_text(script, encoding='utf-8')
            os.chmod(helper, 0o600)
            argv = ['/bin/sh', str(helper)]
            label = 'Close, install and restart' if installation.requires_exit and restart else 'Close and install' if installation.requires_exit else 'Open package installer'
        command = ''
        wait_deadline = time.monotonic()+timeout
        with open(log_path, 'xb') as log:
            os.chmod(log_path, 0o600)
            process = _spawn(argv, environment=environment, log=log)
        deadline = time.monotonic()+ready_timeout
        while not (job/'ready').is_file():
            if process.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError(f'The update helper could not become ready; see {log_path}')
            time.sleep(0.02)
        receipt = (update_receipt.metadata(job, installation.executable,
                   installation._target['current'], download.release.version, system=system)
                   if installation.kind in ('linux-bundle','debian','windows-setup','macos-dmg') else None)
        return PreparedInstall(installation, job, package, label, command, log_path,
                               result_path, process, _identity(package), wait_deadline,
                               _receipt=receipt)
    except BaseException:
        (job/'cancel').touch(mode=0o600, exist_ok=True)
        # Do not delete a running helper or its package. A failed pre-spawn
        # staging job has no diagnostic process and can be safely removed.
        if process is None:
            shutil.rmtree(job)
        raise
