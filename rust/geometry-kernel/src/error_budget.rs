// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Whole-interval estimates for the unchanged external-spur sampled boundary.
//! The reference is the existing trimmed rack/involute construction. Source
//! floating-point/transcendental evaluation is explicitly outside this bound.
use crate::{
    precision::Result,
    profiles::{self, Point, Rack, n, radius},
};
use serde_json::{Value, json};
use std::f64::consts::{PI, TAU};

fn point(curve: &Value, t: f64) -> Point {
    profiles::call("curve_point", &json!({"curve":curve,"t":t}))
        .ok()
        .and_then(|p| serde_json::from_value(p).ok())
        .unwrap_or([f64::NAN; 2])
}

fn bound(curve: &Value, a: f64, b: f64) -> Result<f64> {
    let h = (b - a).abs();
    let error = match curve["kind"].as_str() {
        Some("rack_corner") => {
            let tool: Rack =
                serde_json::from_value(curve["tool"].clone()).map_err(|e| e.to_string())?;
            if !(a >= -PI / 2. - 1e-14 && a <= b && b < 0.) {
                return Err("Unsupported rack derivative interval".into());
            }
            crate::cad_curves::rack_second_bound(&tool, a, b) * h * h / 8.
        }
        Some("involute_flank") => {
            let rb = n(curve, "rb", 0.)?;
            if rb <= 0. || a <= 0. || b < a {
                return Err("Unsupported involute derivative interval".into());
            }
            // C_r=(r/rb)(cos(t),-sin(t)), t=sqrt((r/rb)^2-1).
            // M1*h/2 remains valid at the base, where C_rr is unbounded.
            let m1 = (b / rb).max(1.);
            let first = m1 * h / 2.;
            let t = ((a / rb).powi(2) - 1.).max(0.).sqrt();
            if b <= rb {
                0.
            } else if t == 0. {
                first
            } else {
                let m2 = (1. + (b / rb).powi(4) / (t * t)).sqrt() / rb;
                first.min(m2 * h * h / 8.)
            }
        }
        Some("circle") => n(curve, "radius", 0.)? * h * h / 8.,
        _ => return Err("Unsupported source curve in boundary error budget".into()),
    };
    if !error.is_finite() || error < 0. {
        return Err("Nonfinite profile error estimate".into());
    }
    // A numerical evaluation margin, not directed interval arithmetic.
    Ok(error * (1. + 256. * f64::EPSILON))
}

fn enclosure(
    curve: &Value,
    interval: [f64; 2],
    chord: [Point; 2],
    resolution: f64,
    depth: u8,
    work: &mut usize,
) -> Result<f64> {
    *work += 1;
    if *work > 131072 {
        return Err("Source-profile error audit exhausted its refinement budget".into());
    }
    if *work % 64 == 0 {
        crate::protocol::control_check()?;
    }
    let [a, b] = interval;
    let remainder = bound(curve, a, b)?;
    if remainder > resolution {
        let mid = (a + b) / 2.;
        if depth >= 24 || mid == a || mid == b {
            return Err("Source-profile error audit reached numerical resolution".into());
        }
        return Ok(
            enclosure(curve, [a, mid], chord, resolution, depth + 1, work)?.max(enclosure(
                curve,
                [mid, b],
                chord,
                resolution,
                depth + 1,
                work,
            )?),
        );
    }
    let pa = point(curve, a);
    let pb = point(curve, b);
    let distance = profiles::segment_distance(pa, chord[0], chord[1])
        .max(profiles::segment_distance(pb, chord[0], chord[1]));
    // Distance to a convex segment is convex. The subcurve differs from its
    // own endpoint chord by at most the whole-interval remainder. Conversely,
    // continuous projection from the original curve endpoints covers every
    // point of the original chord (IVT), giving the same Hausdorff bound.
    let evaluation = 1024. * f64::EPSILON * radius(pa).max(radius(pb)).max(1.);
    Ok(distance + remainder + evaluation)
}

fn sampled(
    curve: Value,
    tolerance: f64,
    resolution: f64,
    work: &mut usize,
) -> Result<(Vec<Point>, Value)> {
    let a = n(&curve, "start", 0.)?;
    let b = n(&curve, "end", 0.)?;
    let (points, domains) = profiles::sample_with_domains(&|t| point(&curve, t), a, b, tolerance)?;
    let mut maximum: f64 = 0.;
    let mut intervals = Vec::with_capacity(domains.len());
    for (a, b) in domains {
        crate::protocol::control_check()?;
        let error = enclosure(
            &curve,
            [a, b],
            [point(&curve, a), point(&curve, b)],
            resolution,
            0,
            work,
        )?;
        maximum = maximum.max(error);
        intervals.push(json!({"start":a,"end":b,"chord_bound_mm":error}));
    }
    Ok((
        points,
        json!({"curve":curve,"intervals":intervals,"chord_bound_mm":maximum}),
    ))
}

