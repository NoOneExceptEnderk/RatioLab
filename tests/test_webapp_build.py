# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Deterministic, allowlisted browser bundle checks (no network)."""
from io import BytesIO
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('build_webapp', ROOT/'scripts/build-webapp.py')
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class BuildTests(unittest.TestCase):
    def test_no_implicit_network_runtime_and_no_destructive_unknown_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)/'output'
            with self.assertRaisesRegex(ValueError, 'runtime-dir'):
                builder.build(output)
            output.mkdir(); (output/'precious.txt').write_text('keep')
            with self.assertRaisesRegex(ValueError, 'Refusing to replace'):
                builder.build(output, external_runtime=True)
            self.assertEqual((output/'precious.txt').read_text(), 'keep')

    def test_rebuild_preserves_extra_files_modified_files_and_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            output = folder/'output'
            builder.build(output, external_runtime=True)
            extra = output/'personal.txt'; extra.write_text('keep')
            with self.assertRaisesRegex(ValueError, 'extra files'):
                builder.build(output, external_runtime=True)
            self.assertEqual(extra.read_text(), 'keep')
            extra.unlink()
            client = output/'engine-client.js'; original = client.read_bytes()
            client.write_text('personal edits')
            with self.assertRaisesRegex(ValueError, 'edited output'):
                builder.build(output, external_runtime=True)
            self.assertEqual(client.read_text(), 'personal edits')
            client.write_bytes(original)
            linked = output/'shortcut'; linked.symlink_to(folder/'outside')
            with self.assertRaisesRegex(ValueError, 'symlinks'):
                builder.build(output, external_runtime=True)
            self.assertTrue(linked.is_symlink())
            alias = folder/'alias'; alias.symlink_to(output, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'symlinks'):
                builder.build(alias, external_runtime=True)
            with self.assertRaisesRegex(ValueError, 'overlap'):
                builder.build(ROOT, external_runtime=True)
            with self.assertRaisesRegex(ValueError, 'under ignored work'):
                builder.build(ROOT/'src'/'new-output', external_runtime=True)

    def test_pinned_runtime_corruption_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            runtime = folder/'runtime'; runtime.mkdir()
            config = json.loads((ROOT/'webapp/runtime.json').read_text())
            name = next(iter(config['files']))
            (runtime/name).write_bytes(b'wrong release')
            with self.assertRaisesRegex(ValueError, 'differs from pinned'):
                builder.build(folder/'output', runtime_dir=runtime)
            self.assertFalse((folder/'output').exists())

    def test_external_mode_is_explicit_and_reproducible_allowlist_excludes_private_and_gui(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)/'output'
            manifest = builder.build(output, external_runtime=True)
            first = {p.relative_to(output).as_posix(): p.read_bytes() for p in output.rglob('*') if p.is_file()}
            builder.build(output, external_runtime=True)
            second = {p.relative_to(output).as_posix(): p.read_bytes() for p in output.rglob('*') if p.is_file()}
            self.assertEqual(first, second)
            runtime = json.loads((output/'runtime.json').read_text())
            self.assertTrue(runtime['allow_external'])
            self.assertEqual(runtime['indexURL'], 'https://cdn.jsdelivr.net/pyodide/v314.0.7/full/')
            self.assertNotIn('runtime/pyodide.mjs', manifest['files'])
            self.assertTrue({'LICENSE', 'COPYRIGHT', 'source.zip', 'source-fonts.zip', 'engine.zip'} <= set(first))
            self.assertEqual(set(builder.ASSETS), {'rust-engine.js', 'engine-client.js', 'worker.js', 'index.html', 'app.css', 'app.js', 'model-catalog.js', 'choice-menu.js', 'ui-language.js', 'viewer.js', 'document.js', 'preferences.js', 'tools.js', 'tools.css', 'help-illustrations.json'})
            self.assertEqual(set(builder.BRANDING), {'ratiolab-icon.png', 'ratiolab-logo-dark.png'})
            for name in builder.ASSETS:
                self.assertEqual(first[name], (ROOT/'webapp'/name).read_bytes())
            for name in builder.BRANDING:
                self.assertEqual(first['branding/'+name], (ROOT/'src/ratiolab_resources/branding'/name).read_bytes())
            expected_static = set(builder.ASSETS) | {'branding/'+name for name in builder.BRANDING} | {'runtime.json', 'bundle-manifest.json', 'LICENSE', 'COPYRIGHT', 'source.zip', 'source-fonts.zip', 'engine.zip', 'README.txt', 'serve.py'} | {'notices/'+name for name in builder.NOTICES}
            expected_static |= set(builder.UI_RESOURCES) | {'fonts/'+name for name in builder.FONTS}
            expected_static |= {'ratiolab_geometry.wasm', 'rust-notices.zip'}
            self.assertEqual(set(first), expected_static)
            self.assertEqual(first['ratiolab_geometry.wasm'], (ROOT/'target/wasm32-unknown-unknown/release/ratiolab_geometry.wasm').read_bytes())
            with ZipFile(output/'rust-notices.zip') as archive:
                notices=json.loads(archive.read('components.json'))
                self.assertEqual(notices['format'], 'ratiolab-rust-notices/1')
                self.assertTrue(notices['packages'])
                for package in notices['packages']:
                    for name in package['notice_files']:
                        self.assertTrue(archive.read(name))
                self.assertTrue(archive.read('rust-stdlib/COPYRIGHT-library.html'))
            self.assertEqual(first['serve.py'], (ROOT/'scripts/serve-webapp.py').read_bytes())
            self.assertEqual(first['README.txt'], (ROOT/'webapp/README.txt').read_bytes())
            for name in builder.NOTICES:
                self.assertEqual(first['notices/'+name], (ROOT/'webapp/notices'/name).read_bytes())
            with ZipFile(output/'source.zip') as archive:
                for name in builder.RECIPES:
                    self.assertEqual(archive.read('scripts/'+name), (ROOT/'scripts'/name).read_bytes())
                self.assertIn('docs/web-app.md', archive.namelist())
                self.assertEqual(archive.read('docs/technical/curved-cad-prototype.md'),
                                 (ROOT/'docs/technical/curved-cad-prototype.md').read_bytes())
                self.assertEqual(archive.read('docs/technical/curved-cylindrical-cad.md'),
                                 (ROOT/'docs/technical/curved-cylindrical-cad.md').read_bytes())
                self.assertIn('webapp/README.txt', archive.namelist())
                for name in ('Cargo.toml','Cargo.lock','rust-toolchain.toml','rust/geometry-kernel/src/precision.rs'):
                    self.assertEqual(archive.read(name), (ROOT/name).read_bytes())
            with ZipFile(output/'engine.zip') as archive:
                names = set(archive.namelist())
                self.assertTrue({'backlash_solver.py', 'collision_geometry.py', 'combination_search.py',
                                 'component_geometry.py', 'interference.py'} <= names)
                for module in ('backlash_solver', 'collision_geometry', 'combination_search', 'component_geometry', 'interference'):
                    self.assertEqual(archive.read(module+'.py'), (ROOT/'src'/(module+'.py')).read_bytes())
                expected = {name+'.py' for name in builder.MODULES} | {'engine_bridge.py'} | {'ratiolab_resources/'+name for name in builder.RESOURCES} | {'ratiolab_resources/web-catalog.json', 'ratiolab_resources/LICENSE', 'ratiolab_resources/COPYRIGHT'}
                self.assertEqual(names, expected)
                self.assertFalse(any('work/' in name or '.git' in name or 'fusion' in name or 'credentials' in name for name in names))
                for name in names:
                    if name.endswith('.py'):
                        data = archive.read(name).decode()
                        self.assertNotIn('from gi.repository', data)
                        self.assertNotIn('import gi\n', data)
                self.assertEqual(len(json.loads(archive.read('ratiolab_resources/web-catalog.json'))['catalog']), 15)
            # Import the extracted engine from a neutral directory, no checkout on
            # sys.path. This catches missing closure entries and resource files.
            extracted = Path(temporary)/'engine'
            with ZipFile(output/'engine.zip') as archive: archive.extractall(extracted)
            probe = "import sys,json;sys.path.insert(0,sys.argv[1]);import engine_bridge as b;r=json.loads(b.dispatch('generate',json.dumps({'family':'wolfrom','parameters':{}})));assert r['ok'],r;assert r['result']['triangle_count']>0;assert len(r['result']['parts'])==18;assert r['result']['analysis']['wolfrom']['signed_ratio']==600;assert 'gi' not in sys.modules"
            # The Python archive is an adapter closure, not a second engine.
            # Supply the separately built native equivalent for this CPython
            # probe; the browser itself executes the matching Wasm asset.
            from rust_geometry import _library
            probe_env=dict(os.environ,RATIOLAB_GEOMETRY_LIBRARY=_library()._name)
            result = subprocess.run([sys.executable, '-I', '-c', probe, str(extracted)], cwd=temporary, env=probe_env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            # Published corresponding source can rebuild without GTK source.
            source = Path(temporary)/'source'
            with ZipFile(output/'source.zip') as archive: archive.extractall(source)
            with ZipFile(output/'source-fonts.zip') as archive:
                for name in builder.FONTS:
                    self.assertEqual(archive.read('packaging/fonts/'+name), (ROOT/'packaging/fonts'/name).read_bytes())
                archive.extractall(source)
            rebuilt = Path(temporary)/'rebuilt'
            # Corresponding source includes the complete locked Rust recipe.
            result = subprocess.run([sys.executable, str(source/'scripts/build-rust-engine.py'), '--target', 'wasm', '--offline'], cwd=temporary, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([sys.executable, str(source/'scripts/build-webapp.py'), '--external-runtime', '--output', str(rebuilt)], cwd=temporary, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((output/'engine.zip').read_bytes(), (rebuilt/'engine.zip').read_bytes())
            self.assertEqual((output/'source.zip').read_bytes(), (rebuilt/'source.zip').read_bytes())
            self.assertEqual((output/'source-fonts.zip').read_bytes(), (rebuilt/'source-fonts.zip').read_bytes())
            self.assertEqual((output/'bundle-manifest.json').read_bytes(), (rebuilt/'bundle-manifest.json').read_bytes())
            for name in (*builder.ASSETS, *('branding/'+n for n in builder.BRANDING)):
                self.assertEqual((output/name).read_bytes(), (rebuilt/name).read_bytes())

    def test_reviewed_dependency_closure_and_source_bytes_are_unchanged(self):
        files = builder.engine_files(ROOT)
        self.assertIn('wolfrom', builder.MODULES)
        for module in builder.MODULES:
            self.assertEqual(files[module+'.py'], (ROOT/'src'/f'{module}.py').read_bytes())
        for forbidden in ['app', 'gui_workflow', 'preview3d', 'connection', 'fusion_connection', 'ratiolab_agent', 'ratiolab_mcp', 'updates', 'install_desktop']:
            self.assertNotIn(forbidden+'.py', files)


if __name__ == '__main__': unittest.main()
