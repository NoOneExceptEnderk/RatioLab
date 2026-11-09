# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Closed triangle surfaces in mm, with a Rust BVH and distance/witness kernel.

The mesh is the STL/shared faceted surface (analytic STEP circles can differ).
Distances are Euclidean surface distances, never AABB overlap depths.
"""
from rust_geometry import call as _call,call_buffer,backend,control_check


def sub(a,b): return (a[0]-b[0],a[1]-b[1],a[2]-b[2])
def add(a,b): return (a[0]+b[0],a[1]+b[1],a[2]+b[2])
def mul(a,t): return (a[0]*t,a[1]*t,a[2]*t)
def dot(a,b): return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def norm2(a): return dot(a,a)
def bounds(points):
    return tuple(tuple(p) for p in _call('collision_bounds',dict(points=points)))


def box_distance(a,b):
    return _call('collision_box_distance',dict(a=a,b=b))


def point_triangle(p,t):
    return tuple(_call('collision_point_triangle',dict(point=p,triangle=t)))


def segments(a,b,c,d):
    return tuple(tuple(p) for p in _call('collision_segments',dict(a=a,b=b,c=c,d=d)))


def ray_triangle(p,d,t):
    return _call('collision_ray_triangle',dict(point=p,direction=d,triangle=t))


def triangle_distance(a,b):
    distance,p,q=_call('collision_triangle_distance',dict(a=a,b=b))
    return distance,tuple(p),tuple(q)


class Surface:
    """Own a backend-bound Rust mesh/BVH; coordinates are materialized on demand."""
    def __init__(self,triangles,check=lambda:None,validate=True):
        owner,identity=backend()
        self._backend=owner;self._identity=identity;self._handle=None
        self._triangles=tuple(tuple(tuple(q) for q in t) for t in triangles)
        result=_call('collision_create',dict(triangles=self._triangles,validate=validate),check=check,_backend=owner)
        self._adopt(result,check)

    def _adopt(self,result,check):
        from types import SimpleNamespace
        self.check=check;self._handle=result['handle']
        try:
            self.tree=SimpleNamespace(box=tuple(tuple(p) for p in result['bounds']))
            self.thin_triangles=result['thin_triangles']
            self.edge_approximation_mm=result['edge_approximation_mm']
            self.samples=tuple(tuple(p) for p in result['samples'])
            self.triangle_count=result['triangles']
            control_check(check)
        except BaseException:
            self.close()
            raise

    @classmethod
    def from_part(cls,part,check=lambda:None,*,max_triangles=1000000,deformation=None,flex=False):
        from rust_surfaces import surface
        snapshot=surface(part,check)
        parameters=dict(surface=snapshot.parameters(),max_triangles=max_triangles)
        if flex or deformation is not None:
            metadata=part.profile_metadata.get('wave_mapping',{})
            if not isinstance(metadata,dict):raise ValueError('Unknown strain-wave deformation metadata')
            parameters.update(metadata=metadata,deformation=deformation)
        result=cls.__new__(cls)
        result._backend=snapshot._backend;result._identity=snapshot._identity
        result._handle=None;result._triangles=None
        result._adopt(_call('collision_create_surface',parameters,check=check,_backend=result._backend),check)
        return result

    def posed(self,matrix,deformation=None):
        result=type(self).__new__(type(self))
        result._backend=self._backend;result._identity=self._identity
        result._handle=None;result._triangles=None
        result._adopt(_call('collision_pose',dict(handle=self._handle,matrix=matrix,deformation=deformation),
                            check=self.check,_backend=self._backend),self.check)
        return result

    @property
    def triangles(self):
        control_check(self.check)
        if self._triangles is None:
            import struct
            data=call_buffer('collision_triangles',dict(handle=self._handle),72,
                             self.check,_backend=self._backend)
            rows=[]
            for i,row in enumerate(struct.iter_unpack('<9d',data)):
                if i%1024==0:control_check(self.check)
                rows.append((row[:3],row[3:6],row[6:]))
            self._triangles=tuple(rows)
        return self._triangles

    def close(self):
        handle=getattr(self,'_handle',None)
        if handle is not None:
            _call('collision_release',dict(handle=handle),_backend=self._backend)
            self._handle=None

    def __del__(self):
        try:self.close()
        except Exception:pass  # Interpreter/worker shutdown releases its kernel.

    def nearest(self,p):
        gap,point=_call('collision_nearest',dict(handle=self._handle,point=p),check=self.check,_backend=self._backend)
        return gap,tuple(point)

    def contains(self,p,tolerance):
        return _call('collision_contains',dict(handle=self._handle,point=p,tolerance=tolerance),check=self.check,_backend=self._backend)


def distance(a,b):
    if a._identity!=b._identity:raise ValueError('Collision surfaces belong to different Rust backends')
    gap,p,q=_call('collision_distance',dict(a=a._handle,b=b._handle),check=a.check,_backend=a._backend)
    return gap,tuple(p),tuple(q)


def relation(a,b,tolerance):
    if a._identity!=b._identity:raise ValueError('Collision surfaces belong to different Rust backends')
    return _call('collision_relation',dict(a=a._handle,b=b._handle,tolerance=tolerance),check=a.check,_backend=a._backend)
