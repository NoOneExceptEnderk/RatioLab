// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Pack the existing sampled surface into GPU buffers; no resampling or new gear formula.
use crate::{
    precision::{self, Result},
    solid::P3,
    surfaces::{self, Surface},
    wave::Wave,
};
use serde_json::{Value, json};
use std::{collections::HashMap, sync::Arc};

pub(crate) fn sum3(values: P3, compensated: bool) -> f64 {
    let mut hi = 0.;
    let mut lo = 0.;
    for x in values {
        let t = hi + x;
        if compensated {
            lo += if hi.abs() >= x.abs() {
                (hi - t) + x
            } else {
                (x - t) + hi
            };
        }
        hi = t;
    }
    if compensated && lo != 0. && lo.is_finite() {
        hi + lo
    } else {
        hi
    }
}

/// Keep the same little-endian records and finite-value guard, but append a
/// whole block instead of growing the byte vector once for every scalar.
fn append_floats(output: &mut Vec<u8>, values: &[f32], error: &str) -> Result<()> {
    const FLOATS: usize = 2048;
    let mut bytes = [0u8; FLOATS * 4];
    for (index, block) in values.chunks(FLOATS).enumerate() {
        // Packing used to have no internal checkpoint. Bound the new work
        // between checks to at most 1 MiB without changing vertex checks.
        if index % 128 == 0 {
            crate::protocol::control_check()?;
        }
        if block.iter().any(|x| !x.is_finite()) {
            return Err(error.into());
        }
        for (value, destination) in block.iter().zip(bytes.chunks_exact_mut(4)) {
            destination.copy_from_slice(&value.to_le_bytes());
        }
        output.extend_from_slice(&bytes[..block.len() * 4]);
    }
    crate::protocol::control_check()?;
    Ok(())
}
fn norm(a: P3, b: P3, c: P3, compensated: bool) -> P3 {
    let n = crate::solid::cross(crate::solid::sub(b, a), crate::solid::sub(c, a));
    let size = sum3(n.map(|x| x * x), compensated).sqrt();
    let size = if size == 0. { 1. } else { size };
    n.map(|x| x / size)
}
fn point_key(p: P3) -> [u64; 3] {
    p.map(|x| if x == 0. { 0 } else { x.to_bits() })
}
fn f32_point(p: P3) -> P3 {
    p.map(|x| (x as f32) as f64)
}
struct Bounds {
    lo: P3,
    hi: P3,
    count: usize,
}
impl Bounds {
    fn new() -> Self {
        Self {
            lo: [f64::INFINITY; 3],
            hi: [f64::NEG_INFINITY; 3],
            count: 0,
        }
    }
    fn add(&mut self, p: P3) {
        for (i, x) in p.into_iter().enumerate() {
            if x < self.lo[i] {
                self.lo[i] = x;
            }
            if x > self.hi[i] {
                self.hi[i] = x;
            }
        }
        self.count += 1;
    }
}
struct Builder {
    vertices: Vec<f32>,
    compensated: bool,
    bytes_per_float: usize,
}
impl Builder {
    fn vertex(&mut self, p: P3, n: P3) -> Result<()> {
        if self.vertices.len() % 6144 == 0 {
            crate::protocol::control_check()?;
        }
        if (self.vertices.len() + 6) * self.bytes_per_float > crate::buffers::MAX_BYTES {
            return Err("Preview buffer exceeds its resource limit".into());
        }
        let vertex = [p[0], p[1], p[2], n[0], n[1], n[2]].map(|x| x as f32);
        if vertex.iter().any(|x| !x.is_finite()) {
            return Err("Preview coordinate exceeds binary32 range".into());
        }
        self.vertices.extend_from_slice(&vertex);
        Ok(())
    }
    fn triangle(&mut self, a: P3, b: P3, c: P3, n: Option<P3>) -> Result<()> {
        if a == b || b == c || a == c {
            return Ok(());
        }
        let n = n.unwrap_or_else(|| norm(a, b, c, self.compensated));
        for p in [a, b, c] {
            self.vertex(p, n)?;
        }
        Ok(())
    }
    fn position(&self) -> usize {
        self.vertices.len() / 6
    }
}
struct Item {
    surface: Arc<Surface>,
    meta: Value,
    side: [usize; 2],
    edges: [usize; 2],
    caps: Vec<Value>,
}
fn raw_points(item: &Item, mut consume: impl FnMut(P3)) -> Result<()> {
    let p = &item.surface.part;
    if p.mesh.is_empty() {
        for level in item.surface.rings()?.iter() {
            for loop_ in level {
                for q in loop_ {
                    consume(*q);
                }
            }
        }
    } else {
        for face in &p.mesh {
            for loop_ in face {
                for q in loop_ {
                    consume(p.point([q[0], q[1]], q[2], 0.));
                }
            }
        }
    }
    Ok(())
}
fn value<const N: usize>(v: &Value) -> Result<[f64; N]> {
    let rows = v
        .as_array()
        .filter(|a| a.len() == N)
        .ok_or("Invalid preview vector")?;
    let mut result = [0.; N];
    for (i, x) in rows.iter().enumerate() {
        result[i] = match x.as_f64() {
            Some(value) => value,
            None => precision::sampled_number(x)?,
        };
    }
    Ok(result)
}
fn scalar_source(v: &Value) -> (Value, bool) {
    (v.clone(), !v.is_number())
}
fn arithmetic(op: &str, a: (Value, bool), b: (Value, bool)) -> Result<(Value, bool)> {
    if a.1 || b.1 {
        return Ok((json!({"expression":[op,a.0,b.0]}), true));
    }
    let a = a.0.as_f64().ok_or("Invalid ordinary preview operand")?;
    let b = b.0.as_f64().ok_or("Invalid ordinary preview operand")?;
    Ok((
        json!(match op {
            "add" => a + b,
            "sub" => a - b,
            "div" => a / b,
            _ => return Err("Invalid preview operation".into()),
        }),
        false,
    ))
}
// The original comparisons turn -0.0 into +0.0; f64::clamp preserves -0.0.
#[allow(clippy::manual_clamp)]
pub(crate) fn wave_weight(z: f64, w: &Value) -> Result<f64> {
    let length = scalar_source(&w["length"]);
    let diaphragm = scalar_source(&w["diaphragm"]);
    let numerator = arithmetic(
        "sub",
        arithmetic("add", (json!(z), false), length.clone())?,
        diaphragm.clone(),
    )?;
    let denominator = arithmetic("sub", length, diaphragm)?;
    let source = arithmetic("div", numerator, denominator)?.0;
    let weight = precision::sampled_number(&source)?;
    Ok(if weight <= 0. {
        0.
    } else if weight >= 1. {
        1.
    } else {
        weight
    })
}