pub(crate) fn spur(a: &Value) -> Result<Value> {
    let metadata = profiles::external_cad_reference(a)?;
    if metadata.get("sampling_policy").is_some() {
        return Err(
            "Source-profile budget currently requires the ordinary external-spur sampler".into(),
        );
    }
    let tolerance = n(&metadata, "chord_threshold_mm", 0.015)?;
    let resolution = n(
        a,
        "budget_refinement_mm",
        (tolerance * 0.02).min(n(a, "mt", 2.)? * 0.0001),
    )?;
    if resolution <= 0. {
        return Err("A positive source-audit refinement request is required".into());
    }
    let mut work = 0;
    let descriptors = metadata["sampling_curves"]
        .as_array()
        .ok_or("Missing source curve domains")?;
    if descriptors.len() != 2 {
        return Err("Unsupported external-spur source domains".into());
    }
    let (root, root_report) = sampled(descriptors[0].clone(), tolerance, resolution, &mut work)?;
    let (flank, flank_report) = sampled(descriptors[1].clone(), tolerance, resolution, &mut work)?;
    let first = *root.first().ok_or("Empty rack domain")?;
    let last = *flank.last().ok_or("Empty involute domain")?;
    let root_radius = n(&metadata, "root_radius_mm", 0.)?;
    let tip_radius = n(&metadata, "tip_radius_mm", 0.)?;
    let teeth = n(a, "z", 24.)?;
    let ar = first[1].atan2(first[0]);
    let at = last[1].atan2(last[0]);
    let root_arc =
        json!({"kind":"circle","center":[0.,0.],"radius":root_radius,"start":-PI/teeth,"end":-ar});
    let tip_arc =
        json!({"kind":"circle","center":[0.,0.],"radius":tip_radius,"start":-at,"end":at});
    let (_, root_arc_report) = sampled(root_arc, tolerance, resolution, &mut work)?;
    let (_, tip_arc_report) = sampled(tip_arc, tolerance, resolution, &mut work)?;
    let distance = |a: Point, b: Point| (a[0] - b[0]).hypot(a[1] - b[1]);
    let join = distance(*root.last().unwrap(), flank[0]);
    let radial_join = (radius(first) - root_radius)
        .abs()
        .max((radius(last) - tip_radius).abs());
    let curves = vec![root_report, flank_report, root_arc_report, tip_arc_report];
    let maximum = curves
        .iter()
        .map(|r| r["chord_bound_mm"].as_f64().unwrap())
        .fold(0., f64::max);
    // Rounding to nine decimal places moves a vertex by <=sqrt(2)*0.5e-9.
    // Each discarded vertex maps to its retained predecessor within1e-7;
    // closure cleanup contributes another1e-7. Linear interpolation is convex.
    let grid = 1.415 * (0.5e-9 + 2. * f64::EPSILON * tip_radius.abs().max(root_radius.abs()));
    let cleanup = 2e-7;
    let total = maximum + join + radial_join + grid + cleanup;
    if !total.is_finite() || !(3. ..=200.).contains(&teeth) || TAU / teeth <= 0. {
        return Err("Unsupported finite source-profile budget".into());
    }
    Ok(
        json!({"schema":"ratiolab.spur-profile-error/1","reference":"existing trimmed rounded-rack and involute boundary, binary64 source parameters",
        "profile_bound_mm":total,"curve_interpolation_bound_mm":maximum,"rack_involute_join_residual_mm":join,
        "bound_refinement_mm":resolution,"audit_cells":work,
        "radial_join_residual_mm":radial_join,"coordinate_grid_bound_mm":grid,"cleanup_bound_mm":cleanup,
        "curves":curves,"arithmetic":"analytic estimates evaluated in binary64 with a numerical margin; not directed interval arithmetic",
        "unquantified":["source parameter/solver/transcendental floating-point evaluation against exact real gear equations"],
        "scope":"complete repeated transverse external-spur boundary; manufacturing, strength and contact are separate"}),
    )
}
