# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Standalone STEP, retaining sampled teeth and promoting proven circles only.

No native CAD kernel or SolidCraft installation is needed. Circular construction
provenance comes from geometry.circle; equiradial user polygons are not fitted.
"""
from math import pi, sqrt, radians
from pathlib import Path
import json
import re

from geometry import CircleProfile, profile_sections, section_holes
from solid_geometry import faces, rings, point, signature, step as faceted_step
from export_transaction import directory, write_text


def filename(index, name):
    # Keep ASCII filenames portable across supported desktop platforms.
    name = re.sub(r'[^A-Za-z0-9_-]+', '_', name).strip('_') or 'component'
    return f'{index:03d}-{name}'


def sub(a, b):
    return tuple(x-y for x, y in zip(a, b))


def unit(a):
    length = sqrt(sum(x*x for x in a))
    if length < 1e-14:
        raise ValueError('Degenerate CAD direction.')
    return tuple(x/length for x in a)


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def radial_minimum(triangle, cylinder):
    """Minimum distance to the axis on a triangle's planar projection."""
    x, y = cylinder['x'], cross(cylinder['axis'], cylinder['x'])
    projected = [(dot(sub(p,cylinder['center']),x),dot(sub(p,cylinder['center']),y)) for p in triangle]
    area = lambda a,b:a[0]*b[1]-a[1]*b[0]
    if len(projected)==3:
        a,b,c=projected
        orientation=area((b[0]-a[0],b[1]-a[1]),(c[0]-a[0],c[1]-a[1]))
        sides=[area(a,b),area(b,c),area(c,a)]
        if abs(orientation)>1e-15 and (all(s>=0 for s in sides) or all(s<=0 for s in sides)):
            return 0.
    minimum=float('inf')
    for a,b in zip(projected,projected[1:]+projected[:1]):
        delta=(b[0]-a[0],b[1]-a[1]);den=dot(delta,delta)
        t=max(0,min(1,-dot(a,delta)/den)) if den else 0
        minimum=min(minimum,sqrt(sum((a[i]+t*delta[i])**2 for i in range(2))))
    return minimum


def circular_walls(p):
    """Find whole, invariant cylinders; keep eccentric twists and grooves sampled.

    A candidate must retain explicit circle provenance in *every* section, with
    the same radius and transformed axis. A copy stripped of provenance, mesh,
    modified/keyed contour or variable-radius station never becomes a cylinder.
    """
    if p.mesh:
        return {}
    sections = profile_sections(p)
    all_loops = [[outer]+section_holes(p, z, outer) for z, angle, outer in sections]
    result = {}
    for j in range(len(all_loops[0])):
        loops = [level[j] for level in all_loops]
        if not all(isinstance(loop, CircleProfile) and loop.intact() and loop.radius > 0 for loop in loops):
            continue
        radius = loops[0].radius
        centers = [point(p, loop.center, z, radians(angle)) for loop, (z, angle, _) in zip(loops, sections)]
        axis = unit(sub(centers[-1], centers[0]))
        height = dot(sub(centers[-1], centers[0]), axis)
        # Radius/center variation across a twisted off-axis hole is not a bore.
        if any(abs(loop.radius-radius)>1e-9 or
               sqrt(sum(x*x for x in sub(sub(center, centers[0]), tuple(dot(sub(center, centers[0]), axis)*a for a in axis))))>1e-8
               for loop, center in zip(loops, centers)):
            continue
        # Only rigid, right-handed frames are eligible for analytic promotion.
        origin = point(p, loops[0].center, sections[0][0], 0)
        x = sub(point(p, (loops[0].center[0]+1, loops[0].center[1]), sections[0][0], 0),origin)
        y = sub(point(p, (loops[0].center[0], loops[0].center[1]+1), sections[0][0], 0),origin)
        z_basis = sub(point(p, loops[0].center, sections[0][0]+1, 0),origin)
        if any(abs(dot(v,v)-1)>1e-9 for v in (x,y,z_basis)) or abs(dot(x, y))>1e-9 or dot(cross(x, y), axis)<1-1e-9:
            continue
        # Report actual polygon/cylinder deviation, not the generator threshold.
        errors = []
        for loop in loops:
            cx, cy = loop.center
            for a, b in zip(loop, loop[1:]+loop[:1]):
                a, b = (a[0]-cx, a[1]-cy), (b[0]-cx, b[1]-cy)
                length = sqrt(sum((a[k]-b[k])**2 for k in range(2)))
                errors.append(radius-sqrt(max(0, radius*radius-length*length/4)))
        result[j] = dict(center=centers[0], top=centers[-1], axis=axis, x=x,
                         radius=radius, height=height, max_radial_difference_mm=max(errors))
    return result


