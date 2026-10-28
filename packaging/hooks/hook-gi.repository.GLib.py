"""Use upstream GI collection without copying every desktop schema on the host."""
from PyInstaller.compat import is_win
from PyInstaller.utils.hooks.gi import GiModuleInfo
from pathlib import Path


def hook(hook_api):
    info = GiModuleInfo('GLib', '2.0')
    if not info.available:
        raise RuntimeError('The build Python cannot load GLib')
    binaries, datas, hiddenimports = info.collect_typelib_data()
    hiddenimports += ['gi.repository.GLib'+('Win32' if is_win else 'Unix')]
    if is_win:
        binaries += [(str(path), '.') for path in Path(info.get_libdir()).glob('gspawn-*-helper*.exe')]
    hook_api.add_binaries(binaries)
    hook_api.add_datas(datas)
    hook_api.add_imports(*hiddenimports)
