# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""View-only orthographic navigation, independent of mechanism geometry."""
from math import acos, atan2, cos, sin, sqrt

FACES = (('Right', (1,0,0), (0,1,0), (0,0,1)),
         ('Left', (-1,0,0), (0,-1,0), (0,0,1)),
         ('Back', (0,1,0), (-1,0,0), (0,0,1)),
         ('Front', (0,-1,0), (1,0,0), (0,0,1)),
         ('Top', (0,0,1), (1,0,0), (0,1,0)),
         ('Bottom', (0,0,-1), (1,0,0), (0,-1,0)))


def rotate(p, yaw, tilt):
    x,y,z=p;c,s=cos(yaw),sin(yaw);a,b=cos(tilt),sin(tilt)
    return c*x-s*y, a*(s*x+c*y)-b*z, b*(s*x+c*y)+a*z


def orientation(direction):
    """Aim an outward face/edge/corner normal at the camera, with Z up."""
    x,y,z=direction;length=sqrt(x*x+y*y+z*z)
    return (atan2(-x,-y) if x or y else 0.), -acos(max(-1.,min(1.,z/length)))


def pan_delta(dx, dy, radius, zoom, width, height, yaw, tilt):
    """World-space target displacement for an exact screen-pixel drag."""
    scale=.43/max(radius,1e-12)*zoom*max(1,min(width,height))
    x,y=-dx/scale,dy/scale;c,s=cos(yaw),sin(yaw);a,b=cos(tilt),sin(tilt)
    return c*x+s*a*y, -s*x+c*a*y, -b*y


def cube_patches(yaw, tilt, size=116):
    """Visible face tiles; their normals cover all 26 snap orientations."""
    cuts=(-1.,-.62,.62,1.);result=[]
    def project(p):
        x,y,z=rotate(p,yaw,tilt)
        return size/2+size*.255*x,size/2-size*.255*y
    for name,n,u,v in FACES:
        if rotate(n,yaw,tilt)[2]<1e-6:continue
        for i in range(3):
            for j in range(3):
                def point(a,b):return tuple(n[k]+a*u[k]+b*v[k] for k in range(3))
                polygon=[project(point(a,b)) for a,b in ((cuts[i],cuts[j]),(cuts[i+1],cuts[j]),(cuts[i+1],cuts[j+1]),(cuts[i],cuts[j+1]))]
                direction=tuple(n[k]+(i-1)*u[k]+(j-1)*v[k] for k in range(3))
                result.append((name,polygon,direction,(i,j)==(1,1),rotate(n,yaw,tilt)[2]))
    return result


def hit_cube(patches, x, y):
    for name,polygon,direction,central,shade in patches:
        signs=[(b[0]-a[0])*(y-a[1])-(b[1]-a[1])*(x-a[0]) for a,b in zip(polygon,polygon[1:]+polygon[:1])]
        if min(signs)>=-1e-7 or max(signs)<=1e-7:return direction
    return None
