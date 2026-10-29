# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Nominal dimensions checked against primary catalogs, in mm; no invented prices or SKUs."""
from math import isfinite
VERIFIED='2026-10-23'
SUPPORTED={'spur','helical','double','planetary','cycloidal','parallel','internal'}
MODES={'none':'No additional hardware','standard':'Assembly with standard components'}
KEY_SOURCE='https://www.ganternorm.com/fileadmin/user_upload/downloads/technischer%20anhang/technical_information/6885-1.pdf'
KEY_PRODUCT='https://gardette.com/en/catalog/parallel-key-b'
SHIM_SOURCE='https://www.kippusa.com/en-us/products/METRIC/Machine-and-fixture-components/Screws-nuts-washers/Shim-washers-DIN-988/p/agid.32243'
SCREW_SOURCE='https://stock-api.socketscrews.co.uk/files/Final%20ISO%204762%20Website.pdf'
NUT_SOURCE='https://eshop.boellhoff.de/out/media/pdf/ISO_4032_Stahl_8___en.pdf'
WASHER_SOURCE='https://www.indiafastenersparts.com/documents/India_Specs/Metric_Flatwasher_ISO7089.pdf'
RING_SOURCE='https://www.americanring.com/products/ringseries.aspx?series=DIN472&units=metric'
# shaft diameter: groove diameter, groove width, ring thickness, beam, edge margin
EXTERNAL={}
for d,g,m,s,b,e in [(6,5.7,.8,.7,1.3,.5),(8,7.6,1.1,.8,1.5,.6),(10,9.6,1.1,1,1.8,.6),(12,11.5,1.1,1,1.8,.8)]:
    sku=f'EXT{d:03d}0'
    EXTERNAL[d]=dict(d=d,groove=g,m=m,s=s,beam=b,edge=e,code=sku,manufacturer='Springmasters',source=f'https://www.springmasters.com/shop/{sku.lower()}/',standard='DIN 471')
INTERNAL={}
for d,g,m,s in [(13,13.59,1.09,1),(16,16.79,1.09,1),(19,19.99,1.09,1),(22,23.01,1.09,1),(26,27.20,1.30,1.2),(28,29.39,1.30,1.2),(30,31.39,1.30,1.2),(32,33.71,1.30,1.2)]:
    INTERNAL[d]=dict(d=d,groove=g,m=m,s=s,beam=max(1.5,2.2*s),edge=max(2.,2*s),code=f'DIN472-{d:03d}',manufacturer='American Ring',source=RING_SOURCE,standard='DIN 472',edge_note='Margin used by the generator; verify under load')
# d: key width, height, shaft keyway depth, hub keyway depth. Ganter t4 / t2.
KEYS={6:(2,2,1.2,1),8:(2,2,1.2,1),10:(3,3,1.8,1.4),12:(4,4,2.5,1.8)}
KEY_LENGTHS=[8,10,12,14,16,18,20,22,25,28,32,36,40,45,50,56,63,70]
SHIMS={6:12,7:13,8:14,9:15,10:16,11:17,12:18,13:19}
SHIM_THICKNESSES={'.1':'.1 mm','.2':'.2 mm','.5':'.5 mm','1':'1 mm'}
# d, pitch, head diameter, head height, nut AF, nut height, washer ID, OD, thickness.
FASTENERS={}
for d,p,head,k,af,nut,wi,wo,wt in [(3,.5,5.5,3,5.5,2.4,3.2,7,.5),(4,.7,7,4,7,3.2,4.3,9,.8),(5,.8,8.5,5,8,4.7,5.3,10,1),(6,1,10,6,10,5.2,6.4,12,1.6)]:
    FASTENERS[f'M{d}']=dict(d=d,pitch=p,head=head,k=k,af=af,nut=nut,washer_id=wi,washer_od=wo,washer_t=wt,clearance=d+(.4 if d==3 else .5 if d in (4,5) else .6))
LENGTHS=[6,8,10,12,16,20,25,30,35,40,45,50,60,70,80,90,100,110,120]


def options(family,supplied):
    mode=supplied.get('hardware_mode','none')
    if mode not in MODES:raise ValueError('Unknown hardware mode')
    if mode!='none' and family not in SUPPORTED:raise ValueError('Automatic standard hardware is unavailable for this construction')
    screw=supplied.get('hardware_screw','M3');shim=str(supplied.get('hardware_shim','.5'))
    if screw not in FASTENERS or shim not in SHIM_THICKNESSES:raise ValueError('Hardware size is not in the catalog')
    out=dict(hardware_mode=mode,hardware_screw=screw,hardware_shim=shim)
    for k in ('retaining','keys','bolts','shims'):
        value=supplied.get('hardware_'+k,False if family in ('parallel','internal') and k=='bolts' else True)
        if not isinstance(value,bool):raise ValueError('Hardware options require yes/no')
        out['hardware_'+k]=value
    if family in ('parallel','internal') and mode=='standard' and out['hardware_bolts']:
        from pair_assembly import BOLT_REASON
        raise ValueError(BOLT_REASON)
    return out


def prepare(family,supplied):
    s=dict(supplied);o=options(family,s);s.update(o)
    if o['hardware_mode']=='none' or not o['hardware_retaining']:return s
    if s.get('bearing_mode','manual')=='manual':return s
    from catalog import BEARINGS
    b=BEARINGS[s['bearing']];ring=INTERNAL[int(b.D)];needed=b.B+2*(ring['m']+ring['edge'])
    if s['bearing_mode']=='gear':
        s['width']=max(float(s.get('width',8 if family=='cycloidal' else 10)),needed)
        if s.get('variant') in ('two_stage','two_stage_double'):s['width2']=max(float(s.get('width2',10)),needed)
    elif family in ('planetary','cycloidal'):s['plate']=max(float(s.get('plate',3)),needed)
    return s


def support_width(values,b):
    if values.get('hardware_mode')=='standard' and values.get('hardware_retaining'):
        r=INTERNAL[int(b.D)];return b.B+2*(r['m']+r['edge'])
    return b.B
