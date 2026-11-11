// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Finite rack on +X and cylindrical pinion about +Z; KHK 4.5/4.13.
//! Nominal flanks and axial construction are shared by CAD and sampled solids.
use crate::geometry_data::{Construction, Part, Station};
use crate::nominal::raw;
use crate::{
    precision::Result,
    profiles::{Point, n, radius, rotate},
};
use serde_json::{Value, json};
use std::f64::consts::PI;
const REFINEMENT: f64 = 0.003;

fn rack_tips(v: &Value) -> Result<(crate::tooth_tips::Treatment, f64, f64, f64)> {
    let settings = crate::tooth_tips::member(v, "rack");
    let treatment = crate::tooth_tips::Treatment::read(&settings)?;
    let tip = treatment.tip(n(v, "module", 2.)?, 0., false)?;
    let active = tip - treatment.height;
    if treatment.height > 0. && treatment.angle_deg <= n(v, "pressure", 20.)? {
        return Err("Rack semitopping angle must exceed the normal pressure angle.".into());
    }
    let angle =
        (treatment.angle_deg.to_radians().tan() / n(v, "helix", 0.)?.to_radians().cos()).atan();
    Ok((treatment, tip, active, angle))
}

pub(crate) fn dimensions(v: &Value) -> Result<Value> {
    let m = n(v, "module", 2.)?;
    let z = n(v, "pinion", 24.)?;
    let count = n(v, "rack_teeth", 24.)?;
    let width = n(v, "width", 10.)?;
    let beta = n(v, "helix", 0.)?;
    let backlash = n(v, "backlash", 0.15)?;
    let base = n(v, "base", 6.)?;
    let bore = n(v, "bore", 6.)?;
    let variant = v["variant"].as_str().unwrap_or("spur");
    if !(12. ..=100.).contains(&z)
        || z.fract() != 0.
        || !(8. ..=200.).contains(&count)
        || count.fract() != 0.
        || m <= 0.
        || width <= 0.
        || base <= 0.
        || bore < 0.
        || backlash < 0.
        || beta.abs() > 35.
        || !["spur", "helical", "double"].contains(&variant)
        || variant == "spur" && beta != 0.
    {
        return Err("Invalid finite rack/pinion construction domain.".into());
    }
    let g = crate::engineering::dimensions(
        &json!({"z":z,"m":raw(v,"module",2.),"pressure":raw(v,"pressure",20.),
        "beta":raw(v,"helix",0.),"x":0.,"backlash":raw(v,"backlash",0.15),"topping_mm":raw(v,"pinion_topping_mm",0.)}),
    )?;
    let e = &g["analytic_values"];
    let mt = n(&g, "mt", 0.)?;
    let alpha = n(&g, "alpha_t", 0.)?.to_radians();
    let r = n(&g, "pitch_radius", 0.)?;
    let ra = n(&g, "tip_radius", 0.)?;
    let rb = n(&g, "base_radius", 0.)?;
    let root = n(&g, "root_radius", 0.)?;
    let pitch = PI * mt;
    let half = pitch / 4. - backlash / 4.;
    let (rack_treatment, rack_tip, rack_active, ramp_angle) = rack_tips(v)?;
    let top_half = half - rack_active * alpha.tan() - rack_treatment.height * ramp_angle.tan();
    if top_half <= 0. {
        return Err("Rack semitopping removes the entire tooth top land.".into());
    }
    if half - m * alpha.tan() <= 0.025 * m
        || half + 1.25 * m * alpha.tan() >= pitch / 2. - 0.025 * m
    {
        return Err(
            "Rack teeth are pointed or overlap at the roots; adjust pressure / backlash.".into(),
        );
    }
    if backlash >= 0.7 * m {
        return Err("Rack backlash must be less than 0.7 normal module.".into());
    }
    if bore / 2. >= root - 0.5 {
        return Err("Pinion bore leaves insufficient nominal root wall.".into());
    }
    let approach = r * alpha.sin() - m / alpha.sin();
    if approach <= 0. {
        return Err(
            "Rack tip reaches below the forward pinion involute; increase pinion teeth / pressure."
                .into(),
        );
    }
    let mut profile_args = json!({"z":z,"mt":e["transverse_module_mm"],
        "pressure":e["transverse_pressure_angle_deg"],"depth":m,"normal_pressure":raw(v,"pressure",20.),
        "backlash":backlash,"shift":0.,"ha":1.,"hf":1.25,"endpoints":true});
    profile_args.as_object_mut().unwrap().extend(
        crate::tooth_tips::member(v, "pinion")
            .as_object()
            .unwrap()
            .clone(),
    );
    let profile = crate::profiles::call("external_half", &profile_args)?;
    let start = n(&profile["metadata"], "involute_start_radius_mm", 0.)?;
    let contact_min = rb.hypot(approach);
    if contact_min < start + 1e-6 {
        return Err("Rack tip reaches the trimmed pinion root transition; increase pinion teeth / pressure.".into());
    }
    let active_pinion = n(&profile["metadata"], "involute_end_radius_mm", ra)?;
    let path = (active_pinion * active_pinion - rb * rb).sqrt() - r * alpha.sin()
        + rack_active / alpha.sin();
    let engagement = path / (pitch * alpha.cos());
    if engagement <= 1. + 1e-8 {
        return Err("Rack transverse ideal engagement must exceed one tooth pitch.".into());
    }
    let double = variant == "double";
    let gap = if double { n(v, "gap", 0.)? } else { 0. };
    let core = root * 0.96;
    if gap < 0. || double && gap >= width - 2. {
        return Err("Double rack groove must leave more than 1 mm per helical half.".into());
    }
    if double && bore / 2. >= core - 0.25 {
        return Err("Pinion bore reaches the continuous double-helix core.".into());
    }
    let sweep = beta.to_radians().tan() * if double { (width - gap) / 2. } else { width };
    // Tip treatments only remove material: retain the established conservative
    // motion envelope and finite travel limits instead of expanding the stroke.
    let footprint = ((r + m).powi(2) - (r - m).powi(2)).max(0.).sqrt();
    let travel = count * pitch / 2. - footprint - sweep.abs() - pitch;
    if travel <= pitch / 2. {
        return Err("Rack is too short for a complete safe working stroke; add rack teeth or reduce face width / helix.".into());
    }
    let mut result = json!({"pitch_radius_mm":r,"normal_module_mm":m,"transverse_module_mm":mt,
        "normal_pressure_deg":n(v,"pressure",20.)?,"transverse_pressure_deg":alpha.to_degrees(),
        "transverse_pitch_mm":pitch,"travel_per_revolution_mm":2.*PI*r,"travel_limits_mm":[-travel,travel],
        "pinion_angle_limits_rad":[-travel/r,travel/r],"nominal_contact_transverse":engagement,
        "rack_tip_contact_radius_mm":contact_min,"usable_pinion_involute_start_mm":start,"helix_sweep_mm":sweep,
        "rack_derived_hand":if beta>0.{-1}else if beta<0.{1}else{0},
        "analytic_values":e,"analytic_precision":g["analytic_precision"],"reference":"KHK Calculation of Gear Dimensions, tables4.5/4.13, equations4.2/4.18"});
    if rack_treatment.enabled() {
        result["rack_tip_treatment"] = json!({"topping_mm":rack_treatment.topping,"semitopping_mm":rack_treatment.height,
            "semitopping_angle_deg":rack_treatment.angle_deg,"finished_tip_height_mm":rack_tip,
            "active_tip_height_mm":rack_active,"top_land_width_mm":2.*top_half});
    }
    if !profile["metadata"]["tip_treatment"].is_null() {
        result["pinion_tip_treatment"] = profile["metadata"]["tip_treatment"].clone();
    }
    if rack_treatment.enabled() || !result["pinion_tip_treatment"].is_null() {
        result["contact_basis"] = json!(
            "Unchanged primary involute and straight rack flanks after tip treatments; excludes chamfer contact."
        );
    }
    Ok(result)
}

