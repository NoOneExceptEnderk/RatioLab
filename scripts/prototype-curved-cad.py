#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Export a bounded cylindrical CAD prototype; no installed CAD required."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from curved_cad import export
from geometry import generate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', type=Path, help='New output directory; existing results are never replaced.')
    parser.add_argument('--project', type=Path, help='Spur/helical project, or internal-pair project (exports the ring only).')
    parser.add_argument('--family',choices=('spur','helical','internal'),help='Default sample family when no project is supplied.')
    parser.add_argument('--tolerance-mm', type=float, default=.001, help='Continuous profile/surface approximation request, not a manufacturing tolerance.')
    args = parser.parse_args()
    config = json.loads(args.project.read_text(encoding='utf-8')) if args.project else dict(
        format='solidcraft-riduttori/1', family=args.family or 'spur', parameters={})
    if not isinstance(config, dict): parser.error('A RatioLab project must be a JSON object.')
    if config.get('family') not in ('spur','helical','internal'):
        parser.error('Only spur/helical gears and internal-pair rings are supported by this prototype.')
    if args.project and args.family:parser.error('Use either a project or a default family sample.')
    if config.get('format') != 'solidcraft-riduttori/1':
        parser.error('Unsupported project format.')
    if not isinstance(config.get('parameters'), dict):
        parser.error('Project parameters must be a JSON object.')
    design = generate(config['family'], config['parameters'], quality=config.get('quality'))
    target, info = export(design, args.target, tolerance_mm=args.tolerance_mm)
    profile = info['profile']
    print(json.dumps(dict(target=str(target), requested_curve_mm=profile['requested_curve_mm'],
        curve_interpolation_bound_mm=profile['curve_interpolation_bound_mm'],
        surface_interpolation_bound_mm=info.get('sweep',{}).get('surface_interpolation_bound_mm',profile['curve_interpolation_bound_mm']),
        profile_patches=len(info['patches']), approximation_pieces=len(profile['curves']),
        source_component_index=info.get('source_component_index',1),
        reader_verification=info['reader_verification']), indent=2))


if __name__ == '__main__': main()
