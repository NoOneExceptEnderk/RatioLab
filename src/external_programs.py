# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Launch system programs without exporting the frozen app's private GTK runtime.

PyInstaller documents restoring LD_LIBRARY_PATH_ORIG on Unix, filtering bundle
paths on macOS/Windows, and resetting Windows' inherited SetDllDirectory value.
Only child environments/Gio contexts change. The one process-wide Windows API
is protected by a lock and restored immediately, including when launch fails.
"""
from contextlib import contextmanager
import ctypes
import os
from pathlib import Path
import sys
import threading
import shutil
import subprocess

_dll_lock = threading.RLock()
RUNTIME_VARIABLES = (
    'GI_TYPELIB_PATH', 'GSETTINGS_SCHEMA_DIR', 'XDG_DATA_DIRS', 'PYGI_DLL_PATH',
    'GTK_DATA_PREFIX', 'GTK_EXE_PREFIX', 'GTK_PATH', 'GTK_IM_MODULE_FILE',
    'PANGO_LIBDIR', 'PANGO_SYSCONFDIR', 'FONTCONFIG_FILE', 'FONTCONFIG_PATH',
    'GIO_EXTRA_MODULES', 'GIO_MODULE_DIR', 'GDK_PIXBUF_MODULE_FILE', 'GDK_PIXBUF_MODULEDIR',
    'DYLD_LIBRARY_PATH', 'DYLD_FALLBACK_LIBRARY_PATH', 'DYLD_FRAMEWORK_PATH',
)


def _bundled_path(value):
    root = Path(sys._MEIPASS).resolve()
    if sys.platform == 'darwin':
        root = root.parent  # Both .app/Contents/Frameworks and Resources.
    try:
        return Path(value).resolve().is_relative_to(root)
    except (OSError, ValueError):
        return False


def _without_bundle_paths(value):
    separator = ';' if sys.platform == 'win32' else os.pathsep
    return separator.join(part for part in value.split(separator) if not part or not _bundled_path(part))


def child_environment(environ=None):
    """Copy and sanitize only the environment to be passed to an external child."""
    environment = dict(os.environ if environ is None else environ)
    if not getattr(sys, 'frozen', False) or not hasattr(sys, '_MEIPASS'):
        return environment
    original = getattr(sys, '_ratiolab_original_environment', {})
    for key in RUNTIME_VARIABLES:
        if key in original:
            value = original[key]
            if value is None:
                environment.pop(key, None)
            else:
                environment[key] = _without_bundle_paths(value)
        elif key in environment:
            cleaned = _without_bundle_paths(environment[key])
            if cleaned:
                environment[key] = cleaned
            else:
                environment.pop(key, None)
    if 'LD_LIBRARY_PATH_ORIG' in environment:
        environment['LD_LIBRARY_PATH'] = environment['LD_LIBRARY_PATH_ORIG']
    else:
        environment.pop('LD_LIBRARY_PATH', None)
    path = environment.get('PATH_ORIG', original.get('PATH', environment.get('PATH')))
    if path is not None:
        environment['PATH'] = _without_bundle_paths(path)
    return environment


def configure_launch_context(context):
    """Apply child-only differences without disturbing GTK's current process."""
    environment = child_environment()
    for key in set(os.environ) | set(environment):
        if os.environ.get(key) == environment.get(key):
            continue
        if key in environment:
            context.setenv(key, environment[key])
        else:
            context.unsetenv(key)
    return context


def launch_uri(uri, context):
    """Use the system desktop's handlers, outside the private XDG data tree."""
    if sys.platform.startswith('linux') and getattr(sys, 'frozen', False):
        # Gio resolves .desktop files in the parent process before applying an
        # AppLaunchContext. The isolated bundle XDG_DATA_DIRS has no such files.
        environment = child_environment()
        opener = shutil.which('xdg-open', path=environment.get('PATH', os.defpath))
        if opener is None:
            raise RuntimeError('The desktop needs xdg-open (xdg-utils) to open links or folders.')
        return subprocess.Popen([opener, str(uri)], env=environment,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                start_new_session=True)
    from gi.repository import Gio
    with system_library_search():
        return Gio.AppInfo.launch_default_for_uri(str(uri), configure_launch_context(context))


def open_folder(folder, context):
    return launch_uri(Path(folder).as_uri(), context)


def _kernel32():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetDllDirectoryW.argtypes = [ctypes.c_ulong, ctypes.c_wchar_p]
    kernel.GetDllDirectoryW.restype = ctypes.c_ulong
    kernel.SetDllDirectoryW.argtypes = [ctypes.c_wchar_p]
    kernel.SetDllDirectoryW.restype = ctypes.c_int
    return kernel


@contextmanager
def system_library_search():
    """Temporarily reset only Windows' inherited DLL directory for a spawn."""
    if sys.platform != 'win32' or not getattr(sys, 'frozen', False):
        yield
        return
    with _dll_lock:
        kernel = _kernel32()
        length = kernel.GetDllDirectoryW(0, None)
        previous = None
        if length:
            buffer = ctypes.create_unicode_buffer(length+1)
            copied = kernel.GetDllDirectoryW(len(buffer), buffer)
            if not copied or copied >= len(buffer):
                raise ctypes.WinError(ctypes.get_last_error())
            previous = buffer.value
        if not kernel.SetDllDirectoryW(None):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            yield
        finally:
            if not kernel.SetDllDirectoryW(previous):
                raise ctypes.WinError(ctypes.get_last_error())
