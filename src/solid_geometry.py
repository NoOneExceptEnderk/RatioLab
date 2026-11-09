# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Explicit surfaces shared by preview and faceted STEP, without interpolated lofts.

point() is the placement boundary from local sections to world XYZ millimetres.
faces() preserves corresponding section vertices and outward face winding;
STL, picking and interference consume this same sampled surface.
"""
from math import cos,sin,radians,sqrt,pi,acos,ceil
from geometry import profile_sections,section_holes,circle_info,circle


PALETTE=[(.23,.68,.82),(.96,.66,.33),(.48,.74,.59),(.69,.59,.86)]

def kernel_part(p):
    """Only geometric fields cross the ABI; product metadata stays in Python."""
    return {key:getattr(p,key) for key in ('outer','holes','width','z','center','twist',
        'axis_x','double','gap','core_radius','internal','stations','mesh','frame','alternate_diagonal','surface_tolerance_mm')}


def sampling_report(p):
    """Bounded interpolation relative to sampled contours, never a gear grade."""
    from rust_surfaces import surface
    result=surface(p).sampling_report()
    profile=p.profile_metadata.get('tooth_profile',{})
    result['profile_chord_threshold_mm']=profile.get('chord_threshold_mm')
    result['profile_error_globally_bounded']=False
    return result


def profile_report(p):
    """Keep exported interpolation metadata tied to the live surface snapshot."""
    result=dict(p.profile_metadata)
    if 'surface_sampling' in result:result['surface_sampling']=sampling_report(p)
    return result


def point(part,xy,z,angle):
    from rust_geometry import call
    placement=dict(outer=[[0,0],[1,0],[0,1]],width=part.width,z=part.z,
        center=part.center,axis_x=part.axis_x,frame=part.frame)
    return tuple(call('solid_point',dict(part=placement,xy=xy,z=z,angle=angle)))


def points(part,rows):
    from rust_geometry import call
    placement=dict(outer=[[0,0],[1,0],[0,1]],width=part.width,z=part.z,
        center=part.center,axis_x=part.axis_x,frame=part.frame)
    return [tuple(q) for q in call('solid_points',dict(part=placement,points=rows))]


def section_loops(p,outer,z,station_index=None):
    from rust_surfaces import surface
    from geometry import resolve_station_index
    index=resolve_station_index(p,z,outer,station_index) if p.stations else 0
    return [[tuple(q) for q in loop] for loop in surface(p).call('solid_section_loops',
        outer=outer,z=z,station_index=index)]


def rings(p):
    from rust_surfaces import surface
    return [[[tuple(q) for q in loop] for loop in level]
            for level in surface(p).geometry('solid_rings')]


def faces(p):
    return list(iter_faces(p))


def iter_faces(p,check=None):
    from rust_surfaces import surface
    yield from surface(p,check).faces(check)


def signature(p):
    from rust_surfaces import surface
    return surface(p).call('solid_signature')


def faceted_body(p,quoted_name,add):
    """Write identical shared faces directly into a caller's entity namespace."""
    from rust_surfaces import surface
    snapshot=surface(p);points={}
    def ref(i):return '#'+str(i)
    def refs(ids):return '('+','.join(map(ref,ids))+')'
    def num(x):
        text=format(float(x),'.15g')
        return text if '.' in text or 'e' in text else text+'.'
    for face in snapshot.faces():
        for loop in face:
            for q in loop:
                if q not in points:points[q]=add("CARTESIAN_POINT('',("+','.join(map(num,q))+"))")
    faceids=[]
    for face in snapshot.faces():
        bounds=[]
        for j,loop in enumerate(face):
            wire=add("POLY_LOOP('',"+refs(points[q] for q in loop)+")")
            bounds.append(add(('FACE_OUTER_BOUND' if j==0 else 'FACE_BOUND')+"('',"+ref(wire)+",.T.)"))
        loop=face[0];a=loop[0];b=loop[1]
        u=tuple(b[i]-a[i] for i in range(3));length=sqrt(sum(x*x for x in u));u=tuple(x/length for x in u)
        n=[0.,0.,0.]
        for b,c in zip(loop,loop[1:]+loop[:1]):
            n[0]+=(b[1]-c[1])*(b[2]+c[2]);n[1]+=(b[2]-c[2])*(b[0]+c[0]);n[2]+=(b[0]-c[0])*(b[1]+c[1])
        length=sqrt(sum(x*x for x in n))
        if length<1e-15:raise ValueError('Degenerate face in the shared geometry.')
        n=tuple(x/length for x in n)
        axis=add("DIRECTION('',("+','.join(map(num,n))+"))")
        direction=add("DIRECTION('',("+','.join(map(num,u))+"))")
        placement=add("AXIS2_PLACEMENT_3D('',"+ref(points[a])+","+ref(axis)+","+ref(direction)+")")
        plane=add("PLANE('',"+ref(placement)+")")
        faceids.append(add("FACE_SURFACE('',"+refs(bounds)+","+ref(plane)+",.T.)"))
    shell=add("CLOSED_SHELL('',"+refs(faceids)+")")
    return add("FACETED_BREP("+quoted_name+","+ref(shell)+")")


