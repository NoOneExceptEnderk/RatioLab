// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Prescribed inextensible pitch-line map, not an elasticity calculation.
//! The same eight Fourier coefficients are consumed by the GPU shader.
use crate::{
    precision::Result,
    profiles::{Point, n},
};
use serde_json::{Value, json};
use std::f64::consts::TAU;

#[derive(Clone)]
pub struct Wave {
    a: f64,
    b: f64,
    rp: f64,
    c: [f64; 8],
}
impl Wave {
    pub fn new(a: f64, b: f64, rp: f64) -> Result<Self> {
        if ![a, b, rp].iter().all(|x| x.is_finite())
            || !(0. < b && b <= a && rp > 0.)
            || ((a * a - b * b) / (a * a + b * b)) > 0.25
        {
            return Err("Wave map exceeds its verified ellipse aspect ratio domain.".into());
        }
        thread_local! {static CACHE:std::cell::RefCell<Vec<Wave>>=const {std::cell::RefCell::new(Vec::new())};}
        if let Some(w) = CACHE.with(|cache| {
            cache
                .borrow()
                .iter()
                .find(|w| w.a == a && w.b == b && w.rp == rp)
                .cloned()
        }) {
            return Ok(w);
        }
        let mut c = [0.; 8];
        let count = 2048;
        for j in 0..count {
            let t = TAU * (j as f64 + 0.5) / count as f64;
            let speed = (a * t.sin()).hypot(b * t.cos()) / rp;
            for (k, q) in c.iter_mut().enumerate() {
                let mode = 2. * (k + 1) as f64;
                *q += 2. * speed * (mode * t).cos() / count as f64 / mode;
            }
        }
        let w = Self { a, b, rp, c };
        CACHE.with(|cache| {
            let mut cache = cache.borrow_mut();
            if cache.len() >= 32 {
                cache.remove(0);
            }
            cache.push(w.clone());
        });
        Ok(w)
    }
    pub fn material_angle(&self, t: f64) -> f64 {
        t + self
            .c
            .iter()
            .enumerate()
            .map(|(k, c)| c * (2. * (k + 1) as f64 * t).sin())
            .sum::<f64>()
    }
    pub fn eccentric(&self, material: f64) -> Result<f64> {
        let mut t = material;
        for _ in 0..8 {
            let mut residual = t - material;
            let mut derivative = 1.;
            for (k, c) in self.c.iter().enumerate() {
                let mode = 2. * (k + 1) as f64;
                residual += c * (mode * t).sin();
                derivative += mode * c * (mode * t).cos();
            }
            if derivative.abs() < 1e-12 {
                return Err("Wave material mapping is singular.".into());
            }
            t -= residual / derivative;
        }
        if !t.is_finite() {
            return Err("Nonfinite wave material angle.".into());
        }
        Ok(t)
    }
    pub fn map(
        &self,
        material: f64,
        offset: f64,
        weight: f64,
        flex: f64,
        wave: f64,
    ) -> Result<Point> {
        if ![material, offset, weight, flex, wave]
            .iter()
            .all(|x| x.is_finite())
            || !(0. ..=1.).contains(&weight)
        {
            return Err("Invalid wave material coordinates.".into());
        }
        let u = material + flex;
        let t = self.eccentric(u - wave)?;
        let (mut ex, mut ey) = (self.a * t.cos(), self.b * t.sin());
        let (nx, ny) = (t.cos() / self.a, t.sin() / self.b);
        let length = nx.hypot(ny);
        ex += offset * nx / length;
        ey += offset * ny / length;
        let (c, s) = (wave.cos(), wave.sin());
        Ok([
            (1. - weight) * (self.rp + offset) * u.cos() + weight * (ex * c - ey * s),
            (1. - weight) * (self.rp + offset) * u.sin() + weight * (ex * s + ey * c),
        ])
    }
    pub fn unmap(&self, x: f64, y: f64, w: f64) -> Result<[f64; 3]> {
        let (mut u, mut d) = (y.atan2(x), x.hypot(y) - self.rp);
        for _ in 0..12 {
            let [px, py] = self.map(u, d, w, 0., 0.)?;
            let [qx, qy] = self.map(u + 1e-5, d, w, 0., 0.)?;
            let [nx, ny] = self.map(u, d + 1., w, 0., 0.)?;
            let (tx, ty, nx, ny) = ((qx - px) / 1e-5, (qy - py) / 1e-5, nx - px, ny - py);
            let det = tx * ny - ty * nx;
            if det.abs() < 1e-10 {
                return Err("Wave material mapping is singular.".into());
            }
            let (fx, fy) = (px - x, py - y);
            let du = (fx * ny - fy * nx) / det;
            let dd = (tx * fy - ty * fx) / det;
            u -= du;
            d -= dd;
            if du.abs() < 1e-10 && dd.abs() < 1e-9 {
                break;
            }
        }
        let [px, py] = self.map(u, d, w, 0., 0.)?;
        if (px - x).hypot(py - y) > 1e-5 {
            return Err("Wave material inversion did not converge.".into());
        }
        Ok([u, d, w])
    }
}
pub fn call(op: &str, a: &Value) -> Result<Value> {
    if op == "wave_material_vertices" {
        return material_vertices(a);
    }
    let wave = Wave::new(n(a, "a", 1.)?, n(a, "b", 1.)?, n(a, "rp", 1.)?)?;
    let weight = n(a, "weight", 1.)?;
    match op {
        "wave_coefficients" => Ok(json!(wave.c)),
        "wave_eccentric" => Ok(json!(wave.eccentric(n(a, "material", 0.)?)?)),
        "wave_map" => Ok(json!(wave.map(
            n(a, "material", 0.)?,
            n(a, "offset", 0.)?,
            weight,
            n(a, "flex_angle", 0.)?,
            n(a, "wave_angle", 0.)?
        )?)),
        "wave_unmap" => Ok(json!(wave.unmap(n(a, "x", 0.)?, n(a, "y", 0.)?, weight)?)),
        "wave_map_batch" => {
            let rows = a["points"]
                .as_array()
                .ok_or("Wave material points must be an array")?;
            if rows.len() > 1_000_000 {
                return Err("Wave material vertex limit exceeded".into());
            }
            let flex = n(a, "flex_angle", 0.)?;
            let angle = n(a, "wave_angle", 0.)?;
            let result: Result<Vec<_>> = rows
                .iter()
                .enumerate()
                .map(|(i, row)| {
                    if i % 128 == 0 {
                        crate::protocol::control_check()?;
                    }
                    let q: [f64; 3] =
                        serde_json::from_value(row.clone()).map_err(|e| e.to_string())?;
                    wave.map(q[0], q[1], q[2], flex, angle)
                })
                .collect();
            Ok(json!(result?))
        }
        _ => Err("Unknown wave operation".into()),
    }
}

