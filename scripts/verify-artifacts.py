# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Reject private/generated files and require every runtime payload in artifacts."""
import argparse
from pathlib import Path, PurePosixPath
import tarfile
import zipfile


def verify(folder):
    wheels = list(Path(folder).glob('*.whl'))
    archives = list(Path(folder).glob('*.tar.gz'))
    assert wheels and archives, 'Build both a wheel and an sdist first'
    private_prefixes = {str(Path.home()).encode(), str(Path(__file__).resolve().parent.parent).encode()}
    for artifact in wheels+archives:
        if artifact.suffix == '.whl':
            with zipfile.ZipFile(artifact) as archive:
                files = set(archive.namelist())
                payloads = {name: archive.read(name) for name in files if not name.endswith('/')}
            required = {'app.py', 'app_paths.py', 'geometry.py', 'gl_loader.py', 'ratiolab_cli.py',
                        'ratiolab_agent.py', 'ratiolab_mcp.py', 'ratiolab_resources/MCP.md',
                        'ratiolab_resources/branding/ratiolab-icon.png',
                        'ratiolab_resources/branding/brand.json',
                        'ratiolab_resources/INSTALL.md',
                        'ratiolab_resources/LICENSE', 'ratiolab_resources/COPYRIGHT',
                        'ratiolab_resources/bearing-catalog.json',
                        'ratiolab_resources/hardware-catalog.json'}
            assert required <= files, f'{artifact}: missing {required-files}'
            metadata = next(name for name in files if name.endswith('.dist-info/METADATA'))
            assert b'License-Expression: GPL-3.0-only' in payloads[metadata]
            license_root = metadata.rsplit('/', 1)[0]+'/licenses/'
            assert {license_root+'LICENSE', license_root+'COPYRIGHT'} <= files
        else:
            with tarfile.open(artifact) as archive:
                names = archive.getnames()
                payloads = {name: archive.extractfile(name).read() for name in names if archive.getmember(name).isfile()}
            files = {'/'.join(PurePosixPath(name).parts[1:]) for name in names}
            assert {'pyproject.toml', 'ratiolab_build.py', 'INSTALL.md', 'MCP.md',
                    'LICENSE', 'COPYRIGHT', 'CONTRIBUTING.md', 'CHANGELOG.md',
                    'packaging/mcp_entrypoint.py', 'scripts/check-installed-mcp.py',
                    'assets/branding/ratiolab-icon.png'} <= files
        for name in files:
            path = PurePosixPath(name)
            assert not set(path.parts) & {'work', 'design', 'outputs', 'generated', 'generati', '.git', '.aws', '.codex', '.agents', '__pycache__'}, name
            assert path.name not in {'ui-preferences.json', 'preferenze-ui.json', 'custom-materials.json', 'materiali-custom.json'}, name
            assert path.suffix not in {'.token', '.pyc'}, name
        for name, body in payloads.items():
            for prefix in private_prefixes:
                assert len(prefix) < 2 or prefix not in body, f'{artifact.name}: local absolute path in {name}'
        print(f'{artifact.name}: verified {len(files)} members')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', nargs='?', default='dist')
    verify(parser.parse_args().folder)
