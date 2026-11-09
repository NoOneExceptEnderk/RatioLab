# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Cylindrical ZA/ZI worms and strain wave envelopes. Sources are in docs/technical/variants.md.
Worm wheels use the matching screw envelope; strain-wave rings use the complete prescribed tooth sweep.
"""
from math import pi,sin,cos,tan,atan,acos,atan2,sqrt,hypot,radians,degrees,ceil
from geometry import CircleProfile,Part,gear_part,involute,circle,circle_info,polar,clean,sample_curve,TAU

def round_loop(r):
    return circle(r,max(96,ceil(pi/acos(max(-1,min(1,1-.002/r))))))

def za_profile(starts,module,diameter,pressure,backlash):
    from rust_geometry import call
    return [tuple(p) for p in call('worm_screw_profile',dict(starts=starts,module=module,
        diameter=diameter,pressure=pressure,backlash=backlash,variant='za'))]


def zi_profile(starts,module,diameter,pressure,backlash):
    from rust_geometry import call
    return [tuple(p) for p in call('worm_screw_profile',dict(starts=starts,module=module,
        diameter=diameter,pressure=pressure,backlash=backlash,variant='zi'))]


def worm(d):
    v=d.values;m=v['module'];z=v['teeth'];starts=v['starts'];D=v['diameter'];length=v['length'];width=v['width'];bore=v['bore'];hand=v['worm_hand']
    from rust_geometry import call
    from geometry import part_from_kernel
    from rust_geometry import call_geometry
    result=call_geometry('construction_worm',dict(values=v))
    d.parts.extend(part_from_kernel(p['name'],p) for p in result['parts'])
    metadata=result['wheel_geometry']
    analysis=result['analysis']
    lead=analysis['lead_mm'];gamma_degrees=analysis['lead_angle_deg'];mn=analysis['normal_module_mm'];an=analysis['normal_pressure_deg'];turns=analysis['thread_turns'];jl=analysis['journal_length_mm']
    d.metrics=[f'Worm cilindrica {v["variant"].upper()} · nominal ratio {z/starts:g}:1',f'{starts} principio/i · avanzamento {lead:.3f} mm · γ {gamma_degrees:.3f}°',f'Centre distance {(D+m*z)/2:.3f} mm · length filetto {length:g} mm',f'Codoli {jl:g} mm per side · total length {length+2*jl:g} mm']
    d.analysis['wheel_geometry']=metadata
    d.analysis.update(analysis)
    d.notes+=['Signed worm ratio follows the displayed +X worm / +Z wheel axes (wheel on negative Y): left hand reverses wheel rotation.',
        'ZA worm profile: straight flanks in axial section; ZI: involute in transverse section. Helical surfaces use a nominal angular sagitta of 0.02 mm; geometry is shared by CAD and preview.',
        'The wheel is generated from the matching ZA/ZI screw helicoid, including backlash and the swept hob-tip root transition. Numerical section chord threshold is 0.005 mm; discrete surfaces require clearance checks at the chosen parameters. Strength, lubrication, manufacturing tolerances and self locking are not certified.']
    d.requirements.append('Design worm/wheel supports, bearings, retainers, fasteners and lubrication; the generated envelope does not specify a production hob or manufacturing tolerances.')

def ellipse_axes(radius,amplitude):
    from rust_geometry import call
    return tuple(call('planar_ellipse_axes',dict(radius=radius,amplitude=amplitude)))


def refine_angles(points,radius):
    from rust_geometry import call
    return [tuple(p) for p in call('planar_refine_angles',dict(points=points,radius=radius))]


def harmonic(d):
    from rust_geometry import call
    from geometry import part_from_kernel
    v=d.values;z=v['teeth'];L=v['cup_length'];t=v['diaphragm'];variant=v['variant'];bearing=v['bearing_thickness']
    from rust_geometry import call_geometry
    result=call_geometry('construction_harmonic',dict(values=v))
    parts=[part_from_kernel(p['name'],p) for p in result['parts']]
    d.parts.extend(parts)
    analysis=result['analysis']
    ratio=analysis['signed_ratio'];a,b=analysis['pitch_ellipse_semiaxes_mm']
    circular=v['harmonic_output']=='circular'
    d.metrics=[f'Strain wave · {variant.replace("_"," ")} · ratio {ratio:+g}:1',f'Flexspline {z} · ring {z+2} teeth · body {L:g} mm',f'Pitch ellipse: semiaxes {a:.3f} / {b:.3f} mm',f'Diaphragm/flange {t:g} mm · wave bearing {bearing:g} mm']
    d.analysis.update(analysis)
    d.notes+=['The flexible cup/diaphragm or external flange is one continuous solid with a prescribed circular-to-ellipse transition, uniform pitch arc length and local normal tooth orientation. The rigid ring is generated from the complete swept tooth outline; deformation is prescribed, not an elastic or stress solution.',
        'Wave generator and bearing envelope follow the deformed cavity with separate radial clearances. The bearing envelope is not a selected commercial component.',
        'The ring uses a numerically generated envelope of a thickened reference tooth. Angular-cell enclosure relief is reported separately from reference pair backlash. Discrete verification does not prove continuous clearance or certify load capacity; design supports, fatigue fillets and fasteners.',
        'Wave generator input; '+('fixed flexspline, ring output (same direction).' if circular else 'fixed ring, flexspline output (opposite direction).')]
    d.requirements.append('Design flexspline elastic/fatigue checks, fillets, flange and fasteners, actual bearings and seals; validate tooling and manufacturing tolerances.')
