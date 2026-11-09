# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Explicit mechanical audit of unchanged fixed-axis cylindrical pairs.

Rust owns the equations, whole-curve enclosures and continuous rotation checks.
The adapter checks that the actual design still has the supported construction;
it must not qualify cached analysis while ignoring an edited component.
"""
from math import hypot, pi

from engineering import mesh
from geometry import gear_part
from rust_geometry import call


def audit_pair(z1, z2, module, *, pressure=20, helix=0, width=10,
               profile_shift=0, center_extra=0, internal=False, backlash=.15,
               double_helix=False, gap=0, profile_enclosure_mm=.0001,
               budget=4096, max_depth=20, phase1_rad=0, phase2_rad=None,
               helix2_deg=None, internal_plan=None, pinion_rack_tip_radius_mm=None, check=None,
               tooth_tips1=None, tooth_tips2=None):
    """Audit a specified ideal pair; see returned scopes, not just its status.

    Phases are radians. External axes are O1=(0,0), O2=(a,0); internal
    axes are O1=(a,0), O2=(0,0). Positive rotation is counterclockwise.
    Backlash is the total nominal transverse pair allowance in millimetres.
    """
    parameters = dict(z1=z1, z2=z2, m=module, pressure=pressure, beta=helix,
        width=width, x=profile_shift, center_extra=center_extra, internal=internal,
        backlash=backlash, double_helix=double_helix, gap=gap,
        profile_enclosure_mm=profile_enclosure_mm, budget=budget,
        max_depth=max_depth, phase1_rad=phase1_rad, internal_plan=internal_plan,
        tooth_tips1=tooth_tips1,tooth_tips2=tooth_tips2)
    if pinion_rack_tip_radius_mm is not None:
        parameters['pinion_rack_tip_radius_mm'] = pinion_rack_tip_radius_mm
    if phase2_rad is not None:
        parameters['phase2_rad'] = phase2_rad
    if helix2_deg is not None:
        parameters['helix2_deg'] = helix2_deg
    return call('cylindrical_pair_audit', parameters, check=check)


def audit_design(design, *, profile_enclosure_mm=None, budget=None,
                 max_depth=20, check=None):
    """Check the actual, unchanged parallel/internal spur/helical/double pair.

    Added cuts, placements, explicit meshes and other families require separate
    verification and are rejected. Preview/export quality does not change the
    nominal source being audited. No app state or geometry is modified.
    """
    if design.family not in ('parallel', 'internal'):
        raise ValueError('Mechanical audit currently supports parallel and internal fixed-axis cylindrical pairs.')
    v = design.values
    if v['variant'] not in ('spur', 'helical', 'double'):
        raise ValueError('Unsupported cylindrical pair variant.')
    internal = design.family == 'internal'
    double = v['variant'] == 'double'
    width = v['width']
    gap = v.get('gap', 0) if double else 0
    beta = v.get('helix', 0)
    internal_plan = None
    if internal:
        from internal_mesh import plan_fixed_internal_pair
        internal_plan=plan_fixed_internal_pair(v['pinion'],v['wheel'],v['module'],v['pressure'],beta,v['backlash'])
    if profile_enclosure_mm is None:
        profile_enclosure_mm=min(.0001,5e-6*float(v['module'])) if internal else .0001
    if budget is None:budget=16384 if internal else 4096
    shift = 0 if internal else v['profile_shift']
    extra = 0 if internal else v['center_extra']
    effective = (width-gap)/2 if double else width
    from tooth_tips import parameters as tip_parameters
    tips1=tip_parameters(v,'pinion');tips2=tip_parameters(v,'ring' if internal else 'wheel')
    # Recompute from the exact current parameters, independently of the design's
    # potentially stale stored analysis. Then compare actual construction fields.
    pair = mesh(v['pinion'], v['wheel'], v['module'], v['pressure'], beta,
        effective, shift, extra, internal, backlash=v['backlash'],internal_plan=internal_plan,
        tooth_tips1=tips1,tooth_tips2=tips2)
    center = pair['center_distance_mm']
    expected = [gear_part('Pinion_input' if internal else 'S1_Pinion', v['pinion'],
        v['module'], v['pressure'], v['backlash'], width, v['bore'],
        (center, 0) if internal else (0, 0), helix=beta, shift=shift,
        rack_tip_radius_mm=internal_plan['pinion_rack_tip_radius_mm'] if internal else None,safe_pair_sampling=internal,**tips1),
        gear_part('Ring_output' if internal else 'S1_Wheel', v['wheel'],
        v['module'], v['pressure'], v['backlash'], width,
        0 if internal else v['output_bore'], (0, 0) if internal else (center, 0),
        pi/v['wheel'] if internal else pi+pi/v['wheel'],
        beta if internal else -beta, internal=internal, rim=v.get('rim', 5), shift=-shift,
        ha=internal_plan['ring_addendum_coefficient'] if internal else 1,
        minimum_join_radius_mm=internal_plan['minimum_join_radius_mm'] if internal else None,safe_pair_sampling=internal,**tips2)]
    if double:
        for part in expected:
            part.double = True
            part.gap = gap
            part.core_radius = min(hypot(x, y) for x, y in part.outer)*.96
    actual = [part for part in design.parts if part.role == 'gear']
    if len(actual) != 2:
        raise ValueError('Mechanical audit requires exactly the two unchanged nominal gears.')
    fields = ('outer', 'holes', 'width', 'z', 'center', 'twist', 'axis_x',
              'double', 'gap', 'core_radius', 'internal', 'stations', 'mesh', 'frame')
    for part, original in zip(actual, expected):
        if any(getattr(part, key) != getattr(original, key) for key in fields):
            raise ValueError('Mechanical audit requires unchanged nominal components with no added cuts or placement.')
    report = audit_pair(v['pinion'], v['wheel'], v['module'], pressure=v['pressure'],
        helix=beta, width=width, profile_shift=shift, center_extra=extra,
        internal=internal, backlash=v['backlash'], double_helix=double,
        gap=gap, profile_enclosure_mm=profile_enclosure_mm, budget=budget,
        max_depth=max_depth, internal_plan=internal_plan,check=check,tooth_tips1=tips1,tooth_tips2=tips2)
    report['source'] = dict(family=design.family, variant=v['variant'],
        parameters=dict(v), parts=[p.name for p in actual], unchanged_nominal_pair=True)
    return report
