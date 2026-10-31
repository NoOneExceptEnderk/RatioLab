#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Build the browser engine without network, native GTK, or third-party build tools.

The runtime is supplied explicitly and verified against webapp/runtime.json.
An external pinned CDN build requires --external-runtime; there is no automatic
network fallback. Output defaults to the ignored work/webapp-dist directory.
"""
import argparse
import ast
import hashlib
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
# Reviewed closure of headless generation, shared surfaces, motion and exporters.
# A new dependency must be reviewed and added explicitly, never collected blindly.
MODULES = (
    'app_paths', 'assemblies', 'backdrivability', 'backlash_solver', 'bevel_geometry', 'bom',
    'cad_export', 'catalog', 'collision_geometry', 'combination_search', 'component_geometry', 'differential_wrist', 'engineering',
    'export_transaction', 'gear_measurement', 'geartrains', 'geometry', 'hardware',
    'hardware_catalog', 'interference', 'kinematics', 'motion', 'mounting', 'package_export',
    'pair_assembly', 'parameter_help', 'printed_shaft', 'profile_export',
    'selected_export', 'solid_geometry', 'special_drives', 'standard_parts',
    'stl_export', 'tooth_profiles', 'internal_mesh', 'wave_envelope', 'wave_geometry', 'worm_geometry',
)
RESOURCES = ('__init__.py', 'version.json', 'bearing-catalog.json', 'hardware-catalog.json')
ASSETS = ('engine-client.js', 'worker.js', 'index.html', 'app.css',
          'app.js', 'viewer.js', 'document.js', 'tools.js', 'tools.css')
BRANDING = ('ratiolab-icon.png', 'ratiolab-logo-dark.png')
LEGAL = ('LICENSE', 'COPYRIGHT')
NOTICES = ('README.txt', 'provenance.json', 'PYODIDE-LICENSE', 'CPYTHON-LICENSE',
           'CPYTHON-NOTICES', 'EMSCRIPTEN-LICENSE', 'MUSL-COPYRIGHT')
RECIPES = ('build-webapp.py', 'fetch-web-runtime.py', 'serve-webapp.py')
FORMAT = 'ratiolab-web-bundle/1'


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)+'\n').encode('utf-8')


def zip_bytes(files):
    stream = BytesIO()
    with ZipFile(stream, 'w', ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            info = ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return stream.getvalue()


def metadata(root):
    """Extract only literal catalog data, without executing GTK-importing code."""
    if not (root/'src/gui_workflow.py').is_file():
        return json.loads((root/'webapp/catalog.json').read_text(encoding='utf-8'))
    result = {}
    for node in ast.parse((root/'src/gui_workflow.py').read_text(encoding='utf-8')).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id in ('CATALOG', 'ADVANCED'):
                result[target.id] = ast.literal_eval(node.value)
            elif isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name) and target.value.id == 'CATALOG':
                result['CATALOG'][ast.literal_eval(target.slice)] = ast.literal_eval(node.value)
    if len(result.get('CATALOG', {})) != 10:
        raise ValueError('Review browser catalog metadata after desktop catalog changes.')
    return dict(catalog=result['CATALOG'], advanced=sorted(result['ADVANCED']))


def engine_files(root):
    files = {name+'.py': (root/'src'/f'{name}.py').read_bytes() for name in MODULES}
    # Detect local import additions even when they sit inside an optional branch.
    local = {p.stem for p in (root/'src').glob('*.py')}
    for name, data in files.items():
        for node in ast.walk(ast.parse(data)):
            dependencies = ([alias.name.split('.')[0] for alias in node.names] if isinstance(node, ast.Import)
                            else [node.module.split('.')[0]] if isinstance(node, ast.ImportFrom) and node.module else [])
            missing = (set(dependencies) & local)-set(MODULES)
            if missing:
                raise ValueError(f'{name}: dependencies need explicit browser review: {sorted(missing)}')
    files['engine_bridge.py'] = (root/'webapp/engine_bridge.py').read_bytes()
    files.update({'ratiolab_resources/'+name: (root/'src/ratiolab_resources'/name).read_bytes() for name in RESOURCES})
    files['ratiolab_resources/web-catalog.json'] = encoded(metadata(root))
    files.update({'ratiolab_resources/'+name: (root/name).read_bytes() for name in LEGAL})
    return files


def build(output, runtime_dir=None, external_runtime=False, root=ROOT):
    if runtime_dir and external_runtime:
        raise ValueError('Choose a local runtime or an explicit external runtime, not both.')
    if not runtime_dir and not external_runtime:
        raise ValueError('Supply --runtime-dir for a self-hosted build, or explicitly choose --external-runtime.')
    output = Path(output).absolute()
    resolved_root = root.resolve()
    if output != output.resolve(strict=False):
        raise ValueError('Output and its parents must not be symlinks.')
    if output == resolved_root or output in resolved_root.parents:
        raise ValueError('Output must not overlap the source directory.')
    if output.is_relative_to(resolved_root) and (not output.is_relative_to(resolved_root/'work') or output == resolved_root/'work'):
        raise ValueError('In-checkout output must be a dedicated directory under ignored work/.')
    if output.exists():
        marker = output/'bundle-manifest.json'
        if not marker.is_file() or marker.is_symlink() or json.loads(marker.read_text()).get('format') != FORMAT:
            raise ValueError('Refusing to replace a directory without a RatioLab web bundle manifest.')
        previous = json.loads(marker.read_text())
        owned_files = previous.get('files', {})
        allowed = {'bundle-manifest.json'}
        for name in owned_files:
            path = PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or path.as_posix() != name:
                raise ValueError('Unsafe path in existing bundle manifest.')
            allowed.add(name)
            allowed.update(parent.as_posix() for parent in path.parents if parent.as_posix() != '.')
        for path in output.rglob('*'):
            name = path.relative_to(output).as_posix()
            if path.is_symlink() or name not in allowed:
                raise ValueError('Refusing to remove extra files or symlinks in output: '+name)
            if path.is_file() and name in owned_files:
                expected = owned_files[name]
                if path.stat().st_size != expected['size'] or hashlib.sha256(path.read_bytes()).hexdigest() != expected['sha256']:
                    raise ValueError('Refusing to overwrite edited output: '+name)
    runtime = json.loads((root/'webapp/runtime.json').read_text(encoding='utf-8'))
    if runtime_dir:
        runtime_dir = Path(runtime_dir)
        for name, expected in runtime['files'].items():
            path = runtime_dir/name
            if path.is_symlink() or not path.is_file():
                raise ValueError('Missing ordinary runtime file: '+name)
            data = path.read_bytes()
            if len(data) != expected['size'] or hashlib.sha256(data).hexdigest() != expected['sha256']:
                raise ValueError('Runtime file differs from pinned release: '+name)
        runtime.update(mode='selfhost', indexURL='./runtime/', allow_external=False)
    else:
        runtime.update(mode='external', indexURL=runtime['pinned_external_indexURL'], allow_external=True)
    files = engine_files(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.ratiolab-web-', dir=output.parent) as temporary:
        staging = Path(temporary)/'bundle'
        staging.mkdir()
        (staging/'engine.zip').write_bytes(zip_bytes(files))
        (staging/'runtime.json').write_bytes(encoded(runtime))
        for name in ASSETS:
            (staging/name).write_bytes((root/'webapp'/name).read_bytes())
        (staging/'branding').mkdir()
        for name in BRANDING:
            (staging/'branding'/name).write_bytes((root/'src/ratiolab_resources/branding'/name).read_bytes())
        for name in LEGAL:
            (staging/name).write_bytes((root/name).read_bytes())
        (staging/'README.txt').write_bytes((root/'webapp/README.txt').read_bytes())
        (staging/'serve.py').write_bytes((root/'scripts/serve-webapp.py').read_bytes())
        (staging/'notices').mkdir()
        for name in NOTICES:
            (staging/'notices'/name).write_bytes((root/'webapp/notices'/name).read_bytes())
        if runtime_dir:
            (staging/'runtime').mkdir()
            for name in sorted(runtime['files']):
                shutil.copyfile(runtime_dir/name, staging/'runtime'/name)
        # Engine source is readable in engine.zip; include web glue and builder too.
        source = {'src/'+name: data for name, data in files.items() if name != 'engine_bridge.py'}
        source['webapp/catalog.json'] = encoded(metadata(root))
        source.update({name: (root/name).read_bytes() for name in LEGAL})
        source.update({'webapp/'+name: (root/'webapp'/name).read_bytes() for name in (*ASSETS, 'runtime.json', 'engine_bridge.py')})
        source.update({'src/ratiolab_resources/branding/'+name: (root/'src/ratiolab_resources/branding'/name).read_bytes() for name in BRANDING})
        source.update({'scripts/'+name: (root/'scripts'/name).read_bytes() for name in RECIPES})
        source['webapp/README.txt'] = (root/'webapp/README.txt').read_bytes()
        source['docs/web-app.md'] = (root/'docs/web-app.md').read_bytes()
        source.update({'webapp/notices/'+name: (root/'webapp/notices'/name).read_bytes() for name in NOTICES})
        (staging/'source.zip').write_bytes(zip_bytes(source))
        manifest_files = {path.relative_to(staging).as_posix(): dict(size=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                          for path in sorted(staging.rglob('*')) if path.is_file()}
        identity = json.loads((root/'src/ratiolab_resources/version.json').read_text(encoding='utf-8'))
        manifest = dict(format=FORMAT, engine_api=1, source_version=identity['release'], runtime_version=runtime['version'],
                        runtime_mode=runtime['mode'], modules=list(MODULES), resources=list(RESOURCES), files=manifest_files)
        (staging/'bundle-manifest.json').write_bytes(encoded(manifest))
        if output.exists():
            shutil.rmtree(output)
        shutil.move(str(staging), str(output))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'work/webapp-dist')
    parser.add_argument('--runtime-dir', type=Path)
    parser.add_argument('--external-runtime', action='store_true')
    args = parser.parse_args()
    try:
        manifest = build(args.output, args.runtime_dir, args.external_runtime)
    except (ValueError, OSError) as error:
        parser.exit(2, str(error)+'\n')
    print(f"Built browser engine: {args.output} ({len(manifest['modules'])} shared modules; runtime {manifest['runtime_mode']})")


if __name__ == '__main__':
    main()
