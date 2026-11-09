# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Component ledger and complete supported source-surface error enclosures.

The total names its representation. Output/reader limits remain separate;
unsupported proofs retain a null total and an explicit unresolved reason.
"""
from fractions import Fraction
from math import sin,pi,isfinite,nextafter,inf
import struct


class UnsupportedBudget(ValueError):pass


def _fraction(value):
    value=float(value)
    if not isfinite(value):raise ValueError('Finite error-budget coordinates required.')
    return Fraction.from_float(value)


def _norm_bound(maximum):
    if not maximum:return 0.
    # Exact rational L-infinity error, rounded upward before conversion to L2.
    result=nextafter(1.733*nextafter(float(maximum),inf),inf)
    if not isfinite(result):raise ValueError('Error budget exceeds finite arithmetic.')
    return result


def _exact_world(part,point,z):
    x=_fraction(point[0])+_fraction(part.center[0])
    y=_fraction(point[1])+_fraction(part.center[1])
    zz=_fraction(z)+_fraction(part.z)
    if part.frame:
        return tuple(_fraction(part.frame[0][i])+x*_fraction(part.frame[1][i])+
            y*_fraction(part.frame[2][i])+zz*_fraction(part.frame[3][i]) for i in range(3))
    if part.axis_x:return (zz-_fraction(part.width)/2,y+_fraction(part.center[1]),-x+_fraction(part.z))
    return x,y,zz


def _provenance(design):
    from geometry import gear_part,CircleProfile
    from precise_numbers import transport
    if design.family not in ('spur','helical','double') or len(design.parts)!=1:
        raise UnsupportedBudget('The source error budget currently covers one unchanged external spur, helical or double-helical gear.')
    v=design.values;source=design.parts[0]
    expected=gear_part('Gear',v['teeth'],v['module'],v['pressure'],v['backlash'],
        v['width'],v['bore'],helix=v.get('helix',0),shift=v['profile_shift'],ha=v['addendum'],hf=v['dedendum'])
    if design.family=='double':
        from math import hypot
        expected.double=True;expected.gap=v['gap']
        expected.core_radius=min(hypot(x,y) for x,y in expected.outer)*.96
    for name in ('outer','holes','width','twist','double','gap','core_radius','internal','stations','mesh','alternate_diagonal'):
        if transport({name:getattr(source,name)})!=transport({name:getattr(expected,name)}):
            raise UnsupportedBudget('The cylindrical contour or construction changed; its source budget is not applicable.')
    for loop,original in zip(source.holes,expected.holes):
        if not isinstance(loop,CircleProfile) or not loop.intact() or loop.radius!=original.radius or loop.center!=(0,0):
            raise UnsupportedBudget('The bore must retain its original circular construction provenance.')
    if source.frame:
        if len(source.frame)!=4 or any(len(row)!=3 for row in source.frame):
            raise UnsupportedBudget('A complete finite affine placement is required.')
        a,b,c=[[_fraction(x) for x in row] for row in source.frame[1:]]
        determinant=a[0]*(b[1]*c[2]-b[2]*c[1])-a[1]*(b[0]*c[2]-b[2]*c[0])+a[2]*(b[0]*c[1]-b[1]*c[0])
        if determinant<=0:raise UnsupportedBudget('The budget requires an orientation-preserving nonsingular placement.')
    return source


def _conditional_audit(design,purpose='export',*,details=False):
    from geometry_quality import part as representation_part
    from solid_geometry import rings,section_loops,sampling_report
    from rust_geometry import call,control_check
    if design.family!='spur':raise UnsupportedBudget('Conditional spur proof requires a spur source.')
    source=_provenance(design);v=design.values
    parameters=dict(z=v['teeth'],mt=v['module'],depth=v['module'],pressure=v['pressure'],
        normal_pressure=v['pressure'],backlash=v['backlash'],shift=v['profile_shift'],ha=v['addendum'],hf=v['dedendum'])
    profile=call('spur_profile_error',parameters)
    p=representation_part(design,source,purpose);surface=sampling_report(p)
    if surface['status']!='bounded' or surface['interpolation_bound_mm']!=0.:
        raise UnsupportedBudget('This budget requires the unchanged straight extrusion.')
    bore_bound=0.
    for hole in source.holes:
        bore_bound=max(bore_bound,2*hole.radius*sin(pi/(2*len(hole)))**2*(1+256*2.220446049250313e-16))
    scale=1. if not p.frame else nextafter(2.45*max(abs(float(x)) for row in p.frame[1:3] for x in row),inf)
    placement=Fraction(0);binary32=Fraction(0);text15=Fraction(0)
    levels=rings(p)
    for z,level in zip((0.,p.width),levels):
        local=section_loops(p,p.outer,z)
        for loop,world in zip(local,level):
            if len(loop)!=len(world):raise ValueError('Unexpected spur boundary correspondence.')
            for xy,actual in zip(loop,world):
                control_check()
                exact=_exact_world(p,xy,z)
                for wanted,value in zip(exact,actual):
                    placement=max(placement,abs(wanted-_fraction(value)))
                    try:packed=struct.unpack('<f',struct.pack('<f',value))[0]
                    except OverflowError as error:raise ValueError('Spur surface exceeds binary32 range.') from error
                    binary32=max(binary32,abs(_fraction(packed)-_fraction(value)))
                    text15=max(text15,abs(_fraction(float(format(value,'.15g')))-_fraction(value)))
    placement_bound=_norm_bound(placement);quantization=_norm_bound(binary32)
    profile_bound=scale*max(profile['profile_bound_mm'],bore_bound)
    conditional=nextafter(profile_bound+placement_bound,inf)
    record=dict(schema='ratiolab.geometric-error-budget/1',family='spur',purpose=purpose,units='mm',
        status='conditional_boundary_bound',total_error_bound_mm=None,
        requested_sweep_interpolation_mm=p.surface_tolerance_mm,
        components=dict(transverse_profile_mm=profile['profile_bound_mm'],bore_polygon_mm=bore_bound,
            placement_error_scale=scale,sweep_interpolation_mm=0.,placement_roundoff_mm=placement_bound,
            binary32_coordinate_quantization_mm=quantization,step_vertex_text_quantization_mm=_norm_bound(text15)),
        conditional_binary64_boundary_bound_mm=conditional,
        conditional_stl_boundary_bound_mm=nextafter(conditional+quantization,inf),
        reference='existing trimmed rounded-rack/involute spur boundary and concentric bore; binary64 source parameters, before sampling/grid cleanup',
        coverage='source boundary chords, repeated teeth, grid/cleanup, straight extrusion, affine placement of sampled vertices and binary32 surface-coordinate conversion',
        unquantified=profile['unquantified']+[
            'formal directed-rounding proof of analytic estimates',
            'global correspondence of filled ideal end caps beyond validated sampled solids',
            'STEP reader/kernel tolerances and re-evaluated analytic entities',
            'continuous contact, cutter feasibility, strength and manufacturing'],
        source_profile=profile if details else {k:v for k,v in profile.items() if k!='curves'})
    return record


def available_report(design,purpose):
    try:return audit(design,purpose)
    except UnsupportedBudget as error:
        return dict(schema='ratiolab.geometric-error-budget/1',status='not_evaluated',
            family=design.family,purpose=purpose,total_error_bound_mm=None,reason=str(error),
            components=dict(source_equations_and_trim_mm=None,transverse_profile_mm=None,
                full_surface_interpolation_mm=None,placement_and_roundoff_mm=None,
                output_quantization_mm=None),
            output_bounds={key:dict(status='not_evaluated',bound_mm=None,reason=str(error))
                           for key in ('binary64','stl','preview','step')},
            coverage='No complete source-surface proof for this construction; per-component sweep reports remain separate.')


def _upper(value):
    """Round a nonnegative exact rational upwards, including subnormals."""
    if value<0:raise ValueError('Negative geometric error bound.')
    result=float(value)
    if not isfinite(result):raise UnsupportedBudget('The complete-surface bound exceeds finite arithmetic.')
    return nextafter(result,inf) if _fraction(result)<value else result


def _box(value):
    if not isinstance(value,list) or len(value)!=2:raise UnsupportedBudget('Missing source interval.')
    lo,hi=map(_fraction,value)
    if lo>hi:raise UnsupportedBudget('Reversed source interval.')
    return lo,hi


def _add(a,b):return a[0]+b[0],a[1]+b[1]
def _neg(a):return -a[1],-a[0]
def _mul(a,b):
    values=[x*y for x in a for y in b]
    return min(values),max(values)
def _point(value):
    q=_fraction(value);return q,q


def _source_world(xy,upper,sources,axis_x):
    center=[_box(q) for q in sources['center']];offset=_box(sources['z'])
    width=_box(sources['width']);local_z=width if upper else _point(0.)
    x=_add(_point(xy[0]),center[0]);y=_add(_point(xy[1]),center[1]);z=_add(local_z,offset)
    if sources['frame']:
        frame=[[_box(q) for q in row] for row in sources['frame']]
        return [_add(frame[0][i],_add(_mul(x,frame[1][i]),_add(_mul(y,frame[2][i]),_mul(z,frame[3][i])))) for i in range(3)]
    if axis_x:return [_add(z,_neg(_mul(width,_point(.5)))),_add(y,center[1]),_add(_neg(x),offset)]
    return x,y,z


def _orient(a,b,c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def _area2(loop):
    return sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(loop,loop[1:]+loop[:1]))


def _simple_loops(loops):
    """Exact predicates after cheap, comparison-only disjoint bounding boxes."""
    from rust_geometry import control_check
    if not loops or sum(map(len,loops))>12000:raise UnsupportedBudget('Complete-surface polygon audit exceeds its vertex budget.')
    exact=[[( _fraction(x),_fraction(y)) for x,y in loop] for loop in loops]
    vertices=[p for loop in loops for p in loop]
    if any(len(loop)<3 for loop in loops) or len(set(vertices))!=len(vertices):
        raise UnsupportedBudget('Complete-surface loops have duplicate or touching vertices.')
    from itertools import islice
    edges=[(j,i,a,b,exact[j][i],exact[j][(i+1)%len(loop)])
           for j,loop in enumerate(loops) for i,(a,b) in enumerate(zip(loop,loop[1:]+loop[:1]))]
    edges.sort(key=lambda e:min(e[2][0],e[3][0]))
    candidates=0
    for k,(j,i,a,b,aa,bb) in enumerate(edges):
        if k%32==0:control_check()
        for jj,ii,c,d,cc,dd in islice(edges,k+1,None):
            if min(c[0],d[0])>max(a[0],b[0]):break
            candidates+=1
            if candidates>2000000:raise UnsupportedBudget('Exact loop-intersection proof exceeds its candidate budget.')
            if j==jj and (i-ii)%len(loops[j]) in (1,len(loops[j])-1):continue
            if (max(a[0],b[0])<min(c[0],d[0]) or max(c[0],d[0])<min(a[0],b[0]) or
                max(a[1],b[1])<min(c[1],d[1]) or max(c[1],d[1])<min(a[1],b[1])):continue
            if _orient(aa,bb,cc)*_orient(aa,bb,dd)<=0 and _orient(cc,dd,aa)*_orient(cc,dd,bb)<=0:
                raise UnsupportedBudget('Complete-surface loops cross or touch.')
    def winding(p,loop):
        value=0
        for a,b in zip(loop,loop[1:]+loop[:1]):
            if a[1]<=p[1]<b[1] and _orient(a,b,p)>0:value+=1
            if b[1]<=p[1]<a[1] and _orient(a,b,p)<0:value-=1
        return value
    if _area2(exact[0])<=0 or any(_area2(h)>=0 for h in exact[1:]):
        raise UnsupportedBudget('Complete-surface loops have inconsistent winding.')
    for j,hole in enumerate(exact[1:],1):
        if winding(hole[0],exact[0])!=1 or any(winding(hole[0],h) for i,h in enumerate(exact[1:],1) if i!=j):
            raise UnsupportedBudget('Complete-surface holes are outside or nested.')
    return exact


def _cap_cover(loops,triangles,orientation):
    """Positive exact triangles + boundary chain prove coverage without overlap."""
    from collections import Counter
    xy={p:tuple(map(_fraction,p)) for loop in loops for p in loop}
    edge=Counter();area=Fraction(0)
    for row in triangles:
        if any(p not in xy for p in row):raise UnsupportedBudget('A cap has an unaccounted vertex.')
        a,b,c=[xy[p] for p in row];signed=_orient(a,b,c)
        if signed*orientation<=0:raise UnsupportedBudget('A cap triangle is collapsed or reverses orientation.')
        if orientation<0:row=(row[0],row[2],row[1]);signed=-signed
        area+=signed
        edge.update(zip(row,row[1:]+row[:1]))
    boundary=Counter((a,b) for loop in loops for a,b in zip(loop,loop[1:]+loop[:1]))
    for a,b in set(edge)|set(boundary):
        if edge[(a,b)]-edge[(b,a)]!=boundary[(a,b)]-boundary[(b,a)]:
            raise UnsupportedBudget('Cap triangles do not reproduce the exact outer/hole boundary chain.')
        if edge[(a,b)]>1:raise UnsupportedBudget('Cap triangulation duplicates an oriented edge.')
    expected=sum(_area2([xy[p] for p in loop]) for loop in loops)
    if area!=expected:raise UnsupportedBudget('Cap triangles do not cover the exact polygon area.')
    return dict(triangles=len(triangles),exact_area_and_boundary_chain=True)


def _actual_triangles(part):
    from stl_export import triangles
    return triangles(part)


def _mesh_proof(part,local,levels):
    from collections import Counter
    from rust_geometry import control_check
    if len(levels)<2 or any(len(level)!=len(local) for level in levels):
        raise UnsupportedBudget('Complete-surface coverage requires corresponding source rings.')
    _simple_loops(local)
    identifiers={};points=[];labels=[]
    for k,level in enumerate(levels):
        for j,(loop,reference) in enumerate(zip(level,local)):
            if len(loop)!=len(reference):raise UnsupportedBudget('Extrusion vertex correspondence changed.')
            for i,point in enumerate(loop):
                point=tuple(point)
                if point in identifiers:raise UnsupportedBudget('Placed extrusion vertices collapse or coincide.')
                identifiers[point]=len(points);points.append(point);labels.append((k,j,i))
    caps=[[],[]];side=Counter();edges=Counter();records=[]
    for row in _actual_triangles(part):
        if len(records)%256==0:control_check()
        try:ids=tuple(identifiers[tuple(p)] for p in row)
        except KeyError as error:raise UnsupportedBudget('The actual mesh contains a vertex outside its source rings.') from error
        if len(set(ids))!=3:raise UnsupportedBudget('The actual mesh contains a collapsed triangle.')
        records.append(ids);edges.update(zip(ids,ids[1:]+ids[:1]))
        tags=[labels[i] for i in ids]
        if len({t[0] for t in tags})==1:
            k=tags[0][0]
            if k not in (0,len(levels)-1):raise UnsupportedBudget('An interior ring contains an undeclared cap.')
            caps[int(k>0)].append(tuple(tuple(local[j][i]) for _,j,i in tags))
        else:
            if len({t[1] for t in tags})!=1:raise UnsupportedBudget('A side triangle joins different boundary loops.')
            axial=sorted({t[0] for t in tags})
            if len(axial)!=2 or axial[1]!=axial[0]+1:raise UnsupportedBudget('A side triangle skips source rings.')
            j=tags[0][1];indices=sorted({t[2] for t in tags});n=len(local[j])
            if len(indices)!=2 or (indices[1]-indices[0] not in (1,n-1)):
                raise UnsupportedBudget('A side triangle does not follow adjacent source vertices.')
            first=indices[0] if indices[1]-indices[0]==1 else indices[1]
            side[(axial[0],j,first)]+=1
    if any(count!=1 or edges[(b,a)]!=1 for (a,b),count in edges.items()):
        raise UnsupportedBudget('The actual mesh is not a closed oriented two-manifold.')
    if any(side[(k,j,i)]!=2 for k in range(len(levels)-1) for j,loop in enumerate(local) for i in range(len(loop))):
        raise UnsupportedBudget('Side triangles do not cover every source extrusion quad.')
    cap_records=[_cap_cover(local,rows,orientation) for rows,orientation in zip(caps,(-1,1))]
    # The emitted binary32 triangles retain the same connectivity. Refuse to
    # qualify a collapsed, nonfinite or exactly collinear output triangle.
    quantized=[];stl_reason=None
    for point in points:
        try:q=struct.unpack('<3f',struct.pack('<3f',*point))
        except OverflowError:stl_reason='Binary32 coordinates overflow.';break
        if any(not isfinite(v) for v in q):stl_reason='Binary32 coordinates are not finite.';break
        quantized.append(q)
    # Every finite binary float is dyadic. A shared power-of-two denominator
    # makes these exact predicates much cheaper than per-triangle Fractions.
    denominator=max(v.as_integer_ratio()[1] for row in points+quantized for v in row)
    def integers(rows):
        return [tuple(n*(denominator//d) for n,d in (v.as_integer_ratio() for v in row)) for row in rows]
    original=integers(points);packed=integers(quantized)
    quantization=(Fraction(max(abs(a-b) for x,y in zip(original,packed) for a,b in zip(x,y)),denominator)
                  if len(packed)==len(original) else None)
    def collapsed(exact):
        for k,row in enumerate(records):
            if k%256==0:control_check()
            a,b,c=[exact[i] for i in row];u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
            if not any((u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])):return True
        return False
    if collapsed(original):raise UnsupportedBudget('An actual binary64 triangle is exactly collinear.')
    if stl_reason is None and len(set(quantized))!=len(quantized):stl_reason='Distinct mesh vertices collapse in binary32.'
    if stl_reason is None and collapsed(packed):stl_reason='A binary32 triangle becomes exactly collinear.'
    return dict(reference_loops_simple=True,holes=len(local)-1,caps=cap_records,section_count=len(levels),
        side_triangles=sum(side.values()),closed_oriented_mesh=True,triangles=len(records),
        global_3d_self_intersections='not_evaluated_by_this_audit',
        binary32_topology_preserved=stl_reason is None,binary32_failure=stl_reason),quantization


def _placement_scale(sources):
    if sources['frame']:
        matrix=[[_box(q) for q in row] for row in sources['frame'][1:]]
        a,b,c=matrix
        det=_add(_mul(a[0],_add(_mul(b[1],c[2]),_neg(_mul(b[2],c[1])))),
            _add(_neg(_mul(a[1],_add(_mul(b[0],c[2]),_neg(_mul(b[2],c[0]))))),
                 _mul(a[2],_add(_mul(b[0],c[1]),_neg(_mul(b[1],c[0]))))))
        if det[0]<=0:raise UnsupportedBudget('Exact source placement orientation cannot be resolved.')
        maximum=max(abs(x) for row in matrix[:2] for q in row for x in q)
        scale=_upper(Fraction(245,100)*maximum)  # 2.45 > sqrt(6), a 3x2 Frobenius bound.
    else:scale=1.
    return scale


def _complete(design,purpose,record,details):
    from geometry_quality import part as representation_part
    from solid_geometry import rings,section_loops
    from rust_geometry import call,control_check
    source=design.parts[0];v=design.values;p=representation_part(design,source,purpose)
    parameters=dict(z=v['teeth'],mt=v['module'],pressure=v['pressure'],backlash=v['backlash'],
        shift=v['profile_shift'],ha=v['addendum'],hf=v['dedendum'],bore=v['bore'],
        sources=dict(width=v['width'],center=p.center,z=p.z,frame=p.frame))
    try:profile=call('spur_total_profile_error',parameters)
    except ValueError as error:raise UnsupportedBudget(str(error)) from error
    if profile.get('status')!='outward_enclosed':raise UnsupportedBudget('The source did not supply an outward total-profile enclosure.')
    for name in ('profile_bound_mm','bore_bound_mm'):
        if not isfinite(profile[name]) or profile[name]<0:raise UnsupportedBudget('Invalid outward profile bound.')
    sources=profile['source_enclosures']
    scale=_placement_scale(sources)
    levels=rings(p);local=section_loops(p,p.outer,0.)
    topology,quantization=_mesh_proof(p,local,levels)
    placement=Fraction(0)
    for upper,level in enumerate(levels):
        for loop,world in zip(local,level):
            for xy,point in zip(loop,world):
                control_check()
                exact=_source_world(xy,bool(upper),sources,p.axis_x)
                for interval,value in zip(exact,point):
                    placement=max(placement,abs(interval[0]-_fraction(value)),abs(interval[1]-_fraction(value)))
    placement_bound=_upper(Fraction(1733,1000)*placement)
    quantization_bound=_upper(Fraction(1733,1000)*quantization) if quantization is not None else None
    transverse=max(profile['profile_bound_mm'],profile['bore_bound_mm'])
    native=_upper(_fraction(scale)*_fraction(transverse)+_fraction(placement_bound))
    binary32=_upper(_fraction(native)+_fraction(quantization_bound)) if quantization_bound is not None else None
    output=dict(binary64=dict(status='bounded_complete_surface',bound_mm=native),
        stl=dict(status='bounded_complete_surface' if topology['binary32_topology_preserved'] else 'not_qualified',
            bound_mm=binary32 if topology['binary32_topology_preserved'] else None,reason=topology['binary32_failure']),
        preview=dict(status='bounded_physical_surface_vertices' if topology['binary32_topology_preserved'] else 'not_qualified',
            bound_mm=binary32 if topology['binary32_topology_preserved'] else None,reason=topology['binary32_failure'],
            scope='Physical sampled-surface coordinates before GPU model transforms; shader/motion arithmetic, projection/rasterization and grid/stencil planes are excluded.'),
        step=dict(status='not_evaluated',bound_mm=None,
            reason='Rounded STEP planes, circular promotion, trimming consistency and reader/kernel interpretation require an independent exchange budget.'))
    record.update(status='bounded_complete_surface',total_error_bound_mm=native,
        total_error_representation='binary64_model_surface',
        conditional_binary64_boundary_bound_mm=native,
        conditional_stl_boundary_bound_mm=binary32,
        metric='symmetric Hausdorff distance of the complete reference boundary, including filled end caps and bore',
        reference='exact decimal nominal spur/rack equations and validated usable trim, under the declared affine placement',
        output_bounds=output,topology=topology,
        arithmetic='Outward Rust interval arithmetic plus exact rational topology, placement propagation and output-vertex quantization; mathematical derivation and tested implementation, not proof-assistant verification.',
        coverage='Complete unchanged external-spur surface: exact input source, rack/involute trim, transverse interpolation, tooth replication, grid/cleanup, bore, side faces, filled caps, width/placement and format-specific coordinate quantization.',
        unquantified=['STEP exchange and reader/kernel interpretation (separate output; no STEP total claimed)',
            'screen-space rasterization and display projection (not model geometry)',
            'manufacturing deviations, cutter feasibility, loaded contact and strength (not geometric approximation error)'],
        source_profile=profile if details else {k:v for k,v in profile.items() if k!='curves'})
    record['components'].update(transverse_profile_mm=profile['profile_bound_mm'],bore_polygon_mm=profile['bore_bound_mm'],
        placement_error_scale=scale,placement_and_source_dimensions_mm=placement_bound,
        binary32_coordinate_quantization_mm=quantization_bound)
    return record


def _complete_curved(design,purpose,record,details):
    from geometry_quality import part as representation_part
    from solid_geometry import rings,section_loops,kernel_part,sampling_report
    from rust_geometry import call
    source=design.parts[0];v=design.values;p=representation_part(design,source,purpose)
    parameters=dict(z=v['teeth'],mt=v['module'],pressure=v['pressure'],backlash=v['backlash'],
        shift=v['profile_shift'],ha=v['addendum'],hf=v['dedendum'],bore=v['bore'],helix=v.get('helix',0),
        gap=v.get('gap',0) if p.double else 0,part=kernel_part(p),
        sources=dict(width=v['width'],center=p.center,z=p.z,frame=p.frame))
    try:sweep=call('cylindrical_total_surface_error',parameters)
    except ValueError as error:raise UnsupportedBudget(str(error)) from error
    if sweep.get('status')!='outward_enclosed':raise UnsupportedBudget('No outward cylindrical sweep enclosure.')
    profile=sweep['source_profile'];scale=_placement_scale(profile['source_enclosures'])
    if 'cap_local_loops' not in sweep:raise UnsupportedBudget('The native sweep audit lacks cap correspondence; rebuild the matching engine.')
    levels=rings(p);local=[[tuple(q) for q in loop] for loop in sweep['cap_local_loops']]
    if len(levels)!=sweep['section_count']:raise UnsupportedBudget('The audited mesh has a different section count.')
    topology,quantization=_mesh_proof(p,local,levels)
    transverse=sweep['transverse_and_groove_bound_mm'];interpolation=sweep['sweep_interpolation_mm']
    placement=sweep['placement_and_source_dimensions_mm']
    if any(not isfinite(x) or x<0 for x in (transverse,interpolation,placement,scale)):
        raise UnsupportedBudget('Invalid outward cylindrical total terms.')
    native=_upper(_fraction(scale)*(_fraction(transverse)+_fraction(interpolation))+_fraction(placement))
    quantization_bound=_upper(Fraction(1733,1000)*quantization) if quantization is not None else None
    binary32=_upper(_fraction(native)+_fraction(quantization_bound)) if quantization_bound is not None else None
    qualified=topology['binary32_topology_preserved']
    output=dict(binary64=dict(status='bounded_complete_surface',bound_mm=native),
        stl=dict(status='bounded_complete_surface' if qualified else 'not_qualified',
            bound_mm=binary32 if qualified else None,reason=topology['binary32_failure']),
        preview=dict(status='bounded_physical_surface_vertices' if qualified else 'not_qualified',
            bound_mm=binary32 if qualified else None,reason=topology['binary32_failure'],
            scope='Physical sampled-surface coordinates before GPU model transforms; shader/motion arithmetic, projection/rasterization and grid/stencil planes are excluded.'),
        step=dict(status='not_evaluated',bound_mm=None,
            reason='Rounded STEP entities, trimming consistency and reader/kernel interpretation need a separate exchange budget.'))
    record.update(status='bounded_complete_surface',total_error_bound_mm=native,
        total_error_representation='binary64_model_surface',output_bounds=output,topology=topology,
        requested_sweep_interpolation_mm=p.surface_tolerance_mm,
        conditional_binary64_boundary_bound_mm=native,conditional_stl_boundary_bound_mm=binary32,
        metric='symmetric Hausdorff distance of the complete reference boundary, including filled end caps, bore and declared groove',
        reference=sweep['reference'],
        coverage='Unchanged external cylindrical gear: exact source rack/involute trim and normal/transverse conversion; tooth replication and cleanup; resampled bore; helical sweep triangle interiors; double-helix apex, groove core and affine shoulders; actual mesh caps, width/placement and format-specific coordinates.',
        arithmetic='Outward Rust interval arithmetic and exact rational topology/output quantization; a tested derivation, not proof-assistant verification.',
        components=dict(transverse_profile_mm=profile['profile_bound_mm'],bore_polygon_mm=sweep['resampled_bore_bound_mm'],
            groove_map_lipschitz=sweep['groove_map_lipschitz'],groove_chord_mm=sweep['groove_chord_bound_mm'],
            transverse_and_groove_mm=transverse,placement_error_scale=scale,
            sweep_interpolation_mm=interpolation,placement_and_source_dimensions_mm=placement,
            binary32_coordinate_quantization_mm=quantization_bound),
        unquantified=['STEP exchange and reader/kernel interpretation (no STEP total claimed)',
            'screen projection, GPU transforms and rasterization',
            'manufacturing, tool feasibility, loaded contact, strength and industrial conformity'],
        source_profile=profile if details else {k:v for k,v in profile.items() if k!='curves'},
        source_sweep={k:v for k,v in sweep.items() if k not in ('source_profile','cap_local_loops')},
        sampled_surface_interpolation=sampling_report(p))
    return record


def audit(design,purpose='export',*,details=False,require_total=False):
    """Full supported surface bound, or an explicit unresolved component ledger.

    The scalar total refers to binary64 model geometry. File outputs each have
    their own status; the number is never presented as a manufacturing grade.
    """
    if design.family=='spur':
        record=_conditional_audit(design,purpose,details=details)
    else:
        _provenance(design)
        record=dict(schema='ratiolab.geometric-error-budget/1',family=design.family,purpose=purpose,units='mm',
            status='not_evaluated',total_error_bound_mm=None,
            components=dict(source_equations_and_trim_mm=None,transverse_profile_mm=None,
                full_surface_interpolation_mm=None,placement_and_roundoff_mm=None,output_quantization_mm=None),
            unquantified=['The complete source-surface proof has not been closed.'])
    try:return _complete(design,purpose,record,details) if design.family=='spur' else _complete_curved(design,purpose,record,details)
    except (UnsupportedBudget,ValueError) as error:
        if require_total:raise UnsupportedBudget(str(error)) from error
        record.update(total_error_status='not_evaluated',total_error_reason=str(error),
            output_bounds={key:dict(status='not_evaluated',bound_mm=None,reason=str(error))
                           for key in ('binary64','stl','preview','step')})
        return record
