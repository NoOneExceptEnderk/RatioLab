# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Fixed-axis cylindrical reducers: involute geometry and nominal shafts."""
from math import pi, hypot
from parameter_errors import ParameterError
from geometry import gear_part, Part, circle
from engineering import mesh
from tooth_tips import parameters as tip_parameters

def build_train(d):
    if d.family == 'parallel':
        from parallel_multistage import count, build
        if count(d.values) > 1:
            return build(d)
    v = d.values
    variant = v['variant']
    double = variant == 'double'
    beta = v.get('helix', 0)
    m = v['module']
    w = v['width']
    pa = v['pressure']
    j = v['backlash']
    gap = v.get('gap', 0)
    if double and gap >= min(w, v.get('width2', w)) - 1:
        raise ParameterError('groove.width', ('gap','width'), 'The groove must leave at least 1 mm of teeth in each stage.', 'Reduce the groove or increase the face width.')
    if v['wheel'] <= v['pinion']:
        raise ParameterError('parallel.reduction', ('pinion','wheel'), 'For a reducer, choose more driven wheel teeth than pinion teeth.', 'Increase the wheel tooth count or reduce the pinion tooth count.', limits={'pinion':dict(upper=v['wheel']-1),'wheel':dict(lower=v['pinion']+1)})
    internal_plan = None
    if d.family == 'internal':
        from internal_mesh import plan_fixed_internal_pair
        internal_plan = plan_fixed_internal_pair(v['pinion'],v['wheel'],m,pa,beta,j)

    def pair(z1, z2, module, width, shift=0, extra=0, internal=False):
        return mesh(z1, z2, module, pa, beta, (width - gap) / 2 if double else width, shift, extra, internal, backlash=j,internal_plan=internal_plan if internal else None,
                    tooth_tips1=tip_parameters(v,'pinion'),tooth_tips2=tip_parameters(v,'ring' if internal else 'wheel'))
    first = pair(v['pinion'], v['wheel'], m, w, v.get('profile_shift', 0), v.get('center_extra', 0), d.family == 'internal')
    d.analysis['meshes'] = [first]
    first['torque_factor'] = 1
    a1 = first['center_distance_mm']
    r1 = v['wheel'] / v['pinion']
    parts = []

    def gear(name, z, module, width, bore, center, phase=0, helix=0, zoff=0, internal=False, shift=0,ha=1,minimum_join_radius_mm=None,rack_tip_radius_mm=None,safe_pair_sampling=False):
        p = gear_part(name, z, module, pa, j, width, bore, center, phase, helix, internal, v.get('rim', 5), zoff, shift,
            ha=ha,minimum_join_radius_mm=minimum_join_radius_mm,rack_tip_radius_mm=rack_tip_radius_mm,safe_pair_sampling=safe_pair_sampling,
            **tip_parameters(v,'ring' if internal else 'pinion' if 'Pinion' in name or 'pinion' in name else 'wheel'))
        if internal_plan is not None:
            p.profile_metadata['tooth_profile']['construction_version']=internal_plan['construction_version']
        if double:
            p.double = True
            p.gap = gap
            p.core_radius = min((hypot(x, y) for x, y in p.outer)) * 0.96
            if not internal and bore / 2 >= p.core_radius - 0.25:
                raise ValueError('Bore too large for the continuous double helix hub.')
        d.parts.append(p)
        parts.append(p)
        return p

    def shaft(name, bore, start, end, center):
        if bore:
            d.parts.append(Part(name, circle(bore / 2), [], end - start, start, center, role='support', color=(0.65, 0.72, 0.8)))
    if d.family == 'internal':
        gear('Pinion_input', v['pinion'], m, w, v['bore'], (a1, 0), helix=beta,
             rack_tip_radius_mm=internal_plan['pinion_rack_tip_radius_mm'],safe_pair_sampling=True)
        gear('Ring_output', v['wheel'], m, w, 0, (0, 0), pi / v['wheel'], beta, internal=True,
             ha=internal_plan['ring_addendum_coefficient'],minimum_join_radius_mm=internal_plan['minimum_join_radius_mm'],safe_pair_sampling=True)
        from tooth_tips import verify_internal_pair
        verification=verify_internal_pair(parts[0],parts[1],v['pinion'],v['wheel'],j)
        if verification:
            first['internal_pair_construction']['verification']=verification
        shaft('Shaft_input', v['bore'], -8, w + 8, (a1, 0))
        d.analysis['signed_ratio'] = r1
        d.metrics = [f'Internal ring · reduction +{r1:.5g}:1', f'Centre distance {a1:.3f} mm · fixed axes, same rotation direction']
        d.requirements.append('Annular support, ring output flange, bearings, retainers and housing must be designed; no central shaft passes through the pinion.')
        d.notes.append('The pinion generating rack is paired with the ring active involute. A custom normal tool-tip radius can preserve full nominal contact; its actual value is in the calculation report. This is a virtual generating tool, not a selected commercial cutter or a tooth-root strength verification. Profile sampling removes material at the pinion root and ring active flanks within its reported bound.')
    else:
        x = v['profile_shift']
        gear('S1_Pinion', v['pinion'], m, w, v['bore'], (0, 0), helix=beta, shift=x)
        gear('S1_Wheel', v['wheel'], m, w, v['output_bore'], (a1, 0), pi + pi / v['wheel'], -beta, shift=-x)
        if d.family == 'parallel':
            d.analysis['signed_ratio'] = -r1
            shaft('Shaft_input', v['bore'], -8, w + 8, (0, 0))
            shaft('Shaft_output', v['output_bore'], -8, w + 8, (a1, 0))
            d.metrics = [f'Parallel shafts · reduction −{r1:.5g}:1', f'Centre distance {a1:.3f} mm · opposite rotation direction']
    if double:
        d.notes.append('Double helix: εβ is calculated on one active half, excluding the groove. Axial thrust cancellation assumes symmetric load sharing; Fa is the full torque reference for a single helix.')
    d.requirements.append('Nominal shafts without keys or retainers; supports, bearings, fasteners and housing must be designed. The optional shaft-support catalog covers both parallel shafts, or only the internal pair pinion; an internal ring needs a dedicated annular support.')
    d.notes.append('Total nominal pair backlash is shared between the two profiles. External profile shift is balanced, x1 = −x2; additional centre distance further increases backlash. External roots use a rounded normal rack envelope with undercut trimming. Internal ring roots use a tangent circular construction, not a pinion-cutter envelope; manufacturing and cutter interference remain unverified.')
