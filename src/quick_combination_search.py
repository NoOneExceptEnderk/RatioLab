# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Target-driven, bounded candidate domains for the desktop search."""
from dataclasses import dataclass, field
from itertools import product
from math import floor, gcd, isfinite, prod
import re
from time import monotonic

from combination_search import COUNT_KEYS, Halt, Result, estimated_ratio, evaluate, matches
from geometry import VARIANTS, defaults, get_specs, is_double
from kinematics import default
from parallel_multistage import count, stage_key, tooth_type
from precise_numbers import attach, restore
from shaft_connections import profile_key, targets

RADIAL = frozenset(('planetary', 'cycloidal', 'harmonic', 'internal', 'wolfrom'))
TEETH = {'spur': 'Spur', 'helical': 'Helical', 'double': 'Double helical'}
# A quick run compares a finite, ratio-guided sample. More coverage is available
# through the existing explicit ranges and adjustable budgets.
STAGE_OPTIONS = 24


def parse_ratio(text):
    parts = text.strip().replace('−', '-').replace(',', '.').split(':')
    try:
        if len(parts) > 2 or any(not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', p.strip())
                                 for p in parts):
            raise ValueError
        numerator = float(parts[0])
        denominator = float(parts[1]) if len(parts) == 2 else 1.
        value = abs(numerator/denominator)
        if not isfinite(numerator) or not isfinite(denominator) or denominator <= 0 or not isfinite(value) or value <= 0:
            raise ValueError
    except (ValueError, ZeroDivisionError):
        raise ValueError('Enter a positive ratio magnitude, for example 5:1.') from None
    direction = {'+': 'same', '-': 'opposite'}.get(parts[0].strip()[0], 'either')
    return value, direction


def stage_count(family, variant):
    if family == 'planetary':
        return 2 if variant.startswith('two_stage') else 1
    return count({'variant': variant}) if family == 'parallel' else 1


def available_variants(family, current):
    if family in ('planetary', 'parallel', 'internal', 'wolfrom', 'cycloidal', 'bevel', 'face'):
        return VARIANTS[family]
    return {current: VARIANTS[family][current]}


def variant_teeth(family, variant):
    return 'double' if family == 'planetary' and variant == 'two_stage_double' else tooth_type(variant)


def bearing_modes(family, values):
    from catalog import MODES
    if family == 'parallel':
        enabled = stage_count(family, values['variant']) == 1
    elif family in ('planetary', 'cycloidal'):
        scheme = default(family)
        enabled = values.get('io_scheme', scheme) == scheme and (
            stage_count(family, values['variant']) == 1 or values.get('io_scheme2', scheme) == scheme)
        enabled = enabled and values.get('eccentric_design') != 'fdm_bolted'
    else:
        enabled = family == 'internal'
    return {k: v for k, v in MODES.items() if k == 'manual' or
            enabled and (k != 'gear' or family in ('planetary', 'cycloidal'))}


def fixed_connection(family, values, port):
    if family == 'cycloidal':
        from printed_shaft import DESIGNS
        member = values['io_scheme'].split('_')[0 if port == 'input' else 1]
        return {'eccentric': DESIGNS[values.get('eccentric_design', 'integral')],
                'output': 'Pin flange', 'ring': 'Ring / housing flange'}[member]
    if family in ('internal', 'wolfrom'):
        return 'Annular ring'
    if family == 'harmonic':
        member = values['io_scheme'].split('_')[0 if port == 'input' else 1]
        return 'Flexspline flange' if member == 'flex' else 'Circular spline flange'
    if family == 'planetary':
        scheme = values.get('io_scheme2', values['io_scheme']) if (
            port == 'output' and stage_count(family, values['variant']) == 2) else values['io_scheme']
        member = scheme.split('_')[0 if port == 'input' else 1]
        return {'sun': 'Standard shaft', 'carrier': 'Planet carrier flange', 'ring': 'Annular ring'}[member]
    return 'Standard connection'


def construction(family, base, variant, options):
    """Retain shared dimensions and I/O while adapting the active construction."""
    current = base['variant']
    values = restore(dict(base, variant=variant))
    variant_defaults = defaults(family, variant)
    if variant != current:
        for key in ('helix', 'helix2', 'helix3', 'gap', 'gap2', 'gap3'):
            if key not in variant_defaults:
                values.pop(key, None)
        if 'helix' in variant_defaults and base.get('helix', 0) == 0 and variant_defaults['helix'] != 0:
            for key in ('helix', 'helix2', 'helix3'):
                if key in variant_defaults:
                    attach(values, key, variant_defaults[key])
    if variant != current and is_double(family, variant) and values.get('double_style') == 'separated':
        for key in ('gap', 'gap2', 'gap3'):
            if key in variant_defaults and values.get(key, 0) <= 0:
                attach(values, key, variant_defaults[key])
    for key in COUNT_KEYS[family]:
        if key in variant_defaults:
            values.setdefault(key, variant_defaults[key])
        else:
            values.pop(key, None)
    values.update(options)
    if not is_double(family, variant):
        values.pop('double_style', None)
    if family == 'planetary' and stage_count(family, variant) == 2:
        values.setdefault('io_scheme2', values['io_scheme'])
    modes = bearing_modes(family, values)
    if values.get('bearing_mode', 'manual') not in modes:
        if options.get('bearing_mode', 'manual') != 'manual':
            return None
        values.update(bearing_mode='manual', hardware_mode='none')
    if family == 'parallel' and stage_count(family, variant) > 1:
        values['hardware_mode'] = 'none'
    for port in ('input', 'output'):
        key = profile_key(port)
        if port not in targets(family, values):
            if options.get(key, 'standard') != 'standard':
                return None
            if key in values:
                values[key] = 'standard'
        if key not in base and values.get(key) == 'standard':
            values.pop(key)
    return values


