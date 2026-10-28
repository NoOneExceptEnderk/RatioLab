"""Closed triangle surfaces in mm. Standard-library BVH, no CAD/native runtime.

The mesh is the STL/shared faceted surface (analytic STEP circles can differ).
Distances are Euclidean surface distances, never AABB overlap depths.
"""
from dataclasses import dataclass
from heapq import heappush, heappop
from itertools import count
from math import sqrt, isfinite


def sub(a,b): return (a[0]-b[0],a[1]-b[1],a[2]-b[2])
def add(a,b): return (a[0]+b[0],a[1]+b[1],a[2]+b[2])
def mul(a,t): return (a[0]*t,a[1]*t,a[2]*t)
def dot(a,b): return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def norm2(a): return dot(a,a)
def bounds(points):
    return (tuple(min(q[i] for q in points) for i in range(3)),tuple(max(q[i] for q in points) for i in range(3)))
def box_distance(a,b):
    return sum(max(0,a[0][i]-b[1][i],b[0][i]-a[1][i])**2 for i in range(3))


def point_segment(p,a,b):
    edge=sub(b,a);length=norm2(edge)
    return add(a,mul(edge,max(0,min(1,dot(sub(p,a),edge)/length)))) if length else a


def thin_triangle(t):
    a,b,c=t;ab=sub(b,a);ac=sub(c,a)
    area2=norm2(cross(ab,ac));scale=norm2(ab)*norm2(ac)
    return area2<=1e-24*max(scale,1e-300)


def point_triangle(p,t):
    # Project onto the face plane, then use oriented cross products for the
    # half-plane tests. Dot-product barycentric determinants lose precision
    # for long narrow triangles even well outside the thin-face threshold.
    a,b,c=t
    if thin_triangle(t):
        return min((point_segment(p,a,b),point_segment(p,b,c),point_segment(p,c,a)),key=lambda q:norm2(sub(p,q)))
    n=cross(sub(b,a),sub(c,a));normal2=norm2(n)
    projection=sub(p,mul(n,dot(sub(p,a),n)/normal2))
    if all(dot(cross(sub(y,x),sub(projection,x)),n)>=0 for x,y in ((a,b),(b,c),(c,a))):
        return projection
    return min((point_segment(p,a,b),point_segment(p,b,c),point_segment(p,c,a)),key=lambda q:norm2(sub(p,q)))


def segments(a,b,c,d):
    u=sub(b,a);v=sub(d,c);w=sub(a,c);aa=dot(u,u);bb=dot(u,v);cc=dot(v,v);dd=dot(u,w);ee=dot(v,w)
    if aa==0:return a,point_segment(a,c,d)
    if cc==0:return point_segment(c,a,b),c
    normal=cross(u,v);den=norm2(normal)
    s=max(0,min(1,dot(cross(v,w),normal)/den)) if den>0 else 0
    t=(bb*s+ee)/cc
    if t<0:t=0;s=max(0,min(1,-dd/aa))
    elif t>1:t=1;s=max(0,min(1,(bb-dd)/aa))
    return add(a,mul(u,s)),add(c,mul(v,t))


def ray_triangle(p,d,t):
    a,b,c=t;e1=sub(b,a);e2=sub(c,a);h=cross(d,e2);den=dot(e1,h)
    if abs(den)<=1e-13*sqrt(norm2(e1)*norm2(e2)*norm2(d)):return None
    inv=1/den;s=sub(p,a);u=dot(s,h)*inv
    if u < 0 or u > 1:return None
    q=cross(s,e1);v=dot(d,q)*inv
    if v < 0 or u+v > 1:return None
    return dot(e2,q)*inv


