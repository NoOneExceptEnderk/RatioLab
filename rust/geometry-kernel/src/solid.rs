// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! One shared nominal surface for preview, picking, interference and exports.
use crate::{
    precision::Result,
    profiles::{Point, n, polar, radius, rotate},
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};
use std::f64::consts::PI;
pub type P3 = [f64; 3];
pub type Face = Vec<Vec<P3>>;
pub(crate) type Section = (f64, f64, Vec<Point>);
#[derive(Clone, Serialize, Deserialize)]
pub struct Station {
    pub(crate) z: f64,
    pub(crate) outer: Vec<Point>,
    #[serde(default)]
    pub(crate) holes: Option<Vec<Vec<Point>>>,
    #[serde(default)]
    pub(crate) material_outer: Option<Vec<P3>>,
    #[serde(default)]
    pub(crate) material_holes: Option<Vec<Vec<P3>>>,
}
#[derive(Clone, Serialize, Deserialize)]
pub struct Part {
    pub(crate) outer: Vec<Point>,
    #[serde(default)]
    pub(crate) holes: Vec<Vec<Point>>,
    pub(crate) width: f64,
    #[serde(default)]
    pub(crate) z: f64,
    #[serde(default)]
    pub(crate) center: Point,
    #[serde(default)]
    pub(crate) twist: f64,
    #[serde(default)]
    pub(crate) axis_x: bool,
    #[serde(default)]
    pub(crate) double: bool,
    #[serde(default)]
    pub(crate) gap: f64,
    #[serde(default)]
    pub(crate) core_radius: f64,
    #[serde(default)]
    pub(crate) internal: bool,
    #[serde(default)]
    pub(crate) stations: Vec<Station>,
    #[serde(default)]
    pub(crate) mesh: Vec<Face>,
    #[serde(default)]
    pub(crate) frame: Vec<P3>,
    #[serde(default)]
    pub(crate) alternate_diagonal: bool,
    #[serde(default = "crate::sampling::default_tolerance")]
    pub(crate) surface_tolerance_mm: f64,
}
impl Part {
    pub fn read(a: &Value) -> Result<Self> {
        fn sources(v: &Value) -> bool {
            match v {
                Value::String(_) => true,
                Value::Array(a) => a.iter().any(sources),
                Value::Object(o) => o.contains_key("expression") || o.values().any(sources),
                _ => false,
            }
        }
        fn sampled(v: &Value) -> Result<Value> {
            match v {
                Value::String(_) => Ok(match crate::precision::sampled_number(v) {
                    Ok(n) => json!(n),
                    Err(_) => v.clone(),
                }),
                Value::Object(o) if o.contains_key("expression") => {
                    Ok(json!(crate::precision::sampled_number(v)?))
                }
                Value::Object(o) => Ok(Value::Object(
                    o.iter()
                        .map(|(k, v)| Ok((k.clone(), sampled(v)?)))
                        .collect::<Result<_>>()?,
                )),
                Value::Array(a) => Ok(Value::Array(a.iter().map(sampled).collect::<Result<_>>()?)),
                _ => Ok(v.clone()),
            }
        }
        let normalized;
        let a = if sources(a) {
            normalized = sampled(a)?;
            &normalized
        } else {
            a
        };
        let mut p = Self::deserialize(a).map_err(|e| e.to_string())?;
        if let Some(flat) = a.get("mesh_triangle_points") {
            let values = flat
                .as_array()
                .ok_or("Flat triangle coordinates must be an array")?;
            if values.len() % 3 != 0 || values.len() / 3 > 250000 || !p.mesh.is_empty() {
                return Err("Invalid or ambiguous flat construction triangle count".into());
            }
            let points: Vec<P3> =
                serde_json::from_value(flat.clone()).map_err(|e| e.to_string())?;
            if points.iter().flatten().any(|x| !x.is_finite()) {
                return Err("Nonfinite flat construction coordinate".into());
            }
            p.mesh = points
                .chunks_exact(3)
                .map(|triangle| vec![triangle.to_vec()])
                .collect();
        }
        if p.outer.len() < 3
            || p.width <= 0.
            || !p.surface_tolerance_mm.is_finite()
            || p.surface_tolerance_mm <= 0.
            || ![
                p.width,
                p.z,
                p.twist,
                p.gap,
                p.core_radius,
                p.center[0],
                p.center[1],
            ]
            .iter()
            .all(|v| v.is_finite())
            || (!p.frame.is_empty() && p.frame.len() != 4)
            || p.outer
                .iter()
                .chain(p.holes.iter().flatten())
                .flatten()
                .chain(p.frame.iter().flatten())
                .any(|v| !v.is_finite())
        {
            return Err("Invalid nominal solid geometry".into());
        }
        Ok(p)
    }
    pub(crate) fn point(&self, xy: Point, z: f64, angle: f64) -> P3 {
        let q = rotate(xy, angle);
        let (x, y, z) = (q[0] + self.center[0], q[1] + self.center[1], z + self.z);
        if !self.frame.is_empty() {
            return std::array::from_fn(|i| {
                self.frame[0][i]
                    + x * self.frame[1][i]
                    + y * self.frame[2][i]
                    + z * self.frame[3][i]
            });
        }
        if self.axis_x {
            [z - self.width / 2., y + self.center[1], -x + self.z]
        } else {
            [x, y, z]
        }
    }
    pub(crate) fn sections(&self) -> Result<Vec<Section>> {
        Ok(crate::sampling::build(self)?.sections)
    }
    // Piecewise nominal sweep landmarks. The sampler refines these intervals;
    // it never smooths a groove, changes its endpoints, or invents a reference
    // surface for precomputed station/mesh constructions.
    pub(crate) fn sweep_landmarks(&self) -> Result<Vec<Section>> {
        if !self.stations.is_empty() {
            return Ok(self
                .stations
                .iter()
                .map(|s| (s.z, 0., s.outer.clone()))
                .collect());
        }
        if !self.double {
            return Ok(vec![
                (0., 0., self.outer.clone()),
                (self.width, self.twist, self.outer.clone()),
            ]);
        }
        if self.gap < 0. || self.gap >= self.width {
            return Err("Invalid double-helix groove".into());
        }
        let h = (self.width - self.gap) / 2.;
        let peak = self.twist * h / self.width;
        let shoulder = if self.gap > 0. {
            0.15f64.min(h * 0.08).min(self.gap * 0.2)
        } else {
            0.
        };
        let end = h - shoulder;
        let mut result = vec![
            (0., 0., self.outer.clone()),
            (end, self.twist * end / self.width, self.outer.clone()),
        ];
        if self.gap > 0. {
            let root = self
                .outer
                .iter()
                .map(|q| radius(*q))
                .fold(f64::INFINITY, f64::min);
            let core = if self.internal {
                self.outer.clone()
            } else {
                self.outer
                    .iter()
                    .map(|q| {
                        polar(
                            self.core_radius + 0.001 * (radius(*q) - root),
                            q[1].atan2(q[0]),
                        )
                    })
                    .collect()
            };
            result.push((h, peak, core.clone()));
            result.push((h + self.gap, peak, core));
            let start = h + self.gap + shoulder;
            result.push((
                start,
                peak - self.twist * shoulder / self.width,
                self.outer.clone(),
            ));
        }
        result.push((self.width, 0., self.outer.clone()));
        Ok(result)
    }
    pub(crate) fn holes_at(&self, z: f64, index: usize) -> Result<Vec<Vec<Point>>> {
        if !self.stations.is_empty() {
            return Ok(self
                .stations
                .get(index)
                .ok_or("Invalid station index")?
                .holes
                .clone()
                .unwrap_or_default());
        }
        if !(self.double && self.internal && self.gap > 0.) {
            return Ok(self.holes.clone());
        }
        let h = (self.width - self.gap) / 2.;
        let shoulder = 0.15f64.min(h * 0.08).min(self.gap * 0.2);
        let factor = ((z - h + shoulder) / shoulder)
            .min((h + self.gap + shoulder - z) / shoulder)
            .clamp(0., 1.);
        let first = self.holes.first().ok_or("Internal gear has no hole")?;
        let root = first.iter().map(|q| radius(*q)).fold(0., f64::max);
        let groove = (root + 0.3).min(
            self.outer
                .iter()
                .map(|q| radius(*q))
                .fold(f64::INFINITY, f64::min)
                - 0.5,
        );
        let mut holes = vec![
            first
                .iter()
                .map(|q| {
                    let r = radius(*q);
                    polar(
                        (1. - factor) * r + factor * (groove + 0.001 * (r - root)),
                        q[1].atan2(q[0]),
                    )
                })
                .collect(),
        ];
        holes.extend_from_slice(&self.holes[1..]);
        Ok(holes)
    }
    pub(crate) fn loops(&self, outer: Vec<Point>, z: f64, index: usize) -> Result<Vec<Vec<Point>>> {
        let mut loops = vec![outer];
        loops.extend(self.holes_at(z, index)?);
        for (j, loop_) in loops.iter_mut().enumerate() {
            if self.stations.is_empty() && (self.double || self.twist.abs() > 1e-8) {
                if let Some([x, y, r]) = circle_info(loop_) {
                    let n = loop_
                        .len()
                        .max(96)
                        .max((PI / (1. - 0.002 / r).clamp(-1., 1.).acos()).ceil() as usize);
                    if n > 4096 {
                        return Err("Circle too large for the required precision.".into());
                    }
                    *loop_ = (0..n)
                        .map(|j| {
                            let q = polar(r, 2. * PI * j as f64 / n as f64);
                            [x + q[0], y + q[1]]
                        })
                        .collect();
                }
            }
            let area = area(loop_);
            if (area > 0.) != (j == 0) {
                loop_.reverse();
            }
        }
        Ok(loops)
    }
    pub(crate) fn rings(&self) -> Result<Vec<Vec<Vec<P3>>>> {
        let plan = crate::sampling::build(self)?;
        self.rings_from(plan.sections, &plan.refinements)
    }
    pub(crate) fn rings_from(
        &self,
        sections: impl IntoIterator<Item = Section>,
        refinements: &[Vec<usize>],
    ) -> Result<Vec<Vec<Vec<P3>>>> {
        sections
            .into_iter()
            .enumerate()
            .map(|(index, (z, angle, outer))| {
                crate::protocol::control_check()?;
                Ok(
                    crate::sampling::refine_loops(self.loops(outer, z, index)?, refinements)?
                        .into_iter()
                        .map(|l| {
                            l.iter()
                                .map(|q| self.point(*q, z, angle.to_radians()))
                                .collect()
                        })
                        .collect(),
                )
            })
            .collect()
    }
    pub(crate) fn face_iter(&self) -> Result<Faces<'_>> {
        let levels = if self.mesh.is_empty() {
            std::sync::Arc::new(self.rings()?)
        } else {
            std::sync::Arc::new(Vec::new())
        };
        Faces::new(self, levels)
    }
    pub fn faces(&self) -> Result<Vec<Face>> {
        Ok(self.face_iter()?.collect())
    }
}

