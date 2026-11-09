// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Bounded cubic Hermite curves for one external-spur CAD prototype.
//!
//! Existing rack/involute equations and their trimmed domains remain the source.
//! The Hermite remainder is <= sqrt(2) M4 h^4/384 when M4 bounds the vector
//! fourth derivative. The sqrt(2) is a conservative componentwise conversion.
//! This analytic bound is evaluated in binary64, not certified interval math.
//! See docs/technical/curved-cad-prototype.md for the derivative derivation,
//! reference convention, endpoint joins and the deliberately limited scope.
use crate::precision::Result;
use crate::profiles::{Point, Rack, n, polar, radius, rotate};
use serde_json::{Value, json};
use std::f64::consts::{PI, TAU};

const MAX_SEGMENTS: usize = 32_768;
const MAX_DEPTH: u8 = 20;

#[derive(Clone)]
enum Curve {
    Rack(Rack, f64),
    Involute { rb: f64, offset: f64 },
    InternalInvolute { rb: f64, offset: f64 },
}

impl Curve {
    fn tangent_turn_bound(&self, a: f64, b: f64) -> f64 {
        match self {
            Self::Rack(tool, _) => {
                let q = 1. / b.abs();
                let ellipse = tool.tip_radius * (1. / tool.cos_beta - tool.cos_beta).abs();
                let phi = (ellipse + tool.cos_beta * tool.tip_center_v.abs() * (1. + q * q))
                    / tool.pitch_radius;
                (1. / tool.cos_beta + phi) * (b - a).abs()
            }
            Self::Involute { .. } | Self::InternalInvolute { .. } => (b - a).abs(),
        }
    }
    fn second_bound(&self, a: f64, b: f64) -> f64 {
        match self {
            Self::Involute { rb, .. } | Self::InternalInvolute { rb, .. } => {
                rb * (1. + a.abs().max(b.abs()).powi(2)).sqrt()
            }
            Self::Rack(tool, _) => {
                let q = 1. / b.abs();
                let q1 = 1. + q * q;
                let q2 = 2. * q * q1;
                let v = tool.cos_beta * tool.tip_center_v.abs();
                let ellipse = tool.tip_radius * (1. / tool.cos_beta - tool.cos_beta).abs();
                let p1 = (ellipse + v * q1) / tool.pitch_radius;
                let p2 = (ellipse + v * q2) / tool.pitch_radius;
                let g0 =
                    (v * q).hypot(tool.pitch_radius + tool.tip_center_v.abs()) + tool.tip_radius;
                let g1 = v * q1 + tool.tip_radius;
                let g2 = v * q2 + tool.tip_radius;
                g2 + 2. * g1 * p1 + g0 * (p2 + p1 * p1)
            }
        }
    }
    fn value_tangent(&self, t: f64) -> (Point, Point) {
        match self {
            Self::Rack(tool, rotation) => {
                // The normal rack's transverse ellipse adds
                // rho*(1/cb-cb)*cos(t) to rp*phi. Keep the point on the
                // existing envelope; differentiate its reduced identity.
                let q = t.cos() / t.sin();
                let q1 = -(1. + q * q);
                let cb = tool.cos_beta;
                let ellipse = tool.tip_radius * (1. / cb - cb);
                let phi = (tool.tip_center_u / cb + ellipse * t.cos() - cb * tool.tip_center_v * q)
                    / tool.pitch_radius;
                let phi1 = (-ellipse * t.sin() - cb * tool.tip_center_v * q1) / tool.pitch_radius;
                let g = [
                    cb * (tool.tip_center_v * q + tool.tip_radius * t.cos()),
                    tool.pitch_radius + tool.tip_center_v + tool.tip_radius * t.sin(),
                ];
                let dg = [
                    cb * (tool.tip_center_v * q1 - tool.tip_radius * t.sin()),
                    tool.tip_radius * t.cos(),
                ];
                let tangent = rotate([dg[0] + phi1 * g[1], dg[1] - phi1 * g[0]], rotation - phi);
                (rotate(tool.point(t), *rotation), tangent)
            }
            Self::Involute { rb, offset } => {
                let (s, c) = (t.sin(), t.cos());
                (
                    rotate([rb * (c + t * s), rb * (t * c - s)], *offset),
                    rotate([rb * t * c, -rb * t * s], *offset),
                )
            }
            Self::InternalInvolute { rb, offset } => {
                let (s, c) = (t.sin(), t.cos());
                (
                    rotate([rb * (c + t * s), rb * (s - t * c)], *offset),
                    rotate([rb * t * c, rb * t * s], *offset),
                )
            }
        }
    }

