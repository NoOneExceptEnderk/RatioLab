# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Versioned source mathematics for CAD adapters, independent of preview meshes.

The saved recipe is the editable authority. Recompile after a parameter edit;
CAD attributes alone do not make an imported solid parametric. No CAD runtime
binding is required. Coverage is explicit and unsupported operations fail.
"""
from copy import deepcopy
from hashlib import sha256
import json
from math import isfinite

from precise_numbers import transport
from rust_geometry import call

SCHEMA='ratiolab.cad-recipe/1'
MODEL_REVISION='normal-rack-cylindrical-1'
FRAMES=dict(length='mm',input_angles='deg',phase='rad',handedness='right',
            gear_axis='+Z',rack_translation='+X',placement='local XY then world translation')
REFERENCES=['ISO 21771:2007','ISO 53:1998']


def _encoded(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')


def _single(family,v):
    p=dict(z=v['teeth'],m=v['module'],pressure=v['pressure'],backlash=v['backlash'],
           width=v['width'],bore=v['bore'],helix=v.get('helix',0),shift=v['profile_shift'],
           ha=v['addendum'],hf=v['dedendum'],internal=False,double=family=='double',gap=v.get('gap',0))
    from tooth_tips import parameters
    p.update(parameters(v))
    return dict(schema='ratiolab.nominal-plan/1',components=[dict(id='Gear',name='Gear',
        kind='cylindrical_gear',parameters=transport(p),placement=dict(center_mm=[0.,0.],z_mm=0.,phase_rad=0.),port={})])


def create(family,parameters=None,*,tolerance_mm=.001):
    """Normalize source inputs and derive a CAD-neutral nominal plan in Rust.

    ``tolerance_mm`` is independent of preview/export triangulation quality.
    The requested error is not a claim about a reader's eventual BRep or tool.
    """
    if isinstance(tolerance_mm,bool):raise ValueError('Positive finite CAD tolerance required.')
    try:tolerance=float(tolerance_mm)
    except (TypeError,ValueError,OverflowError) as error:raise ValueError('Positive finite CAD tolerance required.') from error
    if not isfinite(tolerance) or tolerance<=0:raise ValueError('Positive finite CAD tolerance required.')
    from geometry import validate
    from parallel_multistage import count
    v=validate(family,parameters or {})
    if v.get('bearing_mode','manual')!='manual' or v.get('hardware_mode','none')!='none':
        raise ValueError('Direct mathematical CAD currently requires manual dimensions and no catalog hardware.')
    if family in ('spur','helical','double'):plan=_single(family,v)
    elif family=='parallel' and count(v)>1:plan=call('nominal_parallel_plan',v)
    elif family=='rack':plan=call('nominal_rack_plan',v)
    else:raise ValueError('Direct mathematical CAD recipe is not implemented for this family / variant.')
    # Canonical values retain the compatibility number AND exact source map.
    # JSON detaches all mutable caller data, including expression trees.
    values=json.loads(_encoded(v))
    source=dict(schema=SCHEMA,model_revision=MODEL_REVISION,family=family,parameters=values,
                frames=FRAMES,references=REFERENCES,cad_tolerance_mm=tolerance)
    result=dict(source,source_sha256=sha256(_encoded(source)).hexdigest(),components=plan['components'])
    result['accuracy']=dict(requested_cad_mm=tolerance,preview_independent=True,
        arithmetic='256/512-bit analytic dimensions; binary64 source curves, layout and CAD coordinates',
        scope='Continuous source profile/sweep bounds are returned per evaluated component. CAD reader, roundoff, manufacturing, strength and conformity are excluded.')
    return json.loads(_encoded(result))


def validate(recipe):
    """Re-derive untrusted recipes; never accept serialized derived coordinates."""
    if not isinstance(recipe,dict) or recipe.get('schema')!=SCHEMA or recipe.get('model_revision')!=MODEL_REVISION:
        raise ValueError('Unsupported mathematical CAD recipe version.')
    rebuilt=create(recipe.get('family'),recipe.get('parameters'),tolerance_mm=recipe.get('cad_tolerance_mm'))
    if _encoded(recipe)!=_encoded(rebuilt):raise ValueError('CAD recipe source, frames, digest or derived components do not match the mathematical definition.')
    return rebuilt


def edit(recipe,changes):
    """Regenerate source topology and placements after changing mechanical inputs."""
    current=validate(recipe)
    if not isinstance(changes,dict):raise ValueError('CAD parameter changes must be an object.')
    values=deepcopy(current['parameters'])
    from precise_numbers import SOURCE_KEY
    sources=values.get(SOURCE_KEY,{})
    for key,value in changes.items():
        if key not in values or key==SOURCE_KEY:raise ValueError('Unknown CAD source parameter: '+str(key))
        sources.pop(key,None);values[key]=value
    if not sources:values.pop(SOURCE_KEY,None)
    return create(current['family'],values,tolerance_mm=current['cad_tolerance_mm'])


def evaluate_component(recipe,index,*,native_uniform_cubic=False):
    current=validate(recipe)
    if type(index) is not int or not 0<=index<len(current['components']):raise ValueError('Invalid CAD component index.')
    component=current['components'][index]
    if component['kind']=='cylindrical_gear':
        return call('cad_cylindrical_source',dict(component,tolerance_mm=current['cad_tolerance_mm'],native_uniform_cubic=native_uniform_cubic))
    if component['kind']=='circular_extrusion':
        return dict(schema='ratiolab.analytic-extrusion/1',**deepcopy(component),interpolation_bound_mm=0.)
    if component['kind']=='rack':
        return call('cad_rack_source',dict(component,tolerance_mm=current['cad_tolerance_mm']))
    raise ValueError('Unsupported CAD component construction; no preview-mesh fallback.')
