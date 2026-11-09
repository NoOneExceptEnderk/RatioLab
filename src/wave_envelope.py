# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Rust swept envelope for the prescribed strain-wave map; no elasticity."""
from functools import lru_cache
from rust_geometry import call

ANGULAR_CELLS=128
CONVERGENCE=.002

@lru_cache(maxsize=32)
def _circular(reference,z,a,b,rp):
    return call('wave_circular_spline', dict(reference=reference,z=z,a=a,b=b,rp=rp))


def circular_spline(reference,z,a,b,rp):
    result=_circular(tuple(tuple(p) for p in reference),z,a,b,rp)
    return [tuple(p) for p in result['points']],dict(result['metadata'])
