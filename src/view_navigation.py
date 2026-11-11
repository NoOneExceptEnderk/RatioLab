# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""View-only orthographic navigation, independent of mechanism geometry."""
from math import acos, atan2, cos, sin, sqrt, pi, log, exp


def camera_frame(start, end, fraction):
    """Smooth finite camera transition; exact endpoints and shortest angle wraps."""
    t=max(0.,min(1.,fraction))
    if t==0:return start
    if t==1:return end
    t=t*t*t*(10+t*(-15+6*t))
    angles=tuple(a+((b-a+pi)%(2*pi)-pi)*t for a,b in zip(start[:3],end[:3]))
    zoom=exp(log(start[3])*(1-t)+log(end[3])*t)
    center=tuple(a+(b-a)*t for a,b in zip(start[4],end[4]))
    radius=exp(log(start[5])*(1-t)+log(end[5])*t)
    return (*angles,zoom,center,radius)

FACES = (('Right', (1,0,0), (0,1,0), (0,0,1)),
         ('Left', (-1,0,0), (0,-1,0), (0,0,1)),
         ('Back', (0,1,0), (-1,0,0), (0,0,1)),
         ('Front', (0,-1,0), (1,0,0), (0,0,1)),
         ('Top', (0,0,1), (1,0,0), (0,1,0)),
         ('Bottom', (0,0,-1), (1,0,0), (0,-1,0)))


def rotate(p, yaw, tilt, roll=0.):
    x,y,z=p;c,s=cos(yaw),sin(yaw);a,b=cos(tilt),sin(tilt)
    q=(c*x-s*y, a*(s*x+c*y)-b*z, b*(s*x+c*y)+a*z)
    if not roll:return q
    c,s=cos(roll),sin(roll)
    return c*q[0]-s*q[1],s*q[0]+c*q[1],q[2]


def orientation(direction):
    """Aim an outward face/edge/corner normal at the camera, with Z up."""
    x,y,z=direction;length=sqrt(x*x+y*y+z*z)
    return (atan2(-x,-y) if x or y else 0.), -acos(max(-1.,min(1.,z/length)))


def pan_delta(dx, dy, radius, zoom, width, height, yaw, tilt, roll=0.):
    """World-space target displacement for an exact screen-pixel drag."""
    scale=.43/max(radius,1e-12)*zoom*max(1,min(width,height))
    x,y=-dx/scale,dy/scale;c,s=cos(yaw),sin(yaw);a,b=cos(tilt),sin(tilt)
    if roll:
        cr,sr=cos(roll),sin(roll);x,y=cr*x+sr*y,-sr*x+cr*y
    return c*x+s*a*y, -s*x+c*a*y, -b*y


def cube_patches(yaw, tilt, size=116, roll=0.):
    """Visible face tiles; their normals cover all 26 snap orientations."""
    cuts=(-1.,-.62,.62,1.);result=[]
    def project(p):
        x,y,z=rotate(p,yaw,tilt,roll)
        return size/2+size*.255*x,size/2-size*.255*y
    for name,n,u,v in FACES:
        if rotate(n,yaw,tilt,roll)[2]<1e-6:continue
        for i in range(3):
            for j in range(3):
                def point(a,b):return tuple(n[k]+a*u[k]+b*v[k] for k in range(3))
                polygon=[project(point(a,b)) for a,b in ((cuts[i],cuts[j]),(cuts[i+1],cuts[j]),(cuts[i+1],cuts[j+1]),(cuts[i],cuts[j+1]))]
                direction=tuple(n[k]+(i-1)*u[k]+(j-1)*v[k] for k in range(3))
                result.append((name,polygon,direction,(i,j)==(1,1),rotate(n,yaw,tilt,roll)[2]))
    return result


def plane_axes(normal, up):
    """Orthonormal paper axes, independent of any world-axis convention."""
    def unit(v):
        length=sqrt(sum(x*x for x in v))
        if length<1e-12:raise ValueError('Tooth view needs independent plane axes.')
        return tuple(x/length for x in v)
    n=unit(normal);along=sum(a*b for a,b in zip(up,n))
    u=unit(tuple(a-along*b for a,b in zip(up,n)))
    right=(u[1]*n[2]-u[2]*n[1],u[2]*n[0]-u[0]*n[2],u[0]*n[1]-u[1]*n[0])
    return right,u,n


def paper_orientation(normal, up):
    """Face the plane normally and put its local up vector at screen top."""
    _,up,normal=plane_axes(normal,up)
    yaw,tilt=orientation(normal)
    x,y,_=rotate(up,yaw,tilt)
    return yaw,tilt,atan2(x,y)


def plane_coordinates(point, target, axes):
    delta=tuple(a-b for a,b in zip(point,target))
    return tuple(sum(a*b for a,b in zip(delta,axis)) for axis in axes)


def bounds_in_front(bounds, target, axes, radius):
    """Conservative rejection only; real triangles decide occlusion."""
    from itertools import product
    rows=[plane_coordinates(q,target,axes) for q in product(*zip(*bounds))]
    return (max(q[2] for q in rows)>radius*1e-7
            and all(max(q[i] for q in rows)>=-radius and min(q[i] for q in rows)<=radius for i in (0,1)))


def triangle_in_front(triangle, target, axes, radius):
    """Clip a real surface triangle to the focused square and its front half-space.

    Testing real cap triangles preserves holes; a component's bounding box is
    never treated as an occluding surface. Edge-only contact has no pixel area.
    """
    polygon=[plane_coordinates(q,target,axes) for q in triangle]
    for axis,sign,limit in ((0,1,radius),(0,-1,radius),(1,1,radius),(1,-1,radius),(2,-1,-radius*1e-7)):
        if not polygon:return False
        clipped=[]
        for a,b in zip(polygon,polygon[1:]+polygon[:1]):
            da=sign*a[axis]-limit;db=sign*b[axis]-limit
            if da<=0:clipped.append(a)
            if (da<0<db) or (db<0<da):
                f=da/(da-db);clipped.append(tuple(x+f*(y-x) for x,y in zip(a,b)))
        polygon=clipped
    area=abs(sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(polygon,polygon[1:]+polygon[:1])))/2
    return area>radius*radius*1e-12


def hit_cube(patches, x, y):
    for name,polygon,direction,central,shade in patches:
        signs=[(b[0]-a[0])*(y-a[1])-(b[1]-a[1])*(x-a[0]) for a,b in zip(polygon,polygon[1:]+polygon[:1])]
        if min(signs)>=-1e-7 or max(signs)<=1e-7:return direction
    return None
