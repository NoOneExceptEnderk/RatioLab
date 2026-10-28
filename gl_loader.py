"""Typed access to libepoxy's current-context OpenGL dispatch pointers.

GTK itself uses libepoxy. Its dispatch handles EGL, GLX, WGL and macOS; opening
libGL directly would bind the wrong API on some backends. Call only after the
Gtk.GLArea context has been made current. The exported epoxy_gl* symbols are
pointer VARIABLES, not functions; calling their symbol address would crash.
"""
import ctypes as C
import ctypes.util
import os
from pathlib import Path
import sys

from app_paths import bundle_dir, prepare_native_runtime


def library_candidates():
    bundled = bundle_dir()
    if bundled is not None:
        name = ('libepoxy-0.dll' if sys.platform == 'win32' else
                'libepoxy.0.dylib' if sys.platform == 'darwin' else 'libepoxy.so.0')
        for folder in (bundled, bundled/'lib', bundled/'bin'):
            yield str(folder/name)
        return
    found = ctypes.util.find_library('epoxy')
    if found:
        yield found
    if sys.platform == 'win32':
        for folder in (Path(sys.base_prefix)/'bin', Path(sys.executable).parent):
            yield str(folder/'libepoxy-0.dll')
        yield 'libepoxy-0.dll'
    elif sys.platform == 'darwin':
        for folder in (Path(sys.base_prefix)/'lib', Path('/opt/homebrew/lib'), Path('/usr/local/lib')):
            yield str(folder/'libepoxy.0.dylib')
        yield 'libepoxy.0.dylib'
    else:
        yield 'libepoxy.so.0'


def load_epoxy():
    prepare_native_runtime()
    failures = []
    for candidate in dict.fromkeys(library_candidates()):
        try:
            return C.CDLL(candidate)
        except OSError as error:
            failures.append(str(error))
    raise RuntimeError('OpenGL loader libepoxy is unavailable. Install the GTK 4 '
                       'native dependencies for this Python. '+ '; '.join(failures))


def bind_function(library, name, restype, argtypes):
    try:
        address = C.c_void_p.in_dll(library, 'epoxy_gl'+name).value
    except ValueError as error:
        raise RuntimeError(f'OpenGL entry point unavailable: gl{name}') from error
    if address in (None, 0, 1, 2, 3, C.c_void_p(-1).value):
        raise RuntimeError(f'OpenGL entry point is invalid: gl{name}')
    factory = C.WINFUNCTYPE if os.name == 'nt' else C.CFUNCTYPE
    function = factory(restype, *argtypes)(address)
    function._library = library  # Keep the DLL loaded for the function's lifetime.
    return function
