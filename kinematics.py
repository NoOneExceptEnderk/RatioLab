"""Porti cinematici separati dalle varianti costruttive. Vedi MODELLI-IO.md."""
from itertools import permutations
TRIPLES = {'planetary': {'sun': 'Sun', 'carrier': 'Planet carrier', 'ring': 'Ring'}, 'cycloidal': {'eccentric': 'Eccentric', 'output': 'Pin flange', 'ring': 'Ring / housing'}, 'harmonic': {'wave': 'Wave generator', 'flex': 'Flexspline', 'circular': 'Circular spline'}}
PAIRS = {'parallel': ('Pinion', 'Wheel'), 'internal': ('Pinion', 'Ring'), 'worm': ('Worm', 'Wheel')}
DEFAULT = {'planetary': 'sun_carrier_ring', 'cycloidal': 'eccentric_output_ring', 'harmonic': 'wave_flex_circular'}

def options(family):
    if family in TRIPLES:
        names = TRIPLES[family]
        result = {}
        default = DEFAULT[family]
        orders = [tuple(default.split('_'))] + [p for p in permutations(names) if '_'.join(p) != default]
        for a, b, c in orders:
            result['_'.join((a, b, c))] = f'{names[a]} → {names[b]} · {names[c]} fixed'
        return result
    if family in PAIRS:
        a, b = PAIRS[family]
        return {'forward': f'{a} → {b}', 'reverse': f'{b} → {a}'}
    return {}

def default(family):
    return next(iter(options(family)), None)

def prepare(family, supplied):
    v = dict(supplied)
    opts = options(family)
    if family == 'harmonic' and v.get('harmonic_output', 'flex') not in ('flex', 'circular'):
        raise ValueError('Unknown strain wave output configuration.')
    if not opts:
        if 'io_scheme' in v:
            raise ValueError('This component has no selectable inputs/outputs.')
        return v
    scheme = v.get('io_scheme')
    if scheme is None:
        scheme = 'wave_circular_flex' if family == 'harmonic' and v.get('harmonic_output') == 'circular' else default(family)
    if scheme not in opts:
        raise ValueError('Input/output arrangement unavailable for this family.')
    v['io_scheme'] = scheme
    if family == 'planetary' and (scheme != default(family) or (v.get('variant') in ('two_stage', 'two_stage_double') and v.get('io_scheme2', default(family)) != default(family))):
        if v.get('bearing_mode', 'manual') != 'manual' or v.get('hardware_mode', 'none') != 'none':
            raise ValueError('Alternative planetary arrangement: use manual dimensions and disable hardware; automatic seats are defined only for sun input / carrier output.')
    if family == 'cycloidal' and scheme != default(family) and (v.get('bearing_mode', 'manual') != 'manual' or v.get('hardware_mode', 'none') != 'none'):
        raise ValueError('Alternative cycloidal arrangement: use manual dimensions and disable hardware; automatic seats apply to a fixed ring.')
    if family == 'harmonic':
        v['harmonic_output'] = 'circular' if scheme.split('_')[1] == 'circular' else 'flex'
    return v

def coefficients(family, v, stage=1):
    if family == 'planetary':
        zs = v['sun' if stage == 1 else 'sun2']
        zp = v['planet' if stage == 1 else 'planet2']
        zr = zs + 2 * zp
        return {'sun': zs, 'carrier': -zs - zr, 'ring': zr}
    if family == 'cycloidal':
        return {'eccentric': 1, 'output': v['pins'] - 1, 'ring': -v['pins']}
    if family == 'harmonic':
        return {'wave': 2, 'flex': v['teeth'], 'circular': -v['teeth'] - 2}
    raise ValueError('Three member equation unavailable.')

def solve(a, scheme, rpm):
    source, target, fixed = scheme.split('_')
    ratio = -a[target] / a[source]
    rates = {source: rpm, target: rpm / ratio, fixed: 0.0}
    return dict(input=source, output=target, fixed=fixed, signed_ratio=ratio, rates_rpm=rates, coefficients=a)