#[derive(Default)]
pub(crate) struct FacePosition {
    mesh: usize,
    level: usize,
    loop_index: usize,
    vertex: usize,
    triangle: usize,
    cap: usize,
}
pub(crate) fn validate_levels(p: &Part, levels: &[Vec<Vec<P3>>]) -> Result<()> {
    if !p.mesh.is_empty() {
        return Ok(());
    }
    if levels.is_empty() {
        return Err("Solid has no sections".into());
    }
    let count = levels[1..]
        .iter()
        .flat_map(|l| l.iter())
        .map(|l| 2 * l.len())
        .sum::<usize>()
        + 2;
    if count > 250000 {
        return Err(
            "Solid too detailed: reduce tooth count, width or helix angle (250,000 face limit)."
                .into(),
        );
    }
    for pair in levels.windows(2) {
        if pair[0].len() != pair[1].len() {
            return Err("Section hole topology mismatch".into());
        }
        if pair[0]
            .iter()
            .zip(&pair[1])
            .any(|(a, b)| a.len() != b.len())
        {
            return Err("Section vertex correspondence mismatch".into());
        }
    }
    Ok(())
}
pub(crate) fn next_face(p: &Part, levels: &[Vec<Vec<P3>>], pos: &mut FacePosition) -> Option<Face> {
    if !p.mesh.is_empty() {
        let face = p.mesh.get(pos.mesh)?;
        pos.mesh += 1;
        return Some(
            face.iter()
                .map(|l| l.iter().map(|q| p.point([q[0], q[1]], q[2], 0.)).collect())
                .collect(),
        );
    }
    while pos.level + 1 < levels.len() {
        let lower = &levels[pos.level];
        let upper = &levels[pos.level + 1];
        if pos.loop_index == lower.len() {
            pos.level += 1;
            pos.loop_index = 0;
            continue;
        }
        let a = &lower[pos.loop_index];
        let b = &upper[pos.loop_index];
        if pos.vertex == a.len() {
            pos.loop_index += 1;
            pos.vertex = 0;
            continue;
        }
        let j = pos.vertex;
        let k = (j + 1) % a.len();
        let tri = match (p.alternate_diagonal, pos.triangle) {
            (true, 0) => [a[j], a[k], b[j]],
            (true, _) => [a[k], b[k], b[j]],
            (false, 0) => [a[j], a[k], b[k]],
            (false, _) => [a[j], b[k], b[j]],
        };
        pos.triangle += 1;
        if pos.triangle == 2 {
            pos.triangle = 0;
            pos.vertex += 1;
        }
        let n = cross(sub(tri[1], tri[0]), sub(tri[2], tri[0]));
        if dot(n, n) > 1e-24 {
            return Some(vec![tri.to_vec()]);
        }
    }
    if pos.cap >= 2 {
        return None;
    }
    let loops = if pos.cap == 0 {
        levels[0]
            .iter()
            .map(|l| l.iter().rev().copied().collect::<Vec<_>>())
            .collect::<Vec<_>>()
    } else {
        levels.last()?.clone()
    };
    pos.cap += 1;
    Some(
        loops
            .into_iter()
            .map(|l| {
                l.iter()
                    .enumerate()
                    .filter(|(i, q)| **q != l[(i + l.len() - 1) % l.len()])
                    .map(|(_, q)| *q)
                    .collect()
            })
            .collect(),
    )
}
pub(crate) struct Faces<'a> {
    part: &'a Part,
    levels: std::sync::Arc<Vec<Vec<Vec<P3>>>>,
    position: FacePosition,
}
impl<'a> Faces<'a> {
    pub(crate) fn new(part: &'a Part, levels: std::sync::Arc<Vec<Vec<Vec<P3>>>>) -> Result<Self> {
        validate_levels(part, &levels)?;
        Ok(Self {
            part,
            levels,
            position: FacePosition::default(),
        })
    }
}
impl Iterator for Faces<'_> {
    type Item = Face;
    fn next(&mut self) -> Option<Face> {
        next_face(self.part, &self.levels, &mut self.position)
    }
}