class Writer:
    def __init__(self):
        self.entities = []
        self.vertices = {}
        self.edges = {}

    @staticmethod
    def num(x):
        value = format(float(x), '.15g')
        return value if '.' in value or 'e' in value else value+'.'

    @staticmethod
    def quote(value):
        # STEP ISO 10303-21 Unicode escape, including names supplied by callers.
        value = str(value).replace('\\', '\\\\').replace("'", "''")
        return "'"+''.join(c if 32<=ord(c)<=126 else '\\X2\\'+c.encode('utf-16-be').hex().upper()+'\\X0\\' for c in value)+"'"

    def add(self, value):
        self.entities.append(value)
        return '#'+str(len(self.entities))

    def refs(self, values):
        return '('+','.join(values)+')'

    def xyz(self, kind, value):
        return self.add(kind+"('',("+','.join(self.num(x) for x in value)+'))')

    def placement(self, center, axis, x):
        return self.add("AXIS2_PLACEMENT_3D('',"+','.join((self.xyz('CARTESIAN_POINT', center), self.xyz('DIRECTION', axis), self.xyz('DIRECTION', x)))+')')

    def vertex(self, p):
        p = tuple(p)
        if p not in self.vertices:
            self.vertices[p] = self.add("VERTEX_POINT('',"+self.xyz('CARTESIAN_POINT', p)+')')
        return self.vertices[p]

    def edge(self, a, b):
        a, b = tuple(a), tuple(b)
        key = tuple(sorted((a, b)))
        if key not in self.edges:
            start, end = key
            vector = sub(end, start)
            direction = self.xyz('DIRECTION', unit(vector))
            vector = self.add("VECTOR('',"+direction+','+self.num(sqrt(dot(vector, vector)))+')')
            line = self.add("LINE('',"+self.xyz('CARTESIAN_POINT', start)+','+vector+')')
            self.edges[key] = self.add("EDGE_CURVE('',"+self.vertex(start)+','+self.vertex(end)+','+line+',.T.)')
        return self.oriented(self.edges[key], a==key[0])

    def oriented(self, edge, forward=True):
        return self.add("ORIENTED_EDGE('',*,*,"+edge+(','+'.T.' if forward else ','+'.F.')+')')

    def bound(self, edges, outer=True, orientation=True):
        loop = self.add("EDGE_LOOP('',"+self.refs(edges)+')')
        return self.add(('FACE_OUTER_BOUND' if outer else 'FACE_BOUND')+"('',"+loop+(','+'.T.' if orientation else ','+'.F.')+')')

    def circle(self, center, axis, x, radius):
        curve = self.add("CIRCLE('',"+self.placement(center, axis, x)+','+self.num(radius)+')')
        vertex = self.vertex(tuple(c+radius*d for c, d in zip(center, x)))
        return self.add("EDGE_CURVE('',"+vertex+','+vertex+','+curve+',.T.)')

    def plane(self, loops, circles=None):
        outer = loops[0]
        normal = [0., 0., 0.]
        for a, b in zip(outer, outer[1:]+outer[:1]):
            for i in range(3):
                normal[i] += (a[(i+1)%3]-b[(i+1)%3])*(a[(i+2)%3]+b[(i+2)%3])
        normal = unit(normal)
        x = unit(sub(outer[1], outer[0]))
        surface = self.add("PLANE('',"+self.placement(outer[0], normal, x)+')')
        bounds = []
        for j, loop in enumerate(loops):
            if circles and j in circles:
                edge, axis = circles[j]
                # Wires follow each planar face's outward winding; hole reverse.
                forward = (dot(normal, axis)>0)==(j==0)
                edges = [self.oriented(edge, forward)]
            else:
                edges = [self.edge(a,b) for a,b in zip(loop, loop[1:]+loop[:1])]
            bounds.append(self.bound(edges, j==0))
        return self.add("ADVANCED_FACE('',"+self.refs(bounds)+','+surface+',.T.)')

    def body(self, p, name, *, explicit_topology=False):
        shared = signature(p)  # Validate topology before publishing geometry.
        cylinders = circular_walls(p)
        if not cylinders:
            if explicit_topology:
                # Fusion imports implicit POLY_LOOP/FACETED_BREP boundaries as
                # surfaces on some releases. Give the same sampled faces shared
                # EDGE_CURVEs so the reader can retain their closed solid shell.
                faceids = [self.plane(face) for face in faces(p)]
                shell = self.add("CLOSED_SHELL('',"+self.refs(faceids)+')')
                solid = self.add('MANIFOLD_SOLID_BREP('+self.quote(name)+','+shell+')')
                return solid, dict(representation='sampled planar faces with explicit shared edges',
                                   cylinders=0, max_radial_difference_mm=0,
                                   sampled_volume_mm3=shared['volume_mm3'],
                                   cad_volume_mm3=shared['volume_mm3'], volume_difference_mm3=0)
            # Existing planar representation remains compact for freeform meshes.
            source = faceted_step(p, 'body')
            data = source.split('DATA;\n',1)[1].split('\nENDSEC;',1)[0]
            offset = len(self.entities)
            solid = None
            for line in data.splitlines():
                value = line.split('=',1)[1][:-1]
                if 'LENGTH_UNIT()' in value:
                    break
                value = re.sub(r'#(\d+)', lambda m:'#'+str(int(m.group(1))+offset), value)
                if value.startswith("FACETED_BREP('body',"):
                    value = value.replace("FACETED_BREP('body',",'FACETED_BREP('+self.quote(name)+',',1)
                entity = self.add(value)
                if value.startswith('FACETED_BREP('):
                    solid = entity
            return solid, dict(representation='sampled planar faces', cylinders=0, max_radial_difference_mm=0,
                               sampled_volume_mm3=shared['volume_mm3'], cad_volume_mm3=shared['volume_mm3'], volume_difference_mm3=0)
        levels = rings(p)
        faceids = []
        cap_circles = [{}, {}]
        for j, cylinder in cylinders.items():
            axis, x, radius = cylinder['axis'], cylinder['x'], cylinder['radius']
            low = self.circle(cylinder['center'], axis, x, radius)
            high = self.circle(cylinder['top'], axis, x, radius)
            cap_circles[0][j] = low, axis
            cap_circles[1][j] = high, axis
            surface = self.add("CYLINDRICAL_SURFACE('',"+self.placement(cylinder['center'], axis, x)+','+self.num(radius)+')')
            # Periodic cylinder: two complete circular bounds. Opposite winding
            # at bottom and top; inner walls face into the cavity.
            bounds = [self.bound([self.oriented(low, j==0)], True),
                      self.bound([self.oriented(high, j!=0)], False)]
            faceids.append(self.add("ADVANCED_FACE('',"+self.refs(bounds)+','+surface+(','+'.T.' if j==0 else ','+'.F.')+')'))
        for lower, upper in zip(levels, levels[1:]):
            for j, (a, b) in enumerate(zip(lower, upper)):
                if j in cylinders:
                    continue
                for k in range(len(a)):
                    nxt = (k+1)%len(a)
                    if not p.stations and not p.double and abs(p.twist)<1e-8:
                        faceids.append(self.plane([[a[k], a[nxt], b[nxt], b[k]]]))
                    else:
                        triangles = ([a[k],a[nxt],b[k]],[a[nxt],b[nxt],b[k]]) if p.alternate_diagonal else ([a[k],a[nxt],b[nxt]],[a[k],b[nxt],b[k]])
                        for tri in triangles:
                            if dot(cross(sub(tri[1],tri[0]),sub(tri[2],tri[0])),cross(sub(tri[1],tri[0]),sub(tri[2],tri[0])))>1e-24:
                                faceids.append(self.plane([tri]))
        for level, circles in (([[*reversed(loop)] for loop in levels[0]],cap_circles[0]), (levels[-1],cap_circles[1])):
            # Repeated vertices at station shoulders are omitted just as in faces.
            cleaned = [[q for i,q in enumerate(loop) if q!=loop[i-1]] for loop in level]
            faceids.append(self.plane(cleaned, circles))
        shell = self.add("CLOSED_SHELL('',"+self.refs(faceids)+')')
        solid = self.add('MANIFOLD_SOLID_BREP('+self.quote(name)+','+shell+')')
        difference = 0.;wall_metadata=[]
        for j, cylinder in cylinders.items():
            # Signed enclosed volume of the old sampled wall and its two caps.
            # Includes the slight interpolation contraction of rotating polygons.
            triangles = []
            for lower, upper in zip(levels, levels[1:]):
                a, b = lower[j], upper[j]
                for k in range(len(a)):
                    nxt = (k+1)%len(a)
                    triangles.extend(([a[k],a[nxt],b[k]],[a[nxt],b[nxt],b[k]]) if p.alternate_diagonal else ([a[k],a[nxt],b[nxt]],[a[k],b[nxt],b[k]]))
            wall_error=max(cylinder['radius']-radial_minimum(tri,cylinder) for tri in triangles)
            section_error=max(cylinder['radius']-radial_minimum([a,b],cylinder)
                for level in levels for a,b in zip(level[j],level[j][1:]+level[j][:1]))
            for loop in (list(reversed(levels[0][j])),levels[-1][j]):
                triangles.extend((loop[0],b,c) for b,c in zip(loop[1:],loop[2:]))
            sampled = sum(dot(a,cross(b,c))/6 for a,b,c in triangles)
            analytic = (1 if j==0 else -1)*pi*cylinder['radius']**2*cylinder['height']
            difference += analytic-sampled
            wall_metadata.append(dict(loop_index=j,kind='outer' if j==0 else 'hole',radius_mm=cylinder['radius'],
                center_mm=cylinder['center'],axis=cylinder['axis'],height_mm=cylinder['height'],
                max_section_radial_difference_mm=max(0,section_error),max_wall_radial_difference_mm=max(0,wall_error),
                sampled_signed_volume_mm3=sampled,cad_signed_volume_mm3=analytic))
        return solid, dict(representation='cylinders and sampled planar faces', cylinders=len(cylinders),
                           max_radial_difference_mm=max(c['max_wall_radial_difference_mm'] for c in wall_metadata),
                           circular_walls=wall_metadata,
                           sampled_volume_mm3=shared['volume_mm3'], cad_volume_mm3=shared['volume_mm3']+difference,
                           volume_difference_mm3=difference)

    def finish(self, solids):
        mm = self.add('(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.))')
        rad = self.add('(NAMED_UNIT(*) PLANE_ANGLE_UNIT() SI_UNIT($,.RADIAN.))')
        sr = self.add('(NAMED_UNIT(*) SI_UNIT($,.STERADIAN.) SOLID_ANGLE_UNIT())')
        uncertainty = self.add("UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-7),"+mm+",'distance_accuracy_value','')")
        context = self.add('(GEOMETRIC_REPRESENTATION_CONTEXT(3) GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT(('+uncertainty+')) GLOBAL_UNIT_ASSIGNED_CONTEXT('+self.refs([mm,rad,sr])+ ") REPRESENTATION_CONTEXT('',''))")
        shape = self.add("SHAPE_REPRESENTATION('RatioLab assembly',"+self.refs(solids)+','+context+')')
        application = self.add("APPLICATION_CONTEXT('configuration controlled 3d designs of mechanical parts and assemblies')")
        self.add("APPLICATION_PROTOCOL_DEFINITION('international standard','config_control_design',1994,"+application+')')
        product_context = self.add("PRODUCT_CONTEXT('',"+application+",'mechanical')")
        product = self.add("PRODUCT('RatioLab','RatioLab assembly','',("+product_context+'))')
        formation = self.add("PRODUCT_DEFINITION_FORMATION_WITH_SPECIFIED_SOURCE('','',"+product+ ',.NOT_KNOWN.)')
        definition_context = self.add("PRODUCT_DEFINITION_CONTEXT('part definition',"+application+",'design')")
        definition = self.add("PRODUCT_DEFINITION('design','',"+formation+','+definition_context+')')
        product_shape = self.add("PRODUCT_DEFINITION_SHAPE('','',"+definition+')')
        self.add('SHAPE_DEFINITION_REPRESENTATION('+product_shape+','+shape+')')
        return "ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION(('RatioLab: sampled geometry with proven circular walls'),'2;1');\nFILE_NAME('model.step','',(''),(''),'RatioLab','RatioLab','');\nFILE_SCHEMA(('CONFIG_CONTROL_DESIGN'));\nENDSEC;\nDATA;\n"+'\n'.join(f'#{i}={v};' for i,v in enumerate(self.entities,1))+"\nENDSEC;\nEND-ISO-10303-21;\n"


