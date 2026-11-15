# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Optional through-bore interfaces for externally supplied shafts."""
from math import hypot, radians

from geometry import Part, circle_info, transformed
from hardware_catalog import KEYS, KEY_LENGTHS, KEY_SOURCE, KEY_PRODUCT
from parameter_errors import ParameterError

PROFILES = {'standard': 'Standard connection', 'd_shaft': 'D-shaped bore · external shaft',
            'keyed_shaft': 'Keyed bore · external shaft'}
PORT_LABELS = {'input': 'Input shaft connection', 'output': 'Output shaft connection',
               'side_a': 'Side A shaft connection', 'side_b': 'Side B shaft connection'}
FAMILIES = {'planetary', 'parallel', 'internal', 'worm', 'harmonic', 'wolfrom',
            'bevel', 'face', 'hypoid', 'differential'}


def ports(family):
    if family == 'differential':
        return ('side_a', 'side_b', 'output')
    return ('input', 'output') if family in FAMILIES else ()


def profile_key(port):
    return port + '_shaft_profile'


def fields(family):
    return [
        (port + '_connection_' + key, label, default, low, high, step)
        for port in ports(family)
        for key, label, default, low, high, step in (
            ('flat', 'D-shaft flat depth [mm]', .5, .05, 50, .05),
            ('allowance', 'Shaft bore diametral allowance [mm]', 0, 0, .5, .01),
            ('clocking', 'Shaft connection clocking [°]', 0, -180, 180, 1))
    ]


def field_active(key, values):
    port, dimension = key.split('_connection_', 1)
    profile = values.get(profile_key(port), 'standard')
    return profile == 'd_shaft' or (profile == 'keyed_shaft' and dimension != 'flat')


def field_port(key):
    port, separator, _ = key.partition('_connection_')
    return port if separator and port in PORT_LABELS else None


def options(family, supplied):
    result = {}
    for port in ports(family):
        key = profile_key(port)
        if key not in supplied:
            continue
        profile = supplied[key]
        if not isinstance(profile, str) or profile not in PROFILES:
            raise ParameterError('shaft.profile', (key,), 'Unknown shaft connection profile.')
        result[key] = profile
    return result


def targets(family, values):
    """Resolve external roles to the actual bored solids, never to an internal ring."""
    from kinematics import default
    scheme = values.get('io_scheme', default(family))
    if family == 'planetary':
        two = values.get('variant') in ('two_stage', 'two_stage_double')
        last = 2 if two else 1
        first_roles = scheme.split('_')
        last_roles = values.get('io_scheme2', scheme).split('_') if two else first_roles
        result = {}
        standard = scheme == default(family) and last_roles == first_roles
        if first_roles[0] == 'sun':
            result['input'] = ('S1_Sun', ('Shaft_input', 'S1_Attachment_sun_Hub', 'S1_Attachment_sun_Flange'))
        elif first_roles[:2] == ['carrier', 'sun']:
            result['input'] = ('S1_Attachment_carrier_Flange', ())
        if last_roles[1] == 'sun':
            result['output'] = (f'S{last}_Sun', (f'S{last}_Attachment_sun_Hub', f'S{last}_Attachment_sun_Flange'))
        elif last_roles[1] == 'carrier':
            if standard:
                result['output'] = (f'S{last}_Flange_output', (f'S{last}_Shaft_output',))
            elif (two and last_roles[0] == 'sun') or (not two and last_roles[2] == 'sun'):
                result['output'] = (f'S{last}_Attachment_carrier_Flange', ())
        return result
    if family == 'wolfrom':
        return {'input': ('Sun_input', ('Shaft_input',))}
    if family == 'harmonic':
        roles = scheme.split('_')
        return {port: ('Generator_wave_prescribed', ('Attachment_wave_Hub', 'Attachment_wave_Flange'))
                for port, member in zip(('input', 'output'), roles) if member == 'wave'}
    if family == 'differential':
        classic = values.get('configuration') == 'classic'
        label = 'output' if classic else 'input'
        side = 'side' if classic else 'input'
        result = {f'side_{tag.lower()}': (f'Bevel_{side}_{tag}', (f'Shaft_{label}_{tag}',)) for tag in ('A', 'B')}
        if not classic:
            result['output'] = ('Bevel_output', ('Shaft_output',))
        if values.get('output_interface') == 'hollow':
            for port in (result if classic else ('output',)):
                result[port] = (result[port][1][0], ())
        return result
    pair = {
        'parallel': (('S1_Pinion', ('Shaft_input', 'Shaft_lato_A', 'Interface_A_Hub', 'Interface_A_Flange')),
                     ('S1_Wheel', ('Shaft_output', 'Shaft_lato_B', 'Interface_B_Hub', 'Interface_B_Flange'))),
        'internal': (('Pinion_input', ('Shaft_input', 'Shaft_lato_A', 'Interface_A_Hub', 'Interface_A_Flange')), None),
        'worm': (('Screw_', ()), ('Wheel_generated', ())),
        'bevel': (('Bevel_pinion', ()), ('Bevel_wheel', ())),
        'face': (('Face_pinion', ()), ('Face_wheel', ())),
        'hypoid': (('Hypoid_pinion', ()), ('Hypoid_wheel', ())),
    }.get(family, ())
    if family == 'parallel':
        from parallel_multistage import count, VARIANTS
        if values.get('variant') in VARIANTS:
            stages = count(values)
            pair = (('S1_Pinion', ('Shaft_1',)), (f'S{stages}_Wheel', (f'Shaft_{stages + 1}',)))
    if scheme == 'reverse':
        pair = pair[::-1]
    return {port: target for port, target in zip(('input', 'output'), pair) if target}