    fn fourth_bound(&self, a: f64, b: f64) -> f64 {
        match self {
            Self::Involute { rb, .. } | Self::InternalInvolute { rb, .. } => {
                rb * (9. + a.abs().max(b.abs()).powi(2)).sqrt()
            }
            Self::Rack(tool, _) => {
                // On -pi/2<=a<=t<=b<0, |cot(t)|<=1/|b| since tan(x)>=x.
                // q^(1..4) follow from q'=-(1+q^2). All following terms are
                // nonnegative bounds; no sampled maxima enter this estimate.
                let q = 1. / b.abs();
                let q1 = 1. + q * q;
                let q2 = 2. * q * q1;
                let q3 = 2. * q1 * (1. + 3. * q * q);
                let q4 = 8. * q * q1 * (2. + 3. * q * q);
                let v = tool.cos_beta * tool.tip_center_v.abs();
                let ellipse = tool.tip_radius * (1. / tool.cos_beta - tool.cos_beta).abs();
                let [p1, p2, p3, p4] =
                    [q1, q2, q3, q4].map(|d| (ellipse + v * d) / tool.pitch_radius);
                let e1 = p1;
                let e2 = p2 + p1 * p1;
                let e3 = p3 + 3. * p1 * p2 + p1.powi(3);
                let e4 = p4 + 4. * p1 * p3 + 3. * p2 * p2 + 6. * p1 * p1 * p2 + p1.powi(4);
                let g0 =
                    (v * q).hypot(tool.pitch_radius + tool.tip_center_v.abs()) + tool.tip_radius;
                let [g1, g2, g3, g4] = [q1, q2, q3, q4].map(|d| v * d + tool.tip_radius);
                g4 + 4. * g3 * e1 + 6. * g2 * e2 + 4. * g1 * e3 + g0 * e4
            }
        }
    }
}

/// Rotation does not affect the derivative norm. Shared by the source-profile
/// error audit; this adds no CAD operation or alternative rack construction.
pub(crate) fn rack_second_bound(tool: &Rack, a: f64, b: f64) -> f64 {
    Curve::Rack(tool.clone(), 0.).second_bound(a, b)
}

fn tangent_samples(
    curve: Curve,
    a: f64,
    b: f64,
    tolerance: f64,
    scale: f64,
) -> Result<(Vec<Point>, f64)> {
    fn cross(a: Point, b: Point) -> f64 {
        a[0] * b[1] - a[1] * b[0]
    }
    #[allow(
        clippy::too_many_arguments,
        reason = "Explicit adaptive curve and error-budget state"
    )]
    fn recurse(
        curve: &Curve,
        a: f64,
        b: f64,
        tolerance: f64,
        guard: f64,
        depth: u8,
        points: &mut Vec<Point>,
        maximum: &mut f64,
    ) -> Result<()> {
        crate::protocol::control_check()?;
        let (p, dp) = curve.value_tangent(a);
        let (q, dq) = curve.value_tangent(b);
        let d = [q[0] - p[0], q[1] - p[1]];
        let den = cross(dp, dq);
        let mut accepted = None;
        if den > 0.
            && dp[0] * dq[0] + dp[1] * dq[1] > 0.
            && curve.tangent_turn_bound(a, b) < PI / 2.
        {
            let t = cross(d, dq) / den;
            let s = cross(d, dp) / den;
            let vertex = [p[0] + t * dp[0], p[1] + t * dp[1]];
            let length2 = d[0] * d[0] + d[1] * d[1];
            let projection = ((vertex[0] - p[0]) * d[0] + (vertex[1] - p[1]) * d[1]) / length2;
            let height = cross([vertex[0] - p[0], vertex[1] - p[1]], d).abs() / length2.sqrt();
            // The arc and tangent polygon are each within this distance of
            // the common chord. Positive convexity is checked by the caller.
            let bound = 1.415 * curve.second_bound(a, b) * (b - a).powi(2) / 8. + height + guard;
            if t >= 0.
                && s <= 0.
                && (0. ..=1.).contains(&projection)
                && radius(vertex) >= radius(p).min(radius(q)) - guard
                && radius(vertex) <= radius(p).max(radius(q)) + guard
                && bound.is_finite()
                && bound <= tolerance
            {
                accepted = Some((vertex, bound));
            }
        }
        if let Some((vertex, bound)) = accepted {
            if points.len() + 2 > 16_384 {
                return Err(
                    "Conservative paired-profile point budget exhausted; accuracy was not met."
                        .into(),
                );
            }
            points.extend([p, vertex]);
            *maximum = maximum.max(bound);
            return Ok(());
        }
        let mid = (a + b) / 2.;
        if depth >= 24 || mid == a || mid == b {
            return Err(
                "Conservative paired-profile refinement exhausted; accuracy was not met.".into(),
            );
        }
        recurse(curve, a, mid, tolerance, guard, depth + 1, points, maximum)?;
        recurse(curve, mid, b, tolerance, guard, depth + 1, points, maximum)
    }
    let guard = 1024. * f64::EPSILON * scale.max(1.);
    if tolerance <= 4. * guard {
        return Err("Paired-profile request is below numerical resolution.".into());
    }
    let mut points = Vec::new();
    let mut bound = 0.;
    recurse(&curve, a, b, tolerance, guard, 0, &mut points, &mut bound)?;
    points.push(curve.value_tangent(b).0);
    Ok((points, bound))
}

/// The normal rack corner is positively curved in this parameter direction.
/// phi'<=0 is a sufficient whole-domain condition: its tool tangent rotates
/// positively and |q'| never vanishes because v<0 and u'>0. Circumscribed
/// tangents therefore REMOVE pinion material, unlike ordinary root chords.
pub(crate) fn paired_rack_samples(
    tool: &Rack,
    rotation: f64,
    a: f64,
    b: f64,
    tolerance: f64,
) -> Result<(Vec<Point>, f64)> {
    let upper_phi = (tool.tip_radius * (1. / tool.cos_beta - tool.cos_beta).max(0.)
        + tool.cos_beta * tool.tip_center_v)
        / tool.pitch_radius;
    if tool.tip_center_v >= 0. || upper_phi > 0. || a < -PI / 2. - 1e-14 || b >= 0. || b <= a {
        return Err("Paired root has no certified convex tangent-sampling domain.".into());
    }
    tangent_samples(
        Curve::Rack(tool.clone(), rotation),
        a,
        b,
        tolerance,
        tool.pitch_radius + tool.normal_module * tool.dedendum,
    )
}

