# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Orthogonal face-gear envelope. NASA/CR2000-209909 eq21–24,63–69;
NASA/CR2005-213443 sec2–3 eq3–4,15–18. See docs/technical/face-gears.md.
Ideal equal-count pinion/shaper; custom stub crest and nonworking root extension.
"""
from math import pi,sin,cos,tan,atan,atan2,sqrt,hypot,radians,ceil
from hypoid_geometry import Interval

VARIANTS={'spur':'Spur pinion','helical':'Helical pinion',
          'double_helical':'Double helical pinion'}
SPECS=[('module','Normal pinion module [mm]',2,.5,6,.1),
       ('pinion','Pinion teeth',24,16,80,1),('wheel','Face wheel teeth',72,24,160,1),
       ('width','Band width along pinion axis [mm]',8,3,20,.5),
       ('offset','Signed shaft offset [mm]',0,-50,50,.1),
       ('radial_setting','Band setting beyond reference radius [mm]',4,0,40,.1),
       ('base','Face wheel backing thickness [mm]',6,1,30,.5),
       ('face_addendum','Face addendum coefficient',.65,.35,1,.05),
       ('pressure','Normal pressure angle [°]',20,17.5,30,.5),
       ('backlash','Pinion reference pair backlash [mm]',.15,0,1,.01),
       ('bore','Pinion bore [mm]',6,0,100,.5),
       ('output_bore','Face wheel bore [mm]',10,0,150,.5)]
REFINEMENT=.003
CATALOG_REASON=('Face gears generate a bored pinion and a face-wheel blank. '
                'Complete shafts, supports, bearing seats and retention in CAD; automatic catalog hardware is unavailable.')


class Generator:
    def __init__(self,v):
        from geometry import gear_part
        self.v=v;self.e=v['offset'];self.m=v['module'];self.g=v['pinion']/v['wheel']
        self.joined=v['variant']=='double_helical' and v.get('double_style')=='joined'
        self.joined_surface=None
        if self.g>=1:raise ValueError('Face wheel must have more teeth than its pinion.')
        beta=0 if v['variant']=='spur' else v['helix'];self.beta=beta
        self.rp=self.m*v['pinion']/(2*cos(radians(beta)));self.ref=self.rp/self.g
        if abs(self.e)>=self.ref/2:
            raise ValueError('Face shaft offset must be smaller than half the reference wheel radius; reduce offset or enlarge the gears.')
        self.alpha=atan(tan(radians(v['pressure']))/cos(radians(beta)))
        self.rb=self.rp*cos(self.alpha);self.k=tan(radians(beta))/self.rp
        self.height=2*self.rp;self.low=self.rp-v['face_addendum']*self.m
        self.high=self.rp+1.25*self.m;self.root_z=self.height-self.high
        self.x0=self.ref+v['radial_setting'];self.x1=self.x0+v['width']
        if self.low<=self.rb+.025*self.m:
            raise ValueError('Face crest reaches the pinion base-cylinder branch; reduce face addendum or increase pinion teeth / pressure.')
        if v['backlash']>=.7*self.m:raise ValueError('Face pair backlash must be below 0.7 normal module.')
        p=gear_part('Face_pinion',v['pinion'],self.m,v['pressure'],v['backlash'],v['width'],v['bore'],
                    phase=-pi/2,helix=beta,zoff=self.x0)
        p.frame=((0,self.e,self.height),(0,1,0),(0,0,1),(1,0,0))
        self.pinion=p;self.start=p.profile_metadata['tooth_profile']['involute_start_radius_mm']
        self.bands=[(self.x0,self.x1,self.k)]
        if v['variant']=='double_helical':
            gap=v['gap'];half=(v['width']-gap)/2
            if (not self.joined and gap<self.m) or half<=1:
                raise ValueError('Double face gears require separated bands: gap at least one normal module and more than 1 mm per half.')
            p.double=True;p.gap=gap;p.core_radius=min(hypot(*q) for q in p.outer)*.96
            if v['bore']/2>=p.core_radius-.25:raise ValueError('Pinion bore reaches the continuous double-helix core.')
            shoulder=min(.15,half*.08,gap*.2)
            self.bands=[(self.x0,self.x0+half-shoulder,self.k),(self.x1-half+shoulder,self.x1,-self.k)]
            if self.joined and self.k==0:self.bands=[(self.x0,self.x1,0)]
        self.cache={};self.certificates=[]
        for band in self.bands:self.certificates.append(self._certify(band))
        self.outer=max(q['radius_upper_mm'] for q in self.certificates)+self.m
        if v['output_bore']/2>=self.x0-.8:raise ValueError('Face wheel bore reaches the tooth band; reduce bore / increase radial setting.')
        if not self.joined and len(self.bands)>1 and self.certificates[0]['radius_upper_mm']+.25*self.m>=self.bands[1][0]:
            raise ValueError('Mapped double face-gear bands overlap; increase central relief or reduce band width / helix.')
        self._check_widths()
        if self.joined and self.k:
            from face_herringbone import JoinedSurface
            self.joined_surface=JoinedSurface(self)
            self.engagement=self.joined_surface.engagement()
        else:self.engagement=self._engagement()

    def twist(self,x):
        return self.k*(min(x-self.x0,self.x1-x) if len(self.bands)>1 else x-self.x0)

    def scalar(self,y,x,h,side,k):
        s=y*y+h*h;q=sqrt(s-self.rb*self.rb)
        f=k*s*(y+self.e)+side*x*q*y/self.rb+x*h-s/self.g
        d=k*(3*y*y+h*h+2*self.e*y)+side*x*(q+y*y/q)/self.rb-2*y/self.g
        return f,d

    def solve(self,x,h,side,k):
        key=(x,h,side,k)
        if key in self.cache:return self.cache[key]
        y=0.
        for _ in range(45):
            f,d=self.scalar(y,x,h,side,k)
            if side*d<=1e-8:raise ValueError('Face generating branch is singular; increase radial setting / reduce helix or width.')
            if abs(f)<1e-12*self.rp*self.ref:
                result=(y,d)
                if len(self.cache)<100000:self.cache[key]=result
                return result
            step=max(-self.rp*.2,min(self.rp*.2,f/d));accepted=False
            for _ in range(20):
                trial=y-step;ff,dd=self.scalar(trial,x,h,side,k)
                if abs(trial)<self.rp*.75 and side*dd>1e-8 and abs(ff)<abs(f):
                    y=trial;accepted=True;break
                step*=.5
            if not accepted:break
        raise ValueError('Face envelope root did not resolve on its separated branch; adjust radial setting / width / helix.')

    def contact(self,x,h,side,k):
        return self.coordinates(x,h,side,self.solve(x,h,side,k)[0])

    def coordinates(self,x,h,side,y):
        r=hypot(y,h);t=sqrt((r/self.rb)**2-1)
        half=pi/(2*self.v['pinion'])+self.v['backlash']/(4*self.rp)+tan(self.alpha)-self.alpha-(t-atan(t))
        phase=atan2(-h,y)+pi/2-side*half-self.twist(x)
        theta=atan2(y+self.e,x)-self.g*phase
        return hypot(x,y+self.e),theta,self.height-h,r,phase,y

    def point(self,x,h,side,k):
        r,a,z,*_=self.contact(x,h,side,k)
        return r*cos(a),r*sin(a),z

    def enclosure(self,X,H,Y,side,k):
        s=Y.square()+H.square();q=(s-self.rb*self.rb).sqrt();U=Y+self.e if self.e else Y
        f=k*s*U+side*X*q*Y/self.rb+X*H-s/self.g
        fy=k*(3*Y.square()+H.square()+2*self.e*Y if self.e else 3*Y.square()+H.square())+side*X*(q+Y.square()/q)/self.rb-2*Y/self.g
        fx=side*q*Y/self.rb+H
        fh=2*k*H*U+side*X*H*Y/(self.rb*q)+X-2*H/self.g
        yx=-fx/fy;yh=-fh/fy
        phix=(H+side*q*Y/self.rb)*yx/s-k
        phih=(H*yh-Y+side*q*(Y*yh+H)/self.rb)/s
        ax=(X*yx-U)/(X.square()+U.square())-self.g*phix
        ah=X*yh/(X.square()+U.square())-self.g*phih
        ah_at_radius=ah-ax*U*yh/(X+U*yx)
        return f,fy,X+U*yx,Y*yh+H,ah,ax,ah_at_radius,(X.square()+U.square()).sqrt()

    def _cell(self,a,b,c,d,side,k):
        x=(a+b)/2;h=(c+d)/2;yc,dc=self.solve(x,h,side,k)
        ys=[self.solve(xx,hh,side,k)[0] for xx in (a,b) for hh in (c,d)]
        pad=(max(ys)-min(ys))*.35+.01*self.m
        Y=Interval(min(*ys,yc)-pad,max(*ys,yc)+pad);X=Interval(a,b);H=Interval(c,d)
        row=self.enclosure(X,H,Y,side,k)
        # Centered parameter form avoids losing the X*h - h*h/g cancellation.
        # Partial derivatives enclose the whole parameter rectangle at fixed yc.
        s0=yc*yc+H.square();q0=(s0-self.rb*self.rb).sqrt()
        fx0=side*q0*yc/self.rb+H
        fh0=2*k*H*(yc+self.e)+side*X*H*yc/(self.rb*q0)+X-2*H/self.g
        center=self.enclosure(Interval(x),Interval(h),Interval(yc),side,k)[0]
        f0=center+fx0*(X-x)+fh0*(H-h)
        mapped=yc-f0/dc+(1-row[1]/dc)*(Y-yc)
        if not Y.lo<mapped.lo<=mapped.hi<Y.hi:raise ValueError('Unresolved parameterized Krawczyk cell')
        row=self.enclosure(X,H,mapped,side,k)
        if (row[1]*side).lo<=1e-8 or row[2].lo<=1e-8 or row[3].lo<=1e-8 or (row[4]*side).hi>=-1e-9 or (row[6]*side).hi>=-1e-9:
            raise ValueError('Unresolved face surface regularity / ordering')
        if (mapped.square()+H.square()).sqrt().lo<self.start+1e-7:
            raise ValueError('Face working surface reaches the pinion root transition')
        return row

    def _certify(self,band):
        lo,hi,k=band;count=0;radius=0.;minimum=1e99;radial_min=1e99;angle_max=0.
        for side in (-1,1):
            stack=[(lo,hi,self.low,self.high,0)]
            while stack:
                a,b,c,d,depth=stack.pop();count+=1
                if count>8192:raise ValueError('Face regularity budget exhausted; reduce band width / addendum / helix.')
                try:
                    row=self._cell(a,b,c,d,side,k)
                    radius=max(radius,row[-1].hi);minimum=min(minimum,(row[1]*side).lo)
                    radial_min=min(radial_min,(row[2]/row[-1]).lo)
                    angle_max=max(angle_max,abs(row[5].lo),abs(row[5].hi))
                    continue
                except ValueError:pass
                if depth>=16:raise ValueError('Face envelope has undercut or unresolved regularity; adjust radial setting, width or face addendum.')
                if (b-a)/(hi-lo)>=(d-c)/(self.high-self.low):
                    mid=(a+b)/2;stack.extend([(a,mid,c,d,depth+1),(mid,b,c,d,depth+1)])
                else:
                    mid=(c+d)/2;stack.extend([(a,b,c,mid,depth+1),(a,b,mid,d,depth+1)])
        return dict(cells=count,radius_upper_mm=radius,separated_root_derivative_lower=minimum,
            radial_derivative_lower=radial_min,angular_axial_derivative_abs_upper=angle_max,
            method='Parameterized Krawczyk root enclosure and implicit first derivatives',
            scope='Outward-expanded float/libm numerical enclosures; analytic flanks, not continuous sampled-solid clearance')

    def _check_widths(self):
        pitch=2*pi/self.v['wheel'];count=0
        for (lo,hi,k),certificate in zip(self.bands,self.certificates):
            stack=[(lo,hi,0)]
            while stack:
                a,b,depth=stack.pop();count+=1;valid=True
                for h in (self.low,self.high):
                    mid=(a+b)/2;gap=self.contact(mid,h,1,k)[1]-self.contact(mid,h,-1,k)[1]
                    try:
                        rows=[self._cell(a,b,h,h,side,k) for side in (-1,1)]
                        bound=sum(max(abs(row[5].lo),abs(row[5].hi)) for row in rows)*(b-a)/2
                        # Offset/helical flanks have different radii at equal X.
                        # Bound the angular change to the same generated radius
                        # by the global angular slope / positive radial slope.
                        delta=rows[1][-1]-rows[0][-1]
                        bound+=max(abs(delta.lo),abs(delta.hi))*certificate['angular_axial_derivative_abs_upper']/certificate['radial_derivative_lower']
                        valid &= gap-bound>1e-7 and gap+bound<pitch-1e-7
                    except ValueError:valid=False
                if valid:continue
                if depth>=12 or count>4096:raise ValueError('Face teeth are pointed / overlapping or unresolved; reduce band width or radial setting.')
                mid=(a+b)/2;stack.extend([(a,mid,depth+1),(mid,b,depth+1)])

    def _engagement(self):
        rows=[];best={-1:0.,1:0.};tip=self.rp+self.m
        for lo,hi,k in self.bands:
            spans={-1:0.,1:0.}
            for fraction in (.001,.25,.5,.75,.999):
                x=lo+(hi-lo)*fraction
                for side in (-1,1):
                    if self.contact(x,self.low,side,k)[3]>=tip:continue
                    a,b=self.low,self.high;end=self.high
                    if self.contact(x,b,side,k)[3]>tip:
                        for _ in range(48):
                            mid=(a+b)/2
                            if self.contact(x,mid,side,k)[3]<tip:a=mid
                            else:b=mid
                        end=(a+b)/2
                    span=abs(self.contact(x,end,side,k)[4]-self.contact(x,self.low,side,k)[4])/(2*pi/self.v['pinion'])
                    spans[side]=max(spans[side],span);best[side]=max(best[side],span)
            rows.append([spans[-1],spans[1]])
        if min(best.values())<=1+1e-7:
            raise ValueError('Face pair has no complete connected ideal contact track; reduce radial setting / helix or adjust face addendum.')
        return dict(phase_span_lower_bound_teeth=min(best.values()),band_flank_spans_lower_bound_teeth=rows,
            method='Endpoint phase span of connected in-cap, radius-monotone tracks on the actual usable pinion involute',
            scope='At least one complete track per flank; equal sharing / axial cancellation between double bands is not established')

    def profile(self,x,hs,k,segments):
        """One face tooth and following root space, unwrapped in increasing angle."""
        pitch=2*pi/self.v['wheel'];out=[]
        for h in reversed(hs):out.append(self.contact(x,h,1,k)[:3])
        a=self.contact(x,self.low,1,k);b=self.contact(x,self.low,-1,k)
        for j in range(1,segments):
            f=j/segments;out.append((a[0]+f*(b[0]-a[0]),a[1]+f*(b[1]+pitch-a[1]),a[2]))
        for h in hs:
            r,t,z,*_=self.contact(x,h,-1,k);out.append((r,t+pitch,z))
        a=self.contact(x,self.high,-1,k);b=self.contact(x,self.high,1,k)
        for j in range(1,segments):
            f=j/segments;out.append((a[0]+f*(b[0]-a[0]),a[1]+pitch+f*(b[1]-a[1]),a[2]))
        if any(b[1]<=a[1] for a,b in zip(out,out[1:])):
            raise ValueError('Face sampled profile is not ordered; adjust radial setting / helix / width.')
        return [(r*cos(t),r*sin(t),z) for r,t,z in out]

    def grids(self):
        hs=[self.low,self.high];grids=[[lo,hi] for lo,hi,k in self.bands]
        pitch=2*pi/self.v['wheel']
        delta=max(q['radius_upper_mm']-band[0] for q,band in zip(self.certificates,self.bands))
        segments=max(4,ceil(sqrt((self.outer*pitch*pitch+2*delta*pitch)/(8*REFINEMENT))))
        if segments>64:raise ValueError('Face crest/root arc sampling budget exhausted.')
        for _ in range(12):
            split=[]
            for a,b in zip(hs,hs[1:]):
                error=0.
                for xs,band in zip(grids,self.bands):
                    k=band[2]
                    for x in xs+[(u+v)/2 for u,v in zip(xs,xs[1:])]:
                        for side in (-1,1):
                            p=self.point(x,a,side,k);q=self.point(x,b,side,k)
                            for f in (.25,.5,.75):
                                actual=self.point(x,a+(b-a)*f,side,k)
                                error=max(error,sqrt(sum((actual[i]-p[i]-(q[i]-p[i])*f)**2 for i in range(3))))
                if error>REFINEMENT:split.append((a+b)/2)
            hs=sorted(hs+split);changed=bool(split)
            if len(hs)>129:raise ValueError('Face profile refinement budget exhausted.')
            for index,(xs,band) in enumerate(zip(grids,self.bands)):
                additions=[];k=band[2]
                rows={x:self.profile(x,hs,k,segments) for x in xs}
                for a,b in zip(xs,xs[1:]):
                    error=0.
                    for f in (.25,.5,.75):
                        actual=self.profile(a+(b-a)*f,hs,k,segments)
                        error=max(error,max(sqrt(sum((v[i]-p[i]-(q[i]-p[i])*f)**2 for i in range(3))) for v,p,q in zip(actual,rows[a],rows[b])))
                    if error>REFINEMENT:additions.append((a+b)/2)
                grids[index]=sorted(xs+additions);changed|=bool(additions)
                if len(grids[index])>65:raise ValueError('Face band refinement budget exhausted.')
            count=self.v['wheel']*(2*len(hs)+2*(segments-1))
            if count>12000 or count*(2*sum(len(q)-1 for q in grids)+4*len(grids)+10)>250000:
                raise ValueError('Face shared surface budget exhausted; reduce teeth / width / curvature.')
            if not changed:return hs,grids,segments
        raise ValueError('Face surface refinement did not converge within its budget.')

    def mesh(self,hs,grids,segments,profile=None):
        bottom=self.root_z-self.v['base'];root=self.root_z-bottom;pitch=2*pi/self.v['wheel']
        bands=[]
        for xs,band in zip(grids,self.bands):
            rows=[]
            for x in xs:
                one=(profile or self.profile)(x,hs,band[2],segments);loop=[]
                for tooth in range(self.v['wheel']):
                    c,s=cos(tooth*pitch),sin(tooth*pitch)
                    loop.extend((p[0]*c-p[1]*s,p[0]*s+p[1]*c,p[2]-bottom) for p in one)
                rows.append(loop)
            bands.append(rows)
        mesh=[]
        def face(points):
            clean=[]
            for p in points:
                if not clean or p!=clean[-1]:clean.append(p)
            if len(clean)>1 and clean[-1]==clean[0]:clean.pop()
            for a,b in zip(clean[1:],clean[2:]):
                p=clean[0];u=[a[i]-p[i] for i in range(3)];v=[b[i]-p[i] for i in range(3)]
                n=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
                if sum(q*q for q in n)>1e-24:mesh.append([[p,a,b]])
        def strip(a,b):
            for j in range(len(a)):
                n=(j+1)%len(a);face((a[j],b[j],b[n],a[n]))
        def atz(loop,z):return [(p[0],p[1],z) for p in loop]
        def circle_at(loop,r,z):return [(r*p[0]/hypot(p[0],p[1]),r*p[1]/hypot(p[0],p[1]),z) for p in loop]
        for rows in bands:
            for a,b in zip(rows,rows[1:]):strip(a,b)
            strip(atz(rows[0],root),rows[0]);strip(rows[-1],atz(rows[-1],root))
        for a,b in zip(bands,bands[1:]):strip(atz(a[-1],root),atz(b[0],root))
        inner=atz(bands[0][0],root);outer=atz(bands[-1][-1],root)
        bore=circle_at(inner,self.v['output_bore']/2,root);rim=circle_at(outer,self.outer,root)
        bottomrim=atz(rim,0);bottombore=atz(bore,0)
        strip(bore,inner);strip(outer,rim);strip(bottomrim,bottombore)
        strip(rim,bottomrim);strip(bottombore,bore)
        if len(mesh)>250000:raise ValueError('Face wheel exceeds the 250,000 shared triangle budget.')
        return mesh,bottom


def build(d):
    from geometry import Part,circle
    from rack_geometry import _stations
    g=Generator(d.values)
    if g.joined_surface:
        hs,xs,segments=g.joined_surface.grids()
        mesh,bottom=g.mesh(hs,xs,segments,g.joined_surface.profile)
    else:
        hs,xs,segments=g.grids();mesh,bottom=g.mesh(hs,xs,segments)
    pinion=g.pinion;pinion.stations,_=_stations(pinion)
    wheel=Part('Face_wheel',circle(g.outer),[circle(d.values['output_bore']/2)] if d.values['output_bore'] else [],
               g.height-g.low-bottom,bottom,mesh=mesh,color=(.23,.75,.65))
    pinion.color=(.96,.66,.33)
    for p,member,axis in ((pinion,'A','World +X through (0, offset, 2rp)' if g.e else 'World +X through (0, 0, 2rp)'),(wheel,'B','World +Z through origin')):
        p.port=dict(member=member,axis=axis)
        p.profile_metadata['face_profile']=dict(method='Generated equal-count involute pinion envelope',
            reference='NASA/CR2000-209909 eq21–24; NASA/CR2005-213443 eq15–18',
            refinement_threshold_mm=REFINEMENT,
            refinement_scope='Finite quarter/midpoint working-surface probes; not global manufacturing accuracy')
    d.parts.extend((pinion,wheel))
    d.analysis.update(signed_ratio=1/g.g,face_gear=dict(shaft_angle_deg=90,
        shaft_offset_mm=g.e,shortest_axis_distance_mm=abs(g.e),
        axis_intersection_mm=[0,0,g.height] if g.e==0 else None,
        pinion_axis_origin_mm=[0,g.e,g.height],
        pinion_reference_radius_mm=g.rp,wheel_reference_radius_mm=g.ref,blank_outer_radius_mm=g.outer,
        band_axial_intervals_mm=[[a,b] for a,b,k in g.bands],height_parameter_interval_mm=[g.low,g.high],
        face_addendum_coefficient=d.values['face_addendum'],base_thickness_mm=d.values['base'],
        regularity=g.certificates,engagement=g.engagement,height_grid_mm=hs,axial_grids_mm=xs,
        tooth_width_check='Conservative angular separation including an equal-radius correction for asymmetric flanks',
        face_mesh_triangles=len(mesh),construction='Orthogonal equal-count pinion envelope; custom stub crest/root relief',
        double_style=d.values.get('double_style'),tooth_band_count=1 if g.joined else len(g.bands),
        rolling_equation='wheel_rpm / pinion_rpm = pinion_teeth / wheel_teeth about the stated right-hand axes'))
    d.metrics.extend([f'Face gear shaft angle: 90° · reference radii {g.rp:.6f} / {g.ref:.6f} mm',
        f"Ideal connected-track engagement lower bound: {g.engagement['phase_span_lower_bound_teeth']:.6f} tooth pitches",
        f'Face wheel: {1 if g.joined else len(g.bands)} tooth band(s) · {len(mesh)} shared triangles',
        f'Face shaft offset: {g.e:+.6f} mm · shortest axis distance {abs(g.e):.6f} mm'])
    d.notes.extend(['Face wheel is generated as the envelope of the matching cylindrical involute pinion, using the normal-relative-velocity condition. Equal pinion/shaper tooth counts give ideal line contact; industrial localized contact and manufacturing cutter settings are not reproduced.',
        'Normal module/pressure refer to the pinion. Band setting locates the pinion beyond the reference wheel radius; band width is along the pinion shaft. Actual projected tooth-band ends can curve slightly. The circular backing blank includes untoothed inner/outer lands.',
        'Face crest uses the selected stub addendum. Nonworking root relief continues the virtual generating involute beyond the actual pinion tip; it is not a generated cutter-corner fillet. Pinion and face-space allowances split the reference pair backlash.',
        'Numerical float/libm Krawczyk enclosures and implicit derivatives check separated branches, analytic regularity, flank ordering and pointing limits. Connected ideal contact spans are sufficient lower bounds, not loaded contact or continuous sampled-solid clearance proofs.',
        'Face surfaces use finite quarter/midpoint refinement at 0.003 mm; transverse pinion profiles retain their existing sampling. Shared explicit triangles are used for preview, collision inspection, STL and faceted STEP. No global surface-error, manufacturing, strength or durability certification.',
        'Positive pinion speed is about world +X through (0,offset,2rp); positive face speed is about world +Z. Axis directions remain 90 degrees. Zero offset gives intersecting axes; nonzero offset gives skew axes separated by its absolute value. The wheel envelope is regenerated for the signed offset. Swapping roles preserves the physical geometry and bores.',
        'Supported absolute offset is below half the reference wheel radius, using NASA/CR2000-209909 eq69 as a conservative layout bound for all offered pinion types. Geometry checks can impose tighter limits; this bound does not establish sliding losses, heat or loaded contact.'])
    if g.joined:
        d.analysis['face_gear']['joined_transition']=g.joined_surface.info() if g.joined_surface else dict(method='Zero-helix continuous spur limit')
        if g.joined_surface:
            d.analysis['face_gear']['axial_grids_mm']=None
            d.analysis['face_gear']['joined_transition'].update(parameter_grid=xs[0],
                radial_grids_by_height_mm=[[g.joined_surface.radius(t,h) for t in xs[0]] for h in hs])
        d.notes.append('Joined double helix uses one continuous tooth band. Convex pinion cusp edges generate the central transition; overlapping concave envelopes are trimmed at their intersection. Joined teeth use a common circular annular domain inside both supported pinion spans. Smooth patches retain numerical enclosures; cusp/trim root solves and finite surface refinement do not establish a global joined-surface error or manufacturing certificate. No equal loading or net axial-force cancellation is established.')
    elif len(g.bands)>1:d.notes.append('Double helical uses two separated, opposite-handed working bands and a continuous pinion core. One complete track per flank suffices; equal band loading or net axial-force cancellation is not established.')
    d.requirements.append(CATALOG_REASON)
