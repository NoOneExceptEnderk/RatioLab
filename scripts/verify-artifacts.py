# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Reject private/generated files and require every runtime payload in artifacts."""
import argparse
import ast
from pathlib import Path, PurePosixPath
import tarfile
import tomllib
import zipfile


def runtime_modules(root, project):
    """Check local dependencies independently of the distribution's module list.

    Walk function bodies too: GUI dependencies are often imported only when a
    workspace panel is opened. Packaging an incomplete list is not sufficient.
    """
    declared = set(project['tool']['setuptools']['py-modules'])
    local = {path.stem: path for path in (root/'src').glob('*.py')}
    assert declared <= local.keys(), f'Missing module sources: {sorted(declared-local.keys())}'
    for name in sorted(declared):
        tree = ast.parse(local[name].read_text(encoding='utf-8'), filename=str(local[name]))
        for node in ast.walk(tree):
            dependencies = ([alias.name.split('.')[0] for alias in node.names] if isinstance(node, ast.Import)
                            else [node.module.split('.')[0]] if isinstance(node, ast.ImportFrom) and node.module else [])
            missing = (set(dependencies) & local.keys())-declared
            assert not missing, f'{name}:{node.lineno}: unpackaged local dependencies {sorted(missing)}'
    return {name+'.py' for name in declared}


