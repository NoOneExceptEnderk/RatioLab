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
    detail_label = label(detail, 'result-detail') if detail else None
    if detail_label:
        box.append(detail_label)
    box.result_value = number
    box.result_detail = detail_label
    return box


def clear(box):
    while (child := box.get_first_child()):
        box.remove(child)


def items(design):
    """Present existing calculation values; do not introduce a second solver."""
    a, v = design.analysis, design.values
    if design.family == 'rack':
        q=a['rack'];return [('Travel per revolution',f"{q['travel_per_revolution_mm']:.4f}",'mm/rev','Pinion rotation → rack translation'),
            ('Linear speed',f"{a['linear_output']['velocity_mm_s']:+.4f}",'mm/s','Along world +X'),
            ('Working stroke',f"±{q['travel_limits_mm'][1]:.4f}",'mm','Preview stops at the travel limit')]
    if design.family == 'differential':
        q = a['kinematics']['rates_rpm']
        if v.get('configuration','wrist')=='classic':
            return [('Carrier input',f'{q["carrier"]:+.3g}','rpm',f'Prescribed B−A: {v["output_difference_rpm"]:+g} rpm'),
                    ('Side output A',f'{q["side_a"]:+.3g}','rpm','About world +X'),
                    ('Side output B',f'{q["side_b"]:+.3g}','rpm','About world +X')]
        return [('Carrier tilt', f'{q["carrier"]:+.3g}', 'rpm', 'About the common input axis'),
                ('Output spin', f'{q["output_spin"]:+.3g}', 'rpm', 'Relative to the moving carrier'),
                ('Input speeds A / B', f'{q["input_a"]:+g} / {q["input_b"]:+g}', 'rpm', 'Both signs measured about world +X')]
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
    if design.family == 'bevel':
        q=a['bevel_pair']
        result[0]=('Effective ratio', f'{ratio:+.4g}', ':1', 'Signs about pinion +X and wheel +Z')
        result.append(('Pitch cone angles', f'{q["pinion_pitch_angle_deg"]:.3f} / {q["wheel_pitch_angle_deg"]:.3f}', '°', 'Shaft angle 90°'))
    elif design.family == 'face':
        q=a['face_gear'];result[0]=('Effective ratio',f'{ratio:+.4g}',':1','Signs about pinion +X and face wheel +Z')
        result.append(('Tooth-band width',f"{v['width']:g}",'mm','Along pinion shaft · shaft angle 90°'))
        if v['offset']:
            result[-1]=('Shaft offset',f"{v['offset']:+g}",'mm','Skew axes · directions 90°')
    elif design.family == 'hypoid':
        result[0]=('Effective ratio', f'{ratio:+.4g}', ':1', 'Signs about offset pinion +X and wheel +Z')
        result.append(('Shaft offset',f'{v["offset"]:+g}','mm','90° shaft directions · offset along world Y'))
    elif match:
        result.append(('Housing diameter', match.group(1), 'mm',
                       'Nominal housing envelope'))
    elif 'parallel_train' in a:
        distances = ' / '.join(f"{q['center_distance_mm']:g}" for q in a['meshes'])
        result.append(('Stage distances', distances, 'mm', 'Stage 1 / 2' + (' / 3' if len(a['meshes']) == 3 else '')))
    elif 'center_distance_mm' in a:
        result.append(('Centre distance', f'{a["center_distance_mm"]:.3f}', 'mm', 'Axis spacing'))
    elif a.get('meshes'):
        result.append(('Centre distance', f'{a["meshes"][0]["center_distance_mm"]:.3f}', 'mm', 'Axis spacing'))
    else:
        result.append(('Flexible body length', f'{v["cup_length"]:g}', 'mm', 'Prescribed flexible-body geometry'))
    return result


def update(app, design):
    results = items(design)
    # Retain widgets and selection/focus during live speed changes. Rebuild
    # only when the kind of result changes (family, arrangement or units).
    shape = [(title, unit, bool(detail)) for title, _, unit, detail in results]
    if getattr(app, '_result_shape', None) == shape:
        child = app.metric_cards.get_first_child()
        for _, value, _, detail in results:
            box = child.get_child()
            if box.result_value.get_text() != value:box.result_value.set_text(value)
            if box.result_detail and box.result_detail.get_text() != detail:box.result_detail.set_text(detail)
            child = child.get_next_sibling()
        return
    clear(app.metric_cards)
    for title, value, unit, detail in results:
        app.metric_cards.insert(card(title, value, unit, detail), -1)
    app._result_shape = shape
