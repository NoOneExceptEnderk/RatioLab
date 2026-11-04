# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Spherical-involute pairs with straight, logarithmic or circular tooth traces.

Custom planar blanks, not a standard manufacturing tooth system. See
docs/technical/bevel-pair.md for reference equations, frames and limits.
"""
from dataclasses import dataclass, asdict
from math import cos, sin, tan, acos, atan2, hypot, pi, degrees, radians, sqrt, ceil
from bevel_geometry import parameters, section, engagement, SphericalProfile, PROFILE_TOLERANCE

VARIANTS = {'straight': 'Straight teeth · 90° shafts',
            'spiral': 'Spiral teeth · 90° shafts',
            'zerol': 'Zerol-style · circular trace'}
TRACE_TOLERANCE = .003

SPECS = [
    ('module', 'Outer bevel module [mm]', 2, .5, 6, .1),
    ('pinion', 'Pinion teeth', 20, 16, 120, 1),
    ('wheel', 'Wheel teeth', 40, 16, 160, 1),
    ('width', 'Face width along pitch cone [mm]', 8, 2, 25, .5),
    ('pressure', 'Transverse pressure angle [°]', 20, 14.5, 30, .5),
    ('backlash', 'Outer tangential backlash [mm]', .15, 0, 1, .01),
    ('bore', 'Pinion bore [mm]', 6, 0, 100, .5),
    ('output_bore', 'Wheel bore [mm]', 8, 0, 100, .5),
]
FRAME_PINION = ((0, 0, 0), (0, 1, 0), (0, 0, 1), (1, 0, 0))
FRAME_WHEEL = ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1))
CATALOG_REASON = ('Bevel pairs generate two bored gear blanks. Design shafts, '
                  'supports, bearing seats and axial retention in CAD; automatic '
                  'bearing seats and standard hardware are unavailable.')


def trace_specs(variant):
    fields = []
    if variant == 'spiral':
        fields.append(('spiral_angle', 'Unsigned spiral angle [°]', 35, 0, 45, 1))
    elif variant == 'zerol':
        fields.append(('trace_radius', 'Developed trace curvature radius [mm]', 50, 1, 1000, 1))
    if variant in ('spiral', 'zerol'):
        fields.append(('spiral_hand', 'Pinion local trace hand (−1 / +1)', 1, -1, 1, 2))
    return fields


@dataclass(frozen=True)
class CircularProfile(SphericalProfile):
    """Custom spherical flanks with a circular lead on the developed pitch cone.

    The lead is tangent to a radial generator at the mean face distance.
    This is not the industrial Gleason octoidal tooth profile.
    """
    mean_distance: float
    trace_radius: float
    trace_hand: int

    def developed_angle(self, distance):
        if distance <= 0:
            raise ValueError('Circular tooth trace requires a positive cone distance.')
        d = (distance + self.mean_distance**2 / distance) / 2
        a = hypot(self.mean_distance, self.trace_radius)
        if d >= a * (1 - 1e-12):
            raise ValueError('Circular tooth trace leaves its supported arc; increase trace curvature radius.')
        return atan2(self.trace_radius, self.mean_distance) - acos(d / a)

    def trace(self, distance):
        return self.trace_hand * (self.developed_angle(distance) - self.developed_angle(self.outer_distance)) / sin(self.delta)

    def section_trace(self, z, theta):
        return self.trace(z / cos(theta))

    def derivative_bounds(self, low, high):
        """Absolute first/second trace derivatives on an actual-R interval."""
        self.developed_angle(low); self.developed_angle(high)
        mean = self.mean_distance
        dmax = max((low + mean**2 / low) / 2, (high + mean**2 / high) / 2)
        hmin = sqrt(mean**2 + self.trace_radius**2 - dmax**2)
        dp = max(abs(1 - (mean / low)**2), abs(1 - (mean / high)**2)) / 2
        first = dp / hmin / sin(self.delta)
        second = (mean**2 / low**3 / hmin + dmax * dp**2 / hmin**3) / sin(self.delta)
        return first, second


def circular_engagement(a, b, width):
    """Conservative phase-span lower bounds from points in a connected domain.

    Continuous phase on this connected domain covers the interval between any
    two samples. Missed extrema can only increase the true span. This sufficient
    acceptance test can reject a marginal valid pair; it is not an extrema solver.
    """
    base = engagement(a, b, width)  # k=0; reuse only the unchanged cap/action domain.
    lo, hi = base['action_angle_interval_rad']
    outer = a.outer_distance; inner = outer - width
    sa = sqrt(max(0, 1 - (sin(a.base) / sin(a.delta))**2))
    phases = [[], []]
    samples = [lo + (hi - lo) * j / 256 for j in range(257)] + ([0] if lo < 0 < hi else [])
    for s in samples:
        x = cos(a.delta)*cos(s) - sa*sin(a.delta)*sin(s)
        z = sin(a.delta)*cos(s) + sa*cos(a.delta)*sin(s)
        low = max(inner*cos(a.delta)/x, inner*cos(b.delta)/z)
        high = min(outer*cos(a.delta)/x, outer*cos(b.delta)/z)
        if low > high:continue
        for distance in (low, high, max(low, min(high, a.mean_distance))):
            for sign, values in zip((-1, 1), phases):
                values.append(s/sin(a.base) - sign*a.trace(distance))
    spans = [(max(values) - min(values))/(2*pi/a.teeth) for values in phases]
    return dict(contact_phase_span_teeth=min(spans), flank_contact_phase_spans_teeth=spans,
                action_angle_interval_rad=[lo, hi], is_lower_bound=True,
                method='Conservative sampled lower bound of continuous phase on the connected cap/action domain',
                scope='Sufficient ideal engagement only; missed extrema may cause conservative rejection; no load or strength solution')


def stations(profiles, width):
    """Common pitch distances with a 0.003mm sampled-vertex trace chord bound."""
    outer = profiles[0].outer_distance; inner = outer - width
    bound = 0
    for q in profiles:
        amplitude = cos(q.delta)*tan(q.tip)
        if isinstance(q, CircularProfile):
            cmin = cos(q.delta)/cos(q.root); cmax = cos(q.delta)/cos(q.tip)
            first, second = q.derivative_bounds(cmin*inner, cmax*outer)
            bound = max(bound, amplitude*(2*cmax*first + outer*cmax**2*(second + first**2)))
        else:
            bound = max(bound, amplitude*abs(q.k)*sqrt(1 + q.k*q.k)/inner)
    intervals = max(1, ceil(width*sqrt(bound/(8*TRACE_TOLERANCE))))
    if intervals > 128:
        raise ValueError('Curved bevel trace exceeds its section budget; reduce width/spiral angle or increase trace radius.')
    return [inner] + [inner + width*j/intervals for j in range(1, intervals)] + [outer], bound


def curved_section(profile, heel_points, distance):
    """Keep loop correspondence; circular traces require vertex-specific twist."""
    outer = profile.outer_distance; heel = outer*cos(profile.delta)
    result = []
    for x, y in heel_points:
        actual_heel_distance = hypot(hypot(x, y), heel)
        turn = profile.trace(actual_heel_distance*distance/outer) - profile.trace(actual_heel_distance)
        c, s = cos(turn), sin(turn)
        result.append(((x*c - y*s)*distance/outer, (x*s + y*c)*distance/outer))
    return result


def dimensions(v):
    distance = hypot(v['pinion'], v['wheel']) * v['module'] / 2
    if v['width'] > min(distance / 3, 10 * v['module']):
        raise ValueError('Bevel face width must not exceed one third of the pitch cone distance or ten outer modules.')
    if v['backlash'] >= .7 * v['module']:
        raise ValueError('Backlash too large for the bevel module.')
    variant = v.get('variant', 'straight')
    beta = v['spiral_angle'] if variant == 'spiral' else 0
    hand = v.get('spiral_hand', 1)
    a = parameters(v['pinion'], v['wheel'], v['module'], v['pressure'], v['backlash'], beta, hand)
    b = parameters(v['wheel'], v['pinion'], v['module'], v['pressure'], v['backlash'], beta, -hand)
    if variant == 'zerol':
        a = CircularProfile(**asdict(a), mean_distance=distance-v['width']/2, trace_radius=v['trace_radius'], trace_hand=hand)
        b = CircularProfile(**asdict(b), mean_distance=distance-v['width']/2, trace_radius=v['trace_radius'], trace_hand=-hand)
        for q in (a, b):q.derivative_bounds((distance-v['width'])*cos(q.delta)/cos(q.root), distance*cos(q.delta)/cos(q.tip))
        contact = circular_engagement(a, b, v['width'])
    else:
        contact = engagement(a, b, v['width'])
    stations((a, b), v['width'])  # Refuse an unsupported axial sampling budget in validation too.
    if contact['contact_phase_span_teeth'] <= 1 + 1e-8:
        raise ValueError('Bevel face width/addendum leaves a gap in ideal tooth engagement; increase face width or adjust tooth counts / pressure angle.')
    for profile, bore in ((a, v['bore']), (b, v['output_bore'])):
        root = (distance - v['width']) * cos(profile.delta) * tan(profile.root)
        if bore and bore / 2 + .8 >= root:
            raise ValueError('Bore too large for the small-end bevel root; reduce bore diameter or face width.')
    return a, b, contact


def build(d):
    from geometry import Part, circle
    v = d.values
    a, b, contact = dimensions(v)
    distance = a.outer_distance
    scale = 1 - v['width'] / distance
    variant = v.get('variant', 'straight')
    hand = v.get('spiral_hand', 1)
    distances, chord_bound = stations((a, b), v['width'])
    # Wheel tooth at +X, pinion space at the common pitch generator.
    for profile, name, bore, frame, phase, member in (
        (a, 'Bevel_pinion', v['bore'], FRAME_PINION, pi / 2 - pi / v['pinion'], 'A'),
        (b, 'Bevel_wheel', v['output_bore'], FRAME_WHEEL, 0, 'B'),
    ):
        heel = distance * cos(profile.delta)
        toe = heel * scale
        outer = section(profile, heel, phase)
        holes = [circle(bore / 2)] if bore else []
        p = Part(name, outer, holes, heel - toe, toe, frame=frame)
        p.stations = [dict(z=0, outer=[(x * scale, y * scale) for x, y in outer], holes=holes),
                      dict(z=heel - toe, outer=outer, holes=holes)]
        if variant != 'straight' and (profile.k or isinstance(profile, CircularProfile)):
            if 2*(len(outer)+sum(map(len, holes)))*(len(distances)-1)+2 > 250000:
                raise ValueError('Curved bevel surface exceeds the shared face budget; reduce tooth counts, width or curvature.')
            p.stations = [dict(z=0 if j == 0 else heel-toe if j == len(distances)-1 else r*cos(profile.delta)-toe,
                               outer=curved_section(profile, outer, r) if r != distance else outer, holes=holes)
                          for j, r in enumerate(distances)]
        p.port = dict(member=member, axis='World +X' if member == 'A' else 'World +Z')
        p.color = (.96, .66, .33) if member == 'A' else (.23, .75, .65)
        p.profile_metadata['bevel_profile'] = dict(
            method='Exact spherical involute working flanks; custom planar blank',
            pitch_cone_angle_deg=degrees(profile.delta), base_cone_angle_deg=degrees(profile.base),
            root_cone_angle_deg=degrees(profile.root), tip_cone_angle_deg=degrees(profile.tip),
            cone_distance_mm=distance, face_width_mm=v['width'], teeth=profile.teeth,
            profile_refinement_threshold_mm=PROFILE_TOLERANCE,
            section_end_convention='Planar Z caps at pitch-cone heel/toe; actual vertex R=Z/cos(theta)',
            root_method='Nonworking constant-half-angle relief below base; deepened for mate addendum',
            engagement=contact, flank_reference_doi='10.3389/fmech.2025.1643228',
            flank_reference_equation='Section 2 equation 1')
        if variant != 'straight':
            p.profile_metadata['bevel_profile'].update(tooth_type=variant, local_trace_hand=hand if member=='A' else -hand,
                trace_chord_tolerance_mm=TRACE_TOLERANCE, trace_second_derivative_bound=chord_bound,
                cone_stations_mm=distances, spiral_angle_deg=v.get('spiral_angle', 0),
                trace_radius_mm=v.get('trace_radius'), mean_spiral_angle_deg=0 if variant=='zerol' else v['spiral_angle'])
        d.parts.append(p)
    d.analysis.update(signed_ratio=-v['wheel'] / v['pinion'], bevel_pair=dict(
        shaft_angle_deg=90, pitch_cone_distance_mm=distance,
        pinion_pitch_angle_deg=degrees(a.delta), wheel_pitch_angle_deg=degrees(b.delta),
        outer_pitch_diameters_mm=[v['module'] * v[k] for k in ('pinion', 'wheel')],
        engagement=contact, construction='Straight spherical involute; custom planar blanks',
        axes=dict(A=[1, 0, 0], B=[0, 0, 1]),
        rolling_equation='pinion_teeth * pinion_rpm + wheel_teeth * wheel_rpm = 0'))
    if variant != 'straight':
        d.analysis['bevel_pair'].update(tooth_type=variant, spiral_angle_deg=v.get('spiral_angle', 0),
            pinion_local_trace_hand=hand, trace_radius_mm=v.get('trace_radius'), cone_stations_mm=distances,
            construction='Spherical involute; logarithmic spiral trace' if variant=='spiral' else 'Custom spherical involute; circular developed Zerol-style trace')
    d.metrics.extend([f'Shaft angle: 90° · {variant} bevel teeth',
                      f'Pitch cone angles: {degrees(a.delta):.6f}° / {degrees(b.delta):.6f}°',
                      f'Outer cone distance: {distance:.6f} mm',
                      f"Ideal engagement phase span: {contact['contact_phase_span_teeth']:.6f} tooth pitches"])
    d.notes.extend([
        'Positive pinion speed uses world +X; positive wheel speed uses world +Z. '
        'The signed ratio refers to these separate right-hand shaft directions.',
        ('Straight' if variant=='straight' else 'Curved') + ' spherical involute working flanks with custom planar heel/toe caps. '
        'Not a KHK standard full-depth blank or a Gleason/Klingelnberg cutter design. '
        'Below-base root relief is nonworking and is not a generated cutter fillet.',
        'Shared preview and export surfaces sample the analytic flanks; profile refinement '
        'threshold 0.003 mm is not a manufacturing accuracy or strength rating. '
        'Loaded contact, root strength and continuous collision clearance are unverified.',
    ])
    if variant == 'zerol':
        d.notes.append('Zerol-style: circular tooth trace on the developed pitch cone, tangent to the generator at mean face distance. '
                       'Custom spherical involute flanks, not the industrial Gleason octoidal profile, cutter settings or crowning. '
                       'Reported engagement is a conservative lower bound; marginal valid geometries can be refused.')
    d.requirements.append(CATALOG_REASON)
