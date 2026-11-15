# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Construction rows and CAD references for the interactive bill of materials."""
from collections import Counter
from numbers import Real
import re

from geometry import FAMILIES, VARIANTS, circle_info


# Part kinds follow the construction that generated the item. A purchased
# component also retains its existing catalog identity and nominal dimensions.
KINDS = {
    'ring_bushing': ('Roller bushings', 'Ring rollers', 'Each bushing sits inside one roller shell.',
                     'Define the shell fit, pin attachment and axial retention.'),
    'ring_bearing': ('Ring roller bearings', 'Ring rollers', 'Each bearing forms a roller at one pin and disc.',
                     'Define the pin fit and retain the bearing at its inner ring.'),
    'ring_shell': ('Roller shells', 'Ring rollers', 'The shell contacts the disc and seats the bushing.',
                   'Define the bushing seat and roller retention.'),
    'ring_pin': ('Ring pins', 'Ring rollers', 'The ring pin carries the rollers at its position.',
                 'Define how the pin is fixed to the ring.'),
    'output_pin': ('Flange pins', 'Pin flange', 'The flange pins engage the orbiting disc stack.',
                    'Define the attachment to the flange.'),
    'output_sleeve': ('Output pin sleeves', 'Pin flange', 'The sleeve provides the contact surface against the disc.',
                       'Define the sleeve fit and axial retention on the pin.'),
    'eccentric_bushing': ('Eccentric bushings', 'Eccentrics', 'The bushing sits between an eccentric and its disc.',
                          'Define the seat, journal fit and axial retention.'),
    'eccentric_bearing': ('Eccentric bearings', 'Eccentrics', 'The bearing position is between an eccentric and its disc.',
                          'Complete the bearing seat and axial retention.'),
    'eccentric_bolt': ('Eccentric stack screws', 'Printed eccentric shaft', 'The two through screws connect the printed eccentric stack.',
                       'Complete the input coupling and verify the stack fit in CAD.'),
    'eccentric_washer': ('Eccentric stack washers', 'Printed eccentric shaft', 'A washer is modelled at each end of each through screw.',
                         'Complete the input coupling and verify the stack fit in CAD.'),
    'eccentric_nut': ('Eccentric stack nuts', 'Printed eccentric shaft', 'The nuts close the through screw connections.',
                      'Complete the input coupling and verify the stack fit in CAD.'),
    'planet_bushing': ('Planet bushings', 'Planet pins', 'One bushing sits between each planet and its carrier pin.',
                       'Define pin fixing, seat fits and axial restraint.'),
    'planet_pin': ('Planet pins', 'Planet carriers', 'Each carrier pin locates one planet in its stage.',
                   'Define the connection between pin and carrier.'),
    'planet_bearing': ('Planet bearings', 'Planet pins', 'A bearing sits between the planet and its carrier pin.',
                       'Define the seat fits and axial restraint.'),
    'carrier_bearing': ('Carrier bearings', 'Planet carriers', 'The bearing supports a planet carrier at a central seat.',
                         'Complete the seat, shaft shoulders and axial retention.'),
    'end_bearing': ('End bearings', 'End supports', 'These bearing positions are at external shaft supports.',
                     'Complete the seats and axial retention.'),
    'shaft_bushing': ('Shaft bushings', 'Shaft supports', 'The two sleeves support opposite ends of the same shaft.',
                       'Align the blocks and define the fits and axial restraint.'),
    'worm_bushing': ('Worm journal bushings', 'Worm journals', 'The sleeves support the two worm end journals.',
                      'Align the blocks and provide separate axial restraint.'),
    'bushing_block': ('Bushing blocks', 'Bushing seats', 'These blocks provide the outer seats for the selected sleeves.',
                       'Define how the blocks attach to the frame.'),
    'shaft_bearing': ('Shaft bearings', 'Shaft supports', 'The bearings support journals on the modelled shaft.',
                       'Complete the seats, frame and axial retention.'),
    'hub_bearing': ('Gear bore bearing', 'Gear hub', 'The gear turns on a bearing located in its bore.',
                     'Define shaft support, seat fits and bearing retention.'),
    'pinion_bearing': ('Pinion shaft bearings', 'Pinion shaft', 'These bearings support the pinion shaft.',
                        'Complete the locating shoulders, block alignment and retention.'),
    'wheel_bearing': ('Wheel shaft bearings', 'Wheel shaft', 'These bearings support the wheel shaft.',
                       'Complete the locating shoulders, block alignment and retention.'),
    'wave_bearing': ('Wave bearing', 'Wave generator', 'The envelope follows the wave generator inside the flexspline.',
                      'Choose the compliant bearing and define its interfaces.'),
    'compound_bushing': ('Compound planet bushings', 'Compound planets', 'Each rim has its own sleeve on the shared planet pin.',
                          'Define the alignment of both seats and axial restraint.'),
    'compound_pin': ('Compound planet pins', 'Carrier', 'Each pin passes through both rims of one compound planet.',
                      'Define pin fixing and axial restraint.'),
    'spider_bushing': ('Spider bushing', 'Spider gear', 'The sleeve fits between the spider gear and its transverse pin.',
                        'Define the seat, pin fit and retention.'),
    'spider_pin': ('Spider pin', 'Carrier', 'This transverse pin supports the spider gear in the carrier.',
                   'Define pin fixing and axial retention.'),
    'spider_retainer': ('Spider retainers', 'Carrier', 'The retainers locate the spider axially on the transverse pin.',
                        'Define how the retainers are fixed.'),
    'side_bearing': ('Side bearings', 'Side shafts', 'Each side shaft has its own bearing position.',
                     'Complete the seats and axial retention.'),
    'spacer': ('Spacers', 'Axial location', 'The spacer keeps the modelled axial spacing.',
               'Check which surfaces the spacer contacts in the CAD assembly.'),
}
PIN_KINDS = {'ring_pin', 'output_pin', 'planet_pin', 'compound_pin', 'spider_pin'}
BEARING_KINDS = {key for key in KINDS if key.endswith('_bearing')}
PRIORITY = list(KINDS)


