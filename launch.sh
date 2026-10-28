#!/bin/sh
# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
cd -- "$(dirname -- "$0")" || exit 1
exec "${RATIOLAB_PYTHON:-python3}" app.py "$@"
