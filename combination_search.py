"""Finite geometric combination search; standard library only, no document mutation."""
from copy import deepcopy
from dataclasses import dataclass, field
from itertools import product
from math import isfinite, prod
from time import monotonic
from geometry import generate, get_specs, INTEGER
from solid_geometry import rings, point

FAMILIES = ('parallel', 'internal', 'planetary', 'cycloidal', 'harmonic', 'worm')
COUNT_KEYS = dict(parallel=('pinion', 'wheel'), internal=('pinion', 'wheel'),
                  planetary=('sun', 'planet', 'sun2', 'planet2', 'planets'),
                  cycloidal=('pins',), harmonic=('teeth',), worm=('teeth', 'starts'))


def variables(family, values):
    """Only these geometrical dimensions can be unlocked. Every other key is fixed."""
    allowed = set(COUNT_KEYS.get(family, ())) | {'module', 'width', 'width2', 'radius'}
    return [s for s in get_specs(family, values.get('variant'), values.get('double_style')) if s[0] in allowed]


def parse_grid(text):
    """Explicit comma separated numbers or inclusive low:high:step grids."""
    result = []
    for term in text.split(','):
        fields = term.strip().split(':')
        if len(fields) == 1:
            numbers = [float(fields[0])]
        elif len(fields) == 3:
            lo, hi, step = map(float, fields)
            if not all(map(isfinite, (lo, hi, step))) or step <= 0 or hi < lo:
                raise ValueError('Grid requires finite low ≤ high and step > 0.')
            span = (hi-lo)/step
            if not isfinite(span) or span >= 1000:
                raise ValueError('At most 1000 values per variable.')
            count = int(span+1e-10)+1
            if count > 1000:
                raise ValueError('At most 1000 values per variable.')
            numbers = [lo+i*step for i in range(count)]
        else:
            raise ValueError('Use comma separated values or low:high:step.')
        for number in numbers:
            if not isfinite(number):
                raise ValueError('Grid values must be finite.')
            if number not in result:
                result.append(number)
            if len(result) > 1000:
                raise ValueError('At most 1000 values per variable.')
    if not result:
        raise ValueError('Empty variable grid.')
    return tuple(result)


@dataclass(frozen=True)
class Settings:
    target: float = 3.0
    tolerance_percent: float = 1.0
    direction: str = 'either'
    max_xyz: tuple = (1000., 1000., 1000.)
    max_candidates: int = 50000
    max_seconds: float = 30.
    max_results: int = 100

    def validate(self):
        if isinstance(self.target, bool) or not isfinite(self.target) or self.target <= 0:
            raise ValueError('Target magnitude |input speed / output speed| must be finite and positive.')
        if not isfinite(self.tolerance_percent) or not 0 <= self.tolerance_percent < 100:
            raise ValueError('Relative tolerance must be finite, from 0 to less than 100 percent.')
        if self.direction not in ('either', 'same', 'opposite'):
            raise ValueError('Choose either, same or opposite direction.')
        if len(self.max_xyz) != 3 or not all(isfinite(x) and x > 0 for x in self.max_xyz):
            raise ValueError('All three nominal XYZ limits must be finite and positive in mm.')
        for value, low, high, name in ((self.max_candidates, 1, 1000000, 'candidate budget'), (self.max_results, 1, 500, 'result limit')):
            if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
                raise ValueError(f'Invalid {name}.')
        if not isfinite(self.max_seconds) or not 0 < self.max_seconds <= 3600:
            raise ValueError('Time limit must be positive, at most 3600 seconds.')


def matches(ratio, settings):
    direction = 1 if ratio > 0 else -1
    return (isfinite(ratio) and ratio != 0 and
            (settings.direction == 'either' or direction == (1 if settings.direction == 'same' else -1)) and
            abs(abs(ratio)/settings.target-1) <= settings.tolerance_percent/100 + 1e-12)


