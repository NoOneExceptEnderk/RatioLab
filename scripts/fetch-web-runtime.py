#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Fetch or check the six pinned Pyodide runtime files using Python's stdlib."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PINNED_BASE = 'https://cdn.jsdelivr.net/pyodide/v314.0.7/full/'
UPSTREAM_URLS = {name: PINNED_BASE+name for name in (
    'pyodide-lock.json', 'pyodide.asm.mjs', 'pyodide.asm.wasm', 'pyodide.mjs', 'python_stdlib.zip')}
UPSTREAM_URLS['PYODIDE-LICENSE'] = 'https://raw.githubusercontent.com/pyodide/pyodide/314.0.7/LICENSE'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Runtime downloads must not redirect away from their pinned URL.')


def configuration():
    value = json.loads((ROOT/'webapp/runtime.json').read_text(encoding='utf-8'))
    if (value['format'] != 'ratiolab-web-runtime/1' or value['version'] != '314.0.7'
            or value['python'] != '3.14.2' or value['pinned_external_indexURL'] != PINNED_BASE
            or set(value['files']) != set(UPSTREAM_URLS)):
        raise ValueError('Runtime pins changed; review the downloader before fetching.')
    return value


def ordinary_directory(directory):
    directory = Path(directory).absolute()
    if directory != directory.resolve(strict=False):
        raise ValueError('Runtime directory and its parents must not be symlinks.')
    if directory.exists() and not directory.is_dir():
        raise ValueError('Runtime destination must be a directory.')
    return directory


def verified(path, expected):
    if path.is_symlink() or not path.is_file():
        raise ValueError('Runtime target must be an ordinary file: '+path.name)
    data = path.read_bytes()
    if len(data) != expected['size'] or hashlib.sha256(data).hexdigest() != expected['sha256']:
        raise ValueError('Refusing to replace edited or corrupt runtime file: '+path.name)


def fetch_runtime(directory, check_only=False, opener=None):
    config = configuration()
    directory = ordinary_directory(directory)
    missing = []
    # Preflight every existing target before any network or mutation. Unrelated
    # cache metadata is never removed or replaced.
    for name, expected in sorted(config['files'].items()):
        target = directory/name
        if target.exists() or target.is_symlink():
            verified(target, expected)
        else:
            missing.append(name)
    if check_only:
        if missing:
            raise ValueError('Missing pinned runtime files: '+', '.join(missing))
        return []
    if not missing:
        return []
    directory.mkdir(parents=True, exist_ok=True)
    opener = opener or urllib.request.build_opener(NoRedirect()).open
    with tempfile.TemporaryDirectory(prefix='.ratiolab-fetch-', dir=directory) as temporary:
        staged = Path(temporary)
        for name in missing:
            expected = config['files'][name]
            with opener(UPSTREAM_URLS[name], timeout=60) as response:
                # Bound even an incorrect HTTP response to the pinned length.
                data = response.read(expected['size']+1)
            if len(data) != expected['size'] or hashlib.sha256(data).hexdigest() != expected['sha256']:
                raise ValueError('Downloaded runtime differs from pinned size/SHA256: '+name)
            (staged/name).write_bytes(data)
        for name in missing:
            # A hard link publishes a complete file atomically without replacing
            # a target that appeared after preflight (including a symlink).
            os.link(staged/name, directory/name)
    return missing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=ROOT/'work/webapp-runtime')
    parser.add_argument('--check-only', action='store_true', help='Verify cache without network or writes.')
    args = parser.parse_args()
    try:
        downloaded = fetch_runtime(args.directory, args.check_only)
    except (ValueError, OSError) as error:
        parser.exit(2, str(error)+'\n')
    print(f'Runtime verified: {args.directory} ({len(downloaded)} files fetched; Pyodide 314.0.7 / Python 3.14.2)')


if __name__ == '__main__':
    main()