fn pinion_parameters(v: &Value) -> Value {
    let mut p = json!({"z":raw(v,"pinion",24.),"m":raw(v,"module",2.),"pressure":raw(v,"pressure",20.),
        "backlash":raw(v,"backlash",0.15),"width":raw(v,"width",10.),"bore":raw(v,"bore",6.),
        "helix":raw(v,"helix",0.),"shift":0.,"ha":1.,"hf":1.25,"internal":false,
        "double":v["variant"]=="double","gap":raw(v,"gap",0.)});
    p.as_object_mut().unwrap().extend(
        crate::tooth_tips::member(v, "pinion")
            .as_object()
            .unwrap()
            .clone(),
    );
    p
}

pub(crate) fn plan(v: &Value) -> Result<Value> {
    let info = dimensions(v)?;
    let count = n(v, "rack_teeth", 24.)?;
    let phase = -PI / 2.
        + if count as u64 % 2 == 1 {
            PI / n(v, "pinion", 24.)?
        } else {
            0.
        };
    Ok(
        json!({"schema":"ratiolab.nominal-plan/1","analysis":{"rack":info},"components":[
        {"id":"Rack_pinion","name":"Rack_pinion","kind":"cylindrical_gear","parameters":pinion_parameters(v),
            "placement":{"center_mm":[0.,info["pitch_radius_mm"]],"z_mm":0.,"phase_rad":phase},"port":{"member":"pinion","role":"input","axis":"World +Z"}},
        {"id":"Rack","name":"Rack","kind":"rack","parameters":v,
            "placement":{"center_mm":[0.,0.],"z_mm":0.,"phase_rad":0.},"port":{"member":"rack","role":"output","axis":"World +X"}}]}),
    )
}