def band(spec, lower, upper):
    _, _, _, low, high, _ = spec
    lo, hi = max(low, lower), min(high, upper)
    if not isfinite(lo) or not isfinite(hi) or lo > hi:
        return ()
    return range(max(int(low), floor(lo)), min(int(high), floor(hi)+1)+1)


def nearest(spec, center, radius=1):
    _, _, _, low, high, _ = spec
    if not isfinite(center) or center < low-radius-1 or center > high+radius+1:
        return ()
    middle = floor(center)
    return range(max(int(low), middle-radius), min(int(high), middle+radius+1)+1)


def near_count(spec, current, radius):
    return sorted(nearest(spec, current, radius), key=lambda value: (abs(value-current), value))


def stage_ratio(family, values, stage):
    if family == 'parallel':
        return -values[stage_key('wheel', stage)] / values[stage_key('pinion', stage)]
    from kinematics import coefficients
    terms = coefficients(family, values, stage)
    scheme = values['io_scheme'] if stage == 1 else values.get('io_scheme2', values['io_scheme'])
    driving, driven, _ = scheme.split('_')
    return -terms[driven]/terms[driving]


def planetary_companion(sun, magnitude, scheme):
    """Invert the same three-member coefficient quotient used for pruning."""
    # Coefficients divided by sun: sun=1, ring=1+2p/s, carrier=-2-2p/s.
    terms = {'sun': (1, 0), 'ring': (1, 2), 'carrier': (2, 2)}
    driving, driven, _ = scheme.split('_')
    a, b = terms[driven]
    c, d = terms[driving]
    denominator = b-magnitude*d
    return sun*(magnitude*c-a)/denominator if denominator else float('inf')


def stage_candidates(family, values, specs, stage, target, check):
    if not isfinite(target) or target <= 0:
        return []
    if family == 'planetary':
        driver, driven = stage_key('sun', stage), stage_key('planet', stage)
        scheme = values['io_scheme'] if stage == 1 else values.get('io_scheme2', values['io_scheme'])
        companion = lambda n: planetary_companion(n, target, scheme)
    else:
        driver, driven = stage_key('pinion', stage), stage_key('wheel', stage)
        companion = lambda n: target*n
    candidates = []
    _, _, _, low, high, _ = specs[driver]
    for n in range(int(low), int(high)+1):
        check()
        for k in nearest(specs[driven], companion(n)):
            if family == 'planetary' and (2*(n+k)) % values['planets']:
                continue
            pair = {driver: n, driven: k}
            ratio = abs(stage_ratio(family, dict(values, **pair), stage))
            candidates.append((abs(ratio/target-1), abs(n-values[driver]), abs(k-values[driven]), pair))
    candidates.sort(key=lambda item: item[:3])
    return [row[-1] for row in candidates[:STAGE_OPTIONS]]


def cascade_candidates(family, values, specs, settings, check):
    stages = stage_count(family, values['variant'])
    target = settings.target
    if family == 'parallel' and values['io_scheme'] == 'reverse':
        target = 1/target
    if not isfinite(target) or target <= 0:
        return
    baseline = [abs(stage_ratio(family, values, stage)) for stage in range(1, stages+1)]
    current = prod(baseline)
    # Test one-stage changes with the other stages fixed, then share the change
    # across stages, and try an even ratio split. Each stage keeps its own I/O.
    for stage, existing in enumerate(baseline, 1):
        yield from stage_candidates(family, values, specs, stage, target/(current/existing), check)
    if stages > 1:
        scale = (target/current)**(1/stages)
        for targets_per_stage in ([r*scale for r in baseline], [target**(1/stages)]*stages):
            pools = [stage_candidates(family, values, specs, stage, r, check)
                     for stage, r in enumerate(targets_per_stage, 1) if r > 0]
            if len(pools) == stages:
                for combination in product(*(pool[:10] for pool in pools)):
                    yield {key: value for pair in combination for key, value in pair.items()}


