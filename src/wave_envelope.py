# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Outer swept envelope for the prescribed pitch-arc strain-wave map.

Every reference-profile edge, corner and trajectory branch contributes at each
ring angle. Angular cells conservatively enclose the sampled sweep patches;
their numerical relief is reported separately from physical tooth backlash.
No finite element elasticity or production tooling is implied by this model.
"""
from functools import lru_cache
from math import pi,sin,cos,atan2,hypot,ceil,floor
from wave_geometry import arc_coefficients

TAU=2*pi
ANGULAR_CELLS=128
CONVERGENCE=.002


def _sweep(reference,z,a,b,rp,nt,nq):
    g=(z+2)/z;pitch=TAU/(z+2);step=pitch/ANGULAR_CELLS
    coefficient=arc_coefficients(a,b,rp)
    refs=[]
    for p,q in zip(reference,reference[1:]):
        for j in range(nq):
            x=p[0]+(q[0]-p[0])*j/nq;y=p[1]+(q[1]-p[1])*j/nq
            refs.append((atan2(y,x),hypot(x,y)-rp))
    refs.append((atan2(reference[-1][1],reference[-1][0]),hypot(*reference[-1])-rp))
    if len(refs)*(nt+1)>1500000:
        raise ValueError('Strain-wave envelope exceeds its bounded sweep grid; reduce tooth/profile complexity.')
    radial=[0.]*ANGULAR_CELLS;witnesses=[]
    def segment(old,new):
        th0,P=old;th1,Q=new
        low,high=sorted((th0,th1))
        dx,dy=Q[0]-P[0],Q[1]-P[1]
        cross=P[0]*Q[1]-P[1]*Q[0]
        for index in range(ceil((low+pitch/2)/step),floor((high+pitch/2)/step)+1):
            theta=-pitch/2+index*step
            den=cos(theta)*dy-sin(theta)*dx
            if abs(den)<=1e-14:continue
            radius=cross/den
            if radius<=0:continue
            j=index%ANGULAR_CELLS
            radial[j]=max(radial[j],radius)
    previous=None
    for k in range(nt+1):
        t=-pi/2+pi*k/nt;c,s=cos(t),sin(t)
        norm=hypot(c/a,s/b);nx,ny=c/a/norm,s/b/norm
        xi=t+sum(v*sin(2*j*t) for j,v in enumerate(coefficient,1))
        row=[]
        for i,(u,d) in enumerate(refs):
            ex,ey=a*c+d*nx,b*s+d*ny
            theta=u/g+atan2(ey,ex)-xi/g
            radius=hypot(ex,ey)
            current=theta,(radius*cos(theta),radius*sin(theta))
            witnesses.append((theta,radius))
            row.append(current)
            if i:segment(row[i-1],current)
            if previous:
                segment(previous[i],current)
                if i:
                    # Both diagonals enclose either triangulation and retain
                    # folds of the sampled two-parameter sweep patch.
                    segment(previous[i-1],current)
                    segment(previous[i],row[i-1])
        previous=row
    if min(radial)<=0:
        raise ValueError('Strain-wave sweep does not cover every ring angle.')
    # For a chord with endpoint radii Ra,Rb, inverse radial distance is
    # sin(theta_b-theta)/(sin(step)*Ra) + sin(theta-theta_a)/(sin(step)*Rb).
    # Scale only as much as each interior grid witness requires. Clipped
    # segment endpoints on cell boundaries are already bounded by radial[].
    # Each chord half-plane then contains every clipped sweep segment.
    scale=[1.]*ANGULAR_CELLS
    denominator=sin(step)
    for theta,radius in witnesses:
        theta=(theta+pitch/2)%pitch-pitch/2
        j=min(ANGULAR_CELLS-1,floor((theta+pitch/2)/step));lo=-pitch/2+j*step
        A=sin(lo+step-theta)/denominator;B=sin(theta-lo)/denominator
        scale[j]=max(scale[j],radius*(A/radial[j]+B/radial[(j+1)%ANGULAR_CELLS]))
    enclosed=[radial[j]*max(scale[j-1],scale[j]) for j in range(ANGULAR_CELLS)]
    return radial,enclosed


@lru_cache(maxsize=32)
def _profile(reference,z,a,b,rp):
    previous,_=_sweep(reference,z,a,b,rp,128,1)
    nt,nq=256,2
    for _ in range(4):
        radial,enclosed=_sweep(reference,z,a,b,rp,nt,nq)
        change=max(abs(x-y) for x,y in zip(previous,radial))
        if change<=CONVERGENCE:break
        previous=radial;nt*=2;nq*=2
    else:
        raise ValueError('Strain-wave swept envelope did not converge within its bounded grid.')
    depth=max(radial)-min(radial)
    if depth<.1*(2*rp/z):
        raise ValueError('Prescribed strain-wave sweep leaves no usable tooth engagement.')
    pitch=TAU/(z+2)
    points=tuple((r*cos(-pitch/2+j*pitch/ANGULAR_CELLS),r*sin(-pitch/2+j*pitch/ANGULAR_CELLS)) for j,r in enumerate(enclosed))
    return points,dict(method='complete prescribed-map swept outline with angular-cell enclosure',
                       angular_cells_per_tooth=ANGULAR_CELLS,trajectory_intervals=nt,
                       subdivisions_per_reference_edge=nq,convergence_threshold_mm=CONVERGENCE,
                       measured_refinement_change_mm=change,
                       numerical_enclosure_relief_mm=max(x-y for x,y in zip(enclosed,radial)),
                       generated_tooth_depth_mm=depth,reference_wheel_teeth=z+2,
                       elastic_solution=False)


def circular_spline(reference,z,a,b,rp):
    """Generate z+2 teeth from one complete, deliberately thickened FS tooth."""
    if len(reference)%z:
        raise ValueError('Flexspline reference must have identical cyclic tooth topology.')
    n=len(reference)//z
    tooth=list(reference[:n])
    angle=TAU/z;c,s=cos(angle),sin(angle);x,y=reference[0]
    tooth.append((x*c-y*s,x*s+y*c))
    first,metadata=_profile(tuple(tooth),z,a,b,rp)
    result=[]
    for k in range(z+2):
        angle=TAU*k/(z+2);c,s=cos(angle),sin(angle)
        result.extend((x*c-y*s,x*s+y*c) for x,y in first)
    return result,dict(metadata)
