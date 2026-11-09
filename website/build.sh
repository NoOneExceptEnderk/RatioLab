#!/usr/bin/env bash
# Isolated static-site build with the shared Wasm kernel; no native GUI dependencies.
set -euo pipefail

site_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
site_venv=${RATIOLAB_SITE_VENV:-"$site_dir/.venv"}
site_python=${RATIOLAB_SITE_PYTHON:-python3}

if [[ ! -x "$site_venv/bin/python" ]]; then
  "$site_python" -m venv "$site_venv"
fi
"$site_venv/bin/python" -c 'import sys; assert sys.prefix != sys.base_prefix, "RATIOLAB_SITE_VENV must be an isolated virtual environment"'
# Offline means no network, including dependency installation. Already installed
# exact requirements are accepted; an unprepared environment fails without fetches.
site_pip_options=()
site_rust_options=()
for site_argument in "$@"; do
  if [[ "$site_argument" == "--offline" ]]; then
    site_pip_options+=(--no-index)
    site_rust_options+=(--offline)
    break
  fi
done
"$site_venv/bin/python" -m pip install --disable-pip-version-check --no-input "${site_pip_options[@]}" -r "$site_dir/requirements.txt"
"$site_python" "$site_dir/../scripts/build-rust-engine.py" --target wasm "${site_rust_options[@]}"
exec "$site_venv/bin/python" "$site_dir/build.py" "$@"
