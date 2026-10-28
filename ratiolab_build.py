# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Stage the existing resource tree into the wheel without moving source assets."""
from pathlib import Path
from setuptools.command.build_py import build_py


class BuildPy(build_py):
    def run(self):
        super().run()
        root = Path(__file__).resolve().parent
        target = Path(self.build_lib)/'ratiolab_resources'
        # Explicit allowlist: no preferences, generated exports, work/design,
        # personal data or Git metadata can enter the wheel.
        resources = [
            (root/'LICENSE', target/'LICENSE'),
            (root/'COPYRIGHT', target/'COPYRIGHT'),
            (root/'INSTALL.md', target/'INSTALL.md'),
            (root/'MCP.md', target/'MCP.md'),
            (root/'bearing-catalog.json', target/'bearing-catalog.json'),
            (root/'hardware-catalog.json', target/'hardware-catalog.json'),
        ]
        resources.extend((root/'assets/branding'/name, target/'branding'/name)
                         for name in (
                             'brand.json', 'ratiolab-icon.png',
                             'ratiolab-logo-dark.png', 'ratiolab-logo-light.png',
                             'ratiolab-approved-board.png', 'ratiolab-monochrome-reference.png',
                         ))
        for source, destination in resources:
            destination.parent.mkdir(parents=True, exist_ok=True)
            self.copy_file(str(source), str(destination))
