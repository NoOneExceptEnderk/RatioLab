# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Nominal zero-shift two-rim spur Wolfrom, axes +Z, positive CCW.

S/P1/Rf use module m1; P2/Ro use the derived m2. The sun is input,
Rf is fixed and Ro is output. Compound portions have one common body clocking.
Reference: COMPAct, arXiv:2510.07197v1, II-D (7-8), III-B (12).
The gcd assembly test is derived from the three tooth-phase congruences.
This is nominal geometry, not a load, efficiency or backdrivability model.
"""
from math import gcd, pi, sin, hypot

SPECS = [
    ('module', 'First layer module [mm]', .5, .25, 10, .05),
    ('sun', 'Sun teeth · input', 18, 8, 160, 1),
    ('planet', 'First planet teeth', 72, 12, 200, 1),
    ('planet2', 'Second planet teeth', 59, 12, 200, 1),
    ('output_ring', 'Output ring teeth', 135, 22, 400, 1),
    ('planets', 'Compound planet count', 3, 1, 8, 1),
    ('pressure', 'Pressure angle [°]', 20, 14.5, 30, .5),
    ('backlash', 'Transverse pair backlash [mm]', .05, 0, 1, .01),
    ('width', 'First layer face width [mm]', 6, 1, 100, .5),
    ('width2', 'Second layer face width [mm]', 6, 1, 100, .5),
    ('layer_gap', 'Gap between toothed layers [mm]', 2, .1, 30, .1),
    ('rim', 'Ring thickness beyond root [mm]', 3, .5, 30, .5),
    ('bore', 'Sun and compound bore diameter [mm]', 3, 1, 100, .5),
    ('plate', 'Carrier plate thickness [mm]', 2, .5, 30, .5),
    ('assembly_clearance', 'Assembly clearance [mm]', .2, .05, 1, .05),
]


def prepare(supplied):
    """Reject unsupported fields, including editable derived dimensions.

    The generic catalog fields are retained for project round trips; their
    manual/none modes are the only modes available for this family. Retired
    material/stress/process fields are discarded for legacy project compatibility.
    """
    from catalog import options as catalog_options
    from hardware_catalog import options as hardware_options
    from engineering import LOAD_FIELDS
    supplied = {key: value for key, value in supplied.items()
                if key != 'material' and not key.startswith(('stress_', 'manufacturing_'))}
    allowed = {q[0] for q in SPECS + LOAD_FIELDS}
    allowed.update(('variant', 'io_scheme'))
    allowed.update(catalog_options('wolfrom', {}))
    allowed.update(hardware_options('wolfrom', {}))
    unknown = set(supplied) - allowed
    if unknown:
        raise ValueError('Unsupported Wolfrom parameter(s): ' + ', '.join(sorted(unknown)) + '. Only zero-shift two-rim spur geometry is supported; fixed_ring and module2 are derived.')
    if supplied.get('variant', 'spur') != 'spur':
        raise ValueError('Wolfrom supports only the two-rim spur variant.')
    return dict(supplied)


def assembly_phases(s, p1, p2, ro, n):
    """Return full-body phases, preserving the same P2-P1 clocking everywhere.

    First-stage n | (S+Rf); second stage solves P2*k1 = -B (mod P1),
    B=(P1*Ro+P2*S)/n. Solvability requires n*gcd(P1,P2) | numerator.
    Normalisation is by full body turns, never separately by tooth pitch.
    """
    if any(isinstance(q, bool) or not isinstance(q, int) or q <= 0 for q in (s, p1, p2, ro, n)):
        raise ValueError('Wolfrom teeth and planet count must be positive integers.')
    rf = s + 2*p1
    divisor = gcd(p1, p2)
    numerator = p1*ro + p2*s
    if (s+rf) % n or numerator % (n*divisor):
        raise ValueError('Equally spaced identical Wolfrom compounds cannot satisfy all three tooth phases: require n dividing S+Rf and n*gcd(P1,P2) dividing P1*Ro+P2*S.')
    mod = p1//divisor
    k1 = 0 if mod == 1 else (-(numerator//n//divisor)*pow(p2//divisor, -1, mod)) % mod
    delta = pi/p2 - pi/p1
    compounds = []
    for j in range(n):
        theta = 2*pi*j/n
        phi1 = (pi+pi/p1+(s+p1)*theta/p1+2*pi*j*k1/p1) % (2*pi)
        compounds.append(dict(index=j+1, theta_rad=theta, planet_phase_rad=phi1,
                              planet2_phase_rad=phi1+delta, reindex=j*k1))
    return dict(k1=k1, common_clocking_rad=delta, fixed_ring_phase_rad=p1*pi/rf,
                output_ring_phase_rad=p2*pi/ro, compounds=compounds,
                basis='neutral backlash; one common rigid P2-P1 clocking; full-body radians')


def dimensions(v):
    s, p1, p2, ro = (v[k] for k in ('sun', 'planet', 'planet2', 'output_ring'))
    rf = s + 2*p1
    determinant = p1*ro - rf*p2
    if ro <= p2:
        raise ValueError('Wolfrom output ring teeth must exceed second planet teeth.')
    if determinant == 0:
        raise ValueError('Wolfrom determinant P1*Ro−Rf*P2 is zero: the output is stationary; no finite reducer ratio exists.')
    m1 = v['module']
    return dict(fixed_ring_teeth=rf, module2_mm=m1*(s+p1)/(ro-p2),
                center_distance_mm=m1*(s+p1)/2, determinant=determinant,
                signed_ratio=(s+rf)*p1*ro/(s*determinant))


def rates(v, rpm):
    q = dimensions(v)
    s, p1, p2, ro = (v[k] for k in ('sun', 'planet', 'planet2', 'output_ring'))
    rf = q['fixed_ring_teeth']
    den = (s+rf)*p1*ro
    return dict(sun=rpm, ring=0, carrier=rpm*s/(s+rf),
                planet=rpm*s*(p1-rf)/((s+rf)*p1), output=rpm*s*q['determinant']/den)


def validate(v):
    """Cheap exact assembly and complete circular support-envelope checks.

    Actual trimmed involute contact and paired polygon certificates are required
    by build before a Design can be accepted. Nothing mutates a previous Design.
    """
    q = dimensions(v)
    assembly_phases(v['sun'], v['planet'], v['planet2'], v['output_ring'], v['planets'])
    m1, m2, a = v['module'], q['module2_mm'], q['center_distance_mm']
    c, rb = v['assembly_clearance'], v['bore']/2
    if v['backlash'] >= .7*min(m1,m2):
        raise ValueError('Wolfrom backlash too large for one of the derived modules.')
    roots = (m1*(v['sun']/2-1.25), m1*(v['planet']/2-1.25), m2*(v['planet2']/2-1.25))
    if rb >= min(roots)-.5:
        raise ValueError('Wolfrom bore leaves insufficient material at the sun or compound roots.')
    if rb <= c:
        raise ValueError('Wolfrom bore must exceed twice the assembly clearance to leave a positive carrier pin.')
    tips = (m1*(v['planet']/2+1), m2*(v['planet2']/2+1))
    separation = 2*a*sin(pi/v['planets']) if v['planets'] > 1 else None
    if separation is not None and separation <= 2*max(tips)+c:
        raise ValueError('Adjacent Wolfrom compound addendum circles overlap or lack assembly clearance; reduce planet count or dimensions.')
    # Shafts/pins traverse the layers; plates and hubs are axially separate.
    pin = rb-c
    if a <= m1*(v['sun']/2+1)+pin+c:
        raise ValueError('Wolfrom carrier pins intersect the sun addendum envelope.')
    hub = min(roots[1:])*.7
    if hub <= rb+.25:
        raise ValueError('Wolfrom compound hub has no positive material around its bore.')
    carrier = a+pin+max(.5,v['plate']*.5)
    return dict(q, pin_radius_mm=pin, hub_radius_mm=hub,
                carrier_radius_mm=carrier, adjacent_center_separation_mm=separation,
                planet_tip_radii_mm=list(tips))


def apply_kinematics(d):
    """Shared operating metadata path for regeneration and geometry reuse."""
    speeds = rates(d.values, d.values['input_rpm'])
    q = dict(input='sun', output='output', fixed='ring',
             signed_ratio=dimensions(d.values)['signed_ratio'], rates_rpm=speeds,
             constraints='S(ws-wc)+P1(wp-wc)=0; Rf(wf-wc)-P1(wp-wc)=0; Ro(wo-wc)-P2(wp-wc)=0')
    d.analysis['kinematics'] = dict(scheme='sun_output_ring',
        label='Sun → output ring · first ring fixed', stage_results=[q], rates_rpm=speeds)
    for p in d.parts:
        member = p.port['member']
        p.port['rpm'] = speeds[member]
        if member == 'planet':
            p.port['orbital_rpm'] = speeds['carrier']


def build(d):
    from geometry import gear_part, Part, circle, polar
    from internal_mesh import plan_planetary_internal_pair
    from engineering import mesh
    v = d.values
    envelope = validate(v)
    phase = assembly_phases(v['sun'], v['planet'], v['planet2'], v['output_ring'], v['planets'])
    m1, m2 = v['module'], envelope['module2_mm']
    s, p1, p2, ro, rf = v['sun'], v['planet'], v['planet2'], v['output_ring'], envelope['fixed_ring_teeth']
    pa, b, w1, w2 = (v[k] for k in ('pressure', 'backlash', 'width', 'width2'))
    z2 = w1+v['layer_gap']
    top = z2+w2
    plans = [plan_planetary_internal_pair(p1,rf,m1,pa,0,b),
             plan_planetary_internal_pair(p2,ro,m2,pa,0,b)]
    for index, plan in enumerate(plans, 1):
        if plan['verification']['status'] != 'clear':
            raise ValueError(f"Wolfrom layer {index}: paired internal polygon clearance must be clear; {plan['verification']['status']}: {plan['verification'].get('failure_reason', '')}")
    meshes = [mesh(s,p1,m1,pa,width=w1,backlash=b),
              mesh(p1,rf,m1,pa,width=w1,internal=True,backlash=b,internal_plan=plans[0]),
              mesh(p2,ro,m2,pa,width=w2,internal=True,backlash=b,internal_plan=plans[1])]
    for index, pair in enumerate(meshes, 1):
        if pair['profile_contact_total'] < 1 or pair['contact_total'] < 1:
            raise ValueError(f'Wolfrom mesh {index}: usable and nominal involute contact ratios must both be at least 1.')
        pair['torque_factor'] = None
    a, c, rb, t = envelope['center_distance_mm'], v['assembly_clearance'], v['bore']/2, v['plate']
    carrier, pin, hub = (envelope[k] for k in ('carrier_radius_mm','pin_radius_mm','hub_radius_mm'))
    if carrier+c >= min(plan['ring_tip_radius_mm'] for plan in plans):
        raise ValueError('Wolfrom carrier/pin envelope must clear both ring tip circles, leaving access to the annular output.')
    colors = {'input':(.96,.66,.33), 'output':(.23,.75,.65), 'fixed':(.5,.55,.63), 'internal':(.69,.59,.86), 'carrier':(.65,.72,.8)}
    def add(p, member, role, group, **metadata):
        p.port = dict(member=member, role=role, rigid_group=group,
                      label={'sun':'Sun input', 'ring':'Fixed first ring', 'output':'Output ring',
                             'planet':'Compound planet', 'carrier':'Common carrier'}[member], **metadata)
        p.profile_metadata.setdefault('wolfrom', {}).update(member=member, rigid_group=group)
        p.color = colors['carrier' if member=='carrier' else role]
        d.parts.append(p)
        return p
    def gear(name, teeth, module, width, z, member, role, group, body_phase=0, center=(0,0), plan=None, **metadata):
        p = gear_part(name,teeth,module,pa,b,width,v['bore'],center,body_phase,
                      internal=plan is not None,rim=v['rim'],zoff=z,
                      ha=plan['ring_addendum_coefficient'] if plan else 1,
                      minimum_join_radius_mm=plan['minimum_join_radius_mm'] if plan else None)
        p.profile_metadata['wolfrom'] = dict(rigid_group=group, body_phase_rad=body_phase,
                                            common_clocking_rad=phase['common_clocking_rad'], **metadata)
        if plan:
            p.profile_metadata['tooth_profile']['construction_version'] = plan['construction_version']
            if abs(p.profile_metadata['tooth_profile']['involute_end_radius_mm']-plan['ring_join_radius_mm']) > 1e-8:
                raise ValueError('Wolfrom paired ring contour and plan disagree.')
            p.profile_metadata['wolfrom']['internal_pair_construction'] = plan
        return add(p,member,role,group,**metadata)
    gear('Sun_input',s,m1,w1,0,'sun','input','wolfrom_sun')
    gear('Ring_fixed',rf,m1,w1,0,'ring','fixed','wolfrom_fixed',phase['fixed_ring_phase_rad'],plan=plans[0],layer=1)
    gear('Ring_output',ro,m2,w2,z2,'output','output','wolfrom_output',phase['output_ring_phase_rad'],plan=plans[1],layer=2)
    centers = []
    for item in phase['compounds']:
        j = item['index']; center = polar(a,item['theta_rad']); centers.append(center)
        group = f'wolfrom_compound_{j}'
        for name, teeth, module, width, z, angle, layer in (
            (f'Compound_{j}_rim1',p1,m1,w1,0,item['planet_phase_rad'],1),
            (f'Compound_{j}_rim2',p2,m2,w2,z2,item['planet2_phase_rad'],2)):
            gear(name,teeth,module,width,z,'planet','internal',group,angle,center,
                 compound=j,layer=layer)
        p = Part(f'Compound_{j}_hub',circle(hub),[circle(rb)],v['layer_gap'],w1,center,role='gear')
        p.profile_metadata['wolfrom'] = dict(rigid_group=group, body_phase_rad=item['planet_phase_rad'],
                                            common_clocking_rad=phase['common_clocking_rad'], compound=j)
        add(p,'planet','internal',group,compound=j)
    # Axial insertion: two carrier plates outside all teeth, joined by their pins.
    # Pin clearance is explicit inside each compound bore; the hub touches its
    # two gear faces. The input shaft touches the sun bore. Keys/fits are external.
    pinholes = [circle(pin,center=xy) for xy in centers]
    for name,z in (('Carrier_lower',-c-t),('Carrier_upper',top+c)):
        add(Part(name,circle(carrier),[circle(rb+c)]+pinholes,t,z,role='support'),
            'carrier','internal','wolfrom_carrier')
    for j,center in enumerate(centers,1):
        add(Part(f'Carrier_pin_{j}',circle(pin),[],top+2*c+2*t,-c-t,center,role='support'),
            'carrier','internal','wolfrom_carrier')
    add(Part('Shaft_input',circle(rb),[],w1+c+t+4,-c-t-4,role='gear'),
        'sun','input','wolfrom_sun')
    # Check actual generated root envelopes as well as theoretical radii.
    for p in d.parts:
        if 'tooth_profile' in p.profile_metadata and not p.internal and rb >= min(hypot(x,y) for x,y in p.outer)-.25:
            raise ValueError('Wolfrom bore intersects a generated external root envelope.')
    d.analysis.update(signed_ratio=envelope['signed_ratio'], meshes=meshes,
        wolfrom=dict(topology='two_rim_spur', **envelope, assembly=phase,
                     internal_pair_plans=plans, layer_intervals_mm=[[0,w1],[z2,top]],
                     hub_interval_mm=[w1,z2], carrier_intervals_mm=[[-c-t,-c],[top+c,top+c+t]],
                     radial_envelope_basis='addendum circles, actual paired ring tips, bore/root bounds; axially disjoint layers and supports'))
    d.metrics = [f"Two-rim spur Wolfrom · reduction {envelope['signed_ratio']:+.6g}:1",
        f'Z sun / first planet / fixed ring: {s}/{p1}/{rf} · second planet / output ring: {p2}/{ro}',
        f"Derived second module {m2:.9g} mm · common centre distance {a:.6g} mm · {v['planets']} identical compounds",
        'Accessible output annulus; first ring fixed; open carrier with nominal pins']
    d.notes.extend([
        'Two-rim, zero-shift spur Wolfrom: sun input, first ring fixed, second ring output. Both planet rims and their connecting hub are rigidly associated with one common compound clocking. No independent rim clocking or CAD motion joints.',
        'Both paired internal profiles require clear bounded neutral-backlash transverse polygon certificates; usable and nominal contact ratios are at least 1 for all three meshes. Certificates exclude analytic chord error, loaded contact, exported interpolation, cutter envelopes and manufacturing checks.',
        'Open nominal assembly: separated toothed layers, face-touching compound hubs, common carrier plates/pins and a sun shaft. Output is the exposed second annulus. Ring fixing, output mounting, bearings, keys, retention, drive hardware and fits must be designed externally; no housing is generated.',
        'Compound pin bores include radial assembly clearance. Gear hubs and the sun shaft use nominal touching interfaces; these do not establish torque transmission or bearing capacity.',
        'No forces per planet are inferred: elastic load sharing and circulating power losses are not solved. Overall efficiency is a user assumption, not a Wolfrom efficiency prediction. No physical reversibility, self-locking, strength, life or conformity claim is made.',
    ])