pub fn circle_info(points: &[Point]) -> Option<[f64; 3]> {
    if points.len() < 16 {
        return None;
    }
    let cx = points.iter().map(|q| q[0]).sum::<f64>() / points.len() as f64;
    let cy = points.iter().map(|q| q[1]).sum::<f64>() / points.len() as f64;
    let rs: Vec<_> = points
        .iter()
        .map(|q| (q[0] - cx).hypot(q[1] - cy))
        .collect();
    let r = rs.iter().sum::<f64>() / rs.len() as f64;
    if r > 0.
        && rs.iter().copied().fold(f64::NEG_INFINITY, f64::max)
            - rs.iter().copied().fold(f64::INFINITY, f64::min)
            < 1e-7
    {
        Some([cx, cy, r])
    } else {
        None
    }
}
pub fn sub(a: P3, b: P3) -> P3 {
    std::array::from_fn(|i| a[i] - b[i])
}
pub fn cross(a: P3, b: P3) -> P3 {
    [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]
}
pub fn dot(a: P3, b: P3) -> f64 {
    a.iter().zip(b.iter()).map(|(x, y)| x * y).sum()
}
fn key(p: P3) -> [u64; 3] {
    p.map(|v| if v == 0. { 0 } else { v.to_bits() })
}
fn key2(p: Point) -> [u64; 2] {
    p.map(|v| if v == 0. { 0 } else { v.to_bits() })
}
fn signature(p: &Part) -> Result<Value> {
    signature_faces(p.face_iter()?)
}
pub(crate) fn signature_faces(faces: impl Iterator<Item = Face>) -> Result<Value> {
    let mut face_count = 0;
    let mut edges: BTreeMap<([u64; 3], [u64; 3]), (usize, i32)> = BTreeMap::new();
    let mut vertices = BTreeSet::new();
    let mut volume = 0.;
    let mut min = [f64::INFINITY; 3];
    let mut max = [f64::NEG_INFINITY; 3];
    for face in faces {
        face_count += 1;
        for l in &face {
            if l.len() < 3 {
                return Err("Degenerate shared face".into());
            }
            for i in 0..l.len() {
                let a = l[i];
                let b = l[(i + 1) % l.len()];
                vertices.insert(key(a));
                for j in 0..3 {
                    min[j] = min[j].min(a[j]);
                    max[j] = max[j].max(a[j]);
                }
                let (ka, kb) = (key(a), key(b));
                let (edge, sign) = if ka <= kb {
                    ((ka, kb), 1)
                } else {
                    ((kb, ka), -1)
                };
                let e = edges.entry(edge).or_insert((0, 0));
                e.0 += 1;
                e.1 += sign;
            }
            for pair in l[1..].windows(2) {
                volume += dot(l[0], cross(pair[0], pair[1])) / 6.;
            }
        }
    }
    if edges
        .values()
        .any(|(count, balance)| *count != 2 || *balance != 0)
    {
        return Err("Surface is not closed or has inconsistent orientation.".into());
    }
    if volume <= 0. {
        return Err("Solid volume is not positive.".into());
    }
    Ok(
        json!({"faces":face_count,"vertices":vertices.len(),"volume_mm3":volume,"min":min,"max":max}),
    )
}
fn area(l: &[Point]) -> f64 {
    (0..l.len())
        .map(|i| l[i][0] * l[(i + 1) % l.len()][1] - l[(i + 1) % l.len()][0] * l[i][1])
        .sum()
}
fn cross2(a: Point, b: Point, c: Point) -> f64 {
    (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
}
fn inside(p: Point, l: &[Point]) -> bool {
    let mut result = false;
    for i in 0..l.len() {
        let a = l[i];
        let b = l[(i + 1) % l.len()];
        if (a[1] > p[1]) != (b[1] > p[1])
            && p[0] < (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1]) + a[0]
        {
            result = !result;
        }
    }
    result
}
pub(crate) fn intersects(a: Point, b: Point, c: Point, d: Point) -> bool {
    if [c, d].contains(&a) || [c, d].contains(&b) {
        return false;
    }
    let (ac, ad, ca, cb) = (
        cross2(a, b, c),
        cross2(a, b, d),
        cross2(c, d, a),
        cross2(c, d, b),
    );
    if ac * ad < 0. && ca * cb < 0. {
        return true;
    }
    let on = |p: Point, q: Point, r: Point, area: f64| {
        area.abs() < 1e-12
            && p[0].min(q[0]) - 1e-12 <= r[0]
            && r[0] <= p[0].max(q[0]) + 1e-12
            && p[1].min(q[1]) - 1e-12 <= r[1]
            && r[1] <= p[1].max(q[1]) + 1e-12
    };
    on(a, b, c, ac) || on(a, b, d, ad) || on(c, d, a, ca) || on(c, d, b, cb)
}
pub fn triangulate(face: &Face) -> Result<Vec<[P3; 3]>> {
    crate::protocol::control_check()?;
    if face.is_empty() || face.iter().any(|l| l.len() < 3) {
        return Err("Invalid shared face loops".into());
    }
    if face.len() == 1 && face[0].len() == 3 {
        return Ok(vec![[face[0][0], face[0][1], face[0][2]]]);
    }
    let outer = &face[0];
    let mut n = [0f64; 3];
    for i in 0..outer.len() {
        let a = outer[i];
        let b = outer[(i + 1) % outer.len()];
        n[0] += (a[1] - b[1]) * (a[2] + b[2]);
        n[1] += (a[2] - b[2]) * (a[0] + b[0]);
        n[2] += (a[0] - b[0]) * (a[1] + b[1]);
    }
    let drop = (0..3)
        .max_by(|i, j| n[*i].abs().total_cmp(&n[*j].abs()))
        .unwrap();
    let axes: Vec<_> = (0..3).filter(|i| *i != drop).collect();
    let mut points = BTreeMap::new();
    let mut loops: Vec<Vec<Point>> = face
        .iter()
        .map(|l| {
            l.iter()
                .map(|p| {
                    let xy = [p[axes[0]], p[axes[1]]];
                    points.insert(key2(xy), *p);
                    xy
                })
                .collect()
        })
        .collect();
    let reverse = area(&loops[0]) < 0.;
    for (j, l) in loops.iter_mut().enumerate() {
        if (area(l) > 0.) != (j == 0) {
            l.reverse();
        }
    }
    let mut polygon = loops[0].clone();
    let mut holes = loops[1..].to_vec();
    holes.sort_by(|a, b| {
        b.iter()
            .map(|p| p[0])
            .fold(f64::NEG_INFINITY, f64::max)
            .total_cmp(&a.iter().map(|p| p[0]).fold(f64::NEG_INFINITY, f64::max))
    });
    for hole in &holes {
        crate::protocol::control_check()?;
        let h = (0..hole.len())
            .max_by(|i, j| {
                hole[*i][0]
                    .total_cmp(&hole[*j][0])
                    .then_with(|| hole[*j][1].total_cmp(&hole[*i][1]))
            })
            .unwrap();
        let a = hole[h];
        let mut candidates: Vec<_> = (0..polygon.len()).collect();
        let d = |p: Point| (p[0] - a[0]).powi(2) + (p[1] - a[1]).powi(2);
        candidates.sort_by(|i, j| d(polygon[*i]).total_cmp(&d(polygon[*j])));
        let mut bridge = None;
        for i in candidates {
            crate::protocol::control_check()?;
            let b = polygon[i];
            if a == b {
                continue;
            }
            let middle = [(a[0] + b[0]) / 2., (a[1] + b[1]) / 2.];
            if !inside(middle, &loops[0]) || loops[1..].iter().any(|l| inside(middle, l)) {
                continue;
            }
            if std::iter::once(&polygon)
                .chain(holes.iter())
                .any(|l| (0..l.len()).any(|j| intersects(a, b, l[j], l[(j + 1) % l.len()])))
            {
                continue;
            }
            bridge = Some(i);
            break;
        }
        let i = bridge.ok_or("Could not triangulate an STL hole.")?;
        let mut next = polygon[..=i].to_vec();
        next.extend_from_slice(&hole[h..]);
        next.extend_from_slice(&hole[..=h]);
        next.push(polygon[i]);
        next.extend_from_slice(&polygon[i + 1..]);
        polygon = next;
    }
    let len = polygon.len();
    let mut prev: Vec<_> = (0..len).map(|i| (i + len - 1) % len).collect();
    let mut next: Vec<_> = (0..len).map(|i| (i + 1) % len).collect();
    let mut active: BTreeSet<_> = (0..len).collect();
    let mut reflex: BTreeSet<_> = (0..len)
        .filter(|i| cross2(polygon[prev[*i]], polygon[*i], polygon[next[*i]]) <= 1e-14)
        .collect();
    let (mut i, mut missed) = (0, 0);
    let mut triangles = Vec::new();
    while active.len() > 3 {
        crate::protocol::control_check()?;
        let (a, b, c) = (polygon[prev[i]], polygon[i], polygon[next[i]]);
        let mut ear = !reflex.contains(&i);
        if ear {
            let xmin = a[0].min(b[0]).min(c[0]);
            let xmax = a[0].max(b[0]).max(c[0]);
            let ymin = a[1].min(b[1]).min(c[1]);
            let ymax = a[1].max(b[1]).max(c[1]);
            for j in &reflex {
                let p = polygon[*j];
                if [a, b, c].contains(&p)
                    || !(xmin <= p[0] && p[0] <= xmax && ymin <= p[1] && p[1] <= ymax)
                {
                    continue;
                }
                if cross2(a, b, p) >= -1e-14
                    && cross2(b, c, p) >= -1e-14
                    && cross2(c, a, p) >= -1e-14
                {
                    ear = false;
                    break;
                }
            }
        }
        if ear {
            triangles.push([a, b, c]);
            let (left, right) = (prev[i], next[i]);
            next[left] = right;
            prev[right] = left;
            active.remove(&i);
            reflex.remove(&i);
            for j in [left, right] {
                reflex.remove(&j);
                if cross2(polygon[prev[j]], polygon[j], polygon[next[j]]) <= 1e-14 {
                    reflex.insert(j);
                }
            }
            i = right;
            missed = 0;
        } else {
            i = next[i];
            missed += 1;
            if missed > active.len() {
                return Err("Cannot triangulate the STL contour: check the geometry.".into());
            }
        }
    }
    let a = *active.first().unwrap();
    triangles.push([polygon[a], polygon[next[a]], polygon[next[next[a]]]]);
    Ok(triangles
        .iter()
        .map(|tri| {
            let mut q = tri.map(|p| points[&key2(p)]);
            if reverse {
                q.reverse();
            }
            q
        })
        .collect())
}
pub fn call(op: &str, a: &Value) -> Result<Value> {
    if op == "solid_triangulate" {
        let face: Face = serde_json::from_value(a["face"].clone()).map_err(|e| e.to_string())?;
        return Ok(json!(triangulate(&face)?));
    }
    let p = Part::read(&a["part"])?;
    call_part(op, a, &p)
}

