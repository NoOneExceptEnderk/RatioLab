# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Rack envelopes and constructed internal fillets, in millimetres.

No CAD dependency. Coordinates use a tooth centred on +X. See
CALCULATIONS.md for profile conventions, domains and references, and VARIANTS.md
for the separate worm and strain wave study geometry.
"""
from math import sin, cos, tan, atan, atan2, acos, sqrt, hypot, pi, radians

TOLERANCE = 0.015


def rack_parameters(z, mt, pressure, backlash=0.15, depth=None, shift=0,
                    normal_pressure=None, hf=1.25):
    mn = mt if depth is None else depth
    at = radians(pressure)
    an = radians(pressure if normal_pressure is None else normal_pressure)
    # cos(beta) inferred from the normal/transverse pressure and module data.
    cb = mn / mt
    if not (z >= 3 and 0 < cb <= 1.00000001 and 0 < an < pi/2 and 0 < at < pi/2):
        raise ValueError('Rack envelope outside its cylindrical gear domain.')
    land = pi*mn/4 + backlash*cb/4 - hf*mn*tan(an)
    if land <= mn*.025:
        raise ValueError('Impossible rack: dedendum and pressure angle eliminate the tool tip land.')
    rho = min(.3*mn, (land-mn*.025)*cos(an)/(1-sin(an)))
    return dict(pitch_radius=mt*z/2, normal_module=mn, transverse_module=mt,
                alpha_normal=an, alpha_transverse=at, cos_beta=cb,
                tip_radius=rho, tip_center_u=land-rho*(1-sin(an))/cos(an),
                tip_center_v=-hf*mn+rho+shift*mn, shift=shift,
                backlash_transverse=backlash, dedendum=hf)


def rack_point(tool, t):
    """Envelope of the rounded RIGHT corner of one rack cutting tooth.

    Rack in blank-fixed coordinates: R(-phi) (u-Rp*phi, Rp+v).
    u is transverse tangential; normal section is stretched by 1/cos(beta).
    phi=(u+v*v'/u')/Rp follows zero normal relative velocity.
    Result rotated by -pi/2+pi/z in external_half below.
    """
    r = tool['pitch_radius']; rho = tool['tip_radius']; cb = tool['cos_beta']
    u = (tool['tip_center_u']+rho*cos(t))/cb
    v = tool['tip_center_v']+rho*sin(t)
    dx = -rho*sin(t)/cb; dy = rho*cos(t)
    phi = (u+v*dy/dx)/r
    x, y = u-r*phi, r+v
    return x*cos(phi)+y*sin(phi), -x*sin(phi)+y*cos(phi)


def external_half(z, mt, pressure, backlash, depth, shift, normal_pressure, ha, hf, sample):
    """Positive flank from dedendum land through rack fillet to addendum."""
    tool = rack_parameters(z, mt, pressure, backlash, depth, shift, normal_pressure, hf)
    rp=tool['pitch_radius']; rb=rp*cos(tool['alpha_transverse']); mn=tool['normal_module']
    root=rp-mn*(hf-shift); tip=rp+mn*(ha+shift)
    if root <= 0 or tip <= rb or tip <= root:
        raise ValueError('Impossible gear blank for the rack envelope.')
    half=pi/(2*z)-backlash/(4*rp)+2*shift*tan(tool['alpha_normal'])/z
    inv=lambda r: sqrt(max(0,(r/rb)**2-1))-atan(sqrt(max(0,(r/rb)**2-1)))
    angle=lambda r: half+inv(rp)-inv(r)
    if not 0 < angle(tip) < pi/z:
        raise ValueError('Pointed or overlapping tooth: check shift, addendum and backlash.')
    rotation=-pi/2+pi/z
    def corner(t):
        x,y=rack_point(tool,t)
        return (x*cos(rotation)-y*sin(rotation), x*sin(rotation)+y*cos(rotation))
    lo=-pi/2; end=-tool['alpha_normal']
    # A straight rack flank has a reversed involute below its cusp. Remove
    # this branch by intersecting the corner envelope with the usable flank.
    vend=tool['tip_center_v']-tool['tip_radius']*sin(tool['alpha_normal'])
    undercut=vend < -rp*sin(tool['alpha_transverse'])**2-1e-10
    def residual(t):
        x,y=corner(t); r=hypot(x,y)
        return atan2(y,x)-angle(r) if r>=rb else None
    if undercut:
        # Locate the base-circle crossing FIRST. A uniform parameter grid can
        # miss the extremely narrow intersection near the undercut threshold.
        left=lo;right=end
        if hypot(*corner(end))<rb-1e-10:
            raise ValueError('Rack undercut removes the usable involute flank.')
        for _ in range(60):
            mid=(left+right)/2
            if hypot(*corner(mid))<rb:left=mid
            else:right=mid
        left=right;right=end;fl=residual(left);fr=residual(right)
        if fl is None or fl>1e-10 or fr<-1e-10:
            raise ValueError('Unable to bracket the usable rack/involute intersection.')
        for _ in range(60):
            mid=(left+right)/2;fm=residual(mid)
            if fm is None or fm<0:left=mid
            else:right=mid
        end=(left+right)/2
    start=corner(end); start_r=hypot(*start)
    if start_r>=tip-1e-9:
        raise ValueError('Rack fillet reaches the tooth tip; no usable involute remains.')
    fillet=sample(corner,lo,end)
    # Radius ordering keeps the re-entrant undercut simple. Its angle need
    # not be monotonic: requiring that would incorrectly reject undercut.
    checks=[corner(lo+(end-lo)*j/256) for j in range(257)]
    angles=[atan2(y,x) for x,y in checks]
    if angles[0]>=pi/z or min(angles)<=0 or any(hypot(*b)<hypot(*a)-1e-9 for a,b in zip(checks,checks[1:])):
        raise ValueError('Rack envelope has overlapping roots or a non-simple flank.')
    flank=sample(lambda r:(r*cos(angle(r)),r*sin(angle(r))),start_r,tip)
    points=fillet[:-1]+flank
    metadata=dict(method='rounded normal rack envelope', tool=tool, tool_units='mm and radians; dimensionless shift/cos_beta', generated=True,
                  undercut_trimmed=undercut, involute_start_radius_mm=start_r,
                  root_radius_mm=root, tip_radius_mm=tip,
                  chord_threshold_mm=TOLERANCE,
                  domain='external cylindrical; normal circular rack tip; no protuberance or tip relief')
    return points,metadata


def internal_half(z, mt, pressure, backlash, depth, ha, hf, sample):
    """Positive internal flank, tip to root; tangent circular construction.

    Deliberately NOT a shaping-cutter envelope. A circular
    blend is tangent both to the involute and the internal dedendum circle.
    """
    rp=mt*z/2; rb=rp*cos(radians(pressure)); root=rp+hf*depth;tip=rp-ha*depth
    inv=lambda r:sqrt(max(0,(r/rb)**2-1))-atan(sqrt(max(0,(r/rb)**2-1)))
    half=pi/(2*z)-backlash/(4*rp)
    angle=lambda r:half+inv(r)-inv(rp)
    if tip<=rb or angle(tip)<=0 or angle(root)>=pi/z:
        raise ValueError('Internal ring outside the unshifted involute construction domain.')
    nominal_rho=min(.3*depth,.2*(root-tip))
    def solve(rho):
        def center(r):
            q=angle(r); derivative=sqrt(max(0,r*r-rb*rb))/(rb*r)
            tx=cos(q)-r*sin(q)*derivative;ty=sin(q)+r*cos(q)*derivative;norm=hypot(tx,ty)
            return r*cos(q)-rho*ty/norm,r*sin(q)+rho*tx/norm
        left=tip;right=root
        if hypot(*center(left))>=root-rho:return None
        for _ in range(50):
            mid=(left+right)/2
            if hypot(*center(mid))>root-rho:right=mid
            else:left=mid
        join=(left+right)/2;cx,cy=center(join);q=angle(join)
        t0=atan2(join*sin(q)-cy,join*cos(q)-cx);t1=atan2(cy,cx)
        while t1<t0:t1+=2*pi
        return join,cx,cy,t0,t1
    def fits(solution):
        return solution is not None and solution[0]>tip+1e-7 and 0<solution[4]-solution[3]<pi and solution[4]<pi/z-1e-8
    rho=nominal_rho;solution=solve(rho)
    if not fits(solution):
        # The nominal blend is a construction preference, not a reason to
        # reject a viable involute. Find its largest fitting radius, then
        # leave a 10% margin to the adjacent root blend.
        left=0.;right=nominal_rho
        for _ in range(45):
            mid=(left+right)/2
            if fits(solve(mid)):left=mid
            else:right=mid
        rho=.9*left
        if rho<max(1e-6,depth*1e-6):
            raise ValueError('Internal ring has no resolvable tangent root blend.')
        solution=solve(rho)
        if not fits(solution):raise ValueError('Unable to construct a simple internal root blend.')
    join,cx,cy,t0,t1=solution
    flank=sample(lambda r:(r*cos(angle(r)),r*sin(angle(r))),tip,join)
    arc=sample(lambda t:(cx+rho*cos(t),cy+rho*sin(t)),t0,t1)
    return flank[:-1]+arc,dict(method='tangent circular internal root construction',
        generated=False,blend_radius_mm=rho,nominal_blend_radius_mm=nominal_rho,
        blend_radius_adapted=rho<nominal_rho,involute_end_radius_mm=join,
        root_radius_mm=root,tip_radius_mm=tip,chord_threshold_mm=TOLERANCE,
        domain='unshifted internal involute; pinion-cutter envelope/interference unverified')
