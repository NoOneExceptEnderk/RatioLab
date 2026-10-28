"""STL binari in millimetri dalle superfici condivise con il CAD.

I contorni interni vengono triangolati come fori reali; le opzioni di vista
(esploso, sezione, visibilità) non cambiano i componenti esportati.
"""
from math import sqrt
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
    check()
    if len(face) == 1 and len(face[0]) == 3:
        return [tuple(face[0])]
    outer = face[0]
    n = [0.,0.,0.]
    for a,b in zip(outer,outer[1:]+outer[:1]):
        n[0] += (a[1]-b[1])*(a[2]+b[2])
        n[1] += (a[2]-b[2])*(a[0]+b[0])
        n[2] += (a[0]-b[0])*(a[1]+b[1])
    drop = max(range(3), key=lambda i: abs(n[i]))
    axes = [i for i in range(3) if i != drop]
    def xy(p): return (p[axes[0]], p[axes[1]])
    def area(loop): return sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(loop,loop[1:]+loop[:1]))
    points = {xy(p): p for loop in face for p in loop}
    loops = [[xy(p) for p in loop] for loop in face]
    reverse = area(loops[0]) < 0
    loops = [loop if (area(loop)>0)==(j==0) else list(reversed(loop)) for j,loop in enumerate(loops)]
    polygon = loops[0][:]
    holes = sorted(loops[1:], key=lambda loop: max(p[0] for p in loop), reverse=True)
    for hole in holes:
        check()
        h = max(range(len(hole)), key=lambda i: (hole[i][0], -hole[i][1]))
        a = hole[h]
        candidates = sorted(range(len(polygon)), key=lambda i: (polygon[i][0]-a[0])**2+(polygon[i][1]-a[1])**2)
        bridge = None
        for i in candidates:
            check()
            b = polygon[i]
            if a == b: continue
            middle = ((a[0]+b[0])/2,(a[1]+b[1])/2)
            if not inside(middle, loops[0]) or any(inside(middle, loop) for loop in loops[1:]): continue
            if any(intersects(a,b,c,d) for loop in [polygon]+holes for c,d in zip(loop,loop[1:]+loop[:1])): continue
            bridge = i
            break
        if bridge is None: raise ValueError('Could not triangulate an STL hole.')
        polygon = polygon[:bridge+1]+hole[h:]+hole[:h+1]+[polygon[bridge]]+polygon[bridge+1:]
    result = []
    # Ear clipping keeps each original boundary vertex, including collinear ones.
    prev = list(range(-1,len(polygon)-1)); prev[0] = len(polygon)-1
    nxt = list(range(1,len(polygon)+1)); nxt[-1] = 0
    active = set(range(len(polygon)))
    reflex = {i for i in active if cross(polygon[prev[i]],polygon[i],polygon[nxt[i]]) <= 1e-14}
    i = 0; missed = 0
    while len(active)>3:
        check()
        a,b,c = polygon[prev[i]],polygon[i],polygon[nxt[i]]
        ear = i not in reflex
        if ear:
            xmin,xmax = min(a[0],b[0],c[0]),max(a[0],b[0],c[0])
            ymin,ymax = min(a[1],b[1],c[1]),max(a[1],b[1],c[1])
            for j in reflex:
                if j%128==0:check()
                p = polygon[j]
                if p in (a,b,c) or not (xmin<=p[0]<=xmax and ymin<=p[1]<=ymax): continue
                if cross(a,b,p)>=-1e-14 and cross(b,c,p)>=-1e-14 and cross(c,a,p)>=-1e-14:
                    ear = False; break
        if ear:
            result.append((a,b,c)); left,right = prev[i],nxt[i]
            nxt[left]=right;prev[right]=left;active.remove(i);reflex.discard(i)
            for j in (left,right):
                reflex.discard(j)
                if cross(polygon[prev[j]],polygon[j],polygon[nxt[j]])<=1e-14:reflex.add(j)
            i=right;missed=0
        else:
            i=nxt[i];missed+=1
            if missed>len(active):raise ValueError('Cannot triangulate the STL contour: check the geometry.')
    a = next(iter(active));result.append((polygon[a],polygon[nxt[a]],polygon[nxt[nxt[a]]]))
    return [tuple(points[p] for p in (tuple(reversed(tri)) if reverse else tri)) for tri in result]


def triangles(part):
    for face in faces(part):
        yield from triangulate(face)


def write_stl(path, parts):
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
                for a,b,c in triangles(part):
                    u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
                    normal=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
                    length=sqrt(sum(x*x for x in normal))
                    if length<=1e-15:raise ValueError(f'Triangolo STL degenere: {part.name}')
                    out.write(struct.pack('<12fH',*(x/length for x in normal),*a,*b,*c,0));count+=1
            out.seek(80);out.write(struct.pack('<I',count))
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def export(design, stem):
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
