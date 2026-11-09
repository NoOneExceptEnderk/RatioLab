# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Orthogonal face-gear envelope. NASA/CR2000-209909 eq21–24,63–69;
NASA/CR2005-213443 sec2–3 eq3–4,15–18. See docs/technical/face-gears.md.
Ideal equal-count pinion/shaper; custom stub crest and nonworking root extension.
"""
from rust_geometry import call, call_geometry
from hypoid_geometry import Interval

VARIANTS={'spur':'Spur pinion','helical':'Helical pinion',
          'double_helical':'Double helical pinion'}
SPECS=[('module','Normal pinion module [mm]',2,.5,6,.1),
       ('pinion','Pinion teeth',24,16,80,1),('wheel','Face wheel teeth',72,24,160,1),
       ('width','Band width along pinion axis [mm]',8,3,20,.5),
       ('offset','Signed shaft offset [mm]',0,-50,50,.1),
       ('radial_setting','Band setting beyond reference radius [mm]',4,0,40,.1),
       ('base','Face wheel backing thickness [mm]',6,1,30,.5),
       ('face_addendum','Face addendum coefficient',.65,.35,1,.05),
       ('pressure','Normal pressure angle [°]',20,17.5,30,.5),
       ('backlash','Pinion reference pair backlash [mm]',.15,0,1,.01),
       ('bore','Pinion bore [mm]',6,0,100,.5),
       ('output_bore','Face wheel bore [mm]',10,0,150,.5)]
REFINEMENT=.003
CATALOG_REASON=('Face gears generate a bored pinion and a face-wheel blank. '
                'Complete shafts, supports, bearing seats and retention in CAD; automatic catalog hardware is unavailable.')


class Generator:
    """Read-only compatibility view of the prepared Rust face generator."""
    def __init__(self,v):
        from geometry import part_from_kernel
        self.v=v;row=self._call('prepare')
        row['pinion']=part_from_kernel('Face_pinion',row['pinion'])
        joined=row.pop('joined_surface')
        self.__dict__.update(row)
        from face_herringbone import JoinedSurface
        self.joined_surface=JoinedSurface(self,joined) if joined else None
    def _call(self,action,**parameters):return call('face_generator',dict(values=self.v,action=action,**parameters))
    def twist(self,x):return self._call('twist',x=x)
    def scalar(self,y,x,h,side,k):return tuple(self._call('scalar',y=y,x=x,h=h,side=side,k=k))
    def solve(self,x,h,side,k):return tuple(self._call('solve',x=x,h=h,side=side,k=k))
    def contact(self,x,h,side,k):return tuple(self._call('contact',x=x,h=h,side=side,k=k))
    def coordinates(self,x,h,side,y):return tuple(self._call('coordinates',x=x,h=h,side=side,y=y))
    def point(self,x,h,side,k):return tuple(self._call('point',x=x,h=h,side=side,k=k))
    def _cell(self,a,b,c,d,side,k):return tuple(Interval(**row) for row in self._call('cell',a=a,b=b,c=c,d=d,side=side,k=k))
    def enclosure(self,X,H,Y,side,k):return tuple(Interval(**row) for row in self._call('enclosure',X=X._data(),H=H._data(),Y=Y._data(),side=side,k=k))
    def _certify(self,band):return self._call('certify',band=band)
    def _check_widths(self):return self._call('check_widths')
    def _engagement(self):return self._call('engagement')
    def profile(self,x,hs,k,segments):return [tuple(p) for p in self._call('profile',x=x,hs=hs,k=k,segments=segments)]
    def grids(self):return tuple(self._call('grids'))
    def mesh(self,hs,grids,segments,profile=None):
        if profile is not None and (self.joined_surface is None or profile!=self.joined_surface.profile):
            raise ValueError('Face mesh requires its native regular or joined profile.')
        mesh,bottom=self._call('mesh',hs=hs,grids=grids,segments=segments,joined=profile is not None)
        return [[[tuple(p) for p in loop] for loop in face] for face in mesh],bottom


def build(d):
    from geometry import part_from_kernel
    result=call_geometry('construction_face',dict(values=d.values))
    d.parts.extend(part_from_kernel(p['name'],p) for p in result['parts'])
    d.analysis.update(result['analysis'])
    q=result['analysis']['face_gear']
    d.metrics.extend([f"Face gear shaft angle: 90° · reference radii {q['pinion_reference_radius_mm']:.6f} / {q['wheel_reference_radius_mm']:.6f} mm",
        f"Ideal connected-track engagement lower bound: {q['engagement']['phase_span_lower_bound_teeth']:.6f} tooth pitches",
        f"Face wheel: {q['tooth_band_count']} tooth band(s) · {q['face_mesh_triangles']} shared triangles",
        f"Face shaft offset: {q['shaft_offset_mm']:+.6f} mm · shortest axis distance {q['shortest_axis_distance_mm']:.6f} mm"])
    d.notes.extend(['Face wheel is generated as the envelope of the matching cylindrical involute pinion, using the normal-relative-velocity condition. Equal pinion/shaper tooth counts give ideal line contact; industrial localized contact and manufacturing cutter settings are not reproduced.',
        'Normal module/pressure refer to the pinion. Band setting locates the pinion beyond the reference wheel radius; band width is along the pinion shaft. Actual projected tooth-band ends can curve slightly. The circular backing blank includes untoothed inner/outer lands.',
        'Face crest uses the selected stub addendum. Nonworking root relief continues the virtual generating involute beyond the actual pinion tip; it is not a generated cutter-corner fillet. Pinion and face-space allowances split the reference pair backlash.',
        'Numerical float/libm Krawczyk enclosures and implicit derivatives check separated branches, analytic regularity, flank ordering and pointing limits. Connected ideal contact spans are sufficient lower bounds, not loaded contact or continuous sampled-solid clearance proofs.',
        'Face surfaces use finite quarter/midpoint refinement at 0.003 mm; transverse pinion profiles retain their existing sampling. Shared explicit triangles are used for preview, collision inspection, STL and faceted STEP. No global surface-error, manufacturing, strength or durability certification.',
        'Positive pinion speed is about world +X through (0,offset,2rp); positive face speed is about world +Z. Axis directions remain 90 degrees. Zero offset gives intersecting axes; nonzero offset gives skew axes separated by its absolute value. The wheel envelope is regenerated for the signed offset. Swapping roles preserves the physical geometry and bores.',
        'Supported absolute offset is below half the reference wheel radius, using NASA/CR2000-209909 eq69 as a conservative layout bound for all offered pinion types. Geometry checks can impose tighter limits; this bound does not establish sliding losses, heat or loaded contact.'])
    if d.values['variant']=='double_helical' and d.values.get('double_style')=='joined':
        d.notes.append('Joined double helix uses one continuous tooth band. Convex pinion cusp edges generate the central transition; overlapping concave envelopes are trimmed at their intersection. Joined teeth use a common circular annular domain inside both supported pinion spans. Smooth patches retain numerical enclosures; cusp/trim root solves and finite surface refinement do not establish a global joined-surface error or manufacturing certificate. No equal loading or net axial-force cancellation is established.')
    elif q['tooth_band_count']>1:d.notes.append('Double helical uses two separated, opposite-handed working bands and a continuous pinion core. One complete track per flank suffices; equal band loading or net axial-force cancellation is not established.')
    d.requirements.append(CATALOG_REASON)
