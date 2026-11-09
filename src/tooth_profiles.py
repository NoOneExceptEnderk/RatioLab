# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Cylindrical profile adapters. Construction and curve evaluation run in Rust."""
from rust_geometry import call

TOLERANCE = 0.015


def tooth_thickness(z, mt, mn, rp, rb, tip, half, nominal_half,
                    involute_start, involute_end, internal=False):
    return call('tooth_thickness', locals())


def rack_parameters(z, mt, pressure, backlash=0.15, depth=None, shift=0,
                    normal_pressure=None, hf=1.25):
    return call('rack_parameters', locals())


def rack_point(tool, t):
    return tuple(call('rack_point', dict(tool=tool, t=t)))


def _half(operation, parameters, sampler):
    # Keep the callable API for independent inspection/custom samplers. Its
    # functions evaluate Rust curve descriptors; no duplicate Python geometry.
    # The application's adaptive sampler uses the Rust batched implementation.
    adaptive = getattr(sampler, '_ratiolab_rust_adaptive', False)
    result = call(operation, dict(parameters, endpoints=not adaptive))
    info = result['metadata']
    curves = info.pop('sampling_curves')
    if adaptive:
        return [tuple(p) for p in result['points']], info
    points = []
    for curve in curves:
        def evaluate(t, curve=curve):
            return tuple(call('curve_point', dict(curve=curve, t=t)))
        segment = sampler(evaluate, curve['start'], curve['end'])
        points.extend(segment[:-1])
    points.append(segment[-1])
    return points, info


def external_half(z, mt, pressure, backlash, depth, shift, normal_pressure, ha, hf, sample):
    parameters = dict(z=z, mt=mt, pressure=pressure, backlash=backlash, depth=depth,
                      shift=shift, normal_pressure=normal_pressure, ha=ha, hf=hf)
    return _half('external_half', parameters, sample)


def internal_half(z, mt, pressure, backlash, depth, ha, hf, sample, minimum_join_radius_mm=None):
    parameters = dict(z=z, mt=mt, pressure=pressure, backlash=backlash, depth=depth,
                      ha=ha, hf=hf, minimum_join_radius_mm=minimum_join_radius_mm)
    return _half('internal_half', parameters, sample)
