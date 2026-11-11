# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""View-only tooth focus, using the kernel's original construction and placement."""
from dataclasses import dataclass, replace
from array import array
from math import atan2, cos, sin, radians, pi, hypot

from geometry import Part, profile_sections
from rust_geometry import call, control_check
from solid_geometry import point
from tooth_tips import KEYS, key, members


def member_for_field(family, variant, field):
    return next((role for role, _ in members(family, variant)
                 if field in {key(role, name) for name in KEYS}), None)


def component_index(design, field):
    role = member_for_field(design.family, design.values.get('variant'), field)
    if role is None:
        raise ValueError('This control does not edit tooth tips.')
    if design.family in ('spur', 'helical', 'double'):
        name = 'Gear'
    elif design.family == 'parallel':
        stage = role[-1] if role[-1:].isdigit() else '1'
        name = f'S{stage}_{role.rstrip("123").title()}'
    elif design.family == 'planetary':
        stage = role[-1] if role[-1:].isdigit() else '1'
        member = role.rstrip('12').title()
        name = f'S{stage}_{member}' + ('_1' if member == 'Planet' else '')
    elif design.family == 'internal':
        name = {'pinion': 'Pinion_input', 'ring': 'Ring_output'}[role]
    elif design.family == 'wolfrom':
        name = {'sun': 'Sun_input', 'planet': 'Compound_1_rim1',
                'planet2': 'Compound_1_rim2', 'ring': 'Ring_fixed',
                'output_ring': 'Ring_output'}[role]
    else:
        name = {'pinion': 'Rack_pinion', 'rack': 'Rack'}[role]
    return next(i for i, part in enumerate(design.parts) if part.name == name)


@dataclass
class Detail:
    scene: object
    source_index: int
    target: tuple
    direction: tuple
    radius: float
    part_name: str
    removed_sections: int
    band_mm: tuple
    up: tuple = (0.,1.,0.)
    occluded_indices: tuple = ()
    has_tip_controls: bool = True


def supported(part):
    metadata=part.profile_metadata
    if metadata.get('face_profile') or metadata.get('hypoid_profile'):
        return False
    return bool(metadata.get('tip_preview_source') or metadata.get('bevel_profile'))


def _plane(part, local_up, rotation=0.):
    """Use the actual placement boundary, including framed and X-axis parts."""
    origin=point(part,(0.,0.),0.,0.)
    x=tuple(a-b for a,b in zip(point(part,(1.,0.),0.,0.),origin))
    y=tuple(a-b for a,b in zip(point(part,(0.,1.),0.,0.),origin))
    normal=(x[1]*y[2]-x[2]*y[1],x[2]*y[0]-x[0]*y[2],x[0]*y[1]-x[1]*y[0])
    up=tuple(a-b for a,b in zip(point(part,local_up,0.,rotation),origin))
    from view_navigation import plane_axes
    _,up,normal=plane_axes(normal,up)
    return normal,up


def _context(design,index,local_scene,target,normal,up,radius,base_scene=None,visible_indices=None,depth_mm=0.):
    """Preserve the visible assembly and fade actual foreground intersections."""
    from preview3d import Scene, build_scene
    from rust_surfaces import surface
    from geometry_quality import part as representation_part
    from stl_export import triangles
    from view_navigation import plane_axes,bounds_in_front,triangle_in_front
    base=base_scene or build_scene(design,True,True,frame_explosion=True)
    visible=set(visible_indices) if visible_indices is not None else {p.source_index for p in base.parts}
    visible.add(index)
    axes=plane_axes(normal,up);centers={};occluded=[]
    # The viewed material spans a working band below the front profile plane.
    # Equal-height neighbours can hide that band even when their front faces
    # are coplanar with the focused gear's front face.
    behind_band=tuple(a-depth_mm*b for a,b in zip(target,normal))
    for i in sorted(visible):
        control_check()
        part=representation_part(design,design.parts[i],'preview')
        bounds=surface(part).call('solid_bounds')
        centers[i]=tuple((a+b)/2 for a,b in zip(*bounds))
        if i!=index and bounds_in_front(bounds,behind_band,axes,radius):
            if any(triangle_in_front(t,behind_band,axes,radius) for t in triangles(part,control_check)):
                occluded.append(i)
    parts=[replace(p,opacity=.25 if p.source_index in occluded else 1.,
                   center=centers[p.source_index],context=p.source_index in occluded)
           for p in base.parts if p.source_index in visible]
    vertices=array('f',base.vertices)
    if local_scene is not None:
        offset=len(vertices)//6;vertices.extend(local_scene.vertices)
        def shift(span):return (span[0]+offset,span[1])
        for mesh in local_scene.parts[1:]:
            parts.append(replace(mesh,side=shift(mesh.side),edges=shift(mesh.edges),
                caps=[replace(c,fan=shift(c.fan),plane=shift(c.plane)) for c in mesh.caps],
                source_index=index,opacity=.32,center=target))
    # Detail is nominal: none of the material-coordinate deformation attributes
    # are used, and the original scene/buffers remain untouched.
    scene=Scene(vertices,parts,base.grid,base.center,base.radius,base.bounds,array('f'))
    return scene,tuple(occluded)


