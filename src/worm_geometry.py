# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Rust ZA/ZI helicoid envelope; source conventions in docs/technical/worm.md."""
from rust_geometry import call

CHORD=.005


class WormSurface:
    def __init__(self,values):
        self._values=dict(values)
        self.__dict__.update(call('worm_surface',dict(values=self._values)))

    def half_angle(self,radius,*,cutter=False):
        return call('worm_half',dict(values=self._values,radius=radius,cutter=cutter))

    def half_derivative(self,radius):
        return call('worm_derivative',dict(values=self._values,radius=radius))

    def generator(self,radius,height,side):
        return tuple(tuple(p) for p in call('worm_generator',dict(values=self._values,radius=radius,height=height,side=side)))

    def contact(self,radius,height,side):
        p,original,normal,phi=call('worm_contact',dict(values=self._values,radius=radius,height=height,side=side))
        return tuple(p),tuple(original),tuple(normal),phi


class WheelSection:
    def __init__(self,surface,height):
        self.surface=surface
        self._state=call('worm_section',dict(values=surface._values,height=height))
        self.__dict__.update({k:v for k,v in self._state.items() if k!='surface'})
        for key in ('starts','ends','flank_ends'):
            setattr(self,key,{int(k):v for k,v in getattr(self,key).items()})

    def angle(self,p):
        return call('worm_section_angle',dict(section=self._state,point=p))

    def _curve(self,index,t):
        return tuple(call('worm_section_curve',dict(section=self._state,index=index,t=t)))

    def flank(self,side,t):
        return self._curve(0,t) if side==-1 else self._curve(4,1-t)

    def fillet(self,side,t):
        return self._curve(1,t) if side==-1 else self._curve(3,1-t)

    def arc(self,root,t):
        return self._curve(2 if root else 5,t)

    def curves(self):
        return [lambda t,index=index:self._curve(index,t) for index in range(6)]

    def gap(self,counts):
        return [tuple(p) for p in call('worm_section_gap',dict(section=self._state,counts=counts))]


def wheel_sections(values,*,hole_vertices=0):
    result=call('worm_wheel_sections',dict(values=values,hole_vertices=hole_vertices))
    return [(z,[tuple(p) for p in points]) for z,points in result['sections']],result['metadata']
