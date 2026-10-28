# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Printable cycloidal eccentric stack clamped by two off-axis M3 tie bolts.

The asymmetric bolt pattern provides a positive rotational constraint and
indexes opposing cams. Bearing dimensions are from NSK 6804; this construction
is an original adaptation, not a reproduction or a rated mechanical design.
"""
from math import hypot, pi, cos, sin
from geometry import Part, circle
from hardware_catalog import FASTENERS, LENGTHS, SCREW_SOURCE, NUT_SOURCE, WASHER_SOURCE

DESIGNS = {'standard': 'Standard · separate shaft and cams',
           'fdm_bolted': 'FDM · printed shaft + 2 through bolts'}
SUPPORTED_SCHEMES = ('eccentric_output_ring', 'eccentric_ring_output')
BEARING_URL = 'https://www.nsk.com/in-en/engineering/products/bearings/ball-bearings/deep-groove-ball-bearings/single-row-deep-groove-ball-bearings/6804-apn.html?___store=in'
PRESET = dict(input_shaft=17., bore=32.2, width=16., bearing_mode='manual',
              hardware_mode='none', print_bolt_pitch=8.6, print_hole_clearance=.35,
              print_seat_allowance=.2, print_journal_allowance=.15, print_min_wall=1.2)
FIELDS = [('print_bolt_pitch', 'Through bolt spacing [mm]', 8.6, 5, 20, .1),
          ('print_hole_clearance', 'Bolt hole diametral clearance [mm]', .35, .1, .8, .05),
          ('print_seat_allowance', '6804 seat diametral allowance [mm]', .2, 0, .6, .05),
          ('print_journal_allowance', '6804 journal diametral clearance [mm]', .15, 0, .5, .05),
          ('print_min_wall', 'Minimum printed wall [mm]', 1.2, 1, 3, .2)]


def prepare(supplied):
    s = dict(supplied)
    design = s.get('eccentric_design', 'standard')
    if design not in DESIGNS:
        raise ValueError('Unknown eccentric shaft design.')
    if design != 'fdm_bolted':
        return s
    if s.get('io_scheme', SUPPORTED_SCHEMES[0]) not in SUPPORTED_SCHEMES:
        raise ValueError('The FDM shaft requires eccentric input and either pin flange or ring / housing output. Use the standard shaft for other driving members.')
    if s.get('bearing_mode', 'manual') != 'manual' or s.get('hardware_mode', 'none') != 'none':
        raise ValueError('The FDM shaft includes its own 6804 bearings and tie bolts. Set the general bearing catalog to manual and additional hardware to none.')
    for key in ('input_shaft', 'width'):
        s.setdefault(key, PRESET[key])
    s['bore'] = 32 + float(s.get('print_seat_allowance', .2))
    return s


def _stepped(name, levels, centers, hole_radius, role='gear', color=(.25,.72,.8)):
    """Levels are absolute Z, radius, XY centre, hole radius (two holes)."""
    z0 = levels[0][0]
    stations = [dict(z=z-z0, outer=circle(r,192,c),
                     holes=[circle(hr,128,p) for p in centers]) for z,r,c,hr in levels]
    return Part(name,stations[0]['outer'],stations[0]['holes'],levels[-1][0]-z0,z0,
                role=role,color=color,stations=stations)


def _buy(p, code, description, dimensions, standard, source, manufacturer='To be selected'):
    p.procurement = dict(code=code,description=description,dimensions=dimensions,
                         standard=standard,source=source,manufacturer=manufacturer)
    return p


def apply(d):
    if d.family != 'cycloidal' or d.values.get('eccentric_design') != 'fdm_bolted':
        return
    v=d.values;e=v['eccentric'];w=v['width'];count=2 if v['variant']=='dual' else 1
    gap=v.get('disc_gap',v['assembly_clearance']);span=count*w+(count-1)*gap
    wall=v['print_min_wall'];rin=v['input_shaft']/2
    fit=v['print_journal_allowance'];journal=(20-fit)/2
    # NSK 6804: d=20, D=32, B=7; inner-ring shoulder da >=22 mm.
    shoulder=11.2;B=7.;low_shoulder=2.;cap_t=5.2;cap_floor=1.5;protrusion=.12
    f=FASTENERS['M3'];hole=(3+v['print_hole_clearance'])/2
    pocket=(f['washer_od']+v['print_hole_clearance'])/2
    pitch=v['print_bolt_pitch']
    # A 1 mm radial asymmetry indexes the printed stack against a 180° flip.
    centers=[(0.,pitch/2+.5),(0.,-pitch/2+.5)]
    if wall>cap_floor:
        raise ValueError('The recessed FDM cap has a 1.5 mm floor. Reduce minimum wall or choose a different shaft construction.')
    if pitch-2*pocket < wall:
        raise ValueError('FDM bolt head pockets are too close: increase through bolt spacing or reduce hole clearance.')
    if min(rin-hypot(*p)-hole for p in centers) < wall:
        raise ValueError('FDM shaft is too small for two bolt holes and the minimum wall. Increase input shaft diameter or reduce bolt spacing.')
    if rin+e >= journal-.1:
        raise ValueError('FDM shaft/eccentricity do not fit inside the 6804 journal. Reduce input shaft diameter or eccentricity.')
    if max(hypot(x-e,y)+pocket for x,y in centers) > shoulder-wall:
        raise ValueError('FDM cap pockets leave insufficient wall around the eccentric shoulder.')
    if min(journal-hypot(x-e,y)-hole for x,y in centers)<wall:
        raise ValueError('FDM bolt holes leave insufficient wall in the 6804 journal.')
    if w < low_shoulder+B+cap_t+.5:
        raise ValueError('FDM disc thickness must leave room for the 7 mm bearing and recessed bolt cap (at least 14.7 mm).')
    if fit < 0 or 20-fit <= 0:
        raise ValueError('Invalid 6804 journal clearance.')
    bottom=-v['assembly_clearance']-v['plate']-8
    last_start=(count-1)*(w+gap);cap_z=last_start+low_shoulder+B
    head_bottom=cap_z+cap_floor+f['washer_t']
    nut_top=bottom-f['washer_t'];nut_bottom=nut_top-f['nut']
    required=head_bottom-nut_bottom+2*f['pitch']
    length=next((L for L in LENGTHS if L>=required),None)
    if length is None:
        raise ValueError('FDM stack is too long for the available M3 through bolts (120 mm maximum).')
    bolt_bottom=head_bottom-length
    if bottom-bolt_bottom<2*f['pitch']+f['nut']+f['washer_t']-1e-7:
        raise ValueError('FDM bolts do not engage the full nut and two thread pitches.')
    removed={'Shaft_input'}
    d.parts[:]=[p for p in d.parts if p.name not in removed and not p.name.startswith(('Eccentric_','Bearing_eccentric_'))]
    bodies=[]
    def body(name,levels):
        p=_stepped(name,levels,centers,hole)
        p.machining=[dict(type='through_bolt_pair',diameter=2*hole,centers_mm=[list(x) for x in centers],
                          spacing_mm=pitch,minimum_wall_mm=wall)]
        d.parts.append(p);bodies.append(p);return p
    for j in range(count):
        z=j*(w+gap);c=(e if j==0 else -e,0.)
        if j==0:
            levels=[(bottom,rin,(0,0),hole),(0,rin,(0,0),hole),
                    (0,shoulder,c,hole)]
        else:
            prev=(e,0.);prior=low_shoulder+B
            levels=[(prior,shoulder,prev,hole),(prior+2,shoulder,prev,hole),
                    (prior+2,rin,(0,0),hole),(z,rin,(0,0),hole),
                    (z,shoulder,c,hole)]
        levels += [(z+low_shoulder,shoulder,c,hole),(z+low_shoulder,journal,c,hole),
                   (z+low_shoulder+B-protrusion,journal,c,hole)]
        body('Eccentric_printed_base' if j==0 else 'Eccentric_printed_stage_2',levels)
        bearing=Part(f'Bearing_eccentric_{j+1}_NSK_6804',circle(16,256),[circle(10,192)],B,z+low_shoulder,c,
                     role='gear',color=(.52,.57,.63))
        _buy(bearing,'NSK 6804','Open deep groove ball bearing','20 × 32 × 7 mm','6804',BEARING_URL,'NSK')
        d.parts.append(bearing)
    c=(e if count==1 else -e,0.)
    cap=body('Eccentric_printed_cap',[(cap_z,shoulder,c,hole),
          (cap_z+cap_floor,shoulder,c,hole),(cap_z+cap_floor,shoulder,c,pocket),
          (cap_z+cap_t,shoulder,c,pocket)])
    cap.machining.append(dict(type='bolt_head_counterbore',diameter=2*pocket,depth=cap_t-cap_floor,
                             centers_mm=[list(x) for x in centers]))
    steel=(.62,.67,.73)
    for j,xy in enumerate(centers,1):
        bolt=_stepped(f'Eccentric_tie_bolt_{j}',[(bolt_bottom,1.5,xy,0),
              (head_bottom,1.5,xy,0),(head_bottom,f['head']/2,xy,0),
              (head_bottom+f['k'],f['head']/2,xy,0)],[],0,color=steel)
        _buy(bolt,f'ISO4762-M3x{length}','Hex socket head cap screw',f'M3 × {length} mm','ISO 4762',SCREW_SOURCE)
        d.parts.append(bolt)
        for tag,z in [('lower',nut_top),('upper',cap_z+cap_floor)]:
            washer=Part(f'Eccentric_tie_washer_{j}_{tag}',circle(f['washer_od']/2),
                        [circle(f['washer_id']/2)],f['washer_t'],z,xy,role='gear',color=steel)
            _buy(washer,'ISO7089-M3','Flat washer','3.2 × 7 × 0.5 mm','ISO 7089',WASHER_SOURCE)
            d.parts.append(washer)
        r=f['af']/(2*cos(pi/6));outer=[(r*cos(pi/6+2*pi*k/6),r*sin(pi/6+2*pi*k/6)) for k in range(6)]
        nut=Part(f'Eccentric_tie_nut_{j}',outer,[circle(1.5)],f['nut'],nut_bottom,xy,role='gear',color=steel)
        _buy(nut,'ISO4032-M3','Hex nut','M3 · AF 5.5 × 2.4 mm','ISO 4032',NUT_SOURCE)
        d.parts.append(nut)
    d.analysis['printed_eccentric_shaft']=dict(design='fdm_bolted',bolt_count=2,bolt_size='M3',
        bolt_length_mm=length,bolt_centers_mm=[list(p) for p in centers],bolt_hole_diameter_mm=2*hole,
        bearing='NSK 6804',bearing_dimensions_mm=[20,32,7],bearing_count=count,
        journal_diameter_mm=2*journal,seat_diameter_mm=v['bore'],printed_parts=[p.name for p in bodies],
        bearing_axial_protrusion_mm=protrusion,
        phase_deg=[0,180][:count],cap_top_mm=cap_z+cap_t,disc_stack_top_mm=span,
        output_member=v['io_scheme'].split('_')[1],fixed_member=v['io_scheme'].split('_')[2],
        minimum_wall_mm=wall,torque_connection='asymmetric pair of off-axis bolts; bearing in printed holes',
        external_motor_coupling='to be designed for the two-bolt pattern or printed input journal')
    d.metrics.append(f'FDM eccentric shaft · 2 × M3×{length} through bolts · {count} × NSK 6804')
    d.notes.append('The printed eccentric stack is split into a base, an intermediate cam for dual discs, and a removable end cap. Two off-axis through bolts constrain relative rotation; the asymmetric pattern indexes the 180° cam phase. Torque is transmitted through bolt/hole bearing, not solely clamp friction. Bolt clearance permits finite play; this is not a zero-backlash coupling.')
    d.notes.append('The 6804 bearing inner rings sit between printed shoulders and removable retainers, with 0.12 mm journal relief so the stack can clamp the inner rings before the printed journal ends bottom out. Head/washer pockets are recessed below the disc stack top; nuts and lower washers are outside the input end. Threads and socket recesses are simplified reference geometry; the bolts are purchased steel parts.')
    d.requirements.append('FDM assembly: fit bearings from the open cam ends, stack the indexed printed parts, insert both M3 bolts, then fit washers and nuts. Ream/measure holes and bearing seats on a calibration print. Tightening torque, polymer creep, fatigue and allowable input torque require testing; no load rating is assigned.')
    d.requirements.append('Design the external motor coupling for the printed input journal or asymmetric two-bolt pattern. Do not treat either reinforcement bolt as the free rotation axis. Remaining input/output support bearing envelopes still require actual component selection.')


def mount_housing_output(d, record):
    """Retain the bolted input stack and route the housing around the fixed hub.

    No solid central input adapter is added: it would fill the two tie-bolt
    passages. The original output shaft is extended, rather than overlapped by
    a duplicate shaft, to provide the stationary pin-carrier connection.
    """
    from mounting import part, port, radius, bore
    q=record['stage_results'][0];v=d.values;t=v['plate'];g=v['assembly_clearance']
    byname={p.name:p for p in d.parts}
    cover=byname['Cover_output'];carrier=byname['Flange_output'];shaft=byname['Shaft_output']
    base=byname['Eccentric_printed_base'];data=d.analysis['printed_eccentric_shaft']
    ro=radius(cover.outer);ri=max(bore(cover),radius(carrier.outer)+g)
    if ri>=ro-2*v['print_min_wall']:
        raise ValueError('Insufficient annular material for the FDM housing output flange.')
    contact=cover.z+cover.width;plane=contact+8
    ring_port=port(q,'ring');fixed_port=port(q,'output')
    neck=part(d,'Attachment_ring_Hub',ro,ri,contact,plane,ring_port)
    # A full M3 washer footprint fits on the added 7 mm radial rim.
    flange_r=ro+7;bolt_r=ro+3.5;hole=(3+v['print_hole_clearance'])/2
    ring_holes=[circle(hole,64,(bolt_r*cos(2*pi*j/6),bolt_r*sin(2*pi*j/6))) for j in range(6)]
    flange=part(d,'Attachment_ring_Flange',flange_r,ri,plane,plane+t,ring_port,holes=ring_holes)
    neck.role=flange.role='gear'
    # The stationary frame plate lies beyond the moving flange, with a clear
    # coaxial shaft route through its central opening.
    frame_z=plane+t+max(4,t+g);shaft.width=frame_z-shaft.z
    frame_r=min(ri-g-1,max(radius(shaft.outer)+8,12))
    frame_bolt_r=frame_r-3.5
    if frame_bolt_r-hole<=radius(shaft.outer)+v['print_min_wall']:
        raise ValueError('Fixed pin-carrier flange leaves insufficient material around its shaft and M3 holes.')
    frame_holes=[circle(hole,64,(frame_bolt_r*cos(2*pi*j/8),frame_bolt_r*sin(2*pi*j/8))) for j in range(8)]
    frame=part(d,'Attachment_output_Frame_flange',frame_r,0,frame_z,frame_z+t,fixed_port,holes=frame_holes)
    records=d.analysis.setdefault('mount_interfaces',[])
    records.append(dict(member='eccentric',role='input',stage=1,anchor=base.name,
        parts=data['printed_parts']+['Eccentric_tie_bolt_1','Eccentric_tie_bolt_2'],
        contact_z_mm=base.z,terminal_z_mm=base.z,direction=-1,center_mm=(0,0,base.z),axis=(0,0,1),
        bolt_count=2,bolt_centers_mm=data['bolt_centers_mm'],status='printed two-bolt input; external motor coupling required'))
    records.append(dict(member='ring',role='output',stage=1,anchor=cover.name,
        parts=[neck.name,flange.name],contact_z_mm=contact,terminal_z_mm=plane,direction=1,
        center_mm=(0,0,plane),axis=(0,0,1),neck_outer_radius_mm=ro,neck_inner_radius_mm=ri,
        flange_outer_radius_mm=flange_r,flange_thickness_mm=t,bolt_count=6,
        bolt_circle_radius_mm=bolt_r,bolt_hole_diameter_mm=2*hole,
        status='nominal annular housing output; load fasteners and bearing selection required'))
    records.append(dict(member='output',role='fixed',stage=1,anchor=carrier.name,
        parts=[shaft.name,frame.name],contact_z_mm=carrier.z+carrier.width,terminal_z_mm=frame_z,direction=1,
        center_mm=(0,0,frame_z),axis=(0,0,1),neck_outer_radius_mm=radius(shaft.outer),neck_inner_radius_mm=0,
        flange_outer_radius_mm=frame_r,flange_thickness_mm=t,bolt_count=8,
        bolt_circle_radius_mm=frame_bolt_r,bolt_hole_diameter_mm=2*hole,
        status='nominal stationary pin-carrier attachment; frame and fasteners required'))
    data['output_member']='ring'
    data['fixed_member']='output'
    data['housing_output_flange']=flange.name
    data['fixed_frame_flange']=frame.name
    d.analysis['mounting_status']='nominal_role_adapted'
    d.notes.append('FDM housing output: the eccentric stack and both tie bolts remain the input; output pins and their carrier are fixed to the frame. The roller ring, tubular housing, covers and annular six-hole flange rotate together. The stationary eight-hole frame flange is axially beyond the moving output flange; the fixed shaft passes through its clear central opening.')
    d.requirements.append('Connect the load to the annular housing flange and the frame to the separate pin-carrier flange. Select the remaining support bearings, their axial retention and interface fasteners; these mount holes are nominal M3 clearances, not purchased fasteners or a load rating.')
