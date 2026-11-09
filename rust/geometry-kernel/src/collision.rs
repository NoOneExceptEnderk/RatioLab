// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Euclidean distances on closed shared facets, not penetration-depth estimates.
//! Mirrors the original bounded witness/ray policy, including thin triangles.
use crate::precision::Result;
use serde_json::{Value, json};
use std::cmp::Ordering;
use std::collections::{BTreeMap, BinaryHeap, HashMap, HashSet};
use std::sync::{Arc, Mutex, OnceLock};
type P = [f64; 3];
type T = [P; 3];
type Bounds = [P; 2];
fn sub(a: P, b: P) -> P {
    std::array::from_fn(|i| a[i] - b[i])
}
fn add(a: P, b: P) -> P {
    std::array::from_fn(|i| a[i] + b[i])
}
fn mul(a: P, t: f64) -> P {
    a.map(|x| x * t)
}
fn dot(a: P, b: P) -> f64 {
    a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
}
fn cross(a: P, b: P) -> P {
    [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]
}
fn norm2(a: P) -> f64 {
    dot(a, a)
}
fn bounds(points: impl Iterator<Item = P>) -> Bounds {
    let mut b = [[f64::INFINITY; 3], [f64::NEG_INFINITY; 3]];
    for p in points {
        for (i, x) in p.into_iter().enumerate() {
            b[0][i] = b[0][i].min(x);
            b[1][i] = b[1][i].max(x);
        }
    }
    b
}
fn box_distance(a: Bounds, b: Bounds) -> f64 {
    (0..3)
        .map(|i| 0_f64.max(a[0][i] - b[1][i]).max(b[0][i] - a[1][i]).powi(2))
        .sum()
}
fn thin(t: T) -> bool {
    let ab = sub(t[1], t[0]);
    let ac = sub(t[2], t[0]);
    norm2(cross(ab, ac)) <= 1e-24 * (norm2(ab) * norm2(ac)).max(1e-300)
}
fn point_segment(p: P, a: P, b: P) -> P {
    let e = sub(b, a);
    let l = norm2(e);
    if l == 0. {
        a
    } else {
        add(a, mul(e, (dot(sub(p, a), e) / l).clamp(0., 1.)))
    }
}
fn point_triangle(p: P, t: T) -> P {
    if !thin(t) {
        let n = cross(sub(t[1], t[0]), sub(t[2], t[0]));
        let q = sub(p, mul(n, dot(sub(p, t[0]), n) / norm2(n)));
        if (0..3).all(|i| dot(cross(sub(t[(i + 1) % 3], t[i]), sub(q, t[i])), n) >= 0.) {
            return q;
        }
    }
    (0..3)
        .map(|i| point_segment(p, t[i], t[(i + 1) % 3]))
        .min_by(|a, b| norm2(sub(p, *a)).total_cmp(&norm2(sub(p, *b))))
        .unwrap()
}
fn segments(a: P, b: P, c: P, d: P) -> [P; 2] {
    let u = sub(b, a);
    let v = sub(d, c);
    let w = sub(a, c);
    let aa = dot(u, u);
    let bb = dot(u, v);
    let cc = dot(v, v);
    let dd = dot(u, w);
    let ee = dot(v, w);
    if aa == 0. {
        return [a, point_segment(a, c, d)];
    }
    if cc == 0. {
        return [point_segment(c, a, b), c];
    }
    let normal = cross(u, v);
    let den = norm2(normal);
    let mut s = if den > 0. {
        (dot(cross(v, w), normal) / den).clamp(0., 1.)
    } else {
        0.
    };
    let mut t = (bb * s + ee) / cc;
    if t < 0. {
        t = 0.;
        s = (-dd / aa).clamp(0., 1.);
    } else if t > 1. {
        t = 1.;
        s = ((bb - dd) / aa).clamp(0., 1.);
    }
    [add(a, mul(u, s)), add(c, mul(v, t))]
}
fn ray_triangle(p: P, d: P, t: T) -> Option<f64> {
    let e1 = sub(t[1], t[0]);
    let e2 = sub(t[2], t[0]);
    let h = cross(d, e2);
    let den = dot(e1, h);
    if den.abs() <= 1e-13 * (norm2(e1) * norm2(e2) * norm2(d)).sqrt() {
        return None;
    }
    let inv = 1. / den;
    let s = sub(p, t[0]);
    let u = dot(s, h) * inv;
    if !(0. ..=1.).contains(&u) {
        return None;
    }
    let q = cross(s, e1);
    let v = dot(d, q) * inv;
    if v < 0. || u + v > 1. {
        return None;
    }
    Some(dot(e2, q) * inv)
}
fn triangle_distance(a: T, b: T) -> (f64, P, P) {
    let mut best = (f64::INFINITY, a[0], b[0]);
    for (first, second, reverse) in [(a, b, false), (b, a, true)] {
        for i in 0..3 {
            let p = first[i];
            let q = first[(i + 1) % 3];
            if let Some(t) = ray_triangle(p, sub(q, p), second) {
                if (0. ..=1.).contains(&t)
                    && box_distance(bounds(a.into_iter()), bounds(b.into_iter())) == 0.
                {
                    let hit = add(p, mul(sub(q, p), t));
                    return (0., hit, hit);
                }
            }
        }
        for p in first {
            let q = point_triangle(p, second);
            let ds = norm2(sub(p, q));
            if ds < best.0 {
                best = if reverse { (ds, q, p) } else { (ds, p, q) };
            }
        }
    }
    for i in 0..3 {
        for j in 0..3 {
            let [x, y] = segments(a[i], a[(i + 1) % 3], b[j], b[(j + 1) % 3]);
            let ds = norm2(sub(x, y));
            if ds < best.0 {
                best = (ds, x, y);
            }
        }
    }
    best
}
struct Work(usize);
impl Work {
    fn tick(&mut self) -> Result<()> {
        self.0 += 1;
        if self.0 > 10_000_000 {
            return Err("Collision refinement resource limit exceeded; result unresolved".into());
        }
        if self.0 % 128 == 1 {
            crate::protocol::control_check()?;
        }
        Ok(())
    }
}
#[derive(Clone)]
struct Node {
    bounds: Bounds,
    size: usize,
    triangles: Arc<[usize]>,
    children: Option<[usize; 2]>,
}
struct Face {
    triangle: T,
    bounds: Bounds,
    plane: Option<(P, P)>,
    slabs: Vec<(P, P, f64, f64)>,
}
impl Face {
    fn new(triangle: T) -> Self {
        let plane = if thin(triangle) {
            None
        } else {
            let n = cross(sub(triangle[1], triangle[0]), sub(triangle[2], triangle[0]));
            Some((triangle[0], mul(n, 1. / norm2(n).sqrt())))
        };
        let mut slabs = Vec::new();
        if let Some((_, n)) = plane {
            for i in 0..3 {
                let anchor = triangle[i];
                let axis = cross(n, sub(triangle[(i + 1) % 3], anchor));
                let axis = mul(axis, 1. / norm2(axis).sqrt());
                let vals = triangle.map(|p| dot(sub(p, anchor), axis));
                slabs.push((
                    anchor,
                    axis,
                    vals.into_iter().fold(f64::INFINITY, f64::min),
                    vals.into_iter().fold(f64::NEG_INFINITY, f64::max),
                ));
            }
        }
        Self {
            triangle,
            bounds: bounds(triangle.into_iter()),
            plane,
            slabs,
        }
    }
}
fn plane_distance(plane: Option<(P, P)>, t: T) -> f64 {
    if let Some((a, n)) = plane {
        let vals = t.map(|p| dot(sub(p, a), n));
        let low = vals.into_iter().fold(f64::INFINITY, f64::min);
        let hi = vals.into_iter().fold(f64::NEG_INFINITY, f64::max);
        0_f64.max(low).max(-hi).powi(2)
    } else {
        0.
    }
}
fn beyond_slabs(slabs: &[(P, P, f64, f64)], t: T, limit: f64) -> bool {
    slabs.iter().any(|(a, n, lo, hi)| {
        let vals = t.map(|p| dot(sub(p, *a), *n));
        let low = vals.into_iter().fold(f64::INFINITY, f64::min);
        let high = vals.into_iter().fold(f64::NEG_INFINITY, f64::max);
        0_f64.max(lo - high).max(low - hi).powi(2) > limit
    })
}
#[derive(Clone, Copy)]
struct Queue {
    lower: f64,
    serial: usize,
    a: usize,
    b: usize,
}
impl PartialEq for Queue {
    fn eq(&self, o: &Self) -> bool {
        self.serial == o.serial && self.lower == o.lower
    }
}
impl Eq for Queue {}
impl PartialOrd for Queue {
    fn partial_cmp(&self, o: &Self) -> Option<Ordering> {
        Some(self.cmp(o))
    }
}
impl Ord for Queue {
    fn cmp(&self, o: &Self) -> Ordering {
        o.lower
            .total_cmp(&self.lower)
            .then_with(|| o.serial.cmp(&self.serial))
    }
}
struct Surface {
    faces: Vec<Face>,
    nodes: Vec<Node>,
    samples: Vec<P>,
    vertices: HashSet<[u64; 3]>,
    thin_count: usize,
    altitude: f64,
    refitted: bool,
    canonical_nodes: OnceLock<Vec<Node>>,
    material: Option<MaterialMap>,
}

