# Developing and building RatioLab

For normal installation, use the [bundled installers](installation.md).
This page is for contributors and maintainers.

## Work on a checkout

Install the native GTK/Python bindings for your OS as described below, then
create a development environment using that same interpreter. Linux example:

```sh
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -e .
.venv/bin/ratiolab --diagnose
.venv/bin/ratiolab
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
```

`src/` contains application modules and runtime resources. `tests/` contains
automated checks; tests are part of the source distribution and are excluded
from the installed wheel and native application. GUI checks need a working
desktop/GL context; Linux CI uses Xvfb and Mesa.

For a quick source launch use `./launch.sh`. A headless source command from
the repository root can use `PYTHONPATH=src python3 -m ratiolab_cli --diagnose`.
On PowerShell, set `$env:PYTHONPATH = "src"` before the corresponding command.
The editable installation above avoids that extra environment setting.

## Building the native installers

These commands are for the **build machine**. They are not required on a
computer receiving the installer. Each OS is built natively; Linux does not
cross-compile Windows Setup or a macOS application.

The shared build is `scripts/build-bundle.py`, with
`packaging/RatioLab.spec` and project hooks using PyInstaller's official GI
helpers configured for Gtk/Gdk 4.0. It creates an **onedir** application, avoiding
a temporary unpacked GTK runtime at every launch. Native libraries and code are
separate files and third-party notices remain accessible. GPU drivers are not
bundled. The build fails if a collected native file has no package attribution
or its required license documents cannot be collected.

Build on Ubuntu 24.04 to retain the glibc 2.39 baseline:

```sh
sudo apt install python3-venv libpython3.12 python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-girepository-2.0 libepoxy0 libgl1 libegl1 binutils dpkg-dev
/usr/bin/python3 -m venv --system-site-packages .bundle-env
.bundle-env/bin/python -m pip install -r packaging/requirements-build.txt
.bundle-env/bin/python scripts/build-bundle.py
.bundle-env/bin/python scripts/package-linux.py --bundle dist/bundles/linux-x86_64/RatioLab --deb
```

The shared `libpython3.12` package is required by PyInstaller in addition to the
Python interpreter/venv package. `gir1.2-girepository-2.0` supplies the build-time
introspection namespace used by PyInstaller's hooks. Use `--gui` with `build-bundle.py` on a desktop
to require actual GL rendering and full workspace exports. In CI, Xvfb and Mesa
provide this check on the Ubuntu 24.04 runner, with explicit Mesa DRI/GLX/EGL
and fontconfig packages for repeatable headless rendering.

On Windows, use the **MSYS2 UCRT64 build environment** and its native PyInstaller
package (not python.org Python or a PyPI PyInstaller wheel):

```sh
pacman -S --needed mingw-w64-ucrt-x86_64-python mingw-w64-ucrt-x86_64-pyinstaller mingw-w64-ucrt-x86_64-gtk4 mingw-w64-ucrt-x86_64-python-gobject mingw-w64-ucrt-x86_64-python-cairo mingw-w64-ucrt-x86_64-libepoxy mingw-w64-ucrt-x86_64-angleproject
export PYGI_DLL_PATH="$(cygpath -w /ucrt64/bin)"
/ucrt64/bin/python.exe scripts/build-bundle.py
```

Install Inno Setup 6.3+ on the Windows build machine. From PowerShell in this
source folder run `./scripts/package-windows.ps1`. It verifies the native
bundle hashes and executes a frozen self-test without MSYS2 on PATH before
compiling `scripts/package-windows.iss`. Setup installs under
`%LOCALAPPDATA%/Programs/RatioLab` with per-user shortcuts and an uninstaller.
An optional `-CertificateThumbprint` selects an existing code-signing
certificate in the maintainer's CurrentUser/My certificate store to sign the
**installer**; by default it remains unsigned.

MSYS2 file ownership is read once from its installed-file inventory. For the
specific package versions that omit license texts, verified upstream notices
are kept in `packaging/notices/msys2/registry.json` and adjacent text files.
The build checks their versions, license declarations and file hashes. A new
dependency version requires reviewing its exact source archive and updating
the registry; an unrecognized version or changed notice remains a build error.

On macOS 15+, select a Homebrew Python matching the installed GI bindings:

