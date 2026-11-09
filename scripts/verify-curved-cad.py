#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Independently read, measure, rewrite and edit curved cylindrical STEP with OCCT.

Development-only requirement: cadquery-ocp-novtk==8.0.1.1.0 and its proxy wheel.
RatioLab does not import or bundle either dependency. Run in an isolated Python
environment; see docs/technical/curved-cad-prototype.md for the scope of checks.
"""
import argparse
from functools import lru_cache
from collections import Counter
import hashlib
import json
from math import atan, comb, cos, hypot, isfinite, pi, sin, sqrt
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from export_transaction import directory, write_text


def require(condition, message):
    if not condition:
        raise ValueError(message)


def rotate(q, angle):
    c, s = cos(angle), sin(angle)
    return (q[0]*c-q[1]*s, q[0]*s+q[1]*c)


def bezier(row, u):
    points = row['controls']
    for _ in range(3):
        points = [tuple((1-u)*a+u*b for a,b in zip(p,q)) for p,q in zip(points,points[1:])]
    return points[0]


def expected(row, u, sources, theoretical=False):
    if row['kind'] == 'circle_arc':
        a,b = row['angles_rad']
        angle = a+u*(b-a)
        center=row.get('center_mm',(0,0))
        return (center[0]+row['radius_mm']*cos(angle),center[1]+row['radius_mm']*sin(angle))
    if not theoretical:
        return bezier(row, u)
    a,b = row['domain']; t = a+u*(b-a)
    source = sources[row['source']]
    if source['kind'] == 'rack_corner':
        # Evaluate the original rolling-rack formula, independently of the
        # simplified cotangent derivative used by the Rust fitting code.
        tool = source['tool']
        uu = (tool['tip_center_u']+tool['tip_radius']*cos(t))/tool['cos_beta']
        vv = tool['tip_center_v']+tool['tip_radius']*sin(t)
        du = -tool['tip_radius']*sin(t)/tool['cos_beta']
        dv = tool['tip_radius']*cos(t)
        phi = (uu+vv*dv/du)/tool['pitch_radius']
        point = rotate((uu-tool['pitch_radius']*phi,tool['pitch_radius']+vv),source['rotation']-phi)
    else:
        # Polar involute form; the writer uses its Cartesian roll form.
        radius = source['base_radius_mm']*sqrt(1+t*t)
        angle = source['offset_rad']+source.get('orientation',-1)*(t-atan(t))
        point = (radius*cos(angle),radius*sin(angle))
    if row['mirror']: point = (point[0],-point[1])
    return rotate(point,row['rotation_rad'])


def curve_area(row):
    """Signed area of the actual cubic polynomial, or exact circular sector."""
    if row['kind'] == 'circle_arc':
        a,b = row['angles_rad']
        r=row['radius_mm'];cx,cy=row.get('center_mm',(0,0))
        return (r*r*(b-a)+r*(cx*(sin(b)-sin(a))-cy*(cos(b)-cos(a))))/2
    p = row['controls']
    coefficients = [p[0], [3*(b-a) for a,b in zip(p[0],p[1])],
        [3*(c-2*b+a) for a,b,c in zip(p[0],p[1],p[2])],
        [d-3*c+3*b-a for a,b,c,d in zip(*p)]]
    return sum(j*(a[0]*b[1]-a[1]*b[0])/(i+j)/2
        for i,a in enumerate(coefficients) for j,b in enumerate(coefficients) if j)


def rotation_piece(twist, count, index):
    a,b=index/count,(index+1)/count;k=(b-a)*twist/3
    p,q=(cos(twist*a),sin(twist*a)),(cos(twist*b),sin(twist*b))
    return [p,(p[0]-k*p[1],p[1]+k*p[0]),(q[0]+k*q[1],q[1]-k*q[0]),q]


def c1_pieces(pieces,knots):
    """Independent knot insertion reconstruction, including nonuniform spans."""
    result=[[tuple(p) for p in row] for row in pieces]
    for i in range(1,len(result)):
        alpha=(knots[i]-knots[i-1])/(knots[i+1]-knots[i-1])
        point=tuple((1-alpha)*p+alpha*q for p,q in zip(pieces[i-1][2],pieces[i][1]))
        result[i-1][3]=point;result[i][0]=point
    return result


def profile_pieces(group,c1):
    a,b=group[0]['domain'][0],group[-1]['domain'][1]
    knots=[0.]+[(r['domain'][1]-a)/(b-a) for r in group]
    pieces=[r['controls'] for r in group]
    return c1_pieces(pieces,knots) if c1 else pieces


def rotation_pieces(sweep):
    return _rotation_pieces(sweep['twist_rad'],sweep['intervals'],'axial_c1_reconstruction_bound_mm' in sweep)


@lru_cache(maxsize=64)
def _rotation_pieces(twist,count,c1):
    h=1/count;pieces=[]
    for i in range(count):
        xy=rotation_piece(twist,count,i)
        zs=[i/count,i/count+h/3,(i+1)/count-h/3,(i+1)/count]
        pieces.append([(*p,z) for p,z in zip(xy,zs)])
    result=c1_pieces(pieces,[i/count for i in range(count+1)]) if c1 else pieces
    return tuple(tuple(tuple(p) for p in row) for row in result)


def rotation_volume_factor(sweep):
    """Integrate det(R_H)*z_H' as a degree-eight Bernstein polynomial."""
    if not sweep:return 1.
    count=sweep['intervals'];total=0.
    for p in rotation_pieces(sweep):
        dz=[3*count*(b[2]-a[2]) for a,b in zip(p,p[1:])]
        total+=sum((p[i][0]*p[j][0]+p[i][1]*p[j][1])*dz[k]*comb(3,i)*comb(3,j)*comb(2,k)
            /(9*comb(8,i+j+k)) for i in range(4) for j in range(4) for k in range(3))/count
    return total


