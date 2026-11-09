// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Spherical involute and planar cap sections: Dong et al. (2025), sec.2 eq.1;
//! Wang et al. (2011), eq.22. Existing construction conventions are preserved.
use crate::{
    precision::Result,
    profiles::{Point, n, sample},
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::f64::consts::{PI, TAU};

fn spherical(theta: f64, base: f64) -> Result<f64> {
    if !theta.is_finite()
        || !base.is_finite()
        || base <= 0.
        || base >= PI / 2.
        || theta < base - 1e-12
    {
        return Err("A spherical involute has no working branch below its base cone.".into());
    }
    let t = (theta.cos() / base.cos()).clamp(-1., 1.).acos();
    Ok(t / base.sin() - t.sin().atan2(base.sin() * t.cos()))
}
#[derive(Clone, Serialize, Deserialize)]
pub struct Profile {
    pub(crate) teeth: u32,
    pub(crate) delta: f64,
    pub(crate) base: f64,
    pub(crate) root: f64,
    pub(crate) tip: f64,
    pub(crate) outer_distance: f64,
    pub(crate) backlash: f64,
    pub(crate) k: f64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub(crate) mean_distance: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub(crate) trace_radius: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub(crate) trace_hand: Option<f64>,
}
impl Profile {
    pub(crate) fn half(&self, theta: f64) -> f64 {
        PI / (2. * self.teeth as f64)
            - self.backlash / (4. * self.outer_distance * self.delta.sin())
            + spherical(self.delta, self.base).unwrap()
            - spherical(theta.max(self.base), self.base).unwrap()
    }
    fn point(&self, theta: f64, distance: f64, side: f64, phase: f64) -> [f64; 3] {
        let azimuth = phase + self.trace(distance).unwrap_or(f64::NAN) + side * self.half(theta);
        let r = distance * theta.sin();
        [r * azimuth.cos(), r * azimuth.sin(), distance * theta.cos()]
    }
    fn section_point(&self, theta: f64, z: f64, side: f64, phase: f64) -> Point {
        let p = self.point(theta, z / theta.cos(), side, phase);
        [p[0], p[1]]
    }
    pub(crate) fn read(a: &Value) -> Result<Self> {
        let p: Self = serde_json::from_value(a.clone()).map_err(|e| e.to_string())?;
        if p.teeth < 3
            || p.teeth > 100000
            || ![
                p.delta,
                p.base,
                p.root,
                p.tip,
                p.outer_distance,
                p.backlash,
                p.k,
            ]
            .iter()
            .all(|v| v.is_finite())
            || !(0. < p.root
                && p.root < p.tip
                && p.tip < PI / 2.
                && 0. < p.base
                && p.base < p.delta
                && p.delta < PI / 2.
                && p.outer_distance > 0.)
        {
            return Err("Invalid spherical profile".into());
        }
        match (p.mean_distance, p.trace_radius, p.trace_hand) {
            (None, None, None) => {}
            (Some(m), Some(r), Some(h))
                if m.is_finite() && r.is_finite() && m > 0. && r > 0. && h.abs() == 1. => {}
            _ => return Err("Invalid circular spherical trace".into()),
        }
        Ok(p)
    }

    pub(crate) fn developed_angle(&self, distance: f64) -> Result<f64> {
        let mean = self.mean_distance.ok_or("Circular trace required")?;
        let rho = self.trace_radius.ok_or("Circular trace required")?;
        if !distance.is_finite() || distance <= 0. {
            return Err("Circular tooth trace requires a positive cone distance.".into());
        }
        let d = (distance + mean.powi(2) / distance) / 2.;
        let a = mean.hypot(rho);
        if d >= a * (1. - 1e-12) {
            return Err(
                "Circular tooth trace leaves its supported arc; increase trace curvature radius."
                    .into(),
            );
        }
        Ok(rho.atan2(mean) - (d / a).acos())
    }
    pub(crate) fn trace(&self, distance: f64) -> Result<f64> {
        if self.mean_distance.is_some() {
            Ok(self.trace_hand.unwrap()
                * (self.developed_angle(distance)? - self.developed_angle(self.outer_distance)?)
                / self.delta.sin())
        } else if distance > 0. && distance.is_finite() {
            Ok(self.k * (distance / self.outer_distance).ln())
        } else {
            Err("Positive spherical trace distance required".into())
        }
    }
    pub(crate) fn section_trace(&self, z: f64, theta: f64) -> f64 {
        if self.mean_distance.is_some() {
            self.trace(z / theta.cos()).unwrap_or(f64::NAN)
        } else {
            self.k * (z / (theta.cos() * self.outer_distance)).ln()
        }
    }
}
pub(crate) fn parameters(a: &Value) -> Result<Profile> {
    let z = n(a, "teeth", 24.)?;
    let mate = n(a, "mate_teeth", 24.)?;
    let m = n(a, "module", 2.)?;
    let pressure = n(a, "pressure", 20.)?;
    let backlash = n(a, "backlash", 0.)?;
    let beta = n(a, "beta", 0.)?;
    let hand = n(a, "hand", 1.)?;
    if !(z >= 3.
        && z.fract() == 0.
        && mate >= 3.
        && mate.fract() == 0.
        && m > 0.
        && 0. < pressure
        && pressure < 90.
        && backlash >= 0.
        && (0. ..=45.).contains(&beta)
        && [-1., 1.].contains(&hand))
    {
        return Err("Spherical bevel parameters are outside their supported domain.".into());
    }
    let delta = z.atan2(mate);
    let outer = z.hypot(mate) * m / 2.;
    let base = (delta.sin() * pressure.to_radians().cos()).asin();
    let tip = (z + 2.).atan2(mate);
    let mate_tip = (mate + 2.).atan2(z);
    let root = (z - 2.5)
        .atan2(mate)
        .min(PI / 2. - mate_tip - 0.25 * m / outer);
    if root <= 0. {
        return Err("The bevel tooth root reaches the cone apex.".into());
    }
    let limit = (base.sin().powi(2) / (base.cos() * delta.tan()))
        .clamp(-1., 1.)
        .acos();
    if mate_tip >= limit - 1e-9 {
        return Err("The mating bevel tip requires below-base contact; increase tooth counts or pressure angle.".into());
    }
    let q = Profile {
        teeth: z as u32,
        delta,
        base,
        root,
        tip,
        outer_distance: outer,
        backlash,
        k: hand * beta.to_radians().tan() / delta.sin(),
        mean_distance: None,
        trace_radius: None,
        trace_hand: None,
    };
    if !(0. < q.half(tip) && q.half(tip) < q.half(root) && q.half(root) < PI / z) {
        return Err("Pointed or overlapping spherical bevel teeth; reduce backlash or increase tooth count.".into());
    }
    Ok(q)
}
pub(crate) fn engagement(a: &Profile, b: &Profile, width: f64) -> Result<Value> {
    let outer = a.outer_distance;
    let inner = outer - width;
    if !(0. < inner && inner < outer) {
        return Err("Bevel engagement requires a positive inner cone distance.".into());
    }
    let sa = (1. - (a.base.sin() / a.delta.sin()).powi(2)).max(0.).sqrt();
    if sa <= 0. {
        return Err("Bevel engagement requires positive transverse pressure.".into());
    }
    let ga = (sa * a.delta.tan()).atan();
    let gb = (sa * b.delta.tan()).atan();
    let ta = (a.tip.cos() / a.base.cos()).clamp(-1., 1.).acos();
    let tb = (b.tip.cos() / b.base.cos()).clamp(-1., 1.).acos();
    let low = inner / outer * a.delta.tan();
    let high = outer / inner * a.delta.tan();
    let slo = (gb - tb).max(((low.atan() - a.delta).tan() / sa).atan());
    let shi = (ta - ga).min(((high.atan() - a.delta).tan() / sa).atan());
    if slo >= shi {
        return Err("The bevel end faces leave no common working contact interval.".into());
    }
    let mut candidates = vec![slo, shi];
    if slo < 0. && 0. < shi {
        candidates.push(0.);
    }
    if a.k != 0. {
        for sign in [-1., 1.] {
            for offset in [ga, -gb] {
                let crit = (1. / (sign * a.k * a.base.sin())).atan() - offset;
                for winding in [-1., 0., 1.] {
                    let v = crit + winding * PI;
                    if slo < v && v < shi {
                        candidates.push(v);
                    }
                }
            }
        }
    }
    let mut phases = [Vec::new(), Vec::new()];
    for s in candidates {
        let x = a.delta.cos() * s.cos() - sa * a.delta.sin() * s.sin();
        let z = a.delta.sin() * s.cos() + sa * a.delta.cos() * s.sin();
        let lo = (inner * a.delta.cos() / x).max(inner * b.delta.cos() / z);
        let hi = (outer * a.delta.cos() / x).min(outer * b.delta.cos() / z);
        if lo > hi + 1e-10 {
            continue;
        }
        for r in [lo, hi] {
            for (i, sign) in [-1., 1.].iter().enumerate() {
                phases[i].push(s / a.base.sin() - sign * a.k * (r / outer).ln());
            }
        }
    }
    let mut ratios = [0.; 2];
    for (i, p) in phases.iter().enumerate() {
        if p.is_empty() {
            return Err("Empty bevel action domain".into());
        }
        ratios[i] = (p.iter().copied().fold(f64::NEG_INFINITY, f64::max)
            - p.iter().copied().fold(f64::INFINITY, f64::min))
            / (TAU / a.teeth as f64);
    }
    Ok(
        json!({"contact_phase_span_teeth":ratios[0].min(ratios[1]),"flank_contact_phase_spans_teeth":ratios,"action_angle_interval_rad":[slo,shi],
        "method":"Connected spherical action domain with both planar cap intervals; analytic boundary-phase extrema",
        "scope":"Ideal unmodified working flanks, independent of load and manufacturing error"}),
    )
}
pub(crate) fn section(q: &Profile, z: f64, phase: f64, tolerance: f64) -> Result<Vec<Point>> {
    if z <= 0. || !z.is_finite() || !phase.is_finite() || !tolerance.is_finite() || tolerance <= 0.
    {
        return Err("Spherical bevel section must be above the cone apex".into());
    }
    if q.mean_distance.is_some() {
        q.trace(z / q.root.cos())?;
        q.trace(z / q.tip.cos())?;
    }
    let pitch = TAU / q.teeth as f64;
    let mut levels = vec![q.root];
    if q.root < q.base && q.base < q.tip {
        levels.push(q.base);
    }
    levels.push(q.tip);
    let mut points = Vec::new();
    let append = |points: &mut Vec<Point>, mut p: Vec<Point>| {
        p.pop();
        points.extend(p);
    };
    for tooth in 0..q.teeth {
        crate::protocol::control_check()?;
        let center = phase + tooth as f64 * pitch;
        let root_phase = center + q.section_trace(z, q.root);
        let tip_phase = center + q.section_trace(z, q.tip);
        let arc = |theta: f64, start: f64, end: f64| {
            sample(
                &|a| {
                    let r = z * theta.tan();
                    [r * a.cos(), r * a.sin()]
                },
                start,
                end,
                tolerance,
                false,
            )
        };
        append(
            &mut points,
            arc(q.root, root_phase - pitch / 2., root_phase - q.half(q.root))?,
        );
        for p in levels.windows(2) {
            append(
                &mut points,
                sample(
                    &|theta| q.section_point(theta, z, -1., center),
                    p[0],
                    p[1],
                    tolerance,
                    false,
                )?,
            );
        }
        append(
            &mut points,
            arc(q.tip, tip_phase - q.half(q.tip), tip_phase + q.half(q.tip))?,
        );
        for p in levels.windows(2).rev() {
            append(
                &mut points,
                sample(
                    &|theta| q.section_point(theta, z, 1., center),
                    p[1],
                    p[0],
                    tolerance,
                    false,
                )?,
            );
        }
        append(
            &mut points,
            arc(q.root, root_phase + q.half(q.root), root_phase + pitch / 2.)?,
        );
        if points.len() > 10000 {
            return Err("Spherical bevel contour exceeds its vertex budget.".into());
        }
    }
    if points.len() > 10000 {
        return Err("Spherical bevel contour exceeds its vertex budget.".into());
    }
    Ok(points)
}
fn spiral_trace(distance: f64, outer: f64, angle: f64, beta: f64, hand: f64) -> Result<f64> {
    let ratio = distance / outer;
    if !(0. < ratio && ratio <= 1. && 0. < angle && angle < PI / 2.) {
        return Err("Spiral trace requires a positive cone-distance ratio at or below 1 and a valid cone angle.".into());
    }
    if hand.abs() != 1. || !(0. ..=45.).contains(&beta) {
        return Err("Spiral trace requires hand −1 or +1 and unsigned angle from 0 to 45°.".into());
    }
    Ok(hand * beta.to_radians().tan() / angle.sin() * ratio.ln())
}

pub fn call(op: &str, a: &Value) -> Result<Value> {
    match op {
        "bevel_assembly_dimensions" => {
            let v = &a["values"];
            let classic = v["configuration"] == "classic";
            let m = n(v, "module", 0.)?;
            let zs = n(v, "side_teeth", 0.)?;
            let zo = n(v, "output_teeth", 0.)?;
            let width = n(v, "width", 0.)?;
            let backlash = n(v, "backlash", 0.)?;
            let side = m * zs / 2.;
            let output = m * zo / 2.;
            let distance = side.hypot(output);
            if width > distance / 3. {
                return Err(
                    "Bevel face width must not exceed one third of the pitch cone distance.".into(),
                );
            }
            if backlash >= 0.7 * m {
                return Err("Backlash too large for the bevel module.".into());
            }
            let scale = 1. - width / distance;
            let beta = if v["variant"] == "spiral" {
                n(v, "spiral_angle", 0.)?
            } else {
                0.
            };
            let hand = n(v, "spiral_hand", 1.)?;
            let pressure = n(v, "pressure", 20.)?;
            let side_profile = parameters(
                &json!({"teeth":zs,"mate_teeth":zo,"module":m,"pressure":pressure,"backlash":backlash,"beta":beta,"hand":hand}),
            )?;
            let output_profile = parameters(
                &json!({"teeth":zo,"mate_teeth":zs,"module":m,"pressure":pressure,"backlash":backlash,"beta":beta,"hand":-hand}),
            )?;
            let contact = engagement(&side_profile, &output_profile, width)?;
            if n(&contact, "contact_phase_span_teeth", 0.)? <= 1. + 1e-8 {
                return Err("Bevel face width/addendum leaves a gap in ideal tooth engagement; increase face width or adjust tooth counts / pressure angle.".into());
            }
            let transverse = if classic {
                n(v, "spider_pin_diameter", 0.)? + 2. * n(v, "spider_clearance", 0.)?
            } else {
                n(v, "output_shaft", 0.)?
            };
            for (profile, shaft) in [
                (&side_profile, n(v, "input_shaft", 0.)?),
                (&output_profile, transverse),
            ] {
                let root = distance * profile.delta.cos() * profile.root.tan() * scale;
                if shaft / 2. + 0.8 >= root {
                    return Err("Shaft too large for the small end of the bevel gear; reduce its diameter or face width.".into());
                }
            }
            let t = n(v, "plate", 0.)?;
            let clearance = n(v, "assembly_clearance", 0.)?;
            let r = n(
                v,
                if classic {
                    "input_shaft"
                } else {
                    "output_shaft"
                },
                0.,
            )? / 2.;
            let bolt = n(v, "bolt_diameter", 0.)? / 2.;
            let flange = n(v, "flange_radius", 0.)?;
            let pitch = (r + flange) / 2.;
            if v["output_interface"] == "flange" {
                if pitch - bolt <= r + 0.8 || pitch + bolt >= flange - 0.8 {
                    return Err("Output flange holes leave too little material around the shaft or flange edge.".into());
                }
                let count = n(v, "bolt_count", 0.)?;
                if count < 1. || 2. * bolt + 0.8 >= 2. * pitch * (PI / count).sin() {
                    return Err(
                        "Output flange mounting holes overlap or leave too little material.".into(),
                    );
                }
            }
            if v["output_interface"] == "hollow" && r - n(v, "passage_diameter", 0.)? / 2. < 1. {
                return Err("The hollow output shaft requires at least 1 mm radial wall around its passage.".into());
            }
            if v["carrier_style"] == "split" && (t - clearance) / 2. < 1. {
                return Err("Split carrier lap layers require at least 1 mm thickness each: increase carrier thickness or reduce assembly clearance.".into());
            }
            if classic && side * scale - clearance - 1.5_f64.min(t / 2.) <= 0. {
                return Err("Spider axial retainer reaches the cone apex; reduce clearance or increase the gear dimensions.".into());
            }
            Ok(
                json!({"cone_distance":distance,"side_pitch_radius":side,"output_pitch_radius":output,"side_cone_angle":side.atan2(output),"output_cone_angle":output.atan2(side),"inner_scale":scale,"flange_hole_radius":pitch,"transverse_bore":transverse,"side_profile":side_profile,"output_profile":output_profile,"engagement":contact}),
            )
        }
        "bevel_spiral_trace" => {
            let distance = n(a, "cone_distance", 0.)?;
            let outer = n(a, "outer_distance", 0.)?;
            let angle = n(a, "cone_angle", 0.)?;
            let beta = n(a, "beta", 0.)?;
            let hand = n(a, "hand", 1.)?;
            Ok(json!(spiral_trace(distance, outer, angle, beta, hand)?))
        }
        "bevel_spiral_stations" => Ok(json!(
            spiral_stations(a)?
                .into_iter()
                .map(|(z, outer)| json!({"z":z,"outer":outer}))
                .collect::<Vec<_>>()
        )),
        "bevel_cone_stations" => {
            let v = &a["values"];
            let q = &a["dimensions"];
            let outer = n(q, "cone_distance", 0.)?;
            let width = n(v, "width", 0.)?;
            let inner = outer - width;
            if !(0. < inner / outer && inner / outer <= 1.) {
                return Err("The inner pitch cone distance must be positive.".into());
            }
            let beta = n(v, "spiral_angle", 0.)?;
            if v["variant"] != "spiral" || beta == 0. {
                return Ok(json!([inner, outer]));
            }
            let mut bound = 0_f64;
            for (angle, pitch) in [
                (n(q, "side_cone_angle", 0.)?, n(q, "side_pitch_radius", 0.)?),
                (
                    n(q, "output_cone_angle", 0.)?,
                    n(q, "output_pitch_radius", 0.)?,
                ),
            ] {
                let k = beta.to_radians().tan() / angle.sin();
                bound = bound.max(
                    (pitch + n(v, "module", 0.)?) / outer * k.abs() * (1. + k * k).sqrt() / inner,
                );
            }
            let tolerance = n(a, "tolerance", 0.003)?;
            if tolerance <= 0. {
                return Err("Positive trace chord tolerance required".into());
            }
            let count = (width * (bound / (8. * tolerance)).sqrt()).ceil().max(1.) as usize;
            if count > 128 {
                return Err(
                    "Spiral trace exceeds the section budget; reduce width or spiral angle.".into(),
                );
            }
            let mut levels = vec![inner];
            levels.extend((1..count).map(|j| inner + (outer - inner) * j as f64 / count as f64));
            levels.push(outer);
            Ok(json!(levels))
        }
        "bevel_split_cheek" => {
            let half = n(a, "half_y", 0.)?;
            let low = n(a, "low", 0.)?;
            let high = n(a, "high", 0.)?;
            let seat = n(a, "seat", 0.)?;
            let edge = n(a, "gap", 0.)? / 2.;
            if seat <= 0. || edge < 0. || edge >= seat {
                return Err("Invalid open bearing-seat dimensions".into());
            }
            let angle = (edge / seat).acos();
            let height = (seat * seat - edge * edge).sqrt();
            let mut loop_ = vec![
                [edge, low],
                [half, low],
                [half, high],
                [edge, high],
                [edge, height],
            ];
            loop_.extend((1..=64).map(|j| {
                let q = angle - 2. * angle * j as f64 / 64.;
                [seat * q.cos(), seat * q.sin()]
            }));
            if a["positive"] == false {
                loop_ = loop_.into_iter().rev().map(|[x, y]| [-x, y]).collect();
            }
            Ok(json!(loop_))
        }
        "bevel_split_bridge" => {
            let span = n(a, "span", 0.)?;
            let half = n(a, "half_y", 0.)?;
            let seat = n(a, "seat", 0.)?;
            let edge = n(a, "gap", 0.)? / 2.;
            let bolt = n(a, "bolt_radius", 0.)?;
            let inside = n(a, "inside_span", span)?;
            let wall = 1.2;
            let half_tab = bolt + wall;
            let center = (inside + seat) / 2.;
            let depth = bolt + wall;
            if inside - (center + half_tab) < wall || center - half_tab - seat < wall {
                return Err("Split carrier joining holes leave insufficient material beside the bearing seat or bridge ends.".into());
            }
            if half - bolt < wall || depth - bolt < wall - 1e-9 {
                return Err(
                    "Split carrier joining holes leave insufficient bridge edge material.".into(),
                );
            }
            let mut loop_ = vec![
                [-span, edge],
                [-span, half],
                [span, half],
                [span, edge],
                [center + half_tab, edge],
                [center + half_tab, -depth],
                [center - half_tab, -depth],
                [center - half_tab, edge],
            ];
            if seat != 0. {
                if seat < 0. || edge < 0. || edge >= seat {
                    return Err("Invalid open bridge-seat dimensions".into());
                }
                let angle = (edge / seat).acos();
                loop_.push([(seat * seat - edge * edge).sqrt(), edge]);
                loop_.extend((1..=64).map(|j| {
                    let q = angle - 2. * angle * j as f64 / 64.;
                    [seat * q.sin(), seat * q.cos()]
                }));
            }
            loop_.extend([
                [-center + half_tab, edge],
                [-center + half_tab, -depth],
                [-center - half_tab, -depth],
                [-center - half_tab, edge],
            ]);
            if a["positive"] == false {
                loop_ = loop_.into_iter().rev().map(|[x, y]| [x, -y]).collect();
            }
            let holes: Vec<_> = [-center, center]
                .into_iter()
                .map(|x| {
                    (0..48)
                        .map(|j| {
                            let q = TAU * j as f64 / 48.;
                            [x + bolt * q.cos(), bolt * q.sin()]
                        })
                        .collect::<Vec<_>>()
                })
                .collect();
            Ok(json!([loop_, holes]))
        }
        "spherical_involute" => Ok(json!(spherical(n(a, "theta", 0.)?, n(a, "base", 0.)?)?)),
        "bevel_parameters" => Ok(json!(parameters(a)?)),
        "bevel_engagement" => engagement(
            &Profile::read(&a["a"])?,
            &Profile::read(&a["b"])?,
            n(a, "width", 0.)?,
        ),
        "bevel_section" => Ok(json!(section(
            &Profile::read(&a["profile"])?,
            n(a, "z", 1.)?,
            n(a, "phase", 0.)?,
            n(a, "tolerance", 0.003)?
        )?)),
        "bevel_half" | "bevel_point" | "bevel_section_point" => {
            let q = Profile::read(&a["profile"])?;
            let theta = n(a, "theta", q.delta)?;
            if q.mean_distance.is_some() && op != "bevel_half" {
                q.trace(if op == "bevel_point" {
                    n(a, "distance", 1.)?
                } else {
                    n(a, "z", 1.)? / theta.cos()
                })?;
            }
            Ok(if op == "bevel_half" {
                json!(q.half(theta))
            } else if op == "bevel_point" {
                json!(q.point(
                    theta,
                    n(a, "distance", 1.)?,
                    n(a, "side", 1.)?,
                    n(a, "phase", 0.)?
                ))
            } else {
                json!(q.section_point(theta, n(a, "z", 1.)?, n(a, "side", 1.)?, n(a, "phase", 0.)?))
            })
        }
        _ => Err("Unknown bevel operation".into()),
    }
}

pub(crate) fn spiral_stations(a: &Value) -> Result<Vec<(f64, Vec<Point>)>> {
    let points = Vec::<Point>::deserialize(&a["outer"]).map_err(|e| e.to_string())?;
    let distances = Vec::<f64>::deserialize(&a["distances"]).map_err(|e| e.to_string())?;
    if points.len() < 3
        || distances.len() < 2
        || points.len().saturating_mul(distances.len()) > 1_000_000
        || points
            .iter()
            .flatten()
            .chain(distances.iter())
            .any(|x| !x.is_finite())
    {
        return Err("Spiral station batch exceeds its geometry domain or resource limit".into());
    }
    let outer = n(a, "cone_distance", 0.)?;
    let angle = n(a, "cone_angle", 0.)?;
    let heel = n(a, "heel", 0.)?;
    let toe = n(a, "toe", 0.)?;
    let beta = n(a, "beta", 0.)?;
    let hand = n(a, "hand", 1.)?;
    let mut rows = Vec::with_capacity(distances.len());
    for distance in &distances {
        crate::protocol::control_check()?;
        let trace = spiral_trace(*distance, outer, angle, beta, hand)?;
        let contour: Vec<_> = points
            .iter()
            .map(|[x, y]| {
                crate::profiles::rotate([x * distance / outer, y * distance / outer], trace)
            })
            .collect();
        rows.push((
            if *distance == distances[0] {
                0.
            } else {
                distance / outer * heel - toe
            },
            contour,
        ));
    }

    Ok(rows)
}
