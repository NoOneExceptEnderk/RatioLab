"""Fixed-axis shaft supports; no annular ring output bearing is inferred.

The same parts and machined sections feed preview, CAD, STL and BOM. Common
frame screws are unavailable: the generated housings are independent blocks.
"""
from math import hypot
from geometry import Part,circle

PAIRS={'parallel','internal'}
GEAR_REASON='Bearing-in-bore is unavailable for fixed-axis pairs: generated gears are keyed to shafts; internal rings need a dedicated annular support.'
BOLT_REASON='Flange screw automation is unavailable for fixed-axis pairs: independent bearing blocks have no shared frame or common fastening flanges.'
STUDY_REASON='Automatic bearings / hardware are unavailable for worm and strain-wave study frames and deformation.'
PRINT_REASON='The printed eccentric assembly uses its dedicated bearing and bolted-shaft construction; the generic catalog is unavailable.'


def catalog(d,b):
    from standard_parts import bearing
    from hardware_catalog import support_width
    v=d.values
    if v['bearing_mode']!='shaft':raise ValueError(GEAR_REASON)
    sw=support_width(v,b);seat=(b.D+v['seat_allowance'])/2;shaft=(b.d+v['shaft_allowance'])/2
    targets=[('A','Shaft_input','S1_Pinion' if d.family=='parallel' else 'Pinion_input')]
    if d.family=='parallel':targets.append(('B','Shaft_output','S1_Wheel'))
    for member,name,gear_name in targets:
        gear=next(p for p in d.parts if p.name==gear_name)
        shaftpart=next(p for p in d.parts if p.name==name)
        if shaft+.75>=min(hypot(x,y) for x,y in gear.outer):raise ValueError('Catalog shaft leaves insufficient tooth-root material.')
        # The generator already used the linked bore dimensions; assert rather
        # than silently creating a bearing shaft with a different gear bore.
        gear.holes[0:1]=[circle(shaft)]
        shaftpart.outer=circle(shaft);shaftpart.z=-sw-8;shaftpart.width=gear.width+2*sw+16
        for tag,z in [('lower',-sw-2),('upper',gear.width+2)]:
            bearing(d,b,f'Bearing_{member}_{tag}_NSK_{b.code}',z+(sw-b.B)/2,gear.center)
            d.parts.append(Part(f'BearingBlock_{member}_{tag}',circle(seat+max(3,v['shoulder'])),[circle(seat)],sw,z,gear.center,role='housing'))
    d.analysis['fixed_axis_supports']=dict(scope='both gear shafts' if d.family=='parallel' else 'pinion shaft only; ring output annular support is NOT generated',bearing_code=b.code,shaft_members=[q[0] for q in targets],independent_blocks=True)
    d.requirements=[s for s in d.requirements if 'automatic catalog does not yet apply' not in s]
    d.requirements.append('Independent bearing blocks require a common rigid frame, alignment, fits, lubrication and fastening design. No shared frame screws are generated.')
    if d.family=='internal':d.requirements.append('CATALOG SCOPE: pinion shaft only. Ring output requires a separate annular bearing/support and retention design; no catalog completeness is claimed.')


def hardware(d):
    from hardware import key_pair,external_stop,spacer,shim
    from hardware_catalog import INTERNAL
    from catalog import selected
    v=d.values
    shafts=[p for p in d.parts if p.name in ('Shaft_input','Shaft_output')]
    if not shafts:raise ValueError('Fixed-axis hardware requires at least one real shaft bore.')
    for shaft in shafts:
        member='A' if shaft.name=='Shaft_input' else 'B'
        hubname=('S1_Pinion' if d.family=='parallel' else 'Pinion_input') if member=='A' else 'S1_Wheel'
        hub=next(p for p in d.parts if p.name==hubname)
        start=len(d.parts)
        if v['hardware_keys']:key_pair(d,shaft,hub)
        bearings=[p for p in d.parts if p.catalog_code and p.center==shaft.center]
        left,right=hub.z,hub.z+hub.width
        if bearings:
            left=min(p.z for p in bearings);right=max(p.z+p.width for p in bearings)
            if v['hardware_shims']:
                before=max(p.z+p.width for p in bearings if p.z+p.width<=hub.z)
                after=min(p.z for p in bearings if p.z>=hub.z+hub.width)
                spacer(d,shaft,before,hub.z,shaft.name+'_Spacer_hub_lower')
                spacer(d,shaft,hub.z+hub.width,after,shaft.name+'_Spacer_hub_upper')
                if v['hardware_retaining']:
                    clearance=INTERNAL[int(selected(v).D)]['m']+.2
                    spacer(d,shaft,left-clearance,left,shaft.name+'_Spacer_retainer_lower')
                    spacer(d,shaft,right,right+clearance,shaft.name+'_Spacer_retainer_upper')
                    left-=clearance;right+=clearance
        if v['hardware_retaining']:
            external_stop(d,shaft,left,False,shaft.name+'_Retainer_lower')
            external_stop(d,shaft,right,True,shaft.name+'_Retainer_upper')
        elif v['hardware_shims']:
            thick=float(v['hardware_shim']);shim(d,shaft,left-thick,shaft.name+'_Shim_lower');shim(d,shaft,right,shaft.name+'_Shim_upper')
        # Tag physical ownership explicitly. Kinematics supplies forward/reverse
        # RPM and roles after all assembly construction has finished.
        for p in [shaft]+d.parts[start:]:p.port=dict(member=member,role='internal',rpm=0)
    d.requirements=[s for s in d.requirements if 'automatic catalog does not yet apply' not in s]
    d.requirements.append('Keys, retainers and spacers belong to their identified shaft members. Check bearing-ring contact, fits, shoulders and the remaining frame connections. No ring-output bearing is implied.')


def hardware_warnings(family,values):
    """Explain partial catalog applicability next to active UI choices.

    The backend also records each omitted operation in requirements. A choice
    can still apply to a second shaft or to internal bearing retainers.
    """
    if family not in PAIRS:return {}
    from catalog import BEARINGS
    from hardware_catalog import KEYS,EXTERNAL,SHIMS
    if values.get('bearing_mode')=='shaft':
        b=BEARINGS[str(values.get('bearing','626'))]
        diameter=b.d+(float(values.get('shaft_allowance',0)) if values.get('fit')=='custom' else 0)
        sizes=[('A',diameter)]+([('B',diameter)] if family=='parallel' else [])
    else:sizes=[('A',float(values.get('bore',6)))]+([('B',float(values.get('output_bore',8)))] if family=='parallel' else [])
    result={}
    for key,catalog in [('keys',KEYS),('retaining',EXTERNAL),('shims',SHIMS)]:
        if key=='shims':unavailable=[name for name,size in sizes if not any(q>=size-1e-7 for q in catalog)]
        else:unavailable=[name for name,size in sizes if round(size) not in catalog or abs(size-round(size))>.15]
        reasons=[]
        if unavailable:
            reasons.append('Shaft '+', '.join(unavailable)+': '+('keys/keyways' if key=='keys' else 'external rings/grooves' if key=='retaining' else 'DIN 988 shims')+' unavailable at this diameter in the verified catalog; omitted and listed in BOM requirements.')
        if key=='keys' and float(values.get('width',10))<9:reasons.append('Keys/keyways require at least 9 mm hub width; omitted and listed in BOM requirements.')
        if key=='retaining' and unavailable and values.get('bearing_mode')=='shaft':reasons.append('Internal bearing retaining rings remain applicable.')
        if reasons:result[key]=' '.join(reasons)
    return result