def prepare_component(design,index,*,base_scene=None,visible_indices=None):
    """The same paper view for a selected gear, including differential bevels."""
    if type(index) is not int or not 0<=index<len(design.parts) or not supported(design.parts[index]):
        raise ValueError('Tooth view requires one supported gear.')
    part=design.parts[index]
    if part.profile_metadata.get('tip_preview_source'):
        return _prepare(design,index,base_scene,visible_indices)
    # Use a real heel/top-land vertex, rather than inventing a cylindrical
    # profile or an axis from the differential's input/output role.
    z,angle,contour=profile_sections(part)[-1]
    maximum=max(hypot(*q) for q in contour)
    candidates=[q for q in contour if hypot(*q)>=maximum-maximum*1e-7]
    tip=min(candidates,key=lambda q:abs(atan2(q[0],q[1])))
    target=point(part,tip,z,radians(angle))
    normal,up=_plane(part,tip,radians(angle))
    m=design.values['module'];radius=2.4*m;bottom=z-min(2*m,part.width)*.9
    back=point(part,tip,bottom,radians(angle))
    depth=max(0.,sum((a-b)*n for a,b,n in zip(target,back,normal)))
    scene,occluded=_context(design,index,None,target,normal,up,radius,base_scene,visible_indices,depth)
    return Detail(scene,index,target,normal,radius,part.name,0,(bottom,z),up,occluded,False)


def prepare(design, field, *, base_scene=None, visible_indices=None):
    return _prepare(design,component_index(design,field),base_scene,visible_indices)


def _prepare(design,index,base_scene=None,visible_indices=None):
    """CPU-only preparation; neither the design nor its original scene is edited.

    The upper working band avoids the relieved groove of a double helix. Its
    sections follow the actual source's corresponding sweep/station frames.
    """
    from preview3d import build_scene
    from geometry_quality import part as representation_part
    part = representation_part(design, design.parts[index], 'preview')
    source = part.profile_metadata.get('tip_preview_source', {})
    head = call('tooth_tip_preview', dict(source=source,
                 profile=part.profile_metadata.get('tooth_profile', {})))
    m = head['normal_module_mm']
    band = min(2*m, (part.width-part.gap)/2 if part.double else part.width)*.9
    bottom, top = part.width-band, part.width
    linear = source['kind'] == 'linear'
    rows = profile_sections(part)
    frames = []
    previous = 0.
    for z, angle, outer in rows:
        control_check()
        rotation = radians(angle)
        dx = dy = 0.
        if linear:
            # The rack's first three base/end vertices stay fixed. The next
            # corresponding vertex is a tooth root and follows the helix.
            dx, dy = (outer[3][i]-part.outer[3][i] for i in (0, 1))
        elif outer is not part.outer and outer != part.outer:
            a, b = part.outer[0], outer[0]
            rotation += atan2(a[0]*b[1]-a[1]*b[0], a[0]*b[0]+a[1]*b[1])
        rotation += round((previous-rotation)/(2*pi))*2*pi
        frames.append((z, rotation, dx, dy))
        previous = rotation

    def at(z):
        for a, b in zip(frames, frames[1:]):
            if a[0] <= z <= b[0] and b[0] > a[0]:
                f = (z-a[0])/(b[0]-a[0])
                return tuple(a[i]+f*(b[i]-a[i]) for i in (1, 2, 3))
        return frames[-1][1:]

    def placed_xy(q, z):
        angle, dx, dy = at(z)
        c, s = cos(angle), sin(angle)
        return (q[0]*c-q[1]*s+dx, q[0]*s+q[1]*c+dy)

    levels = sorted({bottom, top, *(z for z, *_ in frames if bottom < z < top)})
    ghosts = []
    for polygon in head['polygons']:
        stations = [dict(z=z, outer=[placed_xy(q, z) for q in polygon], holes=[])
                    for z in levels]
        ghosts.append(Part('Removed tooth material', stations[0]['outer'],
            width=part.width, z=part.z, center=part.center, frame=part.frame,
            axis_x=part.axis_x, stations=stations, color=(1., .48, .12),
            surface_tolerance_mm=part.surface_tolerance_mm))
    base=base_scene or build_scene(design,True,True,frame_explosion=True)
    local_scene = build_scene(replace(design, parts=[part, *ghosts]), True, True)
    z = top
    xy = placed_xy(head['target_xy'], z)
    target = point(part, xy, z, 0.)
    rotation = at(z)[0]
    direction,up=_plane(part,head['direction_xy'],rotation)
    back=point(part,xy,bottom,0.)
    depth=max(0.,sum((a-b)*n for a,b,n in zip(target,back,direction)))
    scene,occluded=_context(design,index,local_scene,target,direction,up,2.4*m,base,visible_indices,depth)
    return Detail(scene, index, target, direction, 2.4*m, part.name,
                  len(ghosts), (bottom, top),up,occluded)
