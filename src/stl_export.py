# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Binary STL in millimetres from the surfaces shared with CAD.

Inner contours are triangulated as real holes; display options (explosion,
section and visibility) do not change the exported components.
"""
from pathlib import Path
import re
import struct
import os
import tempfile
import shutil
from solid_geometry import faces


def cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def inside(p, loop):
    result = False
    for a, b in zip(loop, loop[1:]+loop[:1]):
        if (a[1] > p[1]) != (b[1] > p[1]):
            if p[0] < (b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]:
                result = not result
    return result


def intersects(a, b, c, d):
    if a in (c, d) or b in (c, d):
        return False
    ab_c, ab_d, cd_a, cd_b = cross(a,b,c), cross(a,b,d), cross(c,d,a), cross(c,d,b)
    if ab_c*ab_d < 0 and cd_a*cd_b < 0:
        return True
    def on(p, q, r, area):
        return abs(area) < 1e-12 and min(p[0],q[0])-1e-12 <= r[0] <= max(p[0],q[0])+1e-12 and min(p[1],q[1])-1e-12 <= r[1] <= max(p[1],q[1])+1e-12
    return on(a,b,c,ab_c) or on(a,b,d,ab_d) or on(c,d,a,cd_a) or on(c,d,b,cd_b)


def triangulate(face, check=lambda:None):
    from rust_geometry import call
    check()
    if len(face)==1 and len(face[0])==3:
        return [tuple(face[0])]
    result=call('solid_triangulate',dict(face=face),check=check)
    check()
    return [tuple(tuple(p) for p in triangle) for triangle in result]


def triangles(part,check=None):
    from rust_surfaces import surface
    for rows in surface(part,check).records('solid_triangles_chunk',72,check):
        for i,row in enumerate(struct.iter_unpack('<9d',rows)):
            if check and i%1024==0:check()
            yield (row[:3],row[3:6],row[6:])


def write_stl(path, parts,check=None):
    from rust_surfaces import surface
    path = Path(path)
    descriptor, name = tempfile.mkstemp(prefix='.'+path.name+'-',suffix='.tmp',dir=path.parent)
    os.close(descriptor)
    temporary = Path(name)
    count = 0
    try:
        with temporary.open('wb') as out:
            out.write(b'SolidCraft Riduttori | millimetri | posizione di montaggio'.ljust(80,b' '))
            out.write(struct.pack('<I',0))
            for part in parts:
                for records in surface(part,check).records('solid_stl_chunk',50,check):
                    if check:check()
                    out.write(records)
                    count+=len(records)//50
            out.seek(80);out.write(struct.pack('<I',count))
        if check:check()
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def export(design, stem):
    from geometry_quality import representation
    design = representation(design, 'export')
    stem = Path(stem)
    folder = stem.parent/(stem.name+'.stl-parts')
    assembly = stem.parent/(stem.name+'.stl')
    stem.parent.mkdir(parents=True,exist_ok=True)
    if folder.exists() or folder.is_symlink() or assembly.exists() or assembly.is_symlink():
        raise FileExistsError(f'STL export already exists: {stem}')
    if not design.parts:raise ValueError('No components to export.')
    paths=[];assembly_published=False;folder_reserved=False
    with tempfile.TemporaryDirectory(prefix='.'+stem.name+'-stl-',dir=stem.parent) as temporary:
        staging=Path(temporary);parts_folder=staging/'parts';parts_folder.mkdir()
        for i,part in zip(getattr(design,'source_indices',range(1,len(design.parts)+1)),design.parts):
            name = re.sub(r'[^\w-]+','_',part.name).strip('_') or 'componente'
            path=write_stl(parts_folder/f'{i:03d}-{name}.stl',[part])
            paths.append(folder/path.name)
        staged_assembly=write_stl(staging/'assembly.stl',design.parts)
        if design.quality:
            import json
            from geometry_quality import report
            (parts_folder/'geometry-quality.json').write_text(json.dumps(report(design,'export'),indent=2)+'\n',encoding='utf-8')
        try:
            # Reserve both destinations exclusively. Copying instead of hard
            # links also works on FAT/exFAT export volumes and Windows.
            folder.mkdir();folder_reserved=True
            with assembly.open('xb') as output:
                assembly_published=True
                with staged_assembly.open('rb') as source:shutil.copyfileobj(source,output)
            for path in parts_folder.iterdir():path.rename(folder/path.name)
            folder_reserved=False
        except Exception:
            if assembly_published:assembly.unlink()
            if folder_reserved:shutil.rmtree(folder)
            raise
    return assembly, paths