def triangle_distance(a,b):
    best=(float('inf'),a[0],b[0])
    for first,second,reverse in ((a,b,False),(b,a,True)):
        for p,q in zip(first,first[1:]+first[:1]):
            t=ray_triangle(p,sub(q,p),second)
            if t is not None and 0<=t<=1:
                # An intersection cannot bridge a positive AABB lower bound.
                # This also guards roundoff at a boundary of a large triangle.
                if box_distance(bounds(a),bounds(b))>0:continue
                hit=add(p,mul(sub(q,p),t));return (0.,hit,hit)
        for p in first:
            q=point_triangle(p,second);ds=norm2(sub(p,q))
            if ds<best[0]:best=(ds,q,p) if reverse else (ds,p,q)
    for p,q in zip(a,a[1:]+a[:1]):
        for r,s in zip(b,b[1:]+b[:1]):
            x,y=segments(p,q,r,s);ds=norm2(sub(x,y))
            if ds<best[0]:best=(ds,x,y)
    return best


@dataclass
class Node:
    box: tuple
    size: int
    triangles: tuple=()
    left: object=None
    right: object=None


def build(triangles,check=lambda:None):
    check();box=bounds([q for t in triangles for q in t]);n=len(triangles)
    if n<=6:return Node(box,n,tuple(triangles))
    axis=max(range(3),key=lambda i:box[1][i]-box[0][i]);ordered=sorted(triangles,key=lambda t:sum(q[axis] for q in t));half=n//2
    return Node(box,n,left=build(ordered[:half],check),right=build(ordered[half:],check))


class Surface:
    def __init__(self,triangles,check=lambda:None,validate=True):
        self.triangles=tuple(tuple(tuple(q) for q in t) for t in triangles)
        if not self.triangles:raise ValueError('Empty surface')
        self.check=check
        self.thin_triangles=0;self.edge_approximation_mm=0.
        for j,t in enumerate(self.triangles):
            if j%128==0:check()
            if thin_triangle(t):
                self.thin_triangles+=1
                longest2=max(norm2(sub(t[1],t[0])),norm2(sub(t[2],t[0])),norm2(sub(t[2],t[1])),1e-300)
                altitude=sqrt(norm2(cross(sub(t[1],t[0]),sub(t[2],t[0])))/longest2)
                self.edge_approximation_mm=max(self.edge_approximation_mm,altitude)
        if validate:
            edges={};volume=0.;parent={}
            def root(q):
                parent.setdefault(q,q)
                while q!=parent[q]:parent[q]=parent[parent[q]];q=parent[q]
                return q
            for j,t in enumerate(self.triangles):
                if j%128==0:check()
                if any(not isfinite(x) for q in t for x in q):raise ValueError('Nonfinite surface')
                volume+=dot(t[0],cross(t[1],t[2]))/6
                for a,b in zip(t,t[1:]+t[:1]):
                    if a==b:raise ValueError('Zero length edge')
                    key=tuple(sorted((a,b)));n,s=edges.get(key,(0,0));edges[key]=(n+1,s+(1 if a<b else -1))
                    ra,rb=root(a),root(b)
                    if ra!=rb:parent[ra]=rb
            if any(n!=2 or s for n,s in edges.values()):raise ValueError('Surface is not closed and consistently oriented')
            if volume<=0:raise ValueError('Surface has nonpositive signed volume')
            samples={}
            for q in parent:samples.setdefault(root(q),q)
            self.samples=tuple(samples.values())
        else:self.samples=(self.triangles[0][0],)
        self.tree=build(self.triangles,check)

    def nearest(self,p):
        serial=count();heap=[(0,next(serial),self.tree)];best=float('inf');point=None
        while heap:
            self.check();lower,_,node=heappop(heap)
            if lower>best:continue
            if node.triangles:
                for t in node.triangles:
                    q=point_triangle(p,t);ds=norm2(sub(p,q))
                    if ds<best:best=ds;point=q
            else:
                for child in (node.left,node.right):heappush(heap,(box_distance((p,p),child.box),next(serial),child))
        return sqrt(best),point

    def contains(self,p,tolerance):
        if any(p[i]<self.tree.box[0][i]-tolerance or p[i]>self.tree.box[1][i]+tolerance for i in range(3)):return False
        if self.nearest(p)[0]<=tolerance:return None
        # Three nonparallel rays; equal hits on shared edges are counted once.
        votes=[]
        for direction in ((1.,.371390676,.52999894),(.192839,1.,.483928),(.638291,.239182,1.)):
            hits=[];stack=[self.tree]
            while stack:
                self.check();node=stack.pop();low=0.;high=float('inf')
                for i in range(3):
                    a=(node.box[0][i]-p[i])/direction[i];b=(node.box[1][i]-p[i])/direction[i]
                    low=max(low,min(a,b));high=min(high,max(a,b))
                if high<low:continue
                if node.triangles:
                    for t in node.triangles:
                        v=ray_triangle(p,direction,t)
                        if v is not None and v>0:hits.append(v)
                else:stack.extend((node.left,node.right))
            hits.sort();unique=[]
            for v in hits:
                if not unique or abs(v-unique[-1])>1e-8:unique.append(v)
            votes.append(len(unique)%2==1)
        if len(set(votes))>1:raise ValueError('Ambiguous containment rays at this pose')
        return votes[0]


