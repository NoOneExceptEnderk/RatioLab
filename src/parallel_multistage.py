# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Fixed-axis compound cylindrical gear trains. Frames/equations: docs/technical/parallel.md.

Shafts are parallel to +Z; turns change XY centre lines, not shaft axes.
Nonmating swept cylinders are a conservative full-rotation exclusion test.
"""
from math import hypot

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
    from rust_geometry import call
    return call('parallel_rates',values)['forward_ratio']


def rates(values):
    """Shaft-indexed rates, stable for forward/reverse ports and zero RPM."""
    from rust_geometry import call
    return call('parallel_rates',values)['shaft_rates_rpm']


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


def build(design):
    """Assemble the shared Rust nominal plan; presentation adds no gear formula."""
    from geometry import gear_part, Part, circle
    from rust_geometry import call
    v=design.values;n=count(v);teeth_type=tooth_type(v['variant']);double=teeth_type=='double'
    plan=call('nominal_parallel_plan',v)
    for component in plan['components']:
        p=dict(component['parameters']);place=component['placement'];shaft=component['port']['shaft']
        if component['kind']=='cylindrical_gear':
            p.pop('double');gap=p.pop('gap');p['z']=int(p['z'])
            # Exact sources are retained in the recipe through both boundaries.
            from precise_numbers import restore
            p=restore(p)
            part=gear_part(component['name'],center=tuple(place['center_mm']),phase=place['phase_rad'],zoff=place['z_mm'],**p)
            if double:
                part.double=True;part.gap=gap
                part.core_radius=min(hypot(x,y) for x,y in part.outer)*.96
                if p['bore']/2>=part.core_radius-.25:
                    raise ValueError(f"{part.name}: bore too large for the continuous double-helix hub.")
            part.profile_metadata['parallel_train']=dict(stage=component['port']['stage'],shaft=shaft,initial_tooth_phase_rad=place['phase_rad'])
        else:
            part=Part(component['name'],circle(p['radius_mm']),[circle(p['bore_radius_mm'])] if p['bore_radius_mm'] else [],
                      p['width'],place['z_mm'],tuple(place['center_mm']),role='support' if component['name'].startswith('Shaft_') else 'gear')
        part.port=dict(component['port'])
        part.color=(.65,.72,.8) if part.role=='support' else ((.95,.65,.3),(.45,.65,.9),(.3,.78,.65),(.75,.55,.85))[shaft]
        design.parts.append(part)
    design.analysis.update(plan['analysis'])
    for key in ('shaft_centers_mm','stage_levels_mm'):
        design.analysis['parallel_train'][key]=list(map(tuple,design.analysis['parallel_train'][key]))
    meshes=plan['analysis']['meshes']
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
