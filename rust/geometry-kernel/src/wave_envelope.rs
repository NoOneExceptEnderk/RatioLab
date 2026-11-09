// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Complete sampled sweep of the prescribed map; angular-cell enclosure is
//! numerical relief, distinct from physical backlash and elastic deformation.
use crate::{
    precision::Result,
    profiles::{Point, n, polar, radius, rotate},
    wave::Wave,
};
use serde_json::{Value, json};
use std::f64::consts::{PI, TAU};
const CELLS: usize = 128;
const CONVERGENCE: f64 = 0.002;
type Row = (f64, Point);
fn segment(old: Row, new: Row, pitch: f64, step: f64, radial: &mut [f64; CELLS]) {
    let (th0, p) = old;
    let (th1, q) = new;
    let low = th0.min(th1);
    let high = th0.max(th1);
    let (dx, dy) = (q[0] - p[0], q[1] - p[1]);
    let cross = p[0] * q[1] - p[1] * q[0];
    let first = ((low + pitch / 2.) / step).ceil() as i64;
    let last = ((high + pitch / 2.) / step).floor() as i64;
    for index in first..=last {
        let theta = -pitch / 2. + index as f64 * step;
        let den = theta.cos() * dy - theta.sin() * dx;
        if den.abs() <= 1e-14 {
            continue;
        }
        let r = cross / den;
        if r <= 0. {
            continue;
        }
        let j = index.rem_euclid(CELLS as i64) as usize;
        radial[j] = radial[j].max(r);
    }
}
fn sweep(
    reference: &[Point],
    z: usize,
    a: f64,
    b: f64,
    rp: f64,
    nt: usize,
    nq: usize,
) -> Result<([f64; CELLS], [f64; CELLS])> {
    let g = (z + 2) as f64 / z as f64;
    let pitch = TAU / (z + 2) as f64;
    let step = pitch / CELLS as f64;
    let wave = Wave::new(a, b, rp)?;
    let mut refs = Vec::new();
    for p in reference.windows(2) {
        for j in 0..nq {
            let fraction = j as f64 / nq as f64;
            let q = [
                p[0][0] + (p[1][0] - p[0][0]) * fraction,
                p[0][1] + (p[1][1] - p[0][1]) * fraction,
            ];
            refs.push((q[1].atan2(q[0]), radius(q) - rp));
        }
    }
    let q = *reference.last().ok_or("Empty flexspline reference")?;
    refs.push((q[1].atan2(q[0]), radius(q) - rp));
    if refs.len() * (nt + 1) > 1500000 {
        return Err(
            "Strain-wave envelope exceeds its bounded sweep grid; reduce tooth/profile complexity."
                .into(),
        );
    }
    let mut radial = [0f64; CELLS];
    let mut witnesses = Vec::new();
    let mut previous: Option<Vec<Row>> = None;
    for k in 0..=nt {
        let t = -PI / 2. + PI * k as f64 / nt as f64;
        let (c, s) = (t.cos(), t.sin());
        let norm = (c / a).hypot(s / b);
        let (nx, ny) = (c / a / norm, s / b / norm);
        let xi = wave.material_angle(t);
        let mut row: Vec<Row> = Vec::new();
        for (i, (u, d)) in refs.iter().enumerate() {
            let (ex, ey) = (a * c + d * nx, b * s + d * ny);
            let theta = u / g + ey.atan2(ex) - xi / g;
            let r = ex.hypot(ey);
            let current = (theta, polar(r, theta));
            witnesses.push((theta, r));
            if i > 0 {
                segment(row[i - 1], current, pitch, step, &mut radial);
            }
            if let Some(prev) = &previous {
                segment(prev[i], current, pitch, step, &mut radial);
                if i > 0 {
                    segment(prev[i - 1], current, pitch, step, &mut radial);
                    segment(prev[i], row[i - 1], pitch, step, &mut radial);
                }
            }
            row.push(current);
        }
        previous = Some(row);
    }
    if radial.iter().any(|r| *r <= 0.) {
        return Err("Strain-wave sweep does not cover every ring angle.".into());
    }
    let mut scale = [1f64; CELLS];
    let denominator = step.sin();
    for (theta, r) in witnesses {
        let theta = (theta + pitch / 2.).rem_euclid(pitch) - pitch / 2.;
        let j = (((theta + pitch / 2.) / step).floor() as usize).min(CELLS - 1);
        let lo = -pitch / 2. + j as f64 * step;
        let aa = (lo + step - theta).sin() / denominator;
        let bb = (theta - lo).sin() / denominator;
        scale[j] = scale[j].max(r * (aa / radial[j] + bb / radial[(j + 1) % CELLS]));
    }
    let mut enclosed = [0.; CELLS];
    for j in 0..CELLS {
        enclosed[j] = radial[j] * scale[(j + CELLS - 1) % CELLS].max(scale[j]);
    }
    Ok((radial, enclosed))
}
pub fn call(a: &Value) -> Result<Value> {
    let reference: Vec<Point> =
        serde_json::from_value(a["reference"].clone()).map_err(|e| e.to_string())?;
    let z = n(a, "z", 60.)?;
    if z < 3.
        || z.fract() != 0.
        || z > 100000.
        || reference.len() < z as usize
        || reference.len() % z as usize != 0
        || reference.iter().flatten().any(|v| !v.is_finite())
    {
        return Err("Flexspline reference must have identical cyclic tooth topology.".into());
    }
    let z = z as usize;
    let aa = n(a, "a", 1.)?;
    let b = n(a, "b", 1.)?;
    let rp = n(a, "rp", 1.)?;
    let mut tooth = reference[..reference.len() / z].to_vec();
    tooth.push(rotate(reference[0], TAU / z as f64));
    let (mut previous, _) = sweep(&tooth, z, aa, b, rp, 128, 1)?;
    let (mut nt, mut nq) = (256, 2);
    let mut solved = None;
    for _ in 0..4 {
        let (radial, enclosed) = sweep(&tooth, z, aa, b, rp, nt, nq)?;
        let change = previous
            .iter()
            .zip(radial.iter())
            .map(|(x, y)| (x - y).abs())
            .fold(0., f64::max);
        if change <= CONVERGENCE {
            solved = Some((radial, enclosed, change));
            break;
        }
        previous = radial;
        nt *= 2;
        nq *= 2;
    }
    let (radial, enclosed, change) =
        solved.ok_or("Strain-wave swept envelope did not converge within its bounded grid.")?;
    let depth = radial.iter().copied().fold(f64::NEG_INFINITY, f64::max)
        - radial.iter().copied().fold(f64::INFINITY, f64::min);
    if depth < 0.1 * (2. * rp / z as f64) {
        return Err("Prescribed strain-wave sweep leaves no usable tooth engagement.".into());
    }
    let pitch = TAU / (z + 2) as f64;
    let first: Vec<_> = enclosed
        .iter()
        .enumerate()
        .map(|(j, r)| polar(*r, -pitch / 2. + j as f64 * pitch / CELLS as f64))
        .collect();
    let points: Vec<_> = (0..z + 2)
        .flat_map(|k| {
            first
                .iter()
                .map(move |q| rotate(*q, TAU * k as f64 / (z + 2) as f64))
        })
        .collect();
    Ok(
        json!({"points":points,"metadata":{"method":"complete prescribed-map swept outline with angular-cell enclosure",
        "angular_cells_per_tooth":CELLS,"trajectory_intervals":nt,"subdivisions_per_reference_edge":nq,"convergence_threshold_mm":CONVERGENCE,
        "measured_refinement_change_mm":change,"numerical_enclosure_relief_mm":enclosed.iter().zip(radial.iter()).map(|(x,y)|x-y).fold(0.,f64::max),
        "generated_tooth_depth_mm":depth,"reference_wheel_teeth":z+2,"elastic_solution":false}}),
    )
}
