"""Accoppiamenti di catalogo; gli involucri dei cuscinetti sono semplificati."""
from math import hypot
from geometry import Part,circle,circle_info
from catalog import selected


def bearing(d,b,name,z,center=(0,0)):
    p=Part(name,circle(b.D/2),[circle(b.d/2)],b.B,z,center,role='support',color=(.52,.61,.7),catalog_code=b.code)
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
        bearing(d,b,p.name+'_NSK_'+b.code,p.z+(p.width-b.B)/2,p.center)
    def replace_support(p):
        # All callers use simple annular carriers or end plates, with a through seat.
        if b.D/2+.75>=min(hypot(x,y) for x,y in p.outer):raise ValueError('Bearing too large for the support.')
        for loop in p.holes[1:]:
            ci=circle_info(loop)
            if ci and hypot(ci[0],ci[1])-ci[2]<=seat+.5:raise ValueError('Bearing seat overlaps support holes.')
        p.holes[0:1]=[circle(seat)]
        bearing(d,b,p.name+'_NSK_'+b.code,p.z+(p.width-b.B)/2,p.center)
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
            for p in targets:replace_support(p)
    elif d.family=='cycloidal':
        if mode=='gear':
            discs=[p for p in d.parts if p.name.startswith('Disc_cycloidal_')]
            for p in discs:
                bearing(d,b,p.name+'_NSK_'+b.code,p.z+(p.width-b.B)/2,p.center)
            for p in d.parts:
                if p.name.startswith('Eccentric_'):
                    if v['input_shaft']/2+v['eccentric']+.4>=shaft:raise ValueError('Shaft bore too large for the bearing inner ring: choose a larger d or reduce shaft diameter/eccentricity.')
                    p.outer=circle(shaft)
            d.parts[:]=[p for p in d.parts if not (p.name.startswith('Bearing_eccentric_') and p.name.endswith('_envelope'))]
        else:
            targets=[p for p in d.parts if p.name=='Cover_input']
            d.parts[:]=[p for p in d.parts if p.name!='Bearing_input_envelope']
            for p in targets:replace_support(p)
            # Output bearing is placed on the shaft beyond the rotating flange.
            cover=next(p for p in d.parts if p.name=='Cover_output')
            replace_support(cover)
            shaftpart=next(p for p in d.parts if p.name=='Shaft_output')
            shaftpart.width=max(shaftpart.width,cover.z+cover.width+4-shaftpart.z)
            d.parts[:]=[p for p in d.parts if p.name not in ('Bearing_flanges_output_envelope','Seat_support_output')]
    d.metrics.append(f'NSK {b.code} · d {b.d:g} / D {b.D:g} / B {b.B:g} mm · '+('in the bore' if mode=='gear' else 'shaft support'))
    d.notes.extend([f'NSK bearings {b.code} open: simplified envelope, without balls/raceways. Source: {b.url}',
        f'Seat Ø {2*seat:g} mm; shaft Ø {2*shaft:g} mm. DIAMETRAL allowances: seat {v["seat_allowance"]:+g}, shaft {v["shaft_allowance"]:+g} mm. These dimensions do not specify an ISO tolerance class.',
        f'Through seats: axial stops, shoulders (NSK references: da ≥ {b.da_min:g}, Da ≤ {b.Da_max:g}, fillet ra ≤ {b.ra_max:g} mm), retaining rings, keys and lubrication must be designed. Dimensional selection does not verify load, life or speed.'])
