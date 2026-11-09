# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Include canonical documentation and project notices in the runtime wheel."""
from pathlib import Path
import importlib.util
import shutil
from wheel.bdist_wheel import bdist_wheel
from setuptools.command.build_py import build_py


class BuildPy(build_py):
    def run(self):
        super().run()
        root = Path(__file__).resolve().parents[1]
        import json
        identity=json.loads((root/'src/ratiolab_resources/version.json').read_text(encoding='utf-8'))
        if identity['base']!=self.distribution.get_version():
            raise RuntimeError('pyproject.toml version and release identity base differ')
        spec=importlib.util.spec_from_file_location('ratiolab_rust_builder', root/'scripts/build-rust-engine.py')
        builder=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        library=builder.build()
        target = Path(self.build_lib)/'ratiolab_resources'
        (target/'native').mkdir(parents=True,exist_ok=True)
        shutil.copyfile(library,target/'native'/library.name)
        shutil.copytree(root/'target/ratiolab-rust-notices',target/'rust-notices',dirs_exist_ok=True)
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


class BdistWheel(bdist_wheel):
    """The C ABI is Python-version independent, but the library is OS-specific."""
    def finalize_options(self):
        self.distribution.has_ext_modules=lambda:True
        super().finalize_options()
        self.root_is_pure=False

    def get_tag(self):
        _,_,platform=super().get_tag()
        return 'py3','none',platform
