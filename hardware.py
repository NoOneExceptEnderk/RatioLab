'Assembly standard: componenti acquistabili e lavorazioni geometriche collegate.'
from math import sin,cos,asin,sqrt,pi,hypot,radians,acos,ceil
from geometry import Part,circle,circle_info,polar,transformed,profile_sections,section_holes,TAU
from hardware_catalog import *
from catalog import selected
STEEL=(.63,.69,.75);KEY_COLOR=(.94,.72,.33)


def buy(p,code,description,dimensions,manufacturer,source,standard):
    p.procurement=dict(code=code,description=description,dimensions=dimensions,manufacturer=manufacturer,source=source,standard=standard)
    return p


def shim(d,shaft,z,tag):
    actual=2*circle_info(shaft.outer)[2]
    sizes=[size for size in SHIMS if size>=actual-1e-7]
    if not sizes:raise ValueError('Shim unavailable for this shaft.')
    size=min(sizes);outer=SHIMS[size];thick=float(d.values['hardware_shim'])
    p=Part(tag,circle(outer/2),[circle(size/2)],thick,z,shaft.center,role='support',color=STEEL)
    sku=f'K1151.{size:02d}{outer:02d}{round(thick*100):03d}'
    buy(p,sku,'DIN 988 shim',f'{size} × {outer} × {thick:g} mm','KIPP',SHIM_SOURCE,'DIN 988');d.parts.append(p);return thick


def ring_part(d,spec,z,center,tag,internal=False):
    r=spec['groove']/2
    inner=r-spec['beam'] if internal else r;outer=r if internal else r+spec['beam']
    gap=pi/7
    outline=[polar(outer,gap+(TAU-2*gap)*j/128) for j in range(129)]
    outline += [polar(inner,TAU-gap-(TAU-2*gap)*j/128) for j in range(129)]
    p=Part(tag,outline,[],spec['s'],z,center,role='support',color=STEEL)
    buy(p,spec['code'],'Retaining ring '+('internal' if internal else 'external'),f"{spec['standard']} · Ø {spec['d']:g} · s {spec['s']:g} mm",spec['manufacturer'],spec['source'],spec['standard'])
    d.parts.append(p)


def groove(p,spec,a,b,internal=False):
    p.machining.append(dict(type='groove_internal' if internal else 'groove_external',standard=spec['standard'],z0=round(a-p.z,9),z1=round(b-p.z,9),diameter=spec['groove'],width=spec['m'],source=spec['source'],edge_margin=spec['edge']))


def key_pair(d,shaft,hub=None,start=None):
    actual=circle_info(shaft.outer)[2]*2
    nominal=round(actual) if abs(actual-round(actual))<.15 else None
    if nominal not in KEYS:
        d.requirements.append(f'Key {shaft.name}: diameter {actual:g} mm is outside the initial catalog (6, 8, 10, 12 mm).');return
    b,h,ts,th=KEYS[nominal]
    available=(hub.width if hub else 10)
    lengths=[L for L in KEY_LENGTHS if L<=available-1]
    if not lengths:
        d.requirements.append(f'Key {shaft.name}: at least 9 mm of hub is required for the minimum catalog length.');return
    length=max(lengths)
    a=hub.z+(hub.width-length)/2 if hub else start
    end=a+length
    shaft.width=max(shaft.width,end-shaft.z+2)
    radius=actual/2
    shaft.machining.append(dict(type='keyway_shaft',standard='DIN 6885-1 B',z0=a-shaft.z,z1=end-shaft.z,b=b,depth=ts,source=KEY_SOURCE))
    if hub:
        if not hub.holes or not circle_info(hub.holes[0]):raise ValueError('The key requires a circular hub bore.')
        bore=circle_info(hub.holes[0])[2]
        limit=hub.core_radius if hub.double else min(hypot(x,y) for x,y in hub.outer)
        if bore+th+.5>=limit:raise ValueError('Insufficient material above the hub keyway.')
        hub.machining.append(dict(type='keyway_hub',standard='DIN 6885-1 B',z0=0,z1=hub.width,b=b,depth=th,source=KEY_SOURCE))
    else:d.requirements.append(f'{shaft.name}: output keyway and key generated; the external accessory hub is not included.')
    bottom=radius-ts
    p=Part(shaft.name+'_Key',[(bottom,-b/2),(bottom+h,-b/2),(bottom+h,b/2),(bottom,b/2)],[],length,a,shaft.center,role='support',color=KEY_COLOR)
    buy(p,f'DIN 6885-1 B {b:g}x{h:g}x{length:g}','Square ended parallel key',f'{b:g} × {h:g} × {length:g} mm','To be selected',KEY_PRODUCT,'DIN 6885-1 B');d.parts.append(p)


