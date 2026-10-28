# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Surface picking and dimensions on the shared sampled geometry, in mm.

Camera is orthographic, as in preview3d.VERTEX. No AABB is a pick surface.
Nonrigid display poses are deliberately unavailable; nominal geometry remains
inspectable. There is no analytic CAD diameter or surface-distance claim.
"""
from dataclasses import replace
from math import cos, sin, sqrt
from collision_geometry import ray_triangle, sub, add, mul, bounds
from solid_geometry import faces
from stl_export import triangulate
from motion import transform


def displayed_part(design, index, exploded=False):
    p=design.parts[index]
    if not exploded:return p
    mid=sum(q.z+q.width/2 for q in design.parts)/len(design.parts)
    offset=(p.z+p.width/2-mid)*1.1
    if p.role!='gear':offset+=8 if p.z+p.width/2>=mid else -8
    return replace(p,z=p.z+offset,center=tuple(v*1.12 for v in p.center))


def triangles(part):
    return tuple(t for face in faces(part) for t in triangulate(face))


def dimensions(part):
    pts=[q for face in faces(part) for loop in face for q in loop]
    lo,hi=bounds(pts)
    return dict(min_mm=lo,max_mm=hi,size_mm=tuple(b-a for a,b in zip(lo,hi)))


def orbit(q,yaw,tilt):
    c,s=cos(yaw),sin(yaw);a,b=cos(tilt),sin(tilt)
    x,y,z=q;xx,yy=c*x-s*y,s*x+c*y
    return xx,a*yy-b*z,b*yy+a*z


def unorbit(q,yaw,tilt):
    x,y,z=q;a,b=cos(tilt),sin(tilt);c,s=cos(yaw),sin(yaw)
    yy,zz=a*y+b*z,-b*y+a*z
    return c*x+s*yy,-s*x+c*yy,zz


def project(q,center,radius,zoom,yaw,tilt,width,height):
    p=orbit(sub(q,center),yaw,tilt);aspect=max(width,1)/max(height,1)
    scale=.86/radius*zoom
    return (width*(1+p[0]*scale/max(aspect,1))/2,height*(1-p[1]*scale*min(aspect,1))/2)


def ray(x,y,center,radius,zoom,yaw,tilt,width,height):
    aspect=max(width,1)/max(height,1);scale=.86/radius*zoom
    local=((2*x/max(width,1)-1)*max(aspect,1)/scale,(1-2*y/max(height,1))/(scale*min(aspect,1)),4*radius)
    return add(center,unorbit(local,yaw,tilt)),unorbit((0,0,-1),yaw,tilt)


def pick(origin,direction,surfaces,section_y=None,max_distance=None):
    """Return frontmost (source_index, world point, triangle) or None.

    Section removes y>center.y fragments exactly like the renderer. It does
    not invent a filled cutting cap, which the preview does not draw either.
    """
    best=None
    for index,ts in surfaces:
        for t in ts:
            distance=ray_triangle(origin,direction,t)
            if distance is None or distance<0 or (max_distance is not None and distance>max_distance) or (best and distance>=best[0]):continue
            q=add(origin,mul(direction,distance))
            if section_y is not None and q[1]>section_y:continue
            best=(distance,index,q,t)
    return (best[1],best[2],best[3]) if best else None


def posed(ts,plan,index,phase):
    matrix=plan.matrix(index,phase)
    return tuple(tuple(transform(matrix,q) for q in t) for t in ts)


def distance(a,b):return sqrt(sum((x-y)**2 for x,y in zip(a,b)))
