# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Catalog-based fits; bearing envelopes are simplified."""
from math import hypot
from geometry import Part,circle,circle_info
from catalog import selected

CATALOG_BEARING_COLOR = (.52,.61,.7)

def bearing(d,b,name,z,center=(0,0),*,color=CATALOG_BEARING_COLOR,bom_kind='shaft_bearing'):
    p=Part(name,circle(b.D/2),[circle(b.d/2)],b.B,z,center,role='support',color=color,catalog_code=b.code,bom_kind=bom_kind)
    d.parts.append(p);return p


def apply_catalog(d):
    v=d.values;b=selected(v)
    if not b:return
    d.notes=[n.replace('catalog bearings are not generated','fasteners must be completed').replace('bearing envelopes are not catalog parts','remaining supports are not catalog parts') for n in d.notes]
    mode=v['bearing_mode'];seat=(b.D+v['seat_allowance'])/2;shaft=(b.d+v['shaft_allowance'])/2
    def fit_gear(p):
        root=min(hypot(x,y) for x,y in p.outer)
        if seat+.75>=root or (p.double and seat+.5>=p.core_radius):raise ValueError('Bearing too large for the tooth root / hub: choose a smaller size or increase module/tooth count.')
        p.holes[0:1]=[circle(seat)]
        kind = 'planet_bearing' if d.family == 'planetary' else 'hub_bearing'
        bearing(d,b,p.name+'_NSK_'+b.code,p.z+(p.width-b.B)/2,p.center,bom_kind=kind)
    def replace_support(p, *, color=CATALOG_BEARING_COLOR, bom_kind='shaft_bearing'):
        # All callers use simple annular carriers or end plates, with a through seat.
        if b.D/2+.75>=min(hypot(x,y) for x,y in p.outer):raise ValueError('Bearing too large for the support.')
        for loop in p.holes[1:]:
            ci=circle_info(loop)
            if ci and hypot(ci[0],ci[1])-ci[2]<=seat+.5:raise ValueError('Bearing seat overlaps support holes.')
        p.holes[0:1]=[circle(seat)]
        bearing(d,b,p.name+'_NSK_'+b.code,p.z+(p.width-b.B)/2,p.center,color=color,bom_kind=bom_kind)
    if d.family in ('spur','helical','double'):
        p=d.parts[0];margin=v['shoulder']
        if mode=='gear':
            fit_gear(p)
            d.parts.append(Part('Shaft_per_bearing',circle(shaft),[],p.width+12,-6,role='support'))
        else:
            from hardware_catalog import support_width
            sw=support_width(v,b)
            d.parts.append(Part('Shaft_porta_ingranaggio',circle(shaft),[],p.width+2*sw+16,-sw-8,role='support'))
            for tag,z in [('lower',-sw-2+(sw-b.B)/2),('upper',p.width+2+(sw-b.B)/2)]:
                bearing(d,b,'Support_'+tag+'_NSK_'+b.code,z)
                d.parts.append(Part('BearingBlock_'+tag,circle(b.D/2+max(3,margin)),[circle(seat)],sw,z-(sw-b.B)/2,role='housing'))
    elif d.family in ('parallel','internal'):
        from pair_assembly import catalog
        catalog(d,b)
    elif d.family=='planetary':
        if mode=='gear':
            for p in list(d.parts):
                if '_Planet_' in p.name and '_Pin_' not in p.name:fit_gear(p)
                if '_Pin_planet_' in p.name:p.outer=circle(shaft)
                if '_PlanetCarrier_' in p.name or '_Flange_output' in p.name:
                    # First hole is central; all remaining holes locate satellite pins.
                    centers=[(ci[0],ci[1]) for h in p.holes[1:] if (ci:=circle_info(h))]
                    radius=circle_info(p.outer)[2]
                    if centers and max(hypot(x,y) for x,y in centers)+shaft+.75>radius:
                        radius=max(hypot(x,y) for x,y in centers)+shaft+max(1.5,v['plate']*.7)
                        tag=p.name.split('_')[0];ring=next(q for q in d.parts if q.name==tag+'_Ring')
                        if radius+v['assembly_clearance']>=min(hypot(x,y) for x,y in ring.holes[0]):raise ValueError('Catalog pins too large for the carrier and ring: increase module or tooth count.')
                        p.outer=circle(radius)
                        for q in d.parts:
                            if q.name.startswith(tag+'_Retainer_ring_'):q.holes[0]=circle(radius+v['assembly_clearance'])
                    p.holes=[p.holes[0]]+[circle(shaft,48,center) for center in centers]
        else:
            targets=[p for p in d.parts if '_PlanetCarrier_lower' in p.name or p.name in ('Cover_input','Cover_output')]
            d.parts[:]=[p for p in d.parts if 'Bearing_' not in p.name]
            for p in targets:
                replace_support(p, bom_kind='carrier_bearing' if '_PlanetCarrier_' in p.name else 'end_bearing')
    elif d.family=='cycloidal':
        from assemblies import SILVER
        if mode=='gear':
            discs=[p for p in d.parts if p.name.startswith('Disc_cycloidal_')]
            for p in discs:
                bearing(d,b,p.name+'_NSK_'+b.code,p.z+(p.width-b.B)/2,p.center,color=SILVER,bom_kind='eccentric_bearing')
            for p in d.parts:
                if p.name.startswith('Eccentric_'):
                    if v['input_shaft']/2+v['eccentric']+.4>=shaft:raise ValueError('Shaft bore too large for the bearing inner ring: choose a larger d or reduce shaft diameter/eccentricity.')
                    p.outer=circle(shaft)
            d.parts[:]=[p for p in d.parts if not (p.name.startswith('Bearing_eccentric_') and p.name.endswith('_envelope'))]
        else:
            from special_drives import round_loop
            by_name = {p.name: p for p in d.parts}
            plate, gap = v['plate'], v['assembly_clearance']
            carrier = by_name['Ring_pin_carrier']
            flange = by_name['Flange_output']
            block_radius = max(seat, b.D / 2) + v['housing_wall']
            input_z = carrier.z - plate - gap
            output_z = flange.z + flange.width + gap
            for side, z in (('input', input_z), ('output', output_z)):
                block = Part('Bearing_block_' + side, round_loop(block_radius), [circle(seat)],
                             plate, z, role='support', port=dict(member='frame', role='fixed', rpm=0.))
                d.parts.append(block)
                replace_support(block,color=SILVER)
            input_shaft = by_name['Shaft_input']
            shift = max(0., input_shaft.z - (input_z - 8))
            input_shaft.z -= shift
            input_shaft.width += shift
            output_shaft = by_name['Shaft_output']
            output_shaft.width = max(output_shaft.width, output_z + plate + 4 - output_shaft.z)
            d.requirements.append('Attach the two shaft bearing blocks to the fixed frame in CAD.')
    d.metrics.append(f'NSK {b.code} · d {b.d:g} / D {b.D:g} / B {b.B:g} mm · '+('in the bore' if mode=='gear' else 'shaft support'))
    d.notes.extend([f'NSK bearings {b.code} open: simplified envelope, without balls/raceways. Source: {b.url}',
        f'Seat Ø {2*seat:g} mm; shaft Ø {2*shaft:g} mm. DIAMETRAL allowances: seat {v["seat_allowance"]:+g}, shaft {v["shaft_allowance"]:+g} mm. These dimensions do not specify an ISO tolerance class.',
        f'Through seats: axial stops, shoulders (NSK references: da ≥ {b.da_min:g}, Da ≤ {b.Da_max:g}, fillet ra ≤ {b.ra_max:g} mm), retaining rings, keys and lubrication must be designed. Dimensional selection does not verify load, life or speed.'])
