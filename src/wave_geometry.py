# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Prescribed inextensible pitch-line mapping; no elastic solution.

Uniform material angle is ellipse arc length / reference pitch radius. Tooth
height is along the local ellipse normal, preserving flank orientation.
Eight Fourier modes integrate the ellipse speed; CPU and GLSL share them.
"""
from math import pi, sin, cos, atan2, hypot, isfinite
from functools import lru_cache
TAU=2*pi
MATERIAL_RECONSTRUCTION_EPSILON=1e-7  # mm, protocol consistency, not manufacturing accuracy


def _finite(values):
    try:return all(isfinite(v) for v in values)
    except (TypeError,ValueError):return False

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


def material_vertices(part,check=lambda:None):
    """Immutable shared-vertex references for the explicitly prescribed map."""
    from solid_geometry import point
    metadata=part.profile_metadata.get('wave_mapping',{})
    if not isinstance(metadata,dict) or metadata.get('schema')!='ratiolab.wave-map/1' or part.axis_x or part.frame:
        raise ValueError('Unknown deformation: supported strain-wave material coordinates are required')
    axes=metadata.get('ellipse_axes_mm')
    if not isinstance(axes,(tuple,list)) or len(axes)!=2:raise ValueError('Invalid strain-wave material map dimensions')
    shape=(*axes,metadata.get('pitch_radius_mm'))
    if len(shape)!=3 or not _finite(shape):raise ValueError('Invalid strain-wave material map dimensions')
    a,b,rp=shape
    result={}
    count=0
    for station in part.stations:
        check()
        loops=[station['outer']]+station['holes']
        refs=[station.get('material_outer',[])]+station.get('material_holes',[])
        if len(loops)!=len(refs):raise ValueError('Incomplete strain-wave material reference loops')
        for loop,reference in zip(loops,refs):
            if len(loop)!=len(reference):raise ValueError('Incomplete strain-wave material vertex references')
            for xy,material in zip(loop,reference):
                count+=1
                if count%128==0:check()
                if not isinstance(material,(list,tuple)) or len(material)!=3 or not _finite(material) or not 0<=material[2]<=1:
                    raise ValueError('Invalid strain-wave material coordinates')
                vertex=point(part,xy,station['z'],0)
                x,y=map_point(*material,a,b,rp)
                if hypot(x+part.center[0]-vertex[0],y+part.center[1]-vertex[1])>MATERIAL_RECONSTRUCTION_EPSILON:
                    raise ValueError('Strain-wave material references do not reconstruct the nominal shared surface')
                previous=result.get(vertex)
                if previous is not None and (abs((previous[0]-material[0]+pi)%TAU-pi)>1e-8 or abs(previous[1]-material[1])>1e-8 or abs(previous[2]-material[2])>1e-8):
                    raise ValueError('Conflicting strain-wave material references at a shared vertex')
                result[vertex]=tuple(material)
    if not result:raise ValueError('Missing strain-wave material coordinates')
    return result


def posed_vertices(part,references,deformation,check=lambda:None):
    """Map original vertex references at a pose, never a previously posed mesh."""
    metadata=part.profile_metadata.get('wave_mapping',{})
    if not isinstance(metadata,dict) or not isinstance(metadata.get('ellipse_axes_mm'),(tuple,list)):
        raise ValueError('Unknown strain-wave deformation metadata')
    if not isinstance(deformation,(tuple,list)) or len(deformation)!=7 or not _finite(deformation):
        raise ValueError('Unknown or nonfinite strain-wave deformation')
    flex,wave,a,b,rp,length,diaphragm=deformation
    expected=(*metadata.get('ellipse_axes_mm',()),metadata.get('pitch_radius_mm'),metadata.get('body_length_mm'),metadata.get('diaphragm_mm'))
    if (a,b,rp,length,diaphragm)!=expected:
        raise ValueError('Strain-wave deformation does not match its validated material map')
    result={}
    for i,(vertex,material) in enumerate(references.items()):
        if i%128==0:check()
        x,y=map_point(*material,a,b,rp,flex,wave)
        result[vertex]=(x+part.center[0],y+part.center[1],vertex[2])
    return result
