# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Custom hypoid pair: pinion envelope generated from a spherical spiral wheel.

Nie et al. DOI 10.1177/16878132241228195, equations 7–8. The chosen master
surface/blank is custom, not the paper's manufacturing surface or machine setup.
Axes: wheel +Z through origin; pinion +X through (0, offset, 0). Units mm/rad.
"""
from dataclasses import replace
from math import (sin, cos, tan, acos, atan, atan2, sqrt, hypot, pi,
                  degrees, nextafter, inf)
from bevel_geometry import parameters, section
from bevel_pair import stations as wheel_stations, curved_section

SPECS = [
    ('module', 'Wheel reference module [mm]', 2, .5, 6, .1),
    ('pinion', 'Pinion teeth', 20, 16, 80, 1),
    ('wheel', 'Wheel teeth', 40, 16, 120, 1),
    ('offset', 'Signed shaft offset [mm]', 2, -50, 50, .1),
    ('width', 'Wheel reference face width [mm]', 8, 2, 25, .5),
    ('spiral_angle', 'Master-wheel spiral angle [°]', 35, 25, 45, 1),
    ('pressure', 'Master transverse pressure angle [°]', 20, 17.5, 25, .5),
    ('backlash', 'Wheel reference tangential backlash [mm]', .15, 0, 1, .01),
    ('bore', 'Pinion bore [mm]', 6, 0, 100, .5),
    ('output_bore', 'Wheel bore [mm]', 8, 0, 100, .5),
]
CATALOG_REASON = ('Custom hypoid pair: two bored gear blanks. Complete shafts, '
                  'bearing seats, supports and retention in CAD; automatic catalog hardware is unavailable.')
REFINEMENT = .003


def check_contour(points):
    """Reject intersections of the actual sampled section, including tooth neighbors."""
    from stl_export import intersects
    if len(set(points))!=len(points):raise ValueError('Hypoid sampled section has duplicate vertices.')
    segments=sorted((min(a[0],b[0]),max(a[0],b[0]),min(a[1],b[1]),max(a[1],b[1]),i,a,b)
                    for i,(a,b) in enumerate(zip(points,points[1:]+points[:1])))
    active=[];n=len(points)
    for lo,hi,bottom,top,i,a,b in segments:
        active=[row for row in active if row[1]>=lo]
        for _,_,y0,y1,j,c,d in active:
            if (i-j)%n in (1,n-1) or y0>top or y1<bottom:continue
            if intersects(a,b,c,d):raise ValueError('Hypoid sampled pinion section intersects itself; adjust offset / tooth counts / spiral angle.')
        active.append((lo,hi,bottom,top,i,a,b))


def _down(x):return nextafter(x, -inf)
def _up(x):return nextafter(x, inf)


class Interval:
    """Outward-expanded floating-point intervals, not exact-arithmetic proofs."""
    def __init__(self, lo, hi=None):self.lo=lo;self.hi=lo if hi is None else hi
    def __add__(self, other):
        b=interval(other);return Interval(_down(self.lo+b.lo), _up(self.hi+b.hi))
    __radd__=__add__
    def __neg__(self):return Interval(-self.hi,-self.lo)
    def __sub__(self, other):return self+-interval(other)
    def __rsub__(self, other):return interval(other)+-self
    def __mul__(self, other):
        b=interval(other);v=[a*c for a in (self.lo,self.hi) for c in (b.lo,b.hi)]
        return Interval(_down(min(v)),_up(max(v)))
    __rmul__=__mul__
    def __truediv__(self, other):
        b=interval(other)
        if b.lo<=0<=b.hi:raise ValueError('Unresolved interval denominator.')
        return self*Interval(_down(1/b.hi),_up(1/b.lo))
    def square(self):
        v=(self.lo*self.lo,self.hi*self.hi)
        return Interval(0 if self.lo<=0<=self.hi else max(0,_down(min(v))),_up(max(v)))
    def sqrt(self):
        if self.lo<=0:raise ValueError('Unresolved positive interval.')
        return Interval(_down(sqrt(self.lo)),_up(sqrt(self.hi)))
    def sin(self):
        if not -pi/2<self.lo<=self.hi<pi/2:raise ValueError('Unresolved sine branch.')
        return Interval(_down(sin(self.lo)),_up(sin(self.hi)))
    def cos(self):
        if not -pi/2<self.lo<=self.hi<pi/2:raise ValueError('Unresolved cosine branch.')
        return Interval(_down(min(cos(self.lo),cos(self.hi))),_up(1 if self.lo<=0<=self.hi else max(cos(self.lo),cos(self.hi))))
    def acos(self):
        if not -1<self.lo<=self.hi<1:raise ValueError('Unresolved envelope branch.')
        return Interval(_down(acos(self.hi)),_up(acos(self.lo)))
    def atan(self):return Interval(_down(atan(self.lo)),_up(atan(self.hi)))


def interval(x):return x if isinstance(x,Interval) else Interval(x)


class Jet:
    """Interval value and analytic first derivative with respect to master polar angle."""
    def __init__(self, value, derivative=0):self.v=interval(value);self.d=interval(derivative)
    def __add__(self, other):
        b=jet(other);return Jet(self.v+b.v,self.d+b.d)
    __radd__=__add__
    def __neg__(self):return Jet(-self.v,-self.d)
    def __sub__(self, other):return self+-jet(other)
    def __rsub__(self, other):return jet(other)+-self
    def __mul__(self, other):
        b=jet(other);return Jet(self.v*b.v,self.d*b.v+self.v*b.d)
    __rmul__=__mul__
    def __truediv__(self, other):
        b=jet(other);return Jet(self.v/b.v,(self.d*b.v-self.v*b.d)/b.v.square())
    def square(self):return Jet(self.v.square(),2*self.v*self.d)
    def sqrt(self):
        v=self.v.sqrt();return Jet(v,self.d/(2*v))
    def sin(self):return Jet(self.v.sin(),self.v.cos()*self.d)
    def cos(self):return Jet(self.v.cos(),-self.v.sin()*self.d)
    def acos(self):return Jet(self.v.acos(),-self.d/(1-self.v.square()).sqrt())
    def atan(self):return Jet(self.v.atan(),self.d/(1+self.v.square()))


def jet(x):return x if isinstance(x,Jet) else Jet(x)


class Generator:
    def __init__(self, v):
        self.v=v;self.offset=v['offset'];self.ratio=-v['wheel']/v['pinion']
        self.outer=hypot(v['pinion'],v['wheel'])*v['module']/2
        if abs(self.offset)>.06*self.outer:
            raise ValueError('Hypoid offset exceeds the supported 6% of reference cone distance; reduce offset or enlarge the gears.')
        if v['width']>self.outer/3 or v['backlash']>=.7*v['module']:
            raise ValueError('Hypoid reference width must be at most R/3 and backlash less than 0.7 module.')
        self.hand=1 if self.offset>=0 else -1
        q=parameters(v['wheel'],v['pinion'],v['module'],v['pressure'],0,v['spiral_angle'],self.hand)
        self.cutter=replace(q,backlash=-v['backlash'],tip=atan2(v['wheel']+1.4,v['pinion']))
        self.heel=v['module']*v['wheel']/2
        self.toe=self.heel*(1-v['width']/self.outer)
        self.cache={}
        self.top=self._top_angle()
        self.cutter=replace(self.cutter,root=min(self.cutter.root,self.top-.25*v['module']/self.outer))
        self.master=replace(self.cutter,backlash=v['backlash'])
        if not 0<self.master.root<self.top or not 0<self.master.half_angle(self.master.tip)<self.master.half_angle(self.master.root)<pi/v['wheel']:
            raise ValueError('Hypoid master has pointed or overlapping teeth; adjust tooth counts, pressure or backlash.')
        self.regularity=self._certify_regularity()
        self.engagement=self._certify_tracks()
        self._check_bores()

    def constants(self, theta, side):
        q=self.cutter;s=sin(theta);c=cos(theta)
        h=-sqrt(max(0,cos(q.base)**2-c*c))/(sin(q.base)*s)
        return s,c,h,side*h*s*s-q.k*s*c

    @staticmethod
    def solve(a,b,c,side):
        magnitude=hypot(a,b)
        if a<=0 or abs(c)>=magnitude*(1-1e-12):
            raise ValueError('No separated hypoid generating branch; reduce offset or adjust tooth counts / spiral angle.')
        psi=atan2(b,a)-side*acos(-c/magnitude)
        if abs(psi)>=pi/2-.01:raise ValueError('Hypoid generating branch reaches the rear of the blank.')
        return psi

    def at_x(self, theta, x, side):
        key=(theta,x,side)
        if key in self.cache:return self.cache[key]
        s,c,h,nz=self.constants(theta,side)
        psi=self.solve(c+self.offset*nz*s/x,-side*h*s,s/self.ratio,side)
        distance=x/(s*cos(psi));y=x*tan(psi);z=distance*c
        wheel_angle=psi-self.cutter.trace(distance)-side*self.cutter.half_angle(theta)
        azimuth=atan2(z,y-self.offset)-self.ratio*wheel_angle
        result=(hypot(y-self.offset,z),azimuth,distance,wheel_angle)
        if len(self.cache)<60000:self.cache[key]=result
        return result

    def at_r(self, theta, distance, side):
        s,c,h,nz=self.constants(theta,side)
        psi=self.solve(c,-side*h*s,s/self.ratio+self.offset*nz/distance,side)
        x=distance*s*cos(psi);y=distance*s*sin(psi);z=distance*c
        angle=psi-self.cutter.trace(distance)-side*self.cutter.half_angle(theta)
        return x,hypot(y-self.offset,z),atan2(z,y-self.offset)-self.ratio*angle,angle

    def point(self, theta, x, side):
        radius,azimuth,_,_=self.at_x(theta,x,side)
        return radius*cos(azimuth),radius*sin(azimuth),x

    def _top_angle(self):
        q=self.cutter;x=(self.toe+self.heel)/2
        reference=sum(self.at_x(q.delta,x,s)[0] for s in (-1,1))/2
        target=reference+self.v['module']*x/self.heel
        tips=[]
        for side in (-1,1):
            samples=[]
            for j in range(257):
                theta=q.base+.0001+(q.delta-q.base-.0001)*j/256
                try:samples.append((theta,self.at_x(theta,x,side)[0]))
                except ValueError:pass
            if not samples or samples[0][1]<=target:
                raise ValueError('Hypoid pinion addendum exceeds its regular generating branch; reduce offset or change tooth counts.')
            lo,hi=samples[0][0],q.delta
            for _ in range(52):
                mid=(lo+hi)/2
                if self.at_x(mid,x,side)[0]>target:lo=mid
                else:hi=mid
            tips.append((lo+hi)/2)
        return max(tips)

    def _jet(self, low, high, side, axial=None, radius=None):
        theta=Jet(Interval(low,high),1);s=theta.sin();c=theta.cos();q=self.cutter
        h=-(cos(q.base)**2-c.square()).sqrt()/(sin(q.base)*s)
        nz=side*h*s.square()-q.k*s*c
        if axial is not None:
            x=Jet(axial);a=c+self.offset*nz*s/x;cc=s/self.ratio
        else:
            distance=Jet(radius);a=c;cc=s/self.ratio+self.offset*nz/distance
        b=-side*h*s
        if a.v.lo<=0:raise ValueError('Unresolved envelope quadrant.')
        psi=(b/a).atan()-side*(-cc/(a.square()+b.square()).sqrt()).acos()
        cp=psi.cos()
        if cp.v.lo<=0:raise ValueError('Unresolved forward envelope branch.')
        if axial is not None:distance=x/(s*cp)
        else:x=distance*s*cp
        y=distance*s*psi.sin();z=distance*c
        return ((y-self.offset).square()+z.square()).sqrt(),x

    def _certify_regularity(self):
        count=0;upper=-inf
        for side in (-1,1):
            stack=[(self.top,self.cutter.tip,self.toe,self.heel,0)]
            while stack:
                lo,hi,a,b,depth=stack.pop();count+=1
                if count>4096:raise ValueError('Hypoid envelope regularity budget exhausted; reduce offset / face width.')
                try:
                    r,_=self._jet(lo,hi,side,Interval(a,b))
                    valid=r.d.hi < -1e-8
                except ValueError:valid=False
                if valid:upper=max(upper,r.d.hi);continue
                if depth>=14:
                    raise ValueError('Hypoid envelope has undercut or unresolved regularity; reduce offset or face width.')
                if (hi-lo)/(self.cutter.tip-self.top) >= (b-a)/(self.heel-self.toe):
                    mid=(lo+hi)/2;stack.extend([(lo,mid,a,b,depth+1),(mid,hi,a,b,depth+1)])
                else:
                    mid=(a+b)/2;stack.extend([(lo,hi,a,mid,depth+1),(lo,hi,mid,b,depth+1)])
        return dict(method='Outward-expanded interval first derivatives on both working rectangles',
                    cells=count,radial_derivative_upper_mm_per_rad=upper,
                    scope='Numerical libm/float interval enclosure; regular analytic working flanks only, not sampled-mesh clearance')

    def _certify_tracks(self):
        radius=self.outer-self.v['width']/2;q=self.cutter
        wheel_toe=(self.outer-self.v['width'])*cos(q.delta);wheel_heel=self.outer*cos(q.delta)
        if radius*cos(q.tip)<=wheel_toe+1e-8 or radius*cos(self.top)>=wheel_heel-1e-8:
            raise ValueError('No complete mean-radius hypoid contact track inside wheel caps; increase width or change tooth counts.')
        spans=[];count=0
        for side in (-1,1):
            stack=[(self.top,q.tip,0)]
            while stack:
                lo,hi,depth=stack.pop();count+=1
                if count>2048:raise ValueError('Hypoid contact-track budget exhausted.')
                try:
                    _,x=self._jet(lo,hi,side,radius=radius)
                    valid=x.v.lo>self.toe+1e-8 and x.v.hi<self.heel-1e-8
                except ValueError:valid=False
                if valid:continue
                if depth>=14:
                    raise ValueError('Hypoid contact track leaves the pinion caps or generating branch; adjust offset / width.')
                mid=(lo+hi)/2;stack.extend([(lo,mid,depth+1),(mid,hi,depth+1)])
            values=[]
            for j in range(129):
                theta=self.top+(q.tip-self.top)*j/128
                x,_,_,angle=self.at_r(theta,radius,side)
                if abs(self.at_x(theta,x,side)[2]-radius)>1e-8:
                    raise ValueError('Hypoid generation selected inconsistent envelope branches.')
                values.append(angle)
            spans.append((max(values)-min(values))/(2*pi/self.v['wheel']))
        if min(spans)<=1+1e-8:
            raise ValueError('Hypoid connected-track engagement below one tooth pitch; adjust tooth counts / width / spiral angle.')
        return dict(phase_span_lower_bound_teeth=min(spans),flank_spans_lower_bound_teeth=spans,
                    mean_radius_mm=radius,interval_cells=count,
                    method='Continuous mean-radius tracks enclosed inside both cap intervals; conservative unwrapped phase-span lower bound',
                    scope='Sufficient ideal engagement; not a load/contact-pattern or continuous mesh-clearance certificate')

    def root(self,x):
        reference=sum(self.at_x(self.cutter.delta,x,s)[0] for s in (-1,1))/2
        end=min(self.at_x(self.cutter.tip,x,s)[0] for s in (-1,1))
        return min(reference-1.25*self.v['module']*x/self.heel,end-.25*self.v['module']*x/self.heel)

    def _check_bores(self):
        limit=self.v['bore']/2+.8 if self.v['bore'] else 1e-6
        stack=[(self.toe,self.heel,0)]
        while stack:
            low,high,depth=stack.pop()
            try:
                bounds={}
                for theta in (self.cutter.delta,self.cutter.tip):
                    bounds[theta]=[self._jet(theta,theta,side,Interval(low,high))[0].v.lo for side in (-1,1)]
                minimum=min(sum(bounds[self.cutter.delta])/2-1.25*self.v['module']*high/self.heel,
                            min(bounds[self.cutter.tip])-.25*self.v['module']*high/self.heel)
            except ValueError:minimum=-inf
            if minimum>limit:continue
            if self.root((low+high)/2)<=limit or depth>=10:
                raise ValueError('Hypoid pinion bore leaves insufficient or unresolved nominal root wall.')
            mid=(low+high)/2;stack.extend([(low,mid,depth+1),(mid,high,depth+1)])
        root=(self.outer-self.v['width'])*cos(self.master.delta)*tan(self.master.root)
        if root<=self.v['output_bore']/2+.8:
            raise ValueError('Hypoid wheel bore leaves insufficient nominal small-end root wall.')

    def outline(self,x,angles):
        pitch=2*pi/self.v['pinion'];root=self.root(x);ends={}
        for side in (-1,1):
            r,a,_,_=self.at_x(self.cutter.tip,x,side);ends[side]=(r,a-(pitch if side<0 else 0))
        if not 0<ends[1][1]-ends[-1][1]<pitch:
            raise ValueError('Hypoid tooth roots overlap the neighboring tooth.')
        left=self.at_x(self.top,x,-1);right=self.at_x(self.top,x,1)
        la=left[1]-pitch;ra=right[1]
        if not 0<ra-la<pitch:
            raise ValueError('Hypoid pinion has pointed or overlapping crests.')
        out=[]
        for tooth in range(self.v['pinion']):
            def add(r,a):out.append((r*cos(a+tooth*pitch),r*sin(a+tooth*pitch)))
            add(root,ends[-1][1])
            for theta in reversed(angles):
                r,a,_,_=self.at_x(theta,x,-1);add(r,a-pitch)
            for j in range(1,32):
                f=j/32;add(left[0]+(right[0]-left[0])*f,la+(ra-la)*f)
            for theta in angles:
                r,a,_,_=self.at_x(theta,x,1);add(r,a)
            add(root,ends[1][1])
            for j in range(1,32):add(root,ends[1][1]+(ends[-1][1]+pitch-ends[1][1])*j/32)
        return out

    def grids(self):
        angles=[self.top,self.cutter.tip];xs=[self.toe,self.heel]
        for _ in range(12):
            split=[]
            for lo,hi in zip(angles,angles[1:]):
                error=0
                for x in xs+[(a+b)/2 for a,b in zip(xs,xs[1:])]:
                    for side in (-1,1):
                        a=self.point(lo,x,side);b=self.point(hi,x,side)
                        for f in (.25,.5,.75):
                            p=self.point(lo+(hi-lo)*f,x,side)
                            error=max(error,hypot(*(p[k]-(a[k]+(b[k]-a[k])*f) for k in (0,1))))
                if error>REFINEMENT:split.append((lo+hi)/2)
            if split:
                angles=sorted(angles+split)
                if len(angles)>257:raise ValueError('Hypoid flank refinement budget exhausted.')
            vertex_count=self.v['pinion']*(2*len(angles)+64)+(96 if self.v['bore'] else 0)
            if vertex_count>10000 or 2*vertex_count*(len(xs)-1)+2>250000:
                raise ValueError('Hypoid sampled surface exceeds the shared vertex/face budget; reduce tooth counts / width / curvature.')
            outlines={x:self.outline(x,angles) for x in xs};new=[]
            for lo,hi in zip(xs,xs[1:]):
                a=outlines[lo];b=outlines[hi];error=0
                for f in (.25,.5,.75):
                    middle=self.outline(lo+(hi-lo)*f,angles)
                    error=max(error,max(hypot(p[0]-(u[0]+(v[0]-u[0])*f),p[1]-(u[1]+(v[1]-u[1])*f)) for p,u,v in zip(middle,a,b)))
                if error>REFINEMENT:new.append((lo+hi)/2)
            if new:
                xs=sorted(xs+new)
                if len(xs)>65:raise ValueError('Hypoid axial refinement budget exhausted.')
            if not split and not new:return angles,xs
        raise ValueError('Hypoid shared surface refinement did not converge within its budget.')


def build(d):
    from geometry import Part,circle
    v=d.values;g=Generator(v);angles,xs=g.grids()
    contours=[g.outline(x,angles) for x in xs];holes=[circle(v['bore']/2)] if v['bore'] else []
    for contour in contours:check_contour(contour)
    faces=2*(len(contours[0])+sum(map(len,holes)))*(len(xs)-1)+2
    if faces>250000:raise ValueError('Hypoid pinion exceeds the shared face budget; reduce tooth counts / width / curvature.')
    pinion=Part('Hypoid_pinion',contours[-1],holes,g.heel-g.toe,g.toe,
                frame=((0,v['offset'],0),(0,1,0),(0,0,1),(1,0,0)))
    pinion.stations=[dict(z=0 if j==0 else g.heel-g.toe if j==len(xs)-1 else x-g.toe,outer=loop,holes=holes) for j,(x,loop) in enumerate(zip(xs,contours))]
    q=g.master;heel=g.outer*cos(q.delta);toe=(g.outer-v['width'])*cos(q.delta)
    outer=section(q,heel);bores=[circle(v['output_bore']/2)] if v['output_bore'] else []
    wheel=Part('Hypoid_wheel',outer,bores,heel-toe,toe)
    radii,_=wheel_stations((q,),v['width'])
    if 2*(len(outer)+sum(map(len,bores)))*(len(radii)-1)+2>250000:
        raise ValueError('Hypoid master wheel exceeds the shared face budget; reduce tooth counts / width / spiral angle.')
    wheel.stations=[dict(z=0 if j==0 else heel-toe if j==len(radii)-1 else r*cos(q.delta)-toe,
                        outer=outer if r==g.outer else curved_section(q,outer,r),holes=bores) for j,r in enumerate(radii)]
    for p,member,axis,color in ((pinion,'A','World +X through (0, offset, 0)',(.96,.66,.33)),(wheel,'B','World +Z through origin',(.23,.75,.65))):
        p.port=dict(member=member,axis=axis);p.color=color
        p.profile_metadata['hypoid_profile']=dict(method='Conjugate pinion envelope of custom spherical spiral master' if member=='A' else 'Custom spherical spiral master wheel',
            reference_doi='10.1177/16878132241228195',reference_equations='Conjugated surface section, equations 7–8',
            refinement_threshold_mm=REFINEMENT,refinement_scope='Finite quarter/midpoint probes, not a global surface-error or manufacturing bound')
    d.parts.extend([pinion,wheel])
    d.analysis.update(signed_ratio=g.ratio,hypoid=dict(offset_mm=v['offset'],shaft_angle_deg=90,
        reference_distance_mm=g.outer,reference_wheel_module_mm=v['module'],master_reference_cone_angle_deg=degrees(q.delta),
        master_spiral_hand=g.hand,pinion_derived_hand=-g.hand,master_addendum_coefficient=.7,
        master_root_angle_deg=degrees(q.root),pinion_generating_angle_interval_rad=[g.top,q.tip],
        regularity=g.regularity,engagement=g.engagement,pinion_axial_stations_mm=xs,master_cone_stations_mm=radii,
        rolling_equation='pinion_teeth * pinion_rpm + wheel_teeth * wheel_rpm = 0',
        construction='Custom conjugate envelope, not a translated bevel pair or commercial cutter design'))
    d.metrics.extend([f"Shaft offset: {v['offset']:+g} mm · 90° skew shaft directions",
                      f"Hypoid ideal engagement lower bound: {g.engagement['phase_span_lower_bound_teeth']:.6f} wheel tooth pitches",
                      f'Generated pinion: {len(xs)} axial stations · master wheel: {len(radii)} cone stations'])
    d.notes.extend([
        'Custom hypoid construction: pinion is generated as the conjugate envelope of a spherical-involute logarithmic spiral master wheel. Not a Gleason/AGMA production tooth system, machine settings or stock-compatible part.',
        'Reference wheel module and cone size define the chosen master blank, not a standardized hypoid normal module or rolling pitch cone. Master addendum is 0.7 module; root and pinion crest are linked to the generated envelope.',
        'Positive speeds use pinion world +X through (0, offset, 0) and wheel world +Z through origin. Offset sign mirrors the construction; local trace hands are derived. Offset zero is the degenerate generated bevel limit.',
        'Outward-expanded float/libm intervals check analytic envelope regularity and connected mean-radius contact tracks. Phase spans are sufficient conservative lower bounds, not loaded tooth contact or continuous mesh-clearance certification.',
        'Shared surfaces use finite quarter/midpoint refinement at 0.003 mm; this is not a proven whole-surface error or manufacturing tolerance. Crest/root relief are nonworking custom constructions. Check sampled interference and complete supports, lubrication, strength and retention in CAD.',
    ])
    d.requirements.append(CATALOG_REASON)