/// A positive-roll internal involute is convex in its traversal direction;
/// its tangent polygon enlarges the ring void and never adds tooth material.
pub(crate) fn paired_internal_samples(
    rb: f64,
    offset: f64,
    lower: f64,
    upper: f64,
    tolerance: f64,
) -> Result<(Vec<Point>, f64)> {
    let roll = |r: f64| ((r / rb).powi(2) - 1.).max(0.).sqrt();
    if lower <= rb || upper <= lower {
        return Err("Paired internal sampling requires a positive usable involute.".into());
    }
    tangent_samples(
        Curve::InternalInvolute { rb, offset },
        roll(lower),
        roll(upper),
        tolerance,
        upper,
    )
}

#[derive(Clone)]
struct Cubic {
    controls: [Point; 4],
    domain: [f64; 2],
    bound: f64,
    fourth: f64,
}

fn fit(curve: &Curve, a: f64, b: f64, tolerance: f64) -> Result<Vec<Cubic>> {
    fn refine(
        curve: &Curve,
        a: f64,
        b: f64,
        tol: f64,
        depth: u8,
        out: &mut Vec<Cubic>,
    ) -> Result<()> {
        crate::protocol::control_check()?;
        let h = b - a;
        let fourth = curve.fourth_bound(a.min(b), a.max(b));
        // 1.415 exceeds sqrt(2); a small evaluation margin is included. It is
        // deliberately described as a binary64 analytic estimate, not a proof
        // of libm rounding or downstream reader/placement tolerances.
        let bound = 1.415 * fourth * h.powi(4) / 384. * (1. + 64. * f64::EPSILON);
        if !bound.is_finite() {
            return Err("Nonfinite CAD curve bound.".into());
        }
        if bound <= tol {
            let (p, dp) = curve.value_tangent(a);
            let (q, dq) = curve.value_tangent(b);
            let controls = [
                p,
                [p[0] + h * dp[0] / 3., p[1] + h * dp[1] / 3.],
                [q[0] - h * dq[0] / 3., q[1] - h * dq[1] / 3.],
                q,
            ];
            if controls.iter().flatten().any(|v| !v.is_finite()) {
                return Err("Nonfinite CAD curve control point.".into());
            }
            out.push(Cubic {
                controls,
                domain: [a, b],
                bound,
                fourth,
            });
            return Ok(());
        }
        let mid = (a + b) / 2.;
        if depth >= MAX_DEPTH || out.len() >= MAX_SEGMENTS || mid == a || mid == b {
            return Err(
                "CAD curve refinement budget exhausted; requested accuracy was not met.".into(),
            );
        }
        refine(curve, a, mid, tol, depth + 1, out)?;
        refine(curve, mid, b, tol, depth + 1, out)
    }
    let mut out = Vec::new();
    refine(curve, a, b, tolerance, 0, &mut out)?;
    Ok(out)
}

fn transformed(p: Point, mirror: bool, angle: f64) -> Point {
    rotate([p[0], if mirror { -p[1] } else { p[1] }], angle)
}

fn cubics(rows: &[Cubic], mirror: bool, reverse: bool, angle: f64, source: usize) -> Vec<Value> {
    let convert = |row: &Cubic| {
        let mut controls = row.controls.map(|p| transformed(p, mirror, angle));
        let mut domain = row.domain;
        if reverse {
            controls.reverse();
            domain.reverse();
        }
        json!({"kind":"cubic", "controls":controls, "source":source,
            "domain":domain,"mirror":mirror,"rotation_rad":angle,
            "interpolation_bound_mm":row.bound,"fourth_derivative_bound_mm":row.fourth})
    };
    if reverse {
        rows.iter().rev().map(convert).collect()
    } else {
        rows.iter().map(convert).collect()
    }
}

fn arc(radius: f64, start: f64, end: f64, rotation: f64, label: &str) -> Value {
    json!({"kind":"circle_arc","radius_mm":radius,
        "endpoints":[polar(radius,start+rotation),polar(radius,end+rotation)],
        "angles_rad":[start+rotation,end+rotation],"reference":label,
        "interpolation_bound_mm":0.})
}