def estimated_ratio(family, values):
    """Cheap shared I/O equation, used only for pruning, never for accepted results."""
    from kinematics import coefficients, solve
    if family in ('planetary', 'cycloidal', 'harmonic'):
        stages = 2 if family == 'planetary' and values['variant'] in ('two_stage', 'two_stage_double') else 1
        ratio = 1.
        for stage in range(1, stages+1):
            scheme = values['io_scheme2' if stage == 2 else 'io_scheme']
            ratio *= solve(coefficients(family, values, stage), scheme, 1.)['signed_ratio']
        return ratio
    ratio = ((-1 if family == 'parallel' else 1)*values['wheel']/values['pinion']
             if family in ('parallel', 'internal') else values['worm_hand']*values['teeth']/values['starts'])
    return 1/ratio if values['io_scheme'] == 'reverse' else ratio


def nominal_bounds(design, check=lambda: None):
    """AABB of shared nominal surface vertices, all generated parts, world XYZ mm.

    Ring vertices include all facets of lofts/twists and station profiles. Mesh
    vertices use the same point transform as faces(). No motion sweep or view filters.
    """
    low = [float('inf')]*3
    high = [-float('inf')]*3
    for part in design.parts:
        check()
        levels = ([[[point(part, q[:2], q[2], 0) for q in loop] for loop in face] for face in part.mesh]
                  if part.mesh else rings(part))
        for level in levels:
            check()
            for loop in level:
                for vertex in loop:
                    for axis, coordinate in enumerate(vertex):
                        if not isfinite(coordinate):
                            raise ValueError('Non-finite nominal geometry.')
                        low[axis] = min(low[axis], coordinate)
                        high[axis] = max(high[axis], coordinate)
    if not all(map(isfinite, low+high)):
        raise ValueError('No finite solid geometry.')
    return tuple(low), tuple(high)


@dataclass
class Proposal:
    values: dict
    ratio: float
    error_percent: float
    minimum: tuple
    maximum: tuple
    changes: dict

    @property
    def xyz(self):
        return tuple(b-a for a, b in zip(self.minimum, self.maximum))

    @property
    def sort_key(self):
        return (self.error_percent, prod(self.xyz), self.xyz, repr(sorted(self.changes.items())))


@dataclass
class Result:
    family: str
    base: dict
    axes: dict
    settings: Settings
    total: int
    visited: int = 0
    generated: int = 0
    valid: int = 0
    matched: int = 0
    rejected: int = 0
    elapsed: float = 0.
    reason: str = ''
    proposals: list = field(default_factory=list)
    revision: object = None

    @property
    def complete(self):
        return self.visited == self.total and not self.reason

    def text(self):
        s = self.settings
        lines = ['Finite geometric combination search', f'Family: {self.family}; document revision: {self.revision}',
                 f'Target |input speed / output speed| = {s.target:g}; relative tolerance ±{s.tolerance_percent:g}%; direction: {s.direction}',
                 f'Nominal world XYZ limits [mm]: {s.max_xyz}',
                 'Envelope: all generated components, including supports/housing/hardware; nominal sampled shared preview/STL surface vertices in the export pose. Not a motion swept envelope. STEP analytic circles can extend slightly beyond the sampled bound.',
                 'Variants, stages, I/O and all keys outside the enumerated grids remain fixed.',
                 'Ratio comparison uses a 1e-12 relative floating-point guard. Cancellation/time limits are cooperative: one generation or surface section build can finish before the stop is observed.',
                 'Locked baseline parameters: '+repr({k: v for k, v in self.base.items() if k not in self.axes}),
                 'Enumerated grids: '+repr(self.axes),
                 f'Budget: {s.max_candidates} candidates, {s.max_seconds:g} s; {s.max_results} retained results.',
                 f'{"Complete finite domain" if self.complete else "PARTIAL search: "+self.reason} · {self.visited}/{self.total} visited · {self.generated} generated · {self.valid} valid · {self.matched} matching · {self.rejected} rejected · {self.elapsed:.3f} s',
                 'Ranking: ratio error %, then nominal XYZ bounding box volume, then XYZ lengths. No continuous or global optimum claim; only this finite domain.',
                 f'{len(self.proposals)} retained proposals'+(' · No results satisfy this finite search.' if not self.proposals else ''),
                 'Generator validation is not a motion interference check or a strength/load rating. Worm and strain wave remain concept models.']
        for n, p in enumerate(self.proposals, 1):
            lines.append(f'{n}. i={p.ratio:+.12g}; error={p.error_percent:.9g}%; XYZ={p.xyz} mm; changes={p.changes}')
        return '\n'.join(lines)


