# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Prescribed inextensible pitch-line mapping; no elastic solution.

Uniform material angle is ellipse arc length / reference pitch radius. Tooth
height is along the local ellipse normal, preserving flank orientation.
Eight Fourier modes integrate the ellipse speed; CPU and GLSL share them.
"""
from math import pi, sin, cos, atan2, hypot, isfinite
from functools import lru_cache
from rust_geometry import call
TAU=2*pi
MATERIAL_RECONSTRUCTION_EPSILON=1e-7  # mm, protocol consistency, not manufacturing accuracy


def _finite(values):
    try:return all(isfinite(v) for v in values)
    except (TypeError,ValueError):return False

@lru_cache(maxsize=32)
def arc_coefficients(a,b,rp):
    return tuple(call('wave_coefficients', dict(a=a,b=b,rp=rp)))


def eccentric_angle(material,a,b,rp):
    return call('wave_eccentric', dict(material=material,a=a,b=b,rp=rp))


def map_point(material,offset,weight,a,b,rp,flex_angle=0,wave_angle=0):
    return tuple(call('wave_map', locals()))


def unmap_point(x,y,weight,a,b,rp):
    return tuple(call('wave_unmap', locals()))


def material_vertices(part,check=lambda:None):
    """Immutable shared-vertex references for the explicitly prescribed map."""
    from solid_geometry import kernel_part
    rows=call('wave_material_vertices',dict(part=kernel_part(part),metadata=part.profile_metadata.get('wave_mapping',{})),check=check)
    return {tuple(vertex):tuple(material) for vertex,material in rows}


def posed_vertices(part,references,deformation,check=lambda:None):
    """Map original vertex references at a pose, never a previously posed mesh."""
    metadata=part.profile_metadata.get('wave_mapping',{})
    if not isinstance(metadata,dict) or not isinstance(metadata.get('ellipse_axes_mm'),(tuple,list)):
        raise ValueError('Unknown strain-wave deformation metadata')
    if not isinstance(deformation,(tuple,list)) or len(deformation)!=7 or not _finite(deformation):
        raise ValueError('Unknown or nonfinite strain-wave deformation')
    flex,wave,a,b,rp,length,diaphragm=deformation
    expected=(*metadata.get('ellipse_axes_mm',()),metadata.get('pitch_radius_mm'),metadata.get('body_length_mm'),metadata.get('diaphragm_mm'))
    if (a,b,rp,length,diaphragm)!=expected:
        raise ValueError('Strain-wave deformation does not match its validated material map')
    rows=list(references.items())
    mapped=call('wave_map_batch',dict(points=[material for vertex,material in rows],
        a=a,b=b,rp=rp,flex_angle=flex,wave_angle=wave),check=check)
    return {vertex:(xy[0]+part.center[0],xy[1]+part.center[1],vertex[2])
            for (vertex,material),xy in zip(rows,mapped)}
