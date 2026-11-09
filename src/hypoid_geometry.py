# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Custom hypoid pair: pinion envelope generated from a spherical spiral wheel.

Nie et al. DOI 10.1177/16878132241228195, equations 7–8. The chosen master
surface/blank is custom, not the paper's manufacturing surface or machine setup.
Axes: wheel +Z through origin; pinion +X through (0, offset, 0). Units mm/rad.
"""
SPECS = [
    ('module', 'Wheel reference module [mm]', 2, .5, 6, .1),
    ('pinion', 'Pinion teeth', 20, 16, 80, 1),
    ('wheel', 'Wheel teeth', 40, 16, 120, 1),
    ('offset', 'Signed shaft offset [mm]', 2, -50, 50, .1),
    ('width', 'Wheel reference face width [mm]', 8, 2, 25, .5),
    ('spiral_angle', 'Master-wheel spiral angle [°]', 35, 25, 45, 1),
    ('pressure', 'Master transverse pressure angle [°]', 20, 17.5, 25, .5),
    ('backlash', 'Wheel reference tangential backlash [mm]', .15, 0, 1, .01),
    ('bore', 'Pinion bore [mm]', 6, 0, 100, .5),
    ('output_bore', 'Wheel bore [mm]', 8, 0, 100, .5),
]
CATALOG_REASON = ('Custom hypoid pair: two bored gear blanks. Complete shafts, '
                  'bearing seats, supports and retention in CAD; automatic catalog hardware is unavailable.')
REFINEMENT = .003


from bevel_geometry import SphericalProfile
from rust_geometry import call, call_geometry


def check_contour(points):
    return call('hypoid_generator',dict(action='check_contour',points=points))


class Interval:
    """Compatibility value for Rust's outward-expanded float/libm enclosure."""
    def __init__(self,lo,hi=None):self.lo=lo;self.hi=lo if hi is None else hi
    def _data(self):return dict(lo=self.lo,hi=self.hi)
    def _op(self,action,b=None):
        row=call('construction_enclosure',dict(action=action,lhs=self._data(),rhs=None if b is None else interval(b)._data()))
        return Interval(**row)
    def __add__(self,b):return self._op('add',b)
    __radd__=__add__
    def __neg__(self):return self._op('neg')
    def __sub__(self,b):return self._op('sub',b)
    def __rsub__(self,b):return interval(b)._op('sub',self)
    def __mul__(self,b):return self._op('mul',b)
    __rmul__=__mul__
    def __truediv__(self,b):return self._op('div',b)
    def __rtruediv__(self,b):return interval(b)._op('div',self)
    def square(self):return self._op('square')
    def sqrt(self):return self._op('sqrt')
    def sin(self):return self._op('sin')
    def cos(self):return self._op('cos')
    def acos(self):return self._op('acos')
    def atan(self):return self._op('atan')


def interval(x):return x if isinstance(x,Interval) else Interval(x)


class Jet:
    """Compatibility value and first derivative, with operations in Rust."""
    def __init__(self,value,derivative=0):self.v=interval(value);self.d=interval(derivative)
    @classmethod
    def _from_data(cls,row):return cls(Interval(**row['v']),Interval(**row['d']))
    def _data(self):return dict(v=self.v._data(),d=self.d._data())
    def _op(self,action,b=None):
        row=call('construction_enclosure',dict(action=action,jet=True,lhs=self._data(),rhs=None if b is None else jet(b)._data()))
        return Jet._from_data(row)
    def __add__(self,b):return self._op('add',b)
    __radd__=__add__
    def __neg__(self):return self._op('neg')
    def __sub__(self,b):return self._op('sub',b)
    def __rsub__(self,b):return jet(b)._op('sub',self)
    def __mul__(self,b):return self._op('mul',b)
    __rmul__=__mul__
    def __truediv__(self,b):return self._op('div',b)
    def square(self):return self._op('square')
    def sqrt(self):return self._op('sqrt')
    def sin(self):return self._op('sin')
    def cos(self):return self._op('cos')
    def acos(self):return self._op('acos')
    def atan(self):return self._op('atan')


def jet(x):return x if isinstance(x,Jet) else Jet(x)


class Generator:
    def __init__(self,v):
        self.v=v
        row=self._call('prepare')
        row['cutter']=SphericalProfile(**row['cutter']);row['master']=SphericalProfile(**row['master'])
        self.__dict__.update(row)
    def _call(self,action,**parameters):return call('hypoid_generator',dict(values=self.v,action=action,**parameters))
    def at_x(self,theta,x,side):return tuple(self._call('at_x',theta=theta,x=x,side=side))
    def at_r(self,theta,R,side):return tuple(self._call('at_r',theta=theta,radius=R,side=side))
    def point(self,theta,x,side):return tuple(self._call('point',theta=theta,x=x,side=side))
    def root(self,x):return self._call('root',x=x)
    def _jet(self,low,high,side,axial=None,radius=None):
        return tuple(Jet._from_data(row) for row in self._call('jet',low=low,high=high,side=side,axial=None if axial is None else [axial.lo,axial.hi],radius=radius))
    def _certify_regularity(self):return self.regularity
    def _certify_tracks(self):return self.engagement
    def _check_bores(self):return self._call('check_bores')
    def _top_angle(self):return self._call('top_angle')
    def _constants(self,theta,side):return tuple(self._call('constants',theta=theta,side=side))
    def _solve(self,A,B,C,side):return self._call('solve_branch',A=A,B=B,C=C,side=side)
    def outline(self,x,angles):return [tuple(p) for p in self._call('outline',x=x,angles=angles)]
    def grids(self):return tuple(self._call('grids'))


def build(d):
    from geometry import part_from_kernel
    v=d.values;result=call_geometry('construction_hypoid',dict(values=v))
    d.parts.extend(part_from_kernel(p['name'],p) for p in result['parts'])
    d.analysis.update(result['analysis'])
    q=result['analysis']['hypoid'];xs=q['pinion_axial_stations_mm'];radii=q['master_cone_stations_mm']
    d.metrics.extend([f"Shaft offset: {v['offset']:+g} mm · 90° skew shaft directions",
                      f"Hypoid ideal engagement lower bound: {q['engagement']['phase_span_lower_bound_teeth']:.6f} wheel tooth pitches",
                      f'Generated pinion: {len(xs)} axial stations · master wheel: {len(radii)} cone stations'])
    d.notes.extend([
        'Custom hypoid construction: pinion is generated as the conjugate envelope of a spherical-involute logarithmic spiral master wheel. Not a Gleason/AGMA production tooth system, machine settings or stock-compatible part.',
        'Reference wheel module and cone size define the chosen master blank, not a standardized hypoid normal module or rolling pitch cone. Master addendum is 0.7 module; root and pinion crest are linked to the generated envelope.',
        'Positive speeds use pinion world +X through (0, offset, 0) and wheel world +Z through origin. Offset sign mirrors the construction; local trace hands are derived. Offset zero is the degenerate generated bevel limit.',
        'Outward-expanded float/libm intervals check analytic envelope regularity and connected mean-radius contact tracks. Phase spans are sufficient conservative lower bounds, not loaded tooth contact or continuous mesh-clearance certification.',
        'Shared surfaces use finite quarter/midpoint refinement at 0.003 mm; this is not a proven whole-surface error or manufacturing tolerance. Crest/root relief are nonworking custom constructions. Check sampled interference and complete supports, lubrication, strength and retention in CAD.',
    ])
    d.requirements.append(CATALOG_REASON)
