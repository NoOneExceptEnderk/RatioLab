#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
# Run in the MSYS2 UCRT64 terminal, after installing the packages in docs/installation.md.
set -euo pipefail
if [[ ${MSYSTEM:-} != UCRT64 ]]; then
    printf '%s\n' 'Open the MSYS2 UCRT64 terminal to run this installer.' >&2
    exit 1
fi
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
destination=${RATIOLAB_VENV:-$HOME/.local/share/ratiolab/venv}
python=/ucrt64/bin/python.exe
export PYGI_DLL_PATH="$(cygpath -w /ucrt64/bin)${PYGI_DLL_PATH:+;$PYGI_DLL_PATH}"
"$python" -c 'import os,sysconfig,gi,cairo; assert os.name=="nt" and sysconfig.get_platform().startswith("mingw"); gi.require_version("Gtk","4.0"); from gi.repository import Gtk; assert Gtk.check_version(4,12,0) is None, "GTK 4.12 or newer is required"'
"$python" -m venv --system-site-packages "$destination"
"$destination/bin/python.exe" -m pip install --no-build-isolation --no-deps "$root"
"$destination/bin/python.exe" -m ratiolab_cli --diagnose
printf 'From this UCRT64 terminal, run: "%s/bin/python.exe" -m ratiolab_cli\n' "$destination"
