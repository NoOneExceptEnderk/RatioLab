# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Resource location shared by source runs, installed wheels and native bundles."""
from pathlib import Path


def root():
    return Path(__file__).resolve().parent
