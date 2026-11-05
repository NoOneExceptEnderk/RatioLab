# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Printable cycloidal eccentric stack clamped by two off-axis M3 tie bolts.

The asymmetric bolt pattern provides a positive rotational constraint and
indexes opposing cams. Bearing dimensions are from NSK 6804; this construction
is an original adaptation, not a reproduction or a rated mechanical design.
"""
from math import hypot, pi, cos, sin, sqrt, acos, radians
from geometry import Part, circle, transformed
from hardware_catalog import FASTENERS, LENGTHS, SCREW_SOURCE, NUT_SOURCE, WASHER_SOURCE, KEYS, KEY_LENGTHS, KEY_SOURCE, KEY_PRODUCT

DESIGNS = {'integral': 'Integral shaft · solid eccentrics',
           'd_shaft': 'Direct D-shaft · matching cam bores',
           'keyed_shaft': 'Direct keyed shaft · matching keyways',
           'standard': 'Separate bored cams · CAD fixing required',
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
DIRECT_FIELDS = [('eccentric_flat_depth', 'D-shaft flat depth [mm]', .5, .05, 14, .05),
                 ('eccentric_bore_allowance', 'Cam bore diametral allowance [mm]', 0, 0, .5, .01),
                 ('eccentric_connection_angle', 'Shaft connection clocking [°]', 0, -180, 180, 1)]
KEYED_PRESET = dict(input_shaft=6., bore=18., width=10., bearing_mode='manual')


def direct_field_active(key, construction):
    if key == 'eccentric_flat_depth':
        return construction == 'd_shaft'
    return construction in ('d_shaft', 'keyed_shaft')


def prepare(supplied):
    s = dict(supplied)
    design = s.get('eccentric_design', 'integral')
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


def _integral(d):
    """Replace the plain shaft and bored cams with one stepped, solid blank.

    Equal-Z nested sections form the radial shoulders without a loft or an
    overlapping shaft. Catalog journal radii have already been resolved.
    """
    shaft = next(p for p in d.parts if p.name == 'Shaft_input')
    cams = [p for p in d.parts if p.name.startswith('Eccentric_')]
    rin = d.values['input_shaft']/2
    z0 = shaft.z
    levels = [(z0, rin, (0, 0))]
    for index, cam in enumerate(cams):
        radius = hypot(*cam.outer[0])
        if index == 0 or cam.z > cams[index-1].z + cams[index-1].width:
            levels.append((cam.z, rin, (0, 0)))
        levels.extend([(cam.z, radius, cam.center),
                       (cam.z+cam.width, radius, cam.center)])
        if index < len(cams)-1:
            levels.append((cam.z+cam.width, rin, (0, 0)))
    shaft.stations = [dict(z=z-z0, outer=circle(r,192,center), holes=[])
                      for z,r,center in levels]
    shaft.width = levels[-1][0]-z0
    shaft.holes = []
    shaft.role = 'gear'
    d.parts[:] = [p for p in d.parts if p not in cams]
    d.analysis['eccentric_connection'] = dict(construction='integral',
        part=shaft.name, cam_count=len(cams), shaft_bore=False,
        status='one solid CAD blank; external coupling and axial retention to be defined')
    d.requirements[:] = [r.replace('Eccentric cams, pins and output flange connection:',
                                  'Pins and output flange connection:') for r in d.requirements]
    d.notes.append('Integral eccentric shaft: one solid stepped body, without a shaft bore or separate cam fasteners. Disc profiles, eccentric offsets and bearing seats retain their nominal dimensions.')
    d.requirements.append('Complete the integral shaft external coupling, axial bearing retention and any manufacturing details in CAD.')


def _d_profile(radius, flat_x, *, round_section=False):
    """Circle clipped at +X; corresponding round section for axial shoulders.

    Flat endpoints: y=±sqrt(r²-x²), arc angles ±acos(x/r). The fixed
    correspondence gives a planar shoulder when the flat starts at one Z.
    """
    theta = acos(flat_x/radius)
    y = sqrt(radius*radius-flat_x*flat_x)
    points = [(radius*cos(theta+(2*pi-2*theta)*j/256),
               radius*sin(theta+(2*pi-2*theta)*j/256)) for j in range(257)]
    points[0], points[-1] = (flat_x,y), (flat_x,-y)
    for j in range(1,32):
        yy = -y+2*y*j/32
        points.append((sqrt(max(0,radius*radius-yy*yy)) if round_section else flat_x, yy))
    return points


def _direct(d):
    """Direct shaft engagement; no intermediate insert or invented fixing.

    Local part XY is translated from the common world input axis, then the
    unchanged member motion rotates the complete connection. Key dimensions
    use the existing Ganter DIN 6885-1 extract (d,b,h,t4,t2), not fit classes.
    """
    from hardware import shaped_circle
    v = d.values
    construction = v['eccentric_design']
    shaft = next(p for p in d.parts if p.name == 'Shaft_input')
    cams = [p for p in d.parts if p.name in ('Eccentric_1','Eccentric_2')]
    r = v['input_shaft']/2
    allowance = v['eccentric_bore_allowance']/2
    angle = radians(v['eccentric_connection_angle'])
    rotate = lambda points: transformed(points, angle=angle)
    engagements = []
    if construction == 'd_shaft':
        depth = v['eccentric_flat_depth']
        if not 0 < depth < r:
            raise ValueError('D-shaft flat depth must be positive and smaller than the shaft radius.')
        if allowance >= depth:
            raise ValueError('Cam bore allowance removes the D-flat engagement: reduce the allowance or increase flat depth.')
        round_profile = _d_profile(r,r-depth,round_section=True)
        engaged_profile = _d_profile(r,r-depth)
        bore_profile = rotate(_d_profile(r+allowance,r-depth+allowance))
        engagements = [(cams[0].z,cams[-1].z+cams[-1].width)]
        record = dict(flat_depth_mm=depth)
    else:
        diameter = v['input_shaft']
        nominal = round(diameter)
        if abs(diameter-nominal)>1e-8 or nominal not in KEYS:
            raise ValueError('Keyed eccentric shaft requires a nominal diameter of 6, 8, 10 or 12 mm. Apply the compatible keyed dimensions or set the shaft and seat explicitly.')
        b,h,ts,th = KEYS[nominal]
        lengths = [length for length in KEY_LENGTHS if length <= v['width']-1]
        if not lengths:
            raise ValueError('Keyed eccentric cams require disc thickness of at least 9 mm for the supported 8 mm key. Apply the compatible keyed dimensions or increase thickness.')
        if allowance >= h-ts:
            raise ValueError('Cam bore allowance removes key engagement: reduce the allowance.')
        length = max(lengths)
        key_spec = dict(b=b,depth=ts)
        round_profile = shaped_circle(r,key_spec,False)
        engaged_profile = shaped_circle(r,key_spec,True)
        bore_profile = rotate(shaped_circle(r+allowance,dict(b=b,depth=th),True,True))
        for cam in cams:
            start = cam.z+(cam.width-length)/2
            engagements.append((start,start+length))
        record = dict(key_width_mm=b,key_height_mm=h,key_length_mm=length,
                      shaft_keyway_depth_mm=ts,hub_keyway_depth_mm=th,source=KEY_SOURCE)
    # A construction margin in the sampled cam, not a strength/tolerance check.
    for cam in cams:
        hole = transformed(bore_profile,(-cam.center[0],-cam.center[1]))
        outer_apothem = min(abs(a[0]*b[1]-a[1]*b[0])/hypot(b[0]-a[0],b[1]-a[1])
                            for a,b in zip(cam.outer,cam.outer[1:]+cam.outer[:1]))
        if max(hypot(x,y) for x,y in hole)+.5 >= outer_apothem:
            raise ValueError('Eccentric connection leaves less than 0.5 mm nominal cam wall: enlarge the eccentric bearing seat or reduce shaft/connection dimensions.')
        cam.holes[0] = hole
        cam.machining.append(dict(type=construction+'_bore',shaft_diameter_mm=2*r,
            diametral_allowance_mm=2*allowance,clocking_deg=v['eccentric_connection_angle'],**record))
    # Keep round journals below the cams and between finite key pockets.
    round_profile, engaged_profile = rotate(round_profile), rotate(engaged_profile)
    levels = [(shaft.z,round_profile)]
    for start,end in engagements:
        levels.extend([(start,round_profile),(start,engaged_profile),(end,engaged_profile)])
        if end < shaft.z+shaft.width:
            levels.append((end,round_profile))
    if levels[-1][0] < shaft.z+shaft.width:
        levels.append((shaft.z+shaft.width,round_profile))
    shaft.outer = round_profile
    shaft.stations = [dict(z=z-shaft.z,outer=profile,holes=[]) for z,profile in levels]
    shaft.role = 'gear'
    shaft.machining.append(dict(type=construction,engagements_z_mm=engagements,**record))
    if construction == 'keyed_shaft':
        for i,(start,end) in enumerate(engagements,1):
            bottom = r-ts
            outline = rotate([(bottom,-b/2),(bottom+h,-b/2),(bottom+h,b/2),(bottom,b/2)])
            key = Part(f'Eccentric_key_{i}',outline,[],end-start,start,role='gear',color=(.94,.72,.33))
            _buy(key,f'DIN 6885-1 B {b:g}x{h:g}x{length:g}','Square ended parallel key',
                 f'{b:g} × {h:g} × {length:g} mm','DIN 6885-1 B',KEY_PRODUCT)
            d.parts.append(key)
        d.notes[:] = [q.replace('keys, threads and seals are not generated.',
            'cam keys and keyways are generated; threads, seals and remaining connections require CAD design.') for q in d.notes]
    d.analysis['eccentric_connection'] = dict(construction=construction,part=shaft.name,
        cam_parts=[p.name for p in cams],shaft_bore=True,intermediate_insert=False,
        diametral_allowance_mm=2*allowance,clocking_deg=v['eccentric_connection_angle'],
        status='matched nominal shaft/cam connection; axial retention and fits to be defined',**record)
    d.requirements[:] = [q.replace('Eccentric cams, pins and output flange connection:',
                                  'Pins and output flange connection:') for q in d.requirements]
    d.requirements.append('Direct eccentric shaft connection: complete axial retention, external coupling and actual fits in CAD. The matched profile does not retain the cam axially.')
    d.notes.append('Direct shaft connection: matching shaft and cam bores share one input-axis datum. No intermediate insert. The input bearing journal stays round; disc profiles and eccentric offsets are unchanged.')


def apply(d):
    if d.family != 'cycloidal':
        return
    construction = d.values.get('eccentric_design')
    if construction == 'integral':
        _integral(d)
        return
    if construction in ('d_shaft','keyed_shaft'):
        _direct(d)
        return
    if construction == 'standard':
        d.analysis['eccentric_connection'] = dict(construction='standard',
            shaft_bore=True, status='CAD fixing required; no cam-to-shaft fastener generated')
        d.requirements.append('Separate bored eccentric cams: define the cam-to-shaft anti-rotation connection and axial retention in CAD. The circular bore alone is not a fixing.')
        return
    if construction != 'fdm_bolted':
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
