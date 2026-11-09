# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Spherical-involute pairs with straight, logarithmic or circular tooth traces.

Custom planar blanks, not a standard manufacturing tooth system. See
docs/technical/bevel-pair.md for reference equations, frames and limits.
"""
from dataclasses import dataclass, asdict
from rust_geometry import call, call_geometry
from bevel_geometry import SphericalProfile, PROFILE_TOLERANCE

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
    """Circular developed lead with custom spherical flanks, evaluated in Rust."""
    mean_distance: float
    trace_radius: float
    trace_hand: int
    _kernel_trace = 'circular'

    def _call(self, action, **parameters):
        return call('bevel_pair_generator',dict(action=action,profile=asdict(self),**parameters))
    def developed_angle(self, distance):return self._call('developed_angle',distance=distance)
    def trace(self, distance):return self._call('trace',distance=distance)
    def section_trace(self, z, theta):return self._call('section_trace',z=z,theta=theta)
    def derivative_bounds(self, low, high):return tuple(self._call('derivative_bounds',low=low,high=high))


def _profile(p):
    return (CircularProfile if 'mean_distance' in p else SphericalProfile)(**p)


def circular_engagement(a,b,width):
    return call('bevel_pair_generator',dict(action='engagement',a=asdict(a),b=asdict(b),width=width))


def stations(profiles,width):
    rows,bound=call('bevel_pair_generator',dict(action='stations',profiles=[asdict(q) for q in profiles],width=width))
    return rows,bound


def curved_section(profile,heel_points,distance):
    return [tuple(p) for p in call('bevel_pair_generator',dict(action='curved_section',profile=asdict(profile),points=heel_points,distance=distance))]


def dimensions(v):
    a,b,contact=call('bevel_pair_generator',dict(action='dimensions',values=v))
    return _profile(a),_profile(b),contact


def build(d):
    from geometry import part_from_kernel
    v=d.values
    result=call_geometry('construction_bevel_pair',dict(values=v))
    d.parts.extend(part_from_kernel(p['name'],p) for p in result['parts'])
    d.analysis.update(result['analysis'])
    q=result['analysis']['bevel_pair'];contact=q['engagement'];distance=q['pitch_cone_distance_mm']
    variant=v.get('variant','straight')
    d.metrics.extend([f'Shaft angle: 90° · {variant} bevel teeth',
                      f"Pitch cone angles: {q['pinion_pitch_angle_deg']:.6f}° / {q['wheel_pitch_angle_deg']:.6f}°",
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
