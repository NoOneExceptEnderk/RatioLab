# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""One-time native update outcomes, read from a bounded per-user helper job."""
from dataclasses import dataclass
import hashlib
import json
import ntpath
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

from release_version import Version

FORMAT = 'ratiolab-update-result/1'
MAX_RECEIPT = 4096
HANDOFF_DIRECTORY = 'install-handoffs'
_STATUSES = frozenset({'failed', 'cancelled', 'timeout', 'package-changed',
    'checksum-mismatch', 'installation-changed', 'installer-failed',
    'installed', 'installed-restart-requested', 'authorization-failed',
    'package-identity-mismatch', 'runtime-invalid', 'reboot-required',
    'mount-failed', 'signature-invalid', 'rollback-failed'})


@dataclass(frozen=True)
class Outcome:
    success: bool
    message: str
    log_path: Path | None = None


def _path_identity(path, system):
    value = str(Path(path).absolute())
    return ntpath.normcase(ntpath.normpath(value)) if system == 'win32' else value


def receipt_name(executable, *, system=None):
    identity = _path_identity(executable,system or sys.platform).encode('utf-8')
    return 'update-result-'+hashlib.sha256(identity).hexdigest()[:32]+'.json'


def metadata(job, executable, source, target, *, system=None):
    """Small data-only record staged by the app, published by the helper."""
    if not Version(target) > Version(source):
        raise ValueError('An update receipt must identify a newer target')
    return dict(format=FORMAT, job=Path(job).name,
                executable=_path_identity(executable,system or sys.platform), source=source, target=target)


def _linked(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info,'st_file_attributes',0) & 0x400)


def _directory(path, *, private=False, system):
    path = Path(path).absolute()
    for ancestor in (*reversed(path.parents), path):
        info = ancestor.lstat()
        if not stat.S_ISDIR(info.st_mode) or _linked(info):
            raise ValueError('Unsafe update result directory')
    info = path.lstat()
    # Windows cache paths inherit the signed-in user's profile ACL. POSIX uid
    # and mode bits do not represent those permissions; reject reparse paths
    # above instead of inventing a Windows ownership test from st_uid.
    if system != 'win32' and (info.st_uid != os.getuid() or info.st_mode & (0o077 if private else 0o022)):
        raise ValueError('Unsafe update result directory ownership')


def _regular(info, system):
    return (stat.S_ISREG(info.st_mode) and not _linked(info) and info.st_nlink == 1
            and (system == 'win32' or info.st_uid == os.getuid()))


def _read(path, limit, system):
    before = Path(path).lstat()
    if not _regular(before,system):
        raise ValueError('Unsafe update result file')
    descriptor = os.open(path, os.O_RDONLY | getattr(os,'O_NOFOLLOW',0)
                         | getattr(os,'O_NONBLOCK',0) | getattr(os,'O_BINARY',0))
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not _regular(info,system) or (info.st_dev,info.st_ino) != (before.st_dev,before.st_ino):
            raise ValueError('Unsafe update result file')
        data = stream.read(limit+1)
    if len(data) > limit:
        raise ValueError('Update result is too large')
    return data


def consume(directory, *, current, executable, system=None):
    """Atomically consume at most one outcome for this exact executable.

    The helper publishes only after writing its terminal result. No process,
    package, user-supplied path, markup or URI from the receipt is executed.
    Invalid receipts never become success and are consumed once as well.
    """
    directory = Path(directory).absolute()
    system = system or sys.platform
    if not directory.exists():
        return None
    slot = directory/receipt_name(executable,system=system)
    if not slot.exists() and not slot.is_symlink():
        return None
    claimed = None
    try:
        _directory(directory,system=system)
        descriptor, name = tempfile.mkstemp(prefix='.update-result-', dir=directory)
        os.close(descriptor)
        claimed = Path(name)
        try:
            os.replace(slot, claimed)
        except FileNotFoundError:
            return None
        record = json.loads(_read(claimed, MAX_RECEIPT, system))
        if (not isinstance(record, dict) or set(record) != {'format', 'job', 'executable', 'source', 'target'}
                or record['format'] != FORMAT
                or record['executable'] != _path_identity(executable,system)
                or not isinstance(record['job'], str)
                or not re.fullmatch(r'ratiolab-install-[A-Za-z0-9_-]{6,80}', record['job'])
                or not Version(record['target']) > Version(record['source'])):
            raise ValueError('Invalid update result identity')
        job = directory/record['job']
        _directory(job, private=True, system=system)
        status = _read(job/'result', 256, system).decode('ascii').strip()
        if status not in _STATUSES:
            raise ValueError('Invalid update result status')
        log_path = job/'helper.log'
        info = log_path.lstat()
        if not _regular(info,system):
            raise ValueError('Unsafe update log')
        target = record['target']
        if status in ('installed', 'installed-restart-requested'):
            if current == target:
                return Outcome(True, f'RatioLab was updated to {target}.', log_path)
            return Outcome(False, f'The update to {target} finished, but this app is still running '
                           f'version {current}. Close other copies and open the updated application.', log_path)
        if status == 'cancelled':
            message = f'The update to {target} was cancelled. You are running version {current}.'
        else:
            reason = {'timeout': 'the application did not close in time',
                'checksum-mismatch': 'the package verification failed',
                'package-changed': 'the downloaded package changed',
                'installation-changed': 'the installation changed',
                'installer-failed': 'the installer could not complete',
                'authorization-failed': 'system authorization was not granted',
                'package-identity-mismatch': 'the package identity did not match the update',
                'runtime-invalid': 'the updated application could not be verified',
                'mount-failed': 'the update disk image could not be opened',
                'signature-invalid': 'the application signature could not be verified',
                'rollback-failed': 'the update could not complete and the previous application could not be restored; see the log for its backup location',
                'reboot-required': 'Setup requires a system restart; no automatic reboot was requested'}.get(status, 'the update helper stopped')
            message = f'Could not update RatioLab to {target}: {reason}. You are running version {current}.'
        return Outcome(False, message, log_path)
    except (OSError, ValueError, TypeError, UnicodeError):
        return Outcome(False, 'The last update result could not be verified. '
                       f'You are running RatioLab {current}; check for updates to try again.')
    finally:
        if claimed is not None:
            try:
                claimed.unlink(missing_ok=True)
            except OSError:
                pass
