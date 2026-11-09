# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Compile source recipes into native SolidCraft curves and features.

Regeneration is driven by RatioLab, using the same Rust definition each time.
SolidCraft stores a native feature timeline and the source recipe. It has no
RatioLab gear feature that automatically reacts to tooth-count/pressure edits.
The initial native adapter qualifies straight extrusions only. Unsupported
sweeps fail before any CAD mutation; they never become faceted STEP imports.
"""
import json
import re
from uuid import uuid4

from cad_contract import validate,evaluate_component

METADATA_KEY='local.ratiolab.mathematical_recipe'


def _mm(value):return repr(float(value))+' mm'


def compile(recipe,*,group=None):
    current=validate(recipe)
    group=group or 'RatioLab_math_'+uuid4().hex[:12]
    if not isinstance(group,str) or not re.fullmatch(r'RatioLab_math_[a-zA-Z0-9_]{1,64}',group):
        raise ValueError('Invalid mathematical CAD group name.')
    commands=[];bodies=[];coverage=[]
    def add(cmd,**params):
        commands.append(dict(command=cmd,params=params))
        if len(commands)>50_000:raise ValueError('Native CAD command budget exhausted.')
    add('component.activate',component='root');add('component.create',name=group)
    add('component.metadata.set',component=group,values={METADATA_KEY:dict(recipe=current,
        regeneration='RatioLab rebuilds source curves and replaces this group transactionally; native tooth-parameter auto-rebuild is unavailable.')})
    def point(p,center):return [_mm(float(p[i])+center[i]) for i in range(2)]
    for index,component in enumerate(current['components']):
        geometry=evaluate_component(current,index,native_uniform_cubic=True)
        name=group+'_'+str(index);body=name+'_body';bodies.append(body)
        placement=component['placement'];center=placement['center_mm'];z=placement['z_mm']
        width=geometry['sweep']['width_mm'] if component['kind']=='cylindrical_gear' else geometry.get('width_mm',component['parameters']['width'])
        if isinstance(width,(str,dict)):
            from rust_geometry import call
            width=call('numeric_compatibility',dict(value=width))
        width=float(width)
        add('component.create',name=name,parent=group)
        add('component.metadata.set',component=name,values={'local.ratiolab.source_component':dict(
            id=component['id'],placement=placement,port=component['port'],source_sha256=current['source_sha256'])})
        add('sketch.create',plane='XY',offset=_mm(z),name=name+'_profile')
        kind=component['kind']
        if kind=='cylindrical_gear':
            if geometry['sweep']['twist_rad']!=0:
                raise ValueError('SolidCraft native helical sweep accuracy is not qualified by this adapter; no mesh fallback.')
            curves=geometry['profile']['curves']
            points=sum(len(c['controls']) if 'controls' in c else 3 for c in curves)
            if points+2>20_000 or len(curves)>20_000:
                raise ValueError('SolidCraft sketch point/curve budget exhausted at the requested CAD tolerance; no coarser fallback.')
            for curve in curves:
                if curve['kind'] in ('cubic','uniform_cubic'):
                    add('sketch.spline.control_point',points=[point(p,center) for p in curve['controls']])
                elif curve['kind']=='circle_arc':
                    a,b=curve['endpoints']
                    add('sketch.arc.center_point',center=point(curve.get('center_mm',[0.,0.]),center),start=point(a,center),end=point(b,center))
                else:raise ValueError('Unsupported native CAD curve construction.')
            circular=geometry['circular_radius_mm']
            if circular:
                add('sketch.draw.dimensioned',command='sketch.circle.center',params=dict(center=point([0.,0.],center),radius=circular),dimensions=dict(radius=_mm(circular)))
            bound=geometry['sweep']['surface_interpolation_bound_mm']
        elif kind=='circular_extrusion':
            p=component['parameters']
            for radius in (p['radius_mm'],p['bore_radius_mm']):
                if radius:add('sketch.draw.dimensioned',command='sketch.circle.center',params=dict(center=point([0.,0.],center),radius=radius),dimensions=dict(radius=_mm(radius)))
            bound=0.
        elif kind=='rack':
            if geometry['lower']!=geometry['upper']:
                raise ValueError('SolidCraft native sheared rack accuracy is not qualified by this adapter; no mesh fallback.')
            add('sketch.line',points=[point(p,center) for p in geometry['lower']],closed=True,infer=False)
            bound=geometry['interpolation_bound_mm']
        else:raise ValueError('Unsupported native SolidCraft construction.')
        add('sketch.finish')
        add('solid.extrude',sketch=name+'_profile',distance=_mm(width),operation='new',name=name+'_extrusion',body_name=body)
        coverage.append(dict(component=component['id'],source_interpolation_bound_mm=bound,
            requested_cad_mm=current['cad_tolerance_mm'],native_operation='straight extrusion',
            reader_accuracy='requires independent CAD verification; excludes certified roundoff'))
    add('component.activate',component='root')
    if len(json.dumps(commands,allow_nan=False).encode())>16*1024*1024-4096:
        raise ValueError('Native mathematical CAD transfer exceeds the local protocol budget.')
    return dict(schema='ratiolab.solidcraft-reconstruction/1',group=group,source_sha256=current['source_sha256'],
                commands=commands,bodies=bodies,coverage=coverage)


def insert(client,recipe,*,replace=None):
    """Build and validate everything before replacing an explicitly owned group."""
    compiled=compile(recipe)
    before=client.call('document.inspect')
    if before.get('active_sketch'):raise ValueError('Finish the active CAD sketch before mathematical reconstruction.')
    if replace is not None:
        # Ownership is read from the existing CAD document, never inferred from
        # a similar display name. An unrelated component must not be deleted.
        components=client.execute('component.list')
        rows=components.get('components',components) if isinstance(components,dict) else components
        target=next((r for r in rows if r.get('name')==replace or str(r.get('id'))==str(replace)),None)
        if target is None:raise ValueError('Mathematical CAD group to replace was not found.')
        metadata=client.execute('component.metadata',component=replace)
        values=metadata.get('metadata',{})
        owned=values.get(METADATA_KEY)
        if not isinstance(owned,dict):raise ValueError('Refusing to replace a CAD group without RatioLab recipe ownership.')
        validate(owned.get('recipe'))
    registry=client.call('engine.commands');known={c['id'] for c in registry}
    needed={c['command'] for c in compiled['commands']}
    if replace is not None:needed.add('component.delete')
    if missing:=needed-known:raise ValueError('This SolidCraft version lacks '+', '.join(sorted(missing)))
    checkpoint=client.execute('edit.checkpoint')['checkpoint']
    try:
        result=client.execute_commands(compiled['commands'])
        if result.get('failed'):raise ValueError('Native CAD reconstruction failed: '+str(result['failed']))
        after=client.call('document.inspect');old={str(t.get('id')) for t in before.get('timeline',[])}
        errors=[t for t in after.get('timeline',[]) if str(t.get('id')) not in old and (t.get('error') or t.get('warning'))]
        if errors:raise ValueError('Native CAD timeline errors: '+str(errors)[:1800])
        measured=client.execute('inspect.measure',bodies=compiled['bodies'])
        rows=measured.get('bodies',[])
        if len(rows)!=len(compiled['bodies']) or any(not b.get('closed') or b.get('volume_mm3',0)<=0 for b in rows):
            raise ValueError('Native CAD reconstruction did not produce all closed positive-volume bodies.')
        if replace is not None:client.execute('component.delete',component=replace)
        client.execute('edit.restore_checkpoint',checkpoint=checkpoint,forget=True)
        return dict(group=compiled['group'],source_sha256=compiled['source_sha256'],coverage=compiled['coverage'],measurement=measured)
    except Exception as error:
        try:client.execute('edit.restore_checkpoint',checkpoint=checkpoint)
        except Exception as restore_error:
            from connection import ControlError
            raise ControlError(str(error)+'\nCAD restore not confirmed: '+str(restore_error)) from error
        raise
