#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Verify and preview a RatioLab static bundle on 127.0.0.1; no calculations."""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

FORMAT = 'ratiolab-web-bundle/1'


def safe_path(name):
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or '..' in path.parts or '\\' in name
            or path.as_posix() != name or name == '.'):
        raise ValueError('Unsafe bundle manifest path: '+name)
    return path


def read_file(directory, name, expected):
    path = directory
    for part in safe_path(name).parts:
        path = path/part
        if path.is_symlink():
            raise ValueError('Symlinks are not served: '+name)
    if not path.is_file():
        raise ValueError('Missing ordinary bundle file: '+name)
    data = path.read_bytes()
    if len(data) != expected['size'] or hashlib.sha256(data).hexdigest() != expected['sha256']:
        raise ValueError('Bundle file differs from manifest: '+name)
    return data


def verify_bundle(directory):
    directory = Path(directory).absolute()
    if directory != directory.resolve(strict=False) or not directory.is_dir():
        raise ValueError('Bundle directory and its parents must be ordinary directories.')
    marker = directory/'bundle-manifest.json'
    if marker.is_symlink() or not marker.is_file():
        raise ValueError('Missing ordinary bundle-manifest.json.')
    data = marker.read_bytes()
    manifest = json.loads(data)
    if manifest.get('format') != FORMAT or not isinstance(manifest.get('files'), dict):
        raise ValueError('Unsupported bundle manifest.')
    files = manifest['files'].copy()
    if 'bundle-manifest.json' in files or 'index.html' not in files:
        raise ValueError('Incomplete bundle manifest.')
    for name, expected in files.items():
        safe_path(name)
        read_file(directory, name, expected)
    # Unlisted files (for example an archive manager's metadata) are never
    # served. Only manifest paths are opened, verified and allowed over HTTP.
    files['bundle-manifest.json'] = dict(size=len(data), sha256=hashlib.sha256(data).hexdigest())
    return directory, files


def make_server(directory, port=8766):
    directory, files = verify_bundle(directory)

    class StaticHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_file(False)

        def do_HEAD(self):
            self.send_file(True)

        def send_file(self, head):
            path = unquote(urlsplit(self.path).path)
            name = 'index.html' if path == '/' else path[1:] if path.startswith('/') else ''
            if name not in files:
                self.send_error(404, 'File not in bundle manifest')
                return
            try:
                # Recheck before sending, so post-start edits/symlinks cannot
                # expose unrelated data or silently serve a modified artifact.
                data = read_file(directory, name, files[name])
            except (ValueError, OSError):
                self.send_error(409, 'Bundle changed; verify and restart the preview')
                return
            content_type = {'.mjs': 'text/javascript', '.js': 'text/javascript',
                            '.wasm': 'application/wasm', '.md': 'text/plain; charset=utf-8',
                            '.py': 'text/plain; charset=utf-8'}.get(Path(name).suffix)
            content_type = content_type or mimetypes.guess_type(name)[0] or 'text/plain; charset=utf-8'
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            if not head:
                self.wfile.write(data)

    return ThreadingHTTPServer(('127.0.0.1', port), StaticHandler)


def main():
    here = Path(__file__).resolve().parent
    default = here if (here/'bundle-manifest.json').is_file() else here.parent/'work/webapp-dist'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=default)
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('Port must be between 1 and 65535.')
    try:
        server = make_server(args.directory, args.port)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, str(error)+'\n')
    print(f'RatioLab: http://127.0.0.1:{server.server_port}/  (Ctrl+C to stop)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
