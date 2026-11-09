// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Opt-in qualification of the constructed, unloaded cylindrical pair.
//!
//! ISO 21771:2007 5.4.1, 5.4.7 and 5.5: usable involute domains, contact
//! coverage, and backlash. Continuous clearance includes a whole-curve error
//! enclosure; dense probes are not used as a clearance certificate. This is
//! deliberately not a cutting, loaded-contact or manufacturing certificate.
use crate::{
    precision::Result,
    profiles::{Point, n, radius},
};
use serde_json::{Value, json};
use std::f64::consts::{PI, TAU};

const MAX_POINTS: usize = 120_000;

struct Boundary {
    points: Vec<Point>,
    roots: Vec<usize>,
    enclosure: f64,
    guard: f64,
    metadata: Value,
}

fn distance(a: Point, b: Point) -> f64 {
    radius([a[0] - b[0], a[1] - b[1]])
}

fn midpoint(a: Point, b: Point) -> Point {
    [(a[0] + b[0]) / 2., (a[1] + b[1]) / 2.]
}

fn split(c: [Point; 4]) -> ([Point; 4], [Point; 4]) {
    let a = midpoint(c[0], c[1]);
    let b = midpoint(c[1], c[2]);
    let d = midpoint(c[2], c[3]);
    let e = midpoint(a, b);
    let f = midpoint(b, d);
    let g = midpoint(e, f);
    ([c[0], a, e, g], [g, f, d, c[3]])
}

fn line_bound(c: [Point; 4]) -> f64 {
    // Express the chord with the same cubic Bernstein basis. The convex hull
    // of the four difference controls bounds the pointwise interpolation error
    // on the WHOLE interval, including both directions of Hausdorff distance.
    (1..3)
        .map(|i| {
            let t = i as f64 / 3.;
            distance(
                c[i],
                [
                    (1. - t) * c[0][0] + t * c[3][0],
                    (1. - t) * c[0][1] + t * c[3][1],
                ],
            )
        })
        .fold(0., f64::max)
}

impl Boundary {
    fn append(&mut self, p: Point, root: bool, error: f64) -> Result<()> {
        if self.points.len() >= MAX_POINTS {
            return Err("Mechanical verification exceeds its 120000-point boundary budget; accuracy was not met.".into());
        }
        if root {
            self.roots.push(self.points.len());
        }
        self.points.push(p);
        self.enclosure = self.enclosure.max(error);
        Ok(())
    }

    fn cubic(
        &mut self,
        c: [Point; 4],
        fit_error: f64,
        tolerance: f64,
        root: bool,
        depth: u8,
    ) -> Result<()> {
        crate::protocol::control_check()?;
        let error = fit_error + line_bound(c);
        if error + self.guard <= tolerance {
            return self.append(c[0], root, error);
        }
        if depth >= 24 {
            return Err(
                "Mechanical boundary refinement depth exhausted; accuracy was not met.".into(),
            );
        }
        let (a, b) = split(c);
        self.cubic(a, fit_error, tolerance, root, depth + 1)?;
        self.cubic(b, fit_error, tolerance, root, depth + 1)
    }

