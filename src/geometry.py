# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Shared dimensional geometry in millimetres, with no external dependencies.

Input pressure/helix angles and stored section twist use degrees. Low-level
trigonometric helpers and profile phase use radians; convert at those boundaries.
See README.md and docs/technical/calculations.md for model limits.
"""
from dataclasses import dataclass, field
from rust_geometry import call as rust_call
from parameter_errors import ParameterError, field_context
from math import sin, cos, tan, acos, atan, atan2, sqrt, pi, radians, degrees, hypot, isfinite, ceil
import uuid
TAU = 2 * pi
FAMILIES = {'spur': 'Spur gear', 'helical': 'Helical gear', 'double': 'Double helical gear', 'planetary': 'Planetary gearbox', 'cycloidal': 'Cycloidal drive', 'harmonic': 'Strain wave drive', 'worm': 'Worm drive', 'parallel': 'Parallel shaft reducer · single stage', 'internal': 'Internal gear reducer · fixed axes'}
COMMON = [('module', 'Normal module [mm]', 2.0, 0.1, 10, 0.1), ('width', 'Face width [mm]', 10, 1, 100, 1), ('bore', 'Bore diameter [mm]', 6, 0, 100, 0.5), ('pressure', 'Pressure angle [°]', 20, 14.5, 30, 0.5), ('backlash', 'Tangential backlash [mm]', 0.15, 0, 1, 0.01)]
SPECS = {'spur': COMMON + [('teeth', 'Tooth count', 24, 8, 160, 1)], 'helical': COMMON + [('teeth', 'Tooth count', 24, 8, 160, 1), ('helix', 'Helix angle [°] (sign = handedness)', 20, -45, 45, 1)], 'double': COMMON + [('teeth', 'Tooth count', 24, 8, 160, 1), ('helix', 'Helix angle [°]', 25, -45, 45, 1), ('gap', 'Central groove [mm]', 1, 0, 10, 0.1)], 'planetary': COMMON + [('sun', 'Sun teeth', 18, 8, 80, 1), ('planet', 'Planet teeth', 18, 8, 60, 1), ('planets', 'Planet count', 3, 2, 6, 1), ('rim', 'Ring thickness [mm]', 5, 1, 30, 0.5)], 'cycloidal': [('pins', 'Ring roller count', 16, 6, 60, 1), ('radius', 'Roller pitch radius [mm]', 40, 10, 150, 1), ('pin_radius', 'Roller radius [mm]', 3, 1, 10, 0.1), ('eccentric', 'Eccentricity [mm]', 1.2, 0.1, 5, 0.1), ('width', 'Disc thickness [mm]', 8, 1, 40, 1), ('bore', 'Eccentric seat diameter [mm]', 12, 2, 60, 1), ('output_count', 'Output pin count', 6, 3, 10, 1), ('output_radius', 'Output pin pitch radius [mm]', 22, 5, 100, 1), ('output_pin', 'Output pin radius [mm]', 2, 1, 10, 0.1), ('clearance', 'Radial clearance [mm]', 0.1, 0, 0.8, 0.01)], 'harmonic': COMMON + [('teeth', 'Flexspline teeth', 60, 30, 160, 2), ('wall', 'Flexible wall thickness [mm]', 1, 0.3, 4, 0.1), ('rim', 'Ring thickness [mm]', 5, 1, 30, 0.5)], 'worm': COMMON + [('teeth', 'Wheel teeth', 30, 12, 100, 1), ('starts', 'Worm starts', 1, 1, 4, 1), ('diameter', 'Worm pitch diameter [mm]', 20, 8, 80, 1), ('length', 'Worm length [mm]', 24, 5, 80, 1)]}
VARIANTS = {'double': {'joined': 'Joined helices · no groove', 'separated': 'Separate helices · with groove'}, 'worm': {'za': 'Cylindrical ZA · straight axial flanks', 'zi': 'Cylindrical ZI · transverse involute'}, 'harmonic': {'cup': 'Cup', 'flat_cup': 'Flat cup', 'hat': 'External flange · silk hat'}, 'planetary': {'spur': 'Single stage · spur', 'helical': 'Single stage · helical', 'double': 'Single stage · double helical', 'two_stage': 'Two stages in cascade', 'two_stage_double': 'Two stages · double helical'}, 'cycloidal': {'single': 'Complete single disc', 'dual': 'Dual disc · opposing eccentrics'}, 'parallel': {'spur': 'Spur teeth', 'helical': 'Helical', 'double': 'Double helix'}, 'internal': {'spur': 'Internal gear · spur', 'helical': 'Internal gear · helical', 'double': 'Internal gear · double helical'}}
DOUBLE_STYLES = {'joined': 'Joined helices · no groove', 'separated': 'Separate helices · with groove'}
from parallel_multistage import VARIANTS as PARALLEL_MULTISTAGE_VARIANTS
VARIANTS['parallel'].update(PARALLEL_MULTISTAGE_VARIANTS)
FAMILIES['parallel'] = 'Parallel shaft reducer'
from wolfrom import SPECS as WOLFROM_SPECS
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

FAMILIES['wolfrom'] = 'Wolfrom reducer · two-rim'
VARIANTS['wolfrom'] = {'spur': 'Two-rim spur · sun input / ring output',
                       'helical': 'Two-rim helical · sun input / ring output',
                       'double': 'Two-rim double helical · sun input / ring output'}
SPECS['wolfrom'] = WOLFROM_SPECS
from bevel_pair import SPECS as BEVEL_PAIR_SPECS, VARIANTS as BEVEL_VARIANTS
FAMILIES['bevel'] = 'Bevel gear pair'
VARIANTS['bevel'] = BEVEL_VARIANTS
SPECS['bevel'] = BEVEL_PAIR_SPECS
from hypoid_geometry import SPECS as HYPOID_SPECS
FAMILIES['hypoid'] = 'Hypoid gear pair'
VARIANTS['hypoid'] = {'generated': 'Generated spiral pinion'}
SPECS['hypoid'] = HYPOID_SPECS
from rack_geometry import SPECS as RACK_SPECS, VARIANTS as RACK_VARIANTS
FAMILIES['rack'] = 'Rack and pinion'
VARIANTS['rack'] = RACK_VARIANTS
SPECS['rack'] = RACK_SPECS
from face_geometry import SPECS as FACE_SPECS, VARIANTS as FACE_VARIANTS
FAMILIES['face'] = 'Face gear pair'
VARIANTS['face'] = FACE_VARIANTS
SPECS['face'] = FACE_SPECS

def is_double(family, variant=None):
    return family == 'double' or variant in ('double', 'two_stage_double', 'three_stage_double') or family=='face' and variant=='double_helical'
PAIR_FIELDS = COMMON + [('pinion', 'Input pinion teeth', 20, 12, 100, 1), ('wheel', 'Driven wheel teeth', 60, 22, 200, 1), ('output_bore', 'Output bore [mm]', 8, 0, 100, 0.5)]
SPECS['parallel'] = PAIR_FIELDS
SPECS['internal'] = [(k, label, 22 if k == 'pinion' else 66 if k == 'wheel' else default, lo, hi, step) for k, label, default, lo, hi, step in PAIR_FIELDS if k != 'output_bore'] + [('rim', 'Ring thickness [mm]', 5, 2, 30, 0.5)]
ASSEMBLY_FIELDS = [('plate', 'Flange thickness [mm]', 3, 1, 30, 0.5), ('assembly_clearance', 'Axial / assembly clearance [mm]', 0.2, 0.05, 1, 0.05)]

def get_specs(family, variant=None, double_style=None):
    if family not in FAMILIES:
        raise ValueError('Unknown family')
    specs = list(SPECS[family])
    if family == 'face':
        if variant=='double_helical' and double_style is None:double_style='joined'
        if variant in ('helical','double_helical'):specs += [('helix','Pinion helix angle [°]',15,-25,25,1)]
        if variant == 'double_helical' and double_style!='joined':specs += [('gap','Central band relief [mm]',4,1,12,.5)]
    if family == 'rack':
        if variant in ('helical','double'):specs += [('helix','Pinion helix angle [°]',20,-35,35,1)]
        if variant == 'double':specs += [('gap','Central groove [mm]',1,0,10,.1)]
    if family == 'bevel':
        from bevel_pair import trace_specs
        specs += trace_specs(variant or 'straight')
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
        elif family == 'wolfrom':
            if variant in ('helical', 'double'):
                specs += [('helix', 'Sun helix angle [°] (sign = handedness)', 20, -35, 35, 1)]
            if variant == 'double':
                specs += [('gap', 'Central groove in each layer [mm]', 1, 0, 10, .1)]
        elif family == 'cycloidal':
            specs += [('input_shaft', 'Input shaft diameter [mm]', 4, 2, 30, 0.5), ('output_shaft', 'Output shaft diameter [mm]', 8, 3, 40, 0.5), ('housing_wall', 'Housing thickness [mm]', 4, 2, 15, 0.5)]
        elif family in ('parallel', 'internal'):
            from parallel_multistage import tooth_type
            teeth_type = tooth_type(variant)
            if teeth_type in ('helical', 'double'):
                specs += [('helix', 'Input helix angle [°]', 20, -35, 35, 1)]
            if teeth_type == 'double':
                specs += [('gap', 'Central groove [mm]', 1, 0, 10, 0.1)]
            if family != 'internal':
                specs += [('profile_shift', 'Pinion profile shift x (wheel = −x)', 0, -0.5, 0.7, 0.05)]
            if family == 'parallel':
                specs += [('center_extra', 'Centre distance increase [mm]', 0, 0, 5, 0.05)]
                if variant in PARALLEL_MULTISTAGE_VARIANTS:
                    from parallel_multistage import specs as train_specs
                    specs += train_specs(variant)
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
        from printed_shaft import FIELDS, DIRECT_FIELDS
        specs += FIELDS + DIRECT_FIELDS
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
            specs = [s for s in specs if s[0] not in ('gap', 'gap2', 'gap3')]
    from engineering import LOAD_FIELDS
    from tooth_tips import specs as tip_specs
    specs += tip_specs(family, variant)
    if family == 'differential':
        specs += [('input_rpm', 'Input A speed [rpm]', 12, -100000, 100000, 1),
                  ('input_b_rpm', 'Input B speed [rpm]', -12, -100000, 100000, 1)]
    elif family == 'wolfrom':
        specs += [('input_rpm', 'Sun input speed [rpm]', 600, -100000, 100000, 50)] + LOAD_FIELDS[1:]
    else:
        specs += LOAD_FIELDS[:2] if family in ('spur', 'helical', 'double') else LOAD_FIELDS
    if family in ('bevel','hypoid','rack','face') or family == 'parallel' and variant in PARALLEL_MULTISTAGE_VARIANTS:
        specs = [(k, label, d, -100000 if k == 'input_rpm' else lo, hi, st) for k, label, d, lo, hi, st in specs]
    if family == 'rack':specs=[(k,label,12 if k=='input_rpm' else d,lo,hi,st) for k,label,d,lo,hi,st in specs]
    return specs
INTEGER = {'teeth', 'sun', 'planet', 'planets', 'pins', 'output_count', 'starts', 'sun2', 'planet2', 'pinion', 'wheel', 'pinion2', 'wheel2', 'worm_hand', 'rollers', 'crown_teeth', 'segments', 'planet_teeth', 'pairs', 'friction_faces', 'crank_teeth', 'cranks', 'spring_count', 'coils', 'bolt_count', 'bevel_pinion'}
INTEGER.update(('side_teeth', 'output_teeth', 'spiral_hand', 'output_ring'))
INTEGER.update(('pinion3', 'wheel3', 'rack_teeth'))

def defaults(family, variant=None):
    v = {s[0]: s[2] for s in get_specs(family, variant)}
    if family in VARIANTS:
        v['variant'] = variant or next(iter(VARIANTS[family]))
    if family == 'differential':
        from differential_wrist import OPTION_DEFAULTS
        v.update(OPTION_DEFAULTS)
    if family == 'cycloidal':
        v['eccentric_design'] = 'integral'
    if family=='face' and variant=='double_helical':v.update(double_style='joined',gap=0)
    return v

def validate(family, supplied):
    """Resolve linked options before validating the resulting physical dimensions.

    I/O compatibility and printed-shaft preparation precede variant/style
    normalization. Bearing dimensions then feed hardware preparation, so numeric
    and geometric checks see the final bores, widths and assembly choices.
    """
    if family not in FAMILIES:
        raise ValueError('Unknown family')
    from precise_numbers import restore,PreciseFloat,SOURCE_KEY,attach,from_text
    supplied=restore(supplied)
    from tooth_tips import KEYS as TIP_KEYS, specs as tip_specs
    requested_tips={key for key in supplied if any(key==name or key.endswith('_'+name) for name in TIP_KEYS)}
    # Inactive stage/variant drafts follow the existing parameter contract:
    # recognize them here, then retain only the active specs below.
    supported_tips={item[0] for variant in VARIANTS.get(family,{None:None}) for item in tip_specs(family,variant)}
    if requested_tips-supported_tips:
        raise ValueError('Unsupported tooth-tip parameter(s): '+', '.join(sorted(requested_tips-supported_tips)))
    precise={key:value for key,value in supplied.items() if isinstance(value,PreciseFloat)}
    supplied.pop(SOURCE_KEY,None)
    if family == 'parallel':
        from parallel_multistage import prepare as prepare_parallel
        supplied = prepare_parallel(supplied)
    if family == 'wolfrom':
        from wolfrom import prepare as prepare_wolfrom
        supplied = prepare_wolfrom(supplied)
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
    if family=='face' and variant=='double_helical' and 'double_style' not in supplied and 'gap' not in supplied:style='joined'
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
        values['eccentric_design'] = supplied.get('eccentric_design', 'integral')
    for key, label, default, low, high, step in get_specs(family, variant, style):
        v = supplied.get(key, default)
        if isinstance(v, bool):
            raise ParameterError('number.required', (key,), f'{label}: a numeric value is required', kind='input')
        if isinstance(v,str):
            try:v=from_text(v)
            except ValueError as error:
                raise ParameterError('number.required', (key,), f'{label}: a numeric value is required', kind='input') from error
        exact=v if isinstance(v,PreciseFloat) else precise.get(key)
        if exact is not None and float(exact)!=float(v):exact=None
        if exact is not None:
            try:rust_call('validate_number',dict(value=exact.expression,lower=low,upper=high,
                integer=key in INTEGER,compatibility_value=float(v)))
            except ValueError as error:
                number=float(v)
                violation='lower' if number<low else 'upper' if number>high else None
                limits={key:dict(lower=low,upper=high,violation=violation)} if violation and isfinite(number) else {}
                raise ParameterError('number.domain', (key,), label+': '+str(error), kind='input', limits=limits) from error
        try:v = float(v)
        except (ValueError,TypeError,OverflowError) as error:
            raise ParameterError('number.required', (key,), f'{label}: a numeric value is required', kind='input') from error
        if not isfinite(v) or not low <= v <= high:
            raise ParameterError('number.bounds', (key,), f'{label}: must be between {low} and {high}', kind='input', limits={key:dict(lower=low,upper=high,violation='lower' if v<low else 'upper' if v>high else None)})
        if key in INTEGER:
            if v != int(v):
                raise ParameterError('number.integer', (key,), f'{label}: an integer is required', kind='input')
            v = int(v)
        attach(values,key,PreciseFloat(v,exact.expression) if exact is not None and key not in INTEGER else v)
    if family in ('differential', 'bevel') and 'spiral_hand' in values and values['spiral_hand'] not in (-1,1):
        raise ValueError('Spiral handedness must be −1 or +1.')
    if double:
        values['double_style'] = style
        if style == 'joined':
            values['gap'] = 0
        elif values['gap'] <= 0:
            raise ParameterError('groove.positive', ('gap',), 'Separate helices require a groove greater than zero.', 'Increase the groove or select joined helices.')
        if family == 'parallel' and variant in PARALLEL_MULTISTAGE_VARIANTS:
            from parallel_multistage import count, stage_key
            for stage in range(2, count(values)+1):
                key = stage_key('gap', stage)
                if style == 'joined':
                    values[key] = 0
                elif values[key] <= 0:
                    raise ParameterError('groove.positive', (key,), 'Separate helices require a groove greater than zero.', 'Increase the groove or select joined helices.')
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
    from backdrivability import physical_inputs, enforce
    values.update(physical_inputs(family, supplied))
    enforce(family, values)
    if family in ('spur', 'helical', 'double', 'planetary', 'harmonic', 'worm', 'parallel', 'internal'):
        m = values['module']
        z = values.get('teeth', values.get('sun', 24))
        if family in ('spur', 'helical', 'double'):
            from engineering import gear_dimensions
            root = gear_dimensions(z, m, values['pressure'], values.get('helix', 0), values['profile_shift'], values['addendum'], values['dedendum'], backlash=values['backlash'])['root_radius']
        else:
            root = m * (z / 2 - 1.25)
        if family not in ('parallel', 'internal', 'worm') and values['bore'] / 2 >= root - 0.25:
            raise ParameterError('bore.root', ('bore', 'module', 'teeth', 'pressure', 'profile_shift', 'dedendum', 'helix') if family in ('spur','helical','double') else ('bore','module','sun' if family=='planetary' else 'teeth'), 'The bore is too large for the tooth root diameter.', 'Reduce the bore or increase the module or tooth count.', limits={'bore':dict(upper=2*(root-.25),upper_exclusive=True)})
        if values['backlash'] >= m * 0.7:
            raise ParameterError('backlash.module', ('backlash','module'), 'Backlash too large for the module.', 'Reduce backlash or increase the module.', limits={'backlash':dict(upper=m*.7,upper_exclusive=True)})
    if family == 'double' and values['gap'] >= values['width'] - 1:
        raise ParameterError('groove.width', ('gap','width'), 'The groove must leave at least 1 mm of teeth.', 'Reduce the groove or increase the face width.', limits={'gap':dict(upper=values['width']-1,upper_exclusive=True)})
    if family == 'planetary':
        stages = [(values['sun'], values['planet'])]
        if variant in ('two_stage', 'two_stage_double'):
            stages.append((values['sun2'], values['planet2']))
        for stage, (zs, zp) in enumerate(stages, 1):
            sun_key='sun' if stage==1 else 'sun2'
            planet_key='planet' if stage==1 else 'planet2'
            n = values['planets']
            zr = zs + 2 * zp
            if (zs + zr) % n:
                raise ParameterError('planetary.spacing', (sun_key,planet_key,'planets'), 'Equally spaced assembly: (sun teeth + ring teeth) must be divisible by the planet count in each stage.', 'Change the sun or planet tooth count, or the number of planets, to satisfy the divisibility rule.')
            if m * (zs + zp) * sin(pi / n) <= m * (zp + 2) + values['backlash']:
                raise ParameterError('planetary.overlap', (sun_key,planet_key,'planets','module','backlash'), 'Planet envelopes overlap.', 'Reduce the number of planets or the planet tooth count, or increase the sun tooth count. Recheck equal spacing.')
            if values['bore'] < 2:
                raise ParameterError('planetary.bore_minimum', ('bore',), 'The assembly requires a bore of at least 2 mm for shafts and pins.', 'Increase the bore.', limits={'bore':dict(lower=2)})
            if values['bore'] / 2 >= m * (min(zs, zp) / 2 - 1.25) - 0.5:
                raise ParameterError('planetary.bore_root', ('bore','module',sun_key,planet_key), 'Bores too large for the sun or planets.', 'Reduce the bore or increase the module or tooth count.')
    if family == 'planetary' and variant in ('double', 'two_stage_double'):
        if values['gap'] >= min(values['width'], values.get('width2', values['width'])) - 1:
            raise ParameterError('groove.width', ('gap','width','width2') if 'width2' in values else ('gap','width'), 'Groove too wide for the teeth.', 'Reduce the groove or increase the face width.')
    if family == 'harmonic':
        if values['teeth'] % 2:
            raise ParameterError('harmonic.even_teeth', ('teeth',), 'Use an even tooth count for the two lobe flexspline.')
        if values['wall'] >= m * (z / 2 - 1.25) - values['bore'] / 2:
            raise ParameterError('harmonic.wall', ('wall','module','teeth','bore'), 'Flexspline wall too thick.', 'Reduce the wall thickness or bore, or increase the module or tooth count.')
    if family == 'worm' and values['worm_hand'] == 0:
        raise ValueError('Worm handedness must be −1 or +1.')
    if family == 'wolfrom':
        from wolfrom import validate as validate_wolfrom
        validate_wolfrom(values)
    if family == 'bevel':
        from bevel_pair import dimensions
        dimensions(values)
    if family == 'face':
        from face_geometry import Generator
        Generator(values)
    if family == 'rack':
        from rack_geometry import validate_dimensions
        validate_dimensions(values)
    if family == 'hypoid':
        from hypoid_geometry import Generator
        Generator(values)
    return values

def polar(r, a):
    return tuple(rust_call('planar_polar',dict(radius=r,angle=a)))

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
    pending=_CIRCLE_BATCH.get()
    if pending is not None:
        result=CircleProfile([],r,center)
        pending.append((result,dict(radius=r,count=n,center=center)))
        return result
    return CircleProfile([tuple(p) for p in rust_call('planar_circle',dict(radius=r,count=n,center=center))],r,center)


from contextvars import ContextVar
from contextlib import contextmanager
_CIRCLE_BATCH=ContextVar('ratiolab_circle_batch',default=None)


@contextmanager
def batch_circles():
    """Fill independent construction circles together before publishing a Design.
    The planetary builder only stores these loops until this context exits.
    Each CircleProfile owns its list and preserves its circle provenance.
    """
    if _CIRCLE_BATCH.get() is not None:
        yield
        return
    pending=[];token=_CIRCLE_BATCH.set(pending)
    try:
        yield
        if pending:
            from rust_geometry import call_geometry
            rows=call_geometry('planar_circles',dict(circles=[spec for _,spec in pending]))
            if len(rows)!=len(pending):raise RuntimeError('Invalid circle batch result.')
            for (circle,spec),points in zip(pending,rows):
                if len(points)!=spec['count']:raise RuntimeError('Invalid circle point count.')
                circle.extend(points)
                circle.samples=tuple(points)
    finally:
        _CIRCLE_BATCH.reset(token)

def transformed(points, center=(0, 0), angle=0):
    result=[tuple(p) for p in rust_call('planar_transform',dict(points=points,center=center,angle=angle))]
    if isinstance(points,CircleProfile) and points.intact():
        moved=rust_call('planar_transform',dict(points=[points.center],center=center,angle=angle))[0]
        return CircleProfile(result,points.radius,moved)
    return result


def circle_info(points):
    result=rust_call('planar_circle_info',dict(points=points))
    return tuple(result) if result is not None else None


def contains(points,q):
    return rust_call('planar_contains',dict(points=points,point=q))


def material_point(outer,holes):
    return rust_call('planar_material_point',dict(outer=outer,holes=holes))


def clean(points):
    return [tuple(p) for p in rust_call('planar_clean',dict(points=points))]

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

# The callback remains available to callers outside the kernel. Cylindrical
# construction recognizes this sampler and performs its refinement in Rust.
sample_curve._ratiolab_rust_adaptive = True


def involute(z, m, pressure=20, backlash=0.15, internal=False, samples=4, depth_module=None, shift=0, normal_pressure=None, ha=1, hf=1.25, metadata=None, minimum_join_radius_mm=None):
    from rust_geometry import call
    result = call('involute_profile', dict(z=z, mt=m, pressure=pressure,
        backlash=backlash, internal=internal, depth=depth_module, shift=shift,
        normal_pressure=normal_pressure, ha=ha, hf=hf,
        minimum_join_radius_mm=minimum_join_radius_mm))
    if metadata is not None:
        metadata.update(result['metadata'])
    return [tuple(p) for p in result['points']]


def cycloid(n, R, e, pin, clearance=0, samples=None, tolerance=0.01):
    from rust_geometry import call
    with field_context(dict(n='pins',radius='radius',eccentricity='eccentric',pin='pin_radius',clearance='clearance')):
        result = call('cycloid_profile', dict(n=n, radius=R, eccentricity=e, pin=pin,
            clearance=clearance, samples=samples, tolerance=tolerance))
    return [tuple(p) for p in result['points']]

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
    # Surface interpolation only; the sampled 2D tooth profile has its own error.
    surface_tolerance_mm: float = 0.02

def profile_sections(p):
    if p.stations:
        return [(s['z'],0,s['outer']) for s in p.stations]
    from rust_surfaces import surface
    rows=surface(p).call('solid_sections')
    return [(row['z'],row['angle'],p.outer if row['base'] else [tuple(q) for q in row['outer']]) for row in rows]


def resolve_station_index(p,z,outer=None,station_index=None):
    """Select a section explicitly; equal contours can have different bores."""
    if station_index is not None:
        if (type(station_index) is not int or not 0<=station_index<len(p.stations)
                or p.stations[station_index]['z']!=z):
            raise ValueError('Invalid station index or axial position.')
        return station_index
    candidates=[i for i,s in enumerate(p.stations) if s['z']==z]
    if len(candidates)>1 and outer is not None:
        candidates=[i for i in candidates if p.stations[i]['outer'] is outer]
    if len(candidates)!=1:
        raise ValueError('Ambiguous or missing station; supply an explicit station index.')
    return candidates[0]


def section_holes(p,z,outer=None,station_index=None):
    if p.stations:
        return p.stations[resolve_station_index(p,z,outer,station_index)]['holes']
    if not (p.double and p.internal and p.gap):
        return p.holes
    from rust_surfaces import surface
    return [[tuple(q) for q in loop] for loop in surface(p).call('solid_section_holes',z=z)]

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
    quality: dict = field(default_factory=dict)
    component_sheets: dict = field(default_factory=dict)

    def asset_folder(self, asset_dir=None):
        from pathlib import Path
        from app_paths import default_output_dir
        return Path(asset_dir) if asset_dir else default_output_dir() / 'solids' / self.token

    def prepare_assets(self, asset_dir=None):
        from solid_geometry import step, signature
        from export_transaction import write_text
        folder = self.asset_folder(asset_dir)
        from geometry_quality import representation
        for idx, p in zip((i-1 for i in getattr(self,'source_indices',range(1,len(self.parts)+1))),representation(self,'export').parts):
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
        from geometry_quality import representation
        for idx, p in zip((i-1 for i in getattr(self,'source_indices',range(1,len(self.parts)+1))),representation(self,'export').parts):
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
                from solid_geometry import profile_report
                metadata['local.solidcraft.profile_geometry'] = profile_report(p)
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

def gear_part(name, z, m, pressure, backlash, width, bore=0, center=(0, 0), phase=0, helix=0, internal=False, rim=5, zoff=0, shift=0, ha=1, hf=1.25, minimum_join_radius_mm=None,cutter_allowance=False,rack_tip_radius_mm=None,safe_pair_sampling=False,topping_mm=0,semitopping_mm=0,semitopping_angle_deg=45):
    from rust_geometry import cached_call
    result=cached_call('gear_part',dict(name=name,z=z,m=m,pressure=pressure,
        backlash=backlash,width=width,bore=bore,center=center,phase=phase,helix=helix,
        internal=internal,rim=rim,zoff=zoff,shift=shift,ha=ha,hf=hf,
        minimum_join_radius_mm=minimum_join_radius_mm,cutter_allowance=cutter_allowance,rack_tip_radius_mm=rack_tip_radius_mm,safe_pair_sampling=safe_pair_sampling,
        topping_mm=topping_mm,semitopping_mm=semitopping_mm,semitopping_angle_deg=semitopping_angle_deg))
    return part_from_kernel(name,result)


def part_from_kernel(name, result):
    """Decode Rust construction data without rebuilding its mathematical shape."""
    result=dict(result)
    result.pop('name',None)
    outer=[tuple(p) for p in result['outer']]
    holes=[[tuple(p) for p in loop] for loop in result['holes']]
    outer_radius=result.pop('outer_circle_radius',None)
    bore_radius=result.pop('bore_circle_radius',None)
    if outer_radius is not None:
        outer=CircleProfile(outer,outer_radius,(0,0))
    if bore_radius is not None:
        holes[0]=CircleProfile(holes[0],bore_radius,(0,0))
    result.update(outer=outer,holes=holes)
    if 'center' in result:result['center']=tuple(result['center'])
    if 'color' in result:result['color']=tuple(result['color'])
    if 'frame' in result:result['frame']=tuple(tuple(axis) for axis in result['frame'])
    triangle_points=result.pop('mesh_triangle_points',None)
    if triangle_points is not None:
        if len(triangle_points)%3 or len(triangle_points)//3>250000:
            raise RuntimeError('Invalid Rust construction triangle count.')
        from rust_geometry import control_check
        mesh=[]
        for start in range(0,len(triangle_points),3):
            if start%3072==0:control_check()
            mesh.append([[tuple(p) for p in triangle_points[start:start+3]]])
        result['mesh']=mesh
    for station in result.get('stations',[]):
        station['outer']=[tuple(p) for p in station['outer']]
        station['holes']=[[tuple(p) for p in loop] for loop in station['holes']]
    return Part(name,**result)


def generate(family, supplied=None, *, quality=None):
    """Normalize once, construct the assembly, then finalize kinematics and reports."""
    v = validate(family, supplied or {})
    from geometry_quality import normalize
    d = Design(family, v, quality=normalize(quality))
    w = v['width']
    bore = v.get('bore', 0)
    m = v.get('module', 2)
    pa = v.get('pressure', 20)
    b = v.get('backlash', 0.15)

    def gear(name, z, center=(0, 0), phase=0, helix=0, internal=False, rim=5, bore_override=None, zoff=0):
        from tooth_tips import parameters
        p = gear_part(name, z, m, pa, b, w, bore if bore_override is None else bore_override, center, phase, helix, internal, rim, zoff, v.get('profile_shift', 0) if family in ('spur', 'helical', 'double') else 0, v.get('addendum', 1), v.get('dedendum', 1.25), **parameters(v))
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
                raise ParameterError('bore.hub', ('bore','module','teeth','pressure','profile_shift','dedendum','helix'), 'Bore too large for the continuous hub below the groove.', 'Reduce the bore or increase the module or tooth count.')
        d.metrics = [f'Pitch diameter: {m * z / cos(radians(beta)):.3f} mm', f'Teeth: {z} · normal module: {m:g} mm', f'Total twist: {p.twist:.2f}°']
        from engineering import gear_dimensions, force_components, gear_warnings
        g = gear_dimensions(z, m, pa, beta, v['profile_shift'], v['addendum'], v['dedendum'], backlash=b, topping_mm=v['topping_mm'])
        g['tooth_thickness'] = p.profile_metadata['tooth_profile']['tooth_thickness']
        d.analysis['gear'] = g
        d.analysis['forces'] = force_components(v['input_torque'], 2 * g['pitch_radius'], g['alpha_t'], beta)
        d.metrics.append(f"Tip Ø {2 * g['tip_radius']:.3f} · Root Ø {2 * g['root_radius']:.3f} mm · αt {g['alpha_t']:.3f}°")
        d.notes.extend(gear_warnings(g))
        if family == 'double':
            d.notes.append('Theoretical net axial force is zero only when load is shared equally between the two halves. Reported Fa represents a single helix at full torque as a conservative reference.')
        if family == 'double':
            d.notes.append('A single STEP BRep solid from the nominal construction, with independent preview/export interpolation and no interpolated lofts. Continuous hub below the groove and axial transitions of at most 0.15 mm.')
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
    elif family == 'wolfrom':
        from wolfrom import build
        build(d)
    elif family == 'bevel':
        from bevel_pair import build
        build(d)
    elif family == 'face':
        from face_geometry import build
        build(d)
    elif family == 'rack':
        from rack_geometry import build
        build(d)
    elif family == 'hypoid':
        from hypoid_geometry import build
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
    from printed_shaft import omit_reference_shafts
    omit_reference_shafts(d)
    from engineering import attach_report
    attach_report(d)
    if any((p.mesh or p.frame or p.stations or p.double or (abs(p.twist) > 1e-08) for p in d.parts)):
        d.notes.append('Faithful preview export: faceted STEP BRep solids for parts with shared surfaces. Extruded profile circles are sampled with a maximum radial deviation of 0.002 mm; tubes and freeform surfaces use the sampling specified in the guide. Edit dimensions in the generator and regenerate the group. This is not a smooth parametric loft.')
    d.analysis['tooth_profiles'] = [dict(part=p.name, **p.profile_metadata['tooth_profile']) for p in d.parts if 'tooth_profile' in p.profile_metadata]
    treated=[dict(part=p.name,**p.profile_metadata['tooth_profile']['tip_treatment']) for p in d.parts if p.profile_metadata.get('tooth_profile',{}).get('tip_treatment')]
    if treated:
        d.analysis['tooth_tip_treatments']=treated
        d.notes.append('Tooth tips: topping is radial removal from the existing nominal head; semitopping is a secondary involute from a normal rack ramp. Effective contact excludes the chamfer. Internal roots remain nominal constructed blends; a production shaping cutter is not qualified.')
    if family not in ('differential', 'bevel', 'hypoid', 'rack', 'face'):
        d.notes.append('External cylindrical roots use a rounded normal rack envelope with undercut trimming; internal roots use a tangent circular construction, not a shaping cutter envelope. Adaptive chord threshold 0.015 mm; tool geometry and domain are in the calculation JSON. Strength, lubrication and manufacturing tolerances are not verified.')
    return d
