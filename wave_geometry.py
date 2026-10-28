# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Inextensible pitch-line study mapping; no elastic/contact solution.

Uniform material angle is ellipse arc length / reference pitch radius. Tooth
height is along the local ellipse normal, preserving flank orientation.
Eight Fourier modes integrate the ellipse speed; CPU and GLSL share them.
"""
from math import pi, sin, cos, atan2, hypot
from functools import lru_cache
TAU=2*pi

@lru_cache(maxsize=32)
def arc_coefficients(a,b,rp):
    if not (0<b<=a and (a*a-b*b)/(a*a+b*b)<=.25):
        raise ValueError('Wave map exceeds its verified ellipse aspect ratio domain.')
    n=2048
    speeds=[hypot(a*sin(TAU*(j+.5)/n),b*cos(TAU*(j+.5)/n))/rp for j in range(n)]
    return tuple(2*sum(v*cos(2*k*TAU*(j+.5)/n) for j,v in enumerate(speeds))/n/(2*k) for k in range(1,9))

def eccentric_angle(material,a,b,rp):
    coefficients=arc_coefficients(a,b,rp);t=material
    for _ in range(8):
        residual=t+sum(c*sin(2*k*t) for k,c in enumerate(coefficients,1))-material
        derivative=1+sum(2*k*c*cos(2*k*t) for k,c in enumerate(coefficients,1))
        t-=residual/derivative
    return t

def map_point(material,offset,weight,a,b,rp,flex_angle=0,wave_angle=0):
    u=material+flex_angle; t=eccentric_angle(u-wave_angle,a,b,rp)
    ex,ey=a*cos(t),b*sin(t);nx,ny=cos(t)/a,sin(t)/b;length=hypot(nx,ny)
    ex+=offset*nx/length;ey+=offset*ny/length
    c,s=cos(wave_angle),sin(wave_angle)
    return ((1-weight)*(rp+offset)*cos(u)+weight*(ex*c-ey*s),
            (1-weight)*(rp+offset)*sin(u)+weight*(ex*s+ey*c))

def unmap_point(x,y,weight,a,b,rp):
    """Recover immutable material coordinates for the preview vertex attribute."""
    u=atan2(y,x);d=hypot(x,y)-rp
    for _ in range(12):
        px,py=map_point(u,d,weight,a,b,rp);qx,qy=map_point(u+1e-5,d,weight,a,b,rp)
        nx,ny=map_point(u,d+1,weight,a,b,rp);tx,ty=(qx-px)/1e-5,(qy-py)/1e-5;nx-=px;ny-=py
        det=tx*ny-ty*nx
        if abs(det)<1e-10:raise ValueError('Wave material mapping is singular.')
        fx,fy=px-x,py-y;du=(fx*ny-fy*nx)/det;dd=(tx*fy-ty*fx)/det
        u-=du;d-=dd
        if abs(du)<1e-10 and abs(dd)<1e-9:break
    px,py=map_point(u,d,weight,a,b,rp)
    if hypot(px-x,py-y)>1e-5:raise ValueError('Wave material inversion did not converge.')
    return u,d,weight
