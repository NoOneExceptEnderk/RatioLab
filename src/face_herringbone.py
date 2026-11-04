# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Joined face-pinion envelope, including the cusp sweep and concave trimming.

NASA/CR2000-209909 eq21–24,63–68 supplies the moving involute construction.
The explicit cusp/upper-lower envelope derivation is in technical/face-gears.md.
This is a nominal equal-count construction, not an industrial cutter/LTCA model.
"""
from math import pi,sqrt,hypot,cos,sin,ceil
from face_geometry import REFINEMENT


def distance(a,b):return sqrt(sum((x-y)**2 for x,y in zip(a,b)))


class JoinedSurface:
    def __init__(self,g):
        self.g=g;self.mid=(g.x0+g.x1)/2;self.cache={};self.seam_cache={}
        self.inner=0.;self.outer=1e99;self.cusp_max=0.;self.window_cells=0
        for side in (-1,1):
            stack=[(g.low,g.high,0)]
            while stack:
                a,b,depth=stack.pop();self.window_cells+=1
                if self.window_cells>4096:raise ValueError('Joined face annular-domain budget exhausted.')
                try:
                    if b-a>(g.high-g.low)/64:raise ValueError('Refine annular boundary')
                    r0=g._cell(g.x0,g.x0,a,b,side,g.k)[-1]
                    r1=g._cell(g.x1,g.x1,a,b,side,-g.k)[-1]
                    seams=[g._cell(self.mid,self.mid,a,b,side,k)[-1] for k in (g.k,-g.k)]
                except ValueError:
                    if depth>=18:raise ValueError('Joined face annular domain is unresolved; adjust width / offset / helix.')
                    mid=(a+b)/2;stack.extend(((a,mid,depth+1),(mid,b,depth+1)));continue
                self.inner=max(self.inner,r0.hi);self.outer=min(self.outer,r1.lo)
                self.cusp_max=max(self.cusp_max,*(q.hi for q in seams))
        margin=REFINEMENT/4;self.inner+=margin;self.outer-=margin
        if self.outer-self.inner<g.m:raise ValueError('Joined face common tooth band is too narrow; adjust width / offset / helix.')

    def inverse(self,R,h,side,band):
        g=self.g;a,b,k=band;ra=g.contact(a,h,side,k)[0];rb=g.contact(b,h,side,k)[0]
        tolerance=1e-10*g.m
        if R<ra-tolerance or R>rb+tolerance:return None
        x=max(a,min(b,a+(b-a)*(R-ra)/(rb-ra)))
        for _ in range(32):
            row=g.contact(x,h,side,k);error=row[0]-R
            if abs(error)<tolerance:return row,x
            if error<0:a=x
            else:b=x
            y=row[5];q=sqrt(y*y+h*h-g.rb*g.rb);fy=g.scalar(y,x,h,side,k)[1]
            yx=-(side*q*y/g.rb+h)/fy
            trial=x-error*row[0]/(x+(y+g.e)*yx)
            x=trial if a<trial<b else (a+b)/2
        raise ValueError('Joined face inverse radius did not resolve within its bracket.')

    def candidates(self,R,h,side):
        g=self.g;result=[]
        for index,band in enumerate(g.bands):
            row=self.inverse(R,h,side,band)
            if row:result.append((row[0][1],index,row[1],row[0][5]))
        if R>=self.mid:
            ends=[g.contact(self.mid,h,side,k)[5] for k in (g.k,-g.k)]
            for sign in (-1,1):
                y=sign*sqrt(max(0,R*R-self.mid*self.mid))-g.e
                if min(ends)-1e-9*g.m<=y<=max(ends)+1e-9*g.m:
                    row=g.coordinates(self.mid,h,side,y)
                    result.append((row[1],2,self.mid,y))
        if not result:raise ValueError('Joined face envelope has an unsupported radial gap.')
        return result

    def at(self,R,h,side):
        key=R,h,side
        if key not in self.cache:
            if len(self.cache)>=50000:raise ValueError('Joined face surface evaluation budget exhausted.')
            self.cache[key]=(max if side==1 else min)(self.candidates(R,h,side))
        return self.cache[key]

    def anchors(self,h):
        if h in self.seam_cache:return self.seam_cache[h]
        g=self.g;convex=1 if g.k>0 else -1;other=-convex
        ends=[g.contact(self.mid,h,convex,k)[0] for k in (g.k,-g.k)]
        a=g.contact(self.mid,h,other,-g.k)[0];b=g.contact(self.mid,h,other,g.k)[0]
        if a>b+1e-9*g.m:raise ValueError('Joined face concave overlap is not ordered.')
        def difference(R):
            left=self.inverse(R,h,other,g.bands[0]);right=self.inverse(R,h,other,g.bands[1])
            if not left or not right:raise ValueError('Joined face trim intersection left its supported halves.')
            return left[0][1]-right[0][1]
        fa=difference(a);fb=difference(b)
        if fa*fb>0 and min(abs(fa),abs(fb))>1e-11:
            raise ValueError('Joined face trim intersection is not bracketed; adjust offset / helix.')
        for _ in range(44):
            R=(a+b)/2;f=difference(R)
            if f*fa<=0:b=R
            else:a=R;fa=f
            if b-a<1e-10*g.m:break
        radii=sorted(max(self.inner,min(self.outer,R)) for R in (*ends,(a+b)/2))
        result=[self.inner]+radii+[self.outer];self.seam_cache[h]=result
        return result

    def radius(self,t,h):
        anchors=self.anchors(h);index=min(3,int(t))
        return anchors[index]+(anchors[index+1]-anchors[index])*(t-index)

    def polar(self,t,h,side):
        R=self.radius(t,h);return R,self.at(R,h,side)[0],self.g.height-h

    def point(self,t,h,side):
        R,a,z=self.polar(t,h,side);return R*cos(a),R*sin(a),z

    def profile(self,t,hs,k,segments):
        g=self.g;pitch=2*pi/g.v['wheel'];out=[]
        for h in reversed(hs):out.append(self.polar(t,h,1))
        a=self.polar(t,g.low,1);b=self.polar(t,g.low,-1)
        for j in range(1,segments):
            f=j/segments;out.append((a[0],a[1]+f*(b[1]+pitch-a[1]),a[2]))
        for h in hs:
            R,a,z=self.polar(t,h,-1);out.append((R,a+pitch,z))
        a=self.polar(t,g.high,-1);b=self.polar(t,g.high,1)
        for j in range(1,segments):
            f=j/segments;out.append((a[0],a[1]+pitch+f*(b[1]-a[1]),a[2]))
        if any(b[1]<=a[1] for a,b in zip(out,out[1:])):
            raise ValueError('Joined face tooth profile points or reverses; adjust width / offset / helix.')
        return [(R*cos(a),R*sin(a),z) for R,a,z in out]

    def grids(self):
        g=self.g;hs=[g.low,g.high];ts=[0.,1.,2.,3.,4.]
        pitch=2*pi/g.v['wheel'];segments=max(4,ceil(sqrt(g.outer*pitch*pitch/(8*REFINEMENT))))
        for _ in range(12):
            added=[]
            for a,b in zip(hs,hs[1:]):
                error=0.
                for t in ts+[(x+y)/2 for x,y in zip(ts,ts[1:])]:
                    for side in (-1,1):
                        p=self.point(t,a,side);q=self.point(t,b,side)
                        for f in (.25,.5,.75):
                            v=self.point(t,a+(b-a)*f,side)
                            error=max(error,distance(v,tuple(x+(y-x)*f for x,y in zip(p,q))))
                if error>REFINEMENT:added.append((a+b)/2)
            hs=sorted(hs+added);changed=bool(added);added=[]
            rows={t:self.profile(t,hs,0,segments) for t in ts}
            for a,b in zip(ts,ts[1:]):
                error=0.
                for f in (.25,.5,.75):
                    actual=self.profile(a+(b-a)*f,hs,0,segments)
                    error=max(error,max(distance(v,tuple(x+(y-x)*f for x,y in zip(p,q))) for v,p,q in zip(actual,rows[a],rows[b])))
                if error>REFINEMENT:added.append((a+b)/2)
            ts=sorted(ts+added);changed|=bool(added)
            count=g.v['wheel']*(2*len(hs)+2*(segments-1))
            if len(hs)>129 or len(ts)>129 or count>12000 or count*(2*(len(ts)-1)+14)>250000:
                raise ValueError('Joined face refinement budget exhausted; reduce width / helix / offset.')
            if not changed:return hs,[ts],segments
        raise ValueError('Joined face refinement did not converge within its budget.')

    def engagement(self):
        """Whole enclosed intervals on untouched smooth halves, not sampled winners."""
        g=self.g;best={-1:0.,1:0.};records=[];tip=g.rp+g.m;cells=0
        for band_index,(lo,hi,k) in enumerate(g.bands):
            safe_lo=self.inner if band_index==0 else max(self.inner,self.cusp_max)
            safe_hi=min(self.outer,self.mid) if band_index==0 else self.outer
            for fraction in (.2,.4,.6,.8):
                x=lo+(hi-lo)*fraction
                for side in (-1,1):
                    stack=[(g.low,g.high,0)];good=[]
                    while stack:
                        a,b,depth=stack.pop();cells+=1
                        if cells>8192:raise ValueError('Joined face engagement-domain budget exhausted.')
                        try:
                            R=g._cell(x,x,a,b,side,k)[-1]
                            r0=g.contact(x,a,side,k)[3];r1=g.contact(x,b,side,k)[3]
                            if R.hi<=safe_lo or R.lo>=safe_hi or r0>=tip:continue
                            if R.lo>safe_lo and R.hi<safe_hi and r1<tip:
                                good.append((a,b));continue
                        except ValueError:pass
                        if depth>=14:continue
                        mid=(a+b)/2;stack.extend(((a,mid,depth+1),(mid,b,depth+1)))
                    runs=[]
                    for a,b in sorted(good):
                        if runs and a==runs[-1][1]:runs[-1]=(runs[-1][0],b)
                        else:runs.append((a,b))
                    for a,b in runs:
                        span=abs(g.contact(x,b,side,k)[4]-g.contact(x,a,side,k)[4])/(2*pi/g.v['pinion'])
                        if span>best[side]:best[side]=span;records.append(dict(side=side,half=band_index,x_mm=x,height_interval_mm=[a,b],span_teeth=span))
        if min(best.values())<=1+1e-7:
            raise ValueError('Joined face has no complete retained smooth contact track; adjust addendum / radial setting / helix / offset.')
        return dict(phase_span_lower_bound_teeth=min(best.values()),retained_tracks=records,
            method='Connected interval-enclosed actual-pinion tracks outside all cusp/trim radii',
            scope='At least one complete untouched smooth track per flank; no equal loading or axial cancellation')

    def info(self):
        return dict(method='Upper/lower envelope of two involute halves and the pinion cusp sweep; concave intersection trimming',
            annular_radius_mm=[self.inner,self.outer],pinion_cusp_x_mm=self.mid,
            seam_rule='Height-dependent cusp endpoints and concave trim intersection are explicit radial grid anchors',
            refinement_scope='Finite quarter/midpoint probes at 0.003 mm; smooth patches retain numerical enclosures, join is not interval-certified')