struct MaterialMap {
    expected: [f64; 5],
    center: [f64; 2],
    rows: Vec<(P, P)>,
}
impl MaterialMap {
    fn new(part: &crate::solid::Part, metadata: &Value, deformation: &Value) -> Result<Self> {
        let axes: [f64; 2] = serde_json::from_value(metadata["ellipse_axes_mm"].clone())
            .map_err(|_| "Unknown strain-wave deformation metadata")?;
        let number = |key: &str| {
            metadata[key]
                .as_f64()
                .ok_or("Unknown strain-wave deformation metadata")
        };
        let result = Self {
            expected: [
                axes[0],
                axes[1],
                number("pitch_radius_mm")?,
                number("body_length_mm")?,
                number("diaphragm_mm")?,
            ],
            center: part.center,
            rows: crate::wave::material_vertex_rows(part, metadata)?,
        };
        // Keep the original preflight at the requested initial deformation.
        result.map(deformation)?;
        Ok(result)
    }
    fn map(&self, deformation: &Value) -> Result<HashMap<[u64; 3], P>> {
        let pose: [f64; 7] = serde_json::from_value(deformation.clone())
            .map_err(|_| "Unknown or nonfinite strain-wave deformation")?;
        if pose.iter().any(|x| !x.is_finite()) {
            return Err("Unknown or nonfinite strain-wave deformation".into());
        }
        if pose[2..] != self.expected {
            return Err("Strain-wave deformation does not match its validated material map".into());
        }
        if self.rows.len() > 1_000_000 {
            return Err("Wave material vertex limit exceeded".into());
        }
        let wave = crate::wave::Wave::new(pose[2], pose[3], pose[4])?;
        let mut mapped = HashMap::with_capacity(self.rows.len());
        for (i, (vertex, material)) in self.rows.iter().enumerate() {
            if i % 128 == 0 {
                crate::protocol::control_check()?;
            }
            let xy = wave.map(material[0], material[1], material[2], pose[0], pose[1])?;
            mapped.insert(
                key(*vertex),
                [xy[0] + self.center[0], xy[1] + self.center[1], vertex[2]],
            );
        }
        Ok(mapped)
    }
}

