# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Reproducible BOM and SolidCraft metadata, without invented commercial codes."""
import csv,hashlib,json,re
from pathlib import Path
from math import hypot
from catalog import BEARINGS


def port_properties(p):
    if not p.port:return {}
    names={'sun':'Sun','carrier':'Carrier','ring':'Ring','eccentric':'Eccentric','output':'Pin flange','wave':'Wave generator','flex':'Flexspline','circular':'Circular spline','cam':'Cam','cage':'Cage','case':'Housing','satellite_upper':'Upper planet','disc':'Orbiting disc'}
    role={'input':'Input','output':'Output','fixed':'Fixed','internal':'Internal member'}.get(p.port['role'],p.port['role'])
    props={'Kinematic member':p.port.get('label',names.get(p.port['member'],p.port['member'])),'Kinematic role':role}
    if 'stage' in p.port:props['Stage']=str(p.port['stage'])
    if 'rpm' in p.port:props['Member speed [rpm]']=format(p.port['rpm'],'.6g')
    if 'orbital_rpm' in p.port:props['Orbital speed [rpm]']=format(p.port['orbital_rpm'],'.6g')
    for key,label in [('force_N','Tension [N]'),('force_per_branch_N','Tension per branch [N]'),('nominal_stroke_mm','Nominal travel [mm]')]:
        if key in p.port:props[label]=format(p.port[key],'.6g')
    if 'axis' in p.port:props['Speed reference']=p.port['axis']
    return props


def part_info(p):
    profiles=[s['outer'] for s in p.stations] if p.stations else [p.outer]
    dims=f'Ø max {2*max(hypot(x,y) for loop in profiles for x,y in loop):.3f} × {p.width:.3f} mm'
    if p.mesh:
        pts=[q for face in p.mesh for loop in face for q in loop]
        dims=' × '.join(f'{max(q[i] for q in pts)-min(q[i] for q in pts):.3f}' for i in range(3))+' mm'
    if p.manufacturing:dims=p.manufacturing['dimensions']
    if p.procurement:return dict(p.procurement,category='PURCHASE')
    if p.catalog_code:
        b=BEARINGS[p.catalog_code]
        return dict(code='NSK '+b.code,description='Open deep groove ball bearing',category='PURCHASE',manufacturer=b.manufacturer,dimensions=f'{b.d:g} × {b.D:g} × {b.B:g} mm',source=b.url)
    category='TO BE DEFINED' if p.name.endswith('_envelope') else 'MANUFACTURE'
    desc=re.sub(r'_\d+(?=_|$)','',p.name)
    # Rotation-invariant signature; handed teeth and hole positions stay distinct.
    shape={'outer':sorted(round(hypot(x,y),6) for x,y in p.outer),'holes':sorted((len(h),round(sum(hypot(x,y) for x,y in h)/len(h),6)) for h in p.holes),'width':p.width,'twist':p.twist,'double':p.double,'gap':p.gap,'description':desc,'machining':p.machining}
    if p.mesh and not p.manufacturing:shape['mesh']=p.mesh
    if p.stations:shape['stations']=[dict(z=s['z'],outer=sorted(round(hypot(x,y),6) for x,y in s['outer']),holes=sorted((len(h),round(sum(hypot(x,y) for x,y in h)/len(h),6)) for h in s['holes'])) for s in p.stations]
    if p.manufacturing:
        shape={'manufacturing':p.manufacturing}
        desc=p.manufacturing['description']
    code=('DEF-' if category=='TO BE DEFINED' else 'SC-')+hashlib.sha256(json.dumps(shape,sort_keys=True).encode()).hexdigest()[:10].upper()
    return dict(code=code,description=desc.replace('_',' '),category=category,manufacturer='',dimensions=dims,source='')


def build(design):
    grouped={}
    indices=getattr(design,'source_indices',list(range(1,len(design.parts)+1)))
    for source_index,p in zip(indices,design.parts):
        info=part_info(p);key=info['code']
        if key not in grouped:grouped[key]=dict(info,quantity=0,positions=[],**({'source_indices':[]} if hasattr(design,'export_scope') else {}))
        grouped[key]['quantity']+=1;grouped[key]['positions'].append(p.name)
        if hasattr(design,'export_scope'):grouped[key]['source_indices'].append(source_index)
    requirements=['Design and dimension axial stops and bearing shoulders.','Define keys, threaded fasteners, seals, lubricant and their codes/quantities for the assembly.','Envelopes are not selected commercial parts; the purchase list is incomplete while TO BE DEFINED items remain.']
    if design.values.get('hardware_mode')=='standard':requirements=['Define materials, manufacturing tolerances, load checks and service life.','Listed machining operations are present in the model; remaining connections and envelopes must be completed.']
    requirements+=design.requirements
    ports=[dict(position=p.name,**({'source_index':i} if hasattr(design,'export_scope') else {}),**p.port) for i,p in zip(indices,design.parts) if p.port]
    machining=[dict(position=p.name,operation=op,**({'source_index':i} if hasattr(design,'export_scope') else {})) for i,p in zip(indices,design.parts) for op in p.machining]
    return dict(format='solidcraft-riduttori-bom/1',family=design.family,parameters=design.values,analysis=design.analysis,**({'export_scope':design.export_scope} if hasattr(design,'export_scope') else {}),ports=ports,rows=list(grouped.values()),machining=machining,requirements=requirements)


