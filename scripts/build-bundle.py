#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Build and verify a native onedir GTK4/Python application with PyInstaller.

Requires the native build dependencies documented in INSTALL.md. Cross-building
Windows/macOS from Linux is deliberately rejected by their packaging scripts.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import runpy
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def host_system():
    return {'win32': 'windows', 'darwin': 'macos'}.get(sys.platform, 'linux')


def architecture():
    machine = platform.machine().lower()
    return {'amd64': 'x86_64', 'aarch64': 'arm64'}.get(machine, machine)


def version():
    # The supported build Pythons are 3.11+ (runtime remains Python 3.10+).
    import tomllib
    return tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))['project']['version']


def bundle_paths(bundle):
    bundle = Path(bundle).resolve()
    if bundle.suffix == '.app':
        return bundle/'Contents/MacOS/RatioLab', bundle/'Contents/Frameworks', bundle.parent/'bundle-manifest.json'
    return bundle/('RatioLab.exe' if (bundle/'RatioLab.exe').is_file() else 'RatioLab'), bundle/'_internal', bundle/'bundle-manifest.json'


def agent_executable(bundle):
    executable, _, _ = bundle_paths(bundle)
    return executable.with_name('RatioLab-MCP.exe' if executable.suffix == '.exe' else 'RatioLab-MCP')


