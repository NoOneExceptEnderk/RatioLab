#!/bin/sh
# Install Homebrew pygobject3 and gtk4 first; see INSTALL.md.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$root/scripts/macos-python.sh"
python=$(choose_macos_python)
destination=${RATIOLAB_VENV:-$HOME/Library/Application Support/RatioLab/venv}
"$python" -m venv --system-site-packages "$destination"
"$destination/bin/python" -m pip install --no-deps "$root"
"$destination/bin/python" -m ratiolab_cli --diagnose
printf 'Run RatioLab: "%s/bin/ratiolab"\n' "$destination"
