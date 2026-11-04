# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Fixed-axis compound cylindrical gear trains. Frames/equations: docs/technical/parallel.md.

Shafts are parallel to +Z; turns change XY centre lines, not shaft axes.
Nonmating swept cylinders are a conservative full-rotation exclusion test.
"""
from math import cos, sin, pi, radians, hypot, prod

# Legacy spur keys remain unchanged in saved projects.
VARIANTS = {
    'two_stage': 'Two stages · spur', 'three_stage': 'Three stages · spur',
    'two_stage_helical': 'Two stages · helical', 'three_stage_helical': 'Three stages · helical',
    'two_stage_double': 'Two stages · double helical', 'three_stage_double': 'Three stages · double helical',
}
CATALOG_REASON = ('Multistage parallel shafts use manual shaft dimensions. '
                  'Automatic bearing seats and standard hardware cover single-stage pairs only.')
SELECTOR_NOTICE = ''


def count(values):
    variant = values.get('variant')
    if variant not in VARIANTS:
        return 1
    return 2 if variant.startswith('two_stage') else 3


def tooth_type(variant):
    if variant in ('helical', 'double'):
        return variant
    return variant.rsplit('_', 1)[-1] if variant in VARIANTS and variant.endswith(('_helical', '_double')) else 'spur'


def variant_for(stages, teeth):
    if stages == 1:
        return teeth
    prefix = {2: 'two_stage', 3: 'three_stage'}[stages]
    return prefix if teeth == 'spur' else f'{prefix}_{teeth}'


def selectors(variant='spur'):
    """Independent presentation choices; only the canonical variant is saved."""
    stages, teeth = count({'variant': variant}), tooth_type(variant)
    stage_choices = {variant_for(n, teeth): str(n) for n in (1, 2, 3)}
    tooth_choices = {variant_for(stages, t): label for t, label in
                     [('spur', 'Spur'), ('helical', 'Helical'), ('double', 'Double helical')]}
    return [dict(key=key, label=label, type='choice', option_key='variant', value=variant,
                 choices=[dict(value=value, label=title) for value, title in choices.items()])
            for key, label, choices in [('stage_count', 'Number of stages', stage_choices),
                                        ('tooth_type', 'Tooth type', tooth_choices)]]


def stage_key(key, stage):
    return key if stage == 1 else f'{key}{stage}'


def specs(variant):
    """Only active stages enter canonical parameters and saved projects."""
    result = []
    teeth = tooth_type(variant)
    for stage in range(2, count({'variant': variant}) + 1):
        for key, label, default, low, high, step in (
            ('pinion', 'Pinion teeth', 20, 12, 100, 1),
            ('wheel', 'Wheel teeth', 80 if stage == 2 else 60, 22, 200, 1),
            ('module', 'Module [mm]', 2.5 if stage == 3 else 2, .1, 10, .1),
            ('width', 'Face width [mm]', 10, 1, 100, 1),
            ('pressure', 'Pressure angle [°]', 20, 14.5, 30, .5),
            ('backlash', 'Tangential backlash [mm]', .15, 0, 1, .01),
            ('profile_shift', 'Pinion profile shift x (wheel = −x)', 0, -.5, .7, .05),
            ('center_extra', 'Centre distance increase [mm]', 0, 0, 5, .05),
            ('layout_angle', 'Centre-line turn [°]', 0, -180, 180, 1),
        ):
            result.append((stage_key(key, stage), f'{label} · stage {stage}', default, low, high, step))
        if teeth in ('helical', 'double'):
            result.append((stage_key('helix', stage), f'Pinion helix angle [°] · stage {stage}', 20, -35, 35, 1))
        if teeth == 'double':
            result.append((stage_key('gap', stage), f'Central groove [mm] · stage {stage}', 1, 0, 10, .1))
        result.append((f'intermediate_bore{stage-1}', f'Intermediate shaft {stage-1} diameter [mm]', 8, 1, 100, .5))
    result.extend([
        ('stage_gap', 'Axial gap between stages [mm]', 2, .1, 30, .1),
        ('hub_wall', 'Connecting hub radial wall [mm]', 2, .5, 20, .5),
        ('shaft_extension', 'Shaft extension at each end [mm]', 8, 0, 40, 1),
        ('assembly_clearance', 'Nonmating envelope clearance [mm]', .2, .01, 2, .01),
    ])
    return result


def prepare(values):
    if count(values) > 1:
        if values.get('bearing_mode', 'manual') != 'manual' or values.get('hardware_mode', 'none') != 'none':
            raise ValueError(CATALOG_REASON)
    return values


def forward_ratio(values):
    return prod(-values[stage_key('wheel', s)] / values[stage_key('pinion', s)]
                for s in range(1, count(values) + 1))


def rates(values):
    """Shaft-indexed rates, stable for forward/reverse ports and zero RPM."""
    n = count(values)
    ratio = forward_ratio(values)
    first = values['input_rpm'] if values['io_scheme'] == 'forward' else values['input_rpm'] * ratio
    result = [first]
    for s in range(1, n + 1):
        result.append(-result[-1] * values[stage_key('pinion', s)] / values[stage_key('wheel', s)])
    return result


def apply_kinematics(design):
    v = design.values
    n = count(v)
    speed = rates(v)
    ratio = forward_ratio(v)
    reverse = v['io_scheme'] == 'reverse'
    design.analysis['signed_ratio'] = 1 / ratio if reverse else ratio
    stages = []
    for s in range(1, n + 1):
        local = -v[stage_key('wheel', s)] / v[stage_key('pinion', s)]
        stages.append(dict(stage=s, input_shaft=s-1, output_shaft=s,
                           signed_ratio=local, rates_rpm={'pinion': speed[s-1], 'wheel': speed[s]}))
    label = f'Shaft {n+1} → shaft 1' if reverse else f'Shaft 1 → shaft {n+1}'
    design.analysis['kinematics'] = dict(scheme=v['io_scheme'], label=label, stage_results=stages,
                                       shaft_rates_rpm=speed, input_shaft=n if reverse else 0,
                                       output_shaft=0 if reverse else n)
    for part in design.parts:
        shaft = part.port['shaft']
        role = 'input' if shaft == (n if reverse else 0) else 'output' if shaft == (0 if reverse else n) else 'intermediate'
        part.port.update(member=f'shaft_{shaft}', role=role, rpm=speed[shaft])


def _envelope_check(items, clearance):
    tested = 0
    for i, a in enumerate(items):
        for b in items[i+1:]:
            if a['shaft'] == b['shaft']:
                continue  # Nominal bore/shaft fits and joined compound faces.
            if a['kind'] == b['kind'] == 'gear' and a['stage'] == b['stage']:
                continue  # Intentional tooth engagement; canonical mesh checks apply.
            axial = max(a['z0'], b['z0']) - min(a['z1'], b['z1'])
            if axial >= clearance - 1e-9:
                continue
            tested += 1
            radial = hypot(a['center'][0]-b['center'][0], a['center'][1]-b['center'][1]) - a['radius'] - b['radius']
            if radial < clearance - 1e-9:
                raise ValueError(f"Multistage layout: {a['name']} and {b['name']} lack swept-envelope clearance. "
                                 'Change centre-line turns, shaft/hub diameters, stage widths or spacing.')
    return dict(status='clear', tested_pairs=tested, clearance_mm=clearance,
                scope='Conservative swept cylinders of nonmating gears, shafts and hubs; intended meshes and same-shaft interfaces excluded. No tooth-contact, load or tolerance certification.')


def build(design):
    from geometry import gear_part, Part, circle
    from engineering import mesh
    v = design.values
    n = count(v)
    teeth_type = tooth_type(v['variant'])
    double = teeth_type == 'double'
    prepare(v)
    if min(v['bore'], v['output_bore']) <= 0:
        raise ValueError('Multistage trains require positive input and output shaft diameters.')
    bores = [v['bore']] + [v[f'intermediate_bore{s}'] for s in range(1, n)] + [v['output_bore']]
    centers = [(0., 0.)]
    levels, angles, meshes, gears, items = [], [], [], {}, []
    angle, level = 0., 0.
    for stage in range(1, n + 1):
        get = lambda key: v[stage_key(key, stage)]
        zp, zw, m, width = (get(k) for k in ('pinion', 'wheel', 'module', 'width'))
        if zw <= zp:
            raise ValueError(f'Stage {stage}: wheel teeth must exceed pinion teeth for a reduction stage.')
        if get('backlash') >= .7*m:
            raise ValueError(f'Stage {stage}: backlash too large for the module.')
        beta = get('helix') if teeth_type != 'spur' else 0
        gap = get('gap') if double else 0
        if double and gap >= width - 1:
            raise ValueError(f'Stage {stage}: the groove must leave at least 1 mm of teeth.')
        # Report contact overlap on one active half, including Joined (gap=0).
        active_width = (width-gap)/2 if double else width
        q = mesh(zp, zw, m, get('pressure'), beta, active_width,
                 get('profile_shift'), get('center_extra'), backlash=get('backlash'))
        if teeth_type != 'spur':
            q['gear2']['beta'] = -beta
            q.update(pinion_helix_deg=beta, wheel_helix_deg=-beta, active_face_width_mm=active_width)
        # Overall efficiency is not a per-stage loss law; avoid invented mesh loads.
        q.update(stage=stage, torque_factor=None)
        meshes.append(q)
        if stage > 1:
            angle += radians(get('layout_angle'))
        a = q['center_distance_mm']
        previous = centers[-1]
        centers.append((previous[0]+a*cos(angle), previous[1]+a*sin(angle)))
        angles.append(angle)
        levels.append((level, level+width))
        phase_wheel = (zp+zw)*angle/zw + pi + pi/zw
        for kind, teeth, shaft, phase, shift in (
            ('Pinion', zp, stage-1, 0., get('profile_shift')),
            ('Wheel', zw, stage, phase_wheel, -get('profile_shift')),
        ):
            part = gear_part(f'S{stage}_{kind}', teeth, m, get('pressure'), get('backlash'), width,
                             bores[shaft], centers[shaft], phase, helix=beta if kind == 'Pinion' else -beta, zoff=level, shift=shift)
            if double:
                part.double = True
                part.gap = gap
                part.core_radius = min(hypot(x, y) for x, y in part.outer) * .96
                if bores[shaft]/2 >= part.core_radius-.25:
                    raise ValueError(f'Stage {stage} {kind.lower()}: bore too large for the continuous double-helix hub.')
            root = q['gear1' if kind == 'Pinion' else 'gear2']['root_radius']
            if bores[shaft]/2 >= root-.5:
                raise ValueError(f'Stage {stage} {kind.lower()}: shaft bore leaves insufficient tooth-root material.')
            part.profile_metadata['parallel_train'] = dict(stage=stage, shaft=shaft, initial_tooth_phase_rad=phase)
            part.port = dict(shaft=shaft, stage=stage, rigid_group=f'parallel_shaft_{shaft}')
            part.color = ((.95,.65,.3),(.45,.65,.9),(.3,.78,.65),(.75,.55,.85))[shaft]
            design.parts.append(part)
            gears[stage, kind] = part
            items.append(dict(name=part.name, shaft=shaft, stage=stage, kind='gear', center=part.center,
                              z0=level, z1=level+width, radius=q['gear1' if kind == 'Pinion' else 'gear2']['tip_radius']))
        level += width + v['stage_gap']
    for shaft in range(n+1):
        lo = levels[max(0, shaft-1)][0]
        hi = levels[min(n-1, shaft)][1]
        extension = v['shaft_extension']
        part = Part(f'Shaft_{shaft+1}', circle(bores[shaft]/2), [], hi-lo+2*extension,
                    lo-extension, centers[shaft], role='support', color=(.65,.72,.8))
        part.port = dict(shaft=shaft, rigid_group=f'parallel_shaft_{shaft}')
        design.parts.append(part)
        items.append(dict(name=part.name, shaft=shaft, kind='shaft', center=part.center,
                          z0=part.z, z1=part.z+part.width, radius=bores[shaft]/2))
        if 0 < shaft < n:
            radius = bores[shaft]/2+v['hub_wall']
            roots = [meshes[shaft-1]['gear2']['root_radius'], meshes[shaft]['gear1']['root_radius']]
            if radius >= min(roots)-.25:
                raise ValueError(f'Intermediate shaft {shaft}: connecting hub exceeds the available tooth-root radius. Reduce hub wall/shaft diameter or enlarge the gears.')
            z0 = levels[shaft-1][1]
            part = Part(f'Compound_{shaft}_Hub', circle(radius), [circle(bores[shaft]/2)],
                        levels[shaft][0]-z0, z0, centers[shaft], color=gears[shaft, 'Wheel'].color)
            part.port = dict(shaft=shaft, rigid_group=f'parallel_shaft_{shaft}')
            design.parts.append(part)
            items.append(dict(name=part.name, shaft=shaft, kind='hub', center=part.center,
                              z0=part.z, z1=part.z+part.width, radius=radius))
    design.analysis.update(meshes=meshes, signed_ratio=forward_ratio(v),
                           parallel_train=dict(stages=n, shaft_centers_mm=centers, shaft_diameters_mm=bores,
                                               stage_levels_mm=levels, centre_line_angles_rad=angles,
                                               envelope_check=_envelope_check(items, v['assembly_clearance'])))
    design.metrics = [f'{n} stages · {n+1} parallel shafts · '+{'spur': 'spur teeth', 'helical': 'helical teeth', 'double': 'double-helical teeth'}[teeth_type],
                      f"Total reduction {forward_ratio(v):+.6g}:1",
                      'Stage centre distances: '+ ' / '.join(f"{q['center_distance_mm']:.3f}" for q in meshes)+' mm']
    design.notes.extend([
        'All shaft axes are parallel to world +Z. Centre-line turns fold the XY layout; 0° is straight, positive turns counterclockwise viewed from +Z.',
        'Intermediate wheels, connecting hubs and following pinions are nominal rigid compounds. They share one shaft speed and explicit rigid-group metadata. Exported touching solids remain separate bodies; CAD motion joints and a Boolean union are not generated.',
        'Gear pairs occupy separate axial levels. Nonmating swept cylinders are conservatively separated for full rigid rotation; intended tooth meshes retain the canonical mesh checks and limits.',
        'Only overall assumed efficiency is supplied; per-stage forces are not estimated without a stage loss distribution.',
    ])
    if teeth_type != 'spur':
        design.notes.append('Each stage uses normal module and normal pressure angle, with equal and opposite pinion/wheel helix angles. Changing a stage helix changes its centre distance; compound pinions have independent stage helix settings.')
    if double:
        design.notes.append('Double helix: overlap ratio is reported for one active half, excluding its central groove. Joined teeth meet at the mid-plane. Axial thrust cancellation would require symmetric load sharing; no stage axial loads or support capacity are calculated.')
    design.requirements.append('Nominal shafts and compound bores: design fits, torque transfer to shafts, bearings, retainers and frame in CAD. No load capacity or manufacturing qualification is established.')