class Halt(Exception):
    pass


def search(family, base, axes, settings=None, cancel=None, progress=lambda message, fraction: None):
    """Enumerate in insertion order. A generator call is a non-preemptible unit."""
    settings = deepcopy(settings or Settings())
    settings.validate()
    if family not in FAMILIES:
        raise ValueError('A single gear has no independent transmission ratio. Select an assembly family.')
    # Preparation counts toward elapsed time; generation itself is cooperative.
    started = monotonic()
    if cancel is not None and cancel.is_set():
        # No selectable proposal exists, so canonicalizing the baseline is not
        # necessary. Preserve the caller's baseline only for this cancelled report.
        grids = {key: tuple(values) for key, values in axes.items()}
        return Result(family, deepcopy(base), grids, settings, prod(map(len, grids.values())),
                      elapsed=monotonic()-started, reason='cancelled')
    # Baseline generated once to make all default/derived options explicit.
    base = deepcopy(generate(family, deepcopy(base)).values)
    specs = {s[0]: s for s in variables(family, base)}
    grids = {}
    for key, values in axes.items():
        if key not in specs:
            raise ValueError(f'{key}: not an unlockable geometric variable.')
        values = tuple(values)
        if not values or len(values) > 1000:
            raise ValueError(f'{key}: use between 1 and 1000 discrete values.')
        spec = specs[key]
        grid = []
        for value in values:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or not spec[3] <= value <= spec[4]:
                raise ValueError(f'{key}: grid outside [{spec[3]}, {spec[4]}].')
            if key in INTEGER and int(value) != value:
                raise ValueError(f'{key}: integer grid required.')
            if value not in grid:
                grid.append(int(value) if key in INTEGER else value)
        grids[key] = tuple(grid)
    result = Result(family, base, grids, settings, prod(map(len, grids.values())))
    def check():
        if cancel is not None and cancel.is_set():
            raise Halt('cancelled')
        if monotonic()-started >= settings.max_seconds:
            raise Halt('time budget reached')
    try:
        for numbers in product(*grids.values()):
            check()
            if result.visited >= settings.max_candidates:
                raise Halt('candidate budget reached')
            candidate = dict(base, **dict(zip(grids, numbers)))
            result.visited += 1
            progress(f'Evaluating candidate {result.visited}/{result.total} · {result.generated} generated', result.visited/result.total)
            if not matches(estimated_ratio(family, candidate), settings):
                continue
            check()
            result.generated += 1
            try:
                design = generate(family, candidate)
                check()
                # Derived values are locked too: no silent module/bore/width/option changes.
                if any(design.values.get(k) != v for k, v in base.items() if k not in grids):
                    result.rejected += 1
                    continue
                if any(design.values.get(k) != v for k, v in zip(grids, numbers)):
                    result.rejected += 1
                    continue
                ratio = design.analysis['signed_ratio']
                result.valid += 1
                if not matches(ratio, settings):
                    continue
                minimum, maximum = nominal_bounds(design, check)
                xyz = tuple(b-a for a, b in zip(minimum, maximum))
                if any(length > limit for length, limit in zip(xyz, settings.max_xyz)):
                    continue
                changes = {k: (base[k], design.values[k]) for k in grids if base[k] != design.values[k]}
                # Grid values are deduplicated and every enumerated value must
                # survive generation unchanged, so distinct tuples cannot alias.
                result.matched += 1
                proposal = Proposal(deepcopy(design.values), ratio, abs(abs(ratio)-settings.target)/settings.target*100, minimum, maximum, changes)
                result.proposals.append(proposal)
                result.proposals.sort(key=lambda p: p.sort_key)
                del result.proposals[settings.max_results:]
            except (ValueError, KeyError, OverflowError, ZeroDivisionError):
                result.rejected += 1
            finally:
                # Few expensive candidates still report each generator return;
                # the GTK controller throttles these notifications to ~10 Hz.
                progress(f'{result.visited}/{result.total} candidates · {result.generated} generated · {result.valid} valid', result.visited/result.total)
    except Halt as error:
        result.reason = str(error)
    result.elapsed = monotonic()-started
    progress('Search complete' if result.complete else 'Partial search · '+result.reason, result.visited/result.total)
    return result