pub(crate) fn web_packet(original: &Value) -> Result<Vec<u8>> {
    let a = precision::sampled_arguments(original)?;
    let surface = surfaces::get(&a)?;
    let p = &surface.part;
    let limit = a["triangle_limit"]
        .as_u64()
        .filter(|n| *n <= 1_000_000)
        .ok_or("Invalid browser triangle limit")?;
    let compensated = a["compensated_sum"] == true;
    let mut positions = Vec::new();
    let mut normals = Vec::new();
    let mut materials = Vec::new();
    let mut bounds = Bounds::new();
    let mut count = 0u64;
    let raw_wave = original.get("wave").filter(|v| v.is_object());
    let mut references = HashMap::new();
    let mut weights = HashMap::new();
    let wave = if let Some(raw) = raw_wave {
        for (vertex, material) in crate::wave::material_vertex_rows(p, &a["wave"]["metadata"])? {
            references.insert(point_key(vertex), material);
        }
        Some(Wave::new(
            precision::sampled_number(&raw["a"])?,
            precision::sampled_number(&raw["b"])?,
            precision::sampled_number(&raw["rp"])?,
        )?)
    } else {
        None
    };
    let levels = if p.mesh.is_empty() {
        surface.rings()?
    } else {
        Arc::new(Vec::new())
    };
    for face in crate::solid::Faces::new(p, levels)? {
        crate::protocol::control_check()?;
        for triangle in crate::solid::triangulate(&face)? {
            count += 1;
            if count > limit {
                return Err("Mesh exceeds the browser triangle limit.".into());
            }
            let n = crate::solid::cross(
                crate::solid::sub(triangle[1], triangle[0]),
                crate::solid::sub(triangle[2], triangle[0]),
            );
            let length = sum3(n.map(|x| x * x), compensated).sqrt();
            if length <= 1e-15 {
                return Err("Degenerate triangle".into());
            }
            let normal = n.map(|x| x / length);
            for point in triangle {
                bounds.add(point);
                positions.extend(point.map(|x| x as f32));
                normals.extend(normal.map(|x| x as f32));
                if let (Some(wave), Some(raw)) = (&wave, raw_wave) {
                    let key = point_key(point);
                    let material = if let Some(m) = references.get(&key) {
                        *m
                    } else {
                        let weight = if let Some(w) = weights.get(&point[2].to_bits()) {
                            *w
                        } else {
                            let w = wave_weight(point[2], raw)?;
                            weights.insert(point[2].to_bits(), w);
                            w
                        };
                        let material =
                            wave.unmap(point[0] - p.center[0], point[1] - p.center[1], weight)?;
                        references.insert(key, material);
                        material
                    };
                    materials.extend(material.map(|x| x as f32));
                }
            }
        }
    }
    if count == 0 {
        return Err("Component has no mesh".into());
    }
    let meta=serde_json::to_vec(&json!({"format":"ratiolab.web-mesh-buffer/1","triangles":count,
        "position_floats":positions.len(),"normal_floats":normals.len(),"material_floats":materials.len(),"bounds":[bounds.lo,bounds.hi]})).map_err(|e|e.to_string())?;
    let size = 5 + meta.len() + 4 * (positions.len() + normals.len() + materials.len());
    if size > crate::buffers::MAX_BYTES {
        return Err("Web mesh response exceeds its resource limit".into());
    }
    let mut output = Vec::with_capacity(size);
    output.push(0);
    output.extend_from_slice(&(meta.len() as u32).to_le_bytes());
    output.extend_from_slice(&meta);
    append_floats(&mut output, &positions, "Nonfinite browser mesh coordinate")?;
    append_floats(&mut output, &normals, "Nonfinite browser mesh coordinate")?;
    append_floats(&mut output, &materials, "Nonfinite browser mesh coordinate")?;
    Ok(output)
}
pub(crate) fn packet(original: &Value) -> Result<Vec<u8>> {
    let a = precision::sampled_arguments(original)?;
    let descriptions = a["parts"].as_array().ok_or("Preview part array required")?;
    if descriptions.len() > 4096 {
        return Err("Preview part count exceeds its resource limit".into());
    }
    let has_wave = original.get("wave").is_some_and(Value::is_object);
    let mut b = Builder {
        vertices: Vec::new(),
        compensated: a["compensated_sum"] == true,
        // Static zero material attributes can be represented by one explicit
        // constant if the ordinary dense packet would exceed the same budget.
        bytes_per_float: if has_wave { 6 } else { 4 },
    };
    let mut bounds = Bounds::new();
    let mut items = Vec::new();
    for meta in descriptions {
        let surface = surfaces::get(meta)?;
        let p = &surface.part;
        let start = b.position();
        let mut caps = Vec::new();
        let edges = if !p.mesh.is_empty() {
            for face in p.face_iter()? {
                for loop_ in &face {
                    for q in loop_ {
                        bounds.add(*q);
                    }
                    for j in 1..loop_.len().saturating_sub(1) {
                        b.triangle(loop_[0], loop_[j], loop_[j + 1], None)?;
                    }
                }
            }
            [b.position(), 0]
        } else {
            let sections = surface.sections()?;
            let levels = surface.rings()?;
            let first = levels.first().ok_or("Preview has no sections")?;
            for l in first {
                for q in l {
                    bounds.add(*q);
                }
            }
            for pair in levels.windows(2) {
                for (lower, upper) in pair[0].iter().zip(&pair[1]) {
                    for j in 0..lower.len() {
                        let k = (j + 1) % lower.len();
                        let a = lower[j];
                        let c = *upper
                            .get(k)
                            .ok_or("Section vertex correspondence mismatch")?;
                        let d = *upper
                            .get(j)
                            .ok_or("Section vertex correspondence mismatch")?;
                        let q = lower[k];
                        if p.alternate_diagonal {
                            b.triangle(a, q, d, None)?;
                            b.triangle(q, c, d, None)?;
                        } else {
                            b.triangle(a, q, c, None)?;
                            b.triangle(a, c, d, None)?;
                        }
                    }
                    for q in upper {
                        bounds.add(*q);
                    }
                }
            }
            let side_end = b.position();
            let mut edge_loops: Vec<Vec<P3>> = Vec::new();
            for (index, normal) in [(0, "bottom_normal"), (levels.len() - 1, "top_normal")] {
                let (z, angle, outer) = &sections[index];
                let caploops = &levels[index];
                let n = value(&meta[normal])?;
                let begin = b.position();
                for l in caploops {
                    for j in 1..l.len().saturating_sub(1) {
                        b.triangle(l[0], l[j], l[j + 1], Some(n))?;
                    }
                }
                let fan = [begin, b.position() - begin];
                let angle = angle.to_radians();
                let (c, s) = (angle.cos(), angle.sin());
                let rotated: Vec<_> = outer
                    .iter()
                    .map(|q| [q[0] * c - q[1] * s, q[0] * s + q[1] * c])
                    .collect();
                let mut limits = Bounds::new();
                for q in rotated {
                    limits.add([q[0], q[1], 0.]);
                }
                let corners = [
                    [limits.lo[0], limits.lo[1]],
                    [limits.hi[0], limits.lo[1]],
                    [limits.hi[0], limits.hi[1]],
                    [limits.lo[0], limits.hi[1]],
                ]
                .map(|q| p.point(q, *z, 0.));
                let begin = b.position();
                b.triangle(corners[0], corners[1], corners[2], Some(n))?;
                b.triangle(corners[0], corners[2], corners[3], Some(n))?;
                caps.push(json!({"fan":fan,"plane":[begin,6]}));
                edge_loops.extend(caploops.iter().cloned());
            }
            if p.double && p.gap != 0. {
                for (index, ((z, _, _), level)) in sections.iter().zip(levels.iter()).enumerate() {
                    let groove = if p.stations.is_empty() {
                        let h = (p.width - p.gap) / 2.;
                        *z == h || *z == h + p.gap
                    } else {
                        meta["groove_sections"].as_array().is_some_and(|rows| {
                            rows.iter().any(|n| n.as_u64() == Some(index as u64))
                        })
                    };
                    if groove {
                        edge_loops.push(level[0].clone());
                    }
                }
            }
            let begin = b.position();
            for l in &edge_loops {
                for j in 0..l.len() {
                    b.vertex(l[j], [0., 0., 1.])?;
                    b.vertex(l[(j + 1) % l.len()], [0., 0., 1.])?;
                }
            }
            let edges = [begin, b.position() - begin];
            items.push(Item {
                surface,
                meta: meta.clone(),
                side: [start, side_end - start],
                edges,
                caps,
            });
            continue;
        };
        items.push(Item {
            surface,
            meta: meta.clone(),
            side: [start, edges[0] - start],
            edges,
            caps,
        });
    }
    let fallbacks = if bounds.count == 0 {
        let mut result = Vec::new();
        for meta in a["fallback_parts"]
            .as_array()
            .ok_or("Preview fallback parts required")?
        {
            let surface = surfaces::get(meta)?;
            for face in surface.part.face_iter()? {
                for l in face {
                    for p in l {
                        bounds.add(p);
                    }
                }
            }
            result.push(surface);
        }
        result
    } else {
        Vec::new()
    };
    if bounds.count == 0 {
        return Err("The model contains no components".into());
    }
    let frame_explosion = a["frame_explosion"] == true;
    if frame_explosion {
        for item in &items {
            let offset: P3 = value(&item.meta["explosion"])?;
            for i in item.side[0]..item.edges[0] + item.edges[1] {
                bounds.add(std::array::from_fn(|j| {
                    b.vertices[6 * i + j] as f64 + offset[j]
                }));
            }
        }
    }
    let center: P3 = std::array::from_fn(|i| (bounds.lo[i] + bounds.hi[i]) / 2.);
    let mut radius: f64 = 0.;
    let mut distance = |p: P3| {
        let r = sum3(
            std::array::from_fn(|i| {
                let x = p[i] - center[i];
                x * x
            }),
            b.compensated,
        )
        .sqrt();
        if r > radius {
            radius = r;
        }
    };
    for item in &items {
        raw_points(item, &mut distance)?;
    }
    for surface in &fallbacks {
        for face in surface.part.face_iter()? {
            for l in face {
                for p in l {
                    distance(p);
                }
            }
        }
    }
    if frame_explosion {
        for item in &items {
            let offset: P3 = value(&item.meta["explosion"])?;
            for i in item.side[0]..item.edges[0] + item.edges[1] {
                distance(std::array::from_fn(|j| {
                    b.vertices[6 * i + j] as f64 + offset[j]
                }));
            }
        }
    }
    let begin = b.position();
    let span = (bounds.hi[0] - bounds.lo[0])
        .max(bounds.hi[1] - bounds.lo[1])
        .max(10.);
    let mut step = 10f64.powi((span / 8.).log10().floor() as i32);
    if span / step > 16. {
        step *= 2.;
    }
    let extent = (span * 0.7 / step).ceil() * step;
    let ground = bounds.lo[2] - (span * 0.025).max(0.5);
    let n = (extent / step) as i64;
    if n > 10000 || !radius.is_finite() {
        return Err("Invalid preview framing".into());
    }
    for j in -n..=n {
        let off = j as f64 * step;
        for (a, c) in [
            (
                [center[0] + off, center[1] - extent, ground],
                [center[0] + off, center[1] + extent, ground],
            ),
            (
                [center[0] - extent, center[1] + off, ground],
                [center[0] + extent, center[1] + off, ground],
            ),
        ] {
            b.vertex(a, [0., 0., 1.])?;
            b.vertex(c, [0., 0., 1.])?;
        }
    }
    let mut material_count = b.vertices.len() / 2;
    // Static material records are exactly positive binary32 zero. Emit those
    // bytes directly after validation instead of allocating and scanning a
    // second float vector. Prescribed wave values retain their existing path.
    let mut materials = if has_wave {
        vec![0f32; material_count]
    } else {
        Vec::new()
    };
    if has_wave {
        let raw = &original["wave"];
        let w = &a["wave"];
        let wave = Wave::new(
            precision::sampled_number(&w["a"])?,
            precision::sampled_number(&w["b"])?,
            precision::sampled_number(&w["rp"])?,
        )?;
        let mut cache: HashMap<[u64; 3], P3> = HashMap::new();
        let mut weights = HashMap::new();
        for item in &items {
            if item.meta["flexspline"] != true {
                continue;
            }
            let p = &item.surface.part;
            for station in &p.stations {
                for (l, refs) in std::iter::once(station.outer.as_slice())
                    .chain(
                        station
                            .holes
                            .as_deref()
                            .unwrap_or(&[])
                            .iter()
                            .map(Vec::as_slice),
                    )
                    .zip(
                        std::iter::once(station.material_outer.as_deref().unwrap_or(&[])).chain(
                            station
                                .material_holes
                                .as_deref()
                                .unwrap_or(&[])
                                .iter()
                                .map(Vec::as_slice),
                        ),
                    )
                {
                    for (xy, material) in l.iter().zip(refs) {
                        cache.insert(point_key(f32_point(p.point(*xy, station.z, 0.))), *material);
                    }
                }
            }
            for i in item.side[0]..item.edges[0] + item.edges[1] {
                if i % 1024 == 0 {
                    crate::protocol::control_check()?;
                }
                let xyz: P3 = std::array::from_fn(|j| b.vertices[6 * i + j] as f64);
                let key = point_key(xyz);
                let material = if let Some(m) = cache.get(&key) {
                    *m
                } else {
                    let weight = if let Some(weight) = weights.get(&xyz[2].to_bits()) {
                        *weight
                    } else {
                        let weight = wave_weight(xyz[2], raw)?;
                        weights.insert(xyz[2].to_bits(), weight);
                        weight
                    };
                    let material = wave.unmap(xyz[0], xyz[1], weight)?;
                    cache.insert(key, material);
                    material
                };
                for j in 0..3 {
                    materials[3 * i + j] = material[j] as f32;
                }
            }
        }
    }
    let mut meta = json!({"format":"ratiolab.preview-buffer/1","vertex_floats":b.vertices.len(),"material_floats":material_count,
        "scene":{"parts":items.iter().map(|i|json!({"side":i.side,"edges":i.edges,"caps":i.caps,"color":i.meta["color"],
            "source_index":i.meta["source_index"],"explosion":i.meta["explosion"]})).collect::<Vec<_>>(),
            "grid":[begin,b.position()-begin],"center":center,"radius":radius.max(1.),"bounds":[bounds.lo,bounds.hi]}});
    let mut encoded = serde_json::to_vec(&meta).map_err(|e| e.to_string())?;
    if !has_wave
        && 5 + encoded.len() + 4 * (b.vertices.len() + material_count) > crate::buffers::MAX_BYTES
    {
        material_count = 0;
        meta["material_floats"] = json!(0);
        meta["material_fill"] = json!("zero");
        encoded = serde_json::to_vec(&meta).map_err(|e| e.to_string())?;
    }
    let meta = encoded;
    let size = 5 + meta.len() + 4 * (b.vertices.len() + material_count);
    if meta.len() > 16 * 1024 * 1024 || size > crate::buffers::MAX_BYTES {
        return Err("Preview result exceeds its resource limit".into());
    }
    let mut output = Vec::with_capacity(size);
    output.push(0);
    output.extend_from_slice(&(meta.len() as u32).to_le_bytes());
    output.extend_from_slice(&meta);
    append_floats(&mut output, &b.vertices, "Nonfinite preview material")?;
    if has_wave {
        append_floats(&mut output, &materials, "Nonfinite preview material")?;
    } else {
        crate::protocol::control_check()?;
        output.resize(size, 0);
        crate::protocol::control_check()?;
    }
    Ok(output)
}

#[cfg(test)]
mod packing_tests {
    use super::*;

    #[test]
    fn blocked_packing_matches_scalar_bytes_at_every_block_edge() {
        let pattern = [
            0.,
            -0.,
            f32::MIN_POSITIVE,
            f32::from_bits(1),
            f32::MAX,
            -3.75,
        ];
        for count in [0, 1, 2047, 2048, 2049, 262145] {
            let values: Vec<_> = pattern.into_iter().cycle().take(count).collect();
            let expected: Vec<_> = values.iter().flat_map(|x| x.to_le_bytes()).collect();
            let mut actual = Vec::new();
            append_floats(&mut actual, &values, "Nonfinite preview material").unwrap();
            assert_eq!(actual, expected);
        }
    }

    #[test]
    fn blocked_packing_rejects_nonfinite_values_including_later_blocks() {
        for value in [f32::NAN, f32::INFINITY, f32::NEG_INFINITY] {
            for index in [0, 2048, 4097] {
                let mut values = vec![0.; 4098];
                values[index] = value;
                let mut output = Vec::new();
                assert_eq!(
                    append_floats(&mut output, &values, "Nonfinite preview material").unwrap_err(),
                    "Nonfinite preview material"
                );
            }
        }
    }
}