def spacer(d,shaft,a,b,tag):
    if b-a<1e-7:return
    bearing=selected(d.values);radius=circle_info(shaft.outer)[2]
    outside=(bearing.da_min+.1)/2 if bearing else radius+1
    p=Part(tag,circle(outside),[circle(radius)],b-a,a,shaft.center,role='support',color=STEEL)
    p.machining.append(dict(type='spacer_dimensions',inner_diameter=2*radius,outer_diameter=2*outside,length=b-a,z0=0,z1=b-a,source=bearing.url if bearing else 'Progetto'))
    d.parts.append(p)


def external_stop(d,shaft,contact,upper=True,tag='Retainer'):
    actual=2*circle_info(shaft.outer)[2];nominal=round(actual)
    if nominal not in EXTERNAL or abs(actual-nominal)>.15:
        d.requirements.append(f'{shaft.name}: external retaining ring unavailable for Ø {actual:g} mm.');return
    spec=EXTERNAL[nominal];sp=float(d.values['hardware_shim']) if d.values['hardware_shims'] else 0
    if sp:shim(d,shaft,contact if upper else contact-sp,tag+'_Shim')
    a=contact+sp if upper else contact-sp-spec['m'];b=a+spec['m']
    newlo=min(shaft.z,a-spec['edge']);newhi=max(shaft.z+shaft.width,b+spec['edge'])
    if newlo<shaft.z:
        shift=shaft.z-newlo
        for op in shaft.machining:
            op['z0']+=shift;op['z1']+=shift
        shaft.z=newlo
    shaft.width=newhi-shaft.z
    groove(shaft,spec,a,b)
    ring_part(d,spec,a if upper else b-spec['s'],shaft.center,tag+'_Seeger')


def internal_stops(d):
    bearings=[p for p in d.parts if p.catalog_code]
    for bearing in bearings:
        b=selected(d.values);spec=INTERNAL[int(b.D)]
        candidates=[]
        for p in d.parts:
            if p is bearing or p.procurement or p.catalog_code or not p.holes or p.center!=bearing.center:continue
            info=circle_info(p.holes[0])
            if info and abs(info[2]-(b.D+d.values['seat_allowance'])/2)<1e-5 and p.z<=bearing.z+1e-6 and p.z+p.width>=bearing.z+bearing.width-1e-6:candidates.append(p)
        if not candidates:
            d.requirements.append(f'{bearing.name}: internal stop housing not found.');continue
        host=min(candidates,key=lambda p:p.width)
        for upper in (False,True):
            a=bearing.z+bearing.width if upper else bearing.z-spec['m'];end=a+spec['m']
            if a-host.z<spec['edge']-1e-6 or host.z+host.width-end<spec['edge']-1e-6:raise ValueError(f'{host.name}: insufficient margin for the internal retaining ring groove.')
            limit=host.core_radius if host.double else min(hypot(x,y) for x,y in host.outer)
            if spec['groove']/2+.5>=limit:raise ValueError(f'{host.name}: retaining ring groove too close to the edge or tooth root.')
            # Other holes must leave material around the enlarged seat.
            for loop in host.holes[1:]:
                ci=circle_info(loop)
                if ci and hypot(ci[0],ci[1])-ci[2]<spec['groove']/2+.5:raise ValueError(f'{host.name}: retaining ring groove overlaps other holes.')
            groove(host,spec,a,end,True)
            ring_part(d,spec,a if upper else end-spec['s'],host.center,host.name+('_Retainer_upper' if upper else '_Retainer_lower'),True)


