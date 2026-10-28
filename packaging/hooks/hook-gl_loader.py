# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""ctypes cannot discover libepoxy's computed library name automatically."""
import ctypes.util
import sys
from PyInstaller.depend.bindepend import resolve_library_path

names = ['epoxy']
if sys.platform.startswith('linux'):
    # GLVND dispatch libraries are redistributable loaders, not GPU drivers.
    # Driver implementations (Mesa DRI/NVIDIA/AMD) remain supplied by the OS.
    names += ['GL', 'GLX', 'GLdispatch', 'EGL']
binaries = []
for name in names:
    candidate = ctypes.util.find_library(name)
    if not candidate and name == 'epoxy' and sys.platform == 'win32':
        candidate = 'libepoxy-0.dll'
    path = resolve_library_path(candidate) if candidate else None
    if not path:
        if name == 'epoxy':
            raise RuntimeError('Cannot locate native libepoxy for the bundle')
        continue
    binaries.append((path, '.'))
