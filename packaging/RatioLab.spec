# Native PyInstaller build; invoked by scripts/build-bundle.py.
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(SPECPATH)))
from bundle_support import write_notices

root = Path(SPECPATH).parent
metadata = Path(os.environ['RATIOLAB_BUNDLE_METADATA'])
version = os.environ['RATIOLAB_VERSION']
datas = [(str(root/'packaging/fonts.conf'), 'etc/fonts')]
datas += [(str(path), 'share/fonts') for path in (root/'packaging/fonts').glob('*.ttf')]
a = Analysis(
    [str(root/'packaging/entrypoint.py')], pathex=[str(root)],
    binaries=[], datas=datas,
    hiddenimports=['app', 'ratiolab_checks', 'ratiolab_resources', 'cairo', 'gi._gi_cairo',
                   'gi.repository.Gtk', 'gi.repository.Gdk', 'gi.repository.Gio',
                   'gi.repository.GLib', 'gi.repository.GObject'],
    hookspath=[str(root/'packaging/hooks')],
    hooksconfig={'gi': {'module-versions': {'Gtk': '4.0', 'Gdk': '4.0'},
                       'icons': ['Adwaita', 'hicolor'], 'themes': [], 'languages': []}},
    runtime_hooks=[str(root/'packaging/runtime.py')],
    excludes=['tkinter', 'matplotlib', 'numpy', 'PIL', 'IPython', 'pytest'],
    noarchive=False,
)
for source, destination in write_notices(a.binaries, metadata, datas=a.datas):
    a.datas.append((destination, str(source), 'DATA'))
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name='RatioLab', debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=(sys.platform != 'win32' and sys.platform != 'darwin'),
    disable_windowed_traceback=False, contents_directory='_internal',
    icon=str(root/'packaging/icons/RatioLab.ico') if sys.platform == 'win32' else None,
    target_arch=None,
    codesign_identity=os.environ.get('RATIOLAB_CODESIGN_IDENTITY') or None,
    entitlements_file=os.environ.get('RATIOLAB_ENTITLEMENTS') or None,
)
collection = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='RatioLab')
if sys.platform == 'darwin':
    app = BUNDLE(
        collection, name='RatioLab.app', icon=str(root/'packaging/icons/RatioLab.icns'),
        bundle_identifier='local.solidcraft.reducers', version=version,
        info_plist={'CFBundleShortVersionString': version, 'CFBundleVersion': version,
                    'NSHighResolutionCapable': True,
                    'NSSupportsAutomaticGraphicsSwitching': True,
                    'LSMinimumSystemVersion': os.environ.get('MACOSX_DEPLOYMENT_TARGET', '15.0'),
                    'NSHumanReadableCopyright': 'Third-party license notices are included in the application bundle.'},
    )