def fasteners(d):
    housing=[p for p in d.parts if p.role=='housing' and ('Cover_' in p.name or p.name.startswith('BearingBlock_'))]
    if len(housing)<2:
        d.requirements.append('Fasteners: choose shaft support bearings to obtain the two flanges to connect.');return
    lower=min(housing,key=lambda p:p.z);upper=max(housing,key=lambda p:p.z+p.width)
    f=FASTENERS[d.values['hardware_screw']];diam=f['d'];washer=f['washer_t'];nut=f['nut']
    extent=max(hypot(*p.center)+max(hypot(x,y) for x,y in p.outer) for p in d.parts if not p.procurement)
    post_radius=f['washer_od']/2+1;pitch=extent+post_radius+1
    cover_radius=pitch+f['washer_od']/2+1
    if not circle_info(lower.outer) or not circle_info(upper.outer):raise ValueError('Fasteners require circular outer flanges.')
    lower.outer=circle(cover_radius);upper.outer=circle(cover_radius)
    lo=lower.z;hi=upper.z+upper.width;span=hi-lo
    required=span+2*washer+nut+2*f['pitch']
    choices=[L for L in LENGTHS if L>=required]
    if not choices:raise ValueError('Screw length exceeds 120 mm: reduce assembly length or disable fasteners.')
    length=min(choices);thread_top=hi+washer;screw_bottom=thread_top-length
    for j in range(4):
        center=polar(pitch,TAU*(j+.5)/4);label=f'Mounting_{j+1}'
        # Design clearance: normal pass-through clearance, no tapped holes are claimed.
        hole=circle(f['clearance']/2,96,center)
        for plate in (lower,upper):
            plate.holes.append(hole);plate.machining.append(dict(type='clearance_hole',diameter=f['clearance'],center=list(center),through=True,z0=0,z1=plate.width,source='Design choice: diametral clearance of the through hole',thread=d.values['hardware_screw']))
        postz=lower.z+lower.width;postw=upper.z-postz
        if postw>0:d.parts.append(Part(label+'_Spacer_tierod',circle(post_radius),[circle(f['clearance']/2)],postw,postz,center,role='housing',color=STEEL))
        for tag,z in [('upper',hi),('lower',lo-washer)]:
            p=Part(label+'_Washer_'+tag,circle(f['washer_od']/2),[circle(f['washer_id']/2)],washer,z,center,role='support',color=STEEL)
            buy(p,f'ISO 7089 {diam}','Flat washer',f"{f['washer_id']:g} × {f['washer_od']:g} × {washer:g} mm",'To be selected',WASHER_SOURCE,'ISO 7089');d.parts.append(p)
        # Same vertex count through the head shoulder; thread and socket are simplified.
        p=Part(label+'_Screw',circle(diam/2),[],length+f['k'],screw_bottom,center,role='support',color=STEEL)
        p.stations=[dict(z=z,outer=circle(r,128),holes=[]) for z,r in [(0,diam/2),(length,diam/2),(length,f['head']/2),(length+f['k'],f['head']/2)]]
        buy(p,f'ISO 4762 M{diam}x{length}','Hex socket head cap screw',f'M{diam} × {length} mm · P {f["pitch"]:g}','To be selected',SCREW_SOURCE,'ISO 4762');d.parts.append(p)
        radius=f['af']/sqrt(3);hexagon=[polar(radius,TAU*k/6) for k in range(6)]
        p=Part(label+'_Nut',hexagon,[circle(diam/2)],nut,lo-washer-nut,center,role='support',color=STEEL)
        buy(p,f'ISO 4032 M{diam}','Hex nut',f'M{diam} · SW {f["af"]:g} · h {nut:g} mm','To be selected',NUT_SOURCE,'ISO 4032');d.parts.append(p)
    d.metrics.append(f'Fasteners: 4 × M{diam}×{length} · flange fissaggio Ø {2*cover_radius:.2f} mm')
    d.requirements.append('Fasteners: select strength class, material, finish and tightening torque; ISO designations are not manufacturer SKUs. Threads and drive recesses are simplified envelopes.')


def shaped_circle(r,key,active,hub=False):
    b=key['b'];theta=asin(b/(2*r));points=[polar(r,theta+(TAU-2*theta)*j/256) for j in range(257)]
    bottom,top=points[-1],points[0]
    x=r+key['depth'] if hub else r-key['depth']
    for j in range(33):
        y=-b/2+b*j/32
        if not active:points.append(bottom if j==0 else top if j==32 else (sqrt(max(0,r*r-y*y)),y))
        else:points.append((x,y))
    return points


