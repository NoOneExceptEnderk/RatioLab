# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Finite rack/pinion on world X, pinion +Z. KHK tables4.5/4.13, eq4.2/4.18."""
from math import pi, sin, cos, tan, atan, radians, degrees, sqrt, ceil, hypot

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


def dimensions(v):
    m=v['module'];beta=v.get('helix',0);cb=cos(radians(beta))
    mt=m/cb;alpha=atan(tan(radians(v['pressure']))/cb);r=mt*v['pinion']/2
    pitch=pi*mt;ra=r+m;rb=r*cos(alpha);root=r-1.25*m
    half=pitch/4-v['backlash']/4
    if half-m*tan(alpha)<=.025*m or half+1.25*m*tan(alpha)>=pitch/2-.025*m:
        raise ValueError('Rack teeth are pointed or overlap at the roots; adjust pressure / backlash.')
    if v['backlash']>=.7*m:raise ValueError('Rack backlash must be less than 0.7 normal module.')
    if v['bore']/2>=root-.5:raise ValueError('Pinion bore leaves insufficient nominal root wall.')
    # A physical rack tip must meet the forward, usable involute branch.
    approach=r*sin(alpha)-m/sin(alpha)
    if approach<=0:raise ValueError('Rack tip reaches below the forward pinion involute; increase pinion teeth / pressure.')
    from geometry import gear_part
    phase=-pi/2+(pi/v['pinion'] if v['rack_teeth']%2 else 0)
    p=gear_part('Rack_pinion',v['pinion'],m,v['pressure'],v['backlash'],v['width'],v['bore'],
                (0,r),phase,beta)
    start=p.profile_metadata['tooth_profile']['involute_start_radius_mm']
    contact_min=hypot(rb,approach)
    if contact_min<start+1e-6:
        raise ValueError('Rack tip reaches the trimmed pinion root transition; increase pinion teeth / pressure.')
    path=sqrt(ra*ra-rb*rb)-r*sin(alpha)+m/sin(alpha)
    engagement=path/(pitch*cos(alpha))
    if engagement<=1+1e-8:raise ValueError('Rack transverse ideal engagement must exceed one tooth pitch.')
    double=v['variant']=='double'
    if double:
        if v['gap']>=v['width']-2:raise ValueError('Double rack groove must leave more than 1 mm per helical half.')
        p.double=True;p.gap=v['gap'];p.core_radius=root*.96
        if v['bore']/2>=p.core_radius-.25:raise ValueError('Pinion bore reaches the continuous double-helix core.')
    sweep=tan(radians(beta))*(v['width']-v.get('gap',0))/2 if double else tan(radians(beta))*v['width']
    footprint=sqrt(max(0,ra*ra-(r-m)**2))
    travel=v['rack_teeth']*pitch/2-footprint-abs(sweep)-pitch
    if travel<=pitch/2:raise ValueError('Rack is too short for a complete safe working stroke; add rack teeth or reduce face width / helix.')
    return p,dict(pitch_radius_mm=r,normal_module_mm=m,transverse_module_mm=mt,
        normal_pressure_deg=v['pressure'],transverse_pressure_deg=degrees(alpha),
        transverse_pitch_mm=pitch,travel_per_revolution_mm=2*pi*r,
        travel_limits_mm=[-travel,travel],pinion_angle_limits_rad=[-travel/r,travel/r],
        nominal_contact_transverse=engagement,rack_tip_contact_radius_mm=contact_min,
        usable_pinion_involute_start_mm=start,helix_sweep_mm=sweep,
        rack_derived_hand=-1 if beta>0 else 1 if beta<0 else 0,
        reference='KHK Calculation of Gear Dimensions, tables4.5/4.13, equations4.2/4.18')


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


