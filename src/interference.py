# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Discrete kinematic interference analysis, independent from GTK.

Public entry point: analyze(design, settings=Settings(), cancel=Event(),
progress=callable, plan=None) -> Analysis. Inputs are never mutated.

Checks use the shared sampled surfaces over labelled orientation periods, not
continuous swept volumes. Expected interfaces only annotate findings; unknown
poses, unsupported deformation and unfinished coverage remain explicit.
"""
from dataclasses import dataclass, field, asdict
from fractions import Fraction
from math import pi, ceil, lcm, gcd, isfinite
from threading import Event
from time import monotonic
import json
from solid_geometry import faces
from stl_export import triangulate
from motion import build_plan, transform, IDENTITY
from collision_geometry import Surface, relation


@dataclass(frozen=True)
class Settings:
    step_degrees: float=30.
    tolerance_mm: float=.01
    max_poses: int=721
    max_seconds: float=120.
    max_triangles: int=300000
    max_parts: int=128

    def validate(self):
        if not isfinite(self.step_degrees) or not .1<=self.step_degrees<=180:raise ValueError('Angular step must be 0.1–180 degrees')
        if not isfinite(self.tolerance_mm) or not 1e-6<=self.tolerance_mm<=1:raise ValueError('Tolerance must be 0.000001–1 mm')
        if not 1<=self.max_poses<=10000 or not isfinite(self.max_seconds) or not 0<self.max_seconds<=3600:raise ValueError('Invalid analysis resource limits')
        if not 1<=self.max_parts<=128 or not 1<=self.max_triangles<=1000000:raise ValueError('Invalid geometry limits')


@dataclass
class Analysis:
    settings: dict
    period_turns: float | None=None
    period_basis: str='Full labelled part orientations and orbital phases; no tooth symmetry reduction'
    requested_end_degrees: float | None=None
    sampled_end_degrees: float=0.
    attempted_phase_degrees: float=0.
    planned_poses: int=0
    completed_poses: int=0
    completed_pairs: int=0
    pairs_per_pose: int=0
    coverage_complete: bool=False
    cancelled: bool=False
    elapsed_seconds: float=0.
    issues: list=field(default_factory=list)
    studies: list=field(default_factory=list)
    parts: list=field(default_factory=list)
    rows: list=field(default_factory=list)
    revision: object=None

    def text(self):
        lines=['RatioLab · discrete interference check',f'Revision: {self.revision}',
            'Complete sampled coverage' if self.coverage_complete else 'INCOMPLETE / unsupported coverage',
            f'Completed poses: {self.completed_poses}/{self.planned_poses}; pair checks: {self.completed_pairs}',
            f'Last fully completed phase: {self.sampled_end_degrees:.9g} deg; attempted phase: {self.attempted_phase_degrees:.9g} deg; requested end: {self.requested_end_degrees} deg',
            f'Full labelled kinematic period: {self.period_turns} reference turns. {self.period_basis}.',
            f'Angular step ≤ {self.settings["step_degrees"]:g} deg; boundary tolerance {self.settings["tolerance_mm"]:g} mm.',
            'Euclidean distances on shared preview/STL triangles in mm. Analytic STEP cylinders may differ from these facets.',
            'Boundary contact / unresolved includes the tolerance band and inconclusive overlap probes; review it.',
            'Near-collinear triangles (sin angle <= 1e-12) retain topology and use edge/point distance; maximum altitude must be <= boundary tolerance / 100.',
            'Intersection means an interior witness; containment can have positive surface distance.',
            'Depth lower bound means clearance of a strict common-interior witness where available, NOT minimum translation / exact penetration depth. Containment distance is a separate surface margin.',
            'Discrete samples only. No continuous collision-free, conjugacy, elastic or strength certification.',
            f'Limits: {self.settings["max_poses"]} poses, {self.settings["max_seconds"]:g} s, {self.settings["max_parts"]} parts, {self.settings["max_triangles"]} triangles.',
            *self.issues,*self.studies,'']
        for row in self.rows:
            lines.append(f'{row["part_a"]} ↔ {row["part_b"]}: {row["kind"]}; surface distance {row["distance"]:.9g} mm at {row["phase_degrees"]:.9g} deg; depth lower bound {row["depth_lower_bound"]} mm; {row["expected"] or "No expected interface identified"}; {row["samples"]} samples in this class')
        return '\n'.join(lines)

    def json(self):return json.dumps(asdict(self),indent=2,allow_nan=False)


class Stopped(Exception):pass


def period(plan):
    """Conservative repetition of every labelled moving part, in reference turns.

    Rational reconstruction is bounded and verified; unknown custom transforms
    require explicit rates. A float estimate that fails verification is rejected.
    """
    moving=set(plan.poses)|set(plan.warps)|set(plan.flex)
    if moving-set(plan.rates):return None
    values=[r for i in moving for r in plan.rates[i] if r]
    if not values:return 0.
    fractions=[]
    for value in values:
        if not isfinite(value):return None
        f=Fraction(value).limit_denominator(1000000)
        if abs(float(f)-value)>1e-11*max(1,abs(value)):return None
        fractions.append(f)
    denominator=lcm(*(f.denominator for f in fractions))
    numerator=gcd(*(abs(f.numerator)*(denominator//f.denominator) for f in fractions))
    turns=Fraction(denominator,numerator)
    if turns>1000000:return None
    if any(abs(float(turns)*r-round(float(turns)*r))>1e-7 for r in values):return None
    return float(turns)


def expected_interface(d,i,j):
    """Constructor identities/port membership annotate, NEVER suppress a pair."""
    a,b=d.parts[i],d.parts[j];names=(a.name.lower(),b.name.lower());f=d.family
    if f=='wolfrom' and a.port.get('rigid_group') and a.port.get('rigid_group')==b.port.get('rigid_group'):
        return 'Same rigid Wolfrom body · interface candidate (overlap still requires review)'
    if f!='wolfrom' and a.port.get('member') and a.port.get('member')==b.port.get('member') and a.port.get('stage')==b.port.get('stage'):
        return 'Same kinematic member · interface candidate (overlap still requires review)'
    for interface in d.analysis.get('mount_interfaces',[]):
        members=set(interface.get('parts',[]))|{interface.get('anchor')}
        if a.name in members and b.name in members:return 'Constructed mounting interface candidate (overlap still requires review)'
    if f in ('parallel','internal') and all(p.profile_metadata.get('tooth_profile') for p in (a,b)):
        return 'Constructed gear mesh · boundary contact expected, intersection is suspect'
    if f=='wolfrom' and all(p.profile_metadata.get('tooth_profile') for p in (a,b)):
        layers = (a.port.get('layer', 1), b.port.get('layer', 1))
        members = {a.port.get('member'), b.port.get('member')}
        if layers[0] == layers[1] and 'planet' in members and members & {'sun', 'ring', 'output'}:
            return 'Constructed Wolfrom mesh · boundary contact expected, intersection is suspect'
    if f=='planetary':
        stage=lambda n:2 if n.startswith('s2_') else 1
        if stage(names[0])==stage(names[1]) and any('planet_' in n and 'pin_' not in n for n in names) and any('_sun' in n or n.endswith('_ring') for n in names):
            return 'Constructed planetary mesh · boundary contact expected, intersection is suspect'
    if f=='cycloidal' and any(n.startswith('disc_cycloidal') for n in names) and any(n.startswith(('roller_ring','pin_output')) for n in names):
        return 'Constructed disc/roller interface · boundary contact expected, intersection is suspect'
    if f=='worm' and any(n.startswith('screw_') for n in names) and any(n.startswith('wheel_') for n in names):
        return ('Generated matching screw/wheel envelope · sampled contact; all overlaps require review' if d.analysis.get('wheel_geometry',{}).get('conjugate') else 'Worm/wheel study mesh · conjugacy unverified; all overlaps require review')
    if f=='differential' and all(n.startswith('bevel_') for n in names):
        return ('Spherical involute bevel mesh · sampled contact; all overlaps require review' if d.analysis.get('bevel',{}).get('conjugacy_verified') else 'Approximate bevel study mesh · conjugacy unverified; all overlaps require review')
    if f=='harmonic' and any(n.startswith('flexspline') for n in names):
        return ('Prescribed flexible interface · sampled moving geometry; all overlaps require review' if d.analysis.get('wave_mapping',{}).get('conjugate') else 'Flexible study interface · conjugacy unverified')
    return ''


def analyze(design,settings=None,cancel=None,progress=lambda message,fraction:None,plan=None):
    settings=settings or Settings();settings.validate();cancel=cancel or Event();start=monotonic()
    result=Analysis(asdict(settings));plan=plan or build_plan(design)
    def check():
        if cancel.is_set():raise Stopped('Cancelled by user; unfinished poses and pairs are not checked')
        if monotonic()-start>settings.max_seconds:raise Stopped('Time limit reached; unfinished poses and pairs are not checked')
    records={};base={};materials={};unsupported=set();total_triangles=0
    try:
        check()
        if not plan.supported:
            result.issues.append(plan.message);return result
        result.period_turns=period(plan)
        if result.period_turns is None:
            result.issues.append('Kinematic period cannot be established from the motion plan; checking only the initial pose')
        turns=result.period_turns or 0.
        result.requested_end_degrees=360*turns if result.period_turns is not None else None
        required=max(1,ceil(360*turns/settings.step_degrees)+1)
        result.planned_poses=min(required,settings.max_poses)
        if required>settings.max_poses:result.issues.append(f'Pose limit: {required} poses required for the full period; only a prefix is checked')
        if design.family=='worm' and not design.analysis.get('wheel_geometry',{}).get('conjugate'):
            result.studies.append('Worm/wheel conjugacy is unverified; findings describe the sampled model only')
        if design.family=='harmonic':
            result.studies.append('Prescribed flexspline deformation; no elastic, loaded-contact or continuous-clearance certification')
            if not design.analysis.get('wave_mapping',{}).get('conjugate'):
                result.studies.append('Strain-wave tooth conjugacy is unverified')
        if design.family=='differential' and not design.analysis.get('bevel',{}).get('conjugacy_verified'):
            result.studies.append('Approximate bevel tooth geometry: conjugacy and continuous tooth-contact clearance are unverified; prescribed carrier/difference kinematics only' if design.values.get('configuration')=='classic' else 'Approximate bevel tooth geometry: conjugacy and continuous tooth-contact clearance are unverified; ideal two-input kinematics only')
        if not design.parts:
            result.issues.append('No components to check');return result
        if len(design.parts)>settings.max_parts:
            result.issues.append('Part limit exceeded; no assembly check performed');return result
        for i,part in enumerate(design.parts):
            check();progress(f'Preparing {i+1}/{len(design.parts)} · {part.name}',0.)
            result.parts.append(dict(index=i,name=part.name,supported=True))
            try:
                if i in plan.flex:
                    if design.family!='harmonic' or not part.name.startswith('Flexspline'):
                        raise ValueError('Unknown deformation: only the prescribed strain-wave material map is supported')
                    from wave_geometry import material_vertices,posed_vertices
                    materials[i]=material_vertices(part,check)
                    posed_vertices(part,materials[i],plan.deformation(i,0.),check)
                if i in plan.warps:raise ValueError('Time-varying warp is not supported by this checker')
                triangles=[]
                for face in faces(part):
                    check()
                    if sum(len(loop) for loop in face)>40000:raise ValueError('Face vertex limit (40000) exceeded')
                    triangles.extend(triangulate(face,check))
                    if total_triangles+len(triangles)>settings.max_triangles:raise ValueError('Assembly triangle limit exceeded')
                surface=Surface(triangles,check)
                if i in materials and any(q not in materials[i] for triangle in triangles for q in triangle):
                    raise ValueError('Shared surface contains a vertex without an immutable material reference')
                if surface.edge_approximation_mm>settings.tolerance_mm/100:raise ValueError('Near-collinear triangle edge approximation exceeds tolerance / 100')
                result.parts[-1].update(triangles=len(triangles),thin_triangles=surface.thin_triangles,edge_approximation_mm=surface.edge_approximation_mm)
                if i in materials:result.parts[-1]['deformation']='prescribed pitch-arc/normal map'
                total_triangles+=len(triangles);base[i]=surface
            except ValueError as error:
                unsupported.add(i);result.parts[-1].update(supported=False,reason=str(error));result.issues.append(f'{i+1} · {part.name}: {error}')
        indices=list(base);pairs=[(i,j) for k,i in enumerate(indices) for j in indices[k+1:]]
        result.pairs_per_pose=len(pairs)
        step=settings.step_degrees*pi/180
        interval=2*pi*turns
        for sample in range(result.planned_poses):
            check();phase=min(sample*step,interval);result.attempted_phase_degrees=phase*180/pi
            progress(f'Pose {sample+1}/{result.planned_poses} · {phase*180/pi:.3f}°',sample/result.planned_poses)
            surfaces={}
            for i in indices:
                check()
                m=plan.matrix(i,phase)
                if i in materials:
                    mapped=posed_vertices(design.parts[i],materials[i],plan.deformation(i,phase),check)
                    transformed=[]
                    for j,triangle in enumerate(base[i].triangles):
                        if j%128==0:check()
                        transformed.append(tuple(transform(m,mapped[q]) for q in triangle))
                    surfaces[i]=Surface(transformed,check)
                    if surfaces[i].edge_approximation_mm>settings.tolerance_mm/100:raise ValueError('Deformed triangle edge approximation exceeds tolerance / 100')
                elif m==IDENTITY:surfaces[i]=base[i]
                else:
                    transformed=[tuple(transform(m,q) for q in t) for t in base[i].triangles]
                    # Validation at each transformed pose also rejects singular/custom
                    # transforms rather than silently assuming all poses are rigid.
                    surfaces[i]=Surface(transformed,check)
                    if surfaces[i].edge_approximation_mm>settings.tolerance_mm/100:raise ValueError('Transformed triangle edge approximation exceeds tolerance / 100')
            for pair_index,(i,j) in enumerate(pairs):
                check()
                progress(f'Pose {sample+1}/{result.planned_poses} · pair {pair_index+1}/{len(pairs)} · {design.parts[i].name} / {design.parts[j].name}',(sample+pair_index/max(1,len(pairs)))/result.planned_poses)
                try:relation_result=relation(surfaces[i],surfaces[j],settings.tolerance_mm)
                except ValueError as error:
                    result.issues.append(f'Pose {phase*180/pi:g}° · {design.parts[i].name} / {design.parts[j].name}: {error}')
                    continue
                key=(i,j,relation_result['kind']);previous=records.get(key)
                samples=1+(previous['samples'] if previous else 0)
                if previous is None or relation_result['distance']<previous['distance']:
                    records[key]=dict(index_a=i,index_b=j,part_a=design.parts[i].name,part_b=design.parts[j].name,
                        phase_degrees=phase*180/pi,expected=expected_interface(design,i,j),samples=samples,**relation_result)
                else:previous['samples']=samples
                result.completed_pairs+=1
            result.completed_poses+=1;result.sampled_end_degrees=phase*180/pi
        result.coverage_complete=not result.issues and not unsupported and result.completed_poses==required
        progress('Sampled check finished',1.)
    except Stopped as error:
        result.cancelled=cancel.is_set();result.issues.append(str(error))
    except ValueError as error:
        result.issues.append(f'Pose geometry unsupported: {error}')
    finally:
        severity={'Intersection':0,'Containment':1,'Boundary contact / unresolved':2,'Separated':3}
        result.rows=sorted(records.values(),key=lambda r:(severity[r['kind']],r['distance'],r['index_a'],r['index_b']))
        result.elapsed_seconds=monotonic()-start
    return result