def _size_and_identity(part, kind):
    if part.procurement or part.catalog_code:
        from bom import part_info
        info = part_info(part)
        return 'buy', info['code'], info['dimensions']
    if kind in BEARING_KINDS or part.name.endswith('_envelope'):
        return 'define', '', 'Catalog size pending'
    if part.manufacturing:
        return 'make', '', part.manufacturing['dimensions']
    spacer = next((op for op in part.machining if op['type'] == 'spacer_dimensions'), None)
    if spacer:
        return 'make', '', _tube(spacer['outer_diameter'], spacer['inner_diameter'], spacer['length'])
    profile = circle_info(part.outer)
    bore = circle_info(part.holes[0]) if len(part.holes) == 1 else None
    if profile and bore and not part.stations:
        return 'make', '', _tube(2*profile[2], 2*bore[2], part.width)
    if profile and (kind in PIN_KINDS or not part.stations):
        return 'make', '', f'Ø{2*profile[2]:.9g} × {part.width:.9g} mm'
    from bom import part_info
    return 'make', '', part_info(part)['dimensions']


def _tube(outer, bore, length):
    return 'Ø{arg0} OD · Ø{arg1} bore · {arg2} mm'.format(
        arg0=f'{outer:.9g}', arg1=f'{bore:.9g}', arg2=f'{length:.9g}')


def _kind(part):
    if part.bom_kind:
        return part.bom_kind
    if part.catalog_code:
        return 'shaft_bearing'
    if any(op['type'] == 'spacer_dimensions' for op in part.machining):
        return 'spacer'
    if part.procurement:
        return 'frame_fastener' if part.name.startswith('Mounting_') else 'hardware'
    if part.name.endswith('_envelope') and part.name.startswith('Bearing_'):
        return 'shaft_bearing'
    return ''