pub(crate) fn outline(v: &Value, info: &Value, shift: f64, height: f64) -> Result<Vec<Point>> {
    let m = n(v, "module", 2.)?;
    let pitch = n(info, "transverse_pitch_mm", 0.)?;
    let alpha = n(info, "transverse_pressure_deg", 0.)?.to_radians();
    let root = -1.25 * m;
    let (treatment, tip, active, ramp_angle) = rack_tips(v)?;
    let half = pitch / 4. - n(v, "backlash", 0.15)? / 4.;
    let sweep = n(info, "helix_sweep_mm", 0.)?;
    let count = n(v, "rack_teeth", 24.)? as usize;
    let left = -(count as f64 + 1.) * pitch / 2. + sweep.min(0.);
    let right = (count as f64 + 1.) * pitch / 2. + sweep.max(0.);
    let mut top = Vec::with_capacity(4 * count);
    for j in 0..count {
        if j % 32 == 0 {
            crate::protocol::control_check()?;
        }
        let c = (j as f64 - (count as f64 - 1.) / 2.) * pitch + shift;
        let mut flank = vec![[c - half + root * alpha.tan(), root]];
        if treatment.height > 0. {
            flank.push([c - half + active * alpha.tan(), active]);
        }
        let top_half = half - active * alpha.tan() - treatment.height * ramp_angle.tan();
        if treatment.height > 0. {
            flank.extend([[c - top_half, tip], [c + top_half, tip]]);
        } else {
            // Retain the original evaluation order for legacy rack vertices.
            flank.extend([
                [c - half + tip * alpha.tan(), tip],
                [c + half - tip * alpha.tan(), tip],
            ]);
        }
        if treatment.height > 0. {
            flank.push([c + half - active * alpha.tan(), active]);
        }
        flank.push([c + half - root * alpha.tan(), root]);
        for [x, y] in flank {
            top.push([x, root + height * (y - root)]);
        }
    }
    let bottom = root - n(v, "base", 6.)?;
    let mut result = vec![[left, bottom], [right, bottom], [right, root]];
    result.extend(top.into_iter().rev());
    result.push([left, root]);
    Ok(result)
}

