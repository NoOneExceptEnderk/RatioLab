# Install RatioLab

RatioLab is a desktop application. **Use the bundled installer for your system:**
Python, GTK and the application libraries are included. No command line or
separate development environment is needed for Windows/macOS or the Linux `.deb`.

[Download release 0.1.11](https://github.com/NoOneExceptEnderk/RatioLab/releases/tag/v0.1.11)

Release packages are published after their native CI checks pass. Consult the release
notes for completed platform checks; platform requirements do not imply that every
GPU, driver or CAD integration has been tested.

## Windows 11

Supported: 64-bit Intel/AMD Windows 11, build 22000 or newer.

1. Download [Windows Setup](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.11/RatioLab-0.1.11-windows-x86_64-setup.exe).
2. Open the downloaded `.exe` and follow Setup. It installs for your user account.
3. Open **Start → RatioLab**.

Setup is currently unsigned. Windows can show an unrecognized-publisher warning
or block it under your security policy. The release files and their SHA256 checksums
are available on the linked GitHub release. Report launch problems in [Issues](https://github.com/NoOneExceptEnderk/RatioLab/issues).

To uninstall, open **Settings → Apps → Installed apps → RatioLab → Uninstall**.

## macOS

Supported: **macOS 15 or newer**, with separate Apple Silicon and Intel installers.
To identify your Mac, open **Apple menu → About This Mac**: an Apple M-series chip
uses the Apple Silicon download; an Intel processor uses the Intel download.

1. Download the [Apple Silicon DMG](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.11/RatioLab-0.1.11-macos-arm64.dmg) or [Intel DMG](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.11/RatioLab-0.1.11-macos-x86_64.dmg).
2. Open the DMG and drag **RatioLab** onto **Applications**.
3. Eject the disk image, then open RatioLab from Applications.

The macOS packages use ad-hoc signing and have **no Apple notarization**. macOS can
warn about or block the application. This is a release limitation; consult the
system's message and report installation problems rather than disabling system protections.

To uninstall, move RatioLab from Applications to Trash.

## Linux

Supported: **x86-64 Linux with glibc 2.39 or newer**, using Ubuntu 24.04 as the
build baseline. Older systems and ARM Linux are not covered by these installers.

### Debian/Ubuntu package

1. Download [the `.deb` package](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.11/ratiolab_0.1.11_amd64.deb).
2. Open it with your software installer and choose **Install**.
3. Launch RatioLab from your application menu.

The package installs under `/opt/ratiolab`. Remove it through your package manager.

### Per-user installer for compatible Linux systems

Download [the `.run` installer](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.11/RatioLab-0.1.11-linux-x86_64.run).
Open a terminal in the download folder and run:

```sh
sh RatioLab-0.1.11-linux-x86_64.run
```

Follow the prompts, then launch RatioLab from your application menu. The default
location is `~/.local/share/ratiolab/app`; no administrator password is needed.
To remove this installation, run `uninstall.sh` in that folder.

A [portable `.tar.gz` archive](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.11/RatioLab-0.1.11-linux-x86_64.tar.gz)
contains the same runtime and `install.sh` for alternative installations.

## First launch and graphics

Choose a gear/reducer family, adjust dimensions, then use **Save** or **Export…**.
The interface is in English. See the [user guide](https://github.com/NoOneExceptEnderk/RatioLab/blob/main/docs/user-guide.md) and
[example projects](https://github.com/NoOneExceptEnderk/RatioLab/blob/main/examples/) for the available operations and model limits.

The preview needs a working desktop and graphics driver providing desktop
OpenGL 3.3+ or OpenGL ES 3.0+. GTK negotiates an available API; Windows also
includes ANGLE for OpenGL ES over Direct3D. Installing separate GTK/Python packages will not repair an
unsupported graphics driver. SolidCraft is optional; STEP/STL/SVG/DXF exports
work independently of it.

Updates and uninstallers preserve saved preferences and exported projects.
Keep your own backups of valuable project files.

## Agent integration, development and troubleshooting

The installers include `RatioLab-MCP` (`RatioLab-MCP.exe` on Windows).
See [agent setup](https://github.com/NoOneExceptEnderk/RatioLab/blob/main/docs/mcp.md) for its separate, offline workspace and client configuration.

To build from source or create installers, use [development instructions](https://github.com/NoOneExceptEnderk/RatioLab/blob/main/docs/development.md).
These steps are not required to use the downloadable application.

For a problem report, include your OS version, processor architecture, RatioLab
version, exact error and reproduction steps. Normal launches write errors to
`logs/ratiolab.log` under the per-user RatioLab data directory:

| System | Data directory |
|---|---|
| Windows | `%LOCALAPPDATA%/RatioLab` |
| macOS | `~/Library/Application Support/RatioLab` |
| Linux | `${XDG_DATA_HOME:-~/.local/share}/ratiolab` |

[Open an issue](https://github.com/NoOneExceptEnderk/RatioLab/issues).
