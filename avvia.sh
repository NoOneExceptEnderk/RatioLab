#!/bin/sh
cd -- "$(dirname -- "$0")" || exit 1
exec "${RATIOLAB_PYTHON:-python3}" app.py "$@"
