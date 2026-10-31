"""Compose the canonical self-hosted browser bundle into the public site."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_SIZE = 25 * 1024 * 1024
# Independent publication boundary: adding a canonical bundle file requires review.
APP_FILES = (
    'index.html', 'app.css', 'app.js', 'tools.css', 'tools.js', 'document.js',
    'viewer.js', 'engine-client.js', 'worker.js', 'engine.zip', 'runtime.json',
    'LICENSE', 'COPYRIGHT', 'README.txt', 'serve.py', 'source.zip',
    'branding/ratiolab-icon.png', 'branding/ratiolab-logo-dark.png',
    'notices/README.txt', 'notices/provenance.json', 'notices/PYODIDE-LICENSE',
    'notices/CPYTHON-LICENSE', 'notices/CPYTHON-NOTICES',
    'notices/EMSCRIPTEN-LICENSE', 'notices/MUSL-COPYRIGHT',
    'runtime/PYODIDE-LICENSE', 'runtime/pyodide-lock.json',
    'runtime/pyodide.asm.mjs', 'runtime/pyodide.asm.wasm',
    'runtime/pyodide.mjs', 'runtime/python_stdlib.zip', 'bundle-manifest.json',
)
# Stable URLs are intentional in the canonical bundle. Revalidate every app byte
# across deploys, including HTML, worker imports and the matching engine archive.
HEADERS = '''/app
  Cache-Control: no-store
/app/*
  Cache-Control: no-store
/app/runtime/pyodide.asm.wasm
  Content-Type: application/wasm
/app/runtime/pyodide.mjs
  Content-Type: text/javascript; charset=utf-8
/app/runtime/pyodide.asm.mjs
  Content-Type: text/javascript; charset=utf-8
'''


def recipe(name, root=None):
    root = Path(root or ROOT)
    spec = importlib.util.spec_from_file_location('ratiolab_site_' + name.replace('-', '_'), root / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def public_app_files():
    return ['app/' + name for name in APP_FILES]


def allowed_directories(files):
    return {parent.as_posix() for name in files for parent in PurePosixPath(name).parents if parent.as_posix() != '.'}


def validate_bundle(directory, root=None):
    """Check an exact ordinary-file inventory and every canonical manifest hash."""
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError('App output must be an ordinary directory')
    expected = set(APP_FILES)
    directories = allowed_directories(expected)
    actual = set()
    for path in directory.rglob('*'):
        name = path.relative_to(directory).as_posix()
        if path.is_symlink() or (path.is_dir() and name not in directories) or (not path.is_dir() and not path.is_file()):
            raise ValueError('Unsafe or unexpected app output: ' + name)
        if path.is_file():
            if name not in expected or path.stat().st_size >= MAX_FILE_SIZE:
                raise ValueError('Unexpected or oversized app file: ' + name)
            actual.add(name)
    if actual != expected:
        raise ValueError('App output must contain exactly the reviewed browser bundle inventory')
    config = recipe('fetch-web-runtime', root).configuration()
    manifest = json.loads((directory / 'bundle-manifest.json').read_text(encoding='utf-8'))
    if (not isinstance(manifest, dict) or manifest.get('format') != 'ratiolab-web-bundle/1' or manifest.get('runtime_mode') != 'selfhost'
            or manifest.get('runtime_version') != config['version'] or manifest.get('engine_api') != 1
            or not isinstance(manifest.get('files'), dict) or set(manifest['files']) != expected - {'bundle-manifest.json'}):
        raise ValueError('App manifest must describe the complete self-hosted bundle')
    for name, entry in manifest['files'].items():
        if (not isinstance(entry, dict) or set(entry) != {'size', 'sha256'} or type(entry['size']) is not int
                or entry['size'] < 0 or not isinstance(entry['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', entry['sha256'])):
            raise ValueError('Invalid app manifest entry: ' + name)
        path = directory / name
        if path.stat().st_size != entry['size'] or hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('App manifest size/SHA256 mismatch: ' + name)
    runtime = json.loads((directory / 'runtime.json').read_text(encoding='utf-8'))
    if (runtime != dict(config, mode='selfhost', indexURL='./runtime/', allow_external=False)):
        raise ValueError('App runtime must use the pinned self-hosted configuration')
    for name, entry in config['files'].items():
        if manifest['files']['runtime/' + name] != entry:
            raise ValueError('App runtime differs from pinned release: ' + name)
    return manifest


def compose_app(staging, *, offline=False, runtime_dir=None):
    """Fetch only for a normal default-cache build; an explicit cache is read-only."""
    root = ROOT
    fetcher = recipe('fetch-web-runtime', root)
    cache = Path(runtime_dir) if runtime_dir is not None else root / 'work/webapp-runtime'
    fetcher.fetch_runtime(cache, check_only=offline or runtime_dir is not None)
    builder = recipe('build-webapp', root)
    # The canonical builder only allows work/ or external output. Never weaken it
    # to accept website staging; validate externally and copy into our own stage.
    with tempfile.TemporaryDirectory(prefix='ratiolab-site-app-') as temporary:
        bundle = Path(temporary) / 'app'
        builder.build(bundle, runtime_dir=cache, root=root)
        manifest = validate_bundle(bundle, root)
        shutil.copytree(bundle, Path(staging) / 'app')
    (Path(staging) / '_headers').write_text(HEADERS, encoding='utf-8')
    return manifest
