# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Paired planetary construction and bounded continuous polygon clearance.

All lengths are mm and phases radians. The proof concerns the actual transverse
polylines at unloaded neutral backlash, not unsampled curves or exported solids.
"""
from copy import deepcopy
from functools import lru_cache
from math import pi, sin, cos, tan, atan, radians, degrees, sqrt, hypot, inf, isfinite

CONSTRUCTION_VERSION = 'planetary_paired_involute_v1'
PLAN_INTERVAL_BUDGET = 1024
SCOPE = ('continuous separation of generated transverse polygons over one tooth '
         'period at neutral backlash; excludes analytic curve sampling error, '
         'loaded contact, CAD/STL axial interpolation, cutter and manufacturing checks')


def polygon_pose_clearance(planet,ring,tree=None):
    from rust_geometry import call
    return tuple(call('internal_pose_clearance',dict(planet=planet,ring=ring)))


def verify_internal_polygon_pair(planet_loop, ring_void, phaseP, phaseR, zp, zr,
                                 center_distance_mm=0., budget=4096, max_depth=20,
                                 numeric_guard_mm=1e-7, backlash_mm=None):
    from rust_geometry import call
    return call('internal_verify',dict(planet_loop=planet_loop,ring_void=ring_void,
        phaseP=phaseP,phaseR=phaseR,zp=zp,zr=zr,center_distance_mm=center_distance_mm,
        budget=budget,max_depth=max_depth,numeric_guard_mm=numeric_guard_mm,backlash_mm=backlash_mm))


def validate_axial_pair(planet,ring,zp,zr):
    from solid_geometry import kernel_part
    from rust_geometry import cached_call
    # Derive the exact same changed sections beside the verifier in Rust,
    # without exporting them through Python and importing them again.
    double=planet.double or ring.double
    fields=('width','double','gap','twist','stations')
    first=kernel_part(planet) if double else {k:getattr(planet,k) for k in fields}
    second=kernel_part(ring) if double else {k:getattr(ring,k) for k in fields}
    return cached_call('internal_axial_derived',dict(planet=first,ring=second,
        zp=zp,zr=zr))


def plan_planetary_internal_pair(zp,zr,mn,alpha_n=20,beta=0,backlash=.15,
                                profile_chord_threshold_mm=.015):
    """Return a detached cached plan; RPM, width and stage do not enter its key."""
    return deepcopy(_plan(zp,zr,mn,alpha_n,beta,backlash,profile_chord_threshold_mm))


def plan_fixed_internal_pair(zp,zr,mn,alpha_n=20,beta=0,backlash=.15):
    """Detached, cached source geometry; independent of display/export quality."""
    return deepcopy(_fixed_plan(zp,zr,mn,alpha_n,beta,backlash))


@lru_cache(maxsize=32)
def _fixed_plan(zp,zr,mn,alpha_n,beta,backlash):
    from rust_geometry import call
    return call('internal_fixed_plan',dict(zp=zp,zr=zr,mn=mn,alpha_n=alpha_n,beta=beta,backlash=backlash))


@lru_cache(maxsize=16)
def _plan(zp,zr,mn,alpha_n,beta,backlash,tolerance):
    from rust_geometry import call
    return call('internal_plan',dict(zp=zp,zr=zr,mn=mn,alpha_n=alpha_n,beta=beta,
        backlash=backlash,tolerance=tolerance,budget=PLAN_INTERVAL_BUDGET))
