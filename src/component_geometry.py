# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Surface picking and dimensions on the shared sampled geometry, in mm.

Camera is orthographic, as in preview3d.VERTEX. No AABB is a pick surface.
Nonrigid display poses are deliberately unavailable; nominal geometry remains
inspectable. There is no analytic CAD diameter or surface-distance claim.
"""
from dataclasses import replace
from itertools import combinations
from math import cos, sin, sqrt
from collision_geometry import ray_triangle, sub, add, mul
from motion import posed_triangles


def explosion_layout(boxes, family, *, shaft_stack=None, axis=None):
    """Return full world offsets in source order and the first separated pose."""
    if not boxes:
        return (), 0.
    # Keep coaxial and interlocking parts aligned while pulling them apart.
    # For the crossed worm pair, Y is the common normal of the two shafts.
    if axis is None:
        axis = 1 if family == 'worm' else 2
    transverse = [i for i in range(3) if i != axis]
    span = max(max(hi[axis] for _, hi in boxes) - min(lo[axis] for lo, _ in boxes)
               for axis in range(3))
    clearance = max(.01, .04 * span)
    entry_clearance = clearance / 20
    minimum = 0.
    centers = [(lo[axis]+hi[axis])/2 for lo,hi in boxes]
    if shaft_stack:
        shaft,lower,upper = shaft_stack
        # The overall shaft bounds include its protruding journal. Keep its
        # explosion position between the two cams so each disc exits outward.
        centers[shaft] = (centers[lower]+centers[upper])/2
    order = sorted(range(len(boxes)), key=centers.__getitem__)
    shifts = [0.] * len(boxes)
    for position,index in enumerate(order):
        lo,hi = boxes[index]
        overlaps = []
        for other in order[:position]:
            other_lo,other_hi = boxes[other]
            if any(max(lo[i]-other_hi[i], other_lo[i]-hi[i]) >= clearance for i in transverse):
                continue
            gap = lo[axis] - other_hi[axis]
            shifts[index] = max(shifts[index], shifts[other] + max(0., clearance-gap))
            if gap < entry_clearance:
                overlaps.append((other, gap))
        # Every constraint has its final shift now. Entry is the earliest
        # common fraction at which every pair has positive clearance.
        for other,gap in overlaps:
            minimum = max(minimum, (entry_clearance-gap)/(shifts[index]-shifts[other]))

    low = min(box[0][axis]+shift for box,shift in zip(boxes,shifts))
    high = max(box[1][axis]+shift for box,shift in zip(boxes,shifts))
    nominal_low = min(box[0][axis] for box in boxes)
    nominal_high = max(box[1][axis] for box in boxes)
    recenter = ((low-nominal_low) + (high-nominal_high))/2
    offsets = tuple(tuple(shift-recenter if i == axis else 0. for i in range(3)) for shift in shifts)
    return offsets, minimum


def preview_explosion_layout(design, boxes):
    """Return full offsets, the clearance step, and the views that can open gradually."""
    shaft_stack = None
    gradual = False
    if (design.family == 'cycloidal' and design.values.get('variant') == 'dual'
            and design.analysis['ring_rollers']['bearing'] == 'none'):
        parts = {p.name:i for i,p in enumerate(design.parts) if p.role not in ('support','housing')}
        discs = ('Disc_cycloidal_1', 'Disc_cycloidal_2')
        pins = {f'Pin_output_{i+1}' for i in range(design.values['output_count'])}
        expected = set(discs) | {'Ring_pin_carrier'} | pins
        construction = design.values['eccentric_design']
        if construction == 'integral':
            shaft = design.analysis['eccentric_connection']['part']
            gradual = set(parts) == expected | {shaft}
            if gradual:
                shaft_stack = (parts[shaft], *(parts[disc] for disc in discs))
        elif construction in ('standard', 'd_shaft', 'keyed_shaft'):
            expected.update(('Eccentric_1', 'Eccentric_2'))
            if construction == 'keyed_shaft':
                expected.update(('Eccentric_key_1', 'Eccentric_key_2'))
            gradual = set(parts) == expected
    offsets,minimum = explosion_layout(boxes, design.family, shaft_stack=shaft_stack)
    if gradual:
        return offsets,minimum,(0,)
    if not minimum:
        return offsets,minimum,(0,1,2,3)
    return _checked_explosion_layout(design, boxes, offsets, minimum)


def _checked_explosion_layout(design, boxes, fallback, minimum):
    from collision_geometry import Surface, translation_clear
    from rust_geometry import control_check

    roles = [{'support':1, 'housing':2}.get(part.role,0) for part in design.parts]
    main = [i for i,role in enumerate(roles) if not role]
    meshes = {}

    def clear(i, j, offsets):
        control_check()
        movement = sub(offsets[i], offsets[j])
        a,b = boxes[i],boxes[j]
        if any(a[1][k]+max(0.,movement[k])+1e-8 < b[0][k]
               or b[1][k]+1e-8 < a[0][k]+min(0.,movement[k]) for k in range(3)):
            return True
        if not any(movement[:2]) and _matching_bore(design.parts[i], design.parts[j]):
            return True
        try:
            for k in (i,j):
                if k not in meshes:
                    meshes[k] = Surface.from_part(displayed_part(design, k))
            return translation_clear(meshes[i], meshes[j], movement)
        except ValueError:
            # A surface or sweep that could not be checked retains the
            # bounding-box clearance step.
            return False

    preferred = 1 if design.family == 'worm' else 2

    def candidates():
        yield fallback,minimum
        for axis in (0,1,2):
            if axis != preferred:
                yield explosion_layout(boxes, design.family, axis=axis)
        if design.family == 'parallel':
            yield from _parallel_explosion_candidates(design.parts, boxes)
        if design.family == 'differential':
            yield from _differential_explosion_candidates(boxes)

    try:
        if (design.family == 'planetary' and design.values.get('helix')
                and design.values.get('variant') in ('double', 'two_stage_double')):
            return _planetary_stage_offsets(design.parts, boxes, clear), 0., (0,1,2,3)
        for offsets,entry in candidates():
            if not all(clear(i,j,offsets) for i,j in combinations(main,2)):
                continue
            # Test each role combination once. A blocked pair also blocks
            # any view that contains both of those roles.
            blocked = set()
            for i,j in combinations(range(len(boxes)),2):
                view = roles[i] | roles[j]
                if view and not any(view & mask == mask for mask in blocked) and not clear(i,j,offsets):
                    blocked.add(view)
            views = tuple(view for view in range(4) if not any(view & mask == mask for mask in blocked))
            return offsets,entry,views
        return fallback,minimum,()
    finally:
        for mesh in meshes.values():
            mesh.close()


def _planetary_stage_offsets(parts, boxes, clear):
    """Keep each stage's meshes engaged and move only groups with clear paths."""
    by_stage = {}
    for index,part in enumerate(parts):
        stage,_,name = part.name.partition('_')
        gear = name in ('Sun', 'Ring') or name.startswith('Planet_')
        key = stage if stage in ('S1', 'S2') and gear else index
        by_stage.setdefault(key, []).append(index)
    groups = list(by_stage.values())

    while True:
        envelopes = [
            tuple(tuple(extreme(boxes[i][end][axis] for i in group) for axis in range(3))
                  for end,extreme in enumerate((min,max)))
            for group in groups
        ]
        shifts,_ = explosion_layout(envelopes, 'planetary')
        group_indices = [0] * len(parts)
        for index,group in enumerate(groups):
            for part in group:
                group_indices[part] = index
        offsets = tuple(shifts[index] for index in group_indices)
        parents = list(range(len(groups)))

        def root(index):
            while parents[index] != index:
                index = parents[index]
            return index

        for i,j in combinations(range(len(parts)), 2):
            first,second = root(group_indices[i]),root(group_indices[j])
            if first != second and not clear(i,j,offsets):
                parents[second] = first
        if parents == list(range(len(groups))):
            return offsets
        # Retain the original relative pose of any parts that cannot slide
        # apart along this layout. Recheck the paths after every merge.
        combined = {}
        for index,group in enumerate(groups):
            combined.setdefault(root(index), []).extend(group)
        groups = list(combined.values())


