# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Package a verified native onedir bundle as a .run, tar.gz and Debian package."""
import argparse
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parent.parent
HEADER = b'''#!/bin/sh
set -eu
if [ "${1:-}" = --help ]; then
    printf '%s\\n' 'RatioLab installer: GTK and Python are included.' 'Options: --destination /absolute/folder, --no-desktop, --yes'
    exit 0
fi
temporary=$(mktemp -d "${TMPDIR:-/tmp}/ratiolab-setup.XXXXXX")
trap 'rm -rf -- "$temporary"' EXIT HUP INT TERM
line=$(awk '/^__RATIOLAB_ARCHIVE_BELOW__$/ {print NR+1; exit}' "$0")
tail -n +"$line" "$0" | tar -xz -C "$temporary"
package=$(find "$temporary" -mindepth 1 -maxdepth 1 -type d)
sh "$package/install.sh" "$@"
exit $?
__RATIOLAB_ARCHIVE_BELOW__
'''


def add_tree(archive, source, prefix):
    def normalize(info):
        info.uid = info.gid = 0
        info.uname = info.gname = 'root'
        info.mtime = int(os.environ.get('SOURCE_DATE_EPOCH', '0'))
        return info
    archive.add(source, arcname=prefix, filter=normalize)


def make_deb(bundle, output, version, arch, glibc):
    if not shutil.which('dpkg-deb'):
        raise RuntimeError('dpkg-deb is required for --deb; run on Debian/Ubuntu')
    with tempfile.TemporaryDirectory(prefix='ratiolab-deb-') as temporary:
        root = Path(temporary)
        app = root/'opt/ratiolab'
        shutil.copytree(bundle, app, symlinks=True)
        control = root/'DEBIAN'
        control.mkdir()
        size = sum(p.stat().st_size for p in app.rglob('*') if p.is_file() and not p.is_symlink())//1024
        (control/'control').write_text(
            f'Package: ratiolab\nVersion: {version}\nSection: graphics\nPriority: optional\n'
            f'Architecture: {arch}\nInstalled-Size: {size}\nMaintainer: RatioLab project\n'
            f'Depends: libc6 (>= {glibc}), libgl1, libegl1, xdg-utils\n'
            'Description: Parametric gear and reducer generator\n'
            ' Includes the Python and GTK runtime. Graphics drivers are supplied by the operating system.\n', encoding='utf-8')
        desktop = root/'usr/share/applications/local.solidcraft.reducers.desktop'
        desktop.parent.mkdir(parents=True)
        desktop.write_text('[Desktop Entry]\nType=Application\nName=RatioLab\n'
                           'Comment=Parametric gear and reducer generator\n'
                           'Exec=/opt/ratiolab/RatioLab\n'
                           'Icon=/opt/ratiolab/_internal/ratiolab_resources/branding/ratiolab-icon.png\n'
                           'Terminal=false\nStartupNotify=true\nStartupWMClass=local.solidcraft.reducers\n'
                           'Categories=Graphics;Engineering;\n', encoding='utf-8')
        for name in ('postinst', 'postrm'):
            path = control/name
            path.write_text('#!/bin/sh\nset -e\nif command -v update-desktop-database >/dev/null 2>&1; then\n'
                            '    update-desktop-database /usr/share/applications || true\nfi\nexit 0\n')
            path.chmod(0o755)
        subprocess.run(['dpkg-deb', '--build', '--root-owner-group', str(root), str(output)], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, default=ROOT/'dist/installers')
    parser.add_argument('--deb', action='store_true', help='Also create an Ubuntu/Debian package')
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    spec = importlib.util.spec_from_file_location('ratiolab_native_builder', ROOT/'scripts/build-bundle.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    # Never turn an incomplete or modified directory into a downloadable
    # installer. This runs the real frozen executable without host Python/GTK.
    builder.verify_bundle(bundle)
    manifest = json.loads((bundle/'bundle-manifest.json').read_text(encoding='utf-8'))
    version, arch, glibc = (manifest[key] for key in ('version', 'arch', 'min_glibc'))
    if manifest['system'] != 'linux' or not re.fullmatch(r'\d+\.\d+(?:\.\d+)?', version):
        raise ValueError('Expected a versioned Linux bundle')
    if arch not in ('x86_64', 'arm64') or not re.fullmatch(r'\d+\.\d+', glibc):
        raise ValueError('Unsupported architecture or missing glibc build baseline')
    if not (bundle/'RatioLab').is_file():
        raise ValueError('The real RatioLab executable is missing')
    for path in bundle.rglob('*'):
        if path.is_symlink() and (os.path.isabs(os.readlink(path)) or not path.resolve().is_relative_to(bundle)):
            raise ValueError(f'Non-relocatable bundle symlink: {path}')
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    stem = f'RatioLab-{version}-linux-{arch}'
    archive_path = output/(stem+'.tar.gz')
    with tempfile.TemporaryDirectory(prefix='ratiolab-package-') as temporary:
        root = Path(temporary)/stem
        root.mkdir()
        shutil.copy2(ROOT/'scripts/install-bundle-linux.sh', root/'install.sh')
        shutil.copy2(ROOT/'scripts/uninstall-bundle-linux.sh', root/'uninstall.sh')
        paths = [entry['path'] for entry in manifest['files']] + ['bundle-manifest.json']
        if any('\n' in path or '\r' in path or '..' in Path(path).parts or Path(path).is_absolute() for path in paths):
            raise ValueError('Unsafe bundle inventory')
        (root/'installed-files.txt').write_text('\n'.join(sorted(paths))+'\n', encoding='utf-8')
        (root/'install.sh').chmod(0o755)
        (root/'uninstall.sh').chmod(0o755)
        shutil.copytree(bundle, root/'RatioLab', symlinks=True)
        (root/'READ-ME.txt').write_text(
            f'RatioLab {version} for Linux {arch}\n\n'
            f'GTK and Python are included. Requires glibc {glibc}+ and a desktop OpenGL 3.3 driver.\n'
            'Ubuntu/Debian: open the .deb package if supplied.\n'
            'Other desktops: run sh install.sh. No administrator password is needed.\n'
            'To uninstall the user installation, run its uninstall.sh. Projects and preferences are kept.\n', encoding='utf-8')
        with archive_path.open('wb') as stream, gzip.GzipFile(fileobj=stream, mode='wb', mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode='w') as archive:
                add_tree(archive, root, stem)
    installer = output/(stem+'.run')
    with installer.open('wb') as target, archive_path.open('rb') as source:
        target.write(HEADER)
        shutil.copyfileobj(source, target)
    installer.chmod(0o755)
    artifacts = [archive_path, installer]
    if args.deb:
        deb = output/f'ratiolab_{version}_{"amd64" if arch == "x86_64" else "arm64"}.deb'
        make_deb(bundle, deb, version, 'amd64' if arch == 'x86_64' else 'arm64', glibc)
        artifacts.append(deb)
    checksums = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in artifacts}
    (output/(stem+'.sha256')).write_text(''.join(f'{digest}  {name}\n' for name,digest in checksums.items()))
    print(json.dumps(dict(artifacts=checksums, min_glibc=glibc), indent=2))


if __name__ == '__main__':
    main()