def sweep_point(point,t,sweep,approximate=False):
    if not sweep:return (*point,t)
    twist=sweep['twist_rad'];width=sweep['width_mm']
    if approximate:
        count=sweep['intervals'];index=min(count-1,int(t*count));u=t*count-index
        controls=[p[:2] for p in rotation_pieces(sweep)[index]]
        for _ in range(3):controls=[tuple((1-u)*a+u*b for a,b in zip(p,q)) for p,q in zip(controls,controls[1:])]
        c,s=controls[0];x,y=point
        return (c*x-s*y,s*x+c*y,width*t)
    return (*rotate(point,twist*t),width*t)


def control_bound(poles,expected,weights):
    scale=poles.Weight(1,1)/weights[0]
    require(isfinite(scale) and scale>0,'Reader has nonpositive tensor weights.')
    delta=eta=radius=0.;checked=0
    for i,(points,weight) in enumerate(zip(expected,weights),1):
        for j,point in enumerate(points,1):
            actual=poles.Pole(i,j)
            delta=max(delta,sqrt(sum((a-b)**2 for a,b in zip((actual.X(),actual.Y(),actual.Z()),point))))
            radius=max(radius,sqrt(sum(x*x for x in point)))
            w=poles.Weight(i,j)
            require(isfinite(w) and w>0,'Reader has nonpositive tensor weights.')
            eta=max(eta,abs(w/(weight*scale)-1));checked+=1
    require(eta<1 and isfinite(delta),'Reader tensor cannot be bounded.')
    return delta+2*radius*eta/(1-eta),checked


def reader_tensor_bound(surface,group,sweep):
    """Compare every Bezier control/weight after independent OCCT knot insertion.

    This accounts for knot-value roundoff too: C1 pole equality alone does not
    bound the surface when interior knot values change. All spans are checked.
    """
    from OCP.GeomConvert import GeomConvert_BSplineSurfaceToBezierSurface
    first=group[0];c1='axial_c1_reconstruction_bound_mm' in sweep
    if first['kind']=='cubic':
        pieces=profile_pieces(group,c1);degree=3;weights=[1.]*4
    else:
        a,b=first['angles_rad'];r=first['radius_mm'];cx,cy=first['center_mm']
        w=cos((b-a)/2);mid=(a+b)/2
        pieces=[[first['endpoints'][0],(cx+r*cos(mid)/w,cy+r*sin(mid)/w),first['endpoints'][1]]]
        degree=2;weights=[1.,w,1.]
    rotations=rotation_pieces(sweep)
    require(surface.UDegree()==degree and surface.VDegree()==3,'Reader changed spline degree.')
    if c1:require(surface.IsCNu(1) and surface.IsCNv(1),'Reader retained a C0 surface.')
    converted=GeomConvert_BSplineSurfaceToBezierSurface(surface)
    require((converted.NbUPatches(),converted.NbVPatches())==(len(pieces),len(rotations)),
        'Reader changed controlled surface span decomposition.')
    bound=0.;checked=0
    for i,points in enumerate(pieces,1):
        for j,rotation in enumerate(rotations,1):
            actual=converted.Patch(i,j)
            require((actual.NbUPoles(),actual.NbVPoles())==(degree+1,4),'Unexpected Bezier patch degree.')
            expected=[[(c*x-s*y,s*x+c*y,sweep['width_mm']*z) for c,s,z in rotation] for x,y in points]
            error,count=control_bound(actual,expected,weights);bound=max(bound,error);checked+=count
    return dict(bound_mm=bound,poles_checked=checked,
        scope='all Bezier span controls and positive weights after independent knot insertion; numerical binary64 estimate')