def as_text(bom):
    lines=['BILL OF MATERIALS · SOLIDCRAFT REDUCERS',f'Model: {bom["family"]}','Dimensions in mm; strength and service life are not verified.','']
    if bom.get('export_scope'):lines += ['SELECTED COMPONENTS ONLY · not a complete assembly','Source indices: '+', '.join(map(str,bom['export_scope']['source_indices'])),'Calculations describe the source configuration.','']
    for category in ('PURCHASE','MANUFACTURE','TO BE DEFINED'):
        lines.append(category)
        rows=[r for r in bom['rows'] if r['category']==category]
        if not rows:lines.append('  No items.')
        for r in rows:
            lines.append(f'  {r["quantity"]} × {r["code"]} — {r["description"]} — {r["dimensions"]}')
            lines.append('    Positions: '+', '.join(r['positions']))
            if 'source_indices' in r:lines.append('    Source indices: '+', '.join(map(str,r['source_indices'])))
            if r['source']:lines.append('    Catalog: '+r['source'])
        lines.append('')
    if bom.get('machining'):
        lines+=['MACHINING PRESENT IN THE MODEL']
        names={'groove_external':'External retaining ring groove','groove_internal':'Internal retaining ring groove','keyway_shaft':'Shaft keyway','keyway_hub':'Hub keyway','clearance_hole':'Through hole','spacer_dimensions':'Spacer to manufacture'}
        names.update(through_bolt_pair='Two off-axis through holes',bolt_head_counterbore='Recessed bolt head and washer seats')
        for row in bom['machining']:
            op=row['operation'];details=[]
            if op['type']=='profile_indexing':
                lines.append(f'  {row["position"]} · Internal profile orientation {op["angle_deg"]:.6f}° relative to {op["datum"]}')
                continue
            for key,label in [('diameter','Ø'),('width','width'),('b','b'),('depth','depth'),('inner_diameter','Inner Ø'),('outer_diameter','Outer Ø'),('length','length'),('z0','start z'),('z1','end z')]:
                if key in op:details.append(f'{label} {op[key]:.3f}')
            if 'center' in op:details.append('centre '+str(op['center']))
            lines.append('  '+row['position']+' · '+names.get(op['type'],op['type'])+' · '+', '.join(details)+' mm')
        lines.append('')
    if bom.get('analysis',{}).get('kinematics'):
        kinematics=bom['analysis']['kinematics']
        lines.append('INPUTS / OUTPUTS')
        if 'label' in kinematics:
            lines += [kinematics['label'],'']
        else:
            # Differential reports describe coupled member speeds, not one ratio.
            if kinematics.get('kind'):lines.append('Kinematic model: '+kinematics['kind'].replace('_',' '))
            for member,rpm in kinematics.get('rates_rpm',{}).items():
                lines.append(f'  {member.replace("_"," ")}: {rpm:+.6g} rpm')
            if 'prescribed_difference_rpm' in kinematics:
                lines.append(f'Prescribed side speed difference B−A: {kinematics["prescribed_difference_rpm"]:+.6g} rpm')
            if kinematics.get('boundary_condition'):lines.append('Boundary condition: '+kinematics['boundary_condition'])
            for equation in kinematics.get('equations',[]):lines.append('  '+equation)
            if kinematics.get('reference'):lines.append('Speed reference: '+kinematics['reference'])
            if kinematics.get('reference_source'):lines.append('Source: '+kinematics['reference_source'])
            if kinematics.get('reference_section'):lines.append('Source section: '+kinematics['reference_section'])
            lines.append('')
        for q in kinematics.get('stage_results',[]):
            lines.append(f'  Motor: {q["input"]}; output: {q["output"]}; fixed: {q["fixed"]}; ratio {q["signed_ratio"]:+.6g}')
        lines.append('')
    lines+=['TO BE COMPLETED']+['• '+r for r in bom['requirements']]
    return '\n'.join(lines)+'\n'


def export(design,stem):
    stem=Path(stem);stem.parent.mkdir(parents=True,exist_ok=True);bom=build(design)
    Path(str(stem)+'.bom.txt').write_text(as_text(bom),encoding='utf-8')
    Path(str(stem)+'.bom.json').write_text(json.dumps(bom,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    fields=(['source_indices'] if hasattr(design,'export_scope') else [])+['category','code','description','quantity','dimensions','manufacturer','source','standard','positions']
    with Path(str(stem)+'.bom.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for r in bom['rows']:w.writerow({k:('; '.join(r['positions']) if k=='positions' else r.get(k,'')) for k in fields})
    if bom['machining']:
        Path(str(stem)+'.machining.json').write_text(json.dumps(bom['machining'],indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    from engineering import report_text
    Path(str(stem)+'.calculations.json').write_text(json.dumps(design.analysis,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    Path(str(stem)+'.calculations.txt').write_text(('SELECTED COMPONENTS ONLY. Calculations below describe the SOURCE configuration.\n\n' if hasattr(design,'export_scope') else '')+report_text(design),encoding='utf-8')
    return bom
