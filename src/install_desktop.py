#!/usr/bin/python3
# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Register RatioLab's launcher with the current user's Linux desktop."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

from app_paths import APP_ID, resource_path


ROOT = Path(__file__).resolve().parent


def desktop_directory():
    if shutil.which('xdg-user-dir'):
        result = subprocess.run(['xdg-user-dir', 'DESKTOP'], capture_output=True,
                                text=True, timeout=3, check=True)
        path = Path(result.stdout.strip())
        if path.is_absolute() and path != Path.home():
            return path
    return None


def launcher():
    app_id = APP_ID
    # Desktop Exec uses double quotes, not shell-style single-quote escaping.
    if getattr(sys, 'frozen', False):
        arguments = [sys.executable]
    else:
        arguments = [sys.executable, str(ROOT/'app.py')] if (ROOT.parent/'launch.sh').is_file() and ROOT.name == 'src' else [sys.executable, '-m', 'ratiolab_cli']
    def quote(argument):
        for character in ('\\', '"', '`', '$'):
            argument = argument.replace(character, '\\'+character)
        return '"'+argument.replace('%', '%%')+'"'
    command = ' '.join(quote(argument) for argument in arguments)
    return app_id, '\n'.join([
        '[Desktop Entry]',
        'Type=Application',
        'Name=RatioLab',
        'Comment=Parametric gear and reducer generator',
        'Comment[it]=Generatore parametrico di ingranaggi e riduttori',
        f'Exec={command}',
        f'Icon={resource_path("branding/ratiolab-icon.png")}',
        'Terminal=false',
        'StartupNotify=true',
        f'StartupWMClass={app_id}',
        'Categories=Graphics;Engineering;',
        '',
    ])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='Show changes without installing')
    args = parser.parse_args(argv)
    if not sys.platform.startswith('linux'):
        parser.error('Desktop registration is available on Linux only. Use ratiolab to launch the app.')
    app_id, contents = launcher()
    data_home = Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share')))
    applications = data_home/'applications'
    # GNOME matches a window's application ID against this filename.
    targets = [applications/f'{app_id}.desktop']
    desktop = desktop_directory()
    if desktop is not None and desktop.is_dir():
        targets.append(desktop/'RatioLab.desktop')
    if args.dry_run:
        print('\n'.join(map(str, targets)))
        print(contents)
        return
    applications.mkdir(parents=True, exist_ok=True)
    for target in targets:
        target.write_text(contents, encoding='utf-8')
        target.chmod(0o755 if target.parent == desktop else 0o644)
        print('Installed:', target)
    if shutil.which('update-desktop-database'):
        subprocess.run(['update-desktop-database', str(applications)], check=True, timeout=10)
    if desktop is not None and len(targets) > 1 and shutil.which('gio'):
        result = subprocess.run(['gio', 'set', str(targets[-1]), 'metadata::trusted', 'true'],
                                capture_output=True, text=True, timeout=3)
        if result.returncode:
            print('Desktop trust metadata unavailable:', result.stderr.strip())


if __name__ == '__main__':
    main()
