# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Reject private/generated files and require every runtime payload in artifacts."""
import argparse
from pathlib import Path, PurePosixPath
import tarfile
import tomllib
import zipfile


def verify(folder):
    wheels = list(Path(folder).glob('*.whl'))
    archives = list(Path(folder).glob('*.tar.gz'))
    assert wheels and archives, 'Build both a wheel and an sdist first'
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root/'pyproject.toml').read_text(encoding='utf-8'))
    modules = {name+'.py' for name in project['tool']['setuptools']['py-modules']}
    resources = {'ratiolab_resources/'+path.relative_to(root/'src/ratiolab_resources').as_posix()
                 for path in (root/'src/ratiolab_resources').rglob('*')
                 if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc'}
    private_prefixes = {str(Path.home()).encode(), str(root).encode()}
    for artifact in wheels+archives:
        if artifact.suffix == '.whl':
            with zipfile.ZipFile(artifact) as archive:
                files = set(archive.namelist())
                payloads = {name: archive.read(name) for name in files if not name.endswith('/')}
            required = modules | resources | {
                'ratiolab_resources/INSTALL.md', 'ratiolab_resources/MCP.md',
                'ratiolab_resources/LICENSE', 'ratiolab_resources/COPYRIGHT',
            }
            assert required <= files, f'{artifact}: missing {required-files}'
            actual_modules = {name for name in files if '/' not in name and name.endswith('.py')}
            assert actual_modules == modules, f'{artifact}: unexpected application module inventory'
            actual_resources = {name for name in files if name.startswith('ratiolab_resources/')
                                and not name.endswith('/')}
            assert actual_resources == required-modules, f'{artifact}: unexpected resource inventory'
            for name in modules | resources:
                assert payloads[name] == (root/'src'/name).read_bytes(), f'{artifact}: changed payload {name}'
            assert not any(PurePosixPath(name).name in {'ratiolab_build.py', 'build_support.py'} or
                           PurePosixPath(name).name.startswith('test_') or
                           set(PurePosixPath(name).parts) & {'tests', 'build-support', 'docs', 'build_support'}
                           for name in files), f'{artifact}: development files in wheel'
            for source, destination in (
                ('LICENSE', 'LICENSE'), ('COPYRIGHT', 'COPYRIGHT'),
                ('docs/installation.md', 'INSTALL.md'), ('docs/mcp.md', 'MCP.md'),
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
            required = {'pyproject.toml', 'build-support/ratiolab_build.py',
                        'docs/installation.md', 'docs/development.md', 'docs/mcp.md',
                        'LICENSE', 'COPYRIGHT', 'CONTRIBUTING.md', 'CHANGELOG.md',
                        'packaging/mcp_entrypoint.py', 'scripts/check-installed-mcp.py'}
            required |= {'src/'+name for name in modules | resources}
            required |= {'tests/'+path.name for path in (root/'tests').glob('test_*.py')}
            required |= {'packaging/fonts/'+name for name in
                         ('DejaVuSans.ttf', 'DejaVuSansMono.ttf', 'DejaVuSans-Bold.ttf',
                          'LICENSE-DejaVu.txt', 'AUTHORS-DejaVu.txt', 'SOURCE.json')}
            assert required <= files, f'{artifact}: missing {required-files}'
            assert not modules & files, f'{artifact}: application modules outside src/'
            assert not {'bearing-catalog.json', 'hardware-catalog.json'} & files, artifact
            assert not any(name.startswith('assets/branding/') for name in files), artifact
        for name in files:
            path = PurePosixPath(name)
            assert not set(path.parts) & {'work', 'design', 'outputs', 'generated', 'generati', '.git', '.aws', '.codex', '.agents', '.claude', '__pycache__'}, name
            assert path.name not in {'ui-preferences.json', 'preferenze-ui.json', 'custom-materials.json', 'materiali-custom.json',
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