pub fn spur(a: &Value) -> Result<Value> {
    let teeth = n(a, "z", 24.)?;
    if teeth.fract() != 0. || !(3. ..=200.).contains(&teeth) {
        return Err("Curved CAD prototype requires 3 to 200 integer teeth.".into());
    }
    if a["internal"] == true || n(a, "helix", 0.)? != 0. {
        return Err("Curved CAD prototype supports external spur gears only.".into());
    }
    let tolerance = n(a, "tolerance_mm", 0.001)?;
    if tolerance <= 0. {
        return Err("CAD curve tolerance must be positive and finite.".into());
    }
    let metadata = crate::profiles::external_cad_reference(a)?;
    if n(a, "semitopping_mm", 0.)? > 0. {
        return Err("Curved CAD prototype does not yet support semitopping. Use the ordinary STEP/STL exports.".into());
    }
    let sources = metadata["sampling_curves"]
        .as_array()
        .ok_or("Missing CAD curve sources")?;
    let rack_source = &sources[0];
    let tool: Rack =
        serde_json::from_value(rack_source["tool"].clone()).map_err(|e| e.to_string())?;
    if tool.cos_beta != 1. {
        return Err("Curved CAD prototype requires a spur rack.".into());
    }
    let root = n(&metadata, "root_radius_mm", 0.)?;
    let tip = n(&metadata, "tip_radius_mm", 0.)?;
    let guard = 1024. * f64::EPSILON * tip.max(1.);
    if tolerance <= 4. * guard {
        return Err("CAD curve request is below the prototype's binary64 resolution guard.".into());
    }
    let rb = n(&sources[1], "rb", 0.)?;
    let rp = n(&sources[1], "rp", 0.)?;
    let half = n(&sources[1], "half", 0.)?;
    let pitch_roll = ((rp / rb).powi(2) - 1.).max(0.).sqrt();
    let offset = half + pitch_roll - pitch_roll.atan();
    let lower = n(&metadata, "involute_start_radius_mm", 0.)?;
    let t0 = ((lower / rb).powi(2) - 1.).max(0.).sqrt();
    let t1 = ((tip / rb).powi(2) - 1.).max(0.).sqrt();
    let lo = n(rack_source, "start", -PI / 2.)?;
    let hi = n(rack_source, "end", 0.)?;
    if lo < -PI / 2. - 1e-14 || hi >= 0. || hi <= lo || t1 <= t0 {
        return Err("CAD curve source has an unsupported or degenerate domain.".into());
    }
    let rack = Curve::Rack(tool, n(rack_source, "rotation", 0.)?);
    let involute = Curve::Involute { rb, offset };
    let root_fit = fit(&rack, lo, hi, (tolerance - guard) / 2.)?;
    let flank_fit = fit(&involute, t0, t1, (tolerance - guard) / 2.)?;
    let pitch = TAU / teeth;
    let root_point = rack.value_tangent(lo).0;
    let tip_point = involute.value_tangent(t1).0;
    let ar = root_point[1].atan2(root_point[0]);
    let at = tip_point[1].atan2(tip_point[0]);
    let per_tooth = 3 + 2 * (root_fit.len() + flank_fit.len());
    if per_tooth * teeth as usize > MAX_SEGMENTS {
        return Err("Curved CAD prototype exceeds its 32768-edge budget.".into());
    }
    let mut curves = Vec::new();
    for tooth in 0..teeth as usize {
        let angle = tooth as f64 * pitch;
        curves.push(arc(root, -pitch / 2., -ar, angle, "root_circle"));
        curves.extend(cubics(&root_fit, true, false, angle, 0));
        curves.extend(cubics(&flank_fit, true, false, angle, 1));
        curves.push(arc(tip, -at, at, angle, "tip_circle"));
        curves.extend(cubics(&flank_fit, false, true, angle, 1));
        curves.extend(cubics(&root_fit, false, true, angle, 0));
        curves.push(arc(root, ar, pitch / 2., angle, "root_circle"));
    }
    // Share exact endpoint coordinates across adjacent edges. For cubics the
    // endpoint control change is bounded by its Bernstein weight (<=1); both
    // end changes together are bounded by their maximum, not their sum.
    let mut maximum_join: f64 = 0.;
    let mut max_bound: f64 = 0.;
    for i in 0..curves.len() {
        let prev = (i + curves.len() - 1) % curves.len();
        let key = if curves[prev]["kind"] == "cubic" {
            "controls"
        } else {
            "endpoints"
        };
        let previous = curves[prev][key]
            .as_array()
            .unwrap()
            .last()
            .unwrap()
            .clone();
        let key = if curves[i]["kind"] == "cubic" {
            "controls"
        } else {
            "endpoints"
        };
        let old: Point = serde_json::from_value(curves[i][key][0].clone()).unwrap();
        let p: Point = serde_json::from_value(previous.clone()).unwrap();
        let delta = radius([p[0] - old[0], p[1] - old[1]]);
        if !delta.is_finite() || delta > guard {
            return Err("CAD theoretical curve join exceeds the resolution guard.".into());
        }
        curves[i][key][0] = previous;
        curves[i]["join_displacement_mm"] = json!(delta);
        maximum_join = maximum_join.max(delta);
        max_bound = max_bound.max(curves[i]["interpolation_bound_mm"].as_f64().unwrap() + delta);
    }
    if max_bound + guard > tolerance {
        return Err("CAD curve target was not met.".into());
    }
    Ok(
        json!({"schema":"ratiolab.curved-spur-prototype/1","teeth":teeth as u32,
        "curves":curves,"reference_sources":[rack_source,
            {"kind":"involute_roll","base_radius_mm":rb,"offset_rad":offset}],
        "source_profile":metadata,"requested_curve_mm":tolerance,
        "curve_interpolation_bound_mm":max_bound,"resolution_guard_mm":guard,
        "maximum_join_displacement_mm":maximum_join,
        "arithmetic":"binary64 analytic Hermite remainder bound; not certified interval arithmetic",
        "scope":"continuous external-spur rack-root and involute approximation with exact circular arcs, extruded without axial approximation; excludes arithmetic/STEP reader roundoff, cutter validity, contact, strength and manufacturing",
        "ordinary_sampled_geometry_changed":false}),
    )
}

