# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Include canonical documentation and project notices in the runtime wheel."""
from pathlib import Path
from setuptools.command.build_py import build_py


class BuildPy(build_py):
    def run(self):
        super().run()
        root = Path(__file__).resolve().parents[1]
        import json
        identity=json.loads((root/'src/ratiolab_resources/version.json').read_text(encoding='utf-8'))
        if identity['base']!=self.distribution.get_version():
            raise RuntimeError('pyproject.toml version and release identity base differ')
        target = Path(self.build_lib)/'ratiolab_resources'
        # Keep one maintained source for documentation and legal notices.
        for source, name in (
            (root/'LICENSE', 'LICENSE'),
            (root/'COPYRIGHT', 'COPYRIGHT'),
            (root/'docs/installation.md', 'INSTALL.md'),
            (root/'docs/mcp.md', 'MCP.md'),
            (root/'CHANGELOG.md', 'CHANGELOG.md'),
        ):
            target.mkdir(parents=True, exist_ok=True)
            self.copy_file(str(source), str(target/name))
