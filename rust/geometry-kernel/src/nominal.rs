// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Source recipes in mm, +Z gear axes and right-handed world coordinates.
//! CAD reconstruction never consumes preview vertices or triangles. Source
//! decimals/expressions survive until the shared cylindrical analytic kernel.
use crate::{precision::Result, profiles::n};
use serde_json::{Value, json};
use std::f64::consts::PI;
struct Envelope {
    z0: f64,
    z1: f64,
    radius: f64,
    center: [f64; 2],
    shaft: usize,
    stage: Option<usize>,
}

pub(crate) fn raw(v: &Value, key: &str, default: f64) -> Value {
    v.get(key)
        .filter(|x| !x.is_null())
        .cloned()
        .unwrap_or(json!(default))
}
pub(crate) fn key(name: &str, stage: usize) -> String {
    if stage == 1 {
        name.into()
    } else {
        format!("{name}{stage}")
    }
}
pub(crate) fn stages(v: &Value) -> usize {
    match v["variant"].as_str().unwrap_or("spur") {
        "two_stage" | "two_stage_helical" | "two_stage_double" => 2,
        "three_stage" | "three_stage_helical" | "three_stage_double" => 3,
        _ => 1,
    }
}
pub(crate) fn teeth_type(v: &Value) -> &str {
    let s = v["variant"].as_str().unwrap_or("spur");
    if s.ends_with("double") {
        "double"
    } else if s.ends_with("helical") {
        "helical"
    } else {
        "spur"
    }
}
pub(crate) fn parallel_rates(v: &Value) -> Result<Value> {
    let count = stages(v);
    let mut ratio = 1.;
    for stage in 1..=count {
        let zp = n(v, &key("pinion", stage), 20.)?;
        let zw = n(v, &key("wheel", stage), 60.)?;
        if zp <= 0. || zw <= 0. || zp.fract() != 0. || zw.fract() != 0. {
            return Err("Positive integer parallel tooth counts required".into());
        }
        ratio *= -zw / zp;
    }
    let input = n(v, "input_rpm", 1500.)?;
    let first = if v["io_scheme"] == "reverse" {
        input * ratio
    } else {
        input
    };
    let mut rates = vec![first];
    for stage in 1..=count {
        rates.push(
            -rates[stage - 1] * n(v, &key("pinion", stage), 20.)?
                / n(v, &key("wheel", stage), 60.)?,
        );
    }
    if !ratio.is_finite() || rates.iter().any(|r| !r.is_finite()) {
        return Err("Parallel operating rates overflow".into());
    }
    Ok(json!({"forward_ratio":ratio,"shaft_rates_rpm":rates}))
}
fn gear(
    name: String,
    p: Value,
    center: [f64; 2],
    z: f64,
    phase: f64,
    shaft: usize,
    stage: usize,
) -> Value {
    json!({"id":name,"name":name,"kind":"cylindrical_gear","parameters":p,
        "placement":{"center_mm":center,"z_mm":z,"phase_rad":phase},
        "port":{"shaft":shaft,"stage":stage,"rigid_group":format!("parallel_shaft_{shaft}")}})
}
fn round(
    name: String,
    radius: f64,
    bore: f64,
    width: f64,
    center: [f64; 2],
    z: f64,
    shaft: usize,
) -> Value {
    json!({"id":name,"name":name,"kind":"circular_extrusion",
        "parameters":{"radius_mm":radius,"bore_radius_mm":bore,"width":width},
        "placement":{"center_mm":center,"z_mm":z,"phase_rad":0.},
        "port":{"shaft":shaft,"rigid_group":format!("parallel_shaft_{shaft}")}})
}
pub(crate) fn parallel(v: &Value) -> Result<Value> {
    let count = stages(v);
    if count == 1 {
        return Err("Nominal compound plan requires two or three parallel stages.".into());
    }
    if v["bearing_mode"].as_str().is_some_and(|x| x != "manual")
        || v["hardware_mode"].as_str().is_some_and(|x| x != "none")
    {
        return Err("Multistage parallel shafts use manual shaft dimensions.".into());
    }
    let kind = teeth_type(v);
    let double = kind == "double";
    let mut bores = vec![n(v, "bore", 6.)?];
    for s in 1..count {
        bores.push(n(v, &format!("intermediate_bore{s}"), 8.)?);
    }
    bores.push(n(v, "output_bore", 8.)?);
    if bores.iter().any(|x| *x <= 0.) {
        return Err("Multistage trains require positive shaft diameters.".into());
    }
    let gap = n(v, "stage_gap", 2.)?;
    let extension = n(v, "shaft_extension", 8.)?;
    let wall = n(v, "hub_wall", 2.)?;
    if gap <= 0. || extension < 0. || wall <= 0. {
        return Err("Invalid multistage gap, hub or extension.".into());
    }
    let mut centers = vec![[0., 0.]];
    let mut levels = Vec::new();
    let mut angles = Vec::new();
    let mut meshes = Vec::new();
    let mut parts = Vec::new();
    let mut angle = 0.;
    let mut level = 0.;
    let mut ratio = 1.;
    for stage in 1..=count {
        crate::protocol::control_check()?;
        let k = |s: &str| key(s, stage);
        let zp = n(v, &k("pinion"), 20.)?;
        let zw = n(v, &k("wheel"), 60.)?;
        let m = n(v, &k("module"), 2.)?;
        let width = n(v, &k("width"), 10.)?;
        let backlash = n(v, &k("backlash"), 0.15)?;
        let beta = if kind == "spur" {
            json!(0.)
        } else {
            raw(v, &k("helix"), 20.)
        };
        let groove = if double { n(v, &k("gap"), 0.)? } else { 0. };
        if zw <= zp || backlash >= 0.7 * m || groove < 0. || double && groove >= width - 1. {
            return Err(format!(
                "Stage {stage}: invalid reduction, backlash or double-helix groove."
            ));
        }
        let active = if double { (width - groove) / 2. } else { width };
        let tips1 = crate::tooth_tips::member(v, &k("pinion"));
        let tips2 = crate::tooth_tips::member(v, &k("wheel"));
        let mut q = crate::engineering::mesh(&json!({"z1":zp,"z2":zw,"m":raw(v,&k("module"),2.),
            "pressure":raw(v,&k("pressure"),20.),"beta":beta,"width":active,"x":raw(v,&k("profile_shift"),0.),
            "center_extra":raw(v,&k("center_extra"),0.),"backlash":raw(v,&k("backlash"),0.15),
            "tooth_tips1":tips1,"tooth_tips2":tips2}))?;
        let b = n(&json!({"beta":beta}), "beta", 0.)?;
        if kind != "spur" {
            q["gear2"]["beta"] = json!(-b);
            q["pinion_helix_deg"] = json!(b);
            q["wheel_helix_deg"] = json!(-b);
            q["active_face_width_mm"] = json!(active);
        }
        q["stage"] = json!(stage);
        q["torque_factor"] = Value::Null;
        if stage > 1 {
            angle += n(v, &k("layout_angle"), 0.)?.to_radians();
        }
        let a = n(&q, "center_distance_mm", 0.)?;
        let previous = *centers.last().unwrap();
        centers.push([previous[0] + a * angle.cos(), previous[1] + a * angle.sin()]);
        angles.push(angle);
        levels.push([level, level + width]);
        for (label, z, shaft, phase, negative) in [
            ("Pinion", zp, stage - 1, 0., false),
            (
                "Wheel",
                zw,
                stage,
                (zp + zw) * angle / zw + PI + PI / zw,
                true,
            ),
        ] {
            let root = n(
                &q[if negative { "gear2" } else { "gear1" }],
                "root_radius",
                0.,
            )?;
            if bores[shaft] / 2. >= root - 0.5 {
                return Err(format!(
                    "Stage {stage} {label}: shaft bore leaves insufficient tooth-root material."
                ));
            }
            let shift = raw(v, &k("profile_shift"), 0.);
            let mut p = json!({"z":z,"m":raw(v,&k("module"),2.),"pressure":raw(v,&k("pressure"),20.),
                "backlash":raw(v,&k("backlash"),0.15),"width":raw(v,&k("width"),10.),"bore":bores[shaft],
                "helix":if negative{json!({"expression":["neg",beta]})}else{beta.clone()},
                "shift":if negative{json!({"expression":["neg",shift]})}else{shift},"ha":1.,"hf":1.25,
                "internal":false,"double":double,"gap":groove});
            p.as_object_mut().unwrap().extend(
                if negative { &tips2 } else { &tips1 }
                    .as_object()
                    .unwrap()
                    .clone(),
            );
            parts.push(gear(
                format!("S{stage}_{label}"),
                p,
                centers[shaft],
                level,
                phase,
                shaft,
                stage,
            ));
        }
        level += width + gap;
        ratio *= -zw / zp;
        meshes.push(q);
    }
    for shaft in 0..=count {
        let lo = levels[shaft.saturating_sub(1)][0];
        let hi = levels[(count - 1).min(shaft)][1];
        parts.push(round(
            format!("Shaft_{}", shaft + 1),
            bores[shaft] / 2.,
            0.,
            hi - lo + 2. * extension,
            centers[shaft],
            lo - extension,
            shaft,
        ));
        if shaft > 0 && shaft < count {
            let r = bores[shaft] / 2. + wall;
            let root = n(&meshes[shaft - 1]["gear2"], "root_radius", 0.)?.min(n(
                &meshes[shaft]["gear1"],
                "root_radius",
                0.,
            )?);
            if r >= root - 0.25 {
                return Err(format!(
                    "Intermediate shaft {shaft}: connecting hub exceeds the available tooth-root radius."
                ));
            }
            let z0 = levels[shaft - 1][1];
            parts.push(round(
                format!("Compound_{shaft}_Hub"),
                r,
                bores[shaft] / 2.,
                levels[shaft][0] - z0,
                centers[shaft],
                z0,
                shaft,
            ));
        }
    }
    let clearance = n(v, "assembly_clearance", 0.2)?;
    if clearance <= 0. {
        return Err("Positive nonmating envelope clearance required.".into());
    }
    let envelope = |part: &Value| -> Result<Envelope> {
        let p = &part["parameters"];
        let place = &part["placement"];
        let z = n(place, "z_mm", 0.)?;
        let center: [f64; 2] =
            serde_json::from_value(place["center_mm"].clone()).map_err(|e| e.to_string())?;
        let shaft = part["port"]["shaft"]
            .as_u64()
            .ok_or("Missing shaft identity")? as usize;
        let stage = part["port"]["stage"].as_u64().map(|s| s as usize);
        let r = if let Some(stage) = stage {
            n(
                &meshes[stage - 1][if shaft == stage { "gear2" } else { "gear1" }],
                "tip_radius",
                0.,
            )?
        } else {
            n(p, "radius_mm", 0.)?
        };
        Ok(Envelope {
            z0: z,
            z1: z + n(p, "width", 10.)?,
            radius: r,
            center,
            shaft,
            stage,
        })
    };
    let mut tested = 0;
    for (i, a) in parts.iter().enumerate() {
        crate::protocol::control_check()?;
        let ea = envelope(a)?;
        for b in &parts[i + 1..] {
            let eb = envelope(b)?;
            if ea.shaft == eb.shaft
                || ea.stage.is_some() && ea.stage == eb.stage
                || ea.z0.max(eb.z0) - ea.z1.min(eb.z1) >= clearance - 1e-9
            {
                continue;
            }
            tested += 1;
            if (ea.center[0] - eb.center[0]).hypot(ea.center[1] - eb.center[1])
                - ea.radius
                - eb.radius
                < clearance - 1e-9
            {
                return Err(format!(
                    "Multistage layout: {} and {} lack swept-envelope clearance. Change centre-line turns, shaft/hub diameters, stage widths or spacing.",
                    a["name"].as_str().unwrap(),
                    b["name"].as_str().unwrap()
                ));
            }
        }
    }
    Ok(
        json!({"schema":"ratiolab.nominal-plan/1","components":parts,"analysis":{"meshes":meshes,"signed_ratio":ratio,
        "parallel_train":{"stages":count,"shaft_centers_mm":centers,"shaft_diameters_mm":bores,"stage_levels_mm":levels,"centre_line_angles_rad":angles,
        "envelope_check":{"status":"clear","tested_pairs":tested,"clearance_mm":clearance,
            "scope":"Conservative swept cylinders of nonmating gears, shafts and hubs; intended meshes and same-shaft interfaces excluded. No tooth-contact, load or tolerance certification."}}}}),
    )
}

