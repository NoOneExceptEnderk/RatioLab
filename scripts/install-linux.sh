#!/bin/sh
# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
# Native GTK dependencies must be installed as described in INSTALL.md first.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
python=${RATIOLAB_PYTHON:-python3}
destination=${RATIOLAB_VENV:-${XDG_DATA_HOME:-$HOME/.local/share}/ratiolab/venv}
"$python" -c 'import gi,cairo; gi.require_version("Gtk","4.0"); from gi.repository import Gtk; assert Gtk.check_version(4,12,0) is None, "GTK 4.12 or newer is required"'
"$python" -m venv --system-site-packages "$destination"
"$destination/bin/python" -m pip install --no-deps "$root"
"$destination/bin/python" -m ratiolab_cli --diagnose
"$destination/bin/python" -m install_desktop
printf 'Run RatioLab: "%s/bin/ratiolab"\n' "$destination"
