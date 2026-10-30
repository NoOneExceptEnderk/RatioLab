# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Static tooth-contact screening, separate from ideal speed relations.

KHK Calculation of Gear Dimensions, 4.6(4), equation (4.27).
Angles are radians internally, dimensions millimetres, friction dimensionless.
See docs/technical/calculations.md for assumptions and primary references.
"""
from math import atan, cos, degrees, isfinite, radians, tan

FRICTION_KEY = 'worm_static_friction'
KHK_SOURCE = 'https://khkgears.net/new/gear_knowledge/gear_technical_reference/calculation_gear_dimensions.html'
LIMITS = ('Bearings, seals, preload, deformation, '
          'lubrication changes, vibration and operating loads are not evaluated. '
          'This is not a safety brake or a load-holding certification.')
WORM_LIMITS = ('Static reference-cylinder tooth-contact startup model for a passive, unassisted worm shaft. '
               + LIMITS)


class BackdrivabilityError(ValueError):
    """A requested driving member violates an explicit physical constraint."""


def physical_inputs(family, supplied):
    """Retain explicit physical data; never silently discard an invalid field."""
    if FRICTION_KEY not in supplied:
        return {}
    if family != 'worm':
        raise ValueError('Static worm tooth friction applies only to worm drives.')
    mu = supplied[FRICTION_KEY]
    try:
        valid = type(mu) in (int, float) and mu >= 0 and isfinite(mu)
    except (OverflowError, TypeError):
        valid = False
    if not valid:
        raise ValueError('Static worm tooth friction must be an explicit finite number greater than or equal to zero.')
    return {FRICTION_KEY: float(mu)}


def evaluate(family, values):
    """Evaluate normalized values without inferring friction or commercial data."""
    physical = physical_inputs(family, values)
    scheme = values.get('io_scheme', 'forward' if family == 'worm' else 'wave_flex_circular')
    result = dict(status='not_evaluated', reverse_requested=False, allowed=True,
                  message='No backdrivability model is evaluated for this arrangement.', limits=LIMITS)
    if family == 'worm':
        reverse = scheme == 'reverse'
        gamma = atan(values['module'] * values['starts'] / values['diameter'])
        alpha_n = atan(tan(radians(values['pressure'])) * cos(gamma))
        critical = cos(alpha_n) * tan(gamma)
        result.update(reverse_requested=reverse, model='static_worm_tooth_contact', limits=WORM_LIMITS,
                      source=KHK_SOURCE, equation='KHK 4.6(4), Eq. (4.27)',
                      lead_angle_deg=degrees(gamma), normal_pressure_angle_deg=degrees(alpha_n),
                      critical_static_friction=critical)
        if not physical:
            result.update(status='indeterminate', static_friction=None,
                          message='Backdrivability indeterminate: static tooth friction is missing. '
                          'Wheel-driven motion is ideal kinematics only; provide a measured or justified '
                          'coefficient for the actual contact and conditions. No physical backdrivability is established.')
        else:
            mu = physical[FRICTION_KEY]
            blocked = mu >= critical
            result.update(status='not_backdrivable' if blocked else 'potentially_backdrivable',
                          static_friction=mu, allowed=not (reverse and blocked))
            result['message'] = (
                f'The wheel cannot start driving the worm in the static tooth-contact model: friction {mu:.6g} '
                f'is at or above the limiting value {critical:.6g} '
                f'(lead angle {degrees(gamma):.6g}°, normal pressure angle {degrees(alpha_n):.6g}°). '
                'Use worm input or revise the physical data/geometry.' if blocked else
                f'Potentially backdrivable: static tooth friction {mu:.6g} is below {critical:.6g}. '
                'The mesh criterion permits wheel driving; real startup and sustained motion are not guaranteed.')
    elif family == 'harmonic' and scheme.split('_')[0] != 'wave':
        result.update(status='indeterminate', reverse_requested=True,
                      model='no_hardware_breakaway_data',
                      message='Backdrivability indeterminate: output-driven strain-wave motion is ideal kinematics only. '
                      'Measured breakaway torque and operating conditions for this hardware are missing; '
                      'commercial catalog values cannot be transferred to generated geometry.')
    return result


def enforce(family, values):
    result = evaluate(family, values)
    if not result['allowed']:
        raise BackdrivabilityError(result['message'])
    return result
