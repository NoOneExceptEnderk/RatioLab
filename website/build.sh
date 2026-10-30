#!/usr/bin/env bash
# Isolated static-site build; no application or native GUI dependencies.
set -euo pipefail

site_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
site_venv=${RATIOLAB_SITE_VENV:-"$site_dir/.venv"}
site_python=${RATIOLAB_SITE_PYTHON:-python3}

if [[ ! -x "$site_venv/bin/python" ]]; then
  "$site_python" -m venv "$site_venv"
fi
"$site_venv/bin/python" -c 'import sys; assert sys.prefix != sys.base_prefix, "RATIOLAB_SITE_VENV must be an isolated virtual environment"'
"$site_venv/bin/python" -m pip install --disable-pip-version-check --no-input -r "$site_dir/requirements.txt"
exec "$site_venv/bin/python" "$site_dir/build.py" "$@"