```sh
brew install pygobject3 gtk4 gobject-introspection
. scripts/macos-python.sh
python=$(choose_macos_python)
"$python" -m venv --system-site-packages .bundle-env
.bundle-env/bin/python -m pip install -r packaging/requirements-build.txt
MACOSX_DEPLOYMENT_TARGET=15.0 .bundle-env/bin/python scripts/build-bundle.py
RATIOLAB_BUILD_PYTHON="$PWD/.bundle-env/bin/python" sh scripts/package-macos.sh
```

Build separately on Intel and Apple Silicon. PyInstaller constructs a real
`RatioLab.app`, rewrites the native library paths and signs its code ad hoc when
no identity is provided. The builder checks the minimum OS load commands of all
included Mach-O binaries against `LSMinimumSystemVersion`. The DMG packager
verifies the app signature, creates the Applications shortcut and uses
`hdiutil` to produce the compressed image. It does not change the signed app.

To use an existing Developer ID identity, set `RATIOLAB_CODESIGN_IDENTITY` for
**both** the bundle build and DMG packaging. PyInstaller handles the app's
signing order. `RATIOLAB_ENTITLEMENTS` may point to an existing entitlements file
if that identity/build needs one. To submit the finished DMG to Apple's notary
service, set `RATIOLAB_NOTARY_PROFILE` to an existing `notarytool` keychain
profile when running the packager; it submits, waits, staples and validates the
ticket. These options require the maintainer's actual credentials and were not
run here.

Outputs are under `dist/bundles/<system>-<arch>/RatioLab` on Linux/Windows and
`dist/bundles/macos-<arch>/RatioLab.app` on macOS. Final installers and SHA-256
checksums go to `dist/installers/`. Every runtime has a `bundle-manifest.json`
containing version, architecture, OS baseline and file hashes. The manifest is
inside the onedir folder on Linux/Windows and beside the signed app on macOS.
License notices and `components.json` are inside `_internal/notices` or the
macOS app's Resources/notices directory.

The builder's default self-test runs the frozen executable from a neutral
directory with Python/GTK environment paths removed and no MSYS2/Homebrew on
PATH. It checks local typelibs, all nine families, STL/STEP, UTF-8 configurations
and preferences in a temporary user profile. `--gui` also verifies nonblank
pixels and complete workspace exports. To repeat on a built folder:

```sh
python scripts/build-bundle.py --verify-only /path/to/RatioLab --gui
```

For a windowed executable, use `RatioLab.exe --self-test --report report.json`
or the app bundle's `Contents/MacOS/RatioLab` executable. The JSON report and
exit status are usable even with no console. Normal windowed launches write
Python errors to the user's RatioLab data directory under `logs/ratiolab.log`.

