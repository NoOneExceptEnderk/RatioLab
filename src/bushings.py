# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Nominal seated sleeves and their mating assembly interfaces."""
from math import isclose

from catalog import RollerBushing, RING_ROLLER_BUSHINGS, ROLLER_BUSHING_SOURCE
from parameter_errors import ParameterError


BUSHINGS = dict(RING_ROLLER_BUSHINGS)
for code, d, D, B, installed in (
    ('GSM-0608-04', 6, 8, 4, 6.020),
    ('GSM-0608-06', 6, 8, 6, 6.020),
    ('GSM-0810-05', 8, 10, 5, 8.025),
    ('GSM-0810-08', 8, 10, 8, 8.025),
    ('GSM-1012-06', 10, 12, 6, 10.025),
    ('GSM-1214-06', 12, 14, 6, 12.032),
):
    BUSHINGS[code] = RollerBushing(code, d, D, B, installed)

FIELDS = {
    'planetary': {'planet_bushing': 'Planet pin bushings'},
    'wolfrom': {'compound_bushing': 'Compound planet bushings'},
    'differential': {'spider_bushing': 'Differential spider bushing'},
    'cycloidal': {'output_pin_sleeve': 'Output pin sleeves', 'eccentric_bushing': 'Eccentric bushings'},
    'parallel': {'shaft_bushing': 'Output shaft bushings'},
    'internal': {'shaft_bushing': 'Pinion shaft bushings'},
    'spur': {'shaft_bushing': 'Gear shaft bushings'},
    'helical': {'shaft_bushing': 'Gear shaft bushings'},
    'double': {'shaft_bushing': 'Gear shaft bushings'},
    'worm': {'worm_bushing': 'Worm journal bushings'},
}


def fields(family):
    for key, label in FIELDS.get(family, {}).items():
        if key == 'output_pin_sleeve':
            choices = {'none': 'Solid pins', 'sleeved': 'Pins with replaceable sleeves'}
        else:
            choices = {'none': 'Standard construction'}
            for code, bushing in BUSHINGS.items():
                if key == 'eccentric_bushing' and bushing.d < 8:
                    continue
                choices[code] = bushing.label
        yield key, label, choices


def options(family, supplied):
    result = {}
    for key, _, choices in fields(family):
        if key not in supplied:
            continue
        value = supplied[key]
        if not isinstance(value, str) or value not in choices:
            raise ParameterError('bushing.selection', (key,), 'Select a support from the list.', kind='input')
        result[key] = value
    return result


def unavailable(key, values):
    mode = values.get('bearing_mode', 'manual')
    if key == 'planet_bushing' and mode == 'gear':
        return 'Planet bore already uses ball bearings.'
    if key == 'spider_bushing' and values.get('configuration', 'wrist') != 'classic':
        return 'Available for the classic differential.'
    if key == 'eccentric_bushing':
        if values.get('eccentric_design') == 'fdm_bolted':
            return 'The printed shaft uses its dedicated 6804 bearings.'
        if mode == 'gear':
            return 'The eccentric already uses ball bearings.'
    if key == 'shaft_bushing' and mode != 'manual':
        return 'Set Standard fit to free dimensions to use shaft bushings.'
    return ''


def selected(values, key):
    return None if unavailable(key, values) else BUSHINGS.get(values.get(key))


def error(key, message, *fields):
    return ParameterError('bushing.geometry', (key, *fields), message)


def sleeve(design, bushing, name, z, *, center=(0, 0), frame=(), role='support', port=None, bom_kind='shaft_bushing'):
    from geometry import Part, circle
    from hardware import buy

    part = Part(name, circle(bushing.D/2), [circle(bushing.installed_bore_min/2)],
                bushing.B, z, center, frame=frame, role=role, port=dict(port or {}),
                color=(.59, .41, .24), bom_kind=bom_kind)
    buy(part, f'igus {bushing.code}', 'iglide G cylindrical bushing',
        f'{bushing.d:g} × {bushing.D:g} × {bushing.B:g} mm', 'igus', ROLLER_BUSHING_SOURCE, '')
    design.parts.append(part)
    return part


def require_length(bushing, length, key, field):
    if bushing.B > length + 1e-9:
        raise error(key, 'Bushing is longer than the available seat. Select a shorter bushing or lengthen the seat.', field)


def require_wall(part, bushing, key, *fields):
    from shaft_connections import _edge_radius

    root = _edge_radius(part.outer)
    if part.double:
        root = min(root, part.core_radius)
    if part.stations:
        root = min(root, *(_edge_radius(station['outer']) for station in part.stations))
    if root - bushing.D/2 < .5:
        raise error(key, 'Bushing seat leaves less than 0.5 mm of wall. Select a smaller bushing or enlarge the hub.', *fields)


def seat(part, bushing):
    from geometry import circle

    hole = circle(bushing.D/2)
    part.holes[0:1] = [hole]
    for station in part.stations:
        station['holes'][0:1] = [hole]


