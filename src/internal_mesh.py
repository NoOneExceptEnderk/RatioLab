# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Paired planetary construction and bounded continuous polygon clearance.

All lengths are mm and phases radians. The proof concerns the actual transverse
polylines at unloaded neutral backlash, not unsampled curves or exported solids.
"""
from copy import deepcopy
from functools import lru_cache
from math import pi, sin, cos, tan, atan, radians, degrees, sqrt, hypot, inf, isfinite

CONSTRUCTION_VERSION = 'planetary_paired_involute_v1'
PLAN_INTERVAL_BUDGET = 1024
SCOPE = ('continuous separation of generated transverse polygons over one tooth '
         'period at neutral backlash; excludes analytic curve sampling error, '
         'loaded contact, CAD/STL axial interpolation, cutter and manufacturing checks')


def _cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def _point_segment2(p, a, b):
    x=b[0]-a[0]; y=b[1]-a[1]; den=x*x+y*y
    t=max(0.,min(1.,((p[0]-a[0])*x+(p[1]-a[1])*y)/den)) if den else 0.
    return (p[0]-a[0]-t*x)**2+(p[1]-a[1]-t*y)**2


def _segment_distance2(a, b, c, d):
    u=_cross(a,b,c); v=_cross(a,b,d); w=_cross(c,d,a); x=_cross(c,d,b)
    proper=(u*v<0 and w*x<0)
    if proper: return 0., True
    return min(_point_segment2(a,c,d),_point_segment2(b,c,d),
               _point_segment2(c,a,b),_point_segment2(d,a,b)), False


def _inside(p, loop):
    inside=False; x,y=p
    for a,b in zip(loop,loop[1:]+loop[:1]):
        if (a[1]>y)!=(b[1]>y) and x < (b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:
            inside=not inside
    return inside


def _box(segment):
    a,b,_=segment
    return min(a[0],b[0]),min(a[1],b[1]),max(a[0],b[0]),max(a[1],b[1])


def _tree(segments):
    boxes=[_box(s) for s in segments]
    box=(min(b[0] for b in boxes),min(b[1] for b in boxes),
         max(b[2] for b in boxes),max(b[3] for b in boxes))
    if len(segments)<=6: return box,segments,None
    axis=0 if box[2]-box[0]>=box[3]-box[1] else 1
    segments=sorted(segments,key=lambda s:s[0][axis]+s[1][axis]); k=len(segments)//2
    return box,_tree(segments[:k]),_tree(segments[k:])


def _box_distance2(a,b):
    dx=max(0.,a[0]-b[2],b[0]-a[2]); dy=max(0.,a[1]-b[3],b[1]-a[3])
    return dx*dx+dy*dy


def _nearest(a,b,node,best):
    box,left,right=node; query=(min(a[0],b[0]),min(a[1],b[1]),max(a[0],b[0]),max(a[1],b[1]))
    if _box_distance2(query,box)>best: return best,None
    if right is None:
        witness=None
        for c,d,index in left:
            if _box_distance2(query,_box((c,d,index)))>best: continue
            distance,crossing=_segment_distance2(a,b,c,d)
            if crossing:return 0.,index
            if distance<best:best=distance
        return best,witness
    children=sorted((left,right),key=lambda child:_box_distance2(query,child[0]))
    for child in children:
        best,witness=_nearest(a,b,child,best)
        if witness is not None:return best,witness
    return best,None


def _pair_nearest(planet_tree, ring_tree, cp, sp, tx, ty):
    """Dual BVH traversal; transform boxes lazily, retain exact leaf distances."""
    cache={}
    def transformed_node(node):
        key=id(node)
        if key not in cache:
            b=node[0]; x=(b[0]+b[2])/2; y=(b[1]+b[3])/2
            hx=(b[2]-b[0])/2;hy=(b[3]-b[1])/2
            cx=tx+cp*x-sp*y;cy=ty+sp*x+cp*y
            ex=abs(cp)*hx+abs(sp)*hy;ey=abs(sp)*hx+abs(cp)*hy
            cache[key]=(cx-ex,cy-ey,cx+ex,cy+ey)
        return cache[key]
    best=inf; witness=None
    pending=[(planet_tree,ring_tree)]
    while pending:
        p,r=pending.pop(); pb=transformed_node(p)
        if _box_distance2(pb,r[0])>best:continue
        if p[2] is None and r[2] is None:
            for a,b,i in p[1]:
                aa=(tx+cp*a[0]-sp*a[1],ty+sp*a[0]+cp*a[1])
                bb=(tx+cp*b[0]-sp*b[1],ty+sp*b[0]+cp*b[1])
                qb=(min(aa[0],bb[0]),min(aa[1],bb[1]),max(aa[0],bb[0]),max(aa[1],bb[1]))
                if _box_distance2(qb,r[0])>best:continue
                for c,d,j in r[1]:
                    if _box_distance2(qb,_box((c,d,j)))>best:continue
                    distance,crossing=_segment_distance2(aa,bb,c,d)
                    if crossing:return 0.,dict(planet_segment=i,ring_segment=j)
                    best=min(best,distance)
        else:
            if r[2] is None or (p[2] is not None and (pb[2]-pb[0])*(pb[3]-pb[1])>(r[0][2]-r[0][0])*(r[0][3]-r[0][1])):
                children=[(p[1],r),(p[2],r)]
            else:children=[(p,r[1]),(p,r[2])]
            children.sort(key=lambda pair:_box_distance2(transformed_node(pair[0]),pair[1][0]),reverse=True)
            pending.extend(children)
    return sqrt(best),witness


def polygon_pose_clearance(planet, ring, tree=None):
    """Exact segment distances plus containment; proper crossing is a witness.

    A zero distance without a proper crossing remains ambiguous (touch/overlap).
    """
    tree=tree or _tree([(a,b,i) for i,(a,b) in enumerate(zip(ring,ring[1:]+ring[:1]))])
    best=inf
    for index,(a,b) in enumerate(zip(planet,planet[1:]+planet[:1])):
        best,crossing=_nearest(a,b,tree,best)
        if crossing is not None:return 'collision',0.,dict(planet_segment=index,ring_segment=crossing)
    distance=sqrt(best)
    if distance<=1e-10:return 'unresolved',distance,{}
    if not _inside(planet[0],ring):return 'collision',distance,dict(reason='planet outside ring void')
    return 'clear',distance,{}


def verify_internal_polygon_pair(planet_loop, ring_void, phaseP, phaseR, zp, zr,
                                 center_distance_mm=0., budget=4096, max_depth=20,
                                 numeric_guard_mm=1e-7, backlash_mm=None):
    """Certify intervals by d(mid) > motion_bound + guard, or fail visibly.

    Simple closed contours and tooth periodicity must be supplied by the caller's generated gear contours.
    Arbitrary fixtures can use zp=zr=1 to verify a full rotation.
    """
    if not all(isfinite(q) for q in (zp,zr,phaseP,phaseR,center_distance_mm,numeric_guard_mm)) or zp<=0 or zr<=0 or numeric_guard_mm<=0:
        raise ValueError('Invalid internal polygon verification domain.')
    if not isinstance(budget,int) or not isinstance(max_depth,int) or not 0<=budget<=4096 or not 0<=max_depth<=20:
        raise ValueError('Verification limits must be finite integers within budget 4096 and depth 20.')
    period=2*pi/zp; ratio=zp/zr
    result=dict(status='unresolved',scope=SCOPE,phase_period_rad=period,ratio=ratio,
                numeric_guard_mm=numeric_guard_mm,certified_separation_lower_bound_mm=None,
                observed_minimum_distance_mm=None,evaluated_intervals=0,max_depth=0,
                budget=budget,failure_reason=None)
    if backlash_mm is not None and backlash_mm<=4*numeric_guard_mm:
        result['failure_reason']='Zero or numerically tiny backlash cannot certify strict separation.'; return result
    if any(not isfinite(q) for loop in (planet_loop,ring_void) for point in loop for q in point):
        raise ValueError('Polygon coordinates must be finite.')
    if min(len(planet_loop),len(ring_void))<3 or len(planet_loop)+len(ring_void)>30000:
        result['failure_reason']='Unsupported contour complexity.';return result
    tree=_tree([(a,b,i) for i,(a,b) in enumerate(zip(ring_void,ring_void[1:]+ring_void[:1]))])
    planet_tree=_tree([(a,b,i) for i,(a,b) in enumerate(zip(planet_loop,planet_loop[1:]+planet_loop[:1]))])
    # In the static ring frame X(q)=R(-kq)(a,0)+R((1-k)q)p.
    # Its speed is bounded by a*k+RmaxP*|1-k|; the ring is fixed.
    speed=abs(center_distance_mm*ratio)+abs(1-ratio)*max(hypot(*p) for p in planet_loop)
    pending=[(0.,period,0)]; lower=inf; observed=inf
    while pending:
        if result['evaluated_intervals']>=budget:
            result['failure_reason']='Interval evaluation budget exhausted.';break
        start,end,depth=pending.pop(); q=(start+end)/2; ap=phaseP+q; ar=phaseR+ratio*q
        # Ring frame: its boundary stays fixed, including its BVH.
        cp=cos(ap-ar);sp=sin(ap-ar);cr=cos(ar);sr=sin(ar)
        tx=center_distance_mm*cr;ty=-center_distance_mm*sr
        distance,witness=_pair_nearest(planet_tree,tree,cp,sp,tx,ty)
        p=planet_loop[0];point=(tx+cp*p[0]-sp*p[1],ty+sp*p[0]+cp*p[1])
        status='collision' if witness is not None else 'unresolved' if distance<=numeric_guard_mm else 'clear' if _inside(point,ring_void) else 'collision'
        witness=witness or {}
        observed=min(observed,distance);result['evaluated_intervals']+=1
        result['max_depth']=max(depth,result['max_depth'])
        if status=='collision':
            result.update(status='collision',failure_reason='Boundary crossing or failed containment.',witness=dict(phase_planet_rad=ap,phase_ring_rad=ar,**witness));break
        bound=speed*(end-start)/2
        if status=='clear' and distance>bound+numeric_guard_mm:
            lower=min(lower,distance-bound);continue
        if depth>=max_depth or distance<=numeric_guard_mm:
            result['failure_reason']='Touch, tiny separation or subdivision depth limit.';break
        pending.extend(((q,end,depth+1),(start,q,depth+1)))
    else:
        result.update(status='clear',certified_separation_lower_bound_mm=lower)
    result['observed_minimum_distance_mm']=observed if observed<inf else None
    return result


def _same_radial_directions(a,b):
    return len(a)==len(b) and all(abs(p[0]*q[1]-p[1]*q[0])<=1e-10*max(1,hypot(*p)*hypot(*q)) and p[0]*q[0]+p[1]*q[1]>0 for p,q in zip(a,b))


def validate_axial_pair(planet, ring, zp, zr):
    """Check the supported common axial phase law and material subsets.

    profile_sections uses linear twist, or the same triangular twist in each
    double half. Groove shoulders interpolate corresponding radial vertices.
    This concerns ideal transverse sections, not the loft triangles between them.
    """
    from geometry import profile_sections, section_holes
    if planet.stations or ring.stations or planet.width!=ring.width or planet.double!=ring.double or planet.gap!=ring.gap:
        return 'Unsupported axial placement or section construction.'
    if abs(ring.twist-zp/zr*planet.twist)>1e-9:
        return 'Internal helical section phases do not preserve the mesh ratio.'
    if planet.double:
        # Strong disc bounds avoid inferring polygon containment merely from
        # corresponding vertex radii on a concave outline.
        planet_min=min(sqrt(_point_segment2((0.,0.),a,b)) for a,b in zip(planet.outer,planet.outer[1:]+planet.outer[:1]))
        ring_max=max(hypot(*p) for p in ring.holes[0])
        # A common radial vertex order also keeps every ideal shoulder
        # interpolation inside the corresponding origin/edge triangle fan.
        if any(_cross((0.,0.),a,b)<-1e-9 for loop in (planet.outer,ring.holes[0]) for a,b in zip(loop,loop[1:]+loop[:1])):
            return 'Unsupported axial profile without a radial triangle fan.'
        if not _inside((0.,0.),planet.outer) or not _inside((0.,0.),ring.holes[0]):
            return 'Unsupported noncentral axial profile.'
        for _,_,outer in profile_sections(planet):
            if outer is not planet.outer and (not _same_radial_directions(outer,planet.outer) or max(hypot(*p) for p in outer)>planet_min+1e-9):
                return 'Planet groove core is not a certified material subset.'
        for z,_,outer in profile_sections(ring):
            hole=section_holes(ring,z,outer)[0]
            if max(abs(a-b) for p,q in zip(hole,ring.holes[0]) for a,b in zip(p,q))<1e-8:continue
            if not _same_radial_directions(hole,ring.holes[0]) or not _inside((0.,0.),hole):
                return 'Unsupported ring groove contour.'
            minimum=min(sqrt(_point_segment2((0.,0.),a,b)) for a,b in zip(hole,hole[1:]+hole[:1]))
            if minimum<ring_max-1e-9:
                return 'Ring groove is not a certified enlargement of the verified void.'
    return None


def plan_planetary_internal_pair(zp,zr,mn,alpha_n=20,beta=0,backlash=.15,
                                profile_chord_threshold_mm=.015):
    """Return a detached cached plan; RPM, width and stage do not enter its key."""
    return deepcopy(_plan(zp,zr,mn,alpha_n,beta,backlash,profile_chord_threshold_mm))


@lru_cache(maxsize=16)
def _plan(zp,zr,mn,alpha_n,beta,backlash,tolerance):
    from geometry import involute
    from tooth_profiles import external_half,internal_half
    if tolerance!=.015:raise ValueError('Only the shared 0.015 mm profile chord threshold is supported.')
    if not all(isfinite(q) for q in (zp,zr,mn,alpha_n,beta,backlash)) or mn<=0 or zp<=0 or zr<=zp or backlash<0:
        raise ValueError('Invalid planetary internal pair dimensions.')
    mt=mn/cos(radians(beta)); at=atan(tan(radians(alpha_n))/cos(radians(beta)))
    rp=mt*zp/2; rr=mt*zr/2; a=rr-rp; bp=rp*cos(at); br=rr*cos(at)
    endpoints=lambda f,a,b:[f(a),f(b)]
    _,planet_info=external_half(zp,mt,degrees(at),backlash,mn,0,alpha_n,1,1.25,endpoints)
    start=planet_info['involute_start_radius_mm']; tip=rp+mn
    delta=max(.05*mn,4*tolerance)
    if delta>=.25*mn:raise ValueError('Module too small for the paired radial margin at the current chord threshold.')
    rt=max(rr-mn,a+start+delta); ha=(rr-rt)/mn
    if not 0<ha<=1 or rt<=br:raise ValueError('Paired ring tip cannot fit the usable involute domain.')
    minimum_join=a+tip+delta
    _,ring_info=internal_half(zr,mt,degrees(at),backlash,mn,ha,1.25,endpoints,minimum_join)
    join=ring_info['involute_end_radius_mm']; span=a*sin(at)
    low=sqrt(rt*rt-br*br)-span; high=sqrt(tip*tip-bp*bp)
    lower_roll=sqrt(max(0,start*start-bp*bp)); upper_roll=sqrt(join*join-br*br)
    ea=(high-low)/(pi*mt*cos(at))
    if low<lower_roll-1e-8 or high+span>upper_roll+1e-8 or ea<1:
        raise ValueError('Paired planetary full nominal contact interval is outside usable involutes or below one transverse contact ratio.')
    planet=involute(zp,mt,degrees(at),backlash,depth_module=mn,normal_pressure=alpha_n)
    ring=involute(zr,mt,degrees(at),backlash,True,depth_module=mn,ha=ha,minimum_join_radius_mm=minimum_join)
    phaseP=pi/zp+pi;phaseR=(zp*phaseP-pi)/zr
    actual_min=min(sqrt(_point_segment2((0.,0.),p,q)) for p,q in zip(ring,ring[1:]+ring[:1]))
    actual_max=max(hypot(*p) for p in planet)
    if actual_min<a+start+delta-1e-8 or actual_max>tip+1e-8:
        raise ValueError('Generated polygons violate the paired radial exclusions.')
    verification=verify_internal_polygon_pair(planet,ring,phaseP,phaseR,zp,zr,a,budget=PLAN_INTERVAL_BUDGET,backlash_mm=backlash)
    if verification['status']=='collision':raise ValueError('Paired planetary polygon collision: '+str(verification.get('witness')))
    return dict(construction_version=CONSTRUCTION_VERSION,construction_inputs=dict(zp=zp,zr=zr,mn=mn,alpha_n_deg=alpha_n,beta_deg=beta,backlash_mm=backlash),ring_addendum_coefficient=ha,ring_dedendum_coefficient=1.25,
                ring_tip_relief_mm=rt-(rr-mn),actual_ring_min_radius_mm=actual_min,actual_planet_max_radius_mm=actual_max,delta_mm=delta,planet_involute_start_radius_mm=start,
                planet_tip_radius_mm=tip,ring_tip_radius_mm=rt,ring_root_radius_mm=rr+1.25*mn,
                ring_join_radius_mm=join,minimum_join_radius_mm=minimum_join,
                ring_blend_radius_mm=ring_info['blend_radius_mm'],
                planet_root_exclusion_margin_mm=rt-a-start,ring_root_exclusion_margin_mm=join-a-tip,
                nominal_planet_roll_min_mm=low,nominal_planet_roll_max_mm=high,
                planet_roll_margin_mm=low-lower_roll,ring_roll_margin_mm=upper_roll-high-span,
                contact_transverse=ea,center_distance_mm=a,planet_profile=planet_info,ring_profile=ring_info,
                verification=verification)