    fn from_reference(args: &Value, tolerance: f64) -> Result<Self> {
        let mut args = args.clone();
        args["tolerance_mm"] = json!(tolerance / 4.);
        let reference = crate::cad_curves::cylindrical(&args)?;
        let mut out = Self {
            points: Vec::new(),
            roots: Vec::new(),
            enclosure: 0.,
            guard: n(&reference, "resolution_guard_mm", 0.)?,
            metadata: reference["source_profile"].clone(),
        };
        for row in reference["curves"]
            .as_array()
            .ok_or("Missing mechanical curve recipe")?
        {
            let join = n(row, "join_displacement_mm", 0.)?;
            if row["kind"] == "cubic" {
                let controls: [Point; 4] =
                    serde_json::from_value(row["controls"].clone()).map_err(|e| e.to_string())?;
                let source = row["source"].as_u64().ok_or("Missing curve source")? as usize;
                let root = reference["reference_sources"][source]["kind"] == "rack_corner";
                out.cubic(
                    controls,
                    n(row, "interpolation_bound_mm", 0.)? + join,
                    tolerance,
                    root,
                    0,
                )?;
            } else {
                let center: Point =
                    serde_json::from_value(row["center_mm"].clone()).map_err(|e| e.to_string())?;
                let endpoints: [Point; 2] =
                    serde_json::from_value(row["endpoints"].clone()).map_err(|e| e.to_string())?;
                let r = n(row, "radius_mm", 0.)?;
                let angles: [f64; 2] =
                    serde_json::from_value(row["angles_rad"].clone()).map_err(|e| e.to_string())?;
                let mut pieces = 1usize;
                while (angles[1] - angles[0]).abs() / pieces as f64 > PI
                    || 2.
                        * r
                        * ((angles[1] - angles[0]) / (4. * pieces as f64))
                            .sin()
                            .powi(2)
                        + join
                        + out.guard
                        > tolerance
                {
                    pieces *= 2;
                    if pieces > MAX_POINTS {
                        return Err(
                            "Mechanical circular-boundary budget exhausted; accuracy was not met."
                                .into(),
                        );
                    }
                }
                let bound = 2.
                    * r
                    * ((angles[1] - angles[0]) / (4. * pieces as f64))
                        .sin()
                        .powi(2)
                    + join;
                let root = row["reference"] != "tip_circle";
                for i in 0..pieces {
                    let t = angles[0] + (angles[1] - angles[0]) * i as f64 / pieces as f64;
                    let p = if i == 0 {
                        endpoints[0]
                    } else {
                        [center[0] + r * t.cos(), center[1] + r * t.sin()]
                    };
                    out.append(p, root, bound)?;
                }
            }
        }
        out.enclosure += out.guard;
        if out.points.len() < 3 || out.roots.is_empty() || out.enclosure > tolerance {
            return Err("Incomplete or unresolved mechanical boundary.".into());
        }
        Ok(out)
    }
}

fn wrap(a: f64, period: f64) -> f64 {
    (a + period / 2.).rem_euclid(period) - period / 2.
}

fn profile_args(a: &Value, mesh: &Value, second: bool) -> Value {
    let g = &mesh[if second { "gear2" } else { "gear1" }];
    let internal = second && mesh["internal"] == true;
    let mut args = json!({"z":g["teeth"],"mt":g["analytic_values"]["transverse_module_mm"],
        "depth":a.get("m").cloned().unwrap_or(json!(2.)),
        "pressure":g["analytic_values"]["transverse_pressure_angle_deg"],
        "normal_pressure":a.get("pressure").cloned().unwrap_or(json!(20.)),
        "backlash":mesh["nominal_pair_backlash_mm"],"shift":g["x"],
        "ha":1.,"hf":1.25,"internal":internal,"phase":0.});
    if internal && !a["internal_plan"].is_null() {
        args["ha"] = a["internal_plan"]["ring_addendum_coefficient"].clone();
        args["minimum_join_radius_mm"] = a["internal_plan"]["minimum_join_radius_mm"].clone();
    }
    if !second {
        args["rack_tip_radius_mm"] =
            g["analytic_values"]["generating_rack_normal_tip_radius_mm"].clone();
    }
    if let Some(tips) = a[if second { "tooth_tips2" } else { "tooth_tips1" }].as_object() {
        args.as_object_mut().unwrap().extend(tips.clone());
    }
    args
}