fn centered_arc(center: Point, r: f64, start: f64, end: f64, rotation: f64, label: &str) -> Value {
    let point = |t| {
        let p = polar(r, t);
        rotate([center[0] + p[0], center[1] + p[1]], rotation)
    };
    json!({"kind":"circle_arc","radius_mm":r,"center_mm":rotate(center,rotation),
        "endpoints":[point(start),point(end)],"angles_rad":[start+rotation,end+rotation],
        "reference":label,"interpolation_bound_mm":0.})
}

/// Continuous cylindrical profile, using the actual normal/transverse recipe.
/// All curves wind CCW: an external material boundary or an internal void.
pub(crate) fn cylindrical(a: &Value) -> Result<Value> {
    let teeth = n(a, "z", 24.)?;
    if teeth.fract() != 0. || !(3. ..=200.).contains(&teeth) {
        return Err("Curved CAD prototype requires 3 to 200 integer teeth.".into());
    }
    let tolerance = n(a, "tolerance_mm", 0.001)?;
    if tolerance <= 0. {
        return Err("CAD curve tolerance must be positive and finite.".into());
    }
    let internal = a["internal"] == true;
    let metadata = crate::profiles::cylindrical_cad_reference(a)?;
    if n(a, "semitopping_mm", 0.)? > 0. {
        return Err("Curved CAD prototype does not yet support semitopping. Use the ordinary STEP/STL exports.".into());
    }
    let source = metadata["sampling_curves"]
        .as_array()
        .ok_or("Missing cylindrical curve recipe")?;
    let root = n(&metadata, "root_radius_mm", 0.)?;
    let tip = n(&metadata, "tip_radius_mm", 0.)?;
    let guard = 1024. * f64::EPSILON * root.max(tip).max(1.);
    if tolerance <= 4. * guard {
        return Err("CAD curve request is below the prototype's binary64 resolution guard.".into());
    }
    let flank_source = &source[if internal { 0 } else { 1 }];
    let rp = n(flank_source, "rp", 0.)?;
    let rb = n(flank_source, "rb", 0.)?;
    let half = n(flank_source, "half", 0.)?;
    let roll = |r: f64| ((r / rb).powi(2) - 1.).max(0.).sqrt();
    let pitch_roll = roll(rp);
    let inv = crate::profiles::inv_roll(pitch_roll);
    let offset = half + if internal { -inv } else { inv };
    let lower = if internal {
        tip
    } else {
        n(&metadata, "involute_start_radius_mm", 0.)?
    };
    let upper = if internal {
        n(&metadata, "involute_end_radius_mm", 0.)?
    } else {
        tip
    };
    let flank = if internal {
        Curve::InternalInvolute { rb, offset }
    } else {
        Curve::Involute { rb, offset }
    };
    let flank_fit = fit(&flank, roll(lower), roll(upper), (tolerance - guard) / 2.)?;
    let phase = n(a, "phase", 0.)?;
    let pitch = TAU / teeth;
    let mut curves = Vec::new();
    let mut reference_sources = Vec::new();
    if internal {
        if (5 + 2 * flank_fit.len()) * teeth as usize > MAX_SEGMENTS {
            return Err("Curved CAD prototype exceeds its 32768-piece budget.".into());
        }
        let blend = &source[1];
        let center: Point =
            serde_json::from_value(blend["center"].clone()).map_err(|e| e.to_string())?;
        let rho = n(blend, "radius", 0.)?;
        let t0 = n(blend, "start", 0.)?;
        let t1 = n(blend, "end", 0.)?;
        if rho <= 0. || !(0. < t1 - t0 && t1 - t0 < PI) {
            return Err("Unsupported internal blend arc domain.".into());
        }
        let p = polar(rho, t1);
        let ar = (center[1] + p[1]).atan2(center[0] + p[0]);
        let p = flank.value_tangent(roll(tip)).0;
        let at = p[1].atan2(p[0]);
        reference_sources.push(json!({"kind":"involute_roll","base_radius_mm":rb,"offset_rad":offset,"orientation":1.}));
        for tooth in 0..teeth as usize {
            let angle = phase + tooth as f64 * pitch;
            curves.push(centered_arc(
                [0., 0.],
                root,
                -pitch / 2.,
                -ar,
                angle,
                "root_circle",
            ));
            curves.push(centered_arc(
                [center[0], -center[1]],
                rho,
                -t1,
                -t0,
                angle,
                "internal_root_blend",
            ));
            curves.extend(cubics(&flank_fit, true, true, angle, 0));
            curves.push(centered_arc([0., 0.], tip, -at, at, angle, "tip_circle"));
            curves.extend(cubics(&flank_fit, false, false, angle, 0));
            curves.push(centered_arc(
                center,
                rho,
                t0,
                t1,
                angle,
                "internal_root_blend",
            ));
            curves.push(centered_arc(
                [0., 0.],
                root,
                ar,
                pitch / 2.,
                angle,
                "root_circle",
            ));
        }
    } else {
        let rack_source = &source[0];
        let tool: Rack =
            serde_json::from_value(rack_source["tool"].clone()).map_err(|e| e.to_string())?;
        let lo = n(rack_source, "start", -PI / 2.)?;
        let hi = n(rack_source, "end", 0.)?;
        if lo < -PI / 2. - 1e-14 || hi >= 0. || hi <= lo {
            return Err("Unsupported rack curve domain.".into());
        }
        let rack = Curve::Rack(tool, n(rack_source, "rotation", 0.)?);
        let root_fit = fit(&rack, lo, hi, (tolerance - guard) / 2.)?;
        if (3 + 2 * (root_fit.len() + flank_fit.len())) * teeth as usize > MAX_SEGMENTS {
            return Err("Curved CAD prototype exceeds its 32768-piece budget.".into());
        }
        let p = rack.value_tangent(lo).0;
        let ar = p[1].atan2(p[0]);
        let p = flank.value_tangent(roll(tip)).0;
        let at = p[1].atan2(p[0]);
        reference_sources.push(rack_source.clone());
        reference_sources.push(json!({"kind":"involute_roll","base_radius_mm":rb,"offset_rad":offset,"orientation":-1.}));
        for tooth in 0..teeth as usize {
            let angle = phase + tooth as f64 * pitch;
            curves.push(centered_arc(
                [0., 0.],
                root,
                -pitch / 2.,
                -ar,
                angle,
                "root_circle",
            ));
            curves.extend(cubics(&root_fit, true, false, angle, 0));
            curves.extend(cubics(&flank_fit, true, false, angle, 1));
            curves.push(centered_arc([0., 0.], tip, -at, at, angle, "tip_circle"));
            curves.extend(cubics(&flank_fit, false, true, angle, 1));
            curves.extend(cubics(&root_fit, false, true, angle, 0));
            curves.push(centered_arc(
                [0., 0.],
                root,
                ar,
                pitch / 2.,
                angle,
                "root_circle",
            ));
        }
    }
    if curves.len() > MAX_SEGMENTS {
        return Err("Curved CAD prototype exceeds its 32768-piece budget.".into());
    }
    let mut maximum_join: f64 = 0.;
    let mut bound: f64 = 0.;
    for i in 0..curves.len() {
        let prev = (i + curves.len() - 1) % curves.len();
        let key = if curves[prev]["kind"] == "cubic" {
            "controls"
        } else {
            "endpoints"
        };
        let endpoint = curves[prev][key]
            .as_array()
            .unwrap()
            .last()
            .unwrap()
            .clone();
        let key = if curves[i]["kind"] == "cubic" {
            "controls"
        } else {
            "endpoints"
        };
        let p: Point = serde_json::from_value(endpoint.clone()).unwrap();
        let q: Point = serde_json::from_value(curves[i][key][0].clone()).unwrap();
        let delta = radius([p[0] - q[0], p[1] - q[1]]);
        if !delta.is_finite() || delta > guard {
            return Err("CAD theoretical curve join exceeds the resolution guard.".into());
        }
        curves[i][key][0] = endpoint;
        curves[i]["join_displacement_mm"] = json!(delta);
        maximum_join = maximum_join.max(delta);
        bound = bound.max(n(&curves[i], "interpolation_bound_mm", 0.)? + delta);
    }
    Ok(
        json!({"schema":"ratiolab.curved-cylindrical-profile/1","teeth":teeth as u32,
        "internal":internal,"phase_rad":phase,"curves":curves,"reference_sources":reference_sources,
        "source_profile":metadata,"requested_curve_mm":tolerance,"curve_interpolation_bound_mm":bound,
        "resolution_guard_mm":guard,"maximum_join_displacement_mm":maximum_join,
        "arithmetic":"binary64 analytic Hermite remainder bound; not certified interval arithmetic",
        "scope":"continuous normal-rack/involute external boundary or unshifted involute/tangent-circle internal void; excludes cutter, contact, strength and manufacturing qualification",
        "ordinary_sampled_geometry_changed":false}),
    )
}