def _quantity_basis(kind, count, full_count, design):
    if count != full_count:
        # An alternate SKU or size gets its own row. Do not give it the
        # explanation or quantity of the full class.
        return ''
    if kind in ('ring_bushing', 'ring_bearing', 'ring_shell') and design.family == 'cycloidal':
        pins = design.values['pins']
        discs = 2 if design.values['variant'] == 'dual' else 1
        if count == pins * discs:
            return '{value} ring pins × {arg1} discs = {arg2}'.format(value=pins, arg1=discs, arg2=count)
    if kind in ('planet_bushing', 'planet_bearing', 'planet_pin') and design.family == 'planetary':
        planets = design.values['planets']
        stages = len(design.analysis.get('kinematics', {}).get('stage_results', ()))
        if stages and count == planets * stages:
            return '{value} planets per stage × {arg1} stages = {arg2}'.format(
                value=planets, arg1=stages, arg2=count)
    if kind == 'compound_bushing' and count == design.values['planets'] * 2:
        return '{value} compound planets × 2 seats = {arg1}'.format(
            value=design.values['planets'], arg1=count)
    if kind == 'ring_pin':
        return 'One pin per ring position, shared by both discs.' if design.values['variant'] == 'dual' else 'One pin per ring position.'
    if kind == 'output_pin':
        return 'One pin per flange position.'
    if kind == 'compound_pin':
        return 'One pin per compound planet.'
    return ''


def _catalog_rows(design, kinds):
    groups = {}
    full_counts = Counter(kind for kind in kinds if kind)
    for index, (part, kind) in enumerate(zip(design.parts, kinds)):
        if not kind:
            continue
        status, code, dimensions = _size_and_identity(part, kind)
        if kind in KINDS:
            label, group, detail, cad = KINDS[kind]
        else:
            label = part.procurement['description']
            group = 'Frame fastening' if kind == 'frame_fastener' else 'Assembly hardware'
            detail = ('These parts fasten the modelled frame flanges.' if kind == 'frame_fastener'
                      else 'This item belongs to the selected assembly construction.')
            cad = 'Complete mating features and verify fit and retention in CAD.'
        if status == 'define':
            cad = 'Select the bearing, then complete the seats and axial retention.' if kind != 'wave_bearing' else cad
        key = (kind, status, code, dimensions, label)
        if key not in groups:
            groups[key] = dict(kind=kind, label=label, group=group, status=status, quantity=0,
                               dimensions=dimensions, code=code, indices=[], detail=detail, cad=cad,
                               count_basis='', source='')
            if part.procurement:
                groups[key]['source'] = part.procurement.get('source', '')
            elif part.catalog_code:
                from catalog import BEARINGS
                groups[key]['source'] = BEARINGS[part.catalog_code].url
            elif part.catalog_code:
                from catalog import BEARINGS
                groups[key]['source'] = BEARINGS[part.catalog_code].url
        record = groups[key]
        record['indices'].append(index)
        record['quantity'] += 1
    rows = list(groups.values())
    rows.sort(key=lambda row: PRIORITY.index(row['kind']) if row['kind'] in KINDS else len(PRIORITY))
    for row in rows:
        row['count_basis'] = _quantity_basis(row['kind'], row['quantity'], full_counts[row['kind']], design)
    return rows


