# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Finite rack/pinion on world X, pinion +Z. KHK tables4.5/4.13, eq4.2/4.18."""
from math import pi, hypot, radians, ceil, sqrt

VARIANTS={'spur':'Spur teeth','helical':'Helical teeth','double':'Double helical teeth'}
SPECS=[('module','Normal module [mm]',2,.5,6,.1),
       ('pinion','Pinion teeth',24,12,100,1),
       ('rack_teeth','Rack teeth',24,8,200,1),
       ('width','Face width [mm]',10,2,60,.5),
       ('base','Rack base below roots [mm]',6,1,40,.5),
       ('pressure','Normal pressure angle [°]',20,14.5,30,.5),
       ('backlash','Transverse pair backlash [mm]',.15,0,1,.01),
       ('bore','Pinion bore [mm]',6,0,100,.5)]
REFINEMENT=.003
CATALOG_REASON=('Rack and pinion generate two blanks. Complete the linear guide, '
                'shaft, bearings, mounting and end stops in CAD; automatic catalog hardware is unavailable.')


def validate_dimensions(v):
    from rust_geometry import call
    return call('rack_drive_dimensions',v)


def dimensions(v):
    """Compatibility API: the pinion and dimensions come from the shared core."""
    from geometry import gear_part
    from rust_geometry import call
    plan=call('nominal_rack_plan',v);c=plan['components'][0];p=dict(c['parameters']);p.pop('double');p.pop('gap')
    p['z']=int(p['z']);p['name']=c['name'];p['center']=tuple(c['placement']['center_mm']);p['phase']=c['placement']['phase_rad']
    part=gear_part(**p)
    if v['variant']=='double':
        part.double=True;part.gap=v['gap'];part.core_radius=(plan['analysis']['rack']['pitch_radius_mm']-1.25*v['module'])*.96
    return part,plan['analysis']['rack']


def _stations(p):
    """Bound rotational vertex chords of each defined section interpolation."""
    from geometry import profile_sections,transformed
    rows=profile_sections(p);result=[];working=[]
    for (a,aa,oa),(b,ab,ob) in zip(rows,rows[1:]):
        radius=max(hypot(*q) for loop in (oa,ob) for q in loop)
        delta=max(hypot(v[0]-u[0],v[1]-u[1]) for u,v in zip(oa,ob))
        angle=radians(ab-aa)
        # |q''| <= R*angle^2 + 2*|delta_q|*|angle| on this interpolation.
        n=max(1,ceil(sqrt((radius*angle*angle+2*delta*abs(angle))/(8*REFINEMENT))))
        for j in range(n):
            f=j/n;z=a+(b-a)*f;turn=aa+(ab-aa)*f
            loop=[(u[0]+(v[0]-u[0])*f,u[1]+(v[1]-u[1])*f) for u,v in zip(oa,ob)]
            outer=transformed(loop,angle=radians(turn))
            result.append(dict(z=z,outer=outer,holes=p.holes))
            working.append((z,radians(turn),((oa is p.outer)*(1-f)+(ob is p.outer)*f)))
    z,angle,outer=rows[-1]
    result.append(dict(z=z,outer=transformed(outer,angle=radians(angle)),holes=p.holes))
    working.append((z,radians(angle),1 if outer is p.outer else 0))
    if 2*(len(p.outer)+sum(map(len,p.holes)))*(len(result)-1)+2>250000:
        raise ValueError('Rack pinion surface budget exhausted; reduce teeth / face width / helix.')
    return result,working


def operating(d):
    """Only operating metadata changes; geometry is shared during RPM edits."""
    v=d.values;q=d.analysis['rack'];rpm=v['input_rpm'];speed=2*pi*q['pitch_radius_mm']*rpm/60
    d.analysis['linear_output']=dict(axis='World +X',velocity_mm_s=speed,
        nominal_force_magnitude_N=1000*v['input_torque']/q['pitch_radius_mm']*v['efficiency']/100,
        scope='Nominal conversion using assumed efficiency; no guide friction or load rating')
    d.parts[0].port.update(member='pinion',role='input',axis='World +Z',rpm=rpm)
    d.parts[1].port.update(member='rack',role='output',axis='World +X',velocity_mm_s=speed)
    d.analysis['kinematics']=dict(type='rotary_to_linear',label='Pinion → rack',equation='x_mm = pitch_radius_mm * pinion_angle_rad',
        input='pinion',output='rack',input_rpm=rpm,output_velocity_mm_s=speed,periodic=False)


def build(d):
    from geometry import part_from_kernel
    from rust_geometry import call_geometry
    v=d.values
    result=call_geometry('construction_rack',dict(values=v))
    d.parts.extend(part_from_kernel(p['name'],p) for p in result['parts'])
    info=result['analysis']['rack'];d.analysis['rack']=info;operating(d)
    d.metrics.extend([f"Rack travel per revolution: {info['travel_per_revolution_mm']:.6f} mm/rev",
                      f"Rack base length: {info['base_length_mm']:.6f} mm · {v['rack_teeth']} complete teeth",
                      f"Safe nominal travel: ±{info['travel_limits_mm'][1]:.6f} mm · transverse ideal engagement {info['nominal_contact_transverse']:.6f}"])
    d.notes.extend(['Finite rack on world +X, pitch line Y=0, pinion shaft +Z centered at (0, pitch radius). Positive pinion rotation advances the rack toward +X. Preview stops at the conservative stroke limit; the mechanism has no rotary repetition period.',
        'Normal module and pressure angle; transverse pair backlash is split equally between pinion and rack. Matching rack trace is derived from pinion helix. Double helices reverse at the center, with an optional relieved groove and continuous base/core.',
        'Rack has nominal sharp straight-flank corners and rectangular fixed ends with extra untoothed lands for axial tooth sweep. Pinion uses the existing rounded-rack root envelope. Sampling is shared by preview and exports; no manufacturing, strength or guide accuracy is established.',
        'The ideal equation relates pinion rotation to rack translation. Physical guide/supports/end stops, friction, retention and lubrication are left for CAD design.'])
    d.requirements.append(CATALOG_REASON)
