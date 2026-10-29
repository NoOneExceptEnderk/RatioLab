# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Local catalog checked against official NSK pages. Dimensions are in mm.
Open bearings only: no automatic equivalence with ZZ, 2RS, C3 or other brands.
"""
from dataclasses import dataclass,asdict
from math import isfinite

BASE='https://www.nsk.com/engineering/products/bearings/ball-bearings/deep-groove-ball-bearings/'
MINI='extra-small-ball-bearings-and-miniature-ball-bearings-metric-series/'
STANDARD='single-row-deep-groove-ball-bearings/'

@dataclass(frozen=True)
class Bearing:
    code:str
    d:float
    D:float
    B:float
    da_min:float
    Da_max:float
    ra_max:float
    url:str
    manufacturer:str='NSK'
    closure:str='Open, without seals'
    verified:str='2026-10-23'
    @property
    def label(self):return f'{self.code} · {self.d:g} × {self.D:g} × {self.B:g} mm'
    def data(self):return asdict(self)

BEARINGS={}
for code,d,D,B,da,Da,ra in [
 ('624',4,13,5,5.6,11.4,.2),('625',5,16,5,7,14,.3),('626',6,19,6,8,17,.3),('608',8,22,7,10,20,.3),
 ('6000',10,26,8,12,24,.3),('6001',12,28,8,14,26,.3),('6200',10,30,9,14,26,.6),('6201',12,32,10,16,28,.6)]:
    folder,suffix=(MINI,'-esm-md.html') if len(code)==3 else (STANDARD,'-dgbb-sr.html')
    url=BASE+folder+code+suffix
    if code=='624':url=url.replace('/engineering/','/am-en/engineering/')
    BEARINGS[code]=Bearing(code,d,D,B,da,Da,ra,url)

MODES={'manual':'Free dimensions / no catalog','gear':'Bearing in bore','shaft':'Shaft support bearings'}
FITS={'nominal':'Nominal catalog dimensions','custom':'Custom clearance / interference'}
SUPPORTED={'spur','helical','double','planetary','cycloidal','parallel','internal'}

def options(family,supplied):
    mode=supplied.get('bearing_mode','manual');fit=supplied.get('fit','nominal')
    if mode not in MODES or fit not in FITS:raise ValueError('Unknown bearing or fit mode')
    if mode!='manual' and family not in SUPPORTED:raise ValueError('Automatic catalog unavailable for these crossed axes or deforming assemblies.')
    if mode=='gear' and family in ('parallel','internal'):
        from pair_assembly import GEAR_REASON
        raise ValueError(GEAR_REASON)
    code=str(supplied.get('bearing','608' if family=='cycloidal' else '626'))
    if code not in BEARINGS:raise ValueError('Bearing designation is not in the verified catalog')
    result={'bearing_mode':mode,'bearing':code,'fit':fit}
    for key,default,low,high in [('seat_allowance',0,-.08,.8),('shaft_allowance',0,-.8,.08),('shoulder',1,.5,5)]:
        value=float(supplied.get(key,default))
        if not isfinite(value) or not low<=value<=high:raise ValueError(f'{key}: value out of range')
        result[key]=value
    if fit=='nominal':result['seat_allowance']=result['shaft_allowance']=0.
    return result


def prepare(family,supplied):
    """Derive linked dimensions before ordinary geometric validation."""
    s=dict(supplied);o=options(family,s);s.update(o)
    if o['bearing_mode']=='manual':return s
    b=BEARINGS[o['bearing']];mode=o['bearing_mode'];margin=o['shoulder']
    seat=b.D+o['seat_allowance'];shaft=b.d+o['shaft_allowance']
    if seat<=b.Da_max or shaft<=0:raise ValueError('Fit incompatible with the bearing')
    if family in ('spur','helical','double'):
        s['bore']=seat if mode=='gear' else shaft
        s['width']=max(float(s.get('width',10)),b.B+2*margin if mode=='gear' else 1)
    elif family in ('parallel','internal'):
        s['bore']=shaft
        if family=='parallel':s['output_bore']=shaft
    elif family=='planetary':
        if mode=='shaft':s['bore']=shaft;s['plate']=max(float(s.get('plate',3)),b.B+margin)
        else:
            s['width']=max(float(s.get('width',10)),b.B+2*margin)
            if s.get('variant') in ('two_stage','two_stage_double'):s['width2']=max(float(s.get('width2',10)),b.B+2*margin)
    elif family=='cycloidal':
        if mode=='gear':s['bore']=seat;s['width']=max(float(s.get('width',8)),b.B+2*margin)
        else:
            s['input_shaft']=shaft;s['output_shaft']=shaft
            e=float(s.get('eccentric',1.2))
            s['bore']=max(float(s.get('bore',12)),2*(shaft/2+e+.65)/.72)
            s['plate']=max(float(s.get('plate',3)),b.B+margin)
    return s


def selected(values):return BEARINGS[values['bearing']] if values.get('bearing_mode','manual')!='manual' else None