def step(p,name):
    """ISO 10303-21 FACETED_BREP with the same side triangles as the preview."""
    entities=[]
    def add(value):entities.append(value);return len(entities)
    def ref(i):return '#'+str(i)
    def refs(ids):return '('+','.join(map(ref,ids))+')'
    solid=faceted_body(p,"'"+name.replace("'","''")+"'",add)
    mm=add("(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.))")
    rad=add("(NAMED_UNIT(*) PLANE_ANGLE_UNIT() SI_UNIT($,.RADIAN.))")
    sr=add("(NAMED_UNIT(*) SI_UNIT($,.STERADIAN.) SOLID_ANGLE_UNIT())")
    unc=add("UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-7),"+ref(mm)+",'distance_accuracy_value','')")
    context=add("(GEOMETRIC_REPRESENTATION_CONTEXT(3) GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT(("+ref(unc)+")) GLOBAL_UNIT_ASSIGNED_CONTEXT("+refs([mm,rad,sr])+") REPRESENTATION_CONTEXT('',''))")
    shape=add("SHAPE_REPRESENTATION('',("+ref(solid)+"),"+ref(context)+")")
    application=add("APPLICATION_CONTEXT('configuration controlled 3d designs of mechanical parts and assemblies')")
    add("APPLICATION_PROTOCOL_DEFINITION('international standard','config_control_design',1994,"+ref(application)+")")
    product_context=add("PRODUCT_CONTEXT('',"+ref(application)+",'mechanical')")
    product=add("PRODUCT('RatioLab','RatioLab part','',("+ref(product_context)+"))")
    formation=add("PRODUCT_DEFINITION_FORMATION_WITH_SPECIFIED_SOURCE('','',"+ref(product)+",.NOT_KNOWN.)")
    definition_context=add("PRODUCT_DEFINITION_CONTEXT('part definition',"+ref(application)+",'design')")
    definition=add("PRODUCT_DEFINITION('design','',"+ref(formation)+","+ref(definition_context)+")")
    product_shape=add("PRODUCT_DEFINITION_SHAPE('','',"+ref(definition)+")")
    add("SHAPE_DEFINITION_REPRESENTATION("+ref(product_shape)+","+ref(shape)+")")
    data='\n'.join(f'#{i}={v};' for i,v in enumerate(entities,1))
    return "ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION(('RatioLab: shared preview geometry'),'2;1');\nFILE_NAME('part.step','2026-10-23T00:00:00',(''),(''),'RatioLab','RatioLab','');\nFILE_SCHEMA(('CONFIG_CONTROL_DESIGN'));\nENDSEC;\nDATA;\n"+data+"\nENDSEC;\nEND-ISO-10303-21;\n"
