# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Shared dimensional geometry in millimetres, with no external dependencies.

Input pressure/helix angles and stored section twist use degrees. Low-level
trigonometric helpers and profile phase use radians; convert at those boundaries.
See README.md and docs/technical/calculations.md for model limits.
"""
from dataclasses import dataclass, field
from math import sin, cos, tan, acos, atan, atan2, sqrt, pi, radians, degrees, hypot, isfinite, ceil
import uuid
TAU = 2 * pi
FAMILIES = {'spur': 'Spur gear', 'helical': 'Helical gear', 'double': 'Double helical gear', 'planetary': 'Planetary gearbox', 'cycloidal': 'Cycloidal drive', 'harmonic': 'Strain wave drive', 'worm': 'Worm drive', 'parallel': 'Parallel shaft reducer · single stage', 'internal': 'Internal gear reducer · fixed axes'}
COMMON = [('module', 'Normal module [mm]', 2.0, 0.1, 10, 0.1), ('width', 'Face width [mm]', 10, 1, 100, 1), ('bore', 'Bore diameter [mm]', 6, 0, 100, 0.5), ('pressure', 'Pressure angle [°]', 20, 14.5, 30, 0.5), ('backlash', 'Tangential backlash [mm]', 0.15, 0, 1, 0.01)]
SPECS = {'spur': COMMON + [('teeth', 'Tooth count', 24, 8, 160, 1)], 'helical': COMMON + [('teeth', 'Tooth count', 24, 8, 160, 1), ('helix', 'Helix angle [°] (sign = handedness)', 20, -45, 45, 1)], 'double': COMMON + [('teeth', 'Tooth count', 24, 8, 160, 1), ('helix', 'Helix angle [°]', 25, -45, 45, 1), ('gap', 'Central groove [mm]', 1, 0, 10, 0.1)], 'planetary': COMMON + [('sun', 'Sun teeth', 18, 8, 80, 1), ('planet', 'Planet teeth', 18, 8, 60, 1), ('planets', 'Planet count', 3, 2, 6, 1), ('rim', 'Ring thickness [mm]', 5, 1, 30, 0.5)], 'cycloidal': [('pins', 'Ring roller count', 16, 6, 60, 1), ('radius', 'Roller pitch radius [mm]', 40, 10, 150, 1), ('pin_radius', 'Roller radius [mm]', 3, 1, 10, 0.1), ('eccentric', 'Eccentricity [mm]', 1.2, 0.1, 5, 0.1), ('width', 'Disc thickness [mm]', 8, 1, 40, 1), ('bore', 'Eccentric seat diameter [mm]', 12, 2, 60, 1), ('output_count', 'Output pin count', 6, 3, 10, 1), ('output_radius', 'Output pin pitch radius [mm]', 22, 5, 100, 1), ('output_pin', 'Output pin radius [mm]', 2, 1, 10, 0.1), ('clearance', 'Radial clearance [mm]', 0.1, 0, 0.8, 0.01)], 'harmonic': COMMON + [('teeth', 'Flexspline teeth', 60, 30, 160, 2), ('wall', 'Flexible wall thickness [mm]', 1, 0.3, 4, 0.1), ('rim', 'Ring thickness [mm]', 5, 1, 30, 0.5)], 'worm': COMMON + [('teeth', 'Wheel teeth', 30, 12, 100, 1), ('starts', 'Worm starts', 1, 1, 4, 1), ('diameter', 'Worm pitch diameter [mm]', 20, 8, 80, 1), ('length', 'Worm length [mm]', 24, 5, 80, 1)]}
VARIANTS = {'double': {'joined': 'Joined helices · no groove', 'separated': 'Separate helices · with groove'}, 'worm': {'za': 'Cylindrical ZA · straight axial flanks', 'zi': 'Cylindrical ZI · transverse involute'}, 'harmonic': {'cup': 'Cup', 'flat_cup': 'Flat cup', 'hat': 'External flange · silk hat'}, 'planetary': {'spur': 'Single stage · spur', 'helical': 'Single stage · helical', 'double': 'Single stage · double helical', 'two_stage': 'Two stages in cascade', 'two_stage_double': 'Two stages · double helical'}, 'cycloidal': {'single': 'Complete single disc', 'dual': 'Dual disc · opposing eccentrics'}, 'parallel': {'spur': 'Spur teeth', 'helical': 'Helical', 'double': 'Double helix'}, 'internal': {'spur': 'Internal gear · spur', 'helical': 'Internal gear · helical', 'double': 'Internal gear · double helical'}}
DOUBLE_STYLES = {'joined': 'Joined helices · no groove', 'separated': 'Separate helices · with groove'}
HARMONIC_OUTPUTS = {'flex': 'Fixed ring → flexspline output', 'circular': 'Fixed flexspline → ring output'}
FAMILIES['differential'] = 'Bevel differential'
VARIANTS['differential'] = {'straight': 'Straight bevel', 'spiral': 'Spiral bevel'}
SPECS['differential'] = [
    ('module', 'Outer bevel module [mm]', 2, .5, 6, .1),
    ('side_teeth', 'Teeth on each input gear', 24, 16, 60, 1),
    ('output_teeth', 'Output bevel teeth', 24, 16, 60, 1),
    ('width', 'Face width along pitch cone [mm]', 8, 2, 25, .5),
    ('pressure', 'Transverse pressure angle [°]', 20, 14.5, 30, .5),
    ('backlash', 'Outer tangential backlash [mm]', .15, 0, 1, .01),
    ('input_shaft', 'Input shaft diameter [mm]', 6, 2, 24, .5),
    ('output_shaft', 'Output shaft diameter [mm]', 8, 2, 24, .5),
    ('shaft_extension', 'Input shaft extension [mm]', 12, 4, 40, 1),
    ('plate', 'Carrier / flange thickness [mm]', 4, 2, 12, .5),
    ('assembly_clearance', 'Assembly clearance [mm]', .3, .1, 1, .05),
    ('flange_radius', 'Output flange radius [mm]', 12, 6, 40, .5),
    ('bolt_count', 'Flange mounting hole count', 4, 3, 8, 1),
    ('bolt_diameter', 'Flange mounting hole diameter [mm]', 3, 1, 8, .25),
    ('output_extension', 'Output shaft extension [mm]', 12, 4, 60, 1),
    ('passage_diameter', 'Output passage diameter [mm]', 4, 1, 22, .5),
    ('carrier_bolt_diameter', 'Split carrier joining hole diameter [mm]', 3, 1, 6, .25),
    ('spiral_angle', 'Unsigned spiral angle [°]', 35, 0, 45, 1),
    ('spiral_hand', 'Input gear local spiral hand (−1 / +1)', 1, -1, 1, 2),
    ('output_difference_rpm', 'Prescribed side speed difference B−A [rpm]', 0, -200000, 200000, 1),
    ('spider_pin_diameter', 'Spider pin diameter [mm]', 6, 2, 20, .5),
    ('spider_clearance', 'Spider pin radial running clearance [mm]', .15, .05, 1, .05),
]

def is_double(family, variant=None):
    return family == 'double' or variant in ('double', 'two_stage_double')
PAIR_FIELDS = COMMON + [('pinion', 'Input pinion teeth', 20, 12, 100, 1), ('wheel', 'Driven wheel teeth', 60, 22, 200, 1), ('output_bore', 'Output bore [mm]', 8, 0, 100, 0.5)]
SPECS['parallel'] = PAIR_FIELDS
SPECS['internal'] = [(k, label, 22 if k == 'pinion' else 66 if k == 'wheel' else default, lo, hi, step) for k, label, default, lo, hi, step in PAIR_FIELDS if k != 'output_bore'] + [('rim', 'Ring thickness [mm]', 5, 2, 30, 0.5)]
ASSEMBLY_FIELDS = [('plate', 'Flange thickness [mm]', 3, 1, 30, 0.5), ('assembly_clearance', 'Axial / assembly clearance [mm]', 0.2, 0.05, 1, 0.05)]

def get_specs(family, variant=None, double_style=None):
    if family not in FAMILIES:
        raise ValueError('Unknown family')
    specs = list(SPECS[family])
    if family in VARIANTS:
        variant = variant or next(iter(VARIANTS[family]))
        if variant not in VARIANTS[family]:
            raise ValueError('Unknown variant')
        if family in ('planetary', 'cycloidal'):
            specs += ASSEMBLY_FIELDS
        if family == 'planetary':
            if variant in ('helical', 'two_stage', 'double', 'two_stage_double'):
                specs += [('helix', 'Helix angle [°] (0 = spur)', 25 if variant in ('double', 'two_stage_double') else 20 if variant == 'helical' else 0, -35, 35, 1)]
            if variant in ('double', 'two_stage_double'):
                specs += [('gap', 'Central groove [mm]', 1, 0, 10, 0.1)]
            if variant in ('two_stage', 'two_stage_double'):
                specs += [('sun2', 'Sun teeth · stage 2', 18, 8, 80, 1), ('planet2', 'Planet teeth · stage 2', 18, 8, 60, 1), ('width2', 'Width · stage 2 [mm]', 10, 2, 60, 1)]
        elif family == 'cycloidal':
            specs += [('input_shaft', 'Input shaft diameter [mm]', 4, 2, 30, 0.5), ('output_shaft', 'Output shaft diameter [mm]', 8, 3, 40, 0.5), ('housing_wall', 'Housing thickness [mm]', 4, 2, 15, 0.5)]
        elif family in ('parallel', 'internal'):
            if variant in ('helical', 'double'):
                specs += [('helix', 'Input helix angle [°]', 20, -35, 35, 1)]
            if variant == 'double':
                specs += [('gap', 'Central groove [mm]', 1, 0, 10, 0.1)]
            if family != 'internal':
                specs += [('profile_shift', 'Pinion profile shift x (wheel = −x)', 0, -0.5, 0.7, 0.05)]
            if family == 'parallel':
                specs += [('center_extra', 'Centre distance increase [mm]', 0, 0, 5, 0.05)]
    if family in ('spur', 'helical', 'double'):
        specs += [('profile_shift', 'Profile shift coefficient x', 0, -0.5, 1, 0.05), ('addendum', 'Addendum coefficient ha*', 1, 0.7, 1.25, 0.05), ('dedendum', 'Dedendum coefficient hf*', 1.25, 1.1, 1.6, 0.05)]
    if family == 'planetary':
        specs += [('housing_wall', 'Housing thickness [mm]', 3, 2, 15, 0.5), ('shaft_extension', 'Shaft extension [mm]', 8, 4, 40, 1)]
        if variant in ('two_stage', 'two_stage_double'):
            specs += [('stage_gap', 'Additional stage spacing [mm]', 0, 0, 30, 0.5)]
    if family == 'cycloidal':
        specs += [('output_clearance', 'Output pin radial clearance [mm]', 0.1, 0, 0.8, 0.01), ('profile_tolerance', 'Profile sampling tolerance [mm]', 0.01, 0.002, 0.05, 0.002)]
        if variant == 'dual':
            specs += [('disc_gap', 'Disc spacing [mm]', 0.2, 0.05, 10, 0.05)]
        from printed_shaft import FIELDS
        specs += FIELDS
    if family == 'harmonic':
        specs += [('wave_factor', 'Wave amplitude factor', 1, 0.5, 1.5, 0.05)]
    if family == 'harmonic':
        specs += [('cup_length', 'Flexible body length [mm]', 8 if variant == 'flat_cup' else 25, 4, 100, 1), ('diaphragm', 'Diaphragm / flange thickness [mm]', 2, 0.5, 10, 0.5), ('bearing_thickness', 'Wave bearing radial thickness [mm]', 2, 0.5, 8, 0.5), ('wave_clearance', 'Generator radial clearance [mm]', 0.05, 0.01, 0.5, 0.01)]
        if variant == 'hat':
            specs += [('flange_width', 'Flange radial width [mm]', 6, 2, 25, 0.5)]
        else:
            specs += [('output_bore', 'Output diaphragm bore [mm]', 8, 0.5, 100, 0.5)]
    if family == 'worm':
        specs = [(k, 'Worm axial module [mm]' if k == 'module' else 'Worm axial pressure angle [°]' if k == 'pressure' else label, d, lo, hi, st) for k, label, d, lo, hi, st in specs]
        specs += [('wheel_bore', 'Wheel bore [mm]', 6, 0, 100, 0.5), ('worm_hand', 'Worm hand (−1 left, +1 right)', 1, -1, 1, 2)]
        specs += [('journal_length', 'Length of each journal [mm]', 8, 0, 40, 1), ('journal_diameter', 'Journal diameter [mm]', 12, 2, 60, 0.5)]
    if is_double(family, variant):
        style = variant if family == 'double' else double_style
        if style == 'joined':
            specs = [s for s in specs if s[0] != 'gap']
    from engineering import LOAD_FIELDS
    if family == 'differential':
        specs += [('input_rpm', 'Input A speed [rpm]', 12, -100000, 100000, 1),
                  ('input_b_rpm', 'Input B speed [rpm]', -12, -100000, 100000, 1)]
    else:
        specs += LOAD_FIELDS[:2] if family in ('spur', 'helical', 'double') else LOAD_FIELDS
    return specs
INTEGER = {'teeth', 'sun', 'planet', 'planets', 'pins', 'output_count', 'starts', 'sun2', 'planet2', 'pinion', 'wheel', 'pinion2', 'wheel2', 'worm_hand', 'rollers', 'crown_teeth', 'segments', 'planet_teeth', 'pairs', 'friction_faces', 'crank_teeth', 'cranks', 'spring_count', 'coils', 'bolt_count', 'bevel_pinion'}
INTEGER.update(('side_teeth', 'output_teeth', 'spiral_hand'))

def defaults(family, variant=None):
    v = {s[0]: s[2] for s in get_specs(family, variant)}
    if family in VARIANTS:
        v['variant'] = variant or next(iter(VARIANTS[family]))
    if family == 'differential':
        from differential_wrist import OPTION_DEFAULTS
        v.update(OPTION_DEFAULTS)
    return v

def validate(family, supplied):
    """Resolve linked options before validating the resulting physical dimensions.

    I/O compatibility and printed-shaft preparation precede variant/style
    normalization. Bearing dimensions then feed hardware preparation, so numeric
    and geometric checks see the final bores, widths and assembly choices.
    """
    if family not in FAMILIES:
        raise ValueError('Unknown family')
    from kinematics import prepare as prepare_io, options as io_options
    supplied = prepare_io(family, supplied)
    if family == 'differential':
        from differential_wrist import prepare as prepare_wrist
        supplied = prepare_wrist(supplied)
    if family == 'cycloidal':
        from printed_shaft import prepare
        supplied = prepare(supplied)
    if family == 'double' and 'variant' not in supplied:
        supplied['variant'] = 'joined' if supplied.get('gap', 0) == 0 else 'separated'
    variant = supplied.get('variant', next(iter(VARIANTS.get(family, {'': None}))))
    double = is_double(family, variant)
    style = supplied.get('double_style', 'joined' if supplied.get('gap', 1) == 0 else 'separated') if double else None
    if family == 'double':
        style = variant
    if double:
        if style not in DOUBLE_STYLES:
            raise ValueError('Unknown double helix variant.')
        if style == 'joined':
            supplied['gap'] = 0
    if family == 'cycloidal':
        supplied.setdefault('output_clearance', supplied.get('clearance', 0.1))
        supplied.setdefault('disc_gap', supplied.get('assembly_clearance', 0.2))
    from catalog import prepare, options
    supplied = prepare(family, supplied)
    from hardware_catalog import prepare as prepare_hardware, options as hardware_options
    supplied = prepare_hardware(family, supplied)
    variant = supplied.get('variant', next(iter(VARIANTS.get(family, {'': None}))))
    values = {'variant': variant} if family in VARIANTS else {}
    if family == 'differential':
        from differential_wrist import options as wrist_options
        values.update(wrist_options(supplied))
    if family == 'cycloidal':
        values['eccentric_design'] = supplied.get('eccentric_design', 'standard')
    for key, label, default, low, high, step in get_specs(family, variant, style):
        v = supplied.get(key, default)
        if isinstance(v, bool):
            raise ValueError(f'{label}: a numeric value is required')
        v = float(v)
        if not isfinite(v) or not low <= v <= high:
            raise ValueError(f'{label}: must be between {low} and {high}')
        if key in INTEGER:
            if v != int(v):
                raise ValueError(f'{label}: an integer is required')
            v = int(v)
        values[key] = v
    if family == 'differential' and values['spiral_hand'] not in (-1,1):
        raise ValueError('Spiral handedness must be −1 or +1.')
    if double:
        values['double_style'] = style
        if style == 'joined':
            values['gap'] = 0
        elif values['gap'] <= 0:
            raise ValueError('Separate helices require a groove greater than zero.')
    if family == 'harmonic':
        output = supplied.get('harmonic_output', 'flex')
        if output not in HARMONIC_OUTPUTS:
            raise ValueError('Unknown strain wave output configuration.')
        values['harmonic_output'] = output
    if io_options(family):
        values['io_scheme'] = supplied['io_scheme']
        if family == 'planetary' and variant in ('two_stage', 'two_stage_double'):
            values['io_scheme2'] = supplied.get('io_scheme2', supplied['io_scheme'])
            if values['io_scheme2'] not in io_options(family):
                raise ValueError('Second stage input/output arrangement unavailable.')
    values.update(options(family, supplied))
    values.update(hardware_options(family, supplied))
    if family in ('spur', 'helical', 'double', 'planetary', 'harmonic', 'worm', 'parallel', 'internal'):
        m = values['module']
        z = values.get('teeth', values.get('sun', 24))
        if family in ('spur', 'helical', 'double'):
            from engineering import gear_dimensions
            root = gear_dimensions(z, m, values['pressure'], values.get('helix', 0), values['profile_shift'], values['addendum'], values['dedendum'], backlash=values['backlash'])['root_radius']
        else:
            root = m * (z / 2 - 1.25)
        if family not in ('parallel', 'internal', 'worm') and values['bore'] / 2 >= root - 0.25:
            raise ValueError('The bore is too large for the tooth root diameter.')
        if values['backlash'] >= m * 0.7:
            raise ValueError('Backlash too large for the module.')
    if family == 'double' and values['gap'] >= values['width'] - 1:
        raise ValueError('The groove must leave at least 1 mm of teeth.')
    if family == 'planetary':
        stages = [(values['sun'], values['planet'])]
        if variant in ('two_stage', 'two_stage_double'):
            stages.append((values['sun2'], values['planet2']))
        for zs, zp in stages:
            n = values['planets']
            zr = zs + 2 * zp
            if (zs + zr) % n:
                raise ValueError('Equally spaced assembly: (sun teeth + ring teeth) must be divisible by the planet count in each stage.')
            if m * (zs + zp) * sin(pi / n) <= m * (zp + 2) + values['backlash']:
                raise ValueError('I satelliti si sovrappongono: ridurne numero o dimensione.')
            if values['bore'] < 2:
                raise ValueError('The assembly requires a bore of at least 2 mm for shafts and pins.')
            if values['bore'] / 2 >= m * (min(zs, zp) / 2 - 1.25) - 0.5:
                raise ValueError('Bores too large for the sun or planets.')
    if family == 'planetary' and variant in ('double', 'two_stage_double'):
        if values['gap'] >= min(values['width'], values.get('width2', values['width'])) - 1:
            raise ValueError('Groove too wide for the teeth.')
    if family == 'harmonic':
        if values['teeth'] % 2:
            raise ValueError('Use an even tooth count for the two lobe flexspline.')
        if values['wall'] >= m * (z / 2 - 1.25) - values['bore'] / 2:
            raise ValueError('Flexspline wall too thick.')
    if family == 'worm' and values['worm_hand'] == 0:
        raise ValueError('Worm handedness must be −1 or +1.')
    return values

def polar(r, a):
    return (r * cos(a), r * sin(a))

class CircleProfile(list):
    """Sampled circle with explicit construction provenance, for CAD export.

    This remains a normal list for preview/STL. Exporters may promote it only
    while the coordinates still match the original, immutable snapshot.
    Arbitrary equiradial polygons deliberately carry no such provenance.
    """
    def __init__(self, points=(), radius=None, center=None):
        super().__init__(points)
        self.radius = radius
        self.center = tuple(center) if center is not None else None
        self.samples = tuple(tuple(q) for q in self)

    def intact(self):
        return self.radius is not None and self.center is not None and tuple(tuple(q) for q in self) == self.samples


def circle(r, n=96, center=(0, 0)):
    return CircleProfile([(center[0] + r * cos(TAU * i / n), center[1] + r * sin(TAU * i / n)) for i in range(n)], r, center)

def transformed(points, center=(0, 0), angle=0):
    c, s = (cos(angle), sin(angle))
    result = [(center[0] + x * c - y * s, center[1] + x * s + y * c) for x, y in points]
    if isinstance(points, CircleProfile) and points.intact():
        x, y = points.center
        return CircleProfile(result, points.radius, (center[0]+x*c-y*s, center[1]+x*s+y*c))
    return result

def circle_info(points):
    if len(points) < 16:
        return None
    cx = sum((p[0] for p in points)) / len(points)
    cy = sum((p[1] for p in points)) / len(points)
    rs = [hypot(x - cx, y - cy) for x, y in points]
    r = sum(rs) / len(rs)
    if r > 0 and max(rs) - min(rs) < 1e-07:
        return (cx, cy, r)
    return None

def contains(points, q):
    x, y = q
    inside = False
    for a, b in zip(points, points[1:] + points[:1]):
        if (a[1] > y) != (b[1] > y) and x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]:
            inside = not inside
    return inside

def material_point(outer, holes):
    radius = max((hypot(x, y) for x, y in outer))
    for fraction in (0.98, 0.94, 0.88, 0.75, 0.5, 0.25, 0):
        for j in range(48):
            q = polar(radius * fraction, TAU * (j + 0.217) / 48)
            if contains(outer, q) and (not any((contains(h, q) for h in holes))):
                return list(q)
    raise ValueError('No solid region found in the profile: check the remaining thickness.')

def clean(points):
    out = []
    for x, y in points:
        p = (round(x, 9), round(y, 9))
        if not out or hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > 1e-07:
            out.append(p)
    if len(out) > 1 and hypot(out[-1][0] - out[0][0], out[-1][1] - out[0][1]) < 1e-07:
        out.pop()
    return out

def sample_curve(fn, a, b, tolerance=0.015, depth=0):
    start, end = (fn(a), fn(b))
    mid = (a + b) / 2
    actual = fn(mid)
    dx, dy = (end[0] - start[0], end[1] - start[1])
    den = dx * dx + dy * dy

    def deviation(actual):
        t = max(0, min(1, ((actual[0] - start[0]) * dx + (actual[1] - start[1]) * dy) / den)) if den else 0
        return hypot(actual[0] - start[0] - t * dx, actual[1] - start[1] - t * dy)
    error = max(deviation(actual), deviation(fn((3 * a + b) / 4)), deviation(fn((a + 3 * b) / 4)))
    if error <= tolerance or depth >= 12:
        return [start, end]
    return sample_curve(fn, a, mid, tolerance, depth + 1)[:-1] + sample_curve(fn, mid, b, tolerance, depth + 1)

def involute(z, m, pressure=20, backlash=0.15, internal=False, samples=4, depth_module=None, shift=0, normal_pressure=None, ha=1, hf=1.25, metadata=None):
    """Involute with a rack-generated external root or constructed ring blend.

    ``samples`` remains a compatibility argument. All curves use the shared
    adaptive 0.015 mm chord threshold. Metadata is optional, never a second
    geometry path.
    """
    from tooth_profiles import external_half, internal_half
    depth = m if depth_module is None else depth_module
    if internal:
        if shift:
            raise ValueError('Shifted internal rings require a dedicated shaping cutter model.')
        flank, info = internal_half(z, m, pressure, backlash, depth, ha, hf, sample_curve)
    else:
        flank, info = external_half(z, m, pressure, backlash, depth, shift, normal_pressure, ha, hf, sample_curve)
    if metadata is not None:
        metadata.update(info)
    pitch = TAU/z
    root = info['root_radius_mm']; tip = info['tip_radius_mm']
    at = atan2(flank[0 if internal else -1][1], flank[0 if internal else -1][0])
    ar = atan2(flank[-1 if internal else 0][1], flank[-1 if internal else 0][0])
    right = flank if internal else list(reversed(flank))
    points=[]
    for k in range(z):
        a=k*pitch
        local=sample_curve(lambda q:polar(root,q),-pitch/2,-ar)[:-1]
        local += [(x,-y) for x,y in reversed(right)]
        local += sample_curve(lambda q:polar(tip,q),-at,at)[1:-1]
        local += right
        local += sample_curve(lambda q:polar(root,q),ar,pitch/2)[1:]
        points.extend(transformed(local,angle=a))
    return clean(points)

def cycloid(n, R, e, pin, clearance=0, samples=None, tolerance=0.01):
    """Inward offset of the roller-centre trajectory in the disc frame."""
    if e * n >= R * 0.9:
        raise ValueError('Eccentricity eccessiva: usare e × N / R < 0,90.')
    count = max(4096, n * 64)

    def evaluate(t):
        x = R * cos(t) - e * cos(n * t)
        y = R * sin(t) - e * sin(n * t)
        dx = -R * sin(t) + e * n * sin(n * t)
        dy = R * cos(t) - e * n * cos(n * t)
        ddx = -R * cos(t) + e * n * n * cos(n * t)
        ddy = -R * sin(t) + e * n * n * sin(n * t)
        speed = hypot(dx, dy)
        curvature = (dx * ddy - dy * ddx) / speed ** 3
        return ((x - (pin + clearance) * dy / speed, y + (pin + clearance) * dx / speed), curvature)
    min_curvature = min((1 / k for j in range(count) if (k := evaluate(TAU * j / count)[1]) > 0), default=float('inf'))
    if pin + clearance >= min_curvature * 0.98:
        raise ValueError('Cycloidal offset has cusps: reduce roller radius or eccentricity.')
    if 2 * pin >= 2 * R * sin(pi / n):
        raise ValueError('Ring rollers overlap.')
    if samples:
        points = [evaluate(TAU * j / samples)[0] for j in range(samples)]
    else:
        points = []
        for j in range(n * 8):
            points.extend(sample_curve(lambda t: evaluate(t)[0], TAU * j / (n * 8), TAU * (j + 1) / (n * 8), tolerance)[:-1])
    return clean(points)

@dataclass
class Part:
    """One nominal solid, with local XY contours and local Z section levels.

    Dimensions are mm; twist is degrees. solid_geometry.point() applies placement
    after section rotation. Adjacent sections must keep corresponding vertices;
    explicit mesh faces provide an alternative to section construction.
    """
    name: str
    outer: list
    holes: list = field(default_factory=list)
    width: float = 10
    z: float = 0
    center: tuple = (0, 0)
    twist: float = 0
    axis_x: bool = False
    double: bool = False
    gap: float = 0
    core_radius: float = 0
    role: str = 'gear'
    color: tuple = (0.35, 0.72, 0.9)
    internal: bool = False
    catalog_code: str = ''
    procurement: dict = field(default_factory=dict)
    machining: list = field(default_factory=list)
    stations: list = field(default_factory=list)
    alternate_diagonal: bool = False
    mesh: list = field(default_factory=list)
    frame: tuple = ()
    port: dict = field(default_factory=dict)
    manufacturing: dict = field(default_factory=dict)
    profile_metadata: dict = field(default_factory=dict)

def profile_sections(p):
    """Return (local Z mm, twist degrees, outer contour) for one continuous solid.

    The continuous core and groove transitions belong to this shared geometry;
    exporters and preview must not invent separate lofts for the two helices.
    """
    if p.stations:
        return [(s['z'], 0, s['outer']) for s in p.stations]
    if not p.double:
        n = max(1, min(288, ceil(abs(p.twist) / 6)))
        return [(p.width * j / n, p.twist * j / n, p.outer) for j in range(n + 1)]
    h = (p.width - p.gap) / 2
    peak = p.twist * h / p.width
    radius = max((hypot(x, y) for x, y in p.outer))
    maxstep = degrees(2 * acos(max(0, 1 - 0.02 / radius)))
    n = max(2, ceil(abs(peak) / maxstep))
    if 2 * n + 5 > 512:
        raise ValueError('Double helix too complex: reduce width or helix angle.')
    shoulder = min(0.15, h * 0.08, p.gap * 0.2) if p.gap else 0
    end = h - shoulder
    sections = [(end * j / n, p.twist * end * j / n / p.width, p.outer) for j in range(n + 1)]
    if p.gap:
        root = min((hypot(x, y) for x, y in p.outer))
        core = p.outer if p.internal else [polar(p.core_radius + 0.001 * (hypot(x, y) - root), atan2(y, x)) for x, y in p.outer]
        sections.extend([(h, peak, core), (h + p.gap, peak, core)])
        start = h + p.gap + shoulder
        sections.append((start, peak - p.twist * shoulder / p.width, p.outer))
    else:
        start = h
    for j in range(1, n + 1):
        z = start + (p.width - start) * j / n
        sections.append((z, p.twist * (p.width - z) / p.width, p.outer))
    return sections

def section_holes(p, z, outer=None):
    if p.stations:
        return next((s['holes'] for s in p.stations if s['outer'] is outer)) if outer is not None else next((s['holes'] for s in p.stations if s['z'] == z))
    if not (p.double and p.internal and p.gap):
        return p.holes
    h = (p.width - p.gap) / 2
    shoulder = min(0.15, h * 0.08, p.gap * 0.2)
    factor = max(0, min(1, (z - h + shoulder) / shoulder, (h + p.gap + shoulder - z) / shoulder))
    loop = p.holes[0]
    root = max((hypot(x, y) for x, y in loop))
    groove = min(root + 0.3, min((hypot(x, y) for x, y in p.outer)) - 0.5)
    inner = [polar((1 - factor) * hypot(x, y) + factor * (groove + 0.001 * (hypot(x, y) - root)), atan2(y, x)) for x, y in loop]
    return [inner] + p.holes[1:]

@dataclass
class Design:
    """Validated parameters, ordered nominal parts and their shared analysis.

    Internal motion/picking indices are zero-based positions in parts. Export
    source_indices, when present, retain one-based positions from the full model.
    """
    family: str
    values: dict
    parts: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    metrics: list = field(default_factory=list)
    token: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    requirements: list = field(default_factory=list)
    analysis: dict = field(default_factory=dict)

    def asset_folder(self, asset_dir=None):
        from pathlib import Path
        from app_paths import default_output_dir
        return Path(asset_dir) if asset_dir else default_output_dir() / 'solids' / self.token

    def prepare_assets(self, asset_dir=None):
        from solid_geometry import step, signature
        from export_transaction import write_text
        folder = self.asset_folder(asset_dir)
        for idx, p in zip((i-1 for i in getattr(self,'source_indices',range(1,len(self.parts)+1))),self.parts):
            if p.mesh or p.frame or p.stations or p.double or (abs(p.twist) > 1e-08):
                signature(p)
                folder.mkdir(parents=True, exist_ok=True)
                base = f'{self.token}_{idx}_{p.name}'
                write_text(folder / (base + '.step'), step(p, base + '_body'))
        return folder

    def commands(self, asset_dir=None):
        cmds = []

        def add(command, **params):
            cmds.append({'command': command, 'params': params})
        group = f'Reducers_{self.family}_{self.token}'
        add('component.activate', component='root')
        add('component.create', name=group)
        from bom import build
        add('component.metadata.set', component=group, values={'local.solidcraft.riduttori': build(self)})
        for idx, p in zip((i-1 for i in getattr(self,'source_indices',range(1,len(self.parts)+1))),self.parts):
            base = f'{self.token}_{idx}_{p.name}'
            explicit = p.mesh or p.frame or p.stations or p.double or (abs(p.twist) > 1e-08)
            if explicit:
                add('file.insert_step', path=str((self.asset_folder(asset_dir) / (base + '.step')).resolve()), name=base, names='solid', up='z')
            else:
                add('component.create', name=base, parent=group)
            from bom import part_info, port_properties
            info = part_info(p)
            metadata = {}
            if hasattr(self,'export_scope'):metadata['local.ratiolab.selection']={'source_index':idx+1,'scope':self.export_scope}
            if p.port:
                metadata['local.solidcraft.kinematic_port'] = p.port
            if p.manufacturing:
                metadata['local.solidcraft.manufacturing'] = p.manufacturing
            if p.profile_metadata:
                metadata['local.solidcraft.profile_geometry'] = p.profile_metadata
            add('component.metadata.set', component=base, part_number=info['code'], description=info['description'], values=metadata, properties={'Procurement': info['category'], 'Manufacturer': info.get('manufacturer', ''), 'Dimensions': info['dimensions'], 'Source': info.get('source', ''), 'Standard': info.get('standard', ''), **port_properties(p)})
            if p.machining:
                add('component.metadata.set', component=base, values={'local.solidcraft.machining': {'operations': p.machining}})

            def profile(suffix, z, rotation):
                name = base + suffix
                add('sketch.create', name=name, plane={'origin': [p.center[0], p.center[1], z], 'x_dir': [1, 0, 0], 'y_dir': [0, 1, 0]})
                for loop in [p.outer] + p.holes:
                    pts = transformed(loop, angle=radians(rotation))
                    circ = circle_info(pts)
                    if circ:
                        add('sketch.circle.center', center=list(circ[:2]), radius=circ[2])
                    else:
                        add('sketch.line', points=pts, closed=True, infer=False, connect=False)
                add('sketch.finish')
                return name

            def segment(suffix, z, height, rotation, twist):
                sk = profile(suffix, z, rotation)
                if abs(twist) < 1e-08:
                    add('solid.extrude', sketch=sk, profiles=[{'point': material_point(transformed(p.outer, angle=radians(rotation)), [transformed(h, angle=radians(rotation)) for h in p.holes])}], distance=f'{height:.10f} mm', operation='new', body_name=base + suffix)
                else:
                    path = base + suffix + '_path'
                    add('sketch.create', name=path, plane={'origin': [p.center[0], p.center[1], z], 'x_dir': [1, 0, 0], 'y_dir': [0, 0, 1]})
                    add('sketch.line', points=[[0, 0], [0, height]], infer=False, connect=False)
                    add('sketch.finish')
                    add('solid.sweep', sketch=sk, profiles=[{'point': material_point(transformed(p.outer, angle=radians(rotation)), [transformed(h, angle=radians(rotation)) for h in p.holes])}], path_sketch=path, path=['l1'], twist=f'{twist:.10f} deg', operation='new', body_name=base + suffix)
                    add('browser.visibility', visible=False, items=[sk, path])
                return base + suffix
            if not explicit:
                names = [segment('_body', p.z, p.width, 0, 0)]
                if p.axis_x:
                    add('solid.move', bodies=names, axis=[0, 1, 0], angle='90 deg')
                    add('solid.move', bodies=names, translate=[-p.width / 2, p.center[1], p.z])
            from solid_geometry import PALETTE
            color = p.color if p.color != (0.35, 0.72, 0.9) else PALETTE[idx % len(PALETTE)]
            add('appearance.assign', bodies=[base + '_body'], color=[round(v * 255) for v in color])
            add('component.activate', component=group)
        add('component.activate', component='root')
        return cmds

def gear_part(name, z, m, pressure, backlash, width, bore=0, center=(0, 0), phase=0, helix=0, internal=False, rim=5, zoff=0, shift=0, ha=1, hf=1.25):
    """Build from normal module/pressure; pressure and helix are degrees, phase radians."""
    mt = m / cos(radians(helix))
    at = degrees(atan(tan(radians(pressure)) / cos(radians(helix))))
    profile_info = {}
    outline = transformed(involute(z, mt, at, backlash, internal, depth_module=m, shift=shift, normal_pressure=pressure, ha=ha, hf=hf, metadata=profile_info), angle=phase)
    if not internal and bore / 2 >= min((hypot(x, y) for x, y in outline)) - 0.25:
        raise ValueError(f'{name}: bore too large for the tooth root diameter.')
    outer = circle(mt * z / 2 + hf * m + rim) if internal else outline
    holes = [outline] if internal else [circle(bore / 2)] if bore > 0 else []
    return Part(name, outer, holes, width, zoff, center, degrees(width * tan(radians(helix)) / (mt * z / 2)), internal=internal, profile_metadata={'tooth_profile': profile_info})

def generate(family, supplied=None):
    """Normalize once, construct the assembly, then finalize kinematics and reports."""
    v = validate(family, supplied or {})
    d = Design(family, v)
    w = v['width']
    bore = v.get('bore', 0)
    m = v.get('module', 2)
    pa = v.get('pressure', 20)
    b = v.get('backlash', 0.15)

    def gear(name, z, center=(0, 0), phase=0, helix=0, internal=False, rim=5, bore_override=None, zoff=0):
        p = gear_part(name, z, m, pa, b, w, bore if bore_override is None else bore_override, center, phase, helix, internal, rim, zoff, v.get('profile_shift', 0) if family in ('spur', 'helical', 'double') else 0, v.get('addendum', 1), v.get('dedendum', 1.25))
        d.parts.append(p)
        return p
    if family in ('spur', 'helical', 'double'):
        z = v['teeth']
        beta = v.get('helix', 0)
        p = gear('Gear', z, helix=beta)
        if family == 'double':
            p.double = True
            p.gap = v['gap']
            p.core_radius = min((hypot(x, y) for x, y in p.outer)) * 0.96
            if bore / 2 >= p.core_radius - 0.25:
                raise ValueError('Bore too large for the continuous hub below the groove.')
        d.metrics = [f'Pitch diameter: {m * z / cos(radians(beta)):.3f} mm', f'Teeth: {z} · normal module: {m:g} mm', f'Total twist: {p.twist:.2f}°']
        from engineering import gear_dimensions, force_components, gear_warnings
        g = gear_dimensions(z, m, pa, beta, v['profile_shift'], v['addendum'], v['dedendum'], backlash=b)
        d.analysis['gear'] = g
        d.analysis['forces'] = force_components(v['input_torque'], 2 * g['pitch_radius'], g['alpha_t'], beta)
        d.metrics.append(f"Tip Ø {2 * g['tip_radius']:.3f} · Root Ø {2 * g['root_radius']:.3f} mm · αt {g['alpha_t']:.3f}°")
        d.notes.extend(gear_warnings(g))
        if family == 'double':
            d.notes.append('Theoretical net axial force is zero only when load is shared equally between the two halves. Reported Fa represents a single helix at full torque as a conservative reference.')
        if family == 'double':
            d.notes.append('A single STEP BRep solid with the same faces as the preview, without interpolated lofts. Continuous hub below the groove and axial transitions of at most 0.15 mm.')
    elif family in ('planetary', 'cycloidal'):
        from assemblies import planetary, cycloidal
        (planetary if family == 'planetary' else cycloidal)(d)
    elif family in ('parallel', 'internal'):
        from geartrains import build_train
        build_train(d)
    elif family in ('harmonic', 'worm'):
        from special_drives import harmonic, worm
        (harmonic if family == 'harmonic' else worm)(d)
    elif family == 'differential':
        from differential_wrist import build
        build(d)
    from standard_parts import apply_catalog
    apply_catalog(d)
    from hardware import apply_hardware
    apply_hardware(d)
    from printed_shaft import apply as apply_printed_shaft
    apply_printed_shaft(d)
    # Finalize I/O mounting and ports after catalog/hardware/printed additions;
    # reports, motion and exports must describe the same completed assembly.
    from kinematics import apply as apply_kinematics
    apply_kinematics(d)
    from engineering import attach_report
    attach_report(d)
    if any((p.mesh or p.frame or p.stations or p.double or (abs(p.twist) > 1e-08) for p in d.parts)):
        d.notes.append('Faithful preview export: faceted STEP BRep solids for parts with shared surfaces. Extruded profile circles are sampled with a maximum radial deviation of 0.002 mm; tubes and freeform surfaces use the sampling specified in the guide. Edit dimensions in the generator and regenerate the group. This is not a smooth parametric loft.')
    d.analysis['tooth_profiles'] = [dict(part=p.name, **p.profile_metadata['tooth_profile']) for p in d.parts if 'tooth_profile' in p.profile_metadata]
    if family != 'differential':
        d.notes.append('External cylindrical roots use a rounded normal rack envelope with undercut trimming; internal roots use a tangent circular construction, not a shaping cutter envelope. Adaptive chord threshold 0.015 mm; tool geometry and domain are in the calculation JSON. Strength, lubrication and manufacturing tolerances are not verified.')
    return d