def _matching_bore(a, b):
    # Identical constant section loops can slide axially in boundary contact.
    # Keep twisted, stepped and framed solids on the mesh verification path.
    return (a.center == b.center
            and all(not (p.frame or p.axis_x or p.mesh or p.stations or p.twist or p.double) for p in (a,b))
            and (a.outer in b.holes or b.outer in a.holes))


def _parallel_explosion_candidates(parts, boxes):
    """Pull shaft centres apart transversely while opening each axial stack."""
    groups = {}
    for part,box in zip(parts, boxes):
        groups.setdefault(part.center, []).append(box)
    if len(groups) < 2:
        return
    envelopes = {center: tuple(tuple(extreme(box[end][axis] for box in group)
                                    for axis in range(2)) for end,extreme in enumerate((min,max)))
                 for center,group in groups.items()}
    span = max(max(hi[k] for _,hi in boxes)-min(lo[k] for lo,_ in boxes) for k in range(2))
    clearance = max(.01, .02*span)
    scale = 0.
    for first,second in combinations(groups,2):
        separating_scales = []
        for axis in (0,1):
            left,right = sorted((first,second), key=lambda p: p[axis])
            distance = right[axis]-left[axis]
            if distance:
                gap = envelopes[right][0][axis]-envelopes[left][1][axis]
                separating_scales.append((clearance-gap)/distance)
        scale = max(scale, min(separating_scales))
    center = tuple(sum(p[k] for p in groups)/len(groups) for k in range(2))
    radial = [(*(scale*(part.center[k]-center[k]) for k in range(2)), 0.) for part in parts]
    shifted = [tuple(add(corner,delta) for corner in box) for box,delta in zip(boxes,radial)]
    axial,_ = explosion_layout(shifted, 'parallel')
    for factor in (1., 1.5, 2.):
        offsets = tuple(add(z,mul(xy,factor)) for z,xy in zip(axial,radial))
        entry = _clearance_step(boxes, offsets)
        if entry is not None:
            yield offsets,entry


