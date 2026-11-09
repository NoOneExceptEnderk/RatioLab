// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Planar sampled-geometry primitives. All dimensions are millimetres.
use crate::{
    precision::Result,
    profiles::{Point, clean, n, polar, radius},
};
use serde_json::{Value, json};
use std::f64::consts::{PI, TAU};
fn read_points(a: &Value, key: &str) -> Result<Vec<Point>> {
    let q: Vec<Point> = serde_json::from_value(a[key].clone()).map_err(|e| e.to_string())?;
    if q.len() > 1000000 || q.iter().flatten().any(|v| !v.is_finite()) {
        return Err("Invalid sampled planar coordinates".into());
    }
    Ok(q)
}
fn point(a: &Value, key: &str) -> Result<Point> {
    serde_json::from_value(a[key].clone()).map_err(|e| e.to_string())
}
fn inside(points: &[Point], p: Point) -> bool {
    let mut result = false;
    for i in 0..points.len() {
        let a = points[i];
        let b = points[(i + 1) % points.len()];
        if (a[1] > p[1]) != (b[1] > p[1])
            && p[0] < (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1]) + a[0]
        {
            result = !result;
        }
    }
    result
}
pub fn call(op: &str, a: &Value) -> Result<Value> {
    match op {
        "planar_polar" => Ok(json!(polar(n(a, "radius", 1.)?, n(a, "angle", 0.)?))),
        "planar_circle" => Ok(json!(circle_points(a)?)),
        "planar_transform" => {
            let points = read_points(a, "points")?;
            let center = point(a, "center")?;
            let angle = n(a, "angle", 0.)?;
            let (c, s) = (angle.cos(), angle.sin());
            Ok(json!(
                points
                    .iter()
                    .map(|[x, y]| [center[0] + x * c - y * s, center[1] + x * s + y * c])
                    .collect::<Vec<_>>()
            ))
        }
        "planar_circle_info" => Ok(json!(crate::solid::circle_info(&read_points(a, "points")?))),
        "planar_clean" => Ok(json!(clean(read_points(a, "points")?))),
        "planar_contains" => Ok(json!(inside(
            &read_points(a, "points")?,
            point(a, "point")?
        ))),
        "planar_material_point" => {
            let outer = read_points(a, "outer")?;
            let holes: Vec<Vec<Point>> =
                serde_json::from_value(a["holes"].clone()).map_err(|e| e.to_string())?;
            let r = outer.iter().map(|p| radius(*p)).fold(0., f64::max);
            for fraction in [0.98, 0.94, 0.88, 0.75, 0.5, 0.25, 0.] {
                for j in 0..48 {
                    let q = polar(r * fraction, TAU * (j as f64 + 0.217) / 48.);
                    if inside(&outer, q) && !holes.iter().any(|h| inside(h, q)) {
                        return Ok(json!(q));
                    }
                }
            }
            // The legacy radial fractions can miss a real thin annulus (e.g.
            // the circular flexspline wall). Search open scan-line intervals
            // between actual boundaries, retaining the real holes.
            let loops: Vec<_> = std::iter::once(&outer).chain(holes.iter()).collect();
            let mut heights: Vec<_> = loops.iter().flat_map(|l| l.iter().map(|p| p[1])).collect();
            heights.sort_by(f64::total_cmp);
            heights.dedup();
            if let (Some(low), Some(high)) = (heights.first(), heights.last()) {
                let mut candidates = vec![(low + high) / 2.];
                candidates.extend(heights.windows(2).map(|p| (p[0] + p[1]) / 2.));
                let mut work = 0usize;
                for y in candidates {
                    crate::protocol::control_check()?;
                    let mut cuts = Vec::new();
                    for loop_ in &loops {
                        for i in 0..loop_.len() {
                            work += 1;
                            if work > 2_000_000 {
                                return Err(
                                    "Material-point search exceeded its bounded refinement".into(),
                                );
                            }
                            let a = loop_[i];
                            let b = loop_[(i + 1) % loop_.len()];
                            if (a[1] > y) != (b[1] > y) {
                                cuts.push((b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]);
                            }
                        }
                    }
                    cuts.sort_by(f64::total_cmp);
                    cuts.dedup();
                    for pair in cuts.windows(2) {
                        work += loops.iter().map(|l| l.len()).sum::<usize>();
                        if work > 2_000_000 {
                            return Err(
                                "Material-point search exceeded its bounded refinement".into()
                            );
                        }
                        crate::protocol::control_check()?;
                        let x = (pair[0] + pair[1]) / 2.;
                        if x > pair[0]
                            && x < pair[1]
                            && inside(&outer, [x, y])
                            && !holes.iter().any(|h| inside(h, [x, y]))
                        {
                            return Ok(json!([x, y]));
                        }
                    }
                }
            }
            Err("No solid region found in the profile: check the remaining thickness.".into())
        }
        "planar_ellipse_axes" => {
            let r = n(a, "radius", 1.)?;
            let amplitude = n(a, "amplitude", 0.)?;
            let aa = r + amplitude;
            if r <= 0. || amplitude < 0. {
                return Err("Invalid pitch ellipse dimensions".into());
            }
            let perimeter = |b: f64| {
                (0..1024)
                    .map(|j| {
                        let t = TAU * (j as f64 + 0.5) / 1024.;
                        (aa * t.sin()).hypot(b * t.cos())
                    })
                    .sum::<f64>()
                    * TAU
                    / 1024.
            };
            let (mut lo, mut hi) = (r * 0.1, r);
            if perimeter(lo) > TAU * r {
                return Err("Deformation too large for the pitch radius.".into());
            }
            for _ in 0..45 {
                let b = (lo + hi) / 2.;
                if perimeter(b) > TAU * r {
                    hi = b
                } else {
                    lo = b
                }
            }
            Ok(json!([aa, (lo + hi) / 2.]))
        }
        "planar_refine_angles" => {
            let points = read_points(a, "points")?;
            let r = n(a, "radius", 1.)?;
            if r <= 0. {
                return Err("Positive refinement radius required".into());
            }
            let maxstep = 2. * (1. - 0.002 / r).max(0.).acos();
            let mut out = Vec::new();
            for i in 0..points.len() {
                let aa = points[i];
                let b = points[(i + 1) % points.len()];
                let mut delta = (b[1].atan2(b[0]) - aa[1].atan2(aa[0])).rem_euclid(TAU);
                if delta > TAU - 1e-8 {
                    delta = 0.;
                }
                if delta > PI {
                    return Err("Non-monotonic angles in the flexible profile.".into());
                }
                let count = ((delta / maxstep).ceil() as usize).max(1);
                if count > 1000 {
                    return Err("Non-monotonic tooth contour in the cup construction.".into());
                }
                out.extend((0..count).map(|j| {
                    [
                        aa[0] + (b[0] - aa[0]) * j as f64 / count as f64,
                        aa[1] + (b[1] - aa[1]) * j as f64 / count as f64,
                    ]
                }));
            }
            Ok(json!(out))
        }
        _ => Err("Unknown planar geometry operation".into()),
    }
}

pub(crate) fn circle_points(a: &Value) -> Result<Vec<Point>> {
    let r = n(a, "radius", 1.)?;
    let count = a["count"]
        .as_u64()
        .ok_or("Integer circle sample count required")?;
    if !(3..=1000000).contains(&count) || r < 0. {
        return Err("Invalid circle sampling domain".into());
    }
    let center = point(a, "center")?;
    let points: Vec<_> = (0..count)
        .map(|i| {
            let q = polar(r, TAU * i as f64 / count as f64);
            [center[0] + q[0], center[1] + q[1]]
        })
        .collect();

    Ok(points)
}
