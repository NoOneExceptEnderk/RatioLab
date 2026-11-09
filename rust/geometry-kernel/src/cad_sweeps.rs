// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Controlled cylindrical CAD sweeps, with a whole-surface profile+axial budget.
//! A single piecewise cubic rotation operator is applied to all profile poles.
//! Positive rational weights preserve circular arcs transversely. This avoids
//! fitting a surface through sampled axial sections and bounds its interior.
use crate::precision::Result;
use crate::profiles::{Point, n, polar, radius, rotate};
use serde_json::{Value, json};

const MAX_POLES: usize = 500_000;
const MAX_AXIAL: usize = 256;

struct Planar {
    points: Vec<Point>,
    weights: Vec<f64>,
    degree: usize,
    knots: Vec<f64>,
    mults: Vec<usize>,
    circle: Option<(Point, f64)>,
    c1_bound: f64,
}

fn planar(rows: &[Value]) -> Result<Planar> {
    let first = &rows[0];
    if first["kind"] == "cubic" {
        let start = first["domain"][0].as_f64().ok_or("Missing cubic domain")?;
        let end = rows.last().unwrap()["domain"][1]
            .as_f64()
            .ok_or("Missing cubic domain")?;
        let mut points = Vec::new();
        let mut knots = vec![0.];
        for row in rows {
            let controls: Vec<Point> =
                serde_json::from_value(row["controls"].clone()).map_err(|e| e.to_string())?;
            if controls.len() != 4 {
                return Err("Invalid cubic control count.".into());
            }
            if points.is_empty() {
                points.push(controls[0]);
            }
            if *points.last().unwrap() != controls[0] {
                return Err("Disconnected cylindrical CAD curve.".into());
            }
            points.extend_from_slice(&controls[1..]);
            knots.push((row["domain"][1].as_f64().unwrap() - start) / (end - start));
        }
        if knots.windows(2).any(|q| !q[1].is_finite() || q[1] <= q[0]) {
            return Err("Invalid cylindrical CAD knot span.".into());
        }
        let chain = crate::cad_splines::compact(&points, &knots)?;
        Ok(Planar {
            weights: vec![1.; chain.points.len()],
            points: chain.points,
            degree: 3,
            knots,
            mults: chain.mults,
            circle: None,
            c1_bound: chain.bound,
        })
    } else {
        let center: Point =
            serde_json::from_value(first["center_mm"].clone()).map_err(|e| e.to_string())?;
        let r = n(first, "radius_mm", 0.)?;
        let endpoints: Vec<Point> =
            serde_json::from_value(first["endpoints"].clone()).map_err(|e| e.to_string())?;
        let a = first["angles_rad"][0]
            .as_f64()
            .ok_or("Missing circular domain")?;
        let b = first["angles_rad"][1]
            .as_f64()
            .ok_or("Missing circular domain")?;
        let w = ((b - a) / 2.).cos();
        if r <= 0. || endpoints.len() != 2 || b <= a || w <= 1e-6 {
            return Err("Unsupported rational CAD arc domain.".into());
        }
        let p = polar(r / w, (a + b) / 2.);
        Ok(Planar {
            points: vec![
                endpoints[0],
                [center[0] + p[0], center[1] + p[1]],
                endpoints[1],
            ],
            weights: vec![1., w, 1.],
            degree: 2,
            knots: vec![0., 1.],
            mults: vec![3, 3],
            circle: Some((center, r)),
            c1_bound: 0.,
        })
    }
}

struct Rotation {
    points: Vec<Point>,
    z: Vec<f64>,
    knots: Vec<f64>,
    mults: Vec<usize>,
    bound: f64,
}

fn rotation_controls(angle: f64, count: usize) -> Result<Rotation> {
    let h = 1. / count as f64;
    let mut points = Vec::new();
    let mut z = Vec::new();
    let mut knots = vec![0.];
    for i in 0..count {
        let a = i as f64 / count as f64;
        let b = (i + 1) as f64 / count as f64;
        let p = polar(1., angle * a);
        let q = polar(1., angle * b);
        let k = h * angle / 3.;
        if i == 0 {
            points.push(p);
            z.push(a);
        }
        points.extend([
            [p[0] - k * p[1], p[1] + k * p[0]],
            [q[0] + k * q[1], q[1] - k * q[0]],
            q,
        ]);
        z.extend([a + h / 3., b - h / 3., b]);
        knots.push(b);
    }
    let raw = points
        .iter()
        .zip(&z)
        .map(|(p, z)| [p[0], p[1], *z])
        .collect::<Vec<_>>();
    let chain = crate::cad_splines::compact(&raw, &knots)?;
    Ok(Rotation {
        points: chain.points.iter().map(|p| [p[0], p[1]]).collect(),
        z: chain.points.iter().map(|p| p[2]).collect(),
        knots,
        mults: chain.mults,
        bound: chain.bound,
    })
}

fn spline(points: Vec<[f64; 3]>, degree: usize, knots: &[f64], mults: &[usize]) -> Value {
    json!({"kind":"spline","points":points,"degree":degree,"knots":knots,"multiplicities":mults})
}

