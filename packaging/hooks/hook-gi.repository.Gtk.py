"""GTK4 typelibs and runtime data, using PyInstaller's supported GI helpers."""
from pathlib import Path
from PyInstaller.utils.hooks.gi import GiModuleInfo, collect_glib_share_files


def hook(hook_api):
    info = GiModuleInfo('Gtk', '4.0', hook_api=hook_api)
    if not info.available or info.version != '4.0':
        raise RuntimeError('The native build must provide GTK4, not GTK3')
    binaries, datas, hiddenimports = info.collect_typelib_data()
    for theme in ('Adwaita', 'hicolor'):
        datas += collect_glib_share_files('icons', theme)
    schemas = collect_glib_share_files('glib-2.0', 'schemas')
    datas += [(source, destination) for source, destination in schemas
              if Path(source).name.startswith('org.gtk.gtk4.') and source.endswith('.gschema.xml')]
    if not any(source.endswith('.gschema.xml') for source, destination in datas):
        raise RuntimeError('GTK4 GSettings schema sources are missing from the native build')
    hook_api.add_binaries(binaries)
    hook_api.add_datas(datas)
    hook_api.add_imports(*hiddenimports)