def apply(d):
    f = d.family
    v = d.values
    opts = options(f)
    if not opts:
        return
    scheme = v['io_scheme']
    label = opts[scheme]
    record = {'scheme': scheme, 'label': label, 'stage_results': []}
    original = d.analysis.get('signed_ratio')
    if f in TRIPLES:
        n = 2 if f == 'planetary' and v['variant'] in ('two_stage', 'two_stage_double') else 1
        speed = v['input_rpm']
        ratio = 1.0
        for stage in range(1, n + 1):
            key = 'io_scheme2' if stage == 2 else 'io_scheme'
            choice = v[key]
            q = solve(coefficients(f, v, stage), choice, speed)
            record['stage_results'].append(q)
            ratio *= q['signed_ratio']
            speed = q['rates_rpm'][q['output']]
        d.analysis['signed_ratio'] = ratio
        if n == 2:
            label += ' | S2: ' + opts[v['io_scheme2']]
            record['label'] = label
        if scheme != default(f) or (n == 2 and v['io_scheme2'] != default(f)):
            d.notes = [x for x in d.notes if not x.startswith(('Fixed ring;', 'Wave generator input;'))]
            if f == 'planetary':
                reconfigure_planetary(d, record)
            if f == 'cycloidal':
                d.requirements.append('The ring/housing and pin flange have nominal interfaces for the current arrangement; size supports, seals and fasteners for the selected member.')
        if f != 'planetary' and scheme != default(f):
            from mounting import coaxial
            coaxial(d, record)
        tag_members(d, record)
        if f == 'cycloidal' and scheme != default(f):
            renamed = {}
            for p in d.parts:
                old = p.name
                p.name = p.name.replace('Shaft_input', 'Shaft_eccentric').replace('Shaft_output', 'Shaft_pincarrier').replace('Flange_output', 'Flange_pincarrier')
                renamed[old] = p.name
            for q in d.analysis.get('mount_interfaces', []):
                q['anchor'] = renamed.get(q['anchor'], q['anchor'])
                q['parts'] = [renamed.get(name, name) for name in q['parts']]
        if f == 'harmonic' and scheme not in ('wave_flex_circular', 'wave_circular_flex'):
            d.analysis.pop('harmonic_output', None)
    elif f in PAIRS and original is not None:
        if scheme == 'reverse':
            d.analysis['signed_ratio'] = 1 / original
            for mesh in d.analysis.get('meshes', []):
                mesh['torque_factor'] = None
                mesh.pop('forces', None)
            d.analysis.pop('forces', None)
            d.requirements.append('Input and output swapped: review connections, supports and loads for the new driving member. Forces from the previous input are not reused.')
        a_speed = v['input_rpm'] if scheme == 'forward' else v['input_rpm'] / d.analysis['signed_ratio']
        b_speed = v['input_rpm'] / d.analysis['signed_ratio'] if scheme == 'forward' else v['input_rpm']
        for p in d.parts:
            name = p.name
            member = ''
            if f == 'parallel':
                member = p.port.get('member','') if p.port.get('member') in ('A','B') else 'A' if any((k in name for k in ('Pinion', 'Shaft_input'))) else 'B' if any((k in name for k in ('Wheel', 'Shaft_output'))) else ''
            if f == 'internal':
                member = p.port.get('member','') if p.port.get('member') in ('A','B') else 'A' if 'input' in name else 'B' if 'Ring' in name else ''
            if f == 'worm':
                member = 'A' if name.startswith('Screw_') else 'B' if name.startswith('Wheel_') else ''
            if member:
                driving = (member == 'A') == (scheme == 'forward')
                p.port = dict(member=member, role='input' if driving else 'output', rpm=a_speed if member == 'A' else b_speed)
        if f == 'worm' and scheme == 'reverse':
            d.notes.append('Wheel driven: ideal kinematic relation only; backdrivability depends on helix angle, friction, lubrication and load. The generator does not guarantee the worm can be backdriven.')
    if scheme != default(f):
        from mounting import pairs
        if f in PAIRS and f not in TRIPLES:
            pairs(d)
        for p in d.parts:
            if not (p.stations or p.mesh or p.double or p.twist):
                p.stations = [dict(z=q, outer=p.outer, holes=p.holes) for q in (0, p.width)]
    d.analysis['kinematics'] = record
    if d.analysis.get('signed_ratio') is not None and abs(d.analysis['signed_ratio']) < 1:
        d.notes.append('The selected arrangement increases speed: |i|<1. Nominal torque is reduced using the assumed efficiency.')
    if original is not None and d.analysis.get('signed_ratio') != original:
        d.metrics = [x for x in d.metrics if not any((t in x.lower() for t in ('reduction', 'ratio')))]
    if d.analysis.get('signed_ratio') is not None:
        d.metrics.append(f"Input/output ratio {d.analysis['signed_ratio']:+.6g}:1")
    d.metrics.append('Inputs / outputs: ' + label)
    d.notes.append('The kinematic arrangement is independent of the construction variant. Roles are saved in metadata and the BOM; no CAD motion constraints are created. Reverse configurations are kinematic relations, not a guarantee of backdrivability.')

def reconfigure_planetary(d, record):
    from mounting import planetary
    planetary(d, record)

def tag_members(d, record):
    f = d.family
    for p in d.parts:
        name = p.name.lower()
        if 'bearing' in name:
            continue
        stage = 2 if name.startswith('s2_') else 1
        q = record['stage_results'][min(stage, len(record['stage_results'])) - 1]
        member = ''
        if f == 'planetary':
            if 'sun' in name:
                member = 'sun'
            elif 'ring' in name and 'housing' not in name:
                member = 'ring'
            elif any((x in name for x in ('planetcarrier', 'flange_output', 'pin_planet'))):
                member = 'carrier'
        if f == 'cycloidal':
            if name.startswith('disc_cycloidal'):
                p.port = dict(stage=stage, member='disc', role='internal', rpm=q['rates_rpm']['output'], orbital_rpm=q['rates_rpm']['eccentric'])
                p.color = (0.69, 0.59, 0.86)
                continue
            if any((x in name for x in ('eccentric', 'shaft_input'))):
                member = 'eccentric'
            elif any((x in name for x in ('disc_cycloidal', 'pin_output', 'flange_output', 'shaft_output'))):
                member = 'output'
            elif any((x in name for x in ('roller_ring', 'housing', 'cover', 'seat_support'))):
                member = 'ring'
        if f == 'harmonic':
            member = 'flex' if 'flexspline' in name else 'circular' if 'circular_spline' in name else 'wave' if 'generator' in name else ''
        if p.port and p.name.startswith(('Attachment_', 'S1_Attachment_', 'S2_Attachment_', 'S1_Coupling_members')):
            continue
        if member:
            role = 'input' if member == q['input'] else 'output' if member == q['output'] else 'fixed'
            p.port = dict(stage=stage, member=member, role=role, rpm=q['rates_rpm'][member])
            if not (f == 'cycloidal' and d.values.get('eccentric_design') == 'fdm_bolted' and p.procurement):
                p.color = {'input': (0.96, 0.66, 0.33), 'output': (0.23, 0.75, 0.65), 'fixed': (0.5, 0.55, 0.63)}[role]