pub fn cylindrical(a: &Value) -> Result<Value> {
    let width = n(a, "width", 10.)?;
    let twist = n(a, "twist_deg", 0.)?.to_radians();
    let circular = n(a, "circular_radius_mm", 0.)?;
    if width <= 0. || circular < 0. {
        return Err("Invalid cylindrical CAD blank dimensions.".into());
    }
    let mut profile = crate::cad_curves::cylindrical(a)?;
    let internal = profile["internal"] == true;
    let root = profile["source_profile"]["root_radius_mm"]
        .as_f64()
        .unwrap();
    if (internal && circular <= root) || (!internal && circular >= root) {
        return Err("Invalid circular wall for the cylindrical CAD profile.".into());
    }
    let rows = profile["curves"].as_array().unwrap();
    let groups = crate::cad_splines::groups(rows);
    let mut bases = Vec::new();
    let mut maximum: f64 = 0.;
    let mut count_u = 0;
    let mut profile_c1: f64 = 0.;
    for (first, count) in &groups {
        crate::protocol::control_check()?;
        let p = planar(&rows[*first..*first + *count])?;
        maximum = maximum.max(p.points.iter().map(|p| radius(*p)).fold(0., f64::max));
        count_u += p.points.len();
        profile_c1 = profile_c1.max(p.c1_bound);
        bases.push(p);
    }
    let target = n(a, "tolerance_mm", 0.001)?;
    let profile_bound = n(&profile, "curve_interpolation_bound_mm", 0.)? + profile_c1;
    let guard = n(&profile, "resolution_guard_mm", 0.)?
        .max(1024. * f64::EPSILON * width.max(circular).max(1.));
    let remaining = target - profile_bound - guard;
    if remaining <= 0. || profile_c1 > guard {
        return Err("No remaining cylindrical CAD surface error budget.".into());
    }
    let bound = |count: usize| {
        1.415 * maximum * twist.powi(4) / (384. * (count as f64).powi(4))
            * (1. + 64. * f64::EPSILON)
    };
    let mut count = 1;
    let (rotation, z, knots, mults, axial_c1) = loop {
        let rotation = rotation_controls(twist, count)?;
        let correction = maximum.max(width) * rotation.bound;
        if bound(count) + correction <= remaining {
            break (
                rotation.points,
                rotation.z,
                rotation.knots,
                rotation.mults,
                correction,
            );
        }
        if count >= MAX_AXIAL {
            return Err("Cylindrical CAD axial refinement budget exhausted.".into());
        }
        count *= 2;
    };
    if !bound(count).is_finite()
        || count_u
            .checked_mul(2 * count + 2)
            .is_none_or(|n| n > MAX_POLES)
    {
        return Err("Cylindrical CAD surface exceeds its 500000-pole budget.".into());
    }
    let mut patches = Vec::new();
    for ((first, pieces), p) in groups.iter().zip(bases) {
        crate::protocol::control_check()?;
        let mut poles = Vec::new();
        for (i, xy) in p.points.iter().enumerate() {
            if i % 128 == 0 {
                crate::protocol::control_check()?;
            }
            poles.push(
                rotation
                    .iter()
                    .zip(&z)
                    .map(|(c, z)| {
                        [
                            c[0] * xy[0] - c[1] * xy[1],
                            c[1] * xy[0] + c[0] * xy[1],
                            width * z,
                        ]
                    })
                    .collect::<Vec<_>>(),
            );
        }
        let edge_at = |index: usize| -> Value {
            let points = poles.iter().map(|r| r[index]).collect::<Vec<_>>();
            if let Some((center, radius)) = p.circle {
                let center = rotate(center, twist * z[index]);
                json!({"kind":"circle","center_mm":[center[0],center[1],width*z[index]],"radius_mm":radius,
                    "endpoints":[points[0],*points.last().unwrap()]})
            } else {
                spline(points, p.degree, &p.knots, &p.mults)
            }
        };
        let low = edge_at(0);
        let high = edge_at(z.len() - 1);
        let trajectory = |points: Vec<[f64; 3]>| {
            if twist == 0. {
                json!({"kind":"line","points":[points[0],*points.last().unwrap()]})
            } else {
                spline(points, 3, &knots, &mults)
            }
        };
        let start = trajectory(poles[0].clone());
        let end = trajectory(poles.last().unwrap().clone());
        let weights = p
            .weights
            .iter()
            .map(|w| vec![*w; z.len()])
            .collect::<Vec<_>>();
        let kind = if twist != 0. {
            "bspline_surface"
        } else if p.circle.is_some() {
            "cylinder"
        } else {
            "extrusion"
        };
        patches.push(
            json!({"first_curve":first,"curve_count":pieces,"surface_type":kind,
            "u_degree":p.degree,"v_degree":3,"u_knots":p.knots,"v_knots":knots,
            "u_multiplicities":p.mults,"v_multiplicities":mults,
            "poles":poles,"weights":weights,"lower":low,"upper":high,"start":start,"end":end}),
        );
    }
    profile["c1_reconstruction_bound_mm"] = json!(profile_c1);
    profile["curve_interpolation_bound_mm"] = json!(profile_bound);
    Ok(
        json!({"schema":"ratiolab.curved-cylindrical-geometry/1","profile":profile,"patches":patches,
        "sweep":{"width_mm":width,"twist_rad":twist,"intervals":count,"maximum_control_radius_mm":maximum,
            "rotation_controls":rotation,"z_controls":z,"knots":knots,"multiplicities":mults,
            "requested_surface_mm":target,"profile_bound_mm":profile_bound,"axial_bound_mm":bound(count)+axial_c1,
            "profile_c1_reconstruction_bound_mm":profile_c1,"axial_c1_reconstruction_bound_mm":axial_c1,
            "surface_interpolation_bound_mm":profile_bound+bound(count)+axial_c1,"resolution_guard_mm":guard,
            "scope":"whole surface relative to the existing continuous cylindrical profile and linear-twist sweep; excludes roundoff, reader tolerances, cutter/contact/manufacturing qualification",
            "arithmetic":"binary64 analytic bounds, not certified interval arithmetic"},
        "internal":internal,"circular_radius_mm":circular}),
    )
}
