# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Opt-in helical and internal cylindrical CAD prototypes; no CAD dependency.

The Rust operation supplies curves, surface poles and their shared error budget.
This module only validates the source component and serializes STEP topology.
"""
from math import pi

from curved_cad import CurveWriter
from geometry import CircleProfile, gear_part
from rust_geometry import call


def _reference(design):
    v=design.values
    from tooth_tips import parameters as tip_parameters
    if design.family=='helical' and len(design.parts)==1:
        index=0;teeth=v['teeth'];internal=False;phase=0.;shift=v['profile_shift']
        expected=gear_part('Gear',teeth,v['module'],v['pressure'],v['backlash'],v['width'],v['bore'],
            helix=v['helix'],shift=shift,ha=v['addendum'],hf=v['dedendum'],**tip_parameters(v))
    elif design.family=='internal' and v.get('variant') in ('spur','helical') and len(design.parts)>=2:
        from internal_mesh import plan_fixed_internal_pair
        pair=plan_fixed_internal_pair(v['pinion'],v['wheel'],v['module'],v['pressure'],v.get('helix',0),v['backlash'])
        # The fixed-axis family's order and phase convention come directly from
        # geartrains.build_train. Export the ring only, at its nominal placement.
        index=1;teeth=v['wheel'];internal=True;phase=pi/teeth;shift=0.
        expected=gear_part('Ring_output',teeth,v['module'],v['pressure'],v['backlash'],v['width'],0,
            phase=phase,helix=v.get('helix',0),internal=True,rim=v['rim'],ha=pair['ring_addendum_coefficient'],
            minimum_join_radius_mm=pair['minimum_join_radius_mm'],safe_pair_sampling=True,**tip_parameters(v,'ring'))
    else:
        raise ValueError('Curved cylindrical prototype supports one helical gear or the ring of an internal spur/helical pair.')
    part=design.parts[index]
    for key in ('outer','holes','width','z','center','twist','axis_x','double','gap','core_radius','internal','stations','mesh','frame'):
        if getattr(part,key)!=getattr(expected,key):
            raise ValueError('Curved cylindrical prototype requires the unchanged nominal component with no extra cuts or placement.')
    circles=[(part.outer,expected.outer)] if internal else list(zip(part.holes,expected.holes))
    for actual,original in circles:
        if (not isinstance(actual,CircleProfile) or not actual.intact()
                or actual.radius!=original.radius or actual.center!=original.center):
            raise ValueError('Curved cylindrical prototype requires intact circular construction provenance.')
    analytic=expected.profile_metadata['analytic_values']
    circular=part.outer.radius if internal else (part.holes[0].radius if part.holes else 0.)
    parameters=dict(z=teeth,mt=analytic['transverse_module_mm'],depth=v['module'],
        pressure=analytic['transverse_pressure_angle_deg'],normal_pressure=v['pressure'],
        backlash=v['backlash'],shift=shift,ha=v.get('addendum',1),hf=v.get('dedendum',1.25),
        internal=internal,phase=phase,width=part.width,twist_deg=part.twist,circular_radius_mm=circular)
    parameters.update(tip_parameters(v,'ring' if internal else ''))
    if internal:
        parameters.update(ha=pair['ring_addendum_coefficient'],minimum_join_radius_mm=pair['minimum_join_radius_mm'],safe_pair_sampling=True)
    return part,index,parameters


class SweepWriter(CurveWriter):
    def __init__(self):
        super().__init__()
        self.trajectories={}

    def spline(self,points,degree,knots,multiplicities):
        poles=self.refs([self.xyz('CARTESIAN_POINT',p) for p in points])
        return self.add("B_SPLINE_CURVE_WITH_KNOTS('',"+str(degree)+','+poles
            +',.UNSPECIFIED.,.F.,.U.,'+self.refs([str(v) for v in multiplicities])+','
            +self.refs([self.num(v) for v in knots])+',.UNSPECIFIED.)')

    def curve_edge(self,description,*,shared=False):
        kind=description['kind']
        if kind=='line':
            a,b=description['points']
            # Return the raw shared line edge; callers choose its winding.
            oriented=self.edge(a,b)
            # Writer.edge appends an oriented wrapper. Only its shared raw edge
            # is needed here; every used orientation is emitted by the face.
            assert oriented=='#'+str(len(self.entities))
            self.entities.pop()
            edge=self.edges[tuple(sorted((tuple(a),tuple(b))))]
            return edge,None,tuple(a),tuple(b)
        key=None
        if shared:
            key=(kind,tuple(tuple(p) for p in description['points']),tuple(description['knots']))
            if key in self.trajectories:return self.trajectories[key]
        if kind=='spline':
            points=description['points'];a,b=points[0],points[-1]
            curve=self.spline(points,description['degree'],description['knots'],description['multiplicities'])
        else:
            a,b=description['endpoints']
            curve=self.add("CIRCLE('',"+self.placement(description['center_mm'],(0,0,1),(1,0,0))
                +','+self.num(description['radius_mm'])+')')
        edge=self.add("EDGE_CURVE('',"+self.vertex(a)+','+self.vertex(b)+','+curve+',.T.)')
        result=edge,curve,tuple(a),tuple(b)
        if key is not None:self.trajectories[key]=result
        return result

    def surface(self,patch,lower):
        kind=patch['surface_type']
        if kind=='extrusion':
            vector=self.add("VECTOR('',"+self.xyz('DIRECTION',(0,0,1))+',1.)')
            return self.add("SURFACE_OF_LINEAR_EXTRUSION('',"+lower[1]+','+vector+')')
        if kind=='cylinder':
            circle=patch['lower']
            return self.add("CYLINDRICAL_SURFACE('',"+self.placement(circle['center_mm'],(0,0,1),(1,0,0))
                +','+self.num(circle['radius_mm'])+')')
        poles=self.refs([self.refs([self.xyz('CARTESIAN_POINT',p) for p in row]) for row in patch['poles']])
        attributes=','.join((str(patch['u_degree']),str(patch['v_degree']),poles,'.UNSPECIFIED.','.F.','.F.','.U.'))
        knots=','.join((self.refs([str(v) for v in patch['u_multiplicities']]),
            self.refs([str(v) for v in patch['v_multiplicities']]),
            self.refs([self.num(v) for v in patch['u_knots']]),
            self.refs([self.num(v) for v in patch['v_knots']]),'.UNSPECIFIED.'))
        if all(w==1. for row in patch['weights'] for w in row):
            return self.add("B_SPLINE_SURFACE_WITH_KNOTS('',"+attributes+','+knots+')')
        weights=self.refs([self.refs([self.num(w) for w in row]) for row in patch['weights']])
        return self.add('(BOUNDED_SURFACE() B_SPLINE_SURFACE('+attributes+') B_SPLINE_SURFACE_WITH_KNOTS('
            +knots+') GEOMETRIC_REPRESENTATION_ITEM() RATIONAL_B_SPLINE_SURFACE('+weights
            +") REPRESENTATION_ITEM('') SURFACE())")

    def body(self,part,geometry):
        internal=geometry['internal'];faces=[];lower=[];upper=[]
        for patch in geometry['patches']:
            low=self.curve_edge(patch['lower']);high=self.curve_edge(patch['upper'])
            start=self.curve_edge(patch['start'],shared=True);end=self.curve_edge(patch['end'],shared=True)
            lower.append(low[0]);upper.append(high[0])
            refs=[(low[0],True),(end[0],True),(high[0],False),(start[0],False)]
            if internal:refs=[(edge,not forward) for edge,forward in reversed(refs)]
            bound=self.bound([self.oriented(edge,forward) for edge,forward in refs])
            surface=self.surface(patch,low)
            faces.append(self.add("ADVANCED_FACE('',("+bound+'),'+surface+(','+'.F.' if internal else ','+'.T.')+')'))
        radius=geometry['circular_radius_mm']
        low_circle=high_circle=None
        if radius:
            low_circle=self.circle((0,0,0),(0,0,1),(1,0,0),radius)
            high_circle=self.circle((0,0,part.width),(0,0,1),(1,0,0),radius)
            seam=self.curve_edge(dict(kind='line',points=[(radius,0,0),(radius,0,part.width)]))
            refs=[(low_circle,True),(seam[0],True),(high_circle,False),(seam[0],False)]
            if not internal:refs=[(edge,not forward) for edge,forward in reversed(refs)]
            bound=self.bound([self.oriented(edge,forward) for edge,forward in refs])
            surface=self.add("CYLINDRICAL_SURFACE('',"+self.placement((0,0,0),(0,0,1),(1,0,0))+','+self.num(radius)+')')
            faces.append(self.add("ADVANCED_FACE('',("+bound+'),'+surface+(','+'.T.' if internal else ','+'.F.')+')'))
        for top,z,axis in ((False,0.,(0,0,-1)),(True,part.width,(0,0,1))):
            edge_loop=upper if top else lower
            forward=top != internal
            sequence=edge_loop if forward else list(reversed(edge_loop))
            tooth_bound=self.bound([self.oriented(edge,forward) for edge in sequence],not internal)
            if radius:
                circle=self.oriented(high_circle if top else low_circle,top==internal)
                circle_bound=self.bound([circle],internal)
                bounds=[circle_bound,tooth_bound] if internal else [tooth_bound,circle_bound]
            else:bounds=[tooth_bound]
            plane=self.add("PLANE('',"+self.placement((0,0,z),axis,(1,0,0))+')')
            faces.append(self.add("ADVANCED_FACE('',"+self.refs(bounds)+','+plane+',.T.)'))
        shell=self.add("CLOSED_SHELL('',"+self.refs(faces)+')')
        return self.add('MANIFOLD_SOLID_BREP('+self.quote(part.name)+','+shell+')')


def document(design,*,tolerance_mm=.001):
    part,index,parameters=_reference(design)
    geometry=call('cad_cylindrical_geometry',dict(parameters,tolerance_mm=tolerance_mm))
    writer=SweepWriter();solid=writer.body(part,geometry)
    text=writer.finish([solid]).replace('RatioLab: sampled geometry with proven circular walls',
        'RatioLab controlled cylindrical CAD surfaces')
    # The pole grids are already serialized in STEP. Keep the recipe and error
    # contract in the report, without duplicating a large surface payload there.
    patches=[{key:patch[key] for key in ('first_curve','curve_count','surface_type','u_degree','v_degree')}
        for patch in geometry['patches']]
    metadata=dict(format='ratiolab.curved-cylindrical-prototype/1',units='mm',component=part.name,
        coordinates='nominal component coordinates',source_family=design.family,source_component_index=index+1,
        source_components=len(design.parts),scope='one source component; the saved project regenerates the full source model',
        width_mm=float(part.width),internal=part.internal,circular_radius_mm=geometry['circular_radius_mm'],
        representation='controlled tensor-product spline sweep and analytic circular walls' if part.twist else 'curved profile extrusion and analytic circular walls',
        profile=geometry['profile'],patches=patches,sweep=geometry['sweep'],step_uncertainty_mm=1e-7,
        reader_verification='not performed by the writer; use scripts/verify-curved-cad.py with independent OCCT',
        limitations='Bounded cylindrical prototype only. The internal root is the existing tangent-circle construction, not a shaping-cutter envelope. Analytic binary64 error estimates exclude certified roundoff, CAD reader tolerances, contact, strength, manufacturing and general ISO conformity.')
    return text,metadata
