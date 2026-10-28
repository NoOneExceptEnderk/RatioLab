# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Explicit app payload: do not collect checkout preferences or generated data."""
from pathlib import Path

root = Path(__file__).resolve().parents[2]
resources = root/'src/ratiolab_resources'
datas = [(str(resources/name), 'ratiolab_resources') for name in
         ('bearing-catalog.json', 'hardware-catalog.json')]
datas += [(str(root/name), 'ratiolab_resources') for name in ('LICENSE', 'COPYRIGHT')]
datas += [(str(resources/'branding'/name), 'ratiolab_resources/branding') for name in
          ('brand.json', 'ratiolab-icon.png', 'ratiolab-logo-dark.png',
           'ratiolab-logo-light.png', 'ratiolab-approved-board.png',
           'ratiolab-monochrome-reference.png')]
