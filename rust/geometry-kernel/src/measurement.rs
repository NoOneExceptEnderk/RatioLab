// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! ISO21771:2007 A.2.1 A.6/A.9; A.5-A.7 A.42-A.48. Constructed
//! usable involute bounds are respected; no gauge tolerance/strength claim.
use crate::{
    precision::Result,
    profiles::{inv_roll, n},
};
use serde::Deserialize;
use serde_json::{Value, json};
use std::f64::consts::PI;
#[derive(Deserialize)]
struct Geometry {
    teeth: u32,
    reference_radius_mm: f64,
    base_radius_mm: f64,
    reference_half_angle_rad: f64,
    transverse_pressure_angle_rad: f64,
    helix_angle_abs_deg: f64,
    internal: bool,
    involute_start_radius_mm: f64,
    involute_end_radius_mm: f64,
    root_radius_mm: f64,
    tip_radius_mm: f64,
}
impl Geometry {
    fn read(v: &Value) -> Result<Self> {
        let g: Self = serde_json::from_value(v.clone()).map_err(|e| e.to_string())?;
        if g.teeth < 3
            || g.teeth > 1000000
            || ![
                g.reference_radius_mm,
                g.base_radius_mm,
                g.reference_half_angle_rad,
                g.transverse_pressure_angle_rad,
                g.helix_angle_abs_deg,
                g.involute_start_radius_mm,
                g.involute_end_radius_mm,
                g.root_radius_mm,
                g.tip_radius_mm,
            ]
            .iter()
            .all(|v| v.is_finite())
        {
            return Err("Invalid constructed involute geometry for measurement.".into());
        }
        Ok(g)
    }
    fn valid(&self) -> Result<()> {
        let rb = self.base_radius_mm;
        let rp = self.reference_radius_mm;
        let lo = self.involute_start_radius_mm;
        let hi = self.involute_end_radius_mm;
        let at = self.transverse_pressure_angle_rad;
        if !(0. < at && at < PI / 2. && 0. < rb && rb <= rp && rb <= lo && lo <= hi) {
            return Err("Invalid constructed involute geometry for measurement.".into());
        }
        Ok(())
    }
}
fn span(g: &Geometry) -> Result<Value> {
    let mut out = json!({"supported":false,"status":"unsupported","usable_spans":[],"recommended_k":null,
        "scope":"external spur cylindrical involute; symmetric flat jaws; theoretical dimensions only",
        "basis":"ISO 21771:2007 A.2.1 equations (A.6), (A.9); actual allowance-reduced profile; no gauge tolerances or strength assessment"});
    if g.internal {
        out["reason"] = json!("Internal flat-jaw span measurement is not supported.");
        return Ok(out);
    }
    if g.helix_angle_abs_deg.abs() > 1e-7 {
        out["reason"] =
            json!("Helical flat-jaw span and usable-facewidth checks are not supported.");
        return Ok(out);
    }
    g.valid()?;
    let z = g.teeth as f64;
    let rb = g.base_radius_mm;
    let rp = g.reference_radius_mm;
    let half = g.reference_half_angle_rad;
    let at = g.transverse_pressure_angle_rad;
    let lower = g.involute_start_radius_mm;
    let upper = g.involute_end_radius_mm;
    let inv_at = inv_roll(at.tan());
    let pb = 2. * PI * rb / z;
    let sb = 2. * rb * (half + inv_at);
    let tolerance = upper.max(rp) * 1e-10;
    let mut spans = Vec::new();
    let mut best = (f64::INFINITY, u32::MAX);
    for k in 1..=g.teeth {
        let w = (k - 1) as f64 * pb + sb;
        if w <= 0. {
            continue;
        }
        let roll = w / (2. * rb);
        let radius = rb.hypot(w / 2.);
        if !(lower - tolerance <= radius && radius <= upper + tolerance) {
            continue;
        }
        let ca = roll.atan();
        let flank = half + inv_at - inv_roll(roll);
        if !(0. < flank && flank < PI / z) {
            continue;
        }
        spans.push(json!({"k":k,"span_mm":w,"contact_radius_mm":radius,"contact_diameter_mm":2.*radius,"contact_pressure_angle_rad":ca,"contact_roll":roll,
            "root_margin_mm":(radius-lower).max(0.),"tip_margin_mm":(upper-radius).max(0.)}));
        let candidate = ((radius - rp).abs(), k);
        if candidate < best {
            best = candidate;
        }
    }
    out["supported"] = json!(true);
    out["status"] = json!(if spans.is_empty() {
        "no_usable_span"
    } else {
        "ok"
    });
    out["recommended_k"] = if spans.is_empty() {
        Value::Null
    } else {
        json!(best.1)
    };
    out["reason"] = json!(if spans.is_empty() {
        "No integer tooth span has symmetric contacts on both useful involute flanks."
    } else {
        ""
    });
    out["usable_spans"] = json!(spans);
    out["recommendation_basis"] = json!("usable contact radius nearest the reference circle");
    out["base_pitch_mm"] = json!(pb);
    out["base_tooth_thickness_mm"] = json!(sb);
    out["involute_start_radius_mm"] = json!(lower);
    out["involute_end_radius_mm"] = json!(upper);
    Ok(out)
}
fn inverse(value: f64) -> f64 {
    let (mut lo, mut hi) = (0., PI / 2. - 1e-12);
    for _ in 0..100 {
        let mid = (lo + hi) / 2.;
        if inv_roll(mid.tan()) < value {
            lo = mid
        } else {
            hi = mid
        }
    }
    (lo + hi) / 2.
}
fn reject(mut result: Value, status: &str, reason: &str) -> Value {
    result["status"] = json!(status);
    result["reason"] = json!(reason);
    result
}
fn gauges(g: &Geometry, diameter: f64, kind: &str) -> Result<Value> {
    if !["ball", "roller"].contains(&kind) {
        return Err("Gauge type must be ball or roller.".into());
    }
    if !diameter.is_finite() || diameter <= 0. {
        return Err("Gauge diameter must be a positive finite length in mm.".into());
    }
    let mut out = json!({"supported":false,"status":"unsupported","dimension_mm":null,"gauge_type":kind,"gauge_diameter_mm":diameter,
        "scope":"external/internal spur involute; balls or axial cylindrical rollers; theoretical dimensions only",
        "basis":"ISO 21771:2007 A.5 equations (A.42)-(A.46), A.6, A.7 equations (A.47)-(A.48); actual allowance-reduced profile",
        "contact_type":"point contact for balls; axial line contact for rollers",
        "gauge_note":"Spur balls and axial rollers have the same theoretical transverse dimension. Conservative root/tip-circle clearance may exclude usable gauges; finite gauge length, axial access, tolerances and elastic contact are not calculated."});
    if g.helix_angle_abs_deg.abs() > 1e-7 {
        out["reason"] = json!(
            "Helical/double-helical balls and rollers require distinct 3D contact and placement calculations and are not supported."
        );
        return Ok(out);
    }
    g.valid()?;
    let z = g.teeth as f64;
    let rb = g.base_radius_mm;
    let rp = g.reference_radius_mm;
    let half = g.reference_half_angle_rad;
    let at = g.transverse_pressure_angle_rad;
    let lower = g.involute_start_radius_mm;
    let upper = g.involute_end_radius_mm;
    let root = g.root_radius_mm;
    let tip = g.tip_radius_mm;
    let internal = g.internal;
    if !(0. < half
        && half < PI / z
        && if internal {
            0. < tip && tip < root
        } else {
            0. < root && root < tip
        })
    {
        return Err("Invalid constructed involute geometry for gauge measurement.".into());
    }
    out["supported"] = json!(true);
    out["internal"] = json!(internal);
    out["teeth"] = json!(g.teeth);
    out["parity"] = json!(if g.teeth % 2 == 1 { "odd" } else { "even" });
    out["dimension_kind"] = json!(if internal {
        "between gauges"
    } else {
        "over gauges"
    });
    let db = 2. * rb;
    let inv_at = inv_roll(at.tan());
    let eta = PI / z - half + if internal { inv_at } else { -inv_at };
    let target = if internal {
        eta - diameter / db
    } else {
        diameter / db - eta
    };
    if target < 0. {
        return Ok(reject(
            out,
            "no_solution",
            if internal {
                "No nonnegative centre-pressure involute solution exists; the negative internal branch exceeds local concave flank curvature and penetrates the tooth."
            } else {
                "No nonnegative centre-pressure involute solution exists for this external gauge diameter."
            },
        ));
    }
    let ak = inverse(target);
    let roll = ak.tan()
        + if internal {
            diameter / db
        } else {
            -diameter / db
        };
    if internal && diameter / 2. >= rb * roll - rp.max(upper) * 1e-12 {
        return Ok(reject(
            out,
            "no_seating",
            "The gauge radius reaches or exceeds the local concave involute curvature radius; a stable symmetric seat is unavailable.",
        ));
    }
    if roll <= 0. {
        return Ok(reject(
            out,
            "reverse_contact",
            "The solution contacts the reverse involute branch, outside the generated profile.",
        ));
    }
    let contact = rb * 1f64.hypot(roll);
    let centre = rb / ak.cos();
    let tolerance = rp.max(upper).max(diameter) * 1e-10;
    out["centre_circle_diameter_mm"] = json!(2. * centre);
    out["centre_pressure_angle_rad"] = json!(ak);
    out["contact_roll"] = json!(roll);
    out["contact_radius_mm"] = json!(contact);
    out["contact_diameter_mm"] = json!(2. * contact);
    out["contact_pressure_angle_rad"] = json!(roll.atan());
    out["involute_start_radius_mm"] = json!(lower);
    out["involute_end_radius_mm"] = json!(upper);
    if contact < lower - tolerance || contact > upper + tolerance {
        let at_root = if internal {
            contact > upper
        } else {
            contact < lower
        };
        return Ok(reject(
            out,
            if at_root {
                "root_or_fillet_contact"
            } else {
                "beyond_tip"
            },
            if at_root {
                "Contact lies in the root/blend region, outside the useful involute."
            } else {
                "Contact lies beyond the tooth tip, outside the useful involute."
            },
        ));
    }
    let flank = half
        + if internal {
            inv_roll(roll) - inv_at
        } else {
            inv_at - inv_roll(roll)
        };
    if !(0. < flank && flank < PI / z) {
        return Ok(reject(
            out,
            "no_seating",
            "The symmetric contact falls outside the actual tooth-space flanks.",
        ));
    }
    let r = diameter / 2.;
    if if internal {
        centre + r > root + tolerance
    } else {
        centre - r < root - tolerance
    } {
        return Ok(reject(
            out,
            "root_intersection",
            "The gauge intersects the root-circle envelope and cannot seat on these two involute contacts.",
        ));
    }
    let separation = 2.
        * centre
        * if g.teeth % 2 == 1 {
            (PI / (2. * z)).cos()
        } else {
            1.
        };
    if if internal {
        separation / 2. - r >= tip - tolerance
    } else {
        separation / 2. + r <= tip + tolerance
    } {
        return Ok(reject(
            out,
            "hidden_gauge",
            "Parallel-jaw clearance past the tooth-tip circle is not established by this conservative check; a potentially usable gauge may be excluded.",
        ));
    }
    if separation <= diameter + tolerance {
        return Ok(reject(
            out,
            "gauge_overlap",
            "The two measuring gauges overlap or touch each other.",
        ));
    }
    out["status"] = json!("ok");
    out["reason"] = json!("");
    out["dimension_mm"] = json!(separation + if internal { -diameter } else { diameter });
    out["gauge_centre_separation_mm"] = json!(separation);
    out["root_margin_mm"] = json!(if internal {
        upper - contact
    } else {
        contact - lower
    });
    out["tip_margin_mm"] = json!(if internal {
        contact - lower
    } else {
        upper - contact
    });
    Ok(out)
}
fn default_gauge(g: &Geometry) -> Result<Value> {
    if g.helix_angle_abs_deg.abs() > 1e-7 {
        return gauges(g, 1., "ball");
    }
    let rb = g.base_radius_mm;
    let lower = g.involute_start_radius_mm;
    let upper = g.involute_end_radius_mm;
    let at = g.transverse_pressure_angle_rad;
    let half = g.reference_half_angle_rad;
    let z = g.teeth as f64;
    let internal = g.internal;
    let inv_at = inv_roll(at.tan());
    let eta = PI / z - half + if internal { inv_at } else { -inv_at };
    for contact in [
        g.reference_radius_mm.clamp(lower, upper),
        (lower + upper) / 2.,
    ] {
        let roll = ((contact / rb).powi(2) - 1.).max(0.).sqrt();
        let alpha = if internal { roll - eta } else { roll + eta };
        if !(0. < alpha && alpha < PI / 2.) {
            continue;
        }
        let diameter = 2.
            * rb
            * if internal {
                eta - inv_roll(alpha.tan())
            } else {
                inv_roll(alpha.tan()) + eta
            };
        if diameter > 0. {
            let mut out = gauges(g, diameter, "ball")?;
            out["diameter_selection_basis"] = json!(
                "target useful involute contact nearest the reference circle, then interval midpoint; not a stock gauge size"
            );
            if out["status"] == "ok" {
                return Ok(out);
            }
        }
    }
    Ok(
        json!({"supported":true,"status":"no_default_gauge","dimension_mm":null,
        "reason":"No accessible default gauge was found at the reference or midpoint contact; choose a diameter explicitly.","scope":"external/internal spur involute","basis":"ISO 21771:2007 A.5-A.7"}),
    )
}
pub fn call(op: &str, a: &Value) -> Result<Value> {
    let g = Geometry::read(&a["geometry"])?;
    match op {
        "measurement_span" => span(&g),
        "measurement_gauges" => gauges(
            &g,
            n(a, "diameter_mm", 0.)?,
            a["gauge_type"].as_str().unwrap_or("ball"),
        ),
        "measurement_default" => default_gauge(&g),
        _ => Err("Unknown measurement operation".into()),
    }
}