def _edge_radius(loop):
    result = float('inf')
    for (x, y), (u, v) in zip(loop, loop[1:] + loop[:1]):
        dx, dy = u - x, v - y
        squared = dx*dx + dy*dy
        fraction = max(0, min(1, -(x*dx + y*dy)/squared)) if squared else 0
        result = min(result, hypot(x + fraction*dx, y + fraction*dy))
    return result


def bore_profile(values, port, radius):
    from printed_shaft import _d_profile
    from hardware import shaped_circle
    key = profile_key(port)
    profile = values[key]
    prefix = port + '_connection_'
    allowance = values[prefix + 'allowance'] / 2
    clocking = values[prefix + 'clocking']
    record = dict(profile=profile, diameter_mm=2*radius,
                  diametral_allowance_mm=2*allowance, clocking_deg=clocking)
    if profile == 'd_shaft':
        depth = values[prefix + 'flat']
        if not allowance < depth < radius:
            raise ParameterError('shaft.flat', (prefix + 'flat', prefix + 'allowance'), 'D-flat depth must exceed radial clearance and be smaller than the shaft radius.')
        bore = _d_profile(radius + allowance, radius - depth + allowance)
        record['flat_depth_mm'] = depth
    else:
        nominal = round(2*radius)
        if nominal not in KEYS or abs(2*radius - nominal) > 1e-6:
            raise ParameterError('shaft.key_diameter', (key,), 'Keyed bore requires a nominal shaft diameter of 6, 8, 10 or 12 mm.', 'Set the existing shaft bore to a supported diameter.')
        width, height, shaft_depth, hub_depth = KEYS[nominal]
        if allowance >= height - shaft_depth:
            raise ParameterError('shaft.key_engagement', (prefix + 'allowance',), 'Bore clearance removes key engagement.')
        bore = shaped_circle(radius + allowance, dict(b=width, depth=hub_depth), True, True)
        record.update(key_width_mm=width, key_height_mm=height, shaft_keyway_depth_mm=shaft_depth,
                      hub_keyway_depth_mm=hub_depth, source=KEY_SOURCE)
    return transformed(bore, angle=radians(clocking)), record


