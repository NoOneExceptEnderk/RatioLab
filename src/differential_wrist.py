# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Bevel differential wrist/classic geometry and ideal member rates.

Exact spherical involute flanks are sampled into shared planar sections;
nonworking root relief is constructed, not a manufacturing cutter fillet.
No external belt drive, pulleys or motors are part of this assembly.
"""
from math import atan2, cos, sin, hypot, pi, degrees, acos, sqrt, radians, tan, log, ceil
from geometry import Part, circle, transformed, polar
from bevel_geometry import parameters as bevel_parameters, section as bevel_section, engagement, PROFILE_TOLERANCE

# All frames are right handed; their local Z is the positive shaft direction.
FRAME_A = ((0, 0, 0), (0, 1, 0), (0, 0, 1), (1, 0, 0))
FRAME_B = ((0, 0, 0), (0, 1, 0), (0, 0, -1), (-1, 0, 0))
FRAME_OUTPUT = ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1))
COLORS = {'A': (.96, .66, .33), 'B': (.69, .59, .86),
          'output': (.23, .75, .65), 'carrier': (.43, .51, .63), 'spider': (.65,.72,.8)}
CONFIGURATIONS = {'wrist': 'Wrist · two independent inputs', 'classic': 'Classic · carrier input / two outputs'}
OUTPUT_INTERFACES = {'flange': 'Drilled flange', 'solid': 'Solid output shaft', 'hollow': 'Hollow output shaft'}
CARRIER_STYLES = {'open': 'Open carrier', 'split': 'Split carrier · bearing-seat halves'}
RATIO_MODES = {'custom': 'Custom tooth counts', 'one_to_one': '1:1 side / output teeth',
               'spin_2_1': 'Relative spin reduction 2:1'}
OPTION_DEFAULTS = dict(output_interface='flange', carrier_style='open', ratio_mode='custom', configuration='wrist')
SPIRAL_HANDS = {-1: '−1 · local side hand', 1: '+1 · local side hand'}
TRACE_CHORD_TOLERANCE = .003  # mm; sampled outer vertex traces, not tooth accuracy.


def options(supplied):
    result={key:supplied.get(key,default) for key,default in OPTION_DEFAULTS.items()}
    for key,choices in (('output_interface',OUTPUT_INTERFACES),('carrier_style',CARRIER_STYLES),('ratio_mode',RATIO_MODES),('configuration',CONFIGURATIONS)):
        if not isinstance(result[key],str) or result[key] not in choices:raise ValueError('Unknown differential '+key.replace('_',' ')+'.')
    return result


def prepare(supplied):
    result=dict(supplied);result.update(options(result))
    if result['ratio_mode'] != 'custom':
        factor=2 if result['ratio_mode']=='spin_2_1' else 1
        result['output_teeth']=float(result.get('side_teeth',24))*factor
        if result['ratio_mode']=='spin_2_1' and result['output_teeth']>60:
            raise ValueError('Relative spin reduction 2:1 requires input tooth counts of 30 or fewer.')
    return result


def inactive_fields(values):
    inactive=set()
    if values.get('output_interface','flange')!='flange':inactive.update(('flange_radius','bolt_count','bolt_diameter'))
    else:inactive.add('output_extension')
    if values.get('output_interface','flange')!='hollow':inactive.add('passage_diameter')
    classic=values.get('configuration','wrist')=='classic'
    if values.get('carrier_style','open')!='split' and not classic:inactive.add('carrier_bolt_diameter')
    if values.get('variant','straight')!='spiral':inactive.update(('spiral_angle','spiral_hand'))
    if classic:inactive.update(('input_b_rpm','output_shaft','output_extension'))
    else:inactive.update(('output_difference_rpm','spider_pin_diameter','spider_clearance'))
    return inactive


def labelled_specs(specs,values):
    """Physical labels shared by GTK and MCP; saved parameter keys stay stable."""
    classic=values.get('configuration','wrist')=='classic'
    names=dict(side_teeth='Side gear teeth',output_teeth='Spider bevel teeth' if classic else 'Output bevel teeth',
        input_shaft='Side output shaft diameter [mm]' if classic else 'Input shaft diameter [mm]',
        shaft_extension='Side output shaft extension [mm]' if classic else 'Input shaft extension [mm]',
        input_rpm='Carrier input speed [rpm]' if classic else 'Input A speed [rpm]',
        spiral_hand='Side gear local spiral hand (−1 / +1)',
        carrier_bolt_diameter='Carrier joining / mounting hole diameter [mm]')
    return [(key,names.get(key,label),default,low,high,step) for key,label,default,low,high,step in specs]


def ratio_labels(values):
    result=dict(RATIO_MODES)
    if values.get('configuration','wrist')=='classic':
        result.update(one_to_one='1:1 side / spider teeth',spin_2_1='Spider spin reduction 2:1')
    return result


def spiral_trace(cone_distance, outer_distance, cone_angle, beta, hand):
    """Eq. 9 of Cumbicus et al., DOI 10.1007/s00170-025-16738-7.

    Distances are mm, cone_angle radians, beta unsigned degrees; result radians.
    This helper defines the pitch-cone trace within the reference face interval.
    Individual planar-section vertices use their actual apex distance instead.
    """
    ratio=cone_distance/outer_distance
    if not 0<ratio<=1 or not 0<cone_angle<pi/2:
        raise ValueError('Spiral trace requires a positive cone-distance ratio at or below 1 and a valid cone angle.')
    if hand not in (-1,1) or not 0<=beta<=45:
        raise ValueError('Spiral trace requires hand −1 or +1 and unsigned angle from 0 to 45°.')
    return hand*tan(radians(beta))/sin(cone_angle)*log(ratio)


def cone_stations(v,q):
    """Common cone distances with a conservative linear trace chord bound.

    For f(R)=a R exp(i k ln(R/Ro)), |f''|=a |k|sqrt(1+k²)/R.
    Linear interpolation error <= max|f''| deltaR²/8 on each interval.
    """
    outer=q['cone_distance'];inner=outer-v['width']
    if not 0<inner/outer<=1:raise ValueError('The inner pitch cone distance must be positive.')
    if v.get('variant','straight')!='spiral' or v['spiral_angle']==0:return [inner,outer]
    bound=0
    for angle,pitch in ((q['side_cone_angle'],q['side_pitch_radius']),(q['output_cone_angle'],q['output_pitch_radius'])):
        k=tan(radians(v['spiral_angle']))/sin(angle)
        bound=max(bound,(pitch+v['module'])/outer*abs(k)*sqrt(1+k*k)/inner)
    count=max(1,ceil(v['width']*sqrt(bound/(8*TRACE_CHORD_TOLERANCE))))
    if count>128:raise ValueError('Spiral trace exceeds the section budget; reduce width or spiral angle.')
    return [inner]+[inner+(outer-inner)*j/count for j in range(1,count)]+[outer]


def rates(a, b, side_teeth, output_teeth):
    """Input signs share world +X; output spin is relative to its +Z carrier."""
    return dict(input_a=a, input_b=b, carrier=(a+b)/2,
                output_spin=(b-a)*side_teeth/(2*output_teeth))


def classic_rates(carrier,difference,side_teeth,spider_teeth):
    """Delta=B-A is a prescribed speed boundary, not a second motor input."""
    return dict(side_a=carrier-difference/2,side_b=carrier+difference/2,carrier=carrier,
                spider_spin=side_teeth/spider_teeth*difference/2)


def dimensions(v):
    classic=v['configuration']=='classic'
    side = v['module']*v['side_teeth']/2
    output = v['module']*v['output_teeth']/2
    distance = hypot(side, output)
    if v['width'] > distance/3:
        raise ValueError('Bevel face width must not exceed one third of the pitch cone distance.')
    if v['backlash'] >= .7*v['module']:
        raise ValueError('Backlash too large for the bevel module.')
    scale = 1-v['width']/distance
    beta=v['spiral_angle'] if v['variant']=='spiral' else 0
    side_profile=bevel_parameters(v['side_teeth'],v['output_teeth'],v['module'],v['pressure'],v['backlash'],beta,v['spiral_hand'])
    output_profile=bevel_parameters(v['output_teeth'],v['side_teeth'],v['module'],v['pressure'],v['backlash'],beta,-v['spiral_hand'])
    contact=engagement(side_profile,output_profile,v['width'])
    if contact['contact_phase_span_teeth']<=1+1e-8:
        raise ValueError('Bevel face width/addendum leaves a gap in ideal tooth engagement; increase face width or adjust tooth counts / pressure angle.')
    transverse_bore=v['spider_pin_diameter']+2*v['spider_clearance'] if classic else v['output_shaft']
    for profile, shaft in ((side_profile, v['input_shaft']), (output_profile, transverse_bore)):
        root = distance*cos(profile.delta)*tan(profile.root)*scale
        if shaft/2+.8 >= root:
            raise ValueError('Shaft too large for the small end of the bevel gear; reduce its diameter or face width.')
    t = v['plate'];c = v['assembly_clearance'];r = v['input_shaft' if classic else 'output_shaft']/2
    bolt = v['bolt_diameter']/2;flange = v['flange_radius'];pitch = (r+flange)/2
    if v['output_interface']=='flange':
        if pitch-bolt <= r+.8 or pitch+bolt >= flange-.8:
            raise ValueError('Output flange holes leave too little material around the shaft or flange edge.')
        if 2*bolt+.8 >= 2*pitch*sin(pi/v['bolt_count']):
            raise ValueError('Output flange mounting holes overlap or leave too little material.')
    if v['output_interface']=='hollow' and r-v['passage_diameter']/2<1:
        raise ValueError('The hollow output shaft requires at least 1 mm radial wall around its passage.')
    if v['carrier_style']=='split' and (t-c)/2<1:
        raise ValueError('Split carrier lap layers require at least 1 mm thickness each: increase carrier thickness or reduce assembly clearance.')
    if classic and side*scale-c-min(1.5,t/2)<=0:
        raise ValueError('Spider axial retainer reaches the cone apex; reduce clearance or increase the gear dimensions.')
    return dict(cone_distance=distance, side_pitch_radius=side, output_pitch_radius=output,
                side_cone_angle=atan2(side, output), output_cone_angle=atan2(output, side),
                inner_scale=scale, flange_hole_radius=pitch,transverse_bore=transverse_bore,
                side_profile=side_profile,output_profile=output_profile,engagement=contact)


def split_cheek(half_y, low, high, seat, gap, positive=True):
    """One extruded cheek half with a genuinely open circular bearing seat."""
    edge=gap/2;angle=acos(edge/seat);height=sqrt(seat*seat-edge*edge)
    loop=[(edge,low),(half_y,low),(half_y,high),(edge,high),(edge,height)]
    loop.extend((seat*cos(angle-2*angle*j/64),seat*sin(angle-2*angle*j/64)) for j in range(1,65))
    if not positive:loop=[(-x,y) for x,y in reversed(loop)]
    return loop


def split_bridge(span, half_y, seat, gap, bolt_radius, positive=True, inside_span=None):
    """Half bridge with two crossing lap tabs and coaxial joining holes.

    The two halves occupy separate Z layers. Their tabs overlap only in XY;
    the axial clearance between layers remains real shared geometry.
    """
    edge=gap/2;wall=1.2;half_tab=bolt_radius+wall
    inside_span=span if inside_span is None else inside_span
    center=(inside_span+seat)/2;depth=bolt_radius+wall
    if inside_span-(center+half_tab)<wall or center-half_tab-seat<wall:
        raise ValueError('Split carrier joining holes leave insufficient material beside the bearing seat or bridge ends.')
    if half_y-bolt_radius<wall or depth-bolt_radius<wall-1e-9:
        raise ValueError('Split carrier joining holes leave insufficient bridge edge material.')
    loop=[(-span,edge),(-span,half_y),(span,half_y),(span,edge),
          (center+half_tab,edge),(center+half_tab,-depth),
          (center-half_tab,-depth),(center-half_tab,edge)]
    if seat:
        a=acos(edge/seat)
        loop.append((sqrt(seat*seat-edge*edge),edge))
        loop.extend((seat*sin(a-2*a*j/64),seat*cos(a-2*a*j/64)) for j in range(1,65))
    loop.extend([(-center+half_tab,edge),(-center+half_tab,-depth),
                 (-center-half_tab,-depth),(-center-half_tab,edge)])
    if not positive:loop=[(x,-y) for x,y in reversed(loop)]
    return loop,[circle(bolt_radius,48,(x,0)) for x in (-center,center)]


def build(d):
    v=d.values;q=dimensions(v);t=v['plate'];c=v['assembly_clearance'];m=v['module']
    classic=v['configuration']=='classic'
    speed=(classic_rates(v['input_rpm'],v['output_difference_rpm'],v['side_teeth'],v['output_teeth']) if classic
           else rates(v['input_rpm'],v['input_b_rpm'],v['side_teeth'],v['output_teeth']))
    wa,wb=(speed['side_a'],speed['side_b']) if classic else (speed['input_a'],speed['input_b'])
    relative_spin=speed['spider_spin' if classic else 'output_spin']
    distances=cone_stations(v,q)

    def member(p, name, rpm=None):
        p.color=COLORS[name]
        if classic:
            role='output' if name in ('A','B') else 'input' if name=='carrier' else 'internal'
            if name=='carrier':p.color=COLORS['A']
            elif name=='A':p.color=COLORS['output']
        else:role='input' if name in ('A','B') else 'output'
        p.port=dict(member=name,role=role,
                    axis='Spin relative to moving carrier +Z; carrier rotation about world +X' if name=='spider' else 'Spin relative to moving carrier +Z; carrier tilt about world +X' if name=='output' else 'World +X')
        if classic:p.port['label']={'A':'Side output A','B':'Side output B','carrier':'Carrier input','spider':'Internal spider'}[name]
        if rpm is not None:p.port['rpm']=rpm
        if name in ('output','spider'):p.port.update(carrier_rpm=speed['carrier'],relative_spin_rpm=relative_spin)
        d.parts.append(p)
        return p

    def cylinder(name, outer, bore, length, z, frame, group, rpm=None, role='support', holes=()):
        p=Part(name,circle(outer),([circle(bore)] if bore else [])+list(holes),length,z,frame=frame,role=role)
        return member(p,group,rpm)

    def bevel(name, teeth, shaft, angle, frame, phase, group, rpm=None):
        # Exact spherical flank intersected by planar Z sections. Spiral phase
        # varies across a section because each vertex has R=Z/cos(theta).
        profile=q['output_profile' if group in ('output','spider') else 'side_profile']
        heel=q['cone_distance']*cos(angle)
        outer=bevel_section(profile,heel,phase)
        toe=heel*q['inner_scale']
        small=[(x*q['inner_scale'],y*q['inner_scale']) for x,y in outer]
        holes=[circle(shaft/2)]
        p=Part(name,outer,holes,heel-toe,toe,frame=frame)
        p.stations=[dict(z=0,outer=small,holes=holes),dict(z=heel-toe,outer=outer,holes=holes)]
        p.profile_metadata={'bevel_profile':dict(method='Exact spherical involute with logarithmic trace',
            conjugacy_verified=True,verification_scope='Analytic working flanks; sampled surfaces and nonworking relief require discrete motion checks',
            pitch_cone_angle_deg=degrees(angle),base_cone_angle_deg=degrees(profile.base),
            root_cone_angle_deg=degrees(profile.root),tip_cone_angle_deg=degrees(profile.tip),
            root_method='Nonworking constant-half-angle continuation below base; deepened to clear mate addendum',
            cone_distance_mm=q['cone_distance'],face_width_mm=v['width'],teeth=teeth,
            profile_refinement_threshold_mm=PROFILE_TOLERANCE,
            section_end_convention='Planar Z caps at pitch-cone heel/toe; actual vertex R=Z/cos(theta)',
            engagement=q['engagement'],
            flank_reference_doi='10.3389/fmech.2025.1643228',flank_reference_equation='Section 2 equation 1')}
        if v['variant']=='spiral':
            hand=-v['spiral_hand'] if group in ('output','spider') else v['spiral_hand']
            if v['spiral_angle']:
                p.stations=[dict(z=0 if distance==distances[0] else (distance/q['cone_distance'])*heel-toe,
                    outer=transformed([(x*distance/q['cone_distance'],y*distance/q['cone_distance']) for x,y in outer],
                                      angle=spiral_trace(distance,q['cone_distance'],angle,v['spiral_angle'],hand)),
                    holes=holes) for distance in distances]
            p.profile_metadata['bevel_profile'].update(spiral_angle_deg=v['spiral_angle'],local_spiral_hand=hand,
                trace='theta = hand * tan(beta) / sin(delta) * ln(R / R_outer)',
                trace_chord_tolerance_mm=TRACE_CHORD_TOLERANCE,cone_stations_mm=list(distances),
                reference_doi='10.1007/s00170-025-16738-7')
        face_count=2*sum(len(loop) for loop in [outer]+holes)*(len(p.stations)-1)+2
        if face_count>250000:
            raise ValueError('Spherical bevel surface exceeds the shared 250,000-face budget; reduce dimensions, width or spiral angle.')
        member(p,group,rpm)
        return heel,toe,max(hypot(x,y) for x,y in outer)

    # Output has a tooth at +X. Each side has a space at the shared contact line;
    # odd output tooth counts place a space at -X, requiring a half side pitch.
    a_phase=pi/2-pi/v['side_teeth']
    b_phase=-pi/2-(pi/v['side_teeth'] if v['output_teeth']%2==0 else 0)
    side_end,side_toe,side_radius=bevel('Bevel_side_A' if classic else 'Bevel_input_A',v['side_teeth'],v['input_shaft'],q['side_cone_angle'],FRAME_A,a_phase,'A',wa)
    bevel('Bevel_side_B' if classic else 'Bevel_input_B',v['side_teeth'],v['input_shaft'],q['side_cone_angle'],FRAME_B,b_phase,'B',wb)
    out_end,out_toe,_=bevel('Bevel_spider' if classic else 'Bevel_output',v['output_teeth'],q['transverse_bore'],q['output_cone_angle'],FRAME_OUTPUT,0,'spider' if classic else 'output')

    # Independent stub shafts stop at the cone toe and do not cross the centre.
    ra=v['input_shaft']/2;ro=v['spider_pin_diameter' if classic else 'output_shaft']/2
    side_support=max(side_end+t+c,q['output_pitch_radius']+m+c)
    side_length=side_support+t+c+v['shaft_extension']-side_toe
    for tag,frame in (('A',FRAME_A),('B',FRAME_B)):
        rate=wa if tag=='A' else wb
        if classic:
            # A passes through the carrier input mount; reserve its full width
            # before measuring the exposed output extension, including plate=12.
            face=side_support+t+(t if tag=='A' else 0)
            interface=face+v['shaft_extension']
            end=interface+(t if v['output_interface']=='flange' else 0)
            bore=v['passage_diameter']/2 if v['output_interface']=='hollow' else 0
            cylinder('Shaft_output_'+tag,ra,bore,end-side_toe,side_toe,frame,tag,rate)
            cylinder('Hub_output_'+tag,ra+2,ra,t,side_end,frame,tag,rate)
            if v['output_interface']=='flange':
                holes=[circle(v['bolt_diameter']/2,32,polar(q['flange_hole_radius'],2*pi*j/v['bolt_count'])) for j in range(v['bolt_count'])]
                cylinder('Flange_output_'+tag,v['flange_radius'],ra,t,interface,frame,tag,rate,holes=holes)
        else:
            cylinder('Shaft_input_'+tag,ra,0,side_length,side_toe,frame,tag,rate)
            cylinder('Hub_input_'+tag,ra+2,ra,t,side_end,frame,tag,rate)

    out_support=max(out_end+t+c,side_radius+c+t)
    flange_z=out_support+t+2*c
    passage=v['passage_diameter']/2 if v['output_interface']=='hollow' else 0
    shaft_end=flange_z+t if v['output_interface']=='flange' else out_support+t+v['output_extension']
    if classic:
        retainer=min(1.5,t/2)
        cylinder('Pin_spider',ro,0,out_support+t-(out_toe-c-retainer),out_toe-c-retainer,FRAME_OUTPUT,'carrier',speed['carrier'])
        for label,z in (('lower',out_toe-c-retainer),('upper',out_end+c)):
            cylinder('Retainer_spider_'+label,ro+v['spider_clearance']+.8,ro,retainer,z,FRAME_OUTPUT,'carrier',speed['carrier'])
    else:
        cylinder('Shaft_output',ro,passage,shaft_end-out_toe,out_toe,FRAME_OUTPUT,'output')
        cylinder('Hub_output',ro+2,ro,t,out_end,FRAME_OUTPUT,'output')
        if v['output_interface']=='flange':
            holes=[circle(v['bolt_diameter']/2,32,polar(q['flange_hole_radius'],2*pi*j/v['bolt_count'])) for j in range(v['bolt_count'])]
            cylinder('Flange_output',v['flange_radius'],ro,t,flange_z,FRAME_OUTPUT,'output',holes=holes)

    # Open U carrier: two cheeks outside the gear backs, joined behind the
    # pitch-cone apex and above the output gear. Bearings are nominal envelopes.
    # Clearance is reserved at both radial interfaces. Increase the support
    # radius when needed so the bearing envelope retains at least 0.6 mm wall,
    # including at the maximum allowed 1 mm assembly clearance.
    bearing_wall=max(2,2*c+.6);half_y=max(ra,ro)+bearing_wall+2
    transverse_seat=ro if classic else ro+bearing_wall
    bottom=-side_radius-c-t
    for tag,frame in (('A',FRAME_A),('B',FRAME_B)):
        if v['carrier_style']=='split':
            for positive,name in ((True,'front'),(False,'rear')):
                outer=split_cheek(half_y,bottom,out_support+t,ra+bearing_wall,c,positive)
                if tag=='B':outer=[(x,-y) for x,y in reversed(outer)]
                member(Part(f'Carrier_cheek_{tag}_{name}',outer,[],t,side_support,frame=frame,role='support'),'carrier',speed['carrier'])
        else:
            outer=[(-half_y,bottom),(half_y,bottom),(half_y,out_support+t),(-half_y,out_support+t)]
            # B's local Y points down in world Z; keep both cheeks on the same side.
            if tag=='B':outer=[(x,-y) for x,y in reversed(outer)]
            p=Part('Carrier_cheek_'+tag,outer,[circle(ra+bearing_wall)],t,side_support,frame=frame,role='support')
            member(p,'carrier',speed['carrier'])
        cylinder(('Bearing_side_' if classic else 'Bearing_input_')+tag+'_envelope',ra+bearing_wall-c,ra+c,t,side_support,frame,'carrier',speed['carrier'])
    # Split bridge ends butt against the cheek inner faces; they do not occupy
    # the cheek volumes at the four corners. Preserve the original open model.
    span=side_support if v['carrier_style']=='split' else side_support+t
    if v['carrier_style']=='split':
        layer=(t-c)/2
        for label,z,seat in (('spider' if classic else 'output',out_support,transverse_seat),('rear',bottom,0)):
            for positive,name in ((True,'front'),(False,'rear')):
                outer,holes=split_bridge(span,half_y,seat,c,v['carrier_bolt_diameter']/2,positive,side_support)
                p=Part(f'Carrier_{label}_bridge_{name}',outer,holes,layer,z+(0 if positive else layer+c),role='support')
                p.machining=[dict(type='clearance_hole',diameter=v['carrier_bolt_diameter'],center=list(circle_center),
                    through=True,z0=0,z1=layer,source='Nominal split carrier lap joint; fasteners to be selected')
                    for circle_center in ((-(side_support+seat)/2,0),((side_support+seat)/2,0))]
                member(p,'carrier',speed['carrier'])
    else:
        outer=[(-span,-half_y),(span,-half_y),(span,half_y),(-span,half_y)]
        member(Part('Carrier_spider_bridge' if classic else 'Carrier_output_bridge',outer,[circle(transverse_seat)],t,out_support,role='support'),'carrier',speed['carrier'])
        member(Part('Carrier_rear_bridge',outer,[],t,bottom,role='support'),'carrier',speed['carrier'])
    if classic:
        # Direct carrier input: annular mount is coaxial with side A and clears
        # its output shaft. Hole ligaments are derived, not guessed stock sizes.
        inner=ra+bearing_wall+c;bolt=v['carrier_bolt_diameter']/2;outside=inner+2*bolt+2.4
        pitch=(inner+outside)/2
        holes=[circle(bolt,48,polar(pitch,2*pi*j/4+pi/4)) for j in range(4)]
        if 2*bolt+1.2>=2*pitch*sin(pi/4):raise ValueError('Carrier input mount holes leave insufficient spacing.')
        mount=cylinder('Flange_carrier_input',outside,inner,t,side_support+t,FRAME_A,'carrier',speed['carrier'],holes=holes)
        mount.machining=[dict(type='clearance_hole',diameter=2*bolt,through=True,center=list(polar(pitch,2*pi*j/4+pi/4)),
            z0=0,z1=t,source='Nominal direct carrier input mount; drive and fasteners to be selected') for j in range(4)]
    else:cylinder('Bearing_output_envelope',ro+bearing_wall-c,ro+c,t,out_support,FRAME_OUTPUT,'carrier',speed['carrier'])

    equations=(['side_a = carrier - prescribed_difference / 2', 'side_b = carrier + prescribed_difference / 2',
                'spider_spin = (side_teeth / spider_teeth) * prescribed_difference / 2'] if classic else
               ['carrier = (input_a + input_b) / 2','output_spin = (side_teeth / output_teeth) * (input_b - input_a) / 2'])
    d.analysis.update(differential=True,configuration=v['configuration'],
        kinematics=dict(kind='classic_bevel_differential' if classic else 'two_input_bevel_wrist',rates_rpm=speed,equations=equations,
        reference='Carrier and both side output signs use world +X; internal spider spin is relative to carrier +Z' if classic else 'Both input signs use world +X; output spin is relative to carrier +Z'),
        bevel=dict(pitch_cone_distance_mm=q['cone_distance'],side_pitch_angle_deg=degrees(q['side_cone_angle']),
                   output_pitch_angle_deg=degrees(q['output_cone_angle']),profile_method='Exact spherical involute with logarithmic trace',
                   conjugacy_verified=True,verification_scope='Analytic working flanks; discrete sampled motion is separate',
                   profile_refinement_threshold_mm=PROFILE_TOLERANCE,engagement=q['engagement']))
    d.analysis['bevel'].update(variant=v['variant'],spiral_angle_deg=v['spiral_angle'] if v['variant']=='spiral' else 0,
        input_local_spiral_hand=v['spiral_hand'] if v['variant']=='spiral' else 0,
        cone_stations_mm=list(distances),trace_chord_tolerance_mm=TRACE_CHORD_TOLERANCE if v['variant']=='spiral' else None)
    if classic:
        d.analysis['bevel']['side_local_spiral_hand']=d.analysis['bevel'].pop('input_local_spiral_hand')
    construction=dict(output_interface=v['output_interface'],carrier_style=v['carrier_style'],ratio_mode=v['ratio_mode'],
        split_seam_gap_mm=c if v['carrier_style']=='split' else 0,
        joining_hole_diameter_mm=v['carrier_bolt_diameter'] if v['carrier_style']=='split' or classic else 0)
    if classic:
        construction.update(side_extension_mm=v['shaft_extension'],side_passage_diameter_mm=2*passage,
            passage_scope='Each side output axis only; spider and pin can obstruct a route through the complete mechanism',
            spider_pin_diameter_mm=2*ro,spider_bore_diameter_mm=q['transverse_bore'],spider_radial_running_clearance_mm=v['spider_clearance'],
            spider_axial_clearance_mm=c,carrier_input_mount_thickness_mm=t)
        d.analysis['classic_construction']=construction
        d.analysis['kinematics'].update(prescribed_difference_rpm=v['output_difference_rpm'],
            boundary_condition='B-A is prescribed for visualization; no load-based speed split or second motor input',
            reference_source='https://www.mathworks.com/help/sdl/ref/differential.html',reference_section='Equations / Ideal Fundamental Constraints')
        d.metrics=[f"Carrier input: {speed['carrier']:+g} rpm · prescribed B−A: {v['output_difference_rpm']:+g} rpm",
                   f"Side outputs A / B: {wa:+g} / {wb:+g} rpm · internal spider spin: {relative_spin:+g} rpm"]
        d.notes.append('Classic differential: direct carrier input and two coaxial side outputs. B−A is a prescribed kinematic boundary condition for visualization, not a second motor, physical differential lock or speed split predicted from loads. No crown/pinion drive is generated.')
        d.notes.append('The spider turns on a carrier-fixed pin with explicit radial running clearance and nominal axial retainers. Pin retention, lubrication, wear and bearing capacity require design; no stock bearings or threads are inferred.')
    else:
        construction.update(output_extension_mm=shaft_end-(out_support+t),output_passage_diameter_mm=2*passage,
            passage_scope='Output axis from gear toe to shaft end only; no full cable route')
        d.analysis['wrist_construction']=construction
        d.metrics=[f"Inputs A / B: {wa:+g} / {wb:+g} rpm",
                   f"Carrier tilt: {speed['carrier']:+g} rpm · relative output spin: {relative_spin:+g} rpm"]
        d.notes.append('Two independent input stub shafts; equal signed input speeds tilt the carrier, opposing speeds spin the output. Both input signs are measured about the same world +X axis.')
    d.metrics.append(f"Side / transverse teeth: {v['side_teeth']} / {v['output_teeth']} · pitch cone distance {q['cone_distance']:.3f} mm")
    d.notes.extend([
        'Working tooth flanks are exact spherical involutes with a conjugate logarithmic trace. The exported surfaces are sampled approximations; nonworking root relief is constructed, not a generated cutter fillet. Discrete interference checks do not certify continuous clearance, loaded contact, strength or manufacturing readiness.',
        'Shafts, carrier and output connection are nominal interfaces. Bearing envelopes are not selected commercial bearings. Complete axial retention, fits, fasteners and mounting in CAD.',
        'The generator includes no belts, pulleys or motors. Add the external drive and mechanism mounting in your CAD assembly.'])
    if passage:d.notes.append('The hollow passage is continuous locally through each active output gear/shaft/hub assembly from its gear toe to shaft end. It is not a verified unrestricted route through the complete differential mechanism or its moving members.')
    if v['variant']=='spiral':d.notes.append('Logarithmic pitch-cone trace from Cumbicus et al., DOI 10.1007/s00170-025-16738-7, section 3.2 equations 8–9. Local side gear hands match and transverse gear hand is opposite. Every flank vertex uses its actual apex distance. Shared pitch-distance stations bound sampled vertex-trace chord deviation to 0.003 mm; the separate 0.003 mm section refinement threshold is a numerical criterion, not an industrial flank tolerance.')
    if v['carrier_style']=='split':d.notes.append('Split carrier: open bearing-seat halves separated in Y, joined by overlapping bridge tabs in two axial layers with real matching clearance holes. No stock fasteners, thread engagement, clamp strength or seat preload are inferred.')
    d.requirements.append('Verify sampled tooth surfaces, root relief and continuous collision clearance before manufacturing. Size all active member supports, bearing seats, shaft couplings and retention for the selected configuration.')