fn material_vertices(a: &Value) -> Result<Value> {
    let placement = crate::solid::Part::read(&a["part"])?;
    Ok(json!(material_vertex_rows(&placement, &a["metadata"])?))
}

pub(crate) fn material_vertex_rows(
    placement: &crate::solid::Part,
    metadata: &Value,
) -> Result<Vec<([f64; 3], [f64; 3])>> {
    use std::collections::HashMap;
    if metadata["schema"] != "ratiolab.wave-map/1"
        || placement.axis_x
        || !placement.frame.is_empty()
    {
        return Err(
            "Unknown deformation: supported strain-wave material coordinates are required".into(),
        );
    }
    let axes: [f64; 2] = serde_json::from_value(metadata["ellipse_axes_mm"].clone())
        .map_err(|_| "Invalid strain-wave material map dimensions")?;
    let wave = Wave::new(axes[0], axes[1], n(metadata, "pitch_radius_mm", 0.)?)?;
    let center = placement.center;
    let mut indices: HashMap<[u64; 3], usize> = HashMap::new();
    let mut result: Vec<([f64; 3], [f64; 3])> = Vec::new();
    for station in &placement.stations {
        crate::protocol::control_check()?;
        let holes = station
            .holes
            .as_ref()
            .ok_or("Incomplete strain-wave material reference loops")?;
        let material_outer = station
            .material_outer
            .as_ref()
            .ok_or("Incomplete strain-wave material vertex references")?;
        let material_holes = station
            .material_holes
            .as_ref()
            .ok_or("Incomplete strain-wave material reference loops")?;
        if holes.len() != material_holes.len() {
            return Err("Incomplete strain-wave material reference loops".into());
        }
        for (points, materials) in std::iter::once(&station.outer)
            .chain(holes)
            .zip(std::iter::once(material_outer).chain(material_holes))
        {
            if points.len() != materials.len() {
                return Err("Incomplete strain-wave material vertex references".into());
            }
            for (i, (xy, material)) in points.iter().zip(materials).enumerate() {
                if i % 128 == 0 {
                    crate::protocol::control_check()?;
                }
                let vertex = placement.point(*xy, station.z, 0.);
                let [x, y] = wave.map(material[0], material[1], material[2], 0., 0.)?;
                if (x + center[0] - vertex[0]).hypot(y + center[1] - vertex[1]) > 1e-7 {
                    return Err("Strain-wave material references do not reconstruct the nominal shared surface".into());
                }
                let key = vertex.map(|x| if x == 0. { 0 } else { x.to_bits() });
                if let Some(index) = indices.get(&key) {
                    let previous = result[*index].1;
                    if ((previous[0] - material[0] + std::f64::consts::PI).rem_euclid(TAU)
                        - std::f64::consts::PI)
                        .abs()
                        > 1e-8
                        || (previous[1] - material[1]).abs() > 1e-8
                        || (previous[2] - material[2]).abs() > 1e-8
                    {
                        return Err(
                            "Conflicting strain-wave material references at a shared vertex".into(),
                        );
                    }
                } else {
                    indices.insert(key, result.len());
                    result.push((vertex, *material));
                }
            }
        }
    }
    if result.is_empty() {
        return Err("Missing strain-wave material coordinates".into());
    }
    Ok(result)
}
