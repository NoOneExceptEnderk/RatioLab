# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
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
            features = _features_check(output, design)
            previews = []
            if gui:
                previews = _workspace_check(config, output)
            result.update(self_test='passed', families=len(FAMILIES),
                          step_files=len(list(assets.glob('*.step'))), stl_bytes=assembly.stat().st_size,
                          features=features,
                          preview_families=previews,
                          workspace_export='passed' if gui else 'not requested')
    return result


def _features_check(output, design):
    """Exercise the six new feature areas in the actual installed runtime."""
    from copy import deepcopy
    import hashlib
    from xml.etree import ElementTree
    from geometry import Design, Part, generate
    from project_document import Document, Store, atomic_json
    from combination_search import search, Settings as SearchSettings
    from interference import analyze, Settings as InterferenceSettings
    from motion import MotionPlan
    import component_geometry
    import selected_export

    snapshot = dict(family=design.family, values={design.family: design.values},
                    raw={design.family: {'width': str(design.values['width'])}})
    document = Document(snapshot)
    changed = deepcopy(snapshot)
    changed['raw'][design.family]['width'] = '12.5'
    document.record(changed)
    store = Store(output/'project history Ω')
    store.checkpoint(document)
    recovered = store.read_recovery(store.session, {design.family})
    if not recovered.dirty or recovered.current != changed:
        raise RuntimeError('Installed project recovery failed')
    document.undo()
    if document.dirty:
        raise RuntimeError('Installed Undo did not restore the checkpoint')
    document.redo()
    target = output/'project history Ω'/'saved.json'
    atomic_json(target, document.current)
    document.mark_saved(target)
    if document.dirty or json.loads(target.read_text(encoding='utf-8')) != changed:
        raise RuntimeError('Installed project save/Redo failed')

    gear = generate('spur').parts[0]
    if not gear.profile_metadata['tooth_profile']['generated']:
        raise RuntimeError('Generated tooth profile is missing')
    base = generate('parallel', dict(pinion=20, wheel=60)).values
    found = search('parallel', base, {'wheel': (60, 66)},
                   SearchSettings(target=3, tolerance_percent=0, max_seconds=30))
    if not found.complete or len(found.proposals) != 1 or found.proposals[0].ratio != -3:
        raise RuntimeError('Installed combination search failed')

    square = [(0, 0), (2, 0), (2, 2), (0, 2)]
    first = Part('A', square, width=2)
    second = Part('B', square, width=2, center=(4, 0))
    pair = Design('spur', {'input_rpm': 0}, [first, second])
    checked = analyze(pair, InterferenceSettings(max_seconds=30), plan=MotionPlan())
    if (not checked.coverage_complete or len(checked.rows) != 1
            or checked.rows[0]['kind'] != 'Separated' or abs(checked.rows[0]['distance']-2) > 1e-9):
        raise RuntimeError('Installed interference/distance check failed')
    hit = component_geometry.pick((1, 1, 10), (0, 0, -1),
                                  [(0, component_geometry.triangles(first))])
    if hit is None or hit[0] != 0 or abs(hit[1][2]-2) > 1e-9:
        raise RuntimeError('Installed component picking failed')
    if component_geometry.distance((1, 1, 2), (4, 1, 2)) != 3:
        raise RuntimeError('Installed surface measurement failed')

    for kind in ('step', 'profiles'):
        folder = selected_export.export(design, [0], kind, output/('selected '+kind+' Ω'))
        scope = json.loads((folder/'selection.json').read_text(encoding='utf-8'))
        if scope['source_indices'] != [1] or scope['complete_assembly']:
            raise RuntimeError('Installed selected export has incorrect scope')
        manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
        for record in manifest['files']:
            if hashlib.sha256((folder/record['path']).read_bytes()).hexdigest() != record['sha256']:
                raise RuntimeError('Installed selected export checksum mismatch')
        if kind == 'step':
            if not (folder/'assembly.step').read_text(encoding='utf-8').startswith('ISO-10303-21;'):
                raise RuntimeError('Installed standalone STEP missing')
        else:
            svg = list((folder/'profiles').glob('*.svg'))
            dxf = list((folder/'profiles').glob('*.dxf'))
            if not svg or len(svg) != len(dxf):
                raise RuntimeError('Installed SVG/DXF profiles missing')
            for path in svg:
                ElementTree.parse(path)
    return {name: 'passed' for name in ('standalone_cad_profiles', 'project_history_recovery',
             'generated_profiles', 'interference_distance', 'combination_search', 'component_selection_export')}


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
        project_path = application.output_dir/'workspace.config.json'
        if not application.save_project(path=project_path):
            raise RuntimeError('Workspace configuration could not be saved')
        if application.document.dirty or application.document.path != project_path:
            raise RuntimeError('Workspace save did not establish a clean document checkpoint')
        if json.loads(project_path.read_text(encoding='utf-8'))['format'] != 'solidcraft-riduttori/1':
            raise RuntimeError('Workspace configuration format changed')
        for controller in (application.interference, application.combination_search, application.components):
            controller.open()
            wait_for(lambda: controller.window is not None and controller.window.get_visible())
            controller.window.close()
        application.export()
        wait_for(lambda: not application.busy and list(application.output_dir.glob('*.package/manifest.json')))
        package = next(application.output_dir.glob('*.package'))
        for suffix in ('.config.json', '.script.json', '.stl', '.png', '.bom.json', '.calculations.txt'):
            if not list(package.glob('*'+suffix)):
                raise RuntimeError('Workspace export missing '+suffix)
        if not list(package.glob('assets/*.step')):
            raise RuntimeError('Workspace STEP assets missing')
        if not (package/'assembly.step').is_file() or not (package/'profiles.json').is_file():
            raise RuntimeError('Workspace standalone CAD/profile export missing')
        import cairo
        image = cairo.ImageSurface.create_from_png(str(next(package.glob('*.png'))))
        pixels = bytes(image.get_data())
        if not pixels or not any(pixels[i:i+4] != pixels[:4] for i in range(4, len(pixels), 4)):
            raise RuntimeError('Workspace exported a blank preview image')
        import io
        from geometry import FAMILIES, generate
        previews = []
        for family in FAMILIES:
            application.load_config_data(dict(format='solidcraft-riduttori/1', family=family,
                                               parameters=generate(family).values))
            wait_for(lambda: not application.pending and application.canvas.design.family == family)
            canvas = application.canvas
            canvas.set_motion_playing(False)
            canvas.motion_enabled = True
            canvas.motion_phase = 1.25
            captured = []
            canvas.capture_png(lambda data, error: captured.append((data, error)))
            if not captured or captured[0][1] is not None:
                raise RuntimeError('Animated preview capture failed: '+family)
            image = cairo.ImageSurface.create_from_png(io.BytesIO(captured[0][0]))
            pixels = bytes(image.get_data())
            if not pixels or not any(pixels[i:i+4] != pixels[:4] for i in range(4, len(pixels), 4)):
                raise RuntimeError('Animated preview is blank: '+family)
            previews.append(family)
        return previews
    finally:
        for window in application.get_windows():
            window.destroy()
