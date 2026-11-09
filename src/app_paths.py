# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Immutable application resources and writable, per-user RatioLab data.

This module deliberately needs no GTK, so installers and diagnostics can use it.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
from copy import deepcopy
from theme_preferences import defaults as theme_defaults, normalize as normalize_theme

APP_ID = 'local.solidcraft.reducers'
MIN_GTK = (4, 12, 0)
PREFERENCES_FILENAME = 'ui-preferences.json'
LEGACY_PREFERENCES_FILENAME = 'preferenze-ui.json'
UI_DEFAULTS = dict(theme='dark', language='en', text_scale=1, hover_help=True,
                   zoom_speed=1, rotation_speed=1, invert_zoom=False, mouse_navigation='ratiolab',
                   theme_customizations=theme_defaults())


def ui_preferences(data):
    """Validate global UI choices without changing model or unknown preferences."""
    result = deepcopy(UI_DEFAULTS)
    if not isinstance(data, dict):
        return result
    for key, default in result.items():
        value = data.get(key, default)
        if key == 'theme_customizations':
            result[key] = normalize_theme(value)
            continue
        elif key == 'theme':
            valid = isinstance(value, str) and value in ('dark', 'light')
        elif key == 'language':
            valid = isinstance(value, str) and value in ('en','it','es','fr','de','pt','ru','zh-CN','ta')
        elif key == 'mouse_navigation':
            from mouse_navigation import PROFILES
            valid = isinstance(value, str) and value in PROFILES
        elif type(default) is bool:
            valid = type(value) is bool
        else:
            valid = type(value) in (int, float) and value in (
                (1, 1.25, 1.5) if key == 'text_scale' else (.5, 1, 2))
        if valid:
            result[key] = value
    return result
MODULE_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = (MODULE_ROOT.parent
               if MODULE_ROOT.name == 'src' and (MODULE_ROOT.parent/'pyproject.toml').is_file()
               else MODULE_ROOT)
_dll_directories = []


def prepare_application_identity():
    """Match Windows taskbar grouping to the installed RatioLab shortcuts."""
    if sys.platform != 'win32':
        return
    import ctypes
    import logging
    try:
        identify = ctypes.WinDLL('shell32').SetCurrentProcessExplicitAppUserModelID
        identify.argtypes = [ctypes.c_wchar_p]
        identify.restype = ctypes.c_long
        result = identify(APP_ID)
        if result < 0:
            raise OSError(f'Windows rejected the application identity ({result})')
    except OSError as error:
        logging.getLogger(__name__).warning('Could not set RatioLab taskbar identity: %s', error)


def bundle_dir():
    """PyInstaller's immutable runtime root, including macOS bundle symlinks."""
    root = getattr(sys, '_MEIPASS', None)
    return Path(root) if getattr(sys, 'frozen', False) and root else None


def require_gtk_version(gtk):
    error = gtk.check_version(*MIN_GTK)
    if error is not None:
        raise RuntimeError(f'RatioLab requires GTK 4.12 or newer: {error}')


def configure_gtk_text(gtk):
    """Keep Linux font pixels consistent with GTK's partial redraw bounds.

    GTK 4.22 automatic rendering can rasterize DejaVu dots above the declared
    ink rectangle, leaving pixels from an old label after a text change.
    Keep unhinted outlines, as in automatic mode, but use pixel-aligned metrics.
    These overrides are local to RatioLab and require GTK's 4.16 rendering API.
    """
    if not sys.platform.startswith('linux'):
        return
    settings = gtk.Settings.get_default()
    if settings is not None and settings.find_property('gtk-font-rendering'):
        settings.set_property('gtk-font-rendering', gtk.FontRendering.MANUAL)
        settings.set_property('gtk-xft-hintstyle', 'hintnone')
        settings.set_property('gtk-hint-font-metrics', True)


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
    source_documents = {
        'INSTALL.md': 'docs/installation.md',
        'MCP.md': 'docs/mcp.md',
        'CHANGELOG.md': 'CHANGELOG.md',
        'LICENSE': 'LICENSE',
        'COPYRIGHT': 'COPYRIGHT',
    }
    if not path.exists() and relative.as_posix() in source_documents:
        path = SOURCE_ROOT/source_documents[relative.as_posix()]
    if not path.is_file() and not path.is_dir():
        raise FileNotFoundError(f'RatioLab resource missing: {relative}')
    return path


def load_preferences(legacy_root=None):
    path = config_dir()/PREFERENCES_FILENAME
    # Read an earlier installation before consulting a legacy source checkout.
    # A present but invalid new file still takes precedence; otherwise stale
    # settings could silently reappear after a user intentionally resets them.
    if not path.exists():
        previous = config_dir()/LEGACY_PREFERENCES_FILENAME
        if previous.exists():
            path = previous
        elif legacy_root is not None:
            path = Path(legacy_root)/LEGACY_PREFERENCES_FILENAME
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
    target = folder/PREFERENCES_FILENAME
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
