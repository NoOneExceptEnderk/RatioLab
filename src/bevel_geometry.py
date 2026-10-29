# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Exact spherical involute flanks, sampled in planar axial sections.

Dong et al., DOI 10.3389/fmech.2025.1643228, section 2 equation 1;
Wang et al., DOI 10.2174/1874155X01105010051, equation 22. See the
differential technical reference for frames, trace and nonworking root relief.
Lengths are mm; all angles here are radians, except ``pressure``/``beta``.
"""
from dataclasses import dataclass
from math import asin, acos, atan, atan2, cos, sin, tan, log, pi, radians, hypot

PROFILE_TOLERANCE = .003


def spherical_involute(theta, base):
    """Azimuth unrolled from the base cone, NOT a planar involute."""
    if theta < base - 1e-12:
        raise ValueError('A spherical involute has no working branch below its base cone.')
    t = acos(max(-1., min(1., cos(theta) / cos(base))))
    return t / sin(base) - atan2(sin(t), sin(base) * cos(t))


@dataclass(frozen=True)
class SphericalProfile:
    teeth: int
    delta: float
    base: float
    root: float
    tip: float
    outer_distance: float
    backlash: float
    k: float

    def half_angle(self, theta):
        # The constant-angle continuation is deliberately nonworking relief.
        working = max(theta, self.base)
        pitch_radius = self.outer_distance * sin(self.delta)
        return (pi / (2 * self.teeth) - self.backlash / (4 * pitch_radius)
                + spherical_involute(self.delta, self.base)
                - spherical_involute(working, self.base))

    def point(self, theta, distance, side=1, phase=0):
        """Analytic flank point on a sphere of radius ``distance``."""
        azimuth = phase + self.k * log(distance / self.outer_distance) + side * self.half_angle(theta)
        r = distance * sin(theta)
        return r * cos(azimuth), r * sin(azimuth), distance * cos(theta)

    def section_point(self, theta, z, side=1, phase=0):
        # A section's pitch distance is NOT the distance of a flank vertex.
        return self.point(theta, z / cos(theta), side, phase)[:2]


def parameters(teeth, mate_teeth, module, pressure, backlash=0, beta=0, hand=1):
    """Historical planar heel/tip dimensions, with compatible root clearance.

    Root relief is deepened when necessary to clear the mating addendum cone.
    It is not a cutter fillet or a prediction of root strength.
    """
    if not (teeth >= 3 and mate_teeth >= 3 and module > 0 and 0 < pressure < 90
            and backlash >= 0 and 0 <= beta <= 45 and hand in (-1, 1)):
        raise ValueError('Spherical bevel parameters are outside their supported domain.')
    delta = atan2(teeth, mate_teeth)
    outer = hypot(teeth, mate_teeth) * module / 2
    base = asin(sin(delta) * cos(radians(pressure)))
    tip = atan2(teeth + 2, mate_teeth)
    mate_tip = atan2(mate_teeth + 2, teeth)
    root = min(atan2(teeth - 2.5, mate_teeth), pi / 2 - mate_tip - .25 * module / outer)
    if root <= 0:
        raise ValueError('The bevel tooth root reaches the cone apex.')
    # At the base-cone cusp, solve n.(omega_relative x r)=0. A mate
    # addendum beyond this angle would require a reversed/below-base flank.
    limit = acos(max(-1., min(1., sin(base)**2 / (cos(base) * tan(delta)))))
    if mate_tip >= limit - 1e-9:
        raise ValueError('The mating bevel tip requires below-base contact; increase tooth counts or pressure angle.')
    q = SphericalProfile(teeth, delta, base, root, tip, outer, backlash,
                         hand * tan(radians(beta)) / sin(delta))
    if not 0 < q.half_angle(tip) < q.half_angle(root) < pi / teeth:
        raise ValueError('Pointed or overlapping spherical bevel teeth; reduce backlash or increase tooth count.')
    return q


def engagement(a, b, width):
    """Available contact-phase span, accounting for BOTH planar end caps.

    On the common unit-sphere action great circle, s=0 is the pitch point,
    x=cos(delta)cos(s)-sin(alpha)sin(delta)sin(s),
    z=sin(delta)cos(s)+sin(alpha)cos(delta)sin(s).
    Gear phase is s/sin(base)-k*ln(R/R_outer), up to a fixed offset.
    The connected admissible (s,R) domain maps to a connected phase interval.
    Its boundary phases are linear in s plus k*ln(cos(s+offset)). All extrema
    occur at the ends, the branch change s=0, or tan(s+offset)=1/(k*sin(base)).
    """
    outer=a.outer_distance;inner=outer-width
    if not 0<inner<outer:
        raise ValueError('Bevel engagement requires a positive inner cone distance.')
    sa=(max(0., 1-(sin(a.base)/sin(a.delta))**2))**.5
    if sa<=0:
        raise ValueError('Bevel engagement requires positive transverse pressure.')
    gamma_a=atan(sa*tan(a.delta));gamma_b=atan(sa*tan(b.delta))
    t_a=acos(max(-1.,min(1.,cos(a.tip)/cos(a.base))))
    t_b=acos(max(-1.,min(1.,cos(b.tip)/cos(b.base))))
    slo=gamma_b-t_b;shi=t_a-gamma_a
    # z/x must lie between toe_B/heel_A and heel_B/toe_A.
    low_ratio=inner/outer*tan(a.delta);high_ratio=outer/inner*tan(a.delta)
    slo=max(slo,atan(tan(atan(low_ratio)-a.delta)/sa))
    shi=min(shi,atan(tan(atan(high_ratio)-a.delta)/sa))
    if not slo<shi:
        raise ValueError('The bevel end faces leave no common working contact interval.')
    candidates=[slo,shi]
    if slo<0<shi:candidates.append(0.)
    if a.k:
        for sign in (-1,1):
            for offset in (gamma_a,-gamma_b):
                critical=atan(1/(sign*a.k*sin(a.base)))-offset
                for winding in (-1,0,1):
                    value=critical+winding*pi
                    if slo<value<shi:candidates.append(value)
    phases=[[],[]]
    for s in candidates:
        x=cos(a.delta)*cos(s)-sa*sin(a.delta)*sin(s)
        z=sin(a.delta)*cos(s)+sa*cos(a.delta)*sin(s)
        low=max(inner*cos(a.delta)/x,inner*cos(b.delta)/z)
        high=min(outer*cos(a.delta)/x,outer*cos(b.delta)/z)
        if low>high+1e-10:continue
        for R in (low,high):
            # Reflecting the working flank reverses the trace's contribution
            # relative to the action parameter. Both drive directions matter.
            for sign,values in zip((-1,1),phases):
                values.append(s/sin(a.base)-sign*a.k*log(R/outer))
    ratios=[(max(values)-min(values))/(2*pi/a.teeth) for values in phases]
    ratio=min(ratios)
    return dict(contact_phase_span_teeth=ratio,
                flank_contact_phase_spans_teeth=ratios,
                action_angle_interval_rad=[slo,shi],
                method='Connected spherical action domain with both planar cap intervals; analytic boundary-phase extrema',
                scope='Ideal unmodified working flanks, independent of load and manufacturing error')


def _sample(fn, lo, hi, tolerance, depth=0):
    """Quarter/midpoint refinement, with explicit refusal on budget exhaustion."""
    a, b = fn(lo), fn(hi)
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx*dx + dy*dy
    def deviation(p):
        f = max(0, min(1, ((p[0]-a[0])*dx+(p[1]-a[1])*dy)/length2)) if length2 else 0
        return hypot(p[0]-a[0]-f*dx, p[1]-a[1]-f*dy)
    error = max(deviation(fn(lo+(hi-lo)*f)) for f in (.25, .5, .75))
    if error <= tolerance:
        return [a, b]
    if depth >= 16:
        raise ValueError('Spherical bevel section exceeds its refinement budget.')
    mid = (lo+hi)/2
    return _sample(fn, lo, mid, tolerance, depth+1)[:-1] + _sample(fn, mid, hi, tolerance, depth+1)


def section(q, z, phase=0, tolerance=PROFILE_TOLERANCE):
    """One counterclockwise planar heel contour, repeated tooth by tooth."""
    pitch = 2*pi/q.teeth
    # Below-base relief and the working involute meet at a real cusp: do not
    # interpolate across it with one adaptive interval.
    levels = [q.root] + ([q.base] if q.root < q.base < q.tip else []) + [q.tip]
    points = []
    for tooth in range(q.teeth):
        centre = phase+tooth*pitch
        root_phase = centre+q.k*log(z/(cos(q.root)*q.outer_distance))
        tip_phase = centre+q.k*log(z/(cos(q.tip)*q.outer_distance))
        def arc(theta, start, end):
            radius = z*tan(theta)
            return _sample(lambda a:(radius*cos(a), radius*sin(a)), start, end, tolerance)
        points += arc(q.root, root_phase-pitch/2, root_phase-q.half_angle(q.root))[:-1]
        for a,b in zip(levels, levels[1:]):
            points += _sample(lambda theta:q.section_point(theta,z,-1,centre),a,b,tolerance)[:-1]
        points += arc(q.tip, tip_phase-q.half_angle(q.tip), tip_phase+q.half_angle(q.tip))[:-1]
        for a,b in zip(reversed(levels[1:]),reversed(levels[:-1])):
            points += _sample(lambda theta:q.section_point(theta,z,1,centre),a,b,tolerance)[:-1]
        points += arc(q.root, root_phase+q.half_angle(q.root), root_phase+pitch/2)[:-1]
    if len(points)>10000:
        raise ValueError('Spherical bevel contour exceeds its vertex budget.')
    return points
