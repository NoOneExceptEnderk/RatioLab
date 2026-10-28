"""Executed by PyInstaller before GI and the application are imported.

Paths refer only to the bundle. No MSYS2/Homebrew/GTK installation on the target
is needed. User preferences, caches and temporary pixbuf caches stay writable.
"""
import os
from pathlib import Path
import sys

if getattr(sys, 'frozen', False):
    root = Path(sys._MEIPASS)
    # Keep the pre-hook values for external CAD/folder launches. This is a
    # Python snapshot, not an environment mutation shared with other threads.
    names = ('PATH', 'GI_TYPELIB_PATH', 'GSETTINGS_SCHEMA_DIR', 'XDG_DATA_DIRS', 'PYGI_DLL_PATH',
             'GTK_DATA_PREFIX', 'GTK_EXE_PREFIX', 'GTK_PATH', 'GTK_IM_MODULE_FILE',
             'PANGO_LIBDIR', 'PANGO_SYSCONFDIR', 'FONTCONFIG_FILE', 'FONTCONFIG_PATH',
             'GIO_EXTRA_MODULES', 'GIO_MODULE_DIR', 'GDK_PIXBUF_MODULE_FILE', 'GDK_PIXBUF_MODULEDIR',
             'DYLD_LIBRARY_PATH', 'DYLD_FALLBACK_LIBRARY_PATH', 'DYLD_FRAMEWORK_PATH')
    sys._ratiolab_original_environment = {name: os.environ.get(name) for name in names}
    os.environ['GI_TYPELIB_PATH'] = str(root/'gi_typelibs')
    os.environ['GSETTINGS_SCHEMA_DIR'] = str(root/'share/glib-2.0/schemas')
    os.environ['XDG_DATA_DIRS'] = str(root/'share')
    os.environ['GTK_DATA_PREFIX'] = str(root)
    os.environ['GTK_EXE_PREFIX'] = str(root)
    os.environ['GTK_PATH'] = str(root)
    os.environ['PANGO_LIBDIR'] = str(root)
    os.environ['PANGO_SYSCONFDIR'] = str(root/'etc')
    os.environ['FONTCONFIG_FILE'] = str(root/'etc/fonts/fonts.conf')
    os.environ['FONTCONFIG_PATH'] = str(root/'etc/fonts')
    # Ignore third-party GTK/GIO plugin paths from a developer's environment;
    # they may refer to another ABI or a package manager absent on the target.
    os.environ['GTK_IM_MODULE_FILE'] = str(root/'etc/gtk-4.0/immodules.cache')
    os.environ['GIO_EXTRA_MODULES'] = str(root/'gio-modules')
    os.environ['GIO_MODULE_DIR'] = str(root/'gio-modules')
    if sys.platform == 'win32':
        os.environ['PYGI_DLL_PATH'] = str(root)
        if hasattr(os, 'add_dll_directory'):
            sys._ratiolab_dll_directory = os.add_dll_directory(str(root))
    # Local shared objects use PyInstaller's loader paths; the application also
    # opens libepoxy by absolute bundled filename, never from a system prefix.