def outline(v,info,shift=0,height=1):
    m=v['module'];pitch=info['transverse_pitch_mm'];alpha=radians(info['transverse_pressure_deg'])
    root=-1.25*m;tip=m;half=pitch/4-v['backlash']/4
    # Fixed rectangular ends enclose all complete swept teeth; no clipped end teeth.
    sweep=info['helix_sweep_mm'];left=-(v['rack_teeth']+1)*pitch/2+min(0,sweep)
    right=(v['rack_teeth']+1)*pitch/2+max(0,sweep)
    top=[]
    for j in range(v['rack_teeth']):
        c=(j-(v['rack_teeth']-1)/2)*pitch+shift
        for x,y in ((c-half+root*tan(alpha),root),(c-half+tip*tan(alpha),tip),
                    (c+half-tip*tan(alpha),tip),(c+half-root*tan(alpha),root)):
            top.append((x,root+height*(y-root)))
    return [(left,root-v['base']),(right,root-v['base']),(right,root)]+list(reversed(top))+[(left,root)]


def operating(d):
    """Only operating metadata changes; geometry is shared during RPM edits."""
    v=d.values;q=d.analysis['rack'];rpm=v['input_rpm'];speed=2*pi*q['pitch_radius_mm']*rpm/60
    d.analysis['linear_output']=dict(axis='World +X',velocity_mm_s=speed,
        nominal_force_magnitude_N=1000*v['input_torque']/q['pitch_radius_mm']*v['efficiency']/100,
        scope='Nominal conversion using assumed efficiency; no guide friction or load rating')
    d.parts[0].port.update(member='pinion',role='input',axis='World +Z',rpm=rpm)
    d.parts[1].port.update(member='rack',role='output',axis='World +X',velocity_mm_s=speed)
    d.analysis['kinematics']=dict(type='rotary_to_linear',equation='x_mm = pitch_radius_mm * pinion_angle_rad',
        input='pinion',output='rack',input_rpm=rpm,output_velocity_mm_s=speed,periodic=False)


def build(d):
    from geometry import Part
    v=d.values;p,info=dimensions(v);p.stations,rows=_stations(p)
    r=info['pitch_radius_mm'];contours=[outline(v,info,r*angle,height) for z,angle,height in rows]
    rack=Part('Rack',contours[0],[],v['width'],color=(.23,.75,.65))
    rack.stations=[dict(z=z,outer=loop,holes=[]) for (z,angle,height),loop in zip(rows,contours)]
    p.color=(.96,.66,.33)
    info.update(base_length_mm=contours[0][1][0]-contours[0][0][0],base_below_roots_mm=v['base'],
                rack_teeth=v['rack_teeth'],section_count=len(rows),refinement_mm=REFINEMENT,
                end_rule='Complete teeth with fixed end planes and untoothed sweep lands',
                stroke_rule='Conservative finite stroke excludes active pinion footprint, helix sweep and one rack pitch')
    for part in (p,rack):part.profile_metadata['rack_pair']=dict(method='Involute pinion / straight transverse rack flanks',reference=info['reference'])
    d.parts.extend([p,rack]);d.analysis['rack']=info;operating(d)
    d.metrics.extend([f"Rack travel per revolution: {info['travel_per_revolution_mm']:.6f} mm/rev",
                      f"Rack base length: {info['base_length_mm']:.6f} mm · {v['rack_teeth']} complete teeth",
                      f"Safe nominal travel: ±{info['travel_limits_mm'][1]:.6f} mm · transverse ideal engagement {info['nominal_contact_transverse']:.6f}"])
    d.notes.extend(['Finite rack on world +X, pitch line Y=0, pinion shaft +Z centered at (0, pitch radius). Positive pinion rotation advances the rack toward +X. Preview stops at the conservative stroke limit; the mechanism has no rotary repetition period.',
        'Normal module and pressure angle; transverse pair backlash is split equally between pinion and rack. Matching rack trace is derived from pinion helix. Double helices reverse at the center, with an optional relieved groove and continuous base/core.',
        'Rack has nominal sharp straight-flank corners and rectangular fixed ends with extra untoothed lands for axial tooth sweep. Pinion uses the existing rounded-rack root envelope. Sampling is shared by preview and exports; no manufacturing, strength or guide accuracy is established.',
        'The ideal equation relates pinion rotation to rack translation. Physical guide/supports/end stops, friction, retention and lubrication are left for CAD design.'])
    d.requirements.append(CATALOG_REASON)
