// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Custom spherical-involute pairs. KHK 4.17 pitch cones; Dong sec.2 eq.1
//! flanks; circular developed lead, not industrial Gleason octoidal geometry.
use crate::{
    bevel::{self, Profile},
    geometry_data::{Construction, Part, Station},
    precision::Result,
    profiles::{Point, n},
};
use serde_json::{Value, json};
use std::f64::consts::{PI, TAU};
pub(crate) const REFINEMENT: f64 = 0.003;
pub(crate) const PINION_FRAME: [[f64; 3]; 4] =
    [[0., 0., 0.], [0., 1., 0.], [0., 0., 1.], [1., 0., 0.]];
const WHEEL_FRAME: [[f64; 3]; 4] = [[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]];

pub(crate) fn validate(v: &Value) -> Result<()> {
    let m = n(v, "module", 0.)?;
    let width = n(v, "width", 0.)?;
    let pressure = n(v, "pressure", 20.)?;
    if !v.is_object()
        || m <= 0.
        || width <= 0.
        || !(0. < pressure && pressure < 90.)
        || ["backlash", "bore", "output_bore"]
            .iter()
            .any(|k| n(v, k, 0.).map_or(true, |x| x < 0.))
    {
        return Err("Invalid gear-pair dimensions".into());
    }
    for k in ["pinion", "wheel"] {
        let z = n(v, k, 0.)?;
        if !(3. ..=1000.).contains(&z) || z.fract() != 0. {
            return Err("Integer gear-pair tooth counts from 3 to 1000 required".into());
        }
    }
    Ok(())
}
pub(crate) fn circle(r: f64) -> Result<Vec<Point>> {
    if r <= 0. || !r.is_finite() {
        return Err("Positive circle radius required".into());
    }
    // Same canonical 96-point construction circle as geometry.circle(). CAD
    // provenance, rather than extra facets, represents its exact circle.
    let count = 96;
    Ok((0..count)
        .map(|j| {
            let a = TAU * j as f64 / count as f64;
            [r * a.cos(), r * a.sin()]
        })
        .collect())
}
pub(crate) fn bores(r: f64) -> Result<Vec<Vec<Point>>> {
    if r > 0. {
        Ok(vec![circle(r)?])
    } else {
        Ok(vec![])
    }
}
pub(crate) fn derivative_bounds(q: &Profile, low: f64, high: f64) -> Result<[f64; 2]> {
    if !low.is_finite() || !high.is_finite() || low <= 0. || high < low {
        return Err("Invalid circular trace derivative domain".into());
    }
    q.developed_angle(low)?;
    q.developed_angle(high)?;
    let m = q.mean_distance.ok_or("Circular trace required")?;
    let rho = q.trace_radius.unwrap();
    let dmax = ((low + m.powi(2) / low) / 2.).max((high + m.powi(2) / high) / 2.);
    let hmin = (m.powi(2) + rho.powi(2) - dmax.powi(2)).sqrt();
    let dp = (1. - (m / low).powi(2))
        .abs()
        .max((1. - (m / high).powi(2)).abs())
        / 2.;
    let first = dp / hmin / q.delta.sin();
    let second =
        (m.powi(2) / low.powi(3) / hmin + dmax * dp.powi(2) / hmin.powi(3)) / q.delta.sin();
    if !first.is_finite() || !second.is_finite() {
        return Err("Unresolved circular trace derivative bound".into());
    }
    Ok([first, second])
}
pub(crate) fn stations(profiles: &[Profile], width: f64) -> Result<(Vec<f64>, f64)> {
    let outer = profiles
        .first()
        .ok_or("Spherical profiles required")?
        .outer_distance;
    let inner = outer - width;
    if width <= 0. || inner <= 0. || !width.is_finite() {
        return Err("Positive inner cone distance required".into());
    }
    let mut bound = 0_f64;
    for q in profiles {
        let amp = q.delta.cos() * q.tip.tan();
        let v = if q.mean_distance.is_some() {
            let cmin = q.delta.cos() / q.root.cos();
            let cmax = q.delta.cos() / q.tip.cos();
            let [first, second] = derivative_bounds(q, cmin * inner, cmax * outer)?;
            amp * (2. * cmax * first + outer * cmax.powi(2) * (second + first.powi(2)))
        } else {
            amp * q.k.abs() * (1. + q.k * q.k).sqrt() / inner
        };
        bound = bound.max(v);
    }
    let count = (width * (bound / (8. * REFINEMENT)).sqrt()).ceil().max(1.) as usize;
    if count > 128 || !bound.is_finite() {
        return Err("Curved bevel trace exceeds its section budget; reduce width/spiral angle or increase trace radius.".into());
    }
    let mut out = vec![inner];
    out.extend((1..count).map(|j| inner + width * j as f64 / count as f64));
    out.push(outer);
    Ok((out, bound))
}
pub(crate) fn curved_section(q: &Profile, points: &[Point], distance: f64) -> Result<Vec<Point>> {
    let outer = q.outer_distance;
    let heel = outer * q.delta.cos();
    points
        .iter()
        .enumerate()
        .map(|(i, [x, y])| {
            if i % 256 == 0 {
                crate::protocol::control_check()?
            }
            let actual = x.hypot(*y).hypot(heel);
            let turn = q.trace(actual * distance / outer)? - q.trace(actual)?;
            let (c, s) = (turn.cos(), turn.sin());
            Ok([
                (x * c - y * s) * distance / outer,
                (x * s + y * c) * distance / outer,
            ])
        })
        .collect()
}
fn circular_engagement(a: &Profile, b: &Profile, width: f64) -> Result<Value> {
    let base = bevel::engagement(a, b, width)?;
    let lo = base["action_angle_interval_rad"][0].as_f64().unwrap();
    let hi = base["action_angle_interval_rad"][1].as_f64().unwrap();
    let outer = a.outer_distance;
    let inner = outer - width;
    let sa = (1. - (a.base.sin() / a.delta.sin()).powi(2)).max(0.).sqrt();
    let mut samples: Vec<f64> = (0..257).map(|j| lo + (hi - lo) * j as f64 / 256.).collect();
    if lo < 0. && hi > 0. {
        samples.push(0.)
    }
    let mut bounds = [[f64::INFINITY, f64::NEG_INFINITY]; 2];
    for s in samples {
        crate::protocol::control_check()?;
        let x = a.delta.cos() * s.cos() - sa * a.delta.sin() * s.sin();
        let z = a.delta.sin() * s.cos() + sa * a.delta.cos() * s.sin();
        let low = (inner * a.delta.cos() / x).max(inner * b.delta.cos() / z);
        let high = (outer * a.delta.cos() / x).min(outer * b.delta.cos() / z);
        if low > high {
            continue;
        }
        for r in [low, high, a.mean_distance.unwrap().clamp(low, high)] {
            for (i, sign) in [-1., 1.].into_iter().enumerate() {
                let phase = s / a.base.sin() - sign * a.trace(r)?;
                bounds[i][0] = bounds[i][0].min(phase);
                bounds[i][1] = bounds[i][1].max(phase)
            }
        }
    }
    let spans = bounds.map(|[a0, b0]| (b0 - a0) / (TAU / a.teeth as f64));
    if spans.iter().any(|x| !x.is_finite()) {
        return Err("Empty circular bevel action domain".into());
    }
    Ok(
        json!({"contact_phase_span_teeth":spans[0].min(spans[1]),"flank_contact_phase_spans_teeth":spans,
        "action_angle_interval_rad":[lo,hi],"is_lower_bound":true,
        "method":"Conservative sampled lower bound of continuous phase on the connected cap/action domain",
        "scope":"Sufficient ideal engagement only; missed extrema may cause conservative rejection; no load or strength solution"}),
    )
}
pub(crate) fn dimensions(v: &Value) -> Result<(Profile, Profile, Value)> {
    validate(v)?;
    let m = n(v, "module", 2.)?;
    let width = n(v, "width", 8.)?;
    let zp = n(v, "pinion", 20.)?;
    let zw = n(v, "wheel", 40.)?;
    let distance = zp.hypot(zw) * m / 2.;
    if !distance.is_finite() {
        return Err("Bevel reference cone distance overflows sampled geometry".into());
    }
    let j = n(v, "backlash", 0.15)?;
    if width > (distance / 3.).min(10. * m) {
        return Err("Bevel face width must not exceed one third of the pitch cone distance or ten outer modules.".into());
    }
    if j >= 0.7 * m {
        return Err("Backlash too large for the bevel module.".into());
    }
    let variant = v["variant"].as_str().unwrap_or("straight");
    if !["straight", "spiral", "zerol"].contains(&variant) {
        return Err("Unknown bevel pair variant".into());
    }
    let beta = if variant == "spiral" {
        n(v, "spiral_angle", 35.)?
    } else {
        0.
    };
    let hand = n(v, "spiral_hand", 1.)?;
    let p = |z, mate, h| {
        bevel::parameters(
            &json!({"teeth":z,"mate_teeth":mate,"module":m,"pressure":n(v,"pressure",20.)?,"backlash":j,"beta":beta,"hand":h}),
        )
    };
    let (mut a, mut b) = (p(zp, zw, hand)?, p(zw, zp, -hand)?);
    let contact = if variant == "zerol" {
        let rho = n(v, "trace_radius", 50.)?;
        if rho <= 0. {
            return Err("Positive circular trace radius required".into());
        }
        for (q, h) in [(&mut a, hand), (&mut b, -hand)] {
            q.mean_distance = Some(distance - width / 2.);
            q.trace_radius = Some(rho);
            q.trace_hand = Some(h);
            derivative_bounds(
                q,
                (distance - width) * q.delta.cos() / q.root.cos(),
                distance * q.delta.cos() / q.tip.cos(),
            )?;
        }
        circular_engagement(&a, &b, width)?
    } else {
        bevel::engagement(&a, &b, width)?
    };
    stations(&[a.clone(), b.clone()], width)?;
    if n(&contact, "contact_phase_span_teeth", 0.)? <= 1. + 1e-8 {
        return Err("Bevel face width/addendum leaves a gap in ideal tooth engagement; increase face width or adjust tooth counts / pressure angle.".into());
    }
    for (q, bore) in [(&a, n(v, "bore", 0.)?), (&b, n(v, "output_bore", 0.)?)] {
        let root = (distance - width) * q.delta.cos() * q.root.tan();
        if bore > 0. && bore / 2. + 0.8 >= root {
            return Err(
                "Bore too large for the small-end bevel root; reduce bore diameter or face width."
                    .into(),
            );
        }
    }
    Ok((a, b, contact))
}
pub(crate) fn build(v: &Value) -> Result<Construction> {
    let (a, b, contact) = dimensions(v)?;
    let width = n(v, "width", 8.)?;
    let distance = a.outer_distance;
    let scale = 1. - width / distance;
    let variant = v["variant"].as_str().unwrap_or("straight");
    let hand = n(v, "spiral_hand", 1.)?;
    let (distances, bound) = stations(&[a.clone(), b.clone()], width)?;
    let mut parts = Vec::new();
    for (q, name, bore, frame, phase, member, h) in [
        (
            &a,
            "Bevel_pinion",
            n(v, "bore", 0.)?,
            PINION_FRAME,
            PI / 2. - PI / a.teeth as f64,
            "A",
            hand,
        ),
        (
            &b,
            "Bevel_wheel",
            n(v, "output_bore", 0.)?,
            WHEEL_FRAME,
            0.,
            "B",
            -hand,
        ),
    ] {
        crate::protocol::control_check()?;
        let heel = distance * q.delta.cos();
        let toe = heel * scale;
        let outer = bevel::section(q, heel, phase, REFINEMENT)?;
        let holes = bores(bore / 2.)?;
        let mut p = Part::new(name, outer.clone(), holes.clone(), heel - toe);
        p.extra["z"] = json!(toe);
        p.extra["frame"] = json!(frame);
        if bore > 0. {
            p.extra["bore_circle_radius"] = json!(bore / 2.);
        }
        p.stations = vec![
            Station::new(
                0.,
                outer.iter().map(|[x, y]| [x * scale, y * scale]).collect(),
                holes.clone(),
            ),
            Station::new(heel - toe, outer.clone(), holes.clone()),
        ];
        if variant != "straight" && (q.k != 0. || q.mean_distance.is_some()) {
            if 2 * (outer.len() + holes.iter().map(Vec::len).sum::<usize>()) * (distances.len() - 1)
                + 2
                > 250000
            {
                return Err("Curved bevel surface exceeds the shared face budget; reduce tooth counts, width or curvature.".into());
            }
            p.stations = distances
                .iter()
                .enumerate()
                .map(|(i, r)| {
                    Ok(Station::new(
                        if i == 0 {
                            0.
                        } else if i == distances.len() - 1 {
                            heel - toe
                        } else {
                            r * q.delta.cos() - toe
                        },
                        if *r == distance {
                            outer.clone()
                        } else {
                            curved_section(q, &outer, *r)?
                        },
                        holes.clone(),
                    ))
                })
                .collect::<Result<_>>()?;
        }
        p.extra["port"] =
            json!({"member":member,"axis":if member=="A"{"World +X"}else{"World +Z"}});
        p.extra["color"] = if member == "A" {
            json!([0.96, 0.66, 0.33])
        } else {
            json!([0.23, 0.75, 0.65])
        };
        let mut meta = json!({"method":"Exact spherical involute working flanks; custom planar blank",
            "pitch_cone_angle_deg":q.delta.to_degrees(),"base_cone_angle_deg":q.base.to_degrees(),"root_cone_angle_deg":q.root.to_degrees(),"tip_cone_angle_deg":q.tip.to_degrees(),
            "cone_distance_mm":distance,"face_width_mm":width,"teeth":q.teeth,"profile_refinement_threshold_mm":REFINEMENT,
            "section_end_convention":"Planar Z caps at pitch-cone heel/toe; actual vertex R=Z/cos(theta)",
            "root_method":"Nonworking constant-half-angle relief below base; deepened for mate addendum",
            "engagement":contact,"flank_reference_doi":"10.3389/fmech.2025.1643228","flank_reference_equation":"Section 2 equation 1"});
        if variant != "straight" {
            meta.as_object_mut().unwrap().extend(json!({"tooth_type":variant,"local_trace_hand":h,"trace_chord_tolerance_mm":REFINEMENT,"trace_second_derivative_bound":bound,"cone_stations_mm":distances,
            "spiral_angle_deg":n(v,"spiral_angle",0.)?,"trace_radius_mm":v.get("trace_radius"),"mean_spiral_angle_deg":if variant=="zerol"{0.}else{n(v,"spiral_angle",0.)?}}).as_object().unwrap().clone());
        }
        p.extra["profile_metadata"] = json!({"bevel_profile":meta});
        parts.push(p);
    }
    let mut info = json!({"shaft_angle_deg":90,"pitch_cone_distance_mm":distance,"pinion_pitch_angle_deg":a.delta.to_degrees(),"wheel_pitch_angle_deg":b.delta.to_degrees(),
        "outer_pitch_diameters_mm":[n(v,"module",2.)?*a.teeth as f64,n(v,"module",2.)?*b.teeth as f64],"engagement":contact,
        "construction":"Straight spherical involute; custom planar blanks","axes":{"A":[1,0,0],"B":[0,0,1]},"rolling_equation":"pinion_teeth * pinion_rpm + wheel_teeth * wheel_rpm = 0"});
    if variant != "straight" {
        info.as_object_mut().unwrap().extend(json!({"tooth_type":variant,"spiral_angle_deg":n(v,"spiral_angle",0.)?,"pinion_local_trace_hand":hand,"trace_radius_mm":v.get("trace_radius"),"cone_stations_mm":distances,
        "construction":if variant=="spiral"{"Spherical involute; logarithmic spiral trace"}else{"Custom spherical involute; circular developed Zerol-style trace"}}).as_object().unwrap().clone());
    }
    Ok(Construction {
        parts,
        extra: json!({"analysis":{"signed_ratio":-(b.teeth as f64)/(a.teeth as f64),"bevel_pair":info}}),
    })
}
pub fn call(a: &Value) -> Result<Value> {
    match a["action"].as_str().unwrap_or("dimensions") {
        "dimensions" => {
            let (a, b, c) = dimensions(&a["values"])?;
            Ok(json!([a, b, c]))
        }
        "trace" => Ok(json!(
            Profile::read(&a["profile"])?.trace(n(a, "distance", 0.)?)?
        )),
        "section_trace" => {
            let p = Profile::read(&a["profile"])?;
            let z = n(a, "z", 0.)?;
            let theta = n(a, "theta", 0.)?;
            p.trace(z / theta.cos())?;
            Ok(json!(p.section_trace(z, theta)))
        }
        "developed_angle" => Ok(json!(
            Profile::read(&a["profile"])?.developed_angle(n(a, "distance", 0.)?)?
        )),
        "derivative_bounds" => Ok(json!(derivative_bounds(
            &Profile::read(&a["profile"])?,
            n(a, "low", 0.)?,
            n(a, "high", 0.)?
        )?)),
        "engagement" => circular_engagement(
            &Profile::read(&a["a"])?,
            &Profile::read(&a["b"])?,
            n(a, "width", 0.)?,
        ),
        "stations" => {
            let p: Vec<Value> =
                serde_json::from_value(a["profiles"].clone()).map_err(|e| e.to_string())?;
            if p.len() > 8 {
                return Err("Too many spherical profiles".into());
            }
            let p = p.iter().map(Profile::read).collect::<Result<Vec<_>>>()?;
            let (s, b) = stations(&p, n(a, "width", 0.)?)?;
            Ok(json!([s, b]))
        }
        "curved_section" => {
            let p: Vec<Point> =
                serde_json::from_value(a["points"].clone()).map_err(|e| e.to_string())?;
            if p.len() > 10000 {
                return Err("Spherical contour vertex budget exhausted".into());
            }
            Ok(json!(curved_section(
                &Profile::read(&a["profile"])?,
                &p,
                n(a, "distance", 0.)?
            )?))
        }
        _ => Err("Unknown bevel pair operation".into()),
    }
}