pub(crate) fn audit(a: &Value) -> Result<Value> {
    for key in ["internal", "double_helix"] {
        if a.get(key).is_some_and(|v| !v.is_boolean()) {
            return Err("Mechanical mesh topology flags must be booleans.".into());
        }
    }
    for (key, maximum) in [("budget", 16_384), ("max_depth", 20)] {
        if a.get(key)
            .is_some_and(|v| v.as_u64().is_none_or(|n| n > maximum))
        {
            return Err(
                "Mechanical limits must be integers within budget 16384 and depth 20.".into(),
            );
        }
    }
    let width = n(a, "width", 10.)?;
    let gap = n(a, "gap", 0.)?;
    let double = a["double_helix"] == true;
    if width <= 0. || gap < 0. || gap >= width || (!double && gap != 0.) {
        return Err(
            "Mechanical audit requires positive active width; a groove requires double helix."
                .into(),
        );
    }
    let effective = if double { (width - gap) / 2. } else { width };
    let tolerance = n(a, "profile_enclosure_mm", 0.0001)?;
    if tolerance <= 0. {
        return Err("Mechanical profile enclosure must be positive and finite.".into());
    }
    let mut parameters = a.clone();
    parameters["width"] = json!(effective);
    parameters["gap"] = json!(0.);
    let mesh = crate::engineering::mesh(&parameters)?;
    let internal = mesh["internal"] == true;
    let sign = if internal { -1. } else { 1. };
    let z1 = n(&mesh, "z1", 1.)?;
    let z2 = n(&mesh, "z2", 1.)?;
    let ratio = z1 / z2;
    let center = n(&mesh, "center_distance_mm", 0.)?;
    let scale = center / n(&mesh, "reference_center_mm", 1.)?;
    let aw = n(&mesh, "working_pressure_deg", 20.)?.to_radians();
    let beta = n(a, "beta", 0.)?.to_radians();
    let beta2 = n(a, "helix2_deg", -sign * beta.to_degrees())?.to_radians();
    if beta2.abs() >= PI / 2. {
        return Err(
            "Mechanical audit requires a finite second helix angle below 90 degrees.".into(),
        );
    }
    let rp1 = n(&mesh["gear1"], "pitch_radius", 1.)?;
    let rp2 = n(&mesh["gear2"], "pitch_radius", 1.)?;
    let rb1 = n(&mesh["gear1"], "base_radius", 1.)?;
    let rb2 = n(&mesh["gear2"], "base_radius", 1.)?;
    let working_backlash = n(&mesh, "working_pair_backlash_mm", 0.)?;
    let half_play = working_backlash / (2. * rp2 * scale);
    let guard = 4096. * f64::EPSILON * center.max(rp1).max(rp2).max(1.);
    let angle_guard = guard / rb2;
    let phase1 = n(a, "phase1_rad", 0.)?;
    let neutral_phase2 = if internal { PI / z2 } else { PI + PI / z2 };
    let phase2 = n(a, "phase2_rad", neutral_phase2)?;
    if phase1.abs().max(phase2.abs()) > TAU * 4. {
        return Err("Mechanical phase exceeds the angular evaluation budget; reduce it by whole revolutions.".into());
    }
    let phase_error = wrap(phase2 + sign * ratio * phase1 - neutral_phase2, TAU / z2);
    let phase_slope = beta2.tan() / rp2 + sign * ratio * beta.tan() / rp1;
    let end_error = phase_error + effective * phase_slope;
    let conjugate_helix = effective * phase_slope.abs() <= angle_guard;
    let phase_clear = phase_error.abs().max(end_error.abs()) <= half_play + angle_guard;
    let usable_total = n(&mesh, "profile_contact_total", 0.)?;
    let usable_transverse = n(&mesh, "profile_contact_transverse", 0.)?;
    // Axial overlap cannot restore a missing transverse contact interval.
    let contact = usable_transverse > 0. && usable_total >= 1.;
    let mut failures = Vec::new();
    if working_backlash < -guard {
        failures.push("negative working backlash");
    }
    if usable_transverse <= 0. {
        failures.push("usable involute intervals do not overlap");
    } else if !contact {
        failures.push("usable involute coverage below one tooth period");
    }
    if !conjugate_helix {
        failures.push("helical section phases do not preserve the signed mesh ratio");
    }
    if !phase_clear {
        failures.push("assembly phases lie outside the available backlash band");
    }
    let mut out = json!({"schema":"ratiolab.cylindrical-mechanical-audit/1","status":"unresolved",
        "scope":"ideal unchanged cylindrical pair; analytic usable involute coverage and phase compatibility, continuous neutral clearance and operating root-trace separation",
        "arithmetic":"binary64 analytic bounds with explicit resolution guards; not certified interval arithmetic",
        "mesh":mesh,"covered_checks_passed":false,"failures":failures,
        "coverage":{"status":if contact {"covered"}else{"gap"},"basis":"continuous interval length / base pitch, with axial phase sweep on one active helix",
            "tooth_period_rad":TAU/z1,"usable_total":usable_total,"uncovered_fraction":(1.-usable_total).max(0.),
            "active_facewidth_mm":effective,"double_helix":double},
        "phase":{"status":if phase_clear && conjugate_helix {"compatible"}else{"incompatible"},
            "phase1_rad":phase1,"phase2_rad":phase2,"neutral_phase2_rad":neutral_phase2,
            "signed_speed_ratio":-sign*ratio,"error_at_start_rad":phase_error,"error_at_end_rad":end_error,
            "half_backlash_angle_gear2_rad":half_play,"section_phase_slope_rad_per_mm":phase_slope,
            "operating_gear2_offsets_from_neutral_rad":[-half_play,half_play],"resolution_guard_rad":angle_guard},
        "neutral_clearance":null,"operating_root_clearance":[],
        "unqualified":["full loaded tip/flank interference and elastic contact", "actual cutter envelope, cutting and assembly interference", "manufacturing tolerances, strength, durability and lubrication", "CAD/STL axial interpolation, shoulders, hubs, shafts and supports"],
        "internal_root":if internal {"tangent-circle construction; not a pinion-cutter envelope"}else{"rounded normal-rack envelope; no selected commercial cutter"}});
    if !out["failures"].as_array().unwrap().is_empty() {
        out["status"] = json!("failed");
        return Ok(out);
    }
    let p = Boundary::from_reference(&profile_args(a, &out["mesh"], false), tolerance)?;
    let r = Boundary::from_reference(&profile_args(a, &out["mesh"], true), tolerance)?;
    let roll = |rad: f64, base: f64| (rad * rad - base * base).max(0.).sqrt();
    let low1 = roll(
        n(
            &p.metadata["measurement_geometry"],
            "involute_start_radius_mm",
            0.,
        )?,
        rb1,
    );
    let high1 = roll(
        n(
            &p.metadata["measurement_geometry"],
            "involute_end_radius_mm",
            0.,
        )?,
        rb1,
    );
    let low2 = roll(
        n(
            &r.metadata["measurement_geometry"],
            "involute_start_radius_mm",
            0.,
        )?,
        rb2,
    );
    let high2 = roll(
        n(
            &r.metadata["measurement_geometry"],
            "involute_end_radius_mm",
            0.,
        )?,
        rb2,
    );
    let span = center * aw.sin();
    let lower = low1.max(if internal { low2 - span } else { span - high2 });
    let upper = high1.min(if internal { high2 - span } else { span - low2 });
    let pitch = TAU * rb1 / z1;
    if ((upper - lower).max(0.) / pitch - n(&out["mesh"], "profile_contact_transverse", 0.)?).abs()
        > 8. * guard / pitch
    {
        return Err(
            "Constructed curve domains disagree with the reported usable contact path.".into(),
        );
    }
    let half1 = n(
        &p.metadata["measurement_geometry"],
        "reference_half_angle_rad",
        0.,
    )?;
    let half2 = n(
        &r.metadata["measurement_geometry"],
        "reference_half_angle_rad",
        0.,
    )?;
    let at = n(&out["mesh"]["gear1"], "alpha_t", 20.)?.to_radians();
    let inv = crate::profiles::inv_roll(at.tan());
    out["involute"] = json!({"base_pitch_mm":pitch,"base_radii_mm":[rb1,rb2],
        "reference_half_angles_rad":[half1,half2],"flank_offsets_rad":[half1+inv,half2+if internal {-inv}else{inv}],
        "usable_roll1_interval_mm":[lower,upper],"usable_roll2_interval_mm":if internal {[lower+span,upper+span]}else{[span-upper,span-lower]},
        "path_length_mm":(upper-lower).max(0.),"line_of_action_unit":[aw.sin(),aw.cos()],
        "working_pitch_radii_mm":[rp1*scale,rp2*scale],
        "relation":if internal {"roll2 = roll1 + a sin(alpha_w)"}else{"roll2 = a sin(alpha_w) - roll1"}});
    let enclosure = p.enclosure + r.enclosure;
    let mut verify = json!({"planet_loop":p.points,"ring_void":r.points,
        "zp":z1,"zr":z2,"phaseP":phase1,"phaseR":phase2,
        "center_distance_mm":center,"numeric_guard_mm":guard,
        "budget":a.get("budget").cloned().unwrap_or(json!(4096)),
        "max_depth":a.get("max_depth").cloned().unwrap_or(json!(20))});
    let mut neutral =
        crate::internal_mesh::separate(&verify, internal, None, None, enclosure, true)?;
    neutral["scope"] = json!(
        "continuous separation of the two source transverse boundaries at the supplied free-backlash phases; includes curve-to-polygon enclosures"
    );
    let mut clear = neutral["status"] == "clear";
    let mut collision = neutral["status"] == "collision";
    out["neutral_clearance"] = neutral;
    let mut roots = Vec::new();
    for side in [-1., 1.] {
        // Close either working flank by rotating wheel 2. Do not silently use
        // neutral gaps as evidence about the operating root geometry.
        verify["phaseR"] = json!(neutral_phase2 - sign * ratio * phase1 + side * half_play);
        for member in [1, 2] {
            let mut check = crate::internal_mesh::separate(
                &verify,
                internal,
                if member == 1 { Some(&p.roots) } else { None },
                if member == 2 { Some(&r.roots) } else { None },
                enclosure,
                false,
            )?;
            check["scope"] = json!(
                "continuous separation of this member's root-circle/fillet traces from the mating complete transverse boundary over a tooth period at one operating flank"
            );
            check["root_member"] = json!(member);
            check["operating_side"] = json!(side as i32);
            clear &= check["status"] == "clear";
            collision |= check["status"] == "collision";
            roots.push(check);
        }
    }
    out["operating_root_clearance"] = json!(roots);
    out["boundaries"] = json!({"requested_enclosure_per_member_mm":tolerance,
        "enclosure_mm":[p.enclosure,r.enclosure],"combined_enclosure_mm":enclosure,
        "points":[p.points.len(),r.points.len()],"root_segments":[p.roots.len(),r.roots.len()],
        "basis":"analytic Hermite remainder + positive Bernstein control hull for cubic/chord difference; exact circular sagitta; joins and resolution guards included"});
    out["covered_checks_passed"] = json!(clear);
    if collision {
        out["failures"].as_array_mut().unwrap().push(json!(
            "source-boundary interference outside approximation enclosures"
        ));
    }
    out["status"] = json!(if collision {
        "failed"
    } else if clear {
        "passed_with_limits"
    } else {
        "unresolved"
    });
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn cubic_hull_catches_a_deviation_missed_at_the_midpoint() {
        let c = [[0., 0.], [1., 1.], [2., -1.], [3., 0.]];
        assert_eq!(line_bound(c), 1.);
        let (a, b) = split(c);
        assert!(line_bound(a) < line_bound(c));
        assert!(line_bound(b) < line_bound(c));
        assert_eq!(a[3], b[0]);
    }
}
