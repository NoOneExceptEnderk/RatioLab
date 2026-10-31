# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Download release packages and verify HTTPS-published SHA256SUMS.

Checksums detect corruption against the selected GitHub release. They are not
publisher signatures. This module never executes, installs or replaces a package.
Injected openers must disable automatic redirects, as the default opener does.
"""
from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import time
from urllib.error import HTTPError
from urllib.parse import quote, urljoin, urlsplit
from urllib.request import Request, build_opener

from updates import NoRedirect, Release, RELEASES_URL, Version

MAX_CHECKSUMS = 1024 * 1024
MAX_PACKAGE = 512 * 1024 * 1024
SOCKET_TIMEOUT = 15
TOTAL_TIMEOUT = 600
CHUNK_SIZE = 64 * 1024
MAX_REDIRECTS = 5
CDN_HOSTS = {'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}


class DownloadCancelled(Exception):
    """The caller cancelled this download; its partial job was removed."""


def _check(cancel, deadline=None):
    if cancel is not None and (cancel.is_set() if hasattr(cancel, 'is_set') else cancel()):
        raise DownloadCancelled('Update download cancelled')
    if deadline is not None and time.monotonic() >= deadline:
        raise TimeoutError('Update download deadline exceeded')


def _validate_release(release):
    if not isinstance(release, Release):
        raise ValueError('Missing release metadata')
    prefix = RELEASES_URL + '/tag/'
    if not isinstance(release.url, str) or not release.url.startswith(prefix):
        raise ValueError('Untrusted release endpoint')
    tag = release.url[len(prefix):]
    Version(tag)
    if release.url != prefix + quote(tag, safe='') or release.version != tag.removeprefix('v'):
        raise ValueError('Release version and endpoint disagree')
    name = release.asset_name
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_.+-]+', name):
        raise ValueError('No supported package metadata for verified download')
    bases = {'.'.join(map(str, Version(tag).core)), tag.removeprefix('v')}
    names = set()
    for base in bases:
        for arch in ('x86_64', 'arm64'):
            for system, suffixes in (('linux', ('.run', '.tar.gz')),
                                     ('macos', ('.dmg',)), ('windows', ('-setup.exe',))):
                names.update(f'RatioLab-{base}-{system}-{arch}{suffix}' for suffix in suffixes)
        names.update(f'ratiolab_{base}_{arch}.deb' for arch in ('amd64', 'arm64'))
    download_prefix = RELEASES_URL + '/download/' + quote(tag, safe='') + '/'
    if name not in names or release.download != download_prefix + quote(name, safe=''):
        raise ValueError('Untrusted package URL or package name')
    if release.checksums_url != download_prefix + 'SHA256SUMS':
        raise ValueError('Missing trusted SHA256SUMS metadata for this release')
    if release.asset_size is not None and (type(release.asset_size) is not int
                                          or not 0 < release.asset_size <= MAX_PACKAGE):
        raise ValueError('Invalid or oversized release package size')


def _redirect_url(url, initial):
    if any(ord(character) < 33 or ord(character) == 127 for character in url):
        raise ValueError('Unsafe package redirect characters')
    parts = urlsplit(url)
    if (parts.scheme != 'https' or parts.username is not None or parts.password is not None
            or parts.port is not None or parts.fragment):
        raise ValueError('Unsafe package redirect')
    if url != initial and parts.netloc not in CDN_HOSTS:
        raise ValueError('Untrusted package redirect host')
    return url


def _open(opener, url, cancel, deadline):
    """Follow a small explicit HTTPS redirect chain, never a hidden redirect."""
    initial = url
    visited = set()
    for _ in range(MAX_REDIRECTS + 1):
        _check(cancel, deadline)
        _redirect_url(url, initial)
        if url in visited:
            raise ValueError('Package redirect loop')
        visited.add(url)
        request = Request(url, headers={'User-Agent': 'RatioLab-update-download',
                                       'Accept': 'application/octet-stream'})
        try:
            response = opener.open(request, timeout=min(SOCKET_TIMEOUT, deadline-time.monotonic()))
        except HTTPError as error:
            if error.code not in (301, 302, 303, 307, 308):
                error.close()
                raise
            response = error
        status = None
        try:
            if response.geturl() != url:
                raise ValueError('Unexpected automatic package redirect')
            status = getattr(response, 'status', None) or response.getcode()
            if status in (301, 302, 303, 307, 308):
                location = response.headers.get('Location')
                if not location:
                    raise ValueError('Package redirect has no location')
                url = _redirect_url(urljoin(url, location), initial)
                continue
            if status != 200:
                raise ValueError('Unexpected package response status')
            _check(cancel, deadline)
            return response
        except BaseException:
            response.close()
            raise
        finally:
            if status in (301, 302, 303, 307, 308):
                response.close()
    raise ValueError('Too many package redirects')


def _read(opener, url, limit, cancel, deadline, sink=None, progress=None, total=None):
    response = _open(opener, url, cancel, deadline)
    received = 0
    data = bytearray() if sink is None else None
    digest = hashlib.sha256()
    try:
        length = response.headers.get('Content-Length')
        if length is not None:
            if not re.fullmatch(r'[0-9]+', str(length)) or int(length) > limit:
                raise ValueError('Invalid or oversized package response length')
            length = int(length)
            if total is not None and length != total:
                raise ValueError('Package response length disagrees with release metadata')
        if progress is not None:
            progress(0, total if total is not None else length)
        while True:
            _check(cancel, deadline)
            chunk = response.read(min(CHUNK_SIZE, limit-received+1))
            _check(cancel, deadline)
            if not chunk:
                break
            received += len(chunk)
            if received > limit or (total is not None and received > total):
                raise ValueError('Update download exceeds its size limit')
            if sink is None:
                data.extend(chunk)
            else:
                sink.write(chunk)
            digest.update(chunk)
            _check(cancel, deadline)
            if progress is not None:
                progress(received, total if total is not None else length)
        if (length is not None and received != length) or (total is not None and received != total):
            raise ValueError('Truncated update download')
        return bytes(data) if data is not None else digest.hexdigest()
    finally:
        response.close()


def _checksum(raw, selected):
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError as error:
        raise ValueError('Invalid SHA256SUMS encoding') from error
    found = None
    for line in text.splitlines():
        if not line:
            continue
        match = re.fullmatch(r'([A-Fa-f0-9]{64}) [ *]([^\r\n]+)', line)
        if match is None:
            raise ValueError('Invalid SHA256SUMS line')
        digest, name = match.groups()
        if not re.fullmatch(r'[A-Za-z0-9_.+-]+', name) or name in ('.', '..'):
            raise ValueError('Unsafe SHA256SUMS filename')
        if name.casefold() == selected.casefold() and name != selected:
            raise ValueError('Ambiguous package filename in SHA256SUMS')
        if name == selected:
            if found is not None:
                raise ValueError('Duplicate package entry in SHA256SUMS')
            found = digest.lower()
    if found is None:
        raise ValueError('Package is missing from SHA256SUMS')
    return found


@dataclass(frozen=True)
class VerifiedDownload:
    path: Path
    sha256: str
    release: Release
    _job: Path | None = field(default=None, repr=False, compare=False)
    _identity: tuple | None = field(default=None, repr=False, compare=False)

    def _owned_job(self):
        if self._job is None or self.path.parent != self._job:
            raise ValueError('Download has no owned cache job')
        info = self._job.lstat()
        if not stat.S_ISDIR(info.st_mode) or (info.st_dev, info.st_ino) != self._identity:
            raise ValueError('Download cache job was replaced')

    def cleanup(self):
        """Remove only the original private job, never a caller-provided path."""
        if self._job is not None and not self._job.exists() and not self._job.is_symlink():
            return
        self._owned_job()
        shutil.rmtree(self._job)

    def reverify(self, cancel=None):
        """Rehash the regular cache file before use; raise if it changed."""
        _validate_release(self.release)
        self._owned_job()
        if self.path.name != self.release.asset_name:
            raise ValueError('Download cache filename changed')
        deadline = time.monotonic() + TOTAL_TIMEOUT
        digest = hashlib.sha256()
        received = 0
        _check(cancel, deadline)
        if not stat.S_ISREG(self.path.lstat().st_mode):
            raise ValueError('Download cache is not a regular file')
        flags = (os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
                 | getattr(os, 'O_NONBLOCK', 0))
        with os.fdopen(os.open(self.path, flags), 'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError('Download cache is not a regular file')
            while True:
                _check(cancel, deadline)
                chunk = stream.read(CHUNK_SIZE)
                _check(cancel, deadline)
                if not chunk:
                    break
                received += len(chunk)
                if received > MAX_PACKAGE:
                    raise ValueError('Cached package exceeds its size limit')
                digest.update(chunk)
                _check(cancel, deadline)
        if ((self.release.asset_size is not None and received != self.release.asset_size)
                or digest.hexdigest() != self.sha256):
            raise ValueError('Cached package checksum or size changed')
        return True


def download_release(release, directory, cancel=None, progress=None, opener=None):
    """Return a verified private cache file; failures remove only this new job.

    ``cancel`` accepts a callable or threading.Event. ``progress`` receives
    (received_bytes, total_bytes_or_None) on the caller's worker thread.
    """
    _validate_release(release)
    _check(cancel)
    deadline = time.monotonic() + TOTAL_TIMEOUT
    parent = Path(directory)
    parent.mkdir(parents=True, exist_ok=True)
    job = Path(tempfile.mkdtemp(prefix='ratiolab-update-', dir=parent)).absolute()
    identity = job.stat()
    result = VerifiedDownload(job/release.asset_name, '', release, job,
                              (identity.st_dev, identity.st_ino))
    try:
        os.chmod(job, 0o700)
        opener = opener or build_opener(NoRedirect())
        raw = _read(opener, release.checksums_url, MAX_CHECKSUMS, cancel, deadline)
        expected = _checksum(raw, release.asset_name)
        _check(cancel, deadline)
        descriptor = os.open(result.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_BINARY', 0), 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            actual = _read(opener, release.download, MAX_PACKAGE, cancel, deadline,
                           stream, progress, release.asset_size)
        _check(cancel, deadline)
        if actual != expected:
            raise ValueError('Update package SHA256 checksum mismatch')
        return VerifiedDownload(result.path, actual, release, job, result._identity)
    except BaseException:
        result.cleanup()
        raise