def verify(folder):
    wheels = list(Path(folder).glob('*.whl'))
    archives = list(Path(folder).glob('*.tar.gz'))
    assert wheels and archives, 'Build both a wheel and an sdist first'
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root/'pyproject.toml').read_text(encoding='utf-8'))
    modules = runtime_modules(root, project)
    resources = {'ratiolab_resources/'+path.relative_to(root/'src/ratiolab_resources').as_posix()
                 for path in (root/'src/ratiolab_resources').rglob('*')
                 if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc'}
    native_names={'libratiolab_geometry.so','libratiolab_geometry.dylib','ratiolab_geometry.dll'}
    native=next((p for p in (root/'target/release').glob('*') if p.name in native_names),None)
    assert native is not None,'Build the native Rust kernel before verifying its wheel'
    generated={'ratiolab_resources/native/'+native.name:native.read_bytes()}
    notices=root/'target/ratiolab-rust-notices'
    assert (notices/'components.json').is_file(),'Rust notices are missing'
    generated.update({'ratiolab_resources/rust-notices/'+p.relative_to(notices).as_posix():p.read_bytes()
                      for p in notices.rglob('*') if p.is_file()})
    private_prefixes = {str(Path.home()).encode(), str(root).encode()}
    for artifact in wheels+archives:
        if artifact.suffix == '.whl':
            with zipfile.ZipFile(artifact) as archive:
                files = set(archive.namelist())
                payloads = {name: archive.read(name) for name in files if not name.endswith('/')}
            required = modules | resources | set(generated) | {
                'ratiolab_resources/INSTALL.md', 'ratiolab_resources/MCP.md',
                'ratiolab_resources/CHANGELOG.md',
                'ratiolab_resources/LICENSE', 'ratiolab_resources/COPYRIGHT',
            }
            assert required <= files, f'{artifact}: missing {required-files}'
            actual_modules = {name for name in files if '/' not in name and name.endswith('.py')}
            assert actual_modules == modules, f'{artifact}: unexpected application module inventory'
            actual_resources = {name for name in files if name.startswith('ratiolab_resources/')
                                and not name.endswith('/')}
            assert actual_resources == required-modules, f'{artifact}: unexpected resource inventory'
            for name,data in generated.items():
                assert payloads[name]==data, f'{artifact}: changed Rust payload {name}'
            wheel_metadata=next(name for name in files if name.endswith('.dist-info/WHEEL'))
            assert b'Root-Is-Purelib: false' in payloads[wheel_metadata]
            assert not artifact.name.endswith('-any.whl'),'Native Rust wheel requires a platform tag'
            for name in modules | resources:
                assert payloads[name] == (root/'src'/name).read_bytes(), f'{artifact}: changed payload {name}'
            assert not any(PurePosixPath(name).name in {'ratiolab_build.py', 'build_support.py'} or
                           PurePosixPath(name).name.startswith('test_') or
                           set(PurePosixPath(name).parts) & {'tests', 'build-support', 'docs', 'build_support'}
                           for name in files), f'{artifact}: development files in wheel'
            for source, destination in (
                ('LICENSE', 'LICENSE'), ('COPYRIGHT', 'COPYRIGHT'),
                ('docs/installation.md', 'INSTALL.md'), ('docs/mcp.md', 'MCP.md'),
                ('CHANGELOG.md', 'CHANGELOG.md'),
            ):
                assert payloads['ratiolab_resources/'+destination] == (root/source).read_bytes(), destination
            metadata = next(name for name in files if name.endswith('.dist-info/METADATA'))
            assert b'License-Expression: GPL-3.0-only' in payloads[metadata]
            license_root = metadata.rsplit('/', 1)[0]+'/licenses/'
            assert {license_root+'LICENSE', license_root+'COPYRIGHT'} <= files
        else:
            with tarfile.open(artifact) as archive:
                names = archive.getnames()
                payloads = {name: archive.extractfile(name).read() for name in names if archive.getmember(name).isfile()}
            files = {'/'.join(PurePosixPath(name).parts[1:]) for name in names}
            required = {'Cargo.toml','Cargo.lock','rust-toolchain.toml','scripts/build-rust-engine.py','pyproject.toml', 'build-support/ratiolab_build.py',
                        'docs/installation.md', 'docs/development.md', 'docs/mcp.md',
                        'LICENSE', 'COPYRIGHT', 'CONTRIBUTING.md', 'CHANGELOG.md',
                        'packaging/mcp_entrypoint.py', 'scripts/check-installed-mcp.py'}
            required |= {p.relative_to(root).as_posix() for p in (root/'rust').rglob('*') if p.is_file()}
            assert not any(name.startswith('target/') for name in files),'Rust build products must not enter the sdist'
            required |= {'src/'+name for name in modules | resources}
            required |= {'tests/'+path.name for path in (root/'tests').glob('test_*.py')}
            # Include every font payload, licence and provenance record, rather
            # than maintaining a second list that can omit a newly added font.
            fonts = {'packaging/fonts/'+path.relative_to(root/'packaging/fonts').as_posix()
                     for path in (root/'packaging/fonts').rglob('*') if path.is_file()}
            required |= fonts
            assert required <= files, f'{artifact}: missing {required-files}'
            prefix = PurePosixPath(names[0]).parts[0]+'/'
            for name in fonts:
                assert payloads[prefix+name] == (root/name).read_bytes(), f'{artifact}: changed font payload {name}'
            assert not modules & files, f'{artifact}: application modules outside src/'
            assert not {'bearing-catalog.json', 'hardware-catalog.json'} & files, artifact
            assert not any(name.startswith('assets/branding/') for name in files), artifact
        for name in files:
            path = PurePosixPath(name)
            assert not set(path.parts) & {'work', 'design', 'outputs', 'generated', 'generati', '.git', '.aws', '.codex', '.agents', '.claude', '__pycache__'}, name
            assert path.name not in {'ui-preferences.json', 'preferenze-ui.json', 'updates.json', 'custom-materials.json', 'materiali-custom.json',
                                     'TODO.md', 'VERIFICATION.md', 'AGENTS.md', 'SKILL.md'}, name
            assert path.suffix not in {'.token', '.pyc'}, name
        for name, body in payloads.items():
            for prefix in private_prefixes:
                assert len(prefix) < 2 or prefix not in body, f'{artifact.name}: local absolute path in {name}'
        print(f'{artifact.name}: verified {len(files)} members')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', nargs='?', default='dist')
    verify(parser.parse_args().folder)