def apply(design):
    values = design.values
    active = {port: values[profile_key(port)] for port in ports(design.family)
              if values.get(profile_key(port), 'standard') != 'standard'}
    if not active:
        return
    from solid_geometry import point
    available = targets(design.family, values)
    for port, profile in active.items():
        key = profile_key(port)
        if port not in available:
            raise ParameterError('shaft.unavailable', (key,), 'This member has no supported shaft bore for a shaped connection.')
        name, replaced = available[port]
        part = next((p for p in design.parts if p.name == name or (name.endswith('_') and p.name.startswith(name))), None)
        premeshed = part is not None and name == 'Face_wheel'
        if part is None or (part.mesh and not premeshed):
            raise ParameterError('shaft.bore', (key,), 'This connection requires a concentric through-bore.')
        hub_cut = any(op['type'] in ('keyway_hub', 'groove_internal') for op in part.machining)
        if hub_cut or any(p.name in replaced and p.machining for p in design.parts):
            raise ParameterError('shaft.hardware', (key, 'hardware_mode'), 'This shaft connection already has automatic machining.', 'Turn off the conflicting standard hardware for this connection.')
        sections = part.stations or [dict(outer=part.outer, holes=part.holes)]
        bores = [(0, 0, values['output_bore']/2)] if premeshed else [circle_info(s['holes'][0]) if s['holes'] else None for s in sections]
        if any(b is None or hypot(b[0], b[1]) > 1e-6 for b in bores):
            raise ParameterError('shaft.bore', (key,), 'This connection requires a concentric through-bore.')
        radius = bores[0][2]
        if any(abs(b[2] - radius) > 1e-6 for b in bores):
            raise ParameterError('shaft.bore', (key,), 'This connection requires a constant-diameter through-bore.')
        prefix = port + '_connection_'
        bore, record = bore_profile(values, port, radius)
        record.update(port=port, part=part.name, origin_mm=point(part, (0, 0), 0, 0),
                      axis=part.frame[3] if part.frame else (1, 0, 0) if part.axis_x else (0, 0, 1),
                      clocking_reference=part.frame[1] if part.frame else (0, 0, -1) if part.axis_x else (1, 0, 0))
        reach = max(hypot(x, y) for x, y in bore) + .5
        boundary = min(_edge_radius(s['outer']) for s in sections)
        if part.double and part.gap > 0:
            boundary = min(boundary, part.core_radius)
        if reach >= boundary or any(reach >= _edge_radius(hole) for s in sections for hole in s['holes'][1:]):
            raise ParameterError('shaft.wall', (key, prefix + 'allowance'), 'The shaft connection leaves less than 0.5 mm nominal wall.', 'Use a smaller bore or increase the hub dimensions.')
        if not premeshed:
            part.holes[0:1] = [bore]
            for section in part.stations:
                section['holes'] = [bore, *section['holes'][1:]]
            part.fixed_first_bore = True
        if profile == 'keyed_shaft':
            lengths = [length for length in KEY_LENGTHS if length <= part.width - 1]
            if lengths:
                length = lengths[-1]
                width, height, shaft_depth, _ = KEYS[round(2*radius)]
                floor = radius - shaft_depth
                tip = floor + height
                outline = transformed([(floor, -width/2), (tip, -width/2), (tip, width/2), (floor, width/2)], angle=radians(record['clocking_deg']))
                # An axis_x part centers its axial coordinates on width / 2.
                # Its centered key already shares that origin.
                key_part = Part(part.name + '_External_shaft_key', outline, [], length,
                    part.z + (0 if part.axis_x else (part.width - length)/2), part.center,
                    axis_x=part.axis_x, frame=part.frame, role=part.role, port=dict(part.port), color=(.94, .72, .33))
                from hardware import buy
                buy(key_part, f'DIN 6885-1 B {width:g}x{height:g}x{length:g}', 'Square ended parallel key',
                    f'{width:g} × {height:g} × {length:g} mm', 'To be selected', KEY_PRODUCT, 'DIN 6885-1 B')
                design.parts.append(key_part)
                record['key_length_mm'] = length
            else:
                design.requirements.append(f'{part.name}: select a key that engages the short hub in CAD. No catalog key fits the available length.')
        part.machining.append(dict(type=profile + '_bore', **record))
        design.parts[:] = [p for p in design.parts if p.name not in replaced]
        for attachment in design.analysis.get('mount_interfaces', []):
            if set(replaced).intersection(attachment['parts']):
                attachment.update(anchor=part.name, parts=[part.name], external_shaft=True,
                                  status='Shaped through-bore for an external shaft')
        design.analysis.setdefault('shaft_connections', []).append(record)
    design.requirements.append('Complete external shafts, axial retention and actual fits in CAD for the shaped bore connections.')
