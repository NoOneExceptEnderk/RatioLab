# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Diagnostics from validation to presentation, independent of message wording.

Field names belong to the producing operation. Application adapters explicitly
remap them to project keys; neither transport nor UI parses human messages.
"""
import json
from contextlib import contextmanager

FORMAT = 'ratiolab.diagnostic/1'

# UI copy is keyed by constraint identity, never by the wording of an error.
SHORT = {
    'number.required': 'Enter a valid number.',
    'number.incomplete': 'Enter a valid number.',
    'number.domain': 'Enter a valid number.',
    'number.integer': 'Use a whole number.',
    **dict.fromkeys(('bore.root', 'bore.hub', 'planetary.bore_root',
                     'worm.bore_root', 'worm.wheel_bore', 'harmonic.output_bore'), 'Bore too large.'),
    'backlash.module': 'Reduce backlash or increase module.',
    'groove.width': 'Reduce groove or increase width.',
    'groove.positive': 'Groove must be greater than zero.',
    'planetary.spacing': 'Adjust tooth counts or planet count.',
    'planetary.overlap': 'Reduce planet size or count.',
    'planetary.bore_minimum': 'Increase bore diameter.',
    'planetary.rim': 'Increase ring thickness.',
    'parallel.reduction': 'Wheel teeth must exceed pinion teeth.',
    'harmonic.even_teeth': 'Use an even tooth count.',
    'harmonic.wall': 'Reduce wall thickness or bore.',
    'harmonic.diaphragm': 'Reduce diaphragm or increase length.',
    'harmonic.wave_clearance': 'Reduce bore or bearing thickness.',
    'cycloidal.eccentricity': 'Reduce eccentricity or increase radius.',
    'cycloidal.cusps': 'Reduce roller radius or eccentricity.',
    'cycloidal.rollers_overlap': 'Reduce roller size or count.',
    'cycloidal.output_material': 'Reduce holes or adjust their radius.',
    'cycloidal.output_overlap': 'Reduce hole size or pin count.',
    'cycloidal.input_shaft': 'Reduce shaft diameter or eccentricity.',
    'cycloidal.bearing_seat': 'Increase eccentric seat diameter.',
    'cycloidal.output_flange': 'Reduce shaft or pin diameters.',
    'worm.journal': 'Adjust journal diameter.',
}


def compact(error, field=None):
    """Short UI copy; numerical limits come exclusively from the validator.

    Keep full round-trip numbers: rounding an exclusive upper limit upwards
    could suggest a value which the model actually rejects.
    """
    if not isinstance(error, ParameterError):return str(error)
    if field is None and len(error.limits)==1:field=next(iter(error.limits))
    limit=error.limits.get(field, {})
    upper,lower=limit.get('upper'),limit.get('lower')
    violation=limit.get('violation')
    def number(value):
        return str(int(value)) if value==int(value) else str(value)
    if upper is not None and (lower is None or violation=='upper'):
        template='Too large. Below: {value}.' if limit.get('upper_exclusive') else 'Too large. Maximum: {value}.'
        return template.replace('{value}',number(upper))
    if lower is not None and (upper is None or violation=='lower'):
        template='Too small. Above: {value}.' if limit.get('lower_exclusive') else 'Too small. Minimum: {value}.'
        return template.replace('{value}',number(lower))
    if lower is not None and upper is not None:
        return 'Allowed: {arg1}–{arg2}.'.replace('{arg1}',number(lower)).replace('{arg2}',number(upper))
    return SHORT.get(error.constraint,str(error))


class ParameterError(ValueError):
    def __init__(self, constraint, fields, message, remedy='', *, kind='geometry', limits=None):
        self.constraint = constraint
        self.fields = tuple(dict.fromkeys(fields))
        self.message = message
        self.remedy = remedy
        self.kind = kind
        self.code = 'invalid_parameters' if kind == 'input' else 'invalid_geometry'
        self.limits = dict(limits or {})
        super().__init__('\n'.join(filter(None, (message, remedy))))

    def record(self):
        return dict(format=FORMAT, code=self.code, kind=self.kind,
                    constraint=self.constraint, fields=list(self.fields),
                    message=self.message, remedy=self.remedy, limits=self.limits,
                    summary=compact(self), field_messages={key:compact(self,key) for key in self.fields})


class EngineFailure(RuntimeError):
    code = 'internal_error'
    kind = 'internal'


def from_kernel(record):
    """Decode an explicit envelope; legacy errors remain unassigned to fields."""
    if isinstance(record, str):
        try:
            candidate = json.loads(record)
        except (ValueError, TypeError):
            candidate = None
        record = candidate if isinstance(candidate, dict) and (candidate.get('format') == FORMAT or isinstance(candidate.get('code'), str)) else dict(message=record)
    if record.get('format') == FORMAT:
        return ParameterError(record['constraint'], record['fields'], record['message'],
                              record.get('remedy', ''), kind=record.get('kind', 'geometry'),
                              limits=record.get('limits'))
    if record.get('code') in ('internal_error', 'invalid_buffer', 'invalid_utf8'):
        return EngineFailure(record.get('message', 'Geometry calculation failed.'))
    return ValueError(record.get('message', 'Geometry calculation failed.'))


def record(error):
    if isinstance(error, ParameterError):
        return error.record()
    internal = not isinstance(error, ValueError)
    return dict(code=getattr(error, 'code', 'internal_error' if internal else 'invalid_parameters'),
                kind='internal' if internal else 'geometry', fields=[], message=str(error))


@contextmanager
def field_context(mapping):
    """Translate operation parameter identities at the actual call site."""
    try:
        yield
    except ParameterError as error:
        fields = [mapping[key] for key in error.fields if key in mapping]
        limits = {mapping[key]: value for key, value in error.limits.items() if key in mapping}
        raise ParameterError(error.constraint, fields, error.message, error.remedy,
                             kind=error.kind, limits=limits) from error
