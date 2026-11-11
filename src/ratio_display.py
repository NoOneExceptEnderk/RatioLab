# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Presentation of the signed rotary speed ratio, i = n_input / n_output."""
from math import isfinite


def ratio_parts(ratio, digits=4, *, signed=True):
    """Return a signed numerator and colon-prefixed denominator for display."""
    magnitude = abs(float(ratio))
    sign = ('-' if ratio < 0 else '+') if signed else ''
    if 0 < magnitude < 1:
        denominator = 1 / magnitude
        if isfinite(denominator):
            text = format(denominator, f'.{digits}g')
            return sign + '1', ':' + (format(denominator, '.17g') if text == '1' else text)
    text = format(magnitude, f'.{digits}g')
    if magnitude > 1 and text == '1':
        text = format(magnitude, '.17g')
    return sign + text, ':1'