def inventory(bundle):
    bundle = Path(bundle).resolve()
    records = []
    for path in sorted(bundle.rglob('*')):
        relative = path.relative_to(bundle).as_posix()
        if relative == 'bundle-manifest.json':
            continue
        if path.is_symlink():
            target = os.readlink(path)
            if Path(target).is_absolute() or not path.resolve().is_relative_to(bundle):
                raise RuntimeError(f'External symlink in bundle: {relative}')
            records.append(dict(path=relative, kind='symlink', target=target))
        elif path.is_file():
            records.append(dict(path=relative, kind='file', size=path.stat().st_size,
                                sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        if set(Path(relative).parts) & {'work', 'design', 'outputs', 'generated', 'generati', '.git', '.aws', '.codex', '.agents'}:
            raise RuntimeError(f'Private/generated directory in bundle: {relative}')
        if path.name in ('ui-preferences.json', 'preferenze-ui.json', 'custom-materials.json', 'materiali-custom.json') or path.suffix == '.token':
            raise RuntimeError(f'Personal data in bundle: {relative}')
    return records


def sanitized_environment(bundle):
    environment = dict(os.environ)
    for key in ('PYTHONPATH', 'PYTHONHOME', 'GI_TYPELIB_PATH', 'GSETTINGS_SCHEMA_DIR',
                'GTK_DATA_PREFIX', 'GTK_EXE_PREFIX', 'GTK_PATH', 'PYGI_DLL_PATH',
                'GDK_PIXBUF_MODULE_FILE', 'GDK_PIXBUF_MODULEDIR', 'FONTCONFIG_FILE',
                'FONTCONFIG_PATH', 'GIO_EXTRA_MODULES', 'GIO_MODULE_DIR', 'XDG_DATA_DIRS',
                'LD_LIBRARY_PATH', 'DYLD_LIBRARY_PATH', 'DYLD_FALLBACK_LIBRARY_PATH'):
        environment.pop(key, None)
    if sys.platform == 'win32':
        windows = Path(environment.get('SystemRoot', r'C:\Windows'))
        environment['PATH'] = os.pathsep.join(map(str, (windows/'System32', windows)))
    else:
        environment['PATH'] = '/usr/bin:/bin:/usr/sbin:/sbin'
    return environment


def minimum_macos(bundle):
    minimum = (0, 0, 0)
    for path in Path(bundle).rglob('*'):
        if path.is_symlink() or not path.is_file():
            continue
        with path.open('rb') as stream:
            magic = stream.read(4)
        if magic not in (b'\xfe\xed\xfa\xce', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xcf\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca', b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca'):
            continue
        output = subprocess.check_output(['/usr/bin/otool', '-l', str(path)], text=True)
        command = ''
        for line in output.splitlines():
            words = line.strip().split()
            if len(words) == 2 and words[0] == 'cmd':
                command = words[1]
            if len(words) == 2 and ((command == 'LC_BUILD_VERSION' and words[0] == 'minos')
                                  or (command == 'LC_VERSION_MIN_MACOSX' and words[0] == 'version')):
                values = tuple(int(value) for value in words[1].split('.'))
                candidate = values+(0,)*(3-len(values))
                minimum = max(minimum, candidate)
    declared = plistlib.loads((Path(bundle)/'Contents/Info.plist').read_bytes())['LSMinimumSystemVersion']
    values = tuple(int(value) for value in declared.split('.'))
    declared_tuple = values+(0,)*(3-len(values))
    if declared_tuple < minimum:
        required = '.'.join(map(str, minimum))
        raise RuntimeError(f'A native dependency requires macOS {required}; rebuild with MACOSX_DEPLOYMENT_TARGET={required}.')
    return declared


def verify_bundle(bundle, *, gui=False, run=True, check_manifest=True):
    executable, runtime, manifest_file = bundle_paths(bundle)
    bundle = Path(bundle).resolve()
    if not executable.is_file() or not runtime.is_dir():
        raise RuntimeError(f'Not a complete RatioLab onedir bundle: {bundle}')
    if not agent_executable(bundle).is_file():
        raise RuntimeError('The MCP console companion is missing from the bundle')
    # On macOS PyInstaller cross-links data and libraries between Resources and
    # Frameworks; both are inside the signed application and are acceptable.
    required = ['gi_typelibs/Gtk-4.0.typelib', 'gi_typelibs/Gdk-4.0.typelib',
                'share/glib-2.0/schemas/gschemas.compiled',
                'ratiolab_resources/branding/ratiolab-icon.png',
                'ratiolab_resources/bearing-catalog.json',
                'ratiolab_resources/hardware-catalog.json',
                'ratiolab_resources/MCP.md',
                'ratiolab_resources/LICENSE', 'ratiolab_resources/COPYRIGHT',
                'etc/fonts/fonts.conf', 'share/fonts/DejaVuSans.ttf',
                'notices/components.json', 'notices/THIRD-PARTY-NOTICES.txt']
    missing = [name for name in required if not (runtime/name).is_file()]
    if missing:
        raise RuntimeError('Bundle runtime data missing: '+', '.join(missing))
    # Installer assets must carry the project's actual license and attribution,
    # independently of the dependency notices collected below.
    for name in ('LICENSE', 'COPYRIGHT'):
        if (runtime/'ratiolab_resources'/name).read_bytes() != (ROOT/name).read_bytes():
            raise RuntimeError(f'Bundle project notice differs from source: {name}')
    if not any(runtime.glob('*epoxy*')):
        raise RuntimeError('Bundled libepoxy is missing')
    if sys.platform == 'win32' and any(not (runtime/name).is_file() for name in ('libEGL.dll','libGLESv2.dll')):
        raise RuntimeError('Windows GTK EGL/ANGLE runtime is missing')
    notices = json.loads((runtime/'notices/components.json').read_text(encoding='utf-8'))
    if not notices.get('complete'):
        raise RuntimeError('Native third-party notices are incomplete')
    actual = inventory(bundle)
    if check_manifest:
        expected = json.loads(manifest_file.read_text(encoding='utf-8'))
        if expected.get('files') != actual:
            raise RuntimeError('Bundle contents differ from bundle-manifest.json')
    result = dict(structure='passed', file_count=len(actual), native_components=len(notices['components']))
    if run:
        with tempfile.TemporaryDirectory(prefix='ratiolab-bundle-check-') as temporary:
            report = Path(temporary)/'report.json'
            completed = subprocess.run([str(executable), '--self-test-gui' if gui else '--self-test', '--report', str(report)],
                                       cwd=temporary, env=sanitized_environment(bundle),
                                       capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180)
            output = report.read_text(encoding='utf-8') if report.is_file() else completed.stdout
            if completed.returncode:
                raise RuntimeError(f'Frozen self-test failed ({completed.returncode}):\n{output}\n{completed.stderr}')
            runtime_report = json.loads(output)
            if runtime_report.get('self_test') != 'passed' or not runtime_report.get('bundled'):
                raise RuntimeError(f'Frozen self-test did not prove a bundled runtime: {output}')
            if gui and (runtime_report.get('workspace_export') != 'passed' or not runtime_report.get('framebuffer_has_geometry')):
                raise RuntimeError('Frozen GUI self-test did not render/export the full workspace')
            # Keep runtime paths in the local report, not the distributed manifest.
            result['self_test'] = {key: runtime_report[key] for key in
                                   ('self_test', 'families', 'gtk', 'cairo', 'stl_bytes', 'step_files',
                                    'workspace_export', 'opengl_version', 'framebuffer_has_geometry')
                                   if key in runtime_report}
            check_agent = runpy.run_path(str(ROOT/'scripts/check-installed-mcp.py'))['check']
            result['mcp'] = check_agent(agent_executable(bundle), environment=sanitized_environment(bundle))
    return result


def build(args):
    from app_paths import prepare_native_runtime, require_gtk_version
    prepare_native_runtime()
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gtk
    require_gtk_version(Gtk)
    import cairo
    try:
        gi.require_foreign('cairo')
        try:
            gi.require_version('GIRepository', '3.0')
        except ValueError:
            gi.require_version('GIRepository', '2.0')
        from gi.repository import GIRepository
    except (ImportError, ValueError) as error:
        raise RuntimeError('The native GI Cairo converter or build-time GIRepository typelib is missing. '
                           'On Ubuntu 24.04 install python3-gi-cairo and gir1.2-girepository-2.0.') from error
    import PyInstaller
    from PyInstaller.depend.bindepend import get_python_library_path
    try:
        python_library = get_python_library_path()
    except Exception as error:
        raise RuntimeError('The native shared Python library is missing. On Ubuntu 24.04 '
                           'install libpython3.12 (in addition to python3-venv) before building.') from error
    if not python_library:
        raise RuntimeError('A shared Python library is required; on Ubuntu 24.04 install libpython3.12.')
    if sys.platform == 'win32':
        import sysconfig
        if not sysconfig.get_platform().startswith('mingw'):
            raise RuntimeError('Windows builds require MSYS2 UCRT64 Python and its native PyInstaller package')
        if os.environ.get('MSYSTEM') != 'UCRT64' or not shutil.which('pacman') or not shutil.which('cygpath'):
            raise RuntimeError('Run the Windows native build from the MSYS2 UCRT64 terminal, with pacman and cygpath on PATH')
        if architecture() != 'x86_64':
            raise RuntimeError('The Windows installer recipe currently targets UCRT64 x86-64')
    if architecture() not in ('x86_64', 'arm64'):
        raise RuntimeError('Unsupported native architecture: '+architecture())
    label = host_system()+'-'+architecture()
    output = Path(args.dist_dir).resolve()/label
    work = Path(args.work_dir).resolve()/label
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    metadata = work/'notices'
    if metadata.exists():
        shutil.rmtree(metadata)
    metadata.mkdir()
    environment = dict(os.environ, RATIOLAB_VERSION=version(), RATIOLAB_BUNDLE_METADATA=str(metadata),
                       PYINSTALLER_CONFIG_DIR=str(work/'pyinstaller-cache'))
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                    '--distpath', str(output), '--workpath', str(work/'pyinstaller'),
                    str(ROOT/'packaging/RatioLab.spec')], cwd=ROOT, env=environment, check=True)
    bundle = output/('RatioLab.app' if sys.platform == 'darwin' else 'RatioLab')
    executable, runtime, manifest_file = bundle_paths(bundle)
    manifest = dict(format='ratiolab-bundle/1', application_id='local.solidcraft.reducers',
                    name='RatioLab', version=version(), system=host_system(), arch=architecture(),
                    executable=executable.relative_to(bundle).as_posix(),
                    agent_executable=agent_executable(bundle).relative_to(bundle).as_posix(),
                    mcp_protocols=['2026-07-28', '2025-11-25'],
                    min_glibc=platform.libc_ver()[1] if sys.platform.startswith('linux') else None,
                    built_at=datetime.now(timezone.utc).isoformat(), python_version=platform.python_version(),
                    pyinstaller_version=PyInstaller.__version__, notices_complete=True,
                    files=inventory(bundle))
    if sys.platform == 'darwin':
        manifest['min_macos'] = minimum_macos(bundle)
    elif sys.platform == 'win32':
        manifest['min_windows_build'] = 22000
    manifest_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    result = verify_bundle(bundle, gui=args.gui)
    # A self-test must never mutate the installed code or runtime data.
    if inventory(bundle) != manifest['files']:
        raise RuntimeError('The frozen application modified its own bundle')
    print(json.dumps(dict(bundle=str(bundle), manifest=str(manifest_file), verification=result), indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist-dir', default=ROOT/'dist/bundles', type=Path)
    parser.add_argument('--work-dir', default=ROOT/'work/bundle-build', type=Path)
    parser.add_argument('--gui', action='store_true', help='Require real GL rendering and full workspace exports')
    parser.add_argument('--verify-only', type=Path, metavar='BUNDLE')
    parser.add_argument('--structure-only', action='store_true', help='For verify-only: validate files/notices without running the executable')
    args = parser.parse_args()
    if args.structure_only and not args.verify_only:
        parser.error('--structure-only requires --verify-only')
    if args.verify_only:
        print(json.dumps(verify_bundle(args.verify_only, gui=args.gui, run=not args.structure_only), indent=2))
    else:
        build(args)


if __name__ == '__main__':
    main()
