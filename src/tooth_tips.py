# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Member controls and exact-source routing; all tooth construction runs in Rust."""

KEYS = ('topping_mm', 'semitopping_mm', 'semitopping_angle_deg')
SUPPORTED = {'spur', 'helical', 'double', 'parallel', 'internal', 'planetary', 'wolfrom', 'rack'}


def members(family, variant=None):
    if family in ('spur', 'helical', 'double'):
        return [('', 'Gear')]
    if family == 'parallel':
        from parallel_multistage import count
        return [(role + (str(stage) if stage > 1 else ''),
                 f'Stage {stage} {label.lower()}')
                for stage in range(1, count({'variant': variant}) + 1)
                for role, label in [('pinion', 'Pinion'), ('wheel', 'Wheel')]]
    if family == 'internal':
        return [('pinion', 'Pinion'), ('ring', 'Internal ring')]
    if family == 'planetary':
        return [(role + (str(stage) if stage > 1 else ''), f'Stage {stage} {label.lower()}')
                for stage in range(1, 3 if variant in ('two_stage', 'two_stage_double') else 2)
                for role, label in [('sun', 'Sun'), ('planet', 'Planets'), ('ring', 'Ring')]]
    if family == 'wolfrom':
        return [('sun', 'Sun'), ('planet', 'First planet rim'), ('planet2', 'Second planet rim'),
                ('ring', 'Fixed ring'), ('output_ring', 'Output ring')]
    if family == 'rack':
        return [('pinion', 'Pinion'), ('rack', 'Rack')]
    return []


def key(role, name):
    return f'{role}_{name}' if role else name


def specs(family, variant=None):
    return [(key(role, name), f'{label} {caption}', default, low, high, step)
            for role, label in members(family, variant)
            for name, caption, default, low, high, step in (
                ('topping_mm', 'topping removal [mm]', 0, 0, 100, .01),
                ('semitopping_mm', 'semitopping height [mm]', 0, 0, 100, .01),
                ('semitopping_angle_deg', 'semitopping angle [°]', 45, 1, 80, 1))]


def parameters(values, role=''):
    # Keep PreciseFloat expression objects intact until rust_geometry serializes.
    return {name: values[key(role, name)] for name in KEYS if key(role, name) in values}


def group(family, variant, field):
    for role, label in members(family, variant):
        if field in {key(role, name) for name in KEYS}:
            return f'tooth_tips_{role}', f'{label} · tooth tips'
    return None


def verify_internal_pair(pinion, ring, zp, zr, backlash):
    """Recheck the changed actual polygons; do not reuse an untreated certificate."""
    if not any(p.profile_metadata.get('tooth_profile',{}).get('tip_treatment') for p in (pinion,ring)):
        return None
    from math import atan2,hypot
    from geometry import transformed
    from internal_mesh import verify_internal_polygon_pair
    dx=pinion.center[0]-ring.center[0];dy=pinion.center[1]-ring.center[1]
    angle=atan2(dy,dx)
    result=verify_internal_polygon_pair(transformed(pinion.outer,angle=-angle),
        transformed(ring.holes[0],angle=-angle),0,0,zp,zr,
        center_distance_mm=hypot(dx,dy),budget=4096,backlash_mm=backlash)
    if result['status']!='clear':
        raise ValueError('Modified internal tooth tips: neutral transverse polygon clearance is unresolved.')
    result['source']='actual tip-treated pinion and ring polygons, transformed to their common centre line'
    return result
