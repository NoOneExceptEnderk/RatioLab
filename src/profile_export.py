# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Unit-preserving SVG/DXF cross-sections, without fitting sampled tooth curves."""
from pathlib import Path
from xml.sax.saxutils import escape
import json
from math import radians

from geometry import profile_sections, section_holes
from cad_export import filename
from export_transaction import directory
from solid_geometry import point


def number(value):
    return format(float(value), '.15g')


def svg(loops, description):
    points = [q for loop in loops for q in loop]
    xmin, xmax = min(q[0] for q in points), max(q[0] for q in points)
    ymin, ymax = min(q[1] for q in points), max(q[1] for q in points)
    margin = max(.1, (xmax-xmin)*.01, (ymax-ymin)*.01)
    width, height = xmax-xmin+2*margin, ymax-ymin+2*margin
    path = ' '.join('M '+' L '.join(number(x)+' '+number(y) for x,y in loop)+' Z' for loop in loops)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{number(width)}mm" height="{number(height)}mm" '
        f'viewBox="{number(xmin-margin)} {number(-ymax-margin)} {number(width)} {number(height)}">\n'
        f'  <title>{escape(description)}</title>\n'
        '  <desc>Sampled closed contours in local section coordinates, 1 unit = 1 mm. '
        'The Y flip preserves the CAD XY orientation. See profiles.json for axial position, rotation and placement.</desc>\n'
        f'  <path transform="scale(1,-1)" fill="#d5e7ef" fill-rule="evenodd" stroke="#152d3a" stroke-width="0.05" d="{path}"/>\n'
        '</svg>\n')


def dxf(loops, description):
    pairs = [(999, description), (0,'SECTION'), (2,'HEADER'),
             (9,'$ACADVER'), (1,'AC1015'), (9,'$INSUNITS'), (70,4),
             (9,'$MEASUREMENT'), (70,1), (9,'$LUNITS'), (70,2), (0,'ENDSEC'),
             (0,'SECTION'), (2,'ENTITIES')]
    for index, loop in enumerate(loops):
        pairs += [(0,'LWPOLYLINE'), (100,'AcDbEntity'), (8,'OUTER' if index==0 else 'HOLES'),
                  (100,'AcDbPolyline'), (90,len(loop)), (70,1), (38,0)]
        for x,y in loop:
            pairs += [(10,number(x)),(20,number(y))]
    pairs += [(0,'ENDSEC'),(0,'EOF')]
    return ''.join(f'{code}\n{value}\n' for code,value in pairs)


def write_files(design, folder):
    if not design.parts:raise ValueError('No components to export.')
    folder = Path(folder)
    output = folder/'profiles'
    output.mkdir()
    components = []
    for index, p in zip(getattr(design,'source_indices',range(1,len(design.parts)+1)),design.parts):
        record = dict(index=index, name=p.name, center_mm=list(p.center), z_offset_mm=p.z,
                      axis_x=p.axis_x, frame=p.frame, profile_geometry=p.profile_metadata, profiles=[])
        components.append(record)
        if p.mesh:
            record.update(kind='mesh without parametric planar sections', extrudible=False)
            continue
        distinct = {}
        sections = profile_sections(p)
        for z, angle, outer in sections:
            loops = [outer]+section_holes(p,z,outer)
            key = tuple(tuple(tuple(q) for q in loop) for loop in loops)
            if key not in distinct:
                distinct[key] = dict(loops=loops, occurrences=[])
            origin=point(p,(0,0),z,radians(angle))
            xp=point(p,(1,0),z,radians(angle));yp=point(p,(0,1),z,radians(angle))
            distinct[key]['occurrences'].append(dict(z_mm=z, rotation_deg=angle,origin_mm=origin,
                x_axis_vector=[xp[i]-origin[i] for i in range(3)],y_axis_vector=[yp[i]-origin[i] for i in range(3)]))
        extrudible = len(distinct)==1 and all(abs(angle)<1e-9 for z,angle,outer in sections)
        record.update(extrudible=extrudible,
                      kind='planar extrusion profile' if extrudible else 'axial sections only; not an extrusion or manufacturing development')
        for section, data in enumerate(distinct.values(), 1):
            stem = filename(index,p.name)+f'-section-{section:03d}'
            description = f'{index:03d} {p.name} | {record["kind"]} | mm'
            # DXF comments use ASCII; names in the UTF-8 JSON/SVG preserve Unicode.
            (output/(stem+'.svg')).write_text(svg(data['loops'],description),encoding='utf-8')
            (output/(stem+'.dxf')).write_text(dxf(data['loops'],description.encode('ascii','replace').decode('ascii')),encoding='ascii')
            record['profiles'].append(dict(svg='profiles/'+stem+'.svg',dxf='profiles/'+stem+'.dxf',
                contours=len(data['loops']), holes=len(data['loops'])-1, occurrences=data['occurrences']))
    metadata = dict(units='mm', coordinates='local XY section before listed rotation and part placement',
        limitations='Closed polylines retain sampled coordinates. No involute, arc or spline fitting. Only profiles labelled planar extrusion describe a whole part extrusion; other files are sections, not a helical development, cutting template, elastic rest shape or conjugate tool envelope. Repeat occurrences share an unrotated local contour. World placement of local (x,y) is origin_mm + x*x_axis_vector + y*y_axis_vector for each occurrence; z_mm is relative to the part z offset.',
        scope=getattr(design,'export_scope',None), components=components)
    (folder/'profiles.json').write_text(json.dumps(metadata,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return metadata


def export(design, target):
    with directory(target) as staging:
        metadata = write_files(design, staging)
    return Path(target), metadata