/// Complete cubic interpolation in a clamped open-uniform basis. The source
/// supplies positions AND endpoint derivatives, not preview vertices. Relative
/// to exact-derivative Hermite pieces, the complete-spline derivative residual
/// is <= 7 M4 h^3/12; diagonal dominance gives derivative error <=7 M4 h^3/24.
/// Hermite derivative bases have absolute sum <=1/4, so the curve error is <=
/// (sqrt(2)/384 + 7/96) M4 h^4 < M4 h^4/8. See mathematical-cad-contract.md.
struct UniformSpline {
    controls: Vec<Point>,
    domain: [f64; 2],
    bound: f64,
}

fn cubic_basis(knots: &[f64], t: f64) -> Vec<f64> {
    let mut values: Vec<f64> = knots
        .windows(2)
        .map(|k| if k[0] <= t && t < k[1] { 1. } else { 0. })
        .collect();
    for degree in 1..=3 {
        values = (0..values.len() - 1)
            .map(|i| {
                let a = knots[i + degree] - knots[i];
                let b = knots[i + degree + 1] - knots[i + 1];
                (if a > 0. {
                    (t - knots[i]) * values[i] / a
                } else {
                    0.
                }) + (if b > 0. {
                    (knots[i + degree + 1] - t) * values[i + 1] / b
                } else {
                    0.
                })
            })
            .collect();
    }
    values
}
fn uniform_fit(
    curve: &Curve,
    a: f64,
    b: f64,
    tolerance: f64,
    depth: u8,
) -> Result<Vec<UniformSpline>> {
    crate::protocol::control_check()?;
    let m4 = curve.fourth_bound(a, b);
    let steps = (m4 * (b - a).powi(4) / (8. * tolerance))
        .sqrt()
        .sqrt()
        .ceil()
        .max(1.) as usize;
    // Shorter domains reduce pessimism of the analytic derivative bound near
    // the rack-envelope limit and fit the CAD's per-sketch point budget.
    if steps > 125 {
        if depth >= MAX_DEPTH {
            return Err("Native cubic CAD pole budget exhausted; accuracy not met.".into());
        }
        let mid = (a + b) / 2.;
        let mut rows = uniform_fit(curve, a, mid, tolerance, depth + 1)?;
        rows.extend(uniform_fit(curve, mid, b, tolerance, depth + 1)?);
        if rows.len() > MAX_SEGMENTS {
            return Err("Native cubic CAD curve budget exhausted.".into());
        }
        return Ok(rows);
    }
    let h = (b - a) / steps as f64;
    let (p, dp) = curve.value_tangent(a);
    let (q, dq) = curve.value_tangent(b);
    let mut poles = vec![[0.; 2]; steps + 3];
    let last = poles.len() - 1;
    poles[0] = p;
    poles[1] = [p[0] + h * dp[0] / 3., p[1] + h * dp[1] / 3.];
    poles[last] = q;
    poles[last - 1] = [q[0] - h * dq[0] / 3., q[1] - h * dq[1] / 3.];
    if steps > 1 {
        let mut knots = vec![0.; 4];
        knots.extend((1..steps).map(|i| i as f64));
        knots.extend([steps as f64; 4]);
        let count = steps - 1;
        let mut lower = vec![0.; count];
        let mut diag = vec![0.; count];
        let mut upper = vec![0.; count];
        let mut rhs = vec![[0.; 2]; count];
        for k in 1..steps {
            crate::protocol::control_check()?;
            let weights = cubic_basis(&knots, k as f64);
            let i = k - 1;
            diag[i] = weights[k + 1];
            lower[i] = if k > 1 { weights[k] } else { 0. };
            upper[i] = if k < steps - 1 { weights[k + 2] } else { 0. };
            rhs[i] = curve.value_tangent(a + h * k as f64).0;
            if k == 1 {
                for axis in 0..2 {
                    rhs[i][axis] -= weights[1] * poles[1][axis];
                }
            }
            if k == steps - 1 {
                for axis in 0..2 {
                    rhs[i][axis] -= weights[steps + 1] * poles[steps + 1][axis];
                }
            }
        }
        for i in 1..count {
            let factor = lower[i] / diag[i - 1];
            diag[i] -= factor * upper[i - 1];
            let previous = rhs[i - 1];
            for (current, old) in rhs[i].iter_mut().zip(previous) {
                *current -= factor * old;
            }
        }
        for i in (0..count).rev() {
            for axis in 0..2 {
                poles[i + 2][axis] = (rhs[i][axis]
                    - if i + 1 < count {
                        upper[i] * poles[i + 3][axis]
                    } else {
                        0.
                    })
                    / diag[i];
            }
        }
    }
    if poles.iter().flatten().any(|n| !n.is_finite()) {
        return Err("Native cubic source interpolation failed.".into());
    }
    Ok(vec![UniformSpline {
        controls: poles,
        domain: [a, b],
        bound: m4 * h.powi(4) / 8.,
    }])
}

