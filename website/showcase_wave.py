# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Authoring-only Float64 reference for the canonical preview's waveFrame shader.

Validation/fixture helper, never uploaded. This reproduces the prescribed map
and the preview tangent-frame normal transport; it is not an elastic model.
"""
from math import cos, sin, hypot


def wave_frame(material, descriptor, flex=0, wave=0):
    u, offset, weight = material
    a, b = descriptor['ellipseAxes']
    rp = descriptor['pitchRadius']
    angle = u+flex-wave
    t = angle
    for _ in range(8):
        residual, derivative = t-angle, 1.0
        for k, coefficient in enumerate(descriptor['arcCoefficients'], 1):
            residual += coefficient*sin(2*k*t)
            derivative += 2*k*coefficient*cos(2*k*t)
        t -= residual/derivative
    ct, st, cu, su = cos(t), sin(t), cos(u+flex), sin(u+flex)
    nx, ny = ct/a, st/b
    nlength = hypot(nx, ny)
    ex, ey = a*ct+offset*nx/nlength, b*st+offset*ny/nlength
    tx, ty = -a*st, b*ct
    speed = hypot(tx, ty)
    curvature = a*b/speed**3
    scale = rp*(1+offset*curvature)/speed
    tx, ty = tx*scale, ty*scale
    c, s = cos(wave), sin(wave)
    ex, ey = c*ex-s*ey, s*ex+c*ey
    tx, ty = c*tx-s*ty, s*tx+c*ty
    x = (1-weight)*(rp+offset)*cu+weight*ex
    y = (1-weight)*(rp+offset)*su+weight*ey
    tx = (1-weight)*(-(rp+offset)*su)+weight*tx
    ty = (1-weight)*((rp+offset)*cu)+weight*ty
    tlength = hypot(tx, ty)
    return (x, y), (tx/tlength, ty/tlength)


def deform_vertex(point, normal, material, descriptor, phase):
    flex = descriptor['flexOffset']+descriptor['flexRate']*phase
    wave = descriptor['waveOffset']+descriptor['waveRate']*phase
    xy, tangent = wave_frame(material, descriptor, flex, wave)
    _, old = wave_frame(material, descriptor)
    old_normal, new_normal = (old[1], -old[0]), (tangent[1], -tangent[0])
    along = normal[0]*old[0]+normal[1]*old[1]
    across = normal[0]*old_normal[0]+normal[1]*old_normal[1]
    moved_normal = (along*tangent[0]+across*new_normal[0], along*tangent[1]+across*new_normal[1], normal[2])
    center = descriptor['center']
    return (xy[0]+center[0], xy[1]+center[1], point[2]), moved_normal
