#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Regenerate static browser illustrations from the original Cairo drawings.

Development only: PYTHONPATH=src:webapp python3 scripts/generate-web-help.py
Requires pycairo. Browser use and the stdlib-only web builder do not need Cairo.
PNG illustrations are lossless at 2x logical size with vertical padding for
multiline annotations; quantities remain schematic.
Font rendering may differ with Cairo/font versions. --check compares this host's
rendered data with the checked-in asset. The asset records source SHA256 values.
"""
import argparse
import base64
from hashlib import sha256
from io import BytesIO
import itertools
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'webapp')]
import engine_bridge as bridge
import geometry
import parameter_help
import parameter_help_diagrams as diagrams


def contexts(family):
    options = bridge.option_definitions(family)
    variants = [None]+[c['value'] for c in options.get('variant', {}).get('choices', [])]
    styles = [None]+[c['value'] for c in options.get('double_style', {}).get('choices', [])]
    hands = [-1, 1] if family == 'worm' else [1]
    for variant, style, hand in itertools.product(variants, styles, hands):
        yield {k:v for k,v in dict(variant=variant, double_style=style, worm_hand=hand).items() if v is not None}


def generate():
    import cairo
    images, entries, kinds = {}, {}, set()
    numbered_entries, numbered_images, annotations = {}, {}, {}
    for family in geometry.FAMILIES:
        for values in contexts(family):
            current = bridge.schema(family, values)
            for field in current['fields']+current['options']:
                key, help_data = field['key'], field['help']
                if not help_data:
                    continue
                help = parameter_help.lookup(family, key, values)
                context = bridge.help_diagram_context(family, key, values)
                if context in entries:
                    continue
                if diagrams.diagram_kind(family, key, help) == 'text':
                    entries[context] = None
                    numbered_entries[context] = None
                    continue
                surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 720, 480)
                info = diagrams.draw_diagram(None, cairo.Context(surface), 720, 480, help,
                                             key=key, family=family, values=values)
                stream = BytesIO(); surface.write_to_png(stream); data = stream.getvalue()
                digest = sha256(data).hexdigest(); images[digest] = 'data:image/png;base64,'+base64.b64encode(data).decode('ascii')
                entries[context] = digest; kinds.add(info.kind)
                surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 720, 480)
                numbered = diagrams.draw_diagram(None, cairo.Context(surface), 720, 480, help,
                    key=key, family=family, values=values, numbered=True)
                stream = BytesIO(); surface.write_to_png(stream); data = stream.getvalue()
                digest = sha256(data).hexdigest()
                numbered_entries[context] = digest
                numbered_images[digest] = 'data:image/png;base64,'+base64.b64encode(data).decode('ascii')
                annotations[digest] = list(numbered.annotations)
    sources = {path:sha256((ROOT/path).read_bytes()).hexdigest() for path in
               ('src/parameter_help.py', 'src/parameter_help_diagrams.py', 'webapp/engine_bridge.py', 'scripts/generate-web-help.py')}
    return dict(format='ratiolab-help-illustrations/1', sources=sources,
                logical_size=[360,220], pixel_size=[720,480],
                renderer=dict(cairo=cairo.cairo_version_string(), pycairo=cairo.version, font='sans; canonical Cairo renderer'),
                description='Original RatioLab Cairo schematics; not exact model geometry. Development generator: scripts/generate-web-help.py.',
                kinds=sorted(kinds), entries=entries, images=images,
                numbered_entries=numbered_entries, numbered_images=numbered_images, annotations=annotations)


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--check',action='store_true'); args=parser.parse_args()
    target=ROOT/'webapp/help-illustrations.json'
    data=(json.dumps(generate(),sort_keys=True,separators=(',',':'))+'\n').encode()
    if args.check:
        if target.read_bytes()!=data: raise SystemExit('Help illustrations differ: regenerate with the documented development environment.')
    else: target.write_bytes(data)
    result=json.loads(data); print(f"{len(result['entries'])} contexts; {len(result['images'])} unique illustrations; {len(data)} bytes")


if __name__=='__main__': main()