def _differential_explosion_candidates(boxes):
    """Draw the side gears and the transverse gear out along their own axes."""
    groups = {}
    for index,(lo,hi) in enumerate(boxes):
        center = tuple((a+b)/2 for a,b in zip(lo,hi))
        axis = max(range(3), key=lambda k: abs(center[k]))
        direction = 1 if center[axis] >= 0 else -1
        groups.setdefault((axis,direction), []).append(index)
    axial = [None] * len(boxes)
    outward = [None] * len(boxes)
    for (axis,direction),indices in groups.items():
        offsets,_ = explosion_layout([boxes[i] for i in indices], 'differential', axis=axis)
        for index,offset in zip(indices, offsets):
            axial[index] = offset
            outward[index] = tuple(direction if k == axis else 0. for k in range(3))
    span = max(max(hi[k] for _,hi in boxes)-min(lo[k] for lo,_ in boxes) for k in range(3))
    for factor in (.25, .5, .75, 1.):
        offsets = tuple(add(stack,mul(direction,span*factor)) for stack,direction in zip(axial,outward))
        entry = _clearance_step(boxes, offsets)
        if entry is not None:
            yield offsets,entry


def _clearance_step(boxes, offsets):
    """Find a positive box gap for every pair along the final straight path."""
    first_step = 0.
    for i,j in combinations(range(len(boxes)),2):
        candidates = []
        for left,right in ((i,j),(j,i)):
            for axis in range(3):
                gap = boxes[right][0][axis]-boxes[left][1][axis]
                change = offsets[right][axis]-offsets[left][axis]
                end = gap+change
                if end > 1e-7:
                    clearance = end/20
                    candidates.append(0. if gap >= clearance else (clearance-gap)/change)
        if not candidates:
            return None
        first_step = max(first_step, min(candidates))
    return first_step


def explosion_scale(amount, minimum):
    amount = max(0., min(1., float(amount)))
    return minimum + amount * (1.-minimum) if amount else 0.


def displayed_part(design, index, exploded=False, *, shift=None):
    """Return the sampled part at the same world translation as the preview."""
    from geometry_quality import part
    p = part(design, design.parts[index], 'preview')
    if shift is None:
        shift = explosion_offset(design, index, exploded)
    if not any(shift):
        return p
    if p.frame:
        return replace(p, frame=(add(p.frame[0], shift), *p.frame[1:]))
    dx,dy,dz = shift
    x,y = p.center
    if p.axis_x:
        # solid_geometry.point maps local placement changes to (dz, 2dy, dz-dx).
        return replace(p, z=p.z+dx, center=(x+dx-dz, y+dy/2))
    return replace(p, z=p.z+dz, center=(x+dx, y+dy))