pub(crate) fn call_part(op: &str, a: &Value, p: &Part) -> Result<Value> {
    match op {
        "solid_sampling" => Ok(crate::sampling::build(p)?.report),
        "solid_point" => {
            let xy: Point = serde_json::from_value(a["xy"].clone()).map_err(|e| e.to_string())?;
            Ok(json!(p.point(xy, n(a, "z", 0.)?, n(a, "angle", 0.)?)))
        }
        "solid_section_loops" => {
            let outer: Vec<Point> =
                serde_json::from_value(a["outer"].clone()).map_err(|e| e.to_string())?;
            let index = a["station_index"].as_u64().unwrap_or(0) as usize;
            if !p.stations.is_empty() && index >= p.stations.len() {
                return Err("Invalid station index".into());
            }
            Ok(json!(p.loops(outer, n(a, "z", 0.)?, index)?))
        }
        "solid_sections" => Ok(json!(p.sections()?.into_iter().map(|(z,angle,outer)|{
            let base=outer==p.outer;
            json!({"z":z,"angle":angle,"base":base,"outer":if base{Value::Null}else{json!(outer)}})
        }).collect::<Vec<_>>())),
        "solid_section_holes" => Ok(json!(p.holes_at(
            n(a, "z", 0.)?,
            a["station_index"].as_u64().unwrap_or(0) as usize
        )?)),
        "solid_points" => {
            let rows: Vec<[f64; 4]> =
                serde_json::from_value(a["points"].clone()).map_err(|e| e.to_string())?;
            if rows.len() > 1000000 || rows.iter().flatten().any(|v| !v.is_finite()) {
                return Err("Invalid placement batch".into());
            }
            Ok(json!(
                rows.iter()
                    .map(|q| p.point([q[0], q[1]], q[2], q[3]))
                    .collect::<Vec<_>>()
            ))
        }
        "solid_rings" => Ok(json!(p.rings()?)),
        "solid_faces" => Ok(json!(p.faces()?)),
        "solid_signature" => signature(p),
        "solid_triangles" => {
            let mut result = Vec::new();
            for face in p.face_iter()? {
                result.extend(triangulate(&face)?);
            }
            Ok(json!(result))
        }
        _ => Err("Unknown solid operation".into()),
    }
}