def rebuild(p):
    cuts=[o for o in p.machining if o['type'] in ('groove_internal','groove_external','keyway_shaft','keyway_hub')]
    if not cuts:return
    raw=[(z,angle,[outer]+section_holes(p,z)) for z,angle,outer in profile_sections(p)]
    counts=[]
    for j in range(len(raw[0][2])):
        radii=[ci[2] for z,angle,loops in raw if (ci:=circle_info(loops[j]))]
        radii += [op['diameter']/2 for op in cuts if (j==0 and op['type']=='groove_external') or (j==1 and op['type']=='groove_internal')]
        n=max(96,ceil(pi/acos(max(-1,min(1,1-.002/max(radii)))))) if radii else len(raw[0][2][j])
        counts.append(16*ceil(n/16))
    base=[]
    for z,angle,loops in raw:
        normalized=[]
        for j,loop in enumerate(loops):
            ci=circle_info(loop)
            normalized.append(transformed(circle(ci[2],counts[j],ci[:2]) if ci else loop,angle=radians(angle)))
        base.append((z,normalized))
    def at(z):
        for (a,lo),(b,hi) in zip(base,base[1:]):
            if a-1e-8<=z<=b+1e-8:
                t=0 if b==a else (z-a)/(b-a)
                return [[(x+(xx-x)*t,y+(yy-y)*t) for (x,y),(xx,yy) in zip(one,two)] for one,two in zip(lo,hi)]
        return [list(loop) for loop in (base[0][1] if z<=0 else base[-1][1])]
    positions=sorted({0.,p.width,*[z for z,loops in base],*[min(p.width,max(0,o[k])) for o in cuts for k in ('z0','z1')]})
    keyshaft=next((o for o in cuts if o['type']=='keyway_shaft'),None);keyhub=next((o for o in cuts if o['type']=='keyway_hub'),None)
    stations=[]
    for z in positions:
        states=[]
        for sample in ([z+1e-7] if z==0 else [z-1e-7] if z==p.width else [z-1e-7,z+1e-7]):
            active=tuple(o['z0']<=sample<=o['z1'] for o in cuts)
            if states and states[-1]==active:continue
            states.append(active);loops=at(z)
            outer=loops[0];holes=loops[1:]
            for op,on in zip(cuts,active):
                if not on:continue
                if op['type']=='groove_external':outer=circle(op['diameter']/2,counts[0])
                elif op['type']=='groove_internal':holes[0]=circle(op['diameter']/2,counts[1])
            if keyshaft:
                radius=circle_info(outer)[2];outer=shaped_circle(radius,keyshaft,active[cuts.index(keyshaft)])
            if keyhub:
                radius=circle_info(holes[0])[2];holes[0]=shaped_circle(radius,keyhub,active[cuts.index(keyhub)],True)
            stations.append(dict(z=z,outer=list(outer),holes=[list(h) for h in holes]))
    p.stations=stations


