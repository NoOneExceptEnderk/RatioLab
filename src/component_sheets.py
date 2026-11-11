# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Company-authored component documents, separate from nominal geometry.

Only existing construction metadata supplies automatic inspection dimensions.
Limits are absolute values in mm, entered by the company; no pass/fail is inferred.
"""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json
from math import degrees
import re

FORMAT = 'ratiolab-component-sheets/1'
COMPANY_FIELDS = dict(company='Company', customer='Customer', order='Order / job', author='Prepared by')
PART_FIELDS = dict(code='Part code', revision='Drawing revision', drawing='Drawing reference',
    lot='Lot / batch', quantity='Lot quantity', material='Material', stock='Stock / blank',
    treatment='Heat treatment', finish='Surface finish', operations='Operations defined by company',
    notes='Production notes')
CHECK_FIELDS = ('id', 'label', 'nominal', 'unit', 'lower', 'upper', 'method', 'instrument', 'datum')
MAX_CHECKS = 40


def text(value):
    if not isinstance(value, str) or len(value) > 4000 or any(
            ord(c) < 32 and c not in '\n\t' for c in value):
        raise ValueError('Sheet fields must be text, at most 4000 characters without control codes.')
    return value


def decimal(value):
    try:
        number = Decimal(text(value).strip().replace(',', '.'))
    except (InvalidOperation, ValueError):
        raise ValueError('Inspection dimensions and limits must be finite decimal numbers.') from None
    if not number.is_finite() or abs(number) > Decimal('1e12'):
        raise ValueError('Inspection dimensions and limits must be finite and at most 1e12 in magnitude.')
    return number


def normalize(value=None):
    if value is None or value == {}:
        return {}
    if not isinstance(value, dict) or set(value) != {'format', 'company', 'components'} or value['format'] != FORMAT:
        raise ValueError('Invalid component sheet format.')
    def fields(obj, allowed):
        if not isinstance(obj, dict) or set(obj) - set(allowed):
            raise ValueError('Invalid component sheet fields.')
        return {key: text(v) for key, v in obj.items()}
    company = fields(value['company'], COMPANY_FIELDS)
    components = value['components']
    if not isinstance(components, dict) or len(components) > 500:
        raise ValueError('Invalid component sheet collection (maximum 500).')
    result = {}
    for key, record in components.items():
        text(key)
        if not isinstance(record, dict) or set(record) != {'fingerprint', 'fields', 'checks'}:
            raise ValueError('Invalid component sheet record.')
        if not isinstance(record['fingerprint'], str) or not re.fullmatch('[0-9a-f]{64}', record['fingerprint']):
            raise ValueError('Invalid component geometry fingerprint.')
        checks = record['checks']
        if not isinstance(checks, list) or len(checks) > MAX_CHECKS:
            raise ValueError('A sheet supports at most 40 inspection characteristics.')
        ids = set()
        normalized = []
        for check in checks:
            row = fields(check, CHECK_FIELDS)
            if set(row) != set(CHECK_FIELDS) or not row['id'] or row['id'] in ids or not row['label'].strip():
                raise ValueError('Inspection characteristics need unique identifiers and a name.')
            ids.add(row['id'])
            if row['id'].startswith('auto:') and row['unit'] != 'mm':
                raise ValueError('Automatic inspection dimensions use mm.')
            for field in ('nominal', 'lower', 'upper'):
                if row[field].strip():decimal(row[field])
            if row['lower'].strip() and row['upper'].strip() and decimal(row['lower']) > decimal(row['upper']):
                raise ValueError('The lower inspection limit exceeds the upper limit.')
            normalized.append(row)
        result[key] = dict(fingerprint=record['fingerprint'], fields=fields(record['fields'], PART_FIELDS), checks=normalized)
    return dict(format=FORMAT, company=company, components=result)


def component_key(design, index):
    if type(index) is not int or not 0 <= index < len(design.parts):
        raise ValueError('Select one existing component.')
    return json.dumps([design.family, design.parts[index].name], ensure_ascii=False)


def fingerprint(design, index):
    from motion import SPEED_KEYS
    from precise_numbers import SOURCE_KEY
    component_key(design, index)
    values = {k: v for k, v in design.values.items() if k not in SPEED_KEYS and k != SOURCE_KEY}
    sources = {k: v for k, v in design.values.get(SOURCE_KEY, {}).items() if k not in SPEED_KEYS}
    if sources:values[SOURCE_KEY] = sources
    identity = dict(family=design.family, parameters=values, part=design.parts[index].name, position=index+1)
    return hashlib.sha256(json.dumps(identity, sort_keys=True, allow_nan=False).encode()).hexdigest()


def number(value):
    # Display decimals, not a manufacturing tolerance or a rounded acceptance limit.
    return format(float(value), '.12g')


def automatic_checks(part):
    rows = []
    def add(key, label, value, method=''):
        rows.append(dict(id='auto:'+key, label=label, nominal=number(value), unit='mm',
            lower='', upper='', method=method, instrument='', datum=''))
    if not part.mesh:
        length = max(s['z'] for s in part.stations)-min(s['z'] for s in part.stations) if part.stations else part.width
        add('width', 'Axial length (local Z)', length)
    # CircleProfile carries explicit construction provenance. Never fit a circle
    # to an arbitrary polygon and turn the fit into a nominal diameter.
    from geometry import CircleProfile
    for i, hole in enumerate(part.holes):
        if isinstance(hole, CircleProfile) and hole.intact():
            add('hole:'+str(i), f'Circular hole {i+1} diameter', 2*hole.radius)
    profile = part.profile_metadata.get('tooth_profile', {})
    geometry = profile.get('measurement_geometry', {})
    if geometry:
        add('tip', 'Internal tooth tip diameter' if geometry.get('internal') else 'Tooth tip diameter', 2*geometry['tip_radius_mm'])
    span = profile.get('wildhaber_span', {})
    if span.get('status') == 'ok':
        k = span['recommended_k']
        chosen = next(row for row in span['usable_spans'] if row['k'] == k)
        add('span', f'Wildhaber span over {k} teeth', chosen['span_mm'], f'Symmetric flat jaws; k = {k}')
    gauge = profile.get('over_gauges', {})
    if gauge.get('status') == 'ok':
        add('gauges', 'Dimension over / between gauges', gauge['dimension_mm'],
            f"{gauge['gauge_type']}; diameter {number(gauge['gauge_diameter_mm'])} mm; {gauge['dimension_kind']}")
    return rows


def draft(design, index, metadata=None):
    metadata = normalize(metadata)
    old = metadata.get('components', {}).get(component_key(design, index))
    current = fingerprint(design, index)
    auto = automatic_checks(design.parts[index])
    saved = {r['id']: r for r in old['checks']} if old else {}
    checks = []
    for row in auto:
        if row['id'] in saved:
            for key in ('lower', 'upper', 'instrument', 'datum'):
                row[key] = saved[row['id']][key]
            # Nominal and contact method always come from current geometry.
            if not row['method']:row['method'] = saved[row['id']]['method']
        checks.append(row)
    checks += [deepcopy(r) for r in saved.values() if not r['id'].startswith('auto:')]
    return dict(company=deepcopy(metadata.get('company', {})), fields=deepcopy(old['fields']) if old else {},
                checks=checks, stale=bool(old and old['fingerprint'] != current))


def apply(design, index, metadata, company, fields, checks):
    result = normalize(metadata) or dict(format=FORMAT, company={}, components={})
    result['company'] = deepcopy(company)
    # Reconstruct automatic values even when called outside the GUI.
    auto = {r['id']: r for r in automatic_checks(design.parts[index])}
    checks = deepcopy(checks)
    if {r['id'] for r in checks if r['id'].startswith('auto:')} != set(auto):
        raise ValueError('Automatic characteristics do not match the current component.')
    for row in checks:
        if row['id'] in auto:
            for key in ('label', 'nominal', 'unit'):
                row[key] = auto[row['id']][key]
            if auto[row['id']]['method']:row['method'] = auto[row['id']]['method']
    result['components'][component_key(design, index)] = dict(
        fingerprint=fingerprint(design, index), fields=deepcopy(fields), checks=checks)
    return normalize(result)


def report(design, index, metadata, project_name='', document_revision=''):
    metadata = normalize(metadata)
    record = metadata.get('components', {}).get(component_key(design, index))
    if record is None or record['fingerprint'] != fingerprint(design, index):
        raise ValueError('Review and apply the component sheet for the current geometry before exporting.')
    part = design.parts[index]
    # Rebuild calculated values: saved JSON cannot override nominal dimensions.
    current = draft(design, index, metadata)
    profile = part.profile_metadata.get('tooth_profile', {})
    geometry = profile.get('measurement_geometry', {})
    tool = profile.get('tool', {})
    nominal = []
    for label, value in [('Teeth', geometry.get('teeth')), ('Normal module [mm]', tool.get('normal_module')),
            ('Profile shift coefficient', tool.get('shift')), ('Helix angle magnitude [deg]', geometry.get('helix_angle_abs_deg'))]:
        if value is not None:nominal.append((label, number(value)))
    if 'alpha_normal' in tool:nominal.append(('Normal pressure angle [deg]', number(degrees(tool['alpha_normal']))))
    if 'reference_radius_mm' in geometry:
        nominal.append(('Reference diameter (theoretical) [mm]', number(2*geometry['reference_radius_mm'])))
    return dict(format=FORMAT, family=design.family, source_position=index+1, source_name=part.name,
        project=project_name, document_revision=str(document_revision), fingerprint=record['fingerprint'],
        company=metadata['company'], fields=record['fields'], checks=current['checks'],
        profile=deepcopy(profile), nominal=nominal,
        outline=deepcopy(part.stations[0]['outer'] if part.stations else part.outer),
        holes=deepcopy(part.stations[0].get('holes', part.holes) if part.stations else part.holes),
        role=part.role, purchased=bool(part.catalog_code or part.procurement))