def explosion_offset(design,index,amount=1.):
    """World translation at a slider position, without a prepared scene."""
    from rust_surfaces import surface
    amount = max(0., min(1., float(amount)))
    if not amount:
        return (0., 0., 0.)
    boxes = [surface(displayed_part(design, i)).call('solid_bounds')
             for i in range(len(design.parts))]
    offsets, minimum, views = preview_explosion_layout(design, boxes)
    if 0 in views:
        minimum = 0.
    return mul(offsets[index], explosion_scale(amount, minimum))


def triangles(part):
    from stl_export import triangles as shared_triangles
    return tuple(shared_triangles(part))


def dimensions(part):
    from rust_surfaces import surface
    lo,hi=map(tuple,surface(part).call('solid_bounds'))
    return dict(min_mm=lo,max_mm=hi,size_mm=tuple(b-a for a,b in zip(lo,hi)))


def orbit(q,yaw,tilt,roll=0.):
    from view_navigation import rotate
    return rotate(q,yaw,tilt,roll)


def unorbit(q,yaw,tilt,roll=0.):
    x,y,z=q;a,b=cos(tilt),sin(tilt);c,s=cos(yaw),sin(yaw)
    if roll:
        cr,sr=cos(roll),sin(roll);x,y=cr*x+sr*y,-sr*x+cr*y
    yy,zz=a*y+b*z,-b*y+a*z
    return c*x+s*yy,-s*x+c*yy,zz


def project(q,center,radius,zoom,yaw,tilt,width,height,roll=0.):
    p=orbit(sub(q,center),yaw,tilt,roll);aspect=max(width,1)/max(height,1)
    scale=.86/radius*zoom
    return (width*(1+p[0]*scale/max(aspect,1))/2,height*(1-p[1]*scale*min(aspect,1))/2)


def ray(x,y,center,radius,zoom,yaw,tilt,width,height,roll=0.):
    aspect=max(width,1)/max(height,1);scale=.86/radius*zoom
    local=((2*x/max(width,1)-1)*max(aspect,1)/scale,(1-2*y/max(height,1))/(scale*min(aspect,1)),4*radius)
    return add(center,unorbit(local,yaw,tilt,roll)),unorbit((0,0,-1),yaw,tilt,roll)


def pick(origin,direction,surfaces,section_y=None,max_distance=None):
    """Return the frontmost hit, with no source triangle on a cut face."""
    plane_distance=None
    if section_y is not None and abs(direction[1])>1e-12:
        t=(section_y-origin[1])/direction[1]
        if t>=0 and (max_distance is None or t<=max_distance):
            plane_distance=t
    best=None
    for index,ts in surfaces:
        crossings=[]
        for t in ts:
            distance=ray_triangle(origin,direction,t)
            if distance is None:continue
            q=add(origin,mul(direction,distance))
            if plane_distance is not None and q[1]<section_y:
                crossings.append(distance)
            if distance<0 or (max_distance is not None and distance>max_distance) or (best and distance>=best[0]):continue
            if section_y is not None and q[1]>section_y:continue
            best=(distance,index,q,t)
        if crossings and (best is None or plane_distance<best[0]):
            crossings.sort()
            # A ray on a triangulation edge can report the same crossing twice.
            count=1+sum(b-a>1e-9 for a,b in zip(crossings,crossings[1:]))
            if count%2:
                q=add(origin,mul(direction,plane_distance))
                best=(plane_distance,index,(q[0],section_y,q[2]),None)
    return (best[1],best[2],best[3]) if best else None


def pick_displayed(origin, direction, surfaces, section_y, max_distance):
    """Raycast sampled Rust surfaces without transferring their triangles."""
    best = None
    for index, surface, matrix in surfaces:
        hit = surface.call('collision_pick_surface', point=origin, direction=direction,
                           section_y=section_y, max_distance=max_distance, matrix=matrix)
        if hit is not None:
            distance, point, triangle = hit
            if best is not None and distance >= max_distance:
                continue
            best = (index, tuple(point), None if triangle is None else tuple(map(tuple, triangle)))
            # Preserve the first surface on an exact depth tie.
            max_distance = distance
    return best


def posed(ts,plan,index,phase):
    matrix=plan.matrix(index,phase)
    return tuple(posed_triangles(matrix,ts))


def distance(a,b):return sqrt(sum((x-y)**2 for x,y in zip(a,b)))
