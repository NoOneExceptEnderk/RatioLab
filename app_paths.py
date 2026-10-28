"""Immutable application resources and writable, per-user RatioLab data.

This module deliberately needs no GTK, so installers and diagnostics can use it.
"""
import json
import os
from pathlib import Path
import sys
import tempfile

APP_ID = 'local.solidcraft.reducers'
MIN_GTK = (4, 12, 0)
SOURCE_ROOT = Path(__file__).resolve().parent
_dll_directories = []


def bundle_dir():
    """PyInstaller's immutable runtime root, including macOS bundle symlinks."""
    root = getattr(sys, '_MEIPASS', None)
    return Path(root) if getattr(sys, 'frozen', False) and root else None


def require_gtk_version(gtk):
    error = gtk.check_version(*MIN_GTK)
    if error is not None:
        raise RuntimeError(f'RatioLab requires GTK 4.12 or newer: {error}')


def _absolute_env(name, fallback):
    value = os.environ.get(name)
    path = Path(value).expanduser() if value else Path(fallback)
    return path if path.is_absolute() else Path(fallback)


def config_dir():
    if sys.platform == 'win32':
        return _absolute_env('APPDATA', Path.home()/'AppData/Roaming')/'RatioLab'
    if sys.platform == 'darwin':
        return Path.home()/'Library/Application Support/RatioLab'
    return _absolute_env('XDG_CONFIG_HOME', Path.home()/'.config')/'ratiolab'


def data_dir():
    if sys.platform == 'win32':
        return _absolute_env('LOCALAPPDATA', Path.home()/'AppData/Local')/'RatioLab'
    if sys.platform == 'darwin':
        return Path.home()/'Library/Application Support/RatioLab'
    return _absolute_env('XDG_DATA_HOME', Path.home()/'.local/share')/'ratiolab'


def default_output_dir():
    return data_dir()/'exports'


def resource_path(relative):
    """Resolve a bundled resource without consulting the working directory."""
    from ratiolab_resources import root
    relative = Path(relative)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Resource paths must stay inside the resource directory')
    path = root()/relative
    if (not path.exists() and relative.as_posix() in
            ('catalogo-cuscinetti.json', 'catalogo-hardware.json', 'INSTALL.md')):
        path = SOURCE_ROOT/relative
    if not path.is_file() and not path.is_dir():
        raise FileNotFoundError(f'RatioLab resource missing: {relative}')
    return path


def load_preferences(legacy_root=None):
    path = config_dir()/'preferenze-ui.json'
    # Only the source checkout can supply old preferences. Distributions never
    # include them, and a present (even invalid) new file takes precedence.
    if not path.exists() and legacy_root is not None:
        path = Path(legacy_root)/'preferenze-ui.json'
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def saved_output_dir(legacy_root=None):
    value = load_preferences(legacy_root).get('output_dir')
    try:
        path = Path(value)
        if path.is_absolute():
            return path
    except (TypeError, ValueError):
        pass
    return default_output_dir()


def save_preferences(*, legacy_root=None, **changes):
    data = load_preferences(legacy_root)
    data.pop('mode', None)
    data.update(changes)
    folder = config_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder/'preferenze-ui.json'
    # A same-directory atomic replacement leaves the previous preference intact
    # if writing fails or the app closes during a write.
    fd, temporary = tempfile.mkstemp(prefix='.preferences-', dir=folder)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def prepare_native_runtime():
    """Use bundled Windows DLLs, or the selected MSYS2 development runtime."""
    if sys.platform != 'win32' or _dll_directories:
        return
    bundled = bundle_dir()
    folders = ([bundled, bundled/'bin', bundled/'lib'] if bundled else
               [Path(sys.base_prefix)/'bin', Path(sys.executable).parent])
    existing = [str(path) for path in folders if path.is_dir()]
    configured = [] if bundled else os.environ.get('PYGI_DLL_PATH', '').split(';')
    os.environ['PYGI_DLL_PATH'] = ';'.join(dict.fromkeys(p for p in configured+existing if p))
    if hasattr(os, 'add_dll_directory'):
        for path in dict.fromkeys(existing):
            _dll_directories.append(os.add_dll_directory(path))
