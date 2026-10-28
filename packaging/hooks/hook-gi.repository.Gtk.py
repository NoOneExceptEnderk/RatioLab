# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""GTK4 typelibs and runtime data, using PyInstaller's supported GI helpers."""
from pathlib import Path
import sys
from PyInstaller.utils.hooks.gi import GiModuleInfo, collect_glib_share_files


def hook(hook_api):
    info = GiModuleInfo('Gtk', '4.0', hook_api=hook_api)
    if not info.available or info.version != '4.0':
        raise RuntimeError('The native build must provide GTK4, not GTK3')
    binaries, datas, hiddenimports = info.collect_typelib_data()
    if sys.platform == 'win32':
        # GTK's EGL backend loads ANGLE dynamically: no PE import edge lets
        # PyInstaller discover these two libraries automatically.
        for name in ('libEGL.dll', 'libGLESv2.dll'):
            source = Path(sys.base_prefix)/'bin'/name
            if not source.is_file():
                raise RuntimeError('Windows GTK rendering requires MSYS2 angleproject: '+name)
            binaries.append((str(source), '.'))
    datas += collect_glib_share_files('icons', 'Adwaita')
    # hicolor is a shared directory: browsers and other installed applications
    # place their own icons here. Only the fallback theme definition belongs in
    # our runtime; RatioLab supplies its application icon separately.
    datas += [(source, destination)
              for source, destination in collect_glib_share_files('icons', 'hicolor')
              if Path(source).name == 'index.theme'
              and Path(destination).as_posix() == 'share/icons/hicolor']
    schemas = collect_glib_share_files('glib-2.0', 'schemas')
    datas += [(source, destination) for source, destination in schemas
              if Path(source).name.startswith('org.gtk.gtk4.') and source.endswith('.gschema.xml')]
    if not any(source.endswith('.gschema.xml') for source, destination in datas):
        raise RuntimeError('GTK4 GSettings schema sources are missing from the native build')
    hook_api.add_binaries(binaries)
    hook_api.add_datas(datas)
    hook_api.add_imports(*hiddenimports)