def reader_curve_bound(curve,group):
    from OCP.GeomConvert import GeomConvert_BSplineCurveToBezierCurve
    spline=curve.BSpline()
    require(spline.IsCN(1),'Reader retained a C0 profile curve.')
    converted=GeomConvert_BSplineCurveToBezierCurve(spline)
    expected=profile_pieces(group,True)
    require(converted.NbArcs()==len(expected),'Reader changed controlled curve span decomposition.')
    error=0.;checked=0
    for i,points in enumerate(expected,1):
        actual=converted.Arc(i)
        require(actual.NbPoles()==4 and not actual.IsRational(),'Reader changed polynomial curve degree or weights.')
        for j,(x,y) in enumerate(points,1):
            p=actual.Pole(j);error=max(error,sqrt((p.X()-x)**2+(p.Y()-y)**2+p.Z()**2));checked+=1
    return error,checked


def verify(folder, output):
    # No application geometry or Rust transport is imported by this verifier.
    import OCP
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepClass import BRepClass_FaceClassifier
    from OCP.BRepGProp import BRepGProp
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    from OCP.BRepTools import BRepTools
    from OCP.Bnd import Bnd_Box
    from OCP.GeomAbs import GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_SurfaceOfExtrusion, GeomAbs_BSplineSurface
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    from OCP.GProp import GProp_GProps
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.Precision import Precision
    from OCP.STEPControl import STEPControl_Reader, STEPControl_Writer, STEPControl_AsIs
    from OCP.TopAbs import TopAbs_SOLID, TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX, TopAbs_IN, TopAbs_ON
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Pnt, gp_Pnt2d, gp_Ax2, gp_Dir

    info = json.loads((folder/'curved-cad-info.json').read_text())
    require(info.get('format') in ('ratiolab.curved-cad-prototype/1','ratiolab.curved-cylindrical-prototype/1'),'Unsupported prototype record.')
    profile = info['profile']; rows = profile['curves']; sources = profile['reference_sources']
    require(0 < len(rows) <= 32768, 'Unexpected curve budget.')
    sweep=info.get('sweep');internal=info.get('internal',False)
    requested = sweep['requested_surface_mm'] if sweep else profile['requested_curve_mm']
    total_bound=sweep['surface_interpolation_bound_mm'] if sweep else profile['curve_interpolation_bound_mm']
    guard = sweep['resolution_guard_mm'] if sweep else profile['resolution_guard_mm']
    require(isfinite(requested) and requested > 0, 'Invalid tolerance.')
    width, bore = info['width_mm'], info.get('circular_radius_mm',info.get('bore_radius_mm',0.))
    require(isfinite(width) and width > 0 and isfinite(bore) and bore >= 0, 'Invalid blank dimensions.')
    patches = info['patches']
    groups = [rows[p['first_curve']:p['first_curve']+p['curve_count']] for p in patches]
    require(sum(len(g) for g in groups)==len(rows) and all(groups), 'Incomplete curve patch record.')
    base_area=0.
    for group in groups:
        if group[0]['kind']=='cubic' and 'c1_reconstruction_bound_mm' in profile:
            base_area+=sum(curve_area(dict(row,controls=points)) for row,points in zip(group,profile_pieces(group,True)))
        else:base_area+=sum(map(curve_area,group))
    volume_factor=rotation_volume_factor(sweep)
    expected_volume = ((pi*bore*bore-base_area*volume_factor) if internal else (base_area*volume_factor-pi*bore*bore))*width
    require(expected_volume > 0, 'Nonpositive predicted CAD volume.')

    def shapes(shape, kind, cast=lambda x:x):
        explorer = TopExp_Explorer(shape,kind); result = []
        while explorer.More():
            item = explorer.Current()
            if not any(item.IsSame(old) for old in result): result.append(cast(item))
            explorer.Next()
        return result

    def read(path):
        reader = STEPControl_Reader()
        require(reader.ReadFile(str(path))==IFSelect_RetDone,'STEP reader rejected the document.')
        require(reader.TransferRoots()==1,'Expected exactly one transferred root.')
        shape = reader.OneShape()
        require(not shape.IsNull(),'No imported CAD shape.')
        return shape

    def xyz(point): return (point.X(),point.Y(),point.Z())
    def distance(a,b): return sqrt(sum((x-y)**2 for x,y in zip(a,b)))

    def volume(shape):
        props = GProp_GProps()
        # Resolve spline spans explicitly. On the merged sample the ordinary
        # Gauss overload returned a different volume despite identical curve
        # probes; Gauss-Kronrod with span splitting agrees with the independent
        # polynomial line integral and the unmerged representation.
        estimate = BRepGProp.VolumePropertiesGK_s(shape,props,1e-12,True,True)
        require(isfinite(estimate) and estimate >= 0,'OCCT volume integration failed.')
        return props.Mass(),estimate

    def inspect(shape):
        require(BRepCheck_Analyzer(shape,True,False,True).IsValid(),'Invalid imported BRep (exact curve-on-surface checks).')
        solids = shapes(shape,TopAbs_SOLID)
        require(len(solids)==1,'Expected one solid, not a collection of faces.')
        faces = shapes(shape,TopAbs_FACE,TopoDS.Face)
        edges = shapes(shape,TopAbs_EDGE,TopoDS.Edge)
        surface_types = Counter(str(BRepAdaptor_Surface(f).GetType()) for f in faces)
        require(sum(BRepAdaptor_Surface(f).GetType()==GeomAbs_Plane for f in faces)==2,
            'Expected two end planes and curved side faces.')
        expected_types=Counter()
        mapping={'extrusion':GeomAbs_SurfaceOfExtrusion,'cylinder':GeomAbs_Cylinder,'bspline_surface':GeomAbs_BSplineSurface}
        for patch,group in zip(patches,groups):
            expected_types[mapping[patch.get('surface_type','extrusion' if group[0]['kind']=='cubic' else 'cylinder')]]+=1
        if bore:expected_types[GeomAbs_Cylinder]+=1
        expected_types[GeomAbs_Plane]+=2
        require(Counter(BRepAdaptor_Surface(f).GetType() for f in faces)==expected_types,
            'Imported surface types do not match the controlled construction.')
        mass,integration = volume(shape)
        volume_error = abs(mass-expected_volume)
        require(volume_error <= max(1e-7,abs(expected_volume)*2e-9),'CAD volume differs from the integrated source curves.')
        box=Bnd_Box(); BRepBndLib.AddOptimal_s(shape,box,False,False)
        bounds=(*xyz(box.CornerMin()),*xyz(box.CornerMax()))
        require(abs(bounds[2])<1e-6 and abs(bounds[5]-width)<1e-6,'STEP unit or thickness mismatch.')
        max_tolerance = max(BRep_Tool.Tolerance_s(edge) for edge in edges)
        require(max_tolerance <= max(1e-6,10*info['step_uncertainty_mm']), 'Unexpectedly enlarged imported edge tolerances.')
        base = []
        for edge in edges:
            curve = BRepAdaptor_Curve(edge); a,b=curve.FirstParameter(),curve.LastParameter()
            start,end=xyz(curve.Value(a)),xyz(curve.Value(b))
            if abs(start[2])<1e-8 and abs(end[2])<1e-8 and abs(curve.Value((a+b)/2).Z())<1e-8:
                base.append((edge,curve,a,b,start,end))
        used=set(); serial_max=0.; reference_max=0.; curve_samples=0
        interior_serial_max=0.; interior_reference_max=0.; interior_samples=0
        tensor_bound=0.;tensor_poles=0;curve_control_bound=0.;curve_controls=0
        records=[]
        for group in groups:
            first,last=group[0],group[-1]
            start=(*(first['controls'][0] if first['kind']=='cubic' else first['endpoints'][0]),0.)
            end=(*(last['controls'][-1] if last['kind']=='cubic' else last['endpoints'][-1]),0.)
            candidates=[]
            for i,(_,curve,a,b,p,q) in enumerate(base):
                if i in used: continue
                direct=max(distance(start,p),distance(end,q)); reverse=max(distance(start,q),distance(end,p))
                candidates.append((min(direct,reverse),i,direct>reverse))
            require(bool(candidates),'Missing imported profile edge.')
            residual,index,reverse=min(candidates)
            require(residual<=max(guard*8,1e-8),'Imported profile endpoint was displaced or split.')
            used.add(index); edge,curve,a,b,_,_=base[index]
            a,b=(b,a) if reverse else (a,b)
            if first['kind']=='cubic' and 'c1_reconstruction_bound_mm' in profile:
                error,count=reader_curve_bound(curve,group)
                curve_control_bound=max(curve_control_bound,error);curve_controls+=count
            pa,pb=(first['domain'][0],last['domain'][1]) if first['kind']=='cubic' else (0.,1.)
            local_serial=0.;local_reference=0.
            for row in group:
                for k in range(33):
                    u=k/32
                    fraction=(row['domain'][0]+u*(row['domain'][1]-row['domain'][0])-pa)/(pb-pa) if first['kind']=='cubic' else u
                    actual=xyz(curve.Value(a+fraction*(b-a)))
                    spline=(*expected(row,u,sources),0.)
                    ideal=(*expected(row,u,sources,True),0.)
                    serialization=distance(actual,spline);deviation=distance(actual,ideal)
                    require(deviation <= row['interpolation_bound_mm']+row['join_displacement_mm']+serialization+guard*4,
                        'Imported curve exceeds its analytic approximation estimate.')
                    local_serial=max(local_serial,serialization);local_reference=max(local_reference,deviation);curve_samples+=1
            serial_max=max(serial_max,local_serial);reference_max=max(reference_max,local_reference)
            associated=[f for f in faces if BRepAdaptor_Surface(f).GetType()!=GeomAbs_Plane and
                any(edge.IsSame(e) for e in shapes(f,TopAbs_EDGE))]
            require(len(associated)==1,'Profile edge has no unique curved side face.')
            face=associated[0];surface=BRep_Tool.Surface_s(face); uv=BRepTools.UVBounds_s(face)
            if sweep and BRepAdaptor_Surface(face).GetType()==GeomAbs_BSplineSurface:
                tensor_check=reader_tensor_bound(surface,group,sweep)
                tensor_bound=max(tensor_bound,tensor_check['bound_mm'])
                tensor_poles+=tensor_check['poles_checked']
            for fraction in (.137,.5,.863):
                parameter=pa+fraction*(pb-pa)
                if first['kind']=='cubic':
                    row=next(r for r in group if min(r['domain'])-1e-14 <= parameter <= max(r['domain'])+1e-14)
                    u=(parameter-row['domain'][0])/(row['domain'][1]-row['domain'][0])
                else:row,u=first,fraction
                axials=[(i+s)/sweep['intervals'] for i in range(sweep['intervals']) for s in (.19,.53,.87)] if sweep else (.19,.53,.87)
                for axial in axials:
                    for theoretical in (False,True):
                        xy=expected(row,u,sources,theoretical)
                        point=sweep_point(xy,axial,sweep,not theoretical) if sweep else (*xy,width*axial)
                        projection=GeomAPI_ProjectPointOnSurf(gp_Pnt(*point),surface,*uv,1e-12)
                        require(projection.NbPoints()>0,'Interior projection failed.')
                        du,dv=projection.LowerDistanceParameters()
                        state=BRepClass_FaceClassifier(face,gp_Pnt2d(du,dv),Precision.Confusion_s()).State()
                        require(state in (TopAbs_IN,TopAbs_ON),'Interior probe lies outside the trimmed face.')
                        measured=projection.LowerDistance()
                        if theoretical:
                            interior_reference_max=max(interior_reference_max,measured)
                            require(measured<=total_bound+max(interior_serial_max,1e-10)+4*guard,
                                'Surface interior exceeds the combined profile/axial estimate.')
                        else:interior_serial_max=max(interior_serial_max,measured)
                    interior_samples+=1
            records.append(dict(kind=first['kind'],pieces=len(group),endpoint_displacement_mm=residual,
                sampled_serialization_error_mm=local_serial,sampled_reference_deviation_mm=local_reference))
        require(serial_max <= max(guard*16,1e-10),'STEP import changed curve geometry beyond the numerical guard.')
        require(interior_serial_max <= max(guard*64,1e-9),'STEP import changed the extruded surface.')
        require(total_bound+max(serial_max,interior_serial_max,tensor_bound,curve_control_bound)+guard < requested,
            'No remaining error margin for the measured STEP serialization.')
        return dict(valid=True,solids=1,faces=len(faces),edges=len(edges),surface_types=dict(surface_types),
            volume_mm3=mass,source_curve_volume_mm3=expected_volume,volume_difference_mm3=volume_error,
            sweep_area_factor=volume_factor,
            volume_integration_relative_estimate=integration,bounds_mm=bounds,
            maximum_edge_tolerance_mm=max_tolerance,curve_samples=curve_samples,interior_samples=interior_samples,
            sampled_serialization_error_mm=serial_max,sampled_curve_reference_deviation_mm=reference_max,
            sampled_interior_serialization_error_mm=interior_serial_max,
            sampled_interior_reference_deviation_mm=interior_reference_max,
            reader_tensor_control_bound_mm=tensor_bound if tensor_poles else None,
            reader_tensor_poles_checked=tensor_poles,
            reader_curve_control_bound_mm=curve_control_bound,reader_curve_controls_checked=curve_controls,patches=records)

    source_path=folder/'gear.step'; original=read(source_path)
    first=inspect(original)
    with directory(output) as staging:
        rewritten=staging/'occt-roundtrip.step'
        writer=STEPControl_Writer()
        require(writer.Transfer(original,STEPControl_AsIs)==IFSelect_RetDone,'OCCT rewrite transfer failed.')
        require(writer.Write(str(rewritten))==IFSelect_RetDone,'OCCT rewrite failed.')
        second=inspect(read(rewritten))
        root=profile['source_profile']['root_radius_mm']
        cutter_radius=min(.5,((bore-root) if internal else (root-bore))/8)
        require(cutter_radius>0,'No material for the editability check.')
        offset=(root+bore)/2
        tool=BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(offset,0,-1),gp_Dir(0,0,1)),cutter_radius,width+2).Shape()
        operation=BRepAlgoAPI_Cut(original,tool)
        require(operation.IsDone(),'Independent CAD cut failed.')
        edited=operation.Shape()
        require(BRepCheck_Analyzer(edited,True,False,True).IsValid() and len(shapes(edited,TopAbs_SOLID))==1,'CAD edit did not leave one valid solid.')
        edited_volume,_=volume(edited); removed=first['volume_mm3']-edited_volume
        predicted=pi*cutter_radius**2*width
        require(abs(removed-predicted)<=max(1e-7,predicted*1e-7),'CAD cut volume differs from the expected cylindrical hole.')
        result=dict(status='VERIFIED_BOUNDED_CYLINDRICAL_CAD_PROTOTYPE' if sweep else 'VERIFIED_BOUNDED_CURVED_SPUR_PROTOTYPE',ocp_version=OCP.__version__,
            source_step_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),
            source_info_sha256=hashlib.sha256((folder/'curved-cad-info.json').read_bytes()).hexdigest(),
            requested_curve_mm=requested,curve_interpolation_bound_mm=profile['curve_interpolation_bound_mm'],
            surface_interpolation_bound_mm=total_bound,internal=internal,
            first_import=first,occt_write_read=second,
            cad_edit=dict(operation='additional cylindrical through-hole in root annulus',valid=True,
                removed_volume_mm3=removed,predicted_removed_volume_mm3=predicted),
            limits='Numerical reimport probes and BRep validity/editability checks on the named cylindrical construction. The analytic profile/surface bounds are not interval certified. Reader tolerances, manufacturing, cutter/contact and other gear families are not qualified. No GUI import into Fusion, GearTrax or Gleason is claimed.')
        write_text(staging/'verification.json',json.dumps(result,indent=2,allow_nan=False)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('prototype',type=Path)
    parser.add_argument('output',type=Path,help='New verification directory, never overwritten.')
    args=parser.parse_args()
    result=verify(args.prototype,args.output)
    print(json.dumps({k:v for k,v in result.items() if k not in ('first_import','occt_write_read')},indent=2))


if __name__=='__main__': main()