pub(crate) fn build(a: &Value) -> Result<Construction> {
    let v = &a["values"];
    let nominal = plan(v)?;
    let mut info = nominal["analysis"]["rack"].clone();
    let c = &nominal["components"][0];
    let mut args = c["parameters"].clone();
    args.as_object_mut().unwrap().remove("double");
    args.as_object_mut().unwrap().remove("gap");
    args["name"] = json!("Rack_pinion");
    args["center"] = c["placement"]["center_mm"].clone();
    args["phase"] = c["placement"]["phase_rad"].clone();
    let mut p = crate::profiles::gear_part(&args)?;
    let double = v["variant"] == "double";
    p["double"] = json!(double);
    p["gap"] = if double { raw(v, "gap", 0.) } else { json!(0.) };
    p["core_radius"] =
        json!((n(&info, "pitch_radius_mm", 0.)? - 1.25 * n(v, "module", 2.)?) * 0.96);
    // Explicit corresponding sections refine the same nominal landmark law,
    // independently from ordinary procedural preview tessellation.
    let source = crate::solid::Part::read(&p)?;
    let rows = source.sweep_landmarks()?;
    let tolerance = n(a, "refinement_mm", REFINEMENT)?.min(REFINEMENT);
    let guard = 1024. * f64::EPSILON * source.outer.iter().map(|p| radius(*p)).fold(1., f64::max);
    if tolerance <= guard {
        return Err("Rack axial request is below its binary64 resolution guard.".into());
    }
    let perimeter = source.outer.len() + source.holes.iter().map(Vec::len).sum::<usize>();
    let mut pin_stations = Vec::new();
    let mut rack_stations = Vec::new();
    for ((az, aa, oa), (bz, ab, ob)) in rows.iter().zip(&rows[1..]) {
        crate::protocol::control_check()?;
        let r = oa.iter().chain(ob).map(|p| radius(*p)).fold(0., f64::max);
        let delta = oa
            .iter()
            .zip(ob)
            .map(|(p, q)| (q[0] - p[0]).hypot(q[1] - p[1]))
            .fold(0., f64::max);
        let angle = (ab - aa).to_radians();
        let steps = ((r * angle * angle + 2. * delta * angle.abs()) / (8. * tolerance))
            .sqrt()
            .ceil()
            .max(1.) as usize;
        let total = pin_stations
            .len()
            .checked_add(steps)
            .ok_or("Rack station count overflow")?;
        let rack_perimeter = 4 * n(v, "rack_teeth", 24.)? as usize + 4;
        if total
            .checked_mul(2 * perimeter.max(rack_perimeter))
            .is_none_or(|n| n + 2 > 250_000)
        {
            return Err("Rack pinion surface budget exhausted; reduce teeth / face width / helix or request a coarser axial target.".into());
        }
        for j in 0..steps {
            crate::protocol::control_check()?;
            let f = j as f64 / steps as f64;
            let z = az + (bz - az) * f;
            let turn = aa + (ab - aa) * f;
            let loop_: Vec<_> = oa
                .iter()
                .zip(ob)
                .map(|(p, q)| {
                    rotate(
                        [p[0] + (q[0] - p[0]) * f, p[1] + (q[1] - p[1]) * f],
                        turn.to_radians(),
                    )
                })
                .collect();
            let height = if *oa == source.outer { 1. - f } else { 0. }
                + if *ob == source.outer { f } else { 0. };
            pin_stations.push(Station::new(z, loop_, source.holes.clone()));
            rack_stations.push(Station::new(
                z,
                outline(
                    v,
                    &info,
                    n(&info, "pitch_radius_mm", 0.)? * turn.to_radians(),
                    height,
                )?,
                vec![],
            ));
        }
    }
    let (z, angle, outer) = rows.last().ok_or("Rack pinion has no source sections")?;
    pin_stations.push(Station::new(
        *z,
        outer
            .iter()
            .map(|p| rotate(*p, angle.to_radians()))
            .collect(),
        source.holes.clone(),
    ));
    rack_stations.push(Station::new(
        *z,
        outline(
            v,
            &info,
            n(&info, "pitch_radius_mm", 0.)? * angle.to_radians(),
            if *outer == source.outer { 1. } else { 0. },
        )?,
        vec![],
    ));
    let initial = rack_stations[0].outer.clone();
    info["base_length_mm"] = json!(initial[1][0] - initial[0][0]);
    info["base_below_roots_mm"] = raw(v, "base", 6.);
    info["rack_teeth"] = raw(v, "rack_teeth", 24.);
    info["section_count"] = json!(pin_stations.len());
    info["refinement_mm"] = json!(tolerance);
    info["end_rule"] = json!("Complete teeth with fixed end planes and untoothed sweep lands");
    info["stroke_rule"] = json!(
        "Conservative finite stroke excludes active pinion footprint, helix sweep and one rack pitch"
    );
    let metadata = json!({"method":"Involute pinion / straight transverse rack flanks","reference":info["reference"]});
    p["profile_metadata"]["rack_pair"] = metadata.clone();
    let mut pin = Part::new("Rack_pinion", source.outer, source.holes, source.width);
    let mut extra = p.as_object().unwrap().clone();
    for key in ["outer", "holes", "outer_circle_radius"] {
        extra.remove(key);
    }
    extra.insert("color".into(), json!([0.96, 0.66, 0.33]));
    pin.extra = Value::Object(extra);
    pin.stations = pin_stations;
    let mut rack = Part::new("Rack", initial, vec![], source.width);
    rack.stations = rack_stations;
    rack.extra["color"] = json!([0.23, 0.75, 0.65]);
    let mut preview_parameters = json!({});
    for (key, default) in [
        ("module", 2.),
        ("pressure", 20.),
        ("backlash", 0.15),
        ("base", 6.),
        ("rack_teeth", 24.),
        ("helix", 0.),
        ("rack_topping_mm", 0.),
        ("rack_semitopping_mm", 0.),
        ("rack_semitopping_angle_deg", 45.),
    ] {
        preview_parameters[key] = raw(v, key, default);
    }
    rack.extra["profile_metadata"] = json!({"rack_pair":metadata,
        "tip_preview_source":{"kind":"linear","parameters":preview_parameters,"dimensions":{
            "transverse_pitch_mm":info["transverse_pitch_mm"],
            "transverse_pressure_deg":info["transverse_pressure_deg"],
            "helix_sweep_mm":info["helix_sweep_mm"]}}});
    Ok(Construction {
        parts: vec![pin, rack],
        extra: json!({"analysis":{"rack":info}}),
    })
}

pub(crate) fn cad(a: &Value) -> Result<Value> {
    let v = &a["parameters"];
    let info = dimensions(v)?;
    if v["variant"] == "double" {
        return Err(
            "Direct CAD relieved double rack is not yet qualified; no mesh fallback.".into(),
        );
    }
    let lower = outline(v, &info, 0., 1.)?;
    let upper = outline(v, &info, n(&info, "helix_sweep_mm", 0.)?, 1.)?;
    Ok(
        json!({"schema":"ratiolab.ruled-rack/1","lower":lower,"upper":upper,"width_mm":raw(v,"width",10.),
        "interpolation_bound_mm":0.,"arithmetic":"binary64 direct straight flanks and ruled axial traces; excludes roundoff and CAD reader tolerances"}),
    )
}