/// Transfer sampled f64 coordinates or packed STL records without a JSON
/// triangle tree or a second complete vector of triangles. Faces are shared
/// with preview/CAD; triangulation order and normals follow the existing STL.
pub fn binary(a: &Value, stl: bool) -> Result<Vec<u8>> {
    let surface = crate::surfaces::get(a)?;
    let part = &surface.part;
    let levels = if part.mesh.is_empty() {
        surface.rings()?
    } else {
        std::sync::Arc::new(Vec::new())
    };
    let faces = Faces::new(part, levels)?;
    let mut output = vec![0; 5];
    let mut count = 0u32;
    for face in faces {
        crate::protocol::control_check()?;
        for triangle in triangulate(&face)? {
            append_triangle(&mut output, triangle, stl, &mut count)?;
        }
    }
    output[1..5].copy_from_slice(&count.to_le_bytes());
    Ok(output)
}

pub(crate) fn append_triangle(
    output: &mut Vec<u8>,
    triangle: [P3; 3],
    stl: bool,
    count: &mut u32,
) -> Result<()> {
    let size = if stl { 50 } else { 72 };
    if output.len() + size > crate::buffers::MAX_BYTES {
        return Err("Binary geometry response exceeds its resource limit".into());
    }
    if stl {
        let [a, b, c] = triangle;
        let u: P3 = std::array::from_fn(|i| b[i] - a[i]);
        let v: P3 = std::array::from_fn(|i| c[i] - a[i]);
        let normal = [
            u[1] * v[2] - u[2] * v[1],
            u[2] * v[0] - u[0] * v[2],
            u[0] * v[1] - u[1] * v[0],
        ];
        let length = normal.iter().map(|x| x * x).sum::<f64>().sqrt();
        if length <= 1e-15 || !length.is_finite() {
            return Err("Degenerate STL triangle".into());
        }
        for x in normal
            .map(|x| x / length)
            .into_iter()
            .chain(triangle.into_iter().flatten())
        {
            let x = x as f32;
            if !x.is_finite() {
                return Err("STL coordinate exceeds binary32 range".into());
            }
            output.extend_from_slice(&x.to_le_bytes());
        }
        output.extend_from_slice(&0u16.to_le_bytes());
    } else {
        for x in triangle.into_iter().flatten() {
            output.extend_from_slice(&x.to_le_bytes());
        }
    }
    *count = count
        .checked_add(1)
        .ok_or("Triangle count exceeds its resource limit")?;
    Ok(())
}