struct Query<'a> {
    surface: &'a Surface,
    nodes: &'a [Node],
}
impl std::ops::Deref for Query<'_> {
    type Target = Surface;
    fn deref(&self) -> &Self::Target {
        self.surface
    }
}
fn key(p: P) -> [u64; 3] {
    p.map(|x| if x == 0. { 0 } else { x.to_bits() })
}
fn root(parent: &mut [usize], mut i: usize) -> usize {
    while parent[i] != i {
        parent[i] = parent[parent[i]];
        i = parent[i];
    }
    i
}
impl Surface {
    fn new(triangles: Vec<T>, validate: bool, w: &mut Work) -> Result<Self> {
        Self::with_topology(triangles, validate, None, w)
    }
    fn with_topology(
        triangles: Vec<T>,
        validate: bool,
        template: Option<&Self>,
        w: &mut Work,
    ) -> Result<Self> {
        if triangles.is_empty() {
            return Err("Empty surface".into());
        }
        let mut s = Self {
            faces: Vec::new(),
            nodes: Vec::new(),
            samples: Vec::new(),
            vertices: HashSet::new(),
            thin_count: 0,
            altitude: 0.,
            refitted: template.is_some(),
            canonical_nodes: OnceLock::new(),
            material: None,
        };
        let mut vertices = HashMap::new();
        let mut points = Vec::new();
        let mut parent = Vec::new();
        let mut edges: HashMap<(usize, usize), (usize, i32)> = HashMap::new();
        let mut volume = 0.;
        for t in triangles {
            w.tick()?;
            if t.iter().flatten().any(|x| !x.is_finite()) {
                return Err("Nonfinite surface".into());
            }
            s.vertices.extend(t.map(key));
            if thin(t) {
                s.thin_count += 1;
                let longest = norm2(sub(t[1], t[0]))
                    .max(norm2(sub(t[2], t[0])))
                    .max(norm2(sub(t[2], t[1])))
                    .max(1e-300);
                s.altitude = s
                    .altitude
                    .max((norm2(cross(sub(t[1], t[0]), sub(t[2], t[0]))) / longest).sqrt());
            }
            if validate {
                volume += dot(t[0], cross(t[1], t[2])) / 6.;
                let ids = t.map(|p| {
                    *vertices.entry(key(p)).or_insert_with(|| {
                        let id = points.len();
                        points.push(p);
                        parent.push(id);
                        id
                    })
                });
                for i in 0..3 {
                    let (a, b) = (ids[i], ids[(i + 1) % 3]);
                    if a == b {
                        return Err("Zero length edge".into());
                    }
                    let e = edges.entry((a.min(b), a.max(b))).or_insert((0, 0));
                    e.0 += 1;
                    e.1 += if a < b { 1 } else { -1 };
                    let ra = root(&mut parent, a);
                    let rb = root(&mut parent, b);
                    parent[ra] = rb;
                }
            }
            s.faces.push(Face::new(t));
        }
        if validate {
            if edges.values().any(|(n, sign)| *n != 2 || *sign != 0) {
                return Err("Surface is not closed and consistently oriented".into());
            }
            if volume <= 0. {
                return Err("Surface has nonpositive signed volume".into());
            }
            let mut seen = HashSet::new();
            for (i, p) in points.into_iter().enumerate() {
                if seen.insert(root(&mut parent, i)) {
                    s.samples.push(p);
                }
            }
        } else {
            s.samples.push(s.faces[0].triangle[0]);
        }
        if let Some(template) = template {
            if template.faces.len() != s.faces.len() {
                return Err("Collision topology does not match its source".into());
            }
            s.nodes = template.nodes.clone();
            for i in (0..s.nodes.len()).rev() {
                w.tick()?;
                let node = &s.nodes[i];
                let b = if let Some([left, right]) = node.children {
                    bounds(
                        s.nodes[left]
                            .bounds
                            .into_iter()
                            .chain(s.nodes[right].bounds),
                    )
                } else {
                    bounds(node.triangles.iter().flat_map(|t| s.faces[*t].triangle))
                };
                s.nodes[i].bounds = b;
            }
        } else {
            Self::build(&s.faces, &mut s.nodes, (0..s.faces.len()).collect(), w)?;
        }
        Ok(s)
    }
    fn build(
        faces: &[Face],
        nodes: &mut Vec<Node>,
        mut indices: Vec<usize>,
        w: &mut Work,
    ) -> Result<usize> {
        w.tick()?;
        let b = bounds(indices.iter().flat_map(|i| faces[*i].triangle));
        let n = indices.len();
        let index = nodes.len();
        nodes.push(Node {
            bounds: b,
            size: n,
            triangles: Arc::from([]),
            children: None,
        });
        if n <= 6 {
            nodes[index].triangles = indices.into();
        } else {
            let axis = (1..3).fold(0, |best, i| {
                if b[1][i] - b[0][i] > b[1][best] - b[0][best] {
                    i
                } else {
                    best
                }
            });
            indices.sort_by(|a, c| {
                let sum = |i: usize| faces[i].triangle.iter().map(|p| p[axis]).sum::<f64>();
                sum(*a).total_cmp(&sum(*c))
            });
            let right = indices.split_off(n / 2);
            let children = [
                Self::build(faces, nodes, indices, w)?,
                Self::build(faces, nodes, right, w)?,
            ];
            nodes[index].children = Some(children);
        }
        Ok(index)
    }
    fn query(&self) -> Query<'_> {
        Query {
            surface: self,
            nodes: &self.nodes,
        }
    }
    fn canonical_query(&self, w: &mut Work) -> Result<Query<'_>> {
        if !self.refitted {
            return Ok(self.query());
        }
        if self.canonical_nodes.get().is_none() {
            let mut nodes = Vec::new();
            Self::build(&self.faces, &mut nodes, (0..self.faces.len()).collect(), w)?;
            crate::protocol::control_check()?;
            let _ = self.canonical_nodes.set(nodes);
        }
        Ok(Query {
            surface: self,
            nodes: self
                .canonical_nodes
                .get()
                .ok_or("Collision node construction incomplete")?,
        })
    }
    fn posed(&self, a: &Value, w: &mut Work) -> Result<Self> {
        let matrix: [f64; 16] = parse(a, "matrix")?;
        if self.faces.len() * 3 > 1_000_000 || matrix.iter().any(|x| !x.is_finite()) {
            return Err("Invalid affine coordinates or resource limit".into());
        }
        let mapped = match &self.material {
            Some(material) => Some(material.map(&a["deformation"])?),
            None if !a["deformation"].is_null() => {
                return Err("Unknown strain-wave deformation metadata".into());
            }
            None => None,
        };
        let mut triangles = Vec::with_capacity(self.faces.len());
        for face in &self.faces {
            w.tick()?;
            let mut triangle = face.triangle;
            for vertex in &mut triangle {
                if let Some(mapped) = &mapped {
                    *vertex = *mapped.get(&key(*vertex)).ok_or(
                        "Shared surface contains a vertex without an immutable material reference",
                    )?;
                }
                *vertex = crate::affine::transform(matrix, *vertex);
            }
            triangles.push(triangle);
        }
        // Full world-space closure, orientation, volume, thin-face and finite
        // validation remains active, even for custom/nonrigid/singular matrices.
        Self::with_topology(triangles, true, Some(self), w)
    }
}
impl Query<'_> {
    fn nearest(&self, p: P, w: &mut Work) -> Result<(f64, P)> {
        let mut heap = BinaryHeap::from([Queue {
            lower: 0.,
            serial: 0,
            a: 0,
            b: 0,
        }]);
        let mut serial = 0;
        let mut best = (f64::INFINITY, p);
        while let Some(q) = heap.pop() {
            w.tick()?;
            if q.lower > best.0 {
                continue;
            }
            let node = &self.nodes[q.a];
            if let Some(children) = node.children {
                for child in children {
                    serial += 1;
                    heap.push(Queue {
                        lower: box_distance([p, p], self.nodes[child].bounds),
                        serial,
                        a: child,
                        b: 0,
                    });
                }
            } else {
                for i in node.triangles.iter() {
                    let point = point_triangle(p, self.faces[*i].triangle);
                    let ds = norm2(sub(p, point));
                    if ds < best.0 {
                        best = (ds, point);
                    }
                }
            }
        }
        Ok((best.0.sqrt(), best.1))
    }
    fn contains(&self, p: P, tolerance: f64, w: &mut Work) -> Result<Option<bool>> {
        let b = self.nodes[0].bounds;
        if (0..3).any(|i| p[i] < b[0][i] - tolerance || p[i] > b[1][i] + tolerance) {
            return Ok(Some(false));
        }
        if self.nearest(p, w)?.0 <= tolerance {
            return Ok(None);
        }
        let mut votes = Vec::new();
        for direction in [
            [1., 0.371390676, 0.52999894],
            [0.192839, 1., 0.483928],
            [0.638291, 0.239182, 1.],
        ] {
            let mut hits = Vec::new();
            let mut stack = vec![0];
            while let Some(i) = stack.pop() {
                w.tick()?;
                let node = &self.nodes[i];
                let mut low = 0_f64;
                let mut high = f64::INFINITY;
                for j in 0..3 {
                    let a = (node.bounds[0][j] - p[j]) / direction[j];
                    let b = (node.bounds[1][j] - p[j]) / direction[j];
                    low = low.max(a.min(b));
                    high = high.min(a.max(b));
                }
                if high < low {
                    continue;
                }
                if let Some(children) = node.children {
                    stack.extend(children);
                } else {
                    for t in node.triangles.iter() {
                        if let Some(v) = ray_triangle(p, direction, self.faces[*t].triangle) {
                            if v > 0. {
                                hits.push(v);
                            }
                        }
                    }
                }
            }
            hits.sort_by(f64::total_cmp);
            let mut unique = Vec::new();
            for v in hits {
                if unique.last().is_none_or(|q: &f64| (v - q).abs() > 1e-8) {
                    unique.push(v);
                }
            }
            votes.push(unique.len() % 2 == 1);
        }
        if votes.iter().any(|v| *v != votes[0]) {
            return Err("Ambiguous containment rays at this pose".into());
        }
        Ok(Some(votes[0]))
    }
}
fn distance(a: &Query<'_>, b: &Query<'_>, w: &mut Work) -> Result<(f64, P, P)> {
    let mut serial = 0;
    let mut heap = BinaryHeap::from([Queue {
        lower: box_distance(a.nodes[0].bounds, b.nodes[0].bounds),
        serial,
        a: 0,
        b: 0,
    }]);
    let mut best = (f64::INFINITY, [0.; 3], [0.; 3]);
    while let Some(q) = heap.pop() {
        w.tick()?;
        if q.lower > best.0 {
            continue;
        }
        let x = &a.nodes[q.a];
        let y = &b.nodes[q.b];
        if x.children.is_none() && y.children.is_none() {
            for t in x.triangles.iter() {
                let t = &a.faces[*t];
                if box_distance(t.bounds, y.bounds) > best.0 {
                    continue;
                }
                for u in y.triangles.iter() {
                    w.tick()?;
                    let u = &b.faces[*u];
                    if box_distance(t.bounds, u.bounds) > best.0 {
                        continue;
                    }
                    let guard = best.0 * (1. + 1e-12) + 1e-20;
                    if plane_distance(t.plane, u.triangle) > guard
                        || plane_distance(u.plane, t.triangle) > guard
                        || beyond_slabs(&t.slabs, u.triangle, guard)
                        || beyond_slabs(&u.slabs, t.triangle, guard)
                    {
                        continue;
                    }
                    let result = triangle_distance(t.triangle, u.triangle);
                    if result.0 < best.0 {
                        best = result;
                    }
                    if best.0 <= 1e-20 {
                        return Ok((best.0.sqrt(), best.1, best.2));
                    }
                }
            }
        } else if x.children.is_some() && (y.children.is_none() || x.size >= y.size) {
            for child in x.children.unwrap() {
                serial += 1;
                heap.push(Queue {
                    lower: box_distance(a.nodes[child].bounds, y.bounds),
                    serial,
                    a: child,
                    b: q.b,
                });
            }
        } else {
            for child in y.children.unwrap() {
                serial += 1;
                heap.push(Queue {
                    lower: box_distance(x.bounds, b.nodes[child].bounds),
                    serial,
                    a: q.a,
                    b: child,
                });
            }
        }
    }
    Ok((best.0.sqrt(), best.1, best.2))
}
fn relation(a: &Surface, b: &Surface, tolerance: f64, w: &mut Work) -> Result<Value> {
    let measured = distance(&a.query(), &b.query(), w)?;
    // Bounded contact witnesses depend on traversal order. Retain the original
    // world-sorted hierarchy near contact instead of weakening that policy.
    if measured.0 <= tolerance + 1e-8 {
        return relation_query(
            &a.canonical_query(w)?,
            &b.canonical_query(w)?,
            tolerance,
            None,
            w,
        );
    }
    relation_query(&a.query(), &b.query(), tolerance, Some(measured), w)
}
fn relation_query(
    a: &Query<'_>,
    b: &Query<'_>,
    tolerance: f64,
    measured: Option<(f64, P, P)>,
    w: &mut Work,
) -> Result<Value> {
    let (gap, p, q) = match measured {
        Some(v) => v,
        None => distance(a, b, w)?,
    };
    let result = |kind: &str, depth: Option<f64>| json!({"kind":kind,"distance":gap,"point_a":p,"point_b":q,"depth_lower_bound":depth});
    if gap > tolerance {
        for (source, target) in [(a, b), (b, a)] {
            for sample in &source.samples {
                if target.contains(*sample, tolerance, w)? == Some(true) {
                    return Ok(result("Containment", None));
                }
            }
        }
        return Ok(result("Separated", None));
    }
    let mut candidates = Vec::new();
    for (which, source, witness) in [(0, a, p), (1, b, q)] {
        let radius = (tolerance * 4.).max(1e-6);
        let mut stack = vec![0];
        let mut local = Vec::new();
        while let Some(i) = stack.pop() {
            w.tick()?;
            let node = &source.nodes[i];
            if box_distance([witness, witness], node.bounds) > radius * radius {
                continue;
            }
            if let Some(children) = node.children {
                stack.extend(children);
            } else {
                local.extend(node.triangles.iter().copied());
            }
        }
        for i in local.into_iter().take(64) {
            let tri = source.faces[i].triangle;
            for point in tri {
                candidates.push((which, point));
            }
            if thin(tri) {
                continue;
            }
            let n = cross(sub(tri[1], tri[0]), sub(tri[2], tri[0]));
            let n = mul(n, 1. / norm2(n).sqrt());
            let center = mul(add(add(tri[0], tri[1]), tri[2]), 1. / 3.);
            for scale in [4., 16., 64.] {
                candidates.push((which, sub(center, mul(n, tolerance.max(1e-7) * scale))));
            }
        }
    }
    let mut cache = HashMap::new();
    for (which, sample) in candidates {
        w.tick()?;
        let target_index = 1 - which;
        let source = if which == 0 { a } else { b };
        let target = if which == 0 { b } else { a };
        let mut inside = |s: &Query<'_>, id: usize, w: &mut Work| -> Result<Option<bool>> {
            let k = (id, key(sample));
            if let Some(v) = cache.get(&k) {
                Ok(*v)
            } else {
                let value = s.contains(sample, tolerance, w)?;
                cache.insert(k, value);
                Ok(value)
            }
        };
        if inside(target, target_index, w)? == Some(true) {
            if source.vertices.contains(&key(sample)) {
                return Ok(result("Intersection", None));
            }
            if inside(source, which, w)? == Some(true) {
                let depth = source
                    .nearest(sample, w)?
                    .0
                    .min(target.nearest(sample, w)?.0);
                return Ok(result("Intersection", Some(depth)));
            }
        }
    }
    Ok(result("Boundary contact / unresolved", None))
}
#[derive(Default)]
struct Cache {
    next: u64,
    triangles: usize,
    items: BTreeMap<u64, Arc<Surface>>,
    created: u64,
    refits: u64,
}
fn cache() -> &'static Mutex<Cache> {
    static CACHE: OnceLock<Mutex<Cache>> = OnceLock::new();
    CACHE.get_or_init(|| Mutex::new(Cache::default()))
}
fn get(a: &Value, key: &str) -> Result<Arc<Surface>> {
    let id = a[key].as_u64().ok_or("Missing collision surface handle")?;
    cache()
        .lock()
        .map_err(|_| "Collision cache unavailable")?
        .items
        .get(&id)
        .cloned()
        .ok_or("Collision surface handle has expired".into())
}
fn parse<X: serde::de::DeserializeOwned>(a: &Value, k: &str) -> Result<X> {
    serde_json::from_value(a[k].clone()).map_err(|_| format!("Invalid collision {k}"))
}
fn retain(s: Surface) -> Result<Value> {
    let s = Arc::new(s);
    crate::protocol::control_check()?;
    let mut c = cache().lock().map_err(|_| "Collision cache unavailable")?;
    if c.items.len() >= 512 || c.triangles + s.faces.len() > 2_000_000 {
        return Err("Collision surface cache resource limit exceeded".into());
    }
    c.next = c
        .next
        .checked_add(1)
        .ok_or("Collision handle limit exceeded")?;
    let id = c.next;
    let result = json!({"handle":id,"bounds":s.nodes[0].bounds,"triangles":s.faces.len(),
        "thin_triangles":s.thin_count,"edge_approximation_mm":s.altitude,"samples":s.samples});
    c.triangles += s.faces.len();
    c.created += 1;
    c.refits += u64::from(s.refitted);
    c.items.insert(id, s);
    Ok(result)
}