pub(crate) fn native_cylindrical(a: &Value) -> Result<Value> {
    let mut profile = cylindrical(a)?;
    let tolerance = n(a, "tolerance_mm", 0.001)?;
    let guard = n(&profile, "resolution_guard_mm", 0.)?;
    let rows = profile["curves"].as_array().unwrap();
    let sources = profile["reference_sources"].as_array().unwrap();
    let mut result = Vec::new();
    let mut i = 0;
    let mut total_poles = 0usize;
    while i < rows.len() {
        crate::protocol::control_check()?;
        if rows[i]["kind"] != "cubic" {
            result.push(rows[i].clone());
            i += 1;
            continue;
        }
        let row = &rows[i];
        let source = row["source"].as_u64().ok_or("Missing native CAD source")? as usize;
        let start = n(&json!({"t":row["domain"][0]}), "t", 0.)?;
        let mut end = n(&json!({"t":row["domain"][1]}), "t", 0.)?;
        let mut j = i + 1;
        while j < rows.len()
            && rows[j]["kind"] == "cubic"
            && rows[j]["source"] == row["source"]
            && rows[j]["mirror"] == row["mirror"]
            && rows[j]["rotation_rad"] == row["rotation_rad"]
        {
            end = n(&json!({"t":rows[j]["domain"][1]}), "t", 0.)?;
            j += 1;
        }
        let definition = &sources[source];
        let curve = if definition["kind"] == "rack_corner" {
            Curve::Rack(
                serde_json::from_value(definition["tool"].clone()).map_err(|e| e.to_string())?,
                n(definition, "rotation", 0.)?,
            )
        } else if definition["orientation"] == 1. {
            Curve::InternalInvolute {
                rb: n(definition, "base_radius_mm", 0.)?,
                offset: n(definition, "offset_rad", 0.)?,
            }
        } else {
            Curve::Involute {
                rb: n(definition, "base_radius_mm", 0.)?,
                offset: n(definition, "offset_rad", 0.)?,
            }
        };
        let mut fits = uniform_fit(
            &curve,
            start.min(end),
            start.max(end),
            (tolerance - guard) / 2.,
            0,
        )?;
        let reverse = end < start;
        if reverse {
            fits.reverse();
        }
        for UniformSpline {
            controls: points,
            mut domain,
            bound,
        } in fits
        {
            let mut points: Vec<_> = points
                .into_iter()
                .map(|p| {
                    transformed(
                        p,
                        row["mirror"] == true,
                        n(row, "rotation_rad", 0.).unwrap(),
                    )
                })
                .collect();
            if reverse {
                points.reverse();
                domain.reverse();
            }
            total_poles = total_poles
                .checked_add(points.len())
                .ok_or("Native CAD pole count overflow")?;
            if total_poles > 500_000 || result.len() >= MAX_SEGMENTS {
                return Err("Native CAD curve/pole budget exhausted; accuracy not met.".into());
            }
            result.push(json!({"kind":"uniform_cubic","controls":points,"degree":3,"domain":domain,
                "source":source,"mirror":row["mirror"],"rotation_rad":row["rotation_rad"],"interpolation_bound_mm":bound}));
        }
        i = j;
    }
    let mut bound: f64 = 0.;
    let mut join: f64 = 0.;
    for i in 0..result.len() {
        let prev = (i + result.len() - 1) % result.len();
        let key = if result[prev]["kind"] == "uniform_cubic" {
            "controls"
        } else {
            "endpoints"
        };
        let p: Point = serde_json::from_value(
            result[prev][key]
                .as_array()
                .unwrap()
                .last()
                .unwrap()
                .clone(),
        )
        .unwrap();
        let key = if result[i]["kind"] == "uniform_cubic" {
            "controls"
        } else {
            "endpoints"
        };
        let q: Point = serde_json::from_value(result[i][key][0].clone()).unwrap();
        let delta = [p[0] - q[0], p[1] - q[1]];
        let distance = radius(delta);
        if !distance.is_finite() || distance > 2. * guard {
            return Err("Native CAD source join exceeds its resolution guard.".into());
        }
        if key == "controls" {
            let tangent: Point = serde_json::from_value(result[i][key][1].clone()).unwrap();
            result[i][key][1] = json!([tangent[0] + delta[0], tangent[1] + delta[1]]);
        }
        result[i][key][0] = json!(p);
        result[i]["join_displacement_mm"] = json!(distance);
        join = join.max(distance);
        bound = bound.max(n(&result[i], "interpolation_bound_mm", 0.)? + distance);
    }
    if bound + guard > tolerance {
        return Err("Native CAD source exceeded its requested error budget.".into());
    }
    profile["curves"] = json!(result);
    profile["curve_interpolation_bound_mm"] = json!(bound);
    profile["maximum_join_displacement_mm"] = json!(join);
    profile["native_poles"] = json!(total_poles);
    profile["knot_convention"] = json!(
        "clamped open-uniform cubic on [0,1]; n=control_count-3 spans, end multiplicity4, internal simple knots j/n"
    );
    profile["arithmetic"] = json!(
        "binary64 analytic fourth-derivative bound for complete clamped open-uniform cubic curves; endpoint tangents retained; not certified interval arithmetic"
    );
    Ok(profile)
}