`.github/workflows/installers.yml` builds Linux x86-64, Windows x86-64 and both
macOS architectures on their native runners. It creates real installers and
tests their installed/copied applications with package-manager runtime paths
removed. Linux GUI/GL is mandatory; Windows/macOS GUI checks are always
attempted, with explicit lack of runner graphics capability reported separately.
Use `native_gui=true` to require that capability as well. The
workflow uploads build artifacts; publication is a separate maintainer step.
the [completed workflow runs](https://github.com/NoOneExceptEnderk/RatioLab/actions) records completed native runs and the checks actually performed.

Build configuration follows [PyInstaller's GI hook settings](https://pyinstaller.org/en/stable/hooks-config.html),
[PyInstaller's external program guidance](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#launching-external-programs-from-the-frozen-application),
[PyInstaller's macOS signing and bundles](https://pyinstaller.org/en/stable/feature-notes.html),
[MSYS2's native PyInstaller package](https://packages.msys2.org/packages/mingw-w64-ucrt-x86_64-pyinstaller),
[Inno Setup's per-user installation mode](https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm)
and [Apple's distribution signing documentation](https://developer.apple.com/documentation/xcode/creating-distribution-signed-code-for-the-mac/).

## Source and wheel installation (development)

RatioLab 0.1 is a Python/GTK 4 desktop application. Its Python wheel and source
archive can be installed on another computer; GTK, PyGObject, Cairo and libepoxy
come from that computer's native package manager. The wheel is **not** a
self-contained Windows installer, macOS application bundle or Linux AppImage.
An Internet connection is needed to install dependencies, not to generate or
export models.

Required: Python 3.10 or newer, **GTK 4.12 or newer**, PyGObject, Pycairo, libepoxy and a graphics
driver providing **desktop OpenGL 3.3+** or **OpenGL ES 3.0+**. GTK negotiates
an available API; Windows includes ANGLE as a GLES backend. The same Python must load the
native bindings and run RatioLab. A virtual environment uses
`--system-site-packages` so it can see those bindings. The wheel's `py3-none-any`
tag describes its Python code and resources, not the native runtime.

### Linux source/wheel

On Debian 13+/Ubuntu 24.04+ (with GTK >=4.12), install native packages:

```sh
sudo apt update
sudo apt install python3 python3-venv python3-pip python3-gi python3-gi-cairo gir1.2-gtk-4.0 libepoxy0
```

On Fedora use `sudo dnf install python3 python3-pip python3-gobject gtk4 libepoxy`;
on Arch use `sudo pacman -S python python-pip python-gobject python-cairo gtk4 libepoxy`.
Use the distribution's Python, rather than a separate pyenv/Conda interpreter.
The default GTK packages on Debian 12/Ubuntu 22.04 are too old. The runtime
diagnostic stops with the required version instead of failing during UI setup.

From an unpacked source archive or this checkout:

```sh
sh scripts/install-linux.sh
```

This creates a user virtual environment under
`~/.local/share/ratiolab/venv`, installs RatioLab, checks its runtime and registers
the Linux application menu/desktop launcher. Choose another location with
`RATIOLAB_VENV=/absolute/path sh scripts/install-linux.sh`. Choose the native
Python with `RATIOLAB_PYTHON=/usr/bin/python3` if needed. The registration keeps
`local.solidcraft.reducers`, so it matches existing GTK window grouping.

To install a wheel instead (replace the example wheel path):

```sh
/usr/bin/python3 -m venv --system-site-packages "$HOME/.local/share/ratiolab/venv"
"$HOME/.local/share/ratiolab/venv/bin/python" -m pip install --no-deps /path/to/ratiolab-0.1.0-py3-none-any.whl
"$HOME/.local/share/ratiolab/venv/bin/ratiolab" --diagnose
"$HOME/.local/share/ratiolab/venv/bin/ratiolab-install-desktop"
```

### Windows source/wheel (x86-64, MSYS2 UCRT64)

Install [MSYS2](https://www.msys2.org/) using its x86-64 installer. Open **MSYS2
UCRT64** from the Start menu, run `pacman -Syu`, and follow any request to close,
reopen and update the terminal again. Then install one coherent native runtime:

```sh
pacman -S --needed mingw-w64-ucrt-x86_64-python mingw-w64-ucrt-x86_64-python-pip mingw-w64-ucrt-x86_64-python-setuptools mingw-w64-ucrt-x86_64-python-wheel mingw-w64-ucrt-x86_64-gtk4 mingw-w64-ucrt-x86_64-python-gobject mingw-w64-ucrt-x86_64-python-cairo mingw-w64-ucrt-x86_64-libepoxy mingw-w64-ucrt-x86_64-angleproject
```

Unpack the RatioLab source archive in a folder you own, navigate there in that
UCRT64 terminal (`cd /c/Users/YourName/Downloads/ratiolab-0.1.0` for example), then:

```sh
bash scripts/install-windows-msys2.sh
"$HOME/.local/share/ratiolab/venv/bin/python.exe" -m ratiolab_cli --diagnose-gui
"$HOME/.local/share/ratiolab/venv/bin/python.exe" -m ratiolab_cli
```

MSYS2's Python has `bin` inside its virtual environments. It is a separate build
from python.org/Windows Store Python; their compiled extension modules are
incompatible. Always use `/ucrt64/bin/python.exe` to create this environment and
its `bin/python.exe` to run/install RatioLab. Do not combine python.org pip with
MSYS2's GTK bindings. Keep the MSYS2 runtime installed; this is a source/wheel
installation, not a portable executable.

For a wheel, create the same environment with
`/ucrt64/bin/python.exe -m venv --system-site-packages "$HOME/.local/share/ratiolab/venv"`,
then run its `bin/python.exe -m pip install --no-deps /c/path/to/ratiolab-0.1.0-py3-none-any.whl`.
Run from the UCRT64 terminal so GTK's native resource paths remain available.
RatioLab also adds that Python installation's `bin` to DLL discovery before
importing PyGObject. Windows ARM64 is not covered by this UCRT64 x86-64 recipe.

### macOS source/wheel (Homebrew)

Install [Homebrew](https://brew.sh/), then:

```sh
brew install pygobject3 gtk4
sh scripts/install-macos.sh
"$HOME/Library/Application Support/RatioLab/venv/bin/ratiolab" --diagnose-gui
"$HOME/Library/Application Support/RatioLab/venv/bin/ratiolab"
```

The script inspects the installed `pygobject3` formula's Python dependencies and
selects an installed Homebrew interpreter that can actually import both GTK 4
and Cairo. It does not assume that `python3` on your PATH is compatible. If none
works, it stops before creating the environment. Homebrew may change the Python
versions its bindings support; reinstall/recreate the environment after a native
Python upgrade. The script works with Intel or Apple Silicon Homebrew prefixes
when the native formulae are available for that macOS release. Run from a normal
logged-in macOS desktop session; no XQuartz is needed for GTK's Quartz backend.

For a wheel, source `scripts/macos-python.sh`, set
`python=$(choose_macos_python)`, create a `--system-site-packages` environment with
that interpreter, then use its `bin/python -m pip install --no-deps /path/to/ratiolab-0.1.0-py3-none-any.whl`.
For a self-contained app, use the DMGs described above. Those preview builds
use ad-hoc signing, without a Developer ID identity or Apple notarization.

## Check the installation

`ratiolab --diagnose` prints the actual Python, GTK/Cairo versions, libepoxy,
resource paths and default data locations. It needs no graphical display.
`ratiolab --diagnose-gui` opens a small window, compiles the real preview shaders
and renders a gear using the active driver. Run it on the target computer before
assuming 3D support. An unavailable/old GL driver is reported as a failed check.
Remote desktop, virtual machines and CI runners can have different graphics
capabilities from a local session.

After installation you can remove or move the original checkout/source archive.
Launch the installed environment's `ratiolab`, not its former `launch.sh`.
Source development remains supported with `./launch.sh` or `python3 src/app.py`;
`python3 src/install_desktop.py` registers that particular checkout instead.

## User data and existing configurations

| System | Preferences | Default exports and generated STEP assets |
|---|---|---|
| Linux | `$XDG_CONFIG_HOME/ratiolab` or `~/.config/ratiolab` | `$XDG_DATA_HOME/ratiolab/exports` or `~/.local/share/ratiolab/exports` |
| Windows | `%APPDATA%/RatioLab` | `%LOCALAPPDATA%/RatioLab/exports` |
| macOS | `~/Library/Application Support/RatioLab` | `~/Library/Application Support/RatioLab/exports` |

The UI's **Change folder…** overrides the export location. Preferences are UTF-8
JSON in `ui-preferences.json`, saved atomically, and never written into the
installed code/resources. If that file does not exist, RatioLab reads the old
`preferenze-ui.json` in the user directory, then the source checkout's old file
if needed. The next preference save writes the English filename, preserving
the original file and settings. A present but invalid new file takes precedence
over legacy files. For a fresh
installation, select an existing export folder in the UI. Previously generated
files are not copied, moved or deleted by installation/uninstallation. The
`solidcraft-riduttori/1` configuration format and `local.solidcraft.reducers`
application ID are preserved.

Catalogs and runtime branding live in `src/ratiolab_resources/`. The source
launcher is `launch.sh`; reusable project configurations are in `examples/`. Generated reports use `.calculations.json`,
`.calculations.txt` and `.machining.json`; generated STEP assets default to a
`solids/` subdirectory. These names do not change project-format identifiers,
parameter keys or the ability to reopen earlier configurations. Existing user
exports are retained as saved.

## Optional Autodesk Fusion connection

The [Fusion integration guide](fusion360.md) describes the user workflow. The
standalone `fusion_connection` client prepares persistent per-part STEP packages
and submits a hashed manifest to the add-in under
`src/ratiolab_resources/fusion_addin/RatioLabBridge/`. This directory is plain
resource data in wheels and frozen bundles because Fusion loads it with its own
Python and SDK. It must not be imported by RatioLab's Python environment.

The add-in owns a localhost listener and dispatches the two protocol methods
through a Fusion CustomEvent. CAD operations run on Fusion's main thread. Tests
cover the real client/server transport with a simulated dispatcher and a mocked
SDK separately; a live Fusion import is additional evidence, not implied by
those tests. On Linux the native client can connect to the Windows SDK host
running through Wine. It discovers the selected prefix/profile and stages
transfer packages on its C: drive, avoiding a dependency on the Z: mapping.
Wine path/protocol fixtures do not constitute a live Fusion-on-Linux test.

## Optional SolidCraft connection

STL generation and export are local and require no CAD installation. RatioLab
does not install SolidCraft or guarantee a compatible SolidCraft build exists
on each platform. If you have one with the authenticated local control protocol,
start it with `--control 7878` and configure its actual token directory using
the absolute environment variable `SOLIDCRAFT_CONTROL_DIR`.

On Linux the existing `~/.local/share/solidcraft/control` (or XDG equivalent)
and `~/AppImages/solidcraft.appimage` defaults remain. On Windows/macOS the token
directory must be explicitly configured; no AppImage path is guessed. To allow
launching a compatible CAD executable, set `SOLIDCRAFT_EXECUTABLE` to its full
path (for a macOS `.app`, its actual executable under `Contents/MacOS`, not the
bundle directory). Paths with spaces are passed as one argument, without a
shell. A running compatible CAD instance is reused first.

## Build and verification

Use a development environment with `build`, `setuptools>=77` and `wheel`:

```sh
python -m pip install build 'setuptools>=77' wheel
python -m build
python scripts/verify-artifacts.py dist
```

`python -m build` creates the sdist, then builds the wheel **from that sdist**.
Both include explicit code/resource lists; no preferences, credentials, `work/`,
`design/`, `outputs/`, `.git` or generated models are distributed. Runtime assets are packaged from `src/ratiolab_resources/`; the small
`build-support/` hook adds canonical user documentation and legal notices.
It does not copy developer notes or test files into the installed application.

Install the wheel into a fresh native environment outside the checkout. Copy
`scripts/installed_smoke.py` into a neutral directory, change there, and run it
with that environment's Python, using `--forbid-root /absolute/source/path` and
optionally `--gui`. It verifies installed imports/resources, UTF-8 configuration
round trips, generated STEP, standalone STL and preferences under a disposable
profile. The GUI option also opens the full workspace and tests its save/load
path. A read-only installed package must pass these checks.

`.github/workflows/portable.yml` defines Linux, MSYS2 Windows and Homebrew macOS
jobs that build through the sdist and test an installed wheel outside the
checkout. Linux includes software-rendered GUI/GL checks with Xvfb. Windows and
macOS always check native imports/loader and data/export paths; their GUI/driver
check is opt-in via the workflow's `native_gui` input. The workflow logs record
which checks actually ran; a skipped GUI/driver check is not a validation of
graphics hardware. See the [completed workflow runs](https://github.com/NoOneExceptEnderk/RatioLab/actions) for the recorded native runs.

Installation recipes follow [PyGObject's platform instructions](https://pygobject.gnome.org/getting_started.html),
[MSYS2's Python ABI and virtual-environment documentation](https://www.msys2.org/docs/python/),
[Homebrew's PyGObject formula](https://formulae.brew.sh/formula/pygobject3),
[GTK's macOS backend documentation](https://docs.gtk.org/gtk4/osx.html) and
[libepoxy's OpenGL dispatch documentation](https://github.com/anholt/libepoxy).


### Native GUI verification

The installed self-test now checks all six new feature areas: standalone STEP
and SVG/DXF, project history/recovery, generated tooth profiles, interference
distances, finite combination search and component picking/selected export.
It writes only to a disposable profile. The GUI self-test opens the three new
tools, exports the complete workspace and decodes animated preview PNGs for
all nine families to reject blank captures.

The Windows bundle explicitly includes `libEGL.dll` and `libGLESv2.dll` from
[MSYS2 ANGLE](https://packages.msys2.org/packages/mingw-w64-ucrt-x86_64-angleproject).
GTK loads these dynamically, so they must be collected even without a static
DLL import. Their dependent libraries and licenses are included by the normal
native inventory. GPU drivers and Windows Direct3D remain OS components.
The preview allows both APIs and tries desktop GL 3.3, then GLES 3.0, with
separate minimum-version requests. It validates the realized context before
selecting GLSL 330 core or GLSL ES 300 with explicit precision. The shader math
is shared across both APIs.
Preview captures read portable RGBA bytes and convert to native Cairo ARGB32.

The native workflow always attempts installed GUI verification on Windows and
macOS. Only explicit absence of a graphical desktop or GL context may be
recorded as unavailable; missing EGL libraries, crashes, timeouts, shader
errors and blank images fail the job. A successful renderer must also pass
the full GUI self-test. Use `native_gui=true` to require graphics capability
instead of allowing an explicit runner limitation. Reports are uploaded as
separate GUI verification artifacts.
