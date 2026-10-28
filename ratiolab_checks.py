"""Exercise a downloaded bundle without touching the user's preferences or CAD."""
import json
import os
from pathlib import Path
import tempfile
import time
from unittest.mock import patch


def self_test(gui=False):
    import app_paths
    from geometry import FAMILIES, generate
    from ratiolab_cli import diagnose
    import stl_export
    result = diagnose(gui=gui)
    with tempfile.TemporaryDirectory(prefix='ratiolab-check-') as temporary:
        profile = Path(temporary)
        environment = dict(XDG_CONFIG_HOME=str(profile/'config'),
                           XDG_DATA_HOME=str(profile/'data'),
                           APPDATA=str(profile/'roaming'), LOCALAPPDATA=str(profile/'local'))
        with patch.dict(os.environ, environment), patch.object(Path, 'home', return_value=profile):
            output = profile/'Export qualità Ω'
            app_paths.save_preferences(output_dir=str(output))
            if app_paths.saved_output_dir() != output:
                raise RuntimeError('Preferences round trip failed')
            for family in FAMILIES:
                if not generate(family).parts:
                    raise RuntimeError(f'No geometry generated for {family}')
            design = generate('helical')
            assets = design.prepare_assets()
            if not assets.is_relative_to(app_paths.default_output_dir()):
                raise RuntimeError('Generated assets escaped the temporary profile')
            if not list(assets.glob('*.step')):
                raise RuntimeError('STEP generation failed')
            assembly, parts = stl_export.export(design, output/'self-test')
            if assembly.stat().st_size <= 84 or not parts:
                raise RuntimeError('STL generation failed')
            config = dict(format='solidcraft-riduttori/1', family=design.family, parameters=design.values)
            saved = output/'self-test.config.json'
            saved.write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
            restored = json.loads(saved.read_text(encoding='utf-8'))
            if generate(restored['family'], restored['parameters']).parts != design.parts:
                raise RuntimeError('Configuration changed the generated geometry')
            if gui:
                _workspace_check(config, output)
            result.update(self_test='passed', families=len(FAMILIES),
                          step_files=len(list(assets.glob('*.step'))), stl_bytes=assembly.stat().st_size,
                          workspace_export='passed' if gui else 'not requested')
    return result


def _workspace_check(config, output):
    from app import ReducerApp
    from gi.repository import Gio, GLib
    application = ReducerApp()
    application.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
    application.register(None)
    application.activate()
    context = GLib.MainContext.default()

    def wait_for(condition):
        deadline = time.monotonic()+30
        while time.monotonic() < deadline:
            while context.pending():
                context.iteration(False)
            if condition():
                return
            time.sleep(.01)
        raise RuntimeError('Timed out checking the installed workspace')

    try:
        application.output_dir = output/'workspace'
        application.load_config_data(config)
        wait_for(lambda: application.canvas.gl and not application.pending)
        if application.canvas.failure:
            raise RuntimeError(application.canvas.failure)
        application.save_config()
        application.export()
        wait_for(lambda: not application.busy and list(application.output_dir.glob('*.png')))
        for suffix in ('.config.json', '.script.json', '.stl', '.png', '.bom.json', '.calcoli.txt'):
            if not list(application.output_dir.glob('*'+suffix)):
                raise RuntimeError('Workspace export missing '+suffix)
        if not list(application.output_dir.glob('*.assets/*.step')):
            raise RuntimeError('Workspace STEP assets missing')
    finally:
        for window in application.get_windows():
            window.destroy()