def supports(design):
    """Add blocks at the ends of an existing round shaft or worm journals."""
    from geometry import Part, circle, circle_info
    from motion import part_axis

    family, values = design.family, design.values
    key = 'worm_bushing' if family == 'worm' else 'shaft_bushing'
    bushing = selected(values, key)
    if not bushing:
        return
    if family == 'worm':
        shaft = next(p for p in design.parts if p.name.startswith('Screw_'))
        length = values['journal_length']
        require_length(bushing, length, key, 'journal_length')
        diameter_key = 'journal_diameter'
        diameter = values[diameter_key]
        origin, axis = part_axis(shaft)
        frame = ((-shaft.width/2, origin[1], origin[2]), (0, 0, -1), (0, 1, 0), axis)
        center = (0, 0)
        seats = ((length-bushing.B)/2, shaft.width-length+(length-bushing.B)/2)
    else:
        from geometry import PARALLEL_MULTISTAGE_VARIANTS
        if family in ('spur', 'helical', 'double'):
            gear = design.parts[0]
            diameter_key = 'bore'
            diameter = values[diameter_key]
            shaft = next((p for p in design.parts if p.name.startswith('Shaft_')), None)
            if shaft is None and diameter > 0:
                shaft = Part('Shaft_gear', circle(diameter/2), [], gear.width+2*(bushing.B+6),
                             gear.z-bushing.B-6, role='support')
                design.parts.append(shaft)
        elif family == 'internal':
            shaft = next((p for p in design.parts if p.name in ('Shaft_input', 'Shaft_lato_A')), None)
            diameter_key = 'bore'
        elif values['variant'] in PARALLEL_MULTISTAGE_VARIANTS:
            shaft = next((p for p in design.parts if p.name.startswith('Shaft_') and p.port['role'] == 'output'), None)
            diameter_key = 'bore' if values['io_scheme'] == 'reverse' else 'output_bore'
        else:
            reverse = values['io_scheme'] == 'reverse'
            names = ('Shaft_input', 'Shaft_lato_A') if reverse else ('Shaft_output', 'Shaft_lato_B')
            shaft = next((p for p in design.parts if p.name in names), None)
            diameter_key = 'bore' if reverse else 'output_bore'
        if shaft is None:
            raise error(key, 'Create a round shaft before adding its bushings.', diameter_key)
        journal = circle_info(shaft.outer)
        if journal is None or shaft.holes:
            raise error(key, 'The support requires a round shaft journal.', diameter_key)
        diameter = 2*journal[2]
        center, frame = shaft.center, shaft.frame
        start, end = shaft.z, shaft.z+shaft.width
        occupied = [p for p in design.parts if p is not shaft and p.center == center
                    and p.frame == frame and (p.role == 'gear' or p.role == 'support'
                                             or p.name.startswith('Interface_'))]
        # The selected shaft may have ring grooves and keyways. Keep the new
        # seats outside the entire central stack and on plain journal material.
        first = min((p.z for p in occupied if p.z < end and p.z+p.width > start), default=(start+end)/2)
        last = max((p.z+p.width for p in occupied if p.z < end and p.z+p.width > start), default=(start+end)/2)
        gap = .5
        seats = (first-gap-bushing.B, last+gap)
        if any(z < shaft.z+op['z1']-1e-9 and shaft.z+op['z0'] < z+bushing.B-1e-9
               for z in seats for op in shaft.machining):
            raise error(key, 'Bushing seat overlaps shaft machining. Select a shorter bushing or change the shaft hardware.')
        new_start = min(start, seats[0]-.5)
        new_end = max(end, seats[1]+bushing.B+.5)
        if new_start < start or new_end > end:
            extension = start-new_start
            if shaft.stations:
                for station in shaft.stations:
                    station['z'] += extension
                if extension:
                    shaft.stations.insert(0, dict(z=0., outer=circle(diameter/2, len(shaft.stations[0]['outer'])), holes=[]))
                if new_end > end:
                    shaft.stations.append(dict(z=new_end-new_start, outer=circle(diameter/2, len(shaft.stations[-1]['outer'])), holes=[]))
            for operation in shaft.machining:
                operation['z0'] += extension
                operation['z1'] += extension
            shaft.z, shaft.width = new_start, new_end-new_start

    if not isclose(diameter, bushing.d, abs_tol=1e-8):
        raise error(key, f'Set the journal diameter to {bushing.d:g} mm or choose a matching bushing.', diameter_key)
    for end, z in zip(('lower', 'upper'), seats):
        sleeve(design, bushing, 'Bushing_shaft_'+end, z, center=center, frame=frame,
               bom_kind='worm_bushing' if family == 'worm' else 'shaft_bushing')
        design.parts.append(Part('BushingBlock_'+end, circle(bushing.D/2+3),
                                [circle(bushing.D/2)], bushing.B, z, center, frame=frame, role='housing',
                                bom_kind='bushing_block'))
    design.analysis['shaft_bushings'] = dict(part=shaft.name, code=bushing.code, count=2,
        journal_diameter_mm=diameter, seat_diameter_mm=bushing.D, length_mm=bushing.B)
    design.requirements.append('Shaft bushings: align and secure the two blocks to the frame. Define shaft finish, seat fits and separate axial restraint for the operating thrust.')