def document(parts, indices=None, *, explicit_topology=False):
    """Return STEP and approximation metadata; optionally share all planar edges.

    Explicit topology keeps sampled geometry unchanged and helps readers that
    import implicit faceted boundaries as surfaces. Default exports stay compact.
    """
    if not parts:
        raise ValueError('No components to export.')
    writer = Writer()
    solids, metadata = [], []
    if indices is None:indices=range(1,len(parts)+1)
    if len(indices)!=len(parts):raise ValueError('Component index count does not match the parts.')
    for index, p in zip(indices,parts):
        solid, info = writer.body(p, f'{index:03d} {p.name}', explicit_topology=explicit_topology)
        solids.append(solid)
        metadata.append(dict(index=index, name=p.name, profile_geometry=p.profile_metadata, **info))
    return writer.finish(solids), metadata


def write(path, parts, indices=None, *, explicit_topology=False):
    content, metadata = document(parts,indices,explicit_topology=explicit_topology)
    write_text(path, content, encoding='ascii')
    return metadata


def write_files(design, folder):
    folder = Path(folder)
    components = folder/'step-parts'
    components.mkdir()
    indices=getattr(design,'source_indices',list(range(1,len(design.parts)+1)))
    for index, p in zip(indices,design.parts):
        write(components/(filename(index,p.name)+'.step'), [p],indices=[index])
    metadata = write(folder/'assembly.step', design.parts,indices=indices)
    (folder/'step-info.json').write_text(json.dumps(dict(units='mm', coordinates='nominal assembly',
        scope=getattr(design,'export_scope',None), components=metadata, limitations='Sampled tooth contours and freeform surfaces remain planar. Cylinders replace only intact circle constructions with invariant axes/radii. Reported radial differences compare circular walls against the actual shared sampled wall triangles, including twist interpolation. Volume differences are theoretical CAD minus sampled geometry, not a CAD reader measurement. These values do not bound tooth-profile or freeform error.'),indent=2)+'\n',encoding='utf-8')
    return metadata


def export(design, target):
    with directory(target) as staging:
        metadata = write_files(design, staging)
    return Path(target), metadata
