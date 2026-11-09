# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Independent representations of one nominal construction; no GTK dependency.

Only procedural-sweep interpolation is adjustable here. Transverse profiles and
explicit stations/meshes retain their construction and separately stated limits.
An absent override preserves each Part's existing interpolation policy.
"""
from copy import copy
from dataclasses import replace
from math import isfinite

KEYS = frozenset(('preview_mm', 'export_mm'))
DEFAULT_MM = .02
PRESETS = (('Fast', .1), ('Standard', .02), ('Fine', .005))
SCOPE = ('Procedural sweep interpolation relative to sampled 2D contours only. '
         'Explicit stations/meshes retain their construction. Total tooth-profile, '
         'roundoff and file quantization error are not bounded by this setting.')


def normalize(value=None):
    if value is None:
        return {}
    if not isinstance(value, dict) or set(value)-KEYS:
        raise ValueError('Quality requires preview_mm and/or export_mm only.')
    result = {}
    for key, number in value.items():
        try:finite=isfinite(number) if isinstance(number,(int,float)) else False
        except OverflowError:finite=False
        if isinstance(number, bool) or not finite or number <= 0:
            raise ValueError(key+': a positive finite interpolation threshold in mm is required.')
        result[key] = number
    return result


def settings(design):
    return normalize(getattr(design, 'quality', None))


def with_quality(design, value):
    """Keep nominal parts, analysis, motion identity and selected-source indices."""
    value = normalize(value)
    if settings(design) == value:
        return design
    result = copy(design)
    result.quality = value
    return result


def part(design, source, purpose):
    if purpose not in ('preview', 'export'):
        raise ValueError('Representation purpose must be preview or export.')
    tolerance = settings(design).get(purpose+'_mm')
    if tolerance is None:
        return source
    # Geometry lists and exact numeric sources come from the same construction.
    # The Rust boundary freezes them into an owned snapshot before evaluation.
    return replace(source, surface_tolerance_mm=tolerance)


def representation(design, purpose):
    result = copy(design)
    result.parts = [part(design, p, purpose) for p in design.parts]
    return result


def project(design):
    result = dict(format='solidcraft-riduttori/1', family=design.family, parameters=design.values)
    if settings(design):
        result['quality'] = settings(design)
    return result


def summary(design):
    return dict(schema='ratiolab.representations/1', units='mm',
                requested=settings(design), fallback='per-part surface_tolerance_mm',
                scope=SCOPE)


def report(design, purpose):
    """Describe the actual sampled representation without modifying the source."""
    from solid_geometry import sampling_report
    result=dict(summary(design), purpose=purpose,
                components=[dict(index=i, name=p.name, **sampling_report(part(design,p,purpose)))
                            for i,p in zip(getattr(design,'source_indices',range(1,len(design.parts)+1)),design.parts)])
    from geometry_error_budget import available_report
    result['geometric_error_budget']=available_report(design,purpose)
    return result


def deviation(design, purpose):
    """Keep local interpolation and a qualified complete surface bound separate."""
    from solid_geometry import sampling_report
    from geometry_error_budget import available_report
    components = [sampling_report(part(design, source, purpose)) for source in design.parts]
    bounded = bool(components) and all(item['status'] == 'bounded' and
        item.get('interpolation_bound_mm') is not None for item in components)
    budget = available_report(design, purpose)
    complete = budget.get('status') == 'bounded_complete_surface'
    return dict(interpolation_mm=max(item['interpolation_bound_mm'] for item in components)
                    if bounded else None,
                model_mm=budget.get('total_error_bound_mm') if complete else None,
                reason=budget.get('reason') or budget.get('total_error_reason'),
                scope=SCOPE, output_bounds=budget.get('output_bounds', {}))
