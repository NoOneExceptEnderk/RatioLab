# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Run from a neutral directory with an installed RatioLab, never the checkout.

Checks resources, geometry/STL and preferences under a disposable user profile.
--gui also realizes the complete workspace and renders the OpenGL preview.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gui', action='store_true')
    parser.add_argument('--forbid-root', type=Path)
    args = parser.parse_args()
    import app_paths
    import geometry
    if args.forbid_root:
        forbidden = args.forbid_root.resolve()
        for module in (app_paths, geometry):
            if Path(module.__file__).resolve().is_relative_to(forbidden):
                raise AssertionError(f'Imported source checkout: {module.__file__}')
    before = {}
    for filename in ('branding/ratiolab-icon.png', 'branding/ratiolab-logo-dark.png',
                     'branding/ratiolab-logo-light.png', 'branding/brand.json',
                     'bearing-catalog.json', 'hardware-catalog.json',
                     'INSTALL.md', 'MCP.md', 'LICENSE', 'COPYRIGHT'):
        path = app_paths.resource_path(filename)
        if args.forbid_root and path.resolve().is_relative_to(forbidden):
            raise AssertionError(f'Resource depends on source checkout: {path}')
        before[path] = hashlib.sha256(path.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='ratiolab-profile-') as temporary:
        profile = Path(temporary).resolve()
        # Avoid writing to the runner/user's actual preferences on every OS.
        os.environ.update(XDG_CONFIG_HOME=str(profile/'config'), XDG_DATA_HOME=str(profile/'data'),
                          APPDATA=str(profile/'roaming'), LOCALAPPDATA=str(profile/'local'))
        from unittest.mock import patch
        with patch.object(Path, 'home', return_value=profile):
            chosen = profile/'chosen exports · qualità Ω'
            app_paths.save_preferences(output_dir=str(chosen))
            assert app_paths.saved_output_dir() == chosen
            data = app_paths.load_preferences()
            assert data['output_dir'] == str(chosen)
            output = app_paths.default_output_dir()
            import stl_export
            design = geometry.generate('helical')
            assets = design.prepare_assets()
            assert assets.is_relative_to(output)
            assert any(assets.glob('*.step'))
            assembly, parts = stl_export.export(design, output/'portable-test')
            assert assembly.stat().st_size > 84 and parts
            config = output/'portable-test.config.json'
            config.write_text(json.dumps(dict(format='solidcraft-riduttori/1', family=design.family,
                                              parameters=design.values)), encoding='utf-8')
            loaded = json.loads(config.read_text(encoding='utf-8'))
            assert geometry.generate(loaded['family'], loaded['parameters']).values == design.values
            from ratiolab_cli import diagnose
            result = diagnose(gui=args.gui)
            if args.gui:
                # Exercise the same resource location and persistence code used
                # by the full installed app, beyond the small GL diagnostic.
                import app
                import gui_workflow
                from gi.repository import Gio, GLib
                application = app.ReducerApp()
                application.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
                application.register(None)
                application.activate()
                application.output_dir = chosen
                gui_workflow.save_preference(application, output_dir=str(output))
                application.load_config_data(loaded)
                assert application.config()['format'] == 'solidcraft-riduttori/1'
                assert application.family == 'helical'
                context = GLib.MainContext.default()
                from ratiolab_checks import _wait_for_context
                _wait_for_context(context,
                                  lambda: application.canvas.gl and not application.canvas.dirty,
                                  timeout=10)
                assert application.canvas.gl and not application.canvas.failure
                saved_path = chosen/'installed-workspace.config.json'
                assert application.save_project(path=saved_path), 'Workspace save failed'
                assert application.document.path == saved_path and not application.document.dirty
                saved = list(chosen.glob('*.config.json'))
                assert saved, 'The installed workspace did not save its configuration'
                assert json.loads(saved[-1].read_text(encoding='utf-8'))['format'] == 'solidcraft-riduttori/1'
                for window in application.get_windows():
                    window.destroy()
            assert (app_paths.config_dir()/'ui-preferences.json').is_file()
            print(json.dumps(dict(installed_smoke='passed', runtime=result,
                                  stl_bytes=assembly.stat().st_size, step_files=len(list(assets.glob('*.step')))), indent=2))
    for path, digest in before.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, f'Resource changed: {path}'


if __name__ == '__main__':
    main()