def apply_hardware(d):
    v=d.values
    if v['hardware_mode']=='none' or not any(v['hardware_'+k] for k in ('retaining','keys','bolts','shims')):return
    d.notes=[n.replace('Sedi passanti: arresti assiali, spallamenti (','Riferimenti degli spallamenti (').replace('), retaining rings, keys and lubrication must be designed.','). Generated retainers and keyways are listed under machining; check supports and lubrication.').replace('keys, threads, seals and catalog bearings are not generated.','hardware machining is listed in the BOM; seals and remaining connections must be completed.').replace('keys, threads and seals are not generated.','seals and remaining connections must be completed.') for n in d.notes]
    # Keys are added only to real shaft/hub pairs, or to the exposed output interface.
    if d.family in ('spur','helical','double') and any(v['hardware_'+k] for k in ('keys','retaining','shims')):
        gear=d.parts[0];shaft=next((p for p in d.parts if p.name.startswith('Shaft_')),None)
        if shaft is None:
            if v['bore']<=0:raise ValueError('Standard assembly requires a bore and a shaft.')
            shaft=Part('Shaft_standard',circle(v['bore']/2),[],gear.width+12,-6,role='support',color=STEEL);d.parts.append(shaft)
        if v['hardware_keys']:
            if v['bearing_mode']=='gear':d.requirements.append('Hub key omitted: the gear rotates on the bearing and is not fixed to the shaft.')
            else:key_pair(d,shaft,gear)
        if v['hardware_retaining']:
            bearings=[p for p in d.parts if p.catalog_code]
            left,right=0,gear.width
            if v['bearing_mode']=='shaft' and bearings:
                left=min(p.z for p in bearings);right=max(p.z+p.width for p in bearings)
                before=max(p.z+p.width for p in bearings if p.z+p.width<gear.z)
                after=min(p.z for p in bearings if p.z>gear.z+gear.width)
                if v['hardware_shims']:
                    spacer(d,shaft,before,gear.z,'Spacer_internal_lower');spacer(d,shaft,gear.z+gear.width,after,'Spacer_internal_upper')
                    # Keep the large DIN 988 washers outside the internal circlip planes.
                    # Only the narrow custom tube passes through the ring's lug opening.
                    clearance=INTERNAL[int(selected(v).D)]['m']+.2
                    spacer(d,shaft,left-clearance,left,'Spacer_retainer_lower')
                    spacer(d,shaft,right,right+clearance,'Spacer_retainer_upper')
                    left-=clearance;right+=clearance
            elif v['bearing_mode']=='gear' and bearings and v['hardware_shims']:
                bearing=bearings[0]
                spacer(d,shaft,0,bearing.z,'Spacer_internal_lower');spacer(d,shaft,bearing.z+bearing.width,gear.width,'Spacer_internal_upper')
            external_stop(d,shaft,left,False,'Retainer_ingranaggio_lower');external_stop(d,shaft,right,True,'Retainer_ingranaggio_upper')
            if bearings:d.requirements.append('Check that shims and spacers contact only the intended bearing ring; internal raceways are not modelled.')
        elif v['hardware_shims']:
            t=float(v['hardware_shim']);shim(d,shaft,-t,'Shim_lower');shim(d,shaft,gear.width,'Shim_upper')
    elif d.family in ('parallel','internal'):
        from pair_assembly import hardware
        hardware(d)
    elif d.family=='planetary':
        if v['hardware_keys']:
            suns=[p for p in d.parts if p.name.endswith('_Sun')]
            for i,hub in enumerate(suns):
                name='Shaft_input' if i==0 else f'S{i}_Coupling_interstage'
                shaft=next(p for p in d.parts if p.name==name);shaft.width=max(shaft.width,hub.z+hub.width-shaft.z);key_pair(d,shaft,hub)
        output=next(p for p in d.parts if p.name.endswith('Shaft_output'))
        cover=next(p for p in d.parts if p.name=='Cover_output');start=cover.z+cover.width+.5
        if v['hardware_keys']:key_pair(d,output,start=start)
        if v['hardware_retaining']:external_stop(d,output,max(start+9,output.z+output.width-1),True,'Retainer_output')
        elif v['hardware_shims']:shim(d,output,start,'Shim_output')
        d.requirements.append('Planet pins: flange retention must still be completed; output end rings do not retain every internal support.')
    elif d.family=='cycloidal':
        output=next(p for p in d.parts if p.name=='Shaft_output');cover=next(p for p in d.parts if p.name=='Cover_output');start=cover.z+cover.width+.5
        if v['hardware_keys']:key_pair(d,output,start=start)
        if v['hardware_retaining']:external_stop(d,output,max(start+9,output.z+output.width-1),True,'Retainer_output')
        elif v['hardware_shims']:shim(d,output,start,'Shim_output')
        d.requirements.append('Eccentric cams, pins and output flange connection: size the remaining fasteners and retainers.')
    if v['hardware_retaining']:internal_stops(d)
    if v['hardware_bolts']:fasteners(d)
    for p in d.parts:
        if p.machining:rebuild(p)
    count=sum(bool(p.procurement) for p in d.parts)
    d.metrics.append(f'Hardware standard: {count} components · lavorazioni collegate: {sum(len(p.machining) for p in d.parts)}')
    d.notes.append('Hardware: grooves, keyways and through holes are present in the shared preview/CAD geometry. Rings are shown installed as simplified C sections without lugs; screws and nuts have no actual threads. Gear geometry retains the faithful preview backend.')