def _interfaces(design, kinds):
    family, values = design.family, design.values
    by_name = {p.name: i for i, p in enumerate(design.parts)}
    interfaces = []
    def add(pattern, label, group, detail, cad, diameter=None):
        indices = [i for name, i in by_name.items() if re.fullmatch(pattern, name) and not kinds[i]]
        if not indices:
            return
        dimensions = 'Ø{arg0} mm nominal'.format(arg0=f'{diameter:.9g}') if isinstance(diameter, Real) and diameter > 0 else 'Size to define'
        interfaces.append(dict(kind='cad_interface', label=label, group=group, status='interface',
                               quantity=None, dimensions=dimensions, code='', indices=indices,
                               detail=detail, cad=cad, count_basis='', source=''))

    if family in ('spur', 'helical', 'double'):
        if 'hub_bearing' not in kinds:
            # The gear is a reference for the mating connection, not an extra part.
            add('Gear', 'Gear-to-shaft connection', 'Gear hub',
                'Use the gear hub as the mating reference.',
                'Define torque transfer and axial retention.', values.get('bore'))
        if not any(kind in ('shaft_bearing', 'shaft_bushing') for kind in kinds):
            add(r'Shaft_.*', 'Shaft support', 'Gear shaft', 'Supports locate the shaft relative to the frame.',
                'Choose the supports and define their seating and axial location.')
    elif family == 'planetary':
        if not any(kind in ('planet_bushing', 'planet_bearing') for kind in kinds):
            add(r'S\d+_Planet_\d+', 'Planet running fit', 'Planet pins',
                'The planet bores are the references for the running fit on the carrier pins.',
                'Define the pin fit and axial restraint for each stage.')
        if not any(kind in ('carrier_bearing', 'end_bearing') for kind in kinds):
            add(r'S\d+_PlanetCarrier_lower', 'Carrier support', 'Planet carriers',
                'The carrier seats are the references for external supports.',
                'Choose the bearings and retention for the selected input and output arrangement.')
    elif family == 'cycloidal':
        if values['io_scheme'].split('_')[1] == 'ring':
            add('Ring_pin_carrier', 'Annular ring support', 'Rotating ring',
                'The ring locates the rotating output of this arrangement.',
                'Define the external annular support, its seat and axial retention.')
        elif 'ring_pin' not in kinds:
            add('Ring_pin_carrier', 'Integral ring contacts', 'Cycloidal ring',
                'The contacts are formed directly in the ring.',
                'Complete the mounting or external support for the selected ring role.')
        add(r'Flange_(output|pincarrier)', 'Pin flange connection', 'Pin flange',
            'The flange locates the pins and provides an external connection.',
            'Define the mating coupling and its retention.')
        connection = design.analysis.get('eccentric_connection', {})
        if connection.get('shaft_bore'):
            add(r'Eccentric_\d+', 'External shaft connection', 'Eccentrics',
                'The eccentric bores locate the external input shaft.',
                'Define the shaft, torque transfer and axial retention.', values.get('input_shaft'))
    elif family == 'harmonic':
        add(r'Flexspline_.*', 'Flexspline flange connection', 'Flexspline',
            'The flange locates the flexspline connection in the selected arrangement.',
            'Define the mating flange and fastening pattern.')
        add(r'Circular_spline_.*', 'Circular spline connection', 'Circular spline',
            'The rigid circular spline connects to the external assembly.',
            'Define its mounting and retention for the selected arrangement.')
    elif family == 'worm':
        if 'worm_bushing' not in kinds:
            add(r'Screw_.*', 'Worm shaft support', 'Worm journals',
                'The worm bearings or bushings must locate the worm shaft.',
                'Define the journal supports and axial restraint.', values.get('journal_diameter'))
        add(r'Wheel_.*', 'Wheel shaft support', 'Wheel axis',
            'The wheel uses its own axis and supports.',
            'Define the wheel shaft, bearings and retention.', values.get('bore'))
    elif family == 'parallel':
        bushing_shaft = design.analysis.get('shaft_bushings', {}).get('part')
        axis_with_shaft = set()
        for part in design.parts:
            if not re.fullmatch(r'Shaft_(?:input|output|lato_A|lato_B|[1-9]\d*)', part.name):
                continue
            axis_with_shaft.add(part.port.get('member'))
            if part.name == bushing_shaft:
                continue
            bearing_kind = 'pinion_bearing' if part.name in ('Shaft_input', 'Shaft_lato_A') else 'wheel_bearing'
            if bearing_kind in kinds:
                continue
            shaft_number = re.search(r'\d+$', part.name)
            if shaft_number:
                group = 'Shaft ' + shaft_number.group()
            elif part.port.get('member') == 'A' or part.name == 'Shaft_input':
                group = 'Pinion shaft'
            else:
                group = 'Wheel shaft'
            profile = circle_info(part.outer)
            add(re.escape(part.name), 'Shaft support', group, 'Supports locate this shaft relative to the frame.',
                'Define the supports and axial retention for this shaft.', 2*profile[2] if profile else None)
        # A shaped bore can replace the reference shaft. Keep the CAD row
        # anchored to the gear instead of inferring a shaft from a missing part.
        shaped = set()
        for connection in design.analysis.get('shaft_connections', ()):
            shaped.add(connection['part'])
            add(re.escape(connection['part']), 'External shaft connection', 'Shaft connection',
                'The shaped bore is the mating reference for an external shaft.',
                'Define shaft support and axial retention.', connection.get('diameter_mm'))
        if not any(re.fullmatch(r'Shaft_\d+', name) for name in by_name):
            for member, suffix, group in [('A', 'Pinion', 'Pinion shaft'), ('B', 'Wheel', 'Wheel shaft')]:
                gear = 'S1_'+suffix
                if member in axis_with_shaft or gear in shaped:
                    continue
                add(gear, 'Shaft support', group, 'This gear is the reference for its shaft connection.',
                    'Define the shaft, supports and axial retention.')
    elif family == 'internal':
        if not any(kind in ('pinion_bearing', 'shaft_bushing') for kind in kinds):
            add(r'Pinion_input', 'Pinion shaft support', 'Pinion axis', 'The pinion shaft supports the inner gear.',
                'Define the supports, seat fits and retention.', values.get('bore'))
        add(r'Ring_output', 'Annular ring support', 'Ring axis',
            'The ring and pinion turn about different axes.',
            'Define the annular support, its seat and retention.')
    elif family == 'differential':
        add(r'Flange_carrier_input|Flange_output(?:_[AB])?', 'External flange connection', 'Differential flanges',
            'These flanges locate the external connections in the selected construction.',
            'Define the attachments and their fastening.')
    elif family == 'wolfrom':
        add(r'Ring_output', 'Output ring support', 'Rotating ring',
            'The output ring needs support relative to the fixed structure.',
            'Define the annular support and its axial retention.')
    elif family in ('bevel', 'hypoid', 'face'):
        pinion, wheel = {
            'bevel': ('Bevel_pinion', 'Bevel_wheel'),
            'hypoid': ('Hypoid_pinion', 'Hypoid_wheel'),
            'face': ('Face_pinion', 'Face_wheel'),
        }[family]
        detail = {
            'bevel': 'Locate the shafts about the common pitch apex.',
            'hypoid': 'Locate the shafts while preserving the selected offset.',
            'face': 'Locate the pinion relative to the face wheel and preserve the selected axis offset.',
        }[family]
        add(pinion, 'Pinion shaft support', 'Pinion axis', detail,
            'Define the shaft, bearings and axial retention.', values.get('bore'))
        add(wheel, 'Wheel mounting', 'Wheel axis', detail,
            'Define the hub or flange, bearing seats and axial locating features.', values.get('output_bore'))
    elif family == 'rack':
        add(r'Rack_pinion', 'Pinion shaft support', 'Pinion axis', 'Locate the shaft relative to the rack pitch line.',
            'Define the shaft, bearing positions and retention.', values.get('bore'))
        add('Rack', 'Linear guide and travel stops', 'Rack travel', 'The guide constrains travel along the rack.',
            'Define the guide, rack attachment and end stops.')
    return interfaces


def build(design):
    """View data derived from this design's final ordered source components."""
    kinds = [_kind(part) for part in design.parts]
    rows = _catalog_rows(design, kinds) + _interfaces(design, kinds)
    mapped = {index for row in rows for index in row['indices']}
    # Large covers can obscure every useful part. The interactive view retains
    # generated functional hardware, seats and CAD references plus the mechanism.
    # The inventory report and export continue to describe all source bodies.
    context = [i for i, part in enumerate(design.parts)
               if i in mapped or part.role != 'housing'
               or (part.name == 'Ring_pin_carrier' and design.family == 'cycloidal')]
    variant_key = design.values.get('variant')
    variant = VARIANTS.get(design.family, {}).get(variant_key, '')
    if design.family == 'differential':
        configuration = 'Classic differential' if design.values['configuration'] == 'classic' else 'Differential wrist'
        variant = f'{configuration} · {variant}'
    return dict(family=design.family, family_label=FAMILIES[design.family], variant=variant, rows=rows, context_indices=context,
                requirements=list(design.requirements))
