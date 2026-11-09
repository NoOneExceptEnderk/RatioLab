# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Spherical involute adapters with preserved custom Python trace subclasses.

Dong et al., DOI 10.3389/fmech.2025.1643228, section 2 equation 1;
Wang et al., DOI 10.2174/1874155X01105010051, equation 22.
"""
from dataclasses import dataclass, asdict
from rust_geometry import call
from math import cos, sin, tan, log, pi, hypot

PROFILE_TOLERANCE = .003


def spherical_involute(theta, base):
    return call('spherical_involute', dict(theta=theta,base=base))


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

    def trace(self, distance):
        """Local shaft azimuth of the pitch trace at actual apex distance."""
        return self.k * log(distance / self.outer_distance)

    def section_trace(self, z, theta):
        # Preserve the existing logarithmic arc evaluation and its rounding.
        return self.k * log(z / (cos(theta) * self.outer_distance))

    def half_angle(self, theta):
        return call('bevel_half', dict(profile=asdict(self),theta=theta))

    def point(self, theta, distance, side=1, phase=0):
        if type(self) is not SphericalProfile and getattr(self,'_kernel_trace',None)!='circular':
            azimuth = phase + self.trace(distance) + side * self.half_angle(theta)
            r = distance * sin(theta)
            return r * cos(azimuth), r * sin(azimuth), distance * cos(theta)
        return tuple(call('bevel_point', dict(profile=asdict(self),theta=theta,
            distance=distance,side=side,phase=phase)))

    def section_point(self, theta, z, side=1, phase=0):
        if type(self) is not SphericalProfile and getattr(self,'_kernel_trace',None)!='circular':
            p = self.point(theta, z / cos(theta), side, phase)
            return p[0], p[1]
        return tuple(call('bevel_section_point', dict(profile=asdict(self),theta=theta,
            z=z,side=side,phase=phase)))


def parameters(teeth, mate_teeth, module, pressure, backlash=0, beta=0, hand=1):
    return SphericalProfile(**call('bevel_parameters', locals()))


def engagement(a, b, width):
    return call('bevel_engagement', dict(a=asdict(a),b=asdict(b),width=width))


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
    if type(q) is SphericalProfile or getattr(q,'_kernel_trace',None)=='circular':
        return [tuple(p) for p in call('bevel_section', dict(profile=asdict(q),
            z=z,phase=phase,tolerance=tolerance))]
    """One counterclockwise planar heel contour, repeated tooth by tooth."""
    pitch = 2*pi/q.teeth
    # Below-base relief and the working involute meet at a real cusp: do not
    # interpolate across it with one adaptive interval.
    levels = [q.root] + ([q.base] if q.root < q.base < q.tip else []) + [q.tip]
    points = []
    for tooth in range(q.teeth):
        centre = phase+tooth*pitch
        root_phase = centre+q.section_trace(z, q.root)
        tip_phase = centre+q.section_trace(z, q.tip)
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
