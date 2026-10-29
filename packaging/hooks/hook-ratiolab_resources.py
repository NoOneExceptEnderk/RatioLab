# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Explicit app payload: do not collect checkout preferences or generated data."""
from pathlib import Path

root = Path(__file__).resolve().parents[2]
resources = root/'src/ratiolab_resources'
datas = [(str(resources/name), 'ratiolab_resources') for name in
         ('bearing-catalog.json', 'hardware-catalog.json')]
datas += [(str(root/name), 'ratiolab_resources') for name in ('LICENSE', 'COPYRIGHT', 'CHANGELOG.md')]
datas += [(str(resources/'version.json'), 'ratiolab_resources')]
datas += [(str(resources/'branding'/name), 'ratiolab_resources/branding') for name in
          ('brand.json', 'ratiolab-icon.png', 'ratiolab-logo-dark.png',
           'ratiolab-logo-light.png', 'ratiolab-approved-board.png',
           'ratiolab-monochrome-reference.png')]
datas += [(str(path), str(Path('ratiolab_resources')/path.parent.relative_to(resources)))
          for path in sorted((resources/'icons').rglob('*')) if path.is_file()]

# Fusion runs this add-in with its own Python; ship its sources as plain data.
addin = resources/'fusion_addin'/'RatioLabBridge'
datas += [(str(path), 'ratiolab_resources/fusion_addin/RatioLabBridge')
          for pattern in ('*.py', '*.manifest') for path in sorted(addin.glob(pattern))]
