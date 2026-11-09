#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Write a bounded, explicitly scoped cylindrical-pair mechanical audit."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from cylindrical_validation import audit_design
from geometry import generate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, help='New JSON report; existing files are never replaced.')
    parser.add_argument('--project', type=Path, help='Saved RatioLab parallel/internal project.')
    parser.add_argument('--family', choices=('parallel', 'internal'), help='Default pair when no project is supplied.')
    parser.add_argument('--profile-enclosure-mm', type=float,
                        help='Whole-profile approximation request for the clearance check; not a manufacturing tolerance.')
    parser.add_argument('--budget', type=int, help='Maximum intervals per continuous check (0..16384); automatic per family when omitted.')
    parser.add_argument('--max-depth', type=int, default=20, help='Maximum subdivision depth (0..20).')
    args = parser.parse_args()
    if args.project and args.family:
        parser.error('Use either a project or a default family sample.')
    config = json.loads(args.project.read_text(encoding='utf-8')) if args.project else dict(
        format='solidcraft-riduttori/1', family=args.family or 'parallel', parameters={})
    if (not isinstance(config, dict) or config.get('format') != 'solidcraft-riduttori/1'
            or config.get('family') not in ('parallel', 'internal')
            or not isinstance(config.get('parameters'), dict)):
        parser.error('Expected a saved parallel/internal RatioLab project.')
    if args.output.exists():
        parser.error('Refusing to replace an existing report.')
    design = generate(config['family'], config['parameters'], quality=config.get('quality'))
    report = audit_design(design, profile_enclosure_mm=args.profile_enclosure_mm,
        budget=args.budget, max_depth=args.max_depth)
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(report, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(report=str(args.output), status=report['status'],
        covered_checks_passed=report['covered_checks_passed'], unqualified=report['unqualified']), indent=2))
    return 0 if report['covered_checks_passed'] else 2


if __name__ == '__main__':
    sys.exit(main())
