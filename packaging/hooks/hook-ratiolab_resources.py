"""Explicit app payload: do not collect checkout preferences or generated data."""
from pathlib import Path

root = Path(__file__).resolve().parents[2]
datas = [(str(root/name), 'ratiolab_resources') for name in
         ('catalogo-cuscinetti.json', 'catalogo-hardware.json', 'INSTALL.md')]
datas += [(str(root/'assets/branding'/name), 'ratiolab_resources/branding') for name in
          ('brand.json', 'ratiolab-icon.png', 'ratiolab-logo-dark.png',
           'ratiolab-logo-light.png', 'ratiolab-approved-board.png',
           'ratiolab-monochrome-reference.png')]