def distance(a,b):
    serial=count();heap=[(box_distance(a.tree.box,b.tree.box),next(serial),a.tree,b.tree)];best=(float('inf'),None,None)
    while heap:
        a.check();lower,_,x,y=heappop(heap)
        if lower>best[0]:continue
        if x.triangles and y.triangles:
            for t in x.triangles:
                for u in y.triangles:
                    result=triangle_distance(t,u)
                    if result[0]<best[0]:best=result
                    if best[0]<=1e-20:return (sqrt(best[0]),best[1],best[2])
        elif not x.triangles and (y.triangles or x.size>=y.size):
            for child in (x.left,x.right):heappush(heap,(box_distance(child.box,y.box),next(serial),child,y))
        else:
            for child in (y.left,y.right):heappush(heap,(box_distance(x.box,child.box),next(serial),x,child))
    return (sqrt(best[0]),best[1],best[2])


def relation(a,b,tolerance):
    gap,p,q=distance(a,b)
    # Disjoint boundaries: one representative per connected boundary suffices.
    if gap>tolerance:
        for source,target in ((a,b),(b,a)):
            for sample in source.samples:
                if target.contains(sample,tolerance):
                    return dict(kind='Containment',distance=gap,point_a=p,point_b=q,depth_lower_bound=None)
        return dict(kind='Separated',distance=gap,point_a=p,point_b=q,depth_lower_bound=None)
    # At crossing boundaries, use strict interior witnesses, not box overlap.
    # Candidate vertices + nearby triangle centroids also catch coincident solids.
    # A bounded inconclusive search is reported as boundary contact / unresolved.
    candidates=[]
    for source,target in ((a,b),(b,a)):
        witness=p if source is a else q
        radius=max(tolerance*4,1e-6)
        stack=[source.tree];local=[]
        while stack:
            source.check();node=stack.pop()
            if box_distance((witness,witness),node.box)>radius*radius:continue
            if node.triangles:local.extend(node.triangles)
            else:stack.extend((node.left,node.right))
        for tri in local[:64]:
            candidates.extend((source,target,x) for x in tri)
            if thin_triangle(tri):continue  # No stable normal for a line/point face.
            n=cross(sub(tri[1],tri[0]),sub(tri[2],tri[0]));n=mul(n,1/sqrt(norm2(n)))
            center=mul(add(add(tri[0],tri[1]),tri[2]),1/3)
            for scale in (4,16,64):candidates.append((source,target,sub(center,mul(n,max(tolerance,1e-7)*scale))))
    cache={}
    def inside(surface,sample):
        key=(id(surface),sample)
        if key not in cache:cache[key]=surface.contains(sample,tolerance)
        return cache[key]
    vertices={id(s):set(q for t in s.triangles for q in t) for s in (a,b)}
    for source,target,sample in candidates:
        source.check()
        if inside(target,sample):
            if sample in vertices[id(source)]:
                return dict(kind='Intersection',distance=gap,point_a=p,point_b=q,depth_lower_bound=None)
            if inside(source,sample):
                depth=min(source.nearest(sample)[0],target.nearest(sample)[0])
                return dict(kind='Intersection',distance=gap,point_a=p,point_b=q,depth_lower_bound=depth)
    return dict(kind='Boundary contact / unresolved',distance=gap,point_a=p,point_b=q,depth_lower_bound=None)