/// Derive the CAD input from the same high-precision normal-system dimensions
/// as preview construction. No fitted mesh or rounded transverse UI value.
pub(crate) fn cylindrical_source(a: &Value) -> Result<Value> {
    let p = &a["parameters"];
    let width = n(p, "width", 10.)?;
    if p["double"] == true {
        return Err(
            "Direct CAD double-helix reconstruction is not yet qualified; no mesh fallback.".into(),
        );
    }
    let dims = crate::protocol::request(
        &json!({"protocol":1,"operation":"cylindrical_dimensions","parameters":{
        "teeth":p["z"],"module":p["m"],"pressure":raw(p,"pressure",20.),"helix":raw(p,"helix",0.),
        "profile_shift":raw(p,"shift",0.),"addendum":raw(p,"ha",1.),"dedendum":raw(p,"hf",1.25),
        "backlash":raw(p,"backlash",0.15),"width":raw(p,"width",10.),"internal":p["internal"]==true,
        "rack_tip_radius_mm":p["rack_tip_radius_mm"],"topping_mm":raw(p,"topping_mm",0.),"cutter_allowance":p["cutter_allowance"]==true}}),
    )?;
    let e = &dims["values"];
    let bore = n(p, "bore", 0.)? / 2.;
    let internal = p["internal"] == true;
    let circular = if internal {
        n(e, "root_radius_mm", 0.)? + n(p, "rim", 5.)?
    } else {
        bore
    };
    let mut args = json!({"z":p["z"],"mt":e["transverse_module_mm"],"depth":p["m"],"pressure":e["transverse_pressure_angle_deg"],
        "normal_pressure":raw(p,"pressure",20.),"backlash":raw(p,"backlash",0.15),"shift":raw(p,"shift",0.),
        "ha":raw(p,"ha",1.),"hf":raw(p,"hf",1.25),"phase":raw(&a["placement"],"phase_rad",0.),"internal":internal,
        "width":width,"twist_deg":e["twist_deg"],"circular_radius_mm":circular,"tolerance_mm":a["tolerance_mm"],
        "minimum_join_radius_mm":p["minimum_join_radius_mm"],"safe_pair_sampling":p["safe_pair_sampling"],
        "rack_tip_radius_mm":e["generating_rack_normal_tip_radius_mm"]});
    for key in crate::tooth_tips::KEYS {
        if let Some(value) = p.get(key) {
            args[key] = value.clone();
        }
    }
    let mut geometry = if a["native_uniform_cubic"] == true {
        let profile = crate::cad_curves::native_cylindrical(&args)?;
        json!({"profile":profile,"internal":internal,"circular_radius_mm":circular,
            "sweep":{"width_mm":width,"twist_rad":n(e,"twist_deg",0.)?.to_radians(),
                "surface_interpolation_bound_mm":profile["curve_interpolation_bound_mm"]}})
    } else {
        crate::cad_sweeps::cylindrical(&args)?
    };
    geometry["analytic_values"] = e.clone();
    geometry["analytic_precision"] = dims["precision"].clone();
    Ok(geometry)
}
