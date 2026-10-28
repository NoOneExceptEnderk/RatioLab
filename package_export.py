# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Complete package: publish after geometry, reports and preview all succeed."""
from pathlib import Path
import hashlib
import json

import bom
import cad_export
import profile_export
import stl_export
from export_transaction import directory


def export(design, config, target, png):
    """Export a snapshot, returning the published directory.

    png must be complete encoded bytes captured on GTK's main thread. No output
    directory is published before all writers finish. Script STEP references
    are relative to the package, so replay from that directory also works after
    moving the package. The legacy CAD command construction is preserved.
    """
    if not isinstance(png, bytes) or not png.startswith(b'\x89PNG\r\n\x1a\n') or not png.endswith(b'IEND\xaeB`\x82'):
        raise ValueError('The complete package requires a finished PNG preview.')
    scope=getattr(design,'export_scope',None)
    target = Path(target)
    with directory(target) as staging:
        cad_export.write_files(design, staging)
        profile_export.write_files(design, staging)
        assets = staging/'assets'
        design.prepare_assets(assets)
        commands = design.commands(assets)
        for command in commands:
            if command['command']=='file.insert_step':
                command['params']['path'] = 'assets/'+Path(command['params']['path']).name
        (staging/'model.script.json').write_text(json.dumps(dict(commands=commands),indent=2)+'\n',encoding='utf-8')
        (staging/'model.config.json').write_text(json.dumps(dict(config,selected_export=scope) if scope else config,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        stl_export.export(design,staging/'model')
        bom.export(design,staging/'model')
        (staging/'preview.png').write_bytes(png)
        (staging/'README.txt').write_text(
            ('RatioLab SELECTED COMPONENTS export · not a complete assembly\nSource configuration parameters/calculations are retained for reference. Regenerating them creates the source assembly; replay model.script.json for this subset.\n\n' if scope else 'RatioLab complete export\n\n')+
            'Units: millimetres. STEP and STL retain the nominal assembly coordinates.\n'+
            ('Only the explicitly selected source indices are included; no automatic supports, housing or hardware.\n' if scope else 'All components are included, also hidden supports, housing and simplified commercial envelopes.\n')+
            'assembly.step and step-parts/: standalone CAD solids; no SolidCraft installation is required to export them.\n'
            'step-info.json: cylinder promotion, sampled/CAD volume differences and representation limits.\n'
            'model.stl and model.stl-parts/: unchanged shared sampled geometry. Select mm when importing STL.\n'
            'profiles/ and profiles.json: local plane contours, holes, placement and section classification.\n'
            'Helical/deformed sections are NOT an extrusion profile or a manufacturing development.\n'
            'model.config.json: compatible solidcraft-riduttori/1 parameters.\n'
            'model.script.json and assets/: existing native-sketch/faceted-STEP SolidCraft command path.\n'
            'To replay the CAD script, open a terminal IN THIS PACKAGE DIRECTORY and run:\n'
            '  solidcraft-cli run model.script.json --out replay.step\n'
            'Relative STEP paths keep the script portable when the whole package is moved.\n'+
            ('preview.png: only selected components, nominal pose, current camera; no section/explosion.\n' if scope else 'preview.png: captured nominal motion pose; selected visibility/camera settings apply.\n')+
            'No strength, service-life or production certification is implied.\n'
            'manifest.json lists every package file and its SHA-256 checksum.\n',encoding='utf-8')
        if scope:(staging/'selection.json').write_text(json.dumps(scope,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        files = [dict(path=str(p.relative_to(staging)),bytes=p.stat().st_size,
                      sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(staging.rglob('*')) if p.is_file()]
        (staging/'manifest.json').write_text(json.dumps(dict(format='ratiolab-export/1',complete=True,
            complete_assembly=not bool(scope),scope=scope,units='mm',family=design.family,components=len(design.parts),files=files),indent=2)+'\n',encoding='utf-8')
    return target
