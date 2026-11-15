# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Physical limits of output-driven strain-wave motion."""
LIMITS = ('Bearings, seals, preload, deformation, '
          'lubrication changes, vibration and operating loads are not evaluated. '
          'This is not a safety brake or a load-holding certification.')



def evaluate(family, values):
    scheme = values.get('io_scheme', 'wave_flex_circular')
    result = dict(status='not_evaluated', reverse_requested=False, allowed=True,
                  message='No backdrivability model is evaluated for this arrangement.', limits=LIMITS)
    if family == 'harmonic' and scheme.split('_')[0] != 'wave':
        result.update(status='indeterminate', reverse_requested=True,
                      model='no_hardware_breakaway_data',
                      message='Backdrivability indeterminate: output-driven strain-wave motion is ideal kinematics only. '
                      'Measured breakaway torque and operating conditions for this hardware are missing; '
                      'commercial catalog values cannot be transferred to generated geometry.')
    return result
