# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Exact working transverse backlash inverse for generated external fixed-axis pairs.

Lengths are mm; input angles are degrees. No GTK, document mutation or small-angle
substitution. Discrete surface checks retain their own coverage and limits.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from math import acos, cos, isfinite, radians, tan
from pathlib import Path
from threading import Event
import json
from geometry import generate, get_specs, validate
from interference import Settings, analyze


def _number(value, name, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(name+' must be finite.')
    if value < 0 or (positive and value == 0):
        raise ValueError(name+(' must be positive.' if positive else ' must be nonnegative.'))
    return float(value)


def working_backlash(reference_center_mm, transverse_pressure_deg, nominal_backlash_mm, extra_mm):
    """Independent scalar form of engineering.mesh's exact forward relation."""
    a0 = _number(reference_center_mm, 'Reference centre distance', True)
    alpha = _number(transverse_pressure_deg, 'Transverse pressure angle', True)
    if alpha >= 90:
        raise ValueError('Transverse pressure angle must be less than 90 degrees.')
    j0 = _number(nominal_backlash_mm, 'Nominal pair backlash')
    extra = _number(extra_mm, 'Centre distance increase')
    at = radians(alpha)
    if extra == 0:
        return j0
    a = a0+extra
    if not isfinite(a):
        raise ValueError('Centre distance exceeds the finite numerical domain.')
    aw = acos(a0*cos(at)/a)
    value = j0*a/a0+2*a*((tan(aw)-aw)-(tan(at)-at))
    if not isfinite(value):
        raise ValueError('Working backlash exceeds the finite numerical domain.')
    return value


def inverse_distance(reference_center_mm, transverse_pressure_deg, nominal_backlash_mm,
                     desired_backlash_mm, minimum_extra_mm=0., maximum_extra_mm=5.):
    """Unique root in the bounded nonnegative centre increase domain, in mm."""
    target = _number(desired_backlash_mm, 'Desired working transverse tangential backlash')
    low = _number(minimum_extra_mm, 'Minimum centre increase')
    high = _number(maximum_extra_mm, 'Maximum centre increase')
    if high < low:
        raise ValueError('Centre distance bounds are reversed.')
    forward = lambda extra: working_backlash(reference_center_mm, transverse_pressure_deg,
                                             nominal_backlash_mm, extra)
    lower, upper = forward(low), forward(high)
    rounding = 1e-12*max(1., abs(lower), abs(upper))
    if target < lower-rounding:
        raise ValueError(f'Desired backlash is below the reachable baseline {lower:.12g} mm; negative centre increase is unsupported.')
    if target > upper+rounding:
        raise ValueError(f'Desired backlash exceeds {upper:.12g} mm at the parameter limit {high:g} mm.')
    if target <= lower:
        return low
    if target >= upper:
        return high
    for _ in range(90):
        middle = (low+high)/2
        if middle in (low, high):
            break
        if forward(middle) < target:
            low = middle
        else:
            high = middle
    return (low+high)/2


@dataclass
class Proposal:
    source_values: dict
    desired_backlash_mm: float
    source_center_mm: float
    source_backlash_mm: float
    values: dict = field(default_factory=dict)
    status: str = 'rejected'
    reason: str = ''
    center_distance_mm: float | None = None
    working_backlash_mm: float | None = None
    usable_contact_total: float | None = None
    interference: dict | None = None
    revision: object = None
    application: str = 'proposed'
    applied_revision: object = None
    design: object = field(default=None, repr=False)

    @property
    def applicable(self):
        return self.status == 'ready' and self.design is not None

    def payload(self):
        # Never deep-copy/serialize a full surface assembly merely to export its query.
        return {key: deepcopy(value) for key, value in vars(self).items() if key != 'design'}

    def text(self):
        lines = ['RatioLab · inverse working backlash', f'Revision: {self.revision}',
                 f'Application: {self.application}; applied revision: {self.applied_revision}',
                 'Parallel external pair only · spur / helical / double helix',
                 'Target: transverse circumferential (tangential) working backlash, not normal or radial backlash.',
                 f'Desired: {self.desired_backlash_mm:.12g} mm',
                 f'Current working backlash: {self.source_backlash_mm:.12g} mm',
                 f'Current centre distance: {self.source_center_mm:.12g} mm',
                 f'{self.status.upper()}: {self.reason}']
        if self.center_distance_mm is not None:
            lines += [f'Proposed centre distance: {self.center_distance_mm:.12g} mm · change {self.center_distance_mm-self.source_center_mm:+.12g} mm',
                      f'Centre increase from reference: {self.values["center_extra"]:.12g} mm',
                      f'Verified forward backlash: {self.working_backlash_mm:.12g} mm',
                      f'Usable involute total contact ratio: {self.usable_contact_total:.12g}']
        lines += ['Same-member boundary contacts remain unresolved interfaces; they are listed separately from suspect mesh intersections.',
                  'Discrete samples only; no continuous clearance, loaded-contact, strength, durability or full ISO conformity claim.']
        if self.interference is not None:
            from interference import Analysis
            lines += ['', Analysis(**deepcopy(self.interference)).text()]
        return '\n'.join(lines)+'\n'


def _source(design):
    if design is None or design.family != 'parallel' or design.values.get('variant') not in ('spur', 'helical', 'double'):
        raise ValueError('Only generated parallel external spur, helical and double-helical pairs support centre adjustment.')
    values = deepcopy(design.values)
    if validate('parallel', deepcopy(values)) != values:
        raise ValueError('Current parameters are not normalized; regenerate before solving.')
    meshes = design.analysis.get('meshes', [])
    if len(meshes) != 1 or meshes[0].get('internal'):
        raise ValueError('A single external generated mesh is required.')
    return values, meshes[0]


def _check_candidate(design, values, target):
    if design.values != values:
        raise ValueError('Candidate normalization changed parameters; regenerate the source before solving.')
    _, mesh = _source(design)
    independent = working_backlash(mesh['reference_center_mm'], mesh['gear1']['alpha_t'],
                                   values['backlash'], values['center_extra'])
    tolerance = 1e-10*max(1., target)
    if abs(mesh['working_pair_backlash_mm']-target) > tolerance or abs(independent-target) > tolerance:
        raise ValueError('Generated forward backlash does not reproduce the requested target.')
    if not isfinite(mesh['profile_contact_total']) or mesh['profile_contact_total'] < 1:
        raise ValueError('Usable involute total contact ratio is below 1 after root trimming/blending; proposal cannot be applied.')
    return mesh


def interference_blocker(analysis):
    """Conservative application policy; expected labels never hide intersections."""
    if analysis.get('cancelled'):
        return 'Cancelled; no applicable proposal.'
    if not analysis.get('coverage_complete') or analysis.get('issues'):
        return 'Incomplete or unsupported discrete interference coverage; no applicable proposal.'
    for row in analysis.get('rows', []):
        if row['kind'] in ('Intersection', 'Containment'):
            return 'Discrete interference found '+row['kind'].lower()+'; review the report.'
        if row['kind'] != 'Separated' and not (row['kind'] == 'Boundary contact / unresolved' and
                                               row.get('expected', '').startswith('Same kinematic member')):
            return 'Unresolved contact outside a same-member interface; review the discrete report.'
    return None


def solve(design, desired_backlash_mm, settings=None, cancel=None, progress=lambda message, fraction: None):
    """Generate, verify and discretely inspect a copied candidate; never mutate source.

    Source must already be valid and normalized. The reference-distance pair need
    not itself be usable; an increased current distance may cure base interference.
    """
    values, mesh = _source(design)
    target = _number(desired_backlash_mm, 'Desired working transverse tangential backlash')
    settings = settings or Settings(step_degrees=30, max_seconds=60)
    settings.validate()
    cancel = cancel or Event()
    result = Proposal(values, target, mesh['center_distance_mm'], mesh['working_pair_backlash_mm'])
    if cancel.is_set():
        result.status, result.reason = 'cancelled', 'Cancelled before generation.'
        return result
    bounds = next(spec[3:5] for spec in get_specs('parallel', values['variant']) if spec[0] == 'center_extra')
    extra = inverse_distance(mesh['reference_center_mm'], mesh['gear1']['alpha_t'], values['backlash'], target, *bounds)
    if abs(target-mesh['working_pair_backlash_mm']) <= 1e-12*max(1., target):
        # Keep a no-change query bit-for-bit stable instead of creating an Undo
        # step for floating roundoff in inverse/forward trigonometric evaluation.
        extra = values['center_extra']
    result.values = deepcopy(values)
    result.values['center_extra'] = extra
    progress('Generating centre-distance proposal…', 0.)
    try:
        candidate = generate('parallel', deepcopy(result.values))
        verified = _check_candidate(candidate, result.values, target)
    except ValueError as error:
        result.reason = 'Generated candidate rejected: '+str(error)
        return result
    result.center_distance_mm = verified['center_distance_mm']
    result.working_backlash_mm = verified['working_pair_backlash_mm']
    result.usable_contact_total = verified['profile_contact_total']
    if cancel.is_set():
        result.status, result.reason = 'cancelled', 'Cancelled after generation.'
        return result
    result.design = candidate
    report = analyze(candidate, settings=settings, cancel=cancel, progress=progress)
    result.interference = asdict(report)
    blocker = interference_blocker(result.interference)
    if blocker:
        result.status = 'cancelled' if cancel.is_set() else 'rejected'
        result.reason = blocker
    else:
        result.status = 'ready'
        count = sum(row['kind'] == 'Boundary contact / unresolved' for row in report.rows)
        result.reason = f'Generated forward result verified; complete discrete coverage. {count} same-member boundary interfaces remain unresolved.'
        result.design = candidate
    return result


def revalidate(proposal):
    """Fresh generator/normalization/forward checks before intentional document Apply."""
    if not proposal.applicable or proposal.interference is None or interference_blocker(proposal.interference):
        raise ValueError('No current fully checked proposal to apply.')
    expected = deepcopy(proposal.source_values)
    expected['center_extra'] = proposal.values.get('center_extra')
    if expected != proposal.values:
        raise ValueError('Proposal changes parameters other than centre distance.')
    checked = generate('parallel', deepcopy(proposal.values))
    _check_candidate(checked, proposal.values, proposal.desired_backlash_mm)
    if checked.values != proposal.design.values:
        raise ValueError('Validated proposal no longer matches the preview.')
    return checked


def export_proposal(proposal, target):
    """Read-only query transaction, retaining source/target/application and coverage."""
    from export_transaction import directory
    with directory(target) as staging:
        (staging/'backlash.txt').write_text(proposal.text(), encoding='utf-8')
        (staging/'backlash.json').write_text(json.dumps(proposal.payload(), indent=2, allow_nan=False)+'\n', encoding='utf-8')
    return Path(target)
