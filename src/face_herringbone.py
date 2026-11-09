# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Joined face-pinion envelope, including the cusp sweep and concave trimming.

NASA/CR2000-209909 eq21–24,63–68 supplies the moving involute construction.
The explicit cusp/upper-lower envelope derivation is in technical/face-gears.md.
This is a nominal equal-count construction, not an industrial cutter/LTCA model.
"""
from face_geometry import REFINEMENT


class JoinedSurface:
    """Adapter to the Rust continuous swept envelope, cusp and concave trim."""
    def __init__(self,g,state=None):
        self.g=g
        if state is None:state=g._call('prepare')['joined_surface']
        if state is None:raise ValueError('No joined face surface in the zero-helix limit.')
        self.__dict__.update(state)
    def _call(self,action,**parameters):return self.g._call('joined_'+action,**parameters)
    def inverse(self,R,h,side,band):
        row=self._call('inverse',radius=R,h=h,side=side,band=band)
        return None if row is None else (tuple(row[0]),row[1])
    def candidates(self,R,h,side):return [tuple(row) for row in self._call('candidates',radius=R,h=h,side=side)]
    def at(self,R,h,side):return tuple(self._call('at',radius=R,h=h,side=side))
    def anchors(self,h):return self._call('anchors',h=h)
    def radius(self,t,h):return self._call('radius',t=t,h=h)
    def polar(self,t,h,side):return tuple(self._call('polar',t=t,h=h,side=side))
    def point(self,t,h,side):return tuple(self._call('point',t=t,h=h,side=side))
    def profile(self,t,hs,k,segments):return [tuple(p) for p in self._call('profile',t=t,hs=hs,k=k,segments=segments)]
    def grids(self):return tuple(self._call('grids'))
    def engagement(self):return self._call('engagement')
    def info(self):return self._call('info')
