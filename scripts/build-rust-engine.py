#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Compile the shared Rust kernel and collect its notices; never install/publish."""
from contextlib import contextmanager
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def native_name():
    return ('ratiolab_geometry.dll' if sys.platform == 'win32' else
            'libratiolab_geometry.dylib' if sys.platform == 'darwin' else
            'libratiolab_geometry.so')


def environment():
    env = dict(os.environ)
    flags = (env.get('CARGO_ENCODED_RUSTFLAGS', '').split('\x1f')
             if env.get('CARGO_ENCODED_RUSTFLAGS') else shlex.split(env.get('RUSTFLAGS', '')))
    # Release artifacts must not embed a developer's checkout/home paths.
    # rustc gives the last matching prefix precedence. The dependency cache
    # can live inside this checkout: let its more specific mapping win, so a
    # rebuild from extracted source retains identical dependency panic paths.
    mappings = ((str(Path.home()), '/ratiolab-build-home'),
                (env.get('CARGO_HOME') or str(Path.home()/'.cargo'), '/cargo-cache'),
                (str(ROOT), '/ratiolab-source'))
    for source, replacement in sorted(mappings, key=lambda pair: len(pair[0] or '')):
        if source:
            flags.append('--remap-path-prefix='+source+'='+replacement)
    env['CARGO_ENCODED_RUSTFLAGS'] = '\x1f'.join(flags)
    return env


@contextmanager
def notices_lock():
    # Cargo serializes compilation; protect the adjacent generated notice tree
    # as well when wheel/native/browser builders share one target directory.
    lock_path=ROOT/'target/ratiolab-rust-notices.lock'
    lock_path.parent.mkdir(parents=True,exist_ok=True)
    with lock_path.open('a+b') as stream:
        if os.name=='nt':
            import msvcrt
            if stream.tell()==0:
                stream.write(b'0');stream.flush()
            stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_LOCK,1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(),fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name=='nt':
                stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:
                fcntl.flock(stream.fileno(),fcntl.LOCK_UN)


def collect_notices(cargo,env,offline):
    with notices_lock():
        return _collect_notices(cargo,env,offline)


def _collect_notices(cargo, env, offline):
    command = [cargo, 'metadata', '--locked', '--format-version', '1']
    if offline:
        command.append('--offline')
    metadata = json.loads(subprocess.check_output(command, cwd=ROOT, env=env, text=True))
    target = ROOT/'target/ratiolab-rust-notices'
    staging = ROOT/'target/ratiolab-rust-notices.staging'
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    records = []
    for package in sorted(metadata['packages'], key=lambda p: (p['name'], p['version'])):
        if not package.get('source'):
            continue
        folder = Path(package['manifest_path']).parent
        identifier = package['name']+'-'+package['version']
        licenses = sorted(p for p in folder.iterdir() if p.is_file() and
                          p.name.upper().startswith(('LICENSE', 'COPYRIGHT', 'NOTICE')))
        origin=identifier
        if not licenses:
            # Some monorepo subcrates omit the workspace-root LICENSE from the
            # crate archive. Resolve only an identical repository/license/VCS
            # revision whose packaged path is the workspace root.
            vcs_path=folder/'.cargo_vcs_info.json'
            vcs=json.loads(vcs_path.read_text()) if vcs_path.is_file() else {}
            for peer in metadata['packages']:
                peer_root=Path(peer['manifest_path']).parent
                peer_vcs_path=peer_root/'.cargo_vcs_info.json'
                if not peer_vcs_path.is_file():
                    continue
                peer_vcs=json.loads(peer_vcs_path.read_text())
                if (package.get('repository') and peer.get('repository')==package['repository']
                        and peer.get('license')==package['license']
                        and vcs.get('git',{}).get('sha1')
                        and peer_vcs.get('git',{}).get('sha1')==vcs['git']['sha1']
                        and peer_vcs.get('path_in_vcs')==''):
                    licenses=sorted(p for p in peer_root.iterdir() if p.is_file() and
                        p.name.upper().startswith(('LICENSE','COPYRIGHT','NOTICE')))
                    if licenses:
                        origin=peer['name']+'-'+peer['version']
                        break
        if not licenses:
            raise RuntimeError('Missing Rust dependency notices: '+identifier)
        for path in licenses:
            destination = staging/identifier/path.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
        records.append(dict(name=package['name'], version=package['version'],
                            license=package['license'], source=package['source'], notice_origin=origin,
                            notice_files=[identifier+'/'+p.name for p in licenses]))
    rustc = env.get('RUSTC', 'rustc')
    sysroot = Path(subprocess.check_output([rustc, '--print', 'sysroot'], env=env, text=True).strip())
    copyright_file = sysroot/'share/doc/rust/COPYRIGHT-library.html'
    license_root = sysroot/'share/doc/rust/licenses'
    if not copyright_file.is_file() or not license_root.is_dir():
        raise RuntimeError('The Rust standard-library copyright and license texts are required.')
    (staging/'rust-stdlib').mkdir()
    shutil.copyfile(copyright_file, staging/'rust-stdlib'/copyright_file.name)
    shutil.copytree(license_root, staging/'rust-stdlib/licenses')
    report = dict(format='ratiolab-rust-notices/1',
                  rustc=subprocess.check_output([rustc, '--version'], env=env, text=True).strip(),
                  cargo_lock_sha256=hashlib.sha256((ROOT/'Cargo.lock').read_bytes()).hexdigest(),
                  scope='Rust standard library and all locked runtime/build dependencies', packages=records)
    (staging/'components.json').write_text(json.dumps(report, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    if target.exists():
        shutil.rmtree(target)
    staging.rename(target)
    return target


def build(target='native', cargo=None, offline=False):
    cargo = cargo or os.environ.get('RATIOLAB_CARGO', 'cargo')
    command = [cargo, 'build', '--locked', '--release', '-p', 'ratiolab-geometry', '--lib']
    if offline:
        command.append('--offline')
    if target == 'wasm':
        command += ['--target', 'wasm32-unknown-unknown']
    env = environment()
    subprocess.run(command, cwd=ROOT, env=env, check=True)
    collect_notices(cargo, env, offline)
    return (ROOT/'target/wasm32-unknown-unknown/release/ratiolab_geometry.wasm'
            if target == 'wasm' else ROOT/'target/release'/native_name())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=('native', 'wasm', 'all'), default='native')
    parser.add_argument('--cargo', default=None)
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    for target in ('native', 'wasm') if args.target == 'all' else (args.target,):
        print(build(target, args.cargo, args.offline))