def wolfrom_candidates(values, specs, settings, check):
    # With A=(S+Rf)/S, invert i=A*P1*Ro/(P1*Ro-Rf*P2).
    # The two signs lie on opposite sides of the stationary-output determinant.
    n = values['planets']
    for s in near_count(specs['sun'], values['sun'], 8):
        for p1 in near_count(specs['planet'], values['planet'], 14):
            rf = s + 2*p1
            if (s+rf) % n:
                continue
            factor = (s+rf)/s
            for p2 in near_count(specs['planet2'], values['planet2'], 16):
                check()
                for signed in (settings.target, -settings.target):
                    divisor = 1-factor/signed
                    if divisor <= 0:
                        continue
                    for ro in nearest(specs['output_ring'], rf*p2/(p1*divisor), 2):
                        if ro > p2 and (p1*ro + p2*s) % (n*gcd(p1, p2)) == 0:
                            yield dict(sun=s, planet=p1, planet2=p2, output_ring=ro)


def tooth_candidates(family, values, settings, check):
    specs = {spec[0]: spec for spec in get_specs(family, values['variant'], values.get('double_style'))}
    yield {}
    if family in ('planetary', 'parallel'):
        yield from cascade_candidates(family, values, specs, settings, check)
    elif family == 'wolfrom':
        yield from wolfrom_candidates(values, specs, settings, check)
    elif family in ('cycloidal', 'harmonic'):
        key = COUNT_KEYS[family][0]
        _, _, _, low, high, _ = specs[key]
        for value in range(int(low), int(high)+1):
            if family != 'harmonic' or value % 2 == 0:
                yield {key: value}
    else:
        driver, driven = ('starts', 'teeth') if family == 'worm' else ('pinion', 'wheel')
        tolerance = settings.tolerance_percent/100
        lower, upper = settings.target*(1-tolerance), settings.target*(1+tolerance)
        if values['io_scheme'] == 'reverse':
            if not lower:
                return
            lower, upper = 1/upper, 1/lower
        _, _, _, low, high, _ = specs[driver]
        for n in range(int(low), int(high)+1):
            check()
            for k in band(specs[driven], lower*n, upper*n):
                yield {driver: n, driven: k}


@dataclass
class QuickResult(Result):
    max_diameter: float | None = None
    radial: bool = False
    geometry_errors: dict = field(default_factory=dict)
    variants: tuple = ()
    construction_options: dict = field(default_factory=dict)

    def text(self):
        limits = f'Diameter ≤ {self.max_diameter:g} mm' if self.max_diameter is not None else (
            'Diameter unrestricted' if self.radial else ' × '.join(
                f'{v:g}' if v < 1e300 else 'unrestricted' for v in self.settings.max_xyz[:2]) + ' mm (X × Y)')
        lines = [f'Quick combination search · {self.family}', f'Target {self.settings.target:g} · ±{self.settings.tolerance_percent:g}% · {self.settings.direction}',
                 limits, f'Variants: {", ".join(self.variants)}', f'Construction: {self.construction_options}',
                 'Envelope of generated solids in the nominal pose, including supports and hardware.',
                 f'Visited {self.visited}/{self.total} ratio-guided candidates · {self.reason or "complete"}',
                 f'Exclusions: {self.exclusions}', *self.geometry_errors]
        for index, proposal in enumerate(self.proposals, 1):
            lines.append(f'{index}. i={proposal.ratio:+.12g}; {size_text(self.family, proposal)}; {proposal.changes}')
        return '\n'.join(lines)


def size_text(family, proposal):
    diameter = proposal.comparison.get('diameter_mm')
    x, y, z = proposal.xyz
    footprint = f'Ø {diameter:.6g} mm' if diameter is not None else f'{x:.6g} × {y:.6g} mm'
    axial = 'axial' if family in RADIAL or family == 'parallel' else 'along Z'
    return f'{footprint} · {z:.6g} mm {axial}'


def quick_search(family, base, variants, options, settings, max_diameter=None, cancel=None,
                 progress=lambda message, fraction: None, *, quality=None):
    started = monotonic()
    settings.validate()
    variants = tuple(variants)
    result = QuickResult(family, base, {}, settings, 0, radial=family in RADIAL, max_diameter=max_diameter,
                         variants=variants, construction_options=dict(options))
    planned = []
    seen = set()

    def check():
        if cancel is not None and cancel.is_set():
            raise Halt('cancelled')
        if monotonic()-started >= settings.max_seconds:
            raise Halt('time budget reached')

    try:
        for variant in variants:
            check()
            values = construction(family, base, variant, options)
            if values is None:
                continue
            for counts in tooth_candidates(family, values, settings, check):
                check()
                candidate = dict(values, **counts)
                identity = variant, tuple(candidate[k] for k in COUNT_KEYS[family] if k in candidate)
                if identity in seen:
                    continue
                seen.add(identity)
                ratio = estimated_ratio(family, candidate)
                if matches(ratio, settings):
                    distance = sum(abs(candidate[k]-values[k]) for k in counts if k in values)
                    planned.append((round(abs(abs(ratio)/settings.target-1), 12),
                                    distance, variant != base['variant'], candidate))
    except Halt as error:
        result.reason = str(error)
        result.elapsed = monotonic()-started
        return result

    planned.sort(key=lambda row: row[:3])
    result.total = len(planned)
    return evaluate(result, (row[-1] for row in planned), started, cancel, progress,
                    radial=result.radial, max_diameter=max_diameter, quality=quality)
