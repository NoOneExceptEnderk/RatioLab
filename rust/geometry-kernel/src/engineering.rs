// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Working cylindrical pair and useful generated involute intervals.
//! ISO21771:2007 sec.5 contact ratios; allowances follow the published model.
use crate::{precision::Result, profiles::n};
use serde_json::{Value, json};
use std::f64::consts::PI;
fn f(v: &Value, key: &str) -> f64 {
    v[key]
        .as_f64()
        .or_else(|| v[key].as_str().and_then(|s| s.parse().ok()))
        .expect("validated internal numeric field")
}
fn raw(a: &Value, key: &str, default: f64) -> Value {
    a.get(key)
        .filter(|v| !v.is_null())
        .cloned()
        .unwrap_or_else(|| json!(default))
}
pub fn dimensions(a: &Value) -> Result<Value> {
    let args = json!({"teeth":a["z"],"module":a["m"],"pressure":raw(a,"pressure",20.),"helix":raw(a,"beta",0.),
        "profile_shift":raw(a,"x",0.),"addendum":raw(a,"ha",1.),"dedendum":raw(a,"hf",1.25),"backlash":raw(a,"backlash",0.15),"rack_tip_radius_mm":a["rack_tip_radius_mm"],"topping_mm":raw(a,"topping_mm",0.),"internal":a["internal"].as_bool().unwrap_or(false)});
    let r = crate::protocol::request(
        &json!({"protocol":1,"operation":"cylindrical_dimensions","parameters":args}),
    )?;
    let e = &r["values"];
    Ok(
        json!({"teeth":a["z"],"mn":n(a,"m",2.)?,"mt":f(e,"transverse_module_mm"),"alpha_n":n(a,"pressure",20.)?,"alpha_t":f(e,"transverse_pressure_angle_deg"),"beta":n(a,"beta",0.)?,"x":n(a,"x",0.)?,"internal":args["internal"],
        "pitch_radius":f(e,"pitch_radius_mm"),"base_radius":f(e,"base_radius_mm"),"tip_radius":f(e,"tip_radius_mm"),"root_radius":f(e,"root_radius_mm"),
        "virtual_teeth":f(e,"virtual_teeth"),"minimum_shift":f(e,"minimum_shift"),"rack_minimum_shift":f(e,"rack_minimum_shift"),"normal_thickness":f(e,"normal_reference_arc_mm"),
        "nominal_reference_normal_thickness_mm":f(e,"normal_reference_arc_mm"),"reference_normal_thickness_with_allowance_mm":f(e,"normal_reference_arc_with_allowance_mm"),
        "nominal_reference_transverse_thickness_mm":f(e,"transverse_reference_arc_mm"),"reference_transverse_thickness_with_allowance_mm":f(e,"transverse_reference_arc_with_allowance_mm"),
        "reference_thickness_basis":"theoretical reference arcs; useful generated involute must be checked separately","analytic_values":e,"analytic_precision":r["precision"]}),
    )
}
fn usable(
    g: &mut Value,
    ring: bool,
    plan: &Value,
    m: f64,
    backlash: f64,
    pressure: f64,
    tips: &Value,
) -> Result<f64> {
    let treatment = crate::tooth_tips::Treatment::read(tips)?;
    let info = if ring && !plan.is_null() && !treatment.enabled() {
        plan["ring_profile"].clone()
    } else {
        let mut args = json!({"z":g["teeth"],"mt":g["mt"],"pressure":g["alpha_t"],"backlash":backlash,"depth":m,"shift":if ring{0.}else{f(g,"x")},"normal_pressure":pressure,"ha":if ring&&!plan.is_null(){plan["ring_addendum_coefficient"].clone()}else{json!(1.)},"hf":1.25,"endpoints":true,
            "minimum_join_radius_mm":if ring{plan["minimum_join_radius_mm"].clone()}else{Value::Null},
            "rack_tip_radius_mm":g["analytic_values"]["generating_rack_normal_tip_radius_mm"]});
        if let Some(fields) = tips.as_object() {
            args.as_object_mut().unwrap().extend(fields.clone());
        }
        crate::profiles::call(
            if ring {
                "internal_half"
            } else {
                "external_half"
            },
            &args,
        )?["metadata"]
            .clone()
    };
    if treatment.enabled() {
        g["tip_treatment"] = info["tip_treatment"].clone();
        g["active_tip_radius"] = info["tip_treatment"]["active_tip_radius_mm"].clone();
    }
    g["tooth_thickness"] = info["tooth_thickness"].clone();
    g["wildhaber_span"] = crate::measurement::call(
        "measurement_span",
        &json!({"geometry":info["measurement_geometry"]}),
    )?;
    g["over_gauges"] = crate::measurement::call(
        "measurement_default",
        &json!({"geometry":info["measurement_geometry"]}),
    )?;
    let limit = if ring {
        f(&info, "involute_end_radius_mm")
    } else {
        f(&info, "involute_start_radius_mm")
    };
    Ok((limit * limit - f(g, "base_radius").powi(2)).max(0.).sqrt())
}
pub(crate) fn mesh(a: &Value) -> Result<Value> {
    let z1 = n(a, "z1", 20.)?;
    let z2 = n(a, "z2", 60.)?;
    let m = n(a, "m", 2.)?;
    let pressure = n(a, "pressure", 20.)?;
    let beta = n(a, "beta", 0.)?;
    let width = n(a, "width", 10.)?;
    let x = n(a, "x", 0.)?;
    let extra = n(a, "center_extra", 0.)?;
    let gap = n(a, "gap", 0.)?;
    let backlash = n(a, "backlash", 0.)?;
    let internal = a["internal"].as_bool().unwrap_or(false);
    let plan = &a["internal_plan"];
    let tips1 = &a["tooth_tips1"];
    let tips2 = &a["tooth_tips2"];
    let modified = crate::tooth_tips::Treatment::read(tips1)?.enabled()
        || crate::tooth_tips::Treatment::read(tips2)?.enabled();
    let paired_rho = a
        .get("pinion_rack_tip_radius_mm")
        .filter(|v| !v.is_null())
        .unwrap_or(&plan["pinion_rack_tip_radius_mm"]);
    let strict = a["strict"].as_bool().unwrap_or(true);
    if z1 < 3.
        || z2 < 3.
        || z1 > 1000000.
        || z2 > 1000000.
        || z1.fract() != 0.
        || z2.fract() != 0.
        || m <= 0.
        || width <= 0.
        || gap < 0.
        || gap >= width
        || backlash < 0.
    {
        return Err("Invalid cylindrical pair dimensions".into());
    }
    if internal && x != 0. {
        return Err(
            "Internal pairs require zero profile shift in the current construction.".into(),
        );
    }
    let mut a1 = dimensions(
        &json!({"z":z1 as u64,"m":raw(a,"m",2.),"pressure":raw(a,"pressure",20.),"beta":raw(a,"beta",0.),"x":raw(a,"x",0.),"backlash":raw(a,"backlash",0.),"rack_tip_radius_mm":paired_rho,"topping_mm":tips1["topping_mm"]}),
    )?;
    let mut a2 = dimensions(
        &json!({"z":z2 as u64,"m":raw(a,"m",2.),"pressure":raw(a,"pressure",20.),"beta":raw(a,"beta",0.),"x":if internal{json!(0.)}else{json!({"expression":["neg",raw(a,"x",0.)]})},"backlash":raw(a,"backlash",0.),"internal":internal,
            "ha":if plan["construction_version"]=="fixed_internal_rack_pair_v1"{plan["ring_addendum_coefficient"].clone()}else{json!(1.)},"topping_mm":tips2["topping_mm"]}),
    )?;
    if !plan.is_null() {
        if plan["construction_version"] == "fixed_internal_rack_pair_v1"
            && plan["pinion_rack_tip_radius_mm"] != *paired_rho
        {
            return Err("Fixed internal plan does not match the pinion generating rack.".into());
        }
        let expected = json!({"zp":z1 as u64,"zr":z2 as u64,"mn":m,"alpha_n_deg":pressure,"beta_deg":beta,"backlash_mm":backlash});
        let matching = plan["construction_inputs"]
            .as_object()
            .is_some_and(|inputs| {
                inputs.len() == expected.as_object().unwrap().len()
                    && expected.as_object().unwrap().iter().all(|(key, value)| {
                        inputs.get(key).and_then(Value::as_f64) == value.as_f64()
                    })
            });
        if !internal || !matching || x != 0. || extra != 0. {
            return Err("Paired internal plan does not match the mesh construction inputs.".into());
        }
        for value in [
            &plan["ring_tip_radius_mm"],
            &plan["ring_profile"]["involute_end_radius_mm"],
        ] {
            if value.as_f64().is_none_or(|v| !v.is_finite()) {
                return Err("Incomplete paired internal plan".into());
            }
        }
        a2["tip_radius"] = plan["ring_tip_radius_mm"].clone();
        if crate::tooth_tips::Treatment::read(tips2)?.enabled() {
            a2 = dimensions(
                &json!({"z":z2 as u64,"m":raw(a,"m",2.),"pressure":raw(a,"pressure",20.),
                "beta":raw(a,"beta",0.),"x":0.,"internal":true,"ha":plan["ring_addendum_coefficient"],
                "backlash":raw(a,"backlash",0.),"topping_mm":tips2["topping_mm"]}),
            )?;
        }
    }
    let r1 = f(&a1, "pitch_radius");
    let r2 = f(&a2, "pitch_radius");
    let at = f(&a1, "alpha_t").to_radians();
    let a0 = if internal { r2 - r1 } else { r1 + r2 };
    let distance = a0 + extra;
    if distance <= 0. || a0 * at.cos() > distance {
        return Err("Centre distance incompatible with the base circles.".into());
    }
    let aw = (a0 * at.cos() / distance).acos();
    let ra1 = f(&a1, "tip_radius");
    let rb1 = f(&a1, "base_radius");
    let ra2 = f(&a2, "tip_radius");
    let rb2 = f(&a2, "base_radius");
    if ra1 <= rb1 || ra2 <= rb2 {
        return Err("Tip circle below the base circle: unsupported gear pair.".into());
    }
    let g1 = (ra1 * ra1 - rb1 * rb1).sqrt();
    let g2 = (ra2 * ra2 - rb2 * rb2).sqrt();
    let path = if internal {
        g1 - g2 + distance * aw.sin()
    } else {
        g1 + g2 - distance * aw.sin()
    };
    let ea = path / (PI * f(&a1, "mt") * at.cos());
    let effective = if gap != 0. { (width - gap) / 2. } else { width };
    let eb = effective * beta.to_radians().sin().abs() / (PI * m);
    // Subtract the two actual tooth arcs from the working transverse pitch.
    // Increasing the distance opens an external mesh and closes an internal
    // mesh. The latter uses a difference of reference radii, not their sum.
    let added = if internal && extra == 0. {
        // The reference-distance correction is exactly zero; avoid inventing
        // internal backlash changes from the acos(cos(alpha)) round trip.
        0.
    } else {
        (if internal { -1. } else { 1. })
            * 2.
            * distance
            * (crate::profiles::inv_roll(aw.tan()) - crate::profiles::inv_roll(at.tan()))
    };
    let working_backlash = backlash * distance / a0 + added;
    if internal && working_backlash < 0. {
        return Err("Negative working backlash in the internal pair: reduce centre distance or increase tooth allowance.".into());
    }
    let mut warnings = Vec::new();
    if ea <= 0. {
        return Err("No usable involute contact path.".into());
    }
    if ea + eb < 1. {
        return Err(
            "Total contact ratio below 1: increase tooth count/width or reduce centre distance."
                .into(),
        );
    }
    if !internal && g1.max(g2) > distance * aw.sin() + 1e-9 {
        return Err(
            "Interference below the base circle: increase tooth counts or apply profile shift."
                .into(),
        );
    }
    if internal {
        if z2 - z1 <= 9. {
            return Err("Internal ring: tooth count difference must exceed 9; closely spaced counts require a dedicated trochoidal check.".into());
        }
        if g2 < distance * aw.sin() {
            if strict {
                return Err("Internal involute interference at the pinion: increase planet/pinion tooth count.".into());
            }
            warnings.push("Internal involute interference: theoretical contact extends below the planet base circle. The generated root does not establish a valid internal contact path; increase tooth count or redesign the pair.".to_string());
        }
        if plan.is_null() || plan["construction_version"] == "fixed_internal_rack_pair_v1" {
            warnings.push("Axial ring assembly; the tangent root construction is not a pinion-cutter envelope. Check involute, trochoid and trimming interference for the actual cutter.".into());
        }
    }
    for (i, g) in [&a1, &a2].iter().enumerate() {
        if internal && i == 1 {
            continue;
        }
        if f(g, "x") + 1e-9 < f(g, "rack_minimum_shift") {
            warnings.push(format!("Wheel {}: rounded-rack undercut; actual envelope and trimming are recorded per part.",i+1));
        }
    }
    let lower1 = usable(&mut a1, false, plan, m, backlash, pressure, tips1)?;
    let bound2 = usable(&mut a2, internal, plan, m, backlash, pressure, tips2)?;
    let active1 = n(&a1, "active_tip_radius", ra1)?;
    let active2 = n(&a2, "active_tip_radius", ra2)?;
    let primary1 = (active1 * active1 - rb1 * rb1).max(0.).sqrt();
    let primary2 = (active2 * active2 - rb2 * rb2).max(0.).sqrt();
    let span = distance * aw.sin();
    let lower = lower1.max(if internal {
        primary2 - span
    } else {
        span - primary2
    });
    let upper = primary1.min(if internal {
        bound2 - span
    } else {
        span - bound2
    });
    let usable_ea = (upper - lower).max(0.) / (PI * f(&a1, "mt") * at.cos());
    if modified && usable_ea + eb <= 1. + 1e-8 {
        return Err("Tooth tips leave an effective contact ratio of one or less; reduce topping or semitopping.".into());
    }
    let nominal_lower = if internal { g2 - span } else { span - g2 };
    let nominal_upper = g1;
    let nominal_within_profiles = nominal_lower + 1e-9 >= lower && nominal_upper <= upper + 1e-9;
    let head_lower = if internal {
        primary2 - span
    } else {
        span - primary2
    };
    let root_limited = lower > head_lower + 1e-9 || upper + 1e-9 < primary1;
    // Shortening the primary flank at the head is the requested treatment,
    // not itself a warning. Retain warnings for additional root restrictions.
    if !nominal_within_profiles && (!modified || root_limited) {
        warnings.push("Nominal tip-to-tip contact extends outside the generated usable involutes. Non-involute root contact may interfere even when the usable contact ratio exceeds one; qualify the paired root/tip geometry.".into());
    }
    if usable_ea + eb < 1. {
        warnings.push("Usable involute contact ratio after root trimming/blending is below 1; nominal tip/base-circle ratio overstates the active flank. Change tooth counts or tooth geometry to maintain continuous engagement.".into());
    }
    if plan["construction_version"] == "planetary_paired_involute_v1"
        && plan["verification"]["status"] != "clear"
    {
        warnings.push(format!(
            "Planetary internal polygon clearance unresolved: {}",
            plan["verification"]["failure_reason"]
                .as_str()
                .unwrap_or("missing verification")
        ));
    }
    let mut out = json!({"profile_contact_transverse":usable_ea,"profile_contact_total":usable_ea+eb,
        "nominal_contact_within_usable_involutes":nominal_within_profiles,
        "profile_contact_basis":"intersection of usable involute intervals after root envelope/blend; excludes fillet contact, elastic deflection and 3D interference",
        "z1":z1 as u64,"z2":z2 as u64,"internal":internal,"center_distance_mm":distance,"reference_center_mm":a0,"working_pressure_deg":aw.to_degrees(),
        "contact_transverse":ea,"contact_overlap":eb,"contact_total":ea+eb,"extra_backlash_mm":added,"nominal_pair_backlash_mm":backlash,"working_pair_backlash_mm":working_backlash,
        "gear1":a1,"gear2":a2,"warnings":warnings});
    if !plan.is_null() {
        out["internal_pair_construction"] = plan.clone();
    }
    if modified {
        out["profile_contact_basis"] = json!(
            "intersection of primary involute intervals after roots and tip treatments; excludes semitopping, fillet contact, elastic deflection and 3D interference"
        );
    }
    Ok(out)
}
pub fn call(op: &str, a: &Value) -> Result<Value> {
    match op {
        "engineering_dimensions" => dimensions(a),
        "engineering_mesh" => mesh(a),
        "engineering_forces" => {
            let torque = n(a, "torque", 1.)?;
            let diameter = n(a, "diameter", 1.)?;
            let pressure = n(a, "pressure", 20.)?;
            let beta = n(a, "beta", 0.)?;
            if diameter <= 0. {
                return Err("Positive pitch diameter required".into());
            }
            let ft = 2000. * torque.abs() / diameter;
            Ok(
                json!({"tangential_N":ft,"radial_N":ft*pressure.to_radians().tan(),"axial_N":ft*beta.to_radians().tan()}),
            )
        }
        _ => Err("Unknown engineering operation".into()),
    }
}