pub(crate) fn triangles_packet(a: &Value) -> Result<Vec<u8>> {
    crate::protocol::control_check()?;
    let surface = get(a, "handle")?;
    let mut result = Vec::with_capacity(5 + surface.faces.len() * 72);
    result.push(0);
    result.extend_from_slice(&(surface.faces.len() as u32).to_le_bytes());
    for (i, face) in surface.faces.iter().enumerate() {
        if i % 128 == 0 {
            crate::protocol::control_check()?;
        }
        for x in face.triangle.into_iter().flatten() {
            result.extend_from_slice(&x.to_le_bytes());
        }
    }
    Ok(result)
}

pub fn call(op: &str, a: &Value) -> Result<Value> {
    let mut work = Work(0);
    crate::protocol::control_check()?;
    Ok(match op {
        "collision_create" => {
            let triangles: Vec<T> = parse(a, "triangles")?;
            if triangles.len() > 1_000_000 {
                return Err("Collision surface triangle limit exceeded".into());
            }
            retain(Surface::new(
                triangles,
                a["validate"].as_bool().unwrap_or(true),
                &mut work,
            )?)?
        }
        "collision_create_surface" => {
            let shared = crate::surfaces::get(&a["surface"])?;
            let material = if a["metadata"].is_null() {
                None
            } else {
                Some(MaterialMap::new(
                    &shared.part,
                    &a["metadata"],
                    &a["deformation"],
                )?)
            };
            let limit = a["max_triangles"]
                .as_u64()
                .ok_or("Missing assembly triangle limit")?;
            if limit > 1_000_000 {
                return Err("Collision surface triangle limit exceeded".into());
            }
            let triangles = crate::surfaces::collision_triangles(&a["surface"], limit as usize)?;
            let mut s = Surface::new(triangles, true, &mut work)?;
            if let Some(material) = &material {
                let vertices: HashSet<_> = material.rows.iter().map(|(v, _)| key(*v)).collect();
                if s.vertices.iter().any(|v| !vertices.contains(v)) {
                    return Err(
                        "Shared surface contains a vertex without an immutable material reference"
                            .into(),
                    );
                }
            }
            s.material = material;
            retain(s)?
        }
        "collision_pose" => retain(get(a, "handle")?.posed(a, &mut work)?)?,
        "collision_stats" => {
            let c = cache().lock().map_err(|_| "Collision cache unavailable")?;
            json!({"surfaces":c.items.len(),"triangles":c.triangles,"max_surfaces":512,
                "max_triangles":2_000_000,"created":c.created,"refits":c.refits})
        }
        "collision_release" => {
            let id = a["handle"].as_u64().ok_or("Invalid surface handle")?;
            let mut c = cache().lock().map_err(|_| "Collision cache unavailable")?;
            if let Some(s) = c.items.remove(&id) {
                c.triangles -= s.faces.len();
            }
            Value::Null
        }
        "collision_nearest" => json!(
            get(a, "handle")?
                .query()
                .nearest(parse(a, "point")?, &mut work)?
        ),
        "collision_contains" => {
            json!(get(a, "handle")?.query().contains(
                parse(a, "point")?,
                tolerance(a)?,
                &mut work
            )?)
        }
        "collision_distance" => json!(distance(
            &get(a, "a")?.query(),
            &get(a, "b")?.query(),
            &mut work
        )?),
        "collision_relation" => relation(&*get(a, "a")?, &*get(a, "b")?, tolerance(a)?, &mut work)?,
        "collision_point_triangle" => {
            json!(point_triangle(parse(a, "point")?, parse(a, "triangle")?))
        }
        "collision_segments" => json!(segments(
            parse(a, "a")?,
            parse(a, "b")?,
            parse(a, "c")?,
            parse(a, "d")?
        )),
        "collision_triangle_distance" => json!(triangle_distance(parse(a, "a")?, parse(a, "b")?)),
        "collision_ray_triangle" => json!(ray_triangle(
            parse(a, "point")?,
            parse(a, "direction")?,
            parse(a, "triangle")?
        )),
        "collision_bounds" => {
            let points: Vec<P> = parse(a, "points")?;
            if points.is_empty() {
                return Err("Empty point bounds".into());
            }
            json!(bounds(points.into_iter()))
        }
        "collision_box_distance" => json!(box_distance(parse(a, "a")?, parse(a, "b")?)),
        _ => return Err(format!("Unknown collision operation {op}")),
    })
}
fn tolerance(a: &Value) -> Result<f64> {
    let t = a["tolerance"]
        .as_f64()
        .ok_or("Missing boundary tolerance")?;
    if !t.is_finite() || t < 0. {
        Err("Invalid boundary tolerance".into())
    } else {
        Ok(t)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tetrahedra() -> Vec<T> {
        let [a, b, c, d] = [[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]];
        let first = [[a, c, b], [a, b, d], [a, d, c], [b, c, d]];
        first
            .into_iter()
            .chain(first.map(|t| t.map(|p| add(p, [3., 2., 0.]))))
            .collect()
    }

    #[test]
    fn refit_shares_partition_and_canonical_contact_order_matches_rebuild() {
        let original = Surface::new(tetrahedra(), true, &mut Work(0)).unwrap();
        let pose = json!({"matrix":[0.,1.,0.,0.,-1.,0.,0.,0.,0.,0.,1.,0.,4.,-2.,3.,1.]});
        let posed = original.posed(&pose, &mut Work(0)).unwrap();
        assert!(posed.canonical_nodes.get().is_none());
        for (a, b) in original.nodes.iter().zip(&posed.nodes) {
            assert!(Arc::ptr_eq(&a.triangles, &b.triangles));
        }
        assert_eq!(
            posed.nodes[0].bounds,
            bounds(posed.faces.iter().flat_map(|f| f.triangle))
        );
        let rebuilt = Surface::new(
            posed.faces.iter().map(|f| f.triangle).collect(),
            true,
            &mut Work(0),
        )
        .unwrap();
        let canonical = posed.canonical_query(&mut Work(0)).unwrap();
        assert_eq!(canonical.nodes.len(), rebuilt.nodes.len());
        for (a, b) in canonical.nodes.iter().zip(&rebuilt.nodes) {
            assert_eq!(a.bounds, b.bounds);
            assert_eq!(a.triangles, b.triangles);
            assert_eq!(a.children, b.children);
        }
        assert_eq!(posed.samples, rebuilt.samples);
        assert_eq!(posed.vertices, rebuilt.vertices);
    }

    #[test]
    fn refit_retains_singular_orientation_and_work_budget_rejection() {
        let original = Surface::new(tetrahedra(), true, &mut Work(0)).unwrap();
        let zero = json!({"matrix":vec![0.;16]});
        assert!(
            original
                .posed(&zero, &mut Work(0))
                .err()
                .unwrap()
                .contains("Zero length edge")
        );
        let reflection = json!({"matrix":[-1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.]});
        assert!(
            original
                .posed(&reflection, &mut Work(0))
                .err()
                .unwrap()
                .contains("nonpositive signed volume")
        );
        assert!(
            original
                .posed(&reflection, &mut Work(10_000_000))
                .err()
                .unwrap()
                .contains("resource limit")
        );
    }
}
