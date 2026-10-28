# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Read-only geometric results, separate from nominal operating assumptions."""
import re
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk


def label(value, style):
    widget = Gtk.Label(label=value, xalign=0, wrap=True, css_classes=[style])
    widget.set_max_width_chars(27)
    return widget


def card(title, value, unit='', detail='', compact=False):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
    box.add_css_class('metric-card')
    box.append(label(title, 'result-title'))
    line = Gtk.Box(spacing=5)
    box.append(line)
    number = label(value, 'result-small' if compact else 'result-number')
    number.set_selectable(True)
    line.append(number)
    if unit:
        suffix = label(unit, 'result-unit')
        suffix.set_valign(Gtk.Align.END)
        suffix.set_margin_bottom(3)
        line.append(suffix)
    if detail:
        box.append(label(detail, 'result-detail'))
    return box


def clear(box):
    while (child := box.get_first_child()):
        box.remove(child)


def items(design):
    """Present existing calculation values; do not introduce a second solver."""
    a, v = design.analysis, design.values
    ratio, output = a.get('signed_ratio'), a.get('output', {})
    if ratio is None:
        gear = a.get('gear', {})
        return [('Pitch diameter', f'{2*gear["pitch_radius"]:.3f}', 'mm', 'Reference pitch circle'),
                ('Tooth count', str(v['teeth']), '', f'Normal module {v["module"]:g} mm'),
                ('Face width', f'{v["width"]:g}', 'mm', 'Axial gear width')]
    result = [('Effective ratio', f'{ratio:+.4g}', ':1',
               'Same rotation direction' if ratio>0 else 'Opposite rotation direction'),
              ('Output speed', f'{output["rpm"]:.2f}', 'rpm',
               f'At {a["input"]["rpm"]:g} rpm input')]
    # Housing envelopes are already calculated by the assembly generators.
    match = re.search(r'housing (?:diameter |Ø )([0-9.]+) mm', ' · '.join(design.metrics), re.I)
    if match:
        result.append(('Housing diameter', match.group(1), 'mm',
                       'Nominal housing envelope'))
    elif 'center_distance_mm' in a:
        result.append(('Centre distance', f'{a["center_distance_mm"]:.3f}', 'mm', 'Axis spacing'))
    elif a.get('meshes'):
        result.append(('Centre distance', f'{a["meshes"][0]["center_distance_mm"]:.3f}', 'mm', 'Axis spacing'))
    else:
        result.append(('Flexible body length', f'{v["cup_length"]:g}', 'mm', 'Geometric study'))
    return result


def update(app, design):
    clear(app.metric_cards)
    for title, value, unit, detail in items(design):
        app.metric_cards.insert(card(title, value, unit, detail), -1)
