# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Nominal axial interfaces linked to the selected kinematic members.
Dimensions describe geometry, not load-rated joints or bearings.
"""
from math import hypot, pi, cos, sin
from geometry import Part, circle
from special_drives import round_loop
from solid_geometry import point
COLORS = {'input': (0.96, 0.66, 0.33), 'output': (0.23, 0.75, 0.65), 'fixed': (0.5, 0.55, 0.63)}

def radius(loop):
    return max((hypot(x, y) for x, y in loop))

def bore(p):
    return radius(p.holes[0]) if p.holes else 0

def explicit(p):
    if not (p.stations or p.mesh or p.double or p.twist):
        p.stations = [dict(z=q, outer=p.outer, holes=p.holes) for q in (0, p.width)]
    return p

def profile(p, outer=None, holes=None):
    if outer is not None:
        p.outer = outer
    if holes is not None:
        p.holes = holes
    if p.stations:
        for s in p.stations:
            if outer is not None:
                s['outer'] = outer
            if holes is not None:
                s['holes'] = holes

def part(d, name, ro, ri, z0, z1, port, center=(0, 0), frame=(), holes=()):
    if ro <= ri + 0.1 or z1 <= z0 + 1e-06:
        raise ValueError('Axial interface has no material: ' + name)
    p = Part(name, round_loop(ro), ([round_loop(ri)] if ri else []) + list(holes), z1 - z0, z0, center, role='support', frame=frame, port=dict(port), color=COLORS[port['role']])
    explicit(p)
    d.parts.append(p)
    return p

def interface(d, name, anchor, contact, plane, ro, ri, port, *, center=(0, 0), frame=(), flange=True):
    """Neck touches its parent at contact; the flange lies beyond plane."""
    t = d.values.get('plate', 3)
    direction = 1 if plane > contact else -1
    neck = part(d, name + '_Hub', ro, ri, min(contact, plane), max(contact, plane), port, center, frame)
    pieces = [neck.name]
    cap = None
    holes = []
    cap_outer = ro
    if flange:
        cap_outer = ro + max(2, t)
        rbolt = (ro + cap_outer) / 2
        rb = min(1.2, (cap_outer - ro) / 4)
        count = 4 if port['role'] == 'input' else 6 if port['role'] == 'output' else 8
        holes = [circle(rb, 24, (rbolt * cos(2 * pi * j / count), rbolt * sin(2 * pi * j / count))) for j in range(count)]
        cap = part(d, name + '_Flange', cap_outer, ri, plane if direction > 0 else plane - t, plane + t if direction > 0 else plane, port, center, frame, holes)
        pieces.append(cap.name)
    center_world = point(neck, (0, 0), plane - neck.z, 0)
    axis = frame[3] if frame else (0, 0, 1)
    d.analysis.setdefault('mount_interfaces', []).append(dict(member=port['member'], role=port['role'], stage=port.get('stage', 1), anchor=anchor, parts=pieces, contact_z_mm=contact, terminal_z_mm=plane, direction=direction, center_mm=center_world, axis=axis, neck_outer_radius_mm=ro, neck_inner_radius_mm=ri, flange_outer_radius_mm=cap_outer, flange_thickness_mm=t if flange else 0, bolt_count=len(holes), status='nominal; fasteners, fits and load checks required'))
    return (neck, cap)

def port(q, member, stage=1):
    role = 'input' if member == q['input'] else 'output' if member == q['output'] else 'fixed'
    return dict(member=member, role=role, stage=stage, rpm=q['rates_rpm'][member])

def finish(d):
    if not d.analysis.get('mount_interfaces'):
        return
    d.analysis['mounting_status'] = 'nominal_role_adapted'
    d.notes.append('Geometry adapted to the selected members: hubs connect to the indicated surfaces, with distinct flanges for input (4 holes), output (6) and fixed attachment (8). Holes are nominal, with no fastener code assigned. Teeth and kinematic relations retain their family definitions.')
    d.requirements.append('Nominal axial interfaces: define fits, keys/splines or clamps, bolts, bearings, retainers and frame. Face contact is neither a CAD constraint nor a torque transmission check. Check clearances and motion envelope before construction.')

def planetary(d, record):
    v = d.values
    t = v['plate']
    g = v['assembly_clearance']
    ext = v['shaft_extension']
    b = v['bore'] / 2
    d.parts = [p for p in d.parts if not any((k in p.name for k in ('TieRod_ring', 'Retainer_ring', 'Coupling_interstage', 'Shaft_input', 'Shaft_output', 'Cover_', 'Bearing_input', 'Bearing_output', 'Bearing_planetcarrier')))]
    stages = []
    for i, q in enumerate(record['stage_results'], 1):
        prefix = f'S{i}_'
        sun = next((p for p in d.parts if p.name == prefix + 'Sun'))
        ring = next((p for p in d.parts if p.name == prefix + 'Ring'))
        low = next((p for p in d.parts if p.name == prefix + 'PlanetCarrier_lower'))
        high = next((p for p in d.parts if p.name == prefix + 'Flange_output'))
        ring.holes = ring.holes[:1]
        for carrier in (low, high):
            carrier.holes[0] = round_loop(max(bore(carrier), b + g))
            explicit(carrier)
        ri = max(radius(ring.holes[0]) + 0.02, b + 0.5)
        ro = radius(ring.outer)
        stages.append(dict(q=q, sun=sun, ring=ring, low=low, high=high, ring_r=(ro, ri)))
    allbottom = min((s['low'].z for s in stages))
    alltop = max((s['high'].z + s['high'].width for s in stages))

    def add(s, i, member, direction, plane, flange=True):
        if member == 'sun':
            anchor = s['sun']
            contact = anchor.z + anchor.width / 2
            ro, ri = (b, 0)
        elif member == 'carrier':
            anchor = s['high' if direction > 0 else 'low']
            contact = anchor.z + anchor.width if direction > 0 else anchor.z
            ri = max(bore(anchor), b + g)
            ro = ri + max(2, t)
        else:
            anchor = s['ring']
            contact = anchor.z + anchor.width if direction > 0 else anchor.z
            ro, ri = s['ring_r']
        return interface(d, f'S{i}_Attachment_{member}', anchor.name, contact, plane, ro, ri, port(s['q'], member, i), flange=flange)
    two = len(stages) == 2
    for i, s in enumerate(stages, 1):
        for member in ('ring', 'carrier', 'sun'):
            q = s['q']
            linked = two and (i == 1 and member == q['output'] or (i == 2 and member == q['input']))
            if linked:
                continue
            direction = (-1 if i == 1 else 1) if two else 1 if member == q['output'] else -1
            stagger = {'ring': 0, 'carrier': 1, 'sun': 2}[member] * (t + g + 1)
            plane = alltop + ext + stagger if direction > 0 else allbottom - ext - stagger
            add(s, i, member, direction, plane)
    if two:
        a, b2 = stages
        gap0 = a['high'].z + a['high'].width
        gap1 = b2['low'].z
        if gap1 - gap0 < t + 2 * g:
            raise ValueError('Insufficient stage spacing for the selected coupling.')
        mid = (gap0 + gap1) / 2
        z0 = mid - t / 2
        z1 = mid + t / 2
        neck1, _ = add(a, 1, a['q']['output'], 1, z0, False)
        neck2, _ = add(b2, 2, b2['q']['input'], -1, z1, False)
        ro = max(radius(neck1.outer), radius(neck2.outer))
        ri = min(bore(neck1), bore(neck2))
        p = part(d, 'S1_Coupling_members_selezionati', ro, ri, z0, z1, port(a['q'], a['q']['output'], 1))
        p.port['coupled_to'] = 'S2:' + b2['q']['input']
        d.analysis['interstage_mounting'] = dict(from_member=a['q']['output'], to_member=b2['q']['input'], bridge=p.name, z_mm=[z0, z1], rpm=a['q']['rates_rpm'][a['q']['output']])
    for p in d.parts:
        explicit(p)
    for i, s in enumerate(stages, 1):
        if s['q']['output'] != 'carrier':
            old = s['high'].name
            s['high'].name = f'S{i}_Flange_planetcarrier'
            for a in d.analysis.get('mount_interfaces', []):
                if a['anchor'] == old:
                    a['anchor'] = s['high'].name
    d.notes = [n for n in d.notes if not n.startswith('Eliche:')]
    finish(d)

def coaxial(d, record):
    """Alternative three-member layouts, with family-specific clear routes."""
    f = d.family
    v = d.values
    q = record['stage_results'][0]
    t = v.get('plate', v.get('diaphragm', 3))
    g = v.get('assembly_clearance', v.get('axial_gap', v.get('clearance', 0.3)))
    ext = v.get('shaft_extension', 8)

    def add(member, anchor, contact, plane, ro, ri=0):
        return interface(d, 'Attachment_' + member, anchor.name, contact, plane, ro, ri, port(q, member))
    if f == 'cycloidal':
        if v.get('eccentric_design') == 'fdm_bolted':
            from printed_shaft import mount_housing_output
            mount_housing_output(d, record)
            return
        old = {p.name: p for p in d.parts}
        shaft = old['Shaft_input']
        out = old['Shaft_output']
        body = old['Housing_tubular']
        flange = old['Flange_output']
        d.parts = [p for p in d.parts if p.name not in ('Shaft_input', 'Shaft_output', 'Cover_input', 'Cover_output', 'Bearing_input_envelope')]
        lower = body.z - t - g
        upper = max(body.z + body.width, flange.z + flange.width) + t + g
        anchor = next((p for p in d.parts if p.name == 'Eccentric_1'))
        add('eccentric', anchor, anchor.z + anchor.width / 2, lower - ext - 2 * (t + g), radius(shaft.outer), 0)
        add('output', flange, flange.z + flange.width / 2, upper + ext + t + g, radius(out.outer), 0)
        add('ring', body, body.z + body.width, upper + ext, radius(body.outer), bore(body) + 0.02)
        d.notes.append('With a moving ring, the housing and roller seats belong to the same member. Previous fixed covers crossed by interfaces are removed; the new mounting ring follows the ring role. Discs retain rotation and orbit; they are not hubs rigidly fixed to the flange.')
    elif f == 'harmonic':
        flex, ring, bearing, cam = d.parts[:4]
        upper = max((p.z + p.width for p in d.parts))
        bottom = flex.z
        inner = radius(flex.stations[0]['holes'][0])
        outer = min((hypot(*x) for x in flex.stations[0]['outer']))
        if outer - inner < 1:
            raise ValueError('Flexspline flange too small for the selected interface.')
        ro = min(outer, inner + max(2, t))
        add('flex', flex, bottom, bottom - ext, ro, inner)
        wave_radius = bore(cam) if cam.holes else min((hypot(*p) for p in cam.outer)) * 0.25
        wave_contact = cam.z + cam.width / 2 if cam.holes else cam.z + cam.width
        add('wave', cam, wave_contact, upper + ext + t + g, wave_radius, 0)
        add('circular', ring, ring.z + ring.width, upper + ext, radius(ring.outer), radius(ring.holes[0]) + 0.02)
    for p in d.parts:
        explicit(p)
    finish(d)

def pairs(d):
    """Reverse input/output adapters on the existing physical shaft axes."""
    f = d.family
    v = d.values
    t = v.get('plate', 3)
    ext = 8

    def fit(member, p, direction, ro=None, ri=0, shaft=False):
        port_data = dict(p.port)
        port_data['member'] = member
        contact = p.z + (p.width if direction > 0 else 0) if shaft or ri else p.z + p.width / 2
        plane = contact + direction * ext
        center = p.center
        frame = p.frame
        if p.axis_x:
            frame = ((-p.width / 2 + p.z, 0, p.z), (0, 0, -1), (0, 1, 0), (1, 0, 0))
            contact = p.width / 2 if not shaft else p.width if direction > 0 else 0
            plane = contact + direction * (p.width / 2 + ext if not shaft else ext)
            center = (0, 0)
        if ro is None:
            ro = radius(p.outer) if shaft else bore(p)
        if not shaft and (not ri) and (not p.holes):
            ro = max(1, min((hypot(*q) for q in p.outer)) * 0.2)
            contact = p.z + (p.width if direction > 0 else 0)
            plane = contact + direction * ext
            if p.axis_x:
                contact = p.width if direction > 0 else 0
                plane = contact + direction * ext
        if ro <= ri + 0.2:
            d.requirements.append(f'Attachment {member}: component has no usable bore / wall; define an external connection.')
            return
        interface(d, 'Interface_' + member, p.name, contact, plane, ro, ri, port_data, center=center, frame=frame)
    if f in ('parallel',):
        a = next((p for p in d.parts if p.name == 'Shaft_input'), None)
        b = next((p for p in d.parts if p.name == 'Shaft_output'), None)
        fit('A', a or next((p for p in d.parts if p.name == 'S1_Pinion')), -1, shaft=a is not None)
        fit('B', b or next((p for p in d.parts if p.name == ('S1_Wheel' if f == 'parallel' else 'S2_Wheel'))), 1, shaft=b is not None)
    elif f == 'internal':
        a = next((p for p in d.parts if p.name == 'Shaft_input'), None)
        b = next((p for p in d.parts if p.name == 'Ring_output'))
        fit('A', a or next((p for p in d.parts if p.name == 'Pinion_input')), -1, shaft=a is not None)
        fit('B', b, 1, radius(b.outer), radius(b.holes[0]) + 0.02)
    elif f == 'worm':
        a = next((p for p in d.parts if p.name.startswith('Screw_')))
        b = next((p for p in d.parts if p.name.startswith('Wheel_')))
        fit('A', a, -1)
        fit('B', b, 1)
    renamed = {}
    for p in d.parts:
        old = p.name
        if p.name == 'Shaft_input':
            p.name = 'Shaft_lato_A'
        elif p.name == 'Shaft_output':
            p.name = 'Shaft_lato_B'
        renamed[old] = p.name
    for q in d.analysis.get('mount_interfaces', []):
        q['anchor'] = renamed.get(q['anchor'], q['anchor'])
    finish(d)
