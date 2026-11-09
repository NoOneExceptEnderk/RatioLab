// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Existing ZA/ZI screw and prescribed strain-wave solid constructions.
//! Placement, material coordinates and section topology are shared with exports.
use crate::geometry_data::{Construction, Part, Station};
use crate::{
    precision::Result,
    profiles::{Point, n, polar, radius},
    wave::Wave,
};
use serde_json::{Value, json};
use std::f64::consts::{PI, TAU};
fn points(v: &Value) -> Result<Vec<Point>> {
    serde_json::from_value(v.clone()).map_err(|e| e.to_string())
}
fn circle(r: f64, count: usize) -> Vec<Point> {
    (0..count)
        .map(|j| polar(r, TAU * j as f64 / count as f64))
        .collect()
}
fn circle_count(r: f64) -> Result<usize> {
    if !r.is_finite() || r <= 0. {
        return Err("Positive circle radius required".into());
    }
    let count = (PI / (1. - 0.002 / r).clamp(-1., 1.).acos()).ceil() as usize;
    if count > 1_000_000 {
        return Err("Circle sampling limit exceeded".into());
    }
    Ok(count.max(96))
}
fn round(r: f64) -> Result<Vec<Point>> {
    Ok(circle(r, circle_count(r)?))
}
fn material(loop_: &[Point], rp: f64, weight: f64) -> Vec<[f64; 3]> {
    loop_
        .iter()
        .map(|p| [p[1].atan2(p[0]), radius(*p) - rp, weight])
        .collect()
}
fn deform(w: &Wave, loop_: &[Point], rp: f64, weight: f64) -> Result<Vec<Point>> {
    loop_
        .iter()
        .enumerate()
        .map(|(i, p)| {
            if i % 128 == 0 {
                crate::protocol::control_check()?;
            }
            w.map(p[1].atan2(p[0]), radius(*p) - rp, weight, 0., 0.)
        })
        .collect()
}
fn part(name: &str, outer: Vec<Point>, holes: Vec<Vec<Point>>, width: f64) -> Part {
    Part::new(name, outer, holes, width)
}
fn worm(v: &Value) -> Result<Construction> {
    let m = n(v, "module", 2.)?;
    let teeth = n(v, "teeth", 40.)?;
    let starts = n(v, "starts", 1.)?;
    let diameter = n(v, "diameter", 20.)?;
    let length = n(v, "length", 30.)?;
    let width = n(v, "width", 10.)?;
    let bore = n(v, "bore", 0.)?;
    let hand = n(v, "worm_hand", 1.)?;
    let variant = v["variant"].as_str().ok_or("Missing worm variant")?;
    let pressure = n(v, "pressure", 20.)?;
    let backlash = n(v, "backlash", 0.15)?;
    if !["za", "zi"].contains(&variant)
        || m <= 0.
        || starts < 1.
        || starts.fract() != 0.
        || diameter <= 0.
        || length <= 0.
        || width <= 0.
        || bore < 0.
        || hand.abs() != 1.
    {
        return Err("Invalid screw construction domain".into());
    }
    let lead = PI * m * starts;
    let gamma = (m * starts / diameter).atan();
    let mn = m * gamma.cos();
    let an = (pressure.to_radians().tan() * gamma.cos())
        .atan()
        .to_degrees();
    let root = diameter / 2. - 1.25 * m;
    if root <= bore / 2. + 0.5 {
        return Err("Bore too large for the worm root diameter.".into());
    }
    let journal = n(v, "journal_length", 0.)?;
    let jr = n(v, "journal_diameter", 0.)? / 2.;
    if journal < 0. || journal > 0. && (jr > root || jr <= bore / 2. + 0.5) {
        return Err("Journals must fit between the bore and thread root, with at least 0.5 mm wall thickness.".into());
    }
    let (pa, j) = if variant == "za" {
        (pressure, backlash)
    } else {
        let beta = PI / 2. - gamma;
        (
            (an.to_radians().tan() / beta.cos()).atan().to_degrees(),
            backlash / gamma.tan(),
        )
    };
    let mut outline = points(&crate::worm::call(
        "worm_screw_profile",
        &json!({"starts":starts,"module":m,"diameter":diameter,"pressure":pa,"backlash":j,"variant":variant}),
    )?)?;
    let radius = diameter / 2. + m;
    let step = 6_f64.min((2. * (1. - 0.02 / radius).max(0.).acos()).to_degrees());
    let turns = length / lead;
    let count = (360. * turns / step).ceil().max(1.) as usize;
    let mut holes = if bore > 0. {
        vec![round(bore / 2.)?]
    } else {
        vec![]
    };
    if count > 250000
        || 2 * (outline.len() + holes.iter().map(Vec::len).sum::<usize>()) * (count + 6) > 250000
    {
        return Err("Worm too detailed (250,000 face limit): reduce length, diameter or starts, or increase module.".into());
    }
    let rotated = |height: f64, force: Option<f64>| {
        outline
            .iter()
            .map(|p| {
                polar(
                    force.unwrap_or_else(|| crate::profiles::radius(*p)),
                    p[1].atan2(p[0]) + TAU * (height - journal) / lead,
                )
            })
            .collect::<Vec<_>>()
    };
    let mut stations = Vec::new();
    if journal > 0. {
        let ring = rotated(journal, Some(jr));
        stations.push(Station::new(0., ring.clone(), holes.clone()));
        stations.push(Station::new(journal, ring, holes.clone()));
    }
    for j in 0..=count {
        crate::protocol::control_check()?;
        let height = journal + length * j as f64 / count as f64;
        stations.push(Station::new(height, rotated(height, None), holes.clone()));
    }
    if journal > 0. {
        let ring = rotated(journal + length, Some(jr));
        stations.push(Station::new(journal + length, ring.clone(), holes.clone()));
        stations.push(Station::new(2. * journal + length, ring, holes.clone()));
    }
    if hand < 0. {
        let mirror = |l: Vec<Point>| {
            l.into_iter()
                .rev()
                .map(|[x, y]| [x, -y])
                .collect::<Vec<_>>()
        };
        outline = mirror(outline);
        holes = holes.into_iter().map(&mirror).collect();
        for station in &mut stations {
            station.outer = mirror(std::mem::take(&mut station.outer));
            station.holes = holes.clone();
        }
    }
    let mut screw = part(
        &format!("Screw_{}", variant.to_uppercase()),
        outline,
        holes,
        length + 2. * journal,
    );
    screw.extra["twist"] = json!(hand * 360. * turns);
    screw.extra["axis_x"] = json!(true);
    screw.extra["color"] = json!([0.95, 0.65, 0.3]);
    screw.stations = stations;
    screw.extra["alternate_diagonal"] = json!(hand < 0.);
    screw.extra["profile_metadata"] = json!({"screw_profile":{"method":format!("{} cylindrical screw flanks",variant.to_uppercase()),"root_runout":"sharp radial root transition","conjugate_wheel":true}});
    let wheel_bore = n(v, "wheel_bore", 0.)?;
    let wheel_holes = if wheel_bore > 0. {
        vec![round(wheel_bore / 2.)?]
    } else {
        vec![]
    };
    let generated = crate::worm::wheel(v, wheel_holes.iter().map(Vec::len).sum())?;
    let sections = generated.sections;
    if sections.iter().any(|(_, l)| {
        wheel_bore / 2. + 0.25
            >= l.iter()
                .map(|p| crate::profiles::radius(*p))
                .fold(f64::INFINITY, f64::min)
    }) {
        return Err("Wheel bore too large for the generated tooth root.".into());
    }
    let outer = sections
        .iter()
        .min_by(|a, b| a.0.abs().total_cmp(&b.0.abs()))
        .ok_or("Empty worm wheel sections")?
        .1
        .clone();
    let mut wheel = part("Wheel_generated", outer, wheel_holes.clone(), width);
    wheel.extra["z"] = json!(-width / 2.);
    wheel.extra["center"] = json!([0., -(diameter + m * teeth) / 2.]);
    wheel.extra["color"] = json!([0.23, 0.68, 0.82]);
    wheel.extra["alternate_diagonal"] = json!(hand < 0.);
    wheel.stations = sections
        .into_iter()
        .map(|(z, l)| Station::new(z + width / 2., l, wheel_holes.clone()))
        .collect();
    wheel.extra["profile_metadata"] = json!({"wheel_envelope":generated.metadata});
    Ok(Construction {
        parts: vec![screw, wheel],
        extra: json!({"wheel_geometry":generated.metadata,"analysis":{"signed_ratio":hand*teeth/starts,"worm_axis":"+X","wheel_axis":"+Z","wheel_side":"negative Y","profile":variant.to_uppercase(),"lead_mm":lead,"lead_angle_deg":gamma.to_degrees(),"normal_module_mm":mn,"normal_pressure_deg":an,"center_distance_mm":(diameter+m*teeth)/2.,"thread_turns":turns,"thread_length_mm":length,"journal_length_mm":journal}}),
    })
}
fn harmonic(v: &Value) -> Result<Construction> {
    let z = n(v, "teeth", 60.)?;
    let m = n(v, "module", 2.)?;
    let rp = m * z / 2.;
    let root = rp - 1.25 * m;
    let inner = root - n(v, "wall", 1.)?;
    let width = n(v, "width", 10.)?;
    let length = n(v, "cup_length", 20.)?;
    let diaphragm = n(v, "diaphragm", 2.)?;
    let amplitude = m * n(v, "wave_factor", 1.)?;
    let bearing = n(v, "bearing_thickness", 2.)?;
    let clearance = n(v, "wave_clearance", 0.2)?;
    let bore = n(v, "bore", 0.)?;
    let variant = v["variant"]
        .as_str()
        .ok_or("Missing strain-wave construction variant")?;
    if !["cup", "flat_cup", "hat"].contains(&variant)
        || m <= 0.
        || z < 3.
        || z.fract() != 0.
        || width <= 0.
        || inner <= 0.
        || diaphragm < 0.
        || length <= 0.
    {
        return Err("Invalid strain-wave construction domain".into());
    }
    if diaphragm >= length - 1. {
        return Err("Diaphragm/flange too thick for the flexible body length.".into());
    }
    let axes = crate::planar::call(
        "planar_ellipse_axes",
        &json!({"radius":rp,"amplitude":amplitude}),
    )?;
    let [a, b]: [f64; 2] = serde_json::from_value(axes).map_err(|e| e.to_string())?;
    let wave = Wave::new(a, b, rp)?;
    if b - 1.25 * m - n(v, "wall", 1.)? - bearing - 2. * clearance <= bore / 2. + 0.5 {
        return Err("Bore/bearing too large for the wave generator; reduce bore, deformation or thicknesses.".into());
    }
    let gear_args = |backlash: Value, cutter: bool| json!({"name":"Flexspline","z":z,"m":v["module"],"pressure":v["pressure"],"backlash":backlash,"width":v["width"],"bore":0.,"center":[0.,0.],"phase":0.,"helix":0.,"internal":false,"rim":5.,"zoff":0.,"shift":0.,"ha":1.,"hf":1.25,"cutter_allowance":cutter});
    let gear = crate::profiles::gear_part(&gear_args(v["backlash"].clone(), false))?;
    let base_radius = root + n(v, "flange_width", 0.)?;
    let refined = crate::planar::call(
        "planar_refine_angles",
        &json!({"points":gear["outer"],"radius":base_radius.max(rp+m+amplitude)}),
    )?;
    let mut angles: Vec<f64> = Vec::new();
    let mut reference = Vec::new();
    for p in points(&refined)? {
        let mut theta = p[1].atan2(p[0]);
        if let Some(last) = angles.last() {
            if ((theta - last + PI).rem_euclid(TAU) - PI).abs() < 1e-8 {
                theta = *last;
            }
        }
        let mut r = radius(p);
        if (r - root).abs() < 1e-8 {
            r = root;
        }
        angles.push(theta);
        reference.push(polar(r, theta));
    }
    let outer_body: Vec<_> = angles.iter().map(|q| polar(root, *q)).collect();
    let toothed = deform(&wave, &reference, rp, 1.)?;
    let count = circle_count(inner + amplitude)?.max(192);
    let inner_round = circle(inner, count);
    let inner_deformed = deform(&wave, &inner_round, rp, 1.)?;
    let (base_outer, bottom_hole) = if variant == "hat" {
        (
            angles
                .iter()
                .map(|q| polar(base_radius, *q))
                .collect::<Vec<_>>(),
            inner_round.clone(),
        )
    } else {
        let output = n(v, "output_bore", 0.)?;
        if output / 2. >= inner - 0.5 {
            return Err("Output bore too large for the cup diaphragm.".into());
        }
        if output <= 0. {
            return Err(
                "For the cup, use an output bore greater than zero (annular diaphragm).".into(),
            );
        }
        (outer_body.clone(), circle(output / 2., count))
    };
    let mut stations = Vec::new();
    let mut level = |height: f64,
                     outer: &Vec<Point>,
                     hole: &Vec<Point>,
                     outer_ref: &Vec<Point>,
                     hole_ref: &Vec<Point>,
                     weight: f64| {
        stations.push(Station {
            z: height,
            outer: outer.clone(),
            holes: vec![hole.clone()],
            material_outer: Some(material(outer_ref, rp, weight)),
            material_holes: Some(vec![material(hole_ref, rp, weight)]),
        });
    };
    level(0., &base_outer, &bottom_hole, &base_outer, &bottom_hole, 0.);
    level(
        diaphragm,
        &base_outer,
        &bottom_hole,
        &base_outer,
        &bottom_hole,
        0.,
    );
    level(
        diaphragm,
        &outer_body,
        &inner_round,
        &outer_body,
        &inner_round,
        0.,
    );
    for j in 1..=6 {
        let f = j as f64 / 6.;
        level(
            diaphragm + (length - diaphragm) * f,
            &deform(&wave, &outer_body, rp, f)?,
            &deform(&wave, &inner_round, rp, f)?,
            &outer_body,
            &inner_round,
            f,
        );
    }
    level(
        length,
        &toothed,
        &inner_deformed,
        &reference,
        &inner_round,
        1.,
    );
    level(
        length + width,
        &toothed,
        &inner_deformed,
        &reference,
        &inner_round,
        1.,
    );
    let mut flex = part(
        &format!("Flexspline_{variant}"),
        toothed,
        vec![inner_deformed.clone()],
        length + width,
    );
    flex.extra["z"] = json!(-length);
    flex.stations = stations;
    let cutter = crate::profiles::gear_part(&gear_args(json!(-n(v, "backlash", 0.15)?), true))?;
    let generated = crate::wave_envelope::call(
        &json!({"reference":cutter["outer"],"z":z,"a":a,"b":b,"rp":rp}),
    )?;
    let cavity = points(&generated["points"])?;
    let ring_radius = cavity.iter().map(|p| radius(*p)).fold(0., f64::max) + n(v, "rim", 5.)?;
    let mut ring = part(
        "Circular_spline_generated",
        round(ring_radius)?,
        vec![cavity],
        width,
    );
    ring.extra["outer_circle_radius"] = json!(ring_radius);
    ring.extra["internal"] = json!(true);
    ring.extra["color"] = json!([0.69, 0.59, 0.86]);
    ring.extra["profile_metadata"] = json!({"wave_envelope":generated["metadata"]});
    let radial = |distance: f64| {
        inner_deformed
            .iter()
            .map(|p| polar(radius(*p) - distance, p[1].atan2(p[0])))
            .collect::<Vec<_>>()
    };
    let mut bearing_part = part(
        "Bearing_wave_envelope",
        radial(clearance),
        vec![radial(clearance + bearing)],
        width,
    );
    bearing_part.extra["role"] = json!("support");
    bearing_part.extra["color"] = json!([0.52, 0.61, 0.7]);
    let mut generator = part(
        "Generator_wave_prescribed",
        radial(2. * clearance + bearing),
        if bore > 0. {
            vec![round(bore / 2.)?]
        } else {
            vec![]
        },
        width,
    );
    generator.extra["color"] = json!([0.95, 0.65, 0.3]);
    for p in [&mut ring, &mut bearing_part, &mut generator] {
        p.stations = vec![
            Station::new(0., p.outer.clone(), p.holes.clone()),
            Station::new(width, p.outer.clone(), p.holes.clone()),
        ];
    }
    let coefficients = crate::wave::call("wave_coefficients", &json!({"a":a,"b":b,"rp":rp}))?;
    let mapping = json!({"method":"uniform pitch arc length with local normal tooth offsets","arc_fourier_modes":8,"arc_coefficients":coefficients,"aspect_q":(a*a-b*b)/(a*a+b*b),"domain_max_q":0.25,"elastic_solution":false,"conjugate":true,"verification_scope":"Numerically generated envelope under prescribed map; finite sampled containment and engagement checks, no elastic solution","schema":"ratiolab.wave-map/1","ellipse_axes_mm":[a,b],"pitch_radius_mm":rp,"body_length_mm":length,"diaphragm_mm":diaphragm,"reference_pair_backlash_mm":n(v,"backlash",0.15)?,"ring_envelope":generated["metadata"]});
    flex.extra["profile_metadata"] = json!({"wave_mapping":mapping,"undeformed_tooth_reference":gear["profile_metadata"]["tooth_profile"],"analytic_values":gear["profile_metadata"]["analytic_values"],"analytic_precision":gear["profile_metadata"]["analytic_precision"]});
    let circular = v["harmonic_output"] == "circular";
    let ratio = if circular { (z + 2.) / 2. } else { -z / 2. };
    Ok(Construction {
        parts: vec![flex, ring, bearing_part, generator],
        extra: json!({"analysis":{"wave_mapping":mapping,"signed_ratio":ratio,"illustrative_amplitude_mm":amplitude,"pitch_ellipse_semiaxes_mm":[a,b],"reference_pitch_perimeter_mm":TAU*rp,"harmonic_output":v["harmonic_output"],"housing_variant":variant}}),
    })
}
pub(crate) fn build(op: &str, a: &Value) -> Result<Construction> {
    let v = &a["values"];
    if !v.is_object() {
        return Err("Construction requires parameter values".into());
    }
    match op {
        "construction_worm" => worm(v),
        "construction_harmonic" => harmonic(v),
        "construction_rack" => crate::rack_drive::build(a),
        "construction_bevel_pair" => crate::bevel_pair::build(v),
        "construction_hypoid" => crate::hypoid::build(v),
        "construction_face" => crate::face::build(v),
        _ => Err("Unknown solid construction".into()),
    }
}

pub fn call(op: &str, a: &Value) -> Result<Value> {
    serde_json::to_value(build(op, a)?).map_err(|e| e.to_string())
}