#[cfg(test)]
mod tangent_tests {
    use super::*;
    #[test]
    fn circumscribed_internal_involute_keeps_curve_inside_void() {
        let rb = 40.;
        let offset = 0.2;
        let (points, bound) = paired_internal_samples(rb, offset, 41., 45., 0.001).unwrap();
        assert!(bound <= 0.001 && points.len() > 3);
        let curve = Curve::InternalInvolute { rb, offset };
        for i in 0..points.len() - 1 {
            let p = points[i];
            let q = points[i + 1];
            let edge = [q[0] - p[0], q[1] - p[1]];
            // A fine independent polar oracle must remain on the void side
            // of every local supporting tangent segment.
            for k in 0..=1000 {
                let radius = 41. + 4. * k as f64 / 1000.;
                let t = ((radius / rb).powi(2) - 1.).sqrt();
                let source = curve.value_tangent(t).0;
                let projection = ((source[0] - p[0]) * edge[0] + (source[1] - p[1]) * edge[1])
                    / (edge[0] * edge[0] + edge[1] * edge[1]);
                if (0. ..=1.).contains(&projection) {
                    assert!(edge[0] * (source[1] - p[1]) - edge[1] * (source[0] - p[0]) >= -1e-11);
                }
            }
        }
    }
    #[test]
    fn angular_bound_does_not_alias_multiple_tangent_revolutions() {
        let c = Curve::InternalInvolute { rb: 1., offset: 0. };
        assert!(c.tangent_turn_bound(0.1, TAU + 0.2) > TAU);
        assert!(paired_internal_samples(1., 0., 1.01, 1.1, 1e-20).is_err());
    }
}
