# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Theoretical involute measurement geometry, independent of GTK and sampling.

Lengths are mm, angles named ``*_rad`` are radians. References and the
deliberately limited supported domain are in docs/technical/calculations.md.
"""
from math import atan, cos, hypot, isfinite, pi, sqrt, tan


def wildhaber_span(geometry):
    from rust_geometry import call
    if not isfinite(geometry['helix_angle_abs_deg']):
        raise ValueError('Invalid helix angle for span measurement.')
    return call('measurement_span',dict(geometry=geometry))


def over_gauges(geometry,diameter_mm,gauge_type='ball'):
    from rust_geometry import call
    if isinstance(diameter_mm,bool):
        raise ValueError('Gauge diameter must be a positive finite length in mm.')
    return call('measurement_gauges',dict(geometry=geometry,diameter_mm=diameter_mm,gauge_type=gauge_type))


def default_gauge(geometry):
    from rust_geometry import call
    return call('measurement_default',dict(geometry=geometry))


def gauge_report_lines(result):
    """Shared human-readable output for standard and explicitly selected reports."""
    lines = ['Theoretical balls / rollers: '+result['scope']+'.']
    if result['status'] == 'ok':
        lines.append(f"{result['gauge_type'].capitalize()} diameter {result['gauge_diameter_mm']:.6f} mm; {result['parity']} teeth; {result['dimension_kind']} M = {result['dimension_mm']:.6f} mm.")
        lines.append(f"Both contacts R {result['contact_radius_mm']:.6f} mm; useful involute root/tip margins {result['root_margin_mm']:.6f}/{result['tip_margin_mm']:.6f} mm.")
    else:
        if 'gauge_diameter_mm' in result:
            lines.append(f"{result['gauge_type'].capitalize()} diameter {result['gauge_diameter_mm']:.6f} mm.")
        lines.append('Unavailable ('+result['status']+'): '+result['reason'])
    if 'diameter_selection_basis' in result:
        lines.append('Diameter selection: '+result['diameter_selection_basis']+'.')
    if 'gauge_note' in result:
        lines.append(result['gauge_note'])
    lines.append(result['basis']+'.')
    return lines


def measurement_query(design, source_index, diameter_mm, gauge_type='ball', revision=None):
    """Read-only query on a generated, explicitly selected cylindrical member."""
    from copy import deepcopy
    if design.family not in ('spur', 'helical', 'double', 'parallel', 'internal', 'planetary'):
        raise ValueError('This family has no supported cylindrical gauge measurement.')
    if isinstance(source_index, bool) or not isinstance(source_index, int) or not 0 <= source_index < len(design.parts):
        raise ValueError('Select an existing source component.')
    part = design.parts[source_index]
    profile = part.profile_metadata.get('tooth_profile', {})
    if 'measurement_geometry' not in profile:
        raise ValueError('The selected component has no cylindrical involute profile.')
    result = over_gauges(profile['measurement_geometry'], diameter_mm, gauge_type)
    return dict(format='ratiolab-gauge-measurement/1', family=design.family,
                source_position=source_index+1, part=part.name, revision=revision,
                parameters=deepcopy(design.values), geometry=deepcopy(profile['measurement_geometry']),
                result=result)


def measurement_query_text(query):
    return '\n'.join(['RatioLab theoretical gauge measurement',
                      f"Family: {query['family']} · source component {query['source_position']}: {query['part']}",
                      f"Document revision: {query['revision']}",
                      'Read-only query; project parameters have not been changed.', '']+
                     gauge_report_lines(query['result']))+'\n'


def export_measurement(query, target):
    """Publish selected query text and complete context as one new export folder."""
    import json
    from export_transaction import directory
    with directory(target) as staging:
        (staging/'measurement.json').write_text(json.dumps(query, indent=2, allow_nan=False)+'\n', encoding='utf-8')
        (staging/'measurement.txt').write_text(measurement_query_text(query), encoding='utf-8')
