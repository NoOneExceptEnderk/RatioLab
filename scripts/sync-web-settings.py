#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Mirror only the desktop's public UI catalogs; never load GTK or geometry."""
import argparse
import ast
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def catalog(root=ROOT):
    def module(name):
        spec = importlib.util.spec_from_file_location(name, root/'src'/f'{name}.py')
        result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
        return result
    theme = module('theme_preferences'); mouse = module('mouse_navigation')
    # Keyboard data precedes the GTK-dependent normalizer. Evaluate only these
    # reviewed literal/comprehension assignments, with no imports or UI code.
    names = {'COMMANDS', 'DEFAULTS', 'PRESETS', '_ORTHOGRAPHIC', '_OVERRIDES'}
    tree = ast.parse((root/'src/keyboard_shortcuts.py').read_text())
    assignments = [n for n in tree.body if isinstance(n, ast.Assign) and
                   len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and n.targets[0].id in names]
    values = {'__builtins__': {}, 'enumerate': enumerate, 'dict': dict, 'str': str}
    exec(compile(ast.Module(body=assignments, type_ignores=[]), '<keyboard UI catalog>', 'exec'), values)
    palettes = {mode: {preset: dict(colors=theme.palette(mode, preset=preset),
                                    viewport=theme.viewport(mode, preset=preset))
                       for preset in theme.PRESETS} for mode in theme.MODES}
    return dict(themes=dict(presets=theme.PRESETS, interface_roles=theme.INTERFACE_ROLES,
                           view_roles=theme.VIEW_ROLES, palettes=palettes),
                mouse=dict(profiles=mouse.PROFILES, summaries=mouse.SUMMARIES),
                keyboard=dict(commands=values['COMMANDS'], presets=values['PRESETS'],
                              bindings={key: dict(values['DEFAULTS'], **value)
                                        for key, value in values['_OVERRIDES'].items()}))


def source(root=ROOT):
    return ('// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk\n'
            '// SPDX-License-Identifier: GPL-3.0-only\n'
            '// Generated from the desktop UI catalogs by scripts/sync-web-settings.py.\n'
            'export const UI_CATALOG = '+json.dumps(catalog(root), ensure_ascii=False, indent=2)+';\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--check', action='store_true')
    args = parser.parse_args(); path = ROOT/'webapp/ui-catalog.js'; expected = source()
    if args.check:
        if not path.is_file() or path.read_text() != expected:parser.exit(1, 'Web settings catalog differs from desktop; run scripts/sync-web-settings.py.\n')
    else:path.write_text(expected)
