// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Finished tip limits and a second involute from a normal rack ramp.
//! OPEO, "Generation of semi-topping profiles", 2021/2026; see variants.md.
//! Internal teeth retain the application's nominal constructed-root model.
use crate::{precision::Result, profiles::n};
use serde_json::{Value, json};

pub const KEYS: [&str; 3] = ["topping_mm", "semitopping_mm", "semitopping_angle_deg"];

/// Preserve exact input sources when routing a member's controls to the kernel.
pub fn member(v: &Value, role: &str) -> Value {
    let mut out = json!({});
    for key in KEYS {
        let name = if role.is_empty() {
            key.into()
        } else {
            format!("{role}_{key}")
        };
        if let Some(value) = v.get(&name) {
            out[key] = value.clone();
        }
    }
    out
}

#[derive(Clone)]
pub struct Treatment {
    pub topping: f64,
    pub height: f64,
    pub angle_deg: f64,
}

pub struct Chamfer {
    pub join: f64,
    pub base: f64,
    pub half: f64,
    pub pitch: f64,
    pub internal: bool,
}

fn inv(r: f64, base: f64) -> f64 {
    crate::profiles::inv_roll(((r / base).powi(2) - 1.).max(0.).sqrt())
}

impl Chamfer {
    pub fn angle(&self, r: f64) -> f64 {
        self.half
            + if self.internal { -1. } else { 1. }
                * (inv(self.pitch, self.base) - inv(r, self.base))
    }
    pub fn recipe(&self, start: f64, end: f64) -> Value {
        json!({"kind":"involute_flank", "rp":self.pitch,"rb":self.base,
            "half":self.half,"internal":self.internal,"start":start,"end":end})
    }
}

impl Treatment {
    pub fn read(a: &Value) -> Result<Self> {
        let out = Self {
            topping: n(a, KEYS[0], 0.)?,
            height: n(a, KEYS[1], 0.)?,
            angle_deg: n(a, KEYS[2], 45.)?,
        };
        if out.topping < 0. || out.height < 0. || !(0. ..90.).contains(&out.angle_deg) {
            return Err("Tooth tips: removal and height must be nonnegative; angle must be between 0 and 90 degrees.".into());
        }
        Ok(out)
    }
    pub fn enabled(&self) -> bool {
        self.topping > 0. || self.height > 0.
    }
    pub fn tip(&self, nominal: f64, pitch: f64, internal: bool) -> Result<f64> {
        let tip = nominal
            + if internal {
                self.topping
            } else {
                -self.topping
            };
        if self.enabled()
            && if internal {
                tip + self.height >= pitch
            } else {
                tip - self.height <= pitch
            }
        {
            return Err("Tooth tips: topping and semitopping must leave a working addendum above the reference pitch surface.".into());
        }
        Ok(tip)
    }
    #[allow(clippy::too_many_arguments)]
    pub fn chamfer(
        &self,
        pitch: f64,
        base: f64,
        half: f64,
        tip: f64,
        normal_deg: f64,
        cos_beta: f64,
        internal: bool,
    ) -> Result<Option<Chamfer>> {
        if self.height == 0. {
            return Ok(None);
        }
        if self.angle_deg <= normal_deg {
            return Err("Semitopping angle must exceed the normal pressure angle.".into());
        }
        let sign = if internal { -1. } else { 1. };
        let join = tip - sign * self.height;
        let at = (self.angle_deg.to_radians().tan() / cos_beta).atan();
        let b = pitch * at.cos();
        if tip.min(join) <= b {
            return Err("Semitopping lies below its generating base circle.".into());
        }
        let anchor = half + sign * (inv(pitch, base) - inv(join, base));
        let secondary_half = anchor - sign * (inv(pitch, b) - inv(join, b));
        let curve = Chamfer {
            join,
            base: b,
            half: secondary_half,
            pitch,
            internal,
        };
        if curve.angle(tip) <= 1e-10 {
            return Err(
                "Semitopping removes the entire tooth top land; reduce its height or angle.".into(),
            );
        }
        Ok(Some(curve))
    }
    pub fn record(
        &self,
        metadata: &mut Value,
        nominal: f64,
        tip: f64,
        curve: Option<&Chamfer>,
        cos_beta: f64,
    ) {
        if !self.enabled() {
            return;
        }
        metadata["tip_treatment"] = json!({"topping_mm":self.topping,"semitopping_mm":self.height,
            "semitopping_angle_deg":self.angle_deg,"nominal_tip_radius_mm":nominal,
            "finished_tip_radius_mm":tip,"active_tip_radius_mm":curve.map_or(tip, |c|c.join),
            "angle_convention":"normal generating-rack ramp pressure angle; radial height on finished gear",
            "construction":if curve.is_some(){"secondary involute, intersecting the unchanged working flank"}else{"radial tip limit"},
            "scope":"nominal geometry; internal roots retain constructed blend; no production cutter qualification"});
        if let Some(c) = curve {
            let angle = c.angle(tip);
            let transverse = 2. * tip * angle;
            let cb =
                1. / (1. + (tip / c.pitch).powi(2) * (1. / cos_beta.powi(2) - 1.).max(0.)).sqrt();
            let widths = &mut metadata["tooth_thickness"];
            widths["tip"]["generated_transverse_arc_mm"] = json!(transverse);
            widths["tip"]["generated_normal_arc_mm"] = json!(transverse * cb);
            widths["tip"]["generated_transverse_chord_mm"] = json!(2. * tip * angle.sin());
            widths["basis"] = json!(
                "Finished tip widths include semitopping; reference and usable limits refer to the unchanged primary involute."
            );
            let z = metadata["measurement_geometry"]["teeth"]
                .as_u64()
                .unwrap_or(0) as f64;
            let mn = if z > 0. {
                2. * c.pitch * cos_beta / z
            } else {
                0.
            };
            if mn > 0. {
                metadata["tooth_thickness"]["tip_chord_over_normal_module"] =
                    json!(2. * tip * angle.sin() / mn);
            }
        }
    }
}

/// Local removed head sections for the viewer. Reuse the generating curves and
/// the rack's constructed vertices; this operation never changes a design.
pub fn preview(a: &Value) -> Result<Value> {
    use crate::profiles::{Point, clean, polar, rotate, sample};
    use std::f64::consts::{PI, TAU};
    let source = &a["source"];
    let p = &source["parameters"];
    let linear = source["kind"] == "linear";
    if !linear && source["kind"] != "radial" {
        return Err("Tooth detail needs its original profile construction.".into());
    }
    let settings = if linear { member(p, "rack") } else { p.clone() };
    let treatment = Treatment::read(&settings)?;
    let m = if linear {
        n(p, "module", 2.)?
    } else {
        n(p, "depth", 2.)?
    };
    if m <= 0. {
        return Err("Tooth detail needs a positive normal module.".into());
    }
    let mut polygons: Vec<Vec<Point>> = Vec::new();
    let mut add = |points: Vec<Point>| {
        let mut points = clean(points);
        let area = points
            .iter()
            .zip(points.iter().cycle().skip(1))
            .take(points.len())
            .map(|(a, b)| a[0] * b[1] - a[1] * b[0])
            .sum::<f64>()
            / 2.;
        if points.len() >= 3 && area.abs() > m * m * 1e-14 {
            if area < 0. {
                points.reverse();
            }
            polygons.push(points);
        }
    };
    let (target, direction);
    if linear {
        let info = &source["dimensions"];
        let count = n(p, "rack_teeth", 24.)?;
        if !(8. ..=200.).contains(&count) || count.fract() != 0. {
            return Err("Tooth detail needs a valid finite rack tooth count.".into());
        }
        let count = count as usize;
        let mut original = p.clone();
        original["rack_topping_mm"] = json!(0.);
        original["rack_semitopping_mm"] = json!(0.);
        let before = crate::rack_drive::outline(&original, info, 0., 1.)?;
        let after = crate::rack_drive::outline(p, info, 0., 1.)?;
        let height = m - treatment.topping;
        let join = height - treatment.height;
        let center = count / 2;
        let middle = 3 + 4 * (count - 1 - center);
        target = [(before[middle + 1][0] + before[middle + 2][0]) / 2., height];
        direction = [0., 1.];
        if treatment.enabled() {
            let size = if treatment.height > 0. { 6 } else { 4 };
            for j in center - 1..=center + 1 {
                let b = 3 + 4 * (count - 1 - j);
                let c = 3 + size * (count - 1 - j);
                let right = before[b + 1];
                let left = before[b + 2];
                let at_join = |root: Point, tip: Point| {
                    let f = (join - root[1]) / (tip[1] - root[1]);
                    [root[0] + f * (tip[0] - root[0]), join]
                };
                let rj = at_join(before[b], right);
                let lj = at_join(before[b + 3], left);
                let ri = if size == 6 { c + 2 } else { c + 1 };
                let li = ri + 1;
                if treatment.topping > 0. {
                    add(vec![lj, left, right, rj, after[ri], after[li]]);
                } else {
                    add(vec![lj, left, after[li]]);
                    add(vec![rj, right, after[ri]]);
                }
            }
        }
    } else {
        let profile = &a["profile"];
        let g = &profile["measurement_geometry"];
        let z = n(g, "teeth", 0.)?;
        let rp = n(g, "reference_radius_mm", 0.)?;
        let rb = n(g, "base_radius_mm", 0.)?;
        let half = n(g, "reference_half_angle_rad", 0.)?;
        if z < 3. || rp <= 0. || rb <= 0. {
            return Err("Incomplete tooth detail provenance.".into());
        }
        let internal = g["internal"].as_bool().unwrap_or(false);
        let sign = if internal { -1. } else { 1. };
        let tip = n(profile, "tip_radius_mm", 0.)?;
        let nominal = n(&profile["tip_treatment"], "nominal_tip_radius_mm", tip)?;
        let join = tip - sign * treatment.height;
        let primary = Chamfer {
            join,
            base: rb,
            half,
            pitch: rp,
            internal,
        };
        let cb = m / n(p, "mt", m)?;
        let secondary = treatment.chamfer(
            rp,
            rb,
            half,
            tip,
            n(p, "normal_pressure", 20.)?,
            cb,
            internal,
        )?;
        let finished = secondary.as_ref().unwrap_or(&primary);
        let phase = n(source, "phase_rad", 0.)?;
        let pitch = TAU / z;
        let focus = phase + ((PI / 2. - phase) / pitch).round() * pitch;
        target = polar(tip, focus);
        direction = [sign * focus.cos(), sign * focus.sin()];
        if treatment.enabled() {
            if primary.angle(nominal) <= 0. {
                return Err(
                    "Original tooth has no top land for a removed-material preview.".into(),
                );
            }
            let tol = (m * 0.0001)
                .min((treatment.topping + treatment.height) / 30.)
                .max(m * 1e-9);
            let old = sample(&|r| polar(r, primary.angle(r)), join, nominal, tol, false)?;
            let new = sample(&|r| polar(r, finished.angle(r)), join, tip, tol, false)?;
            let mirror = |q: Point| [q[0], -q[1]];
            let arc =
                |r: f64, start: f64, end: f64| sample(&|t| polar(r, t), start, end, tol, false);
            for angle in [focus - pitch, focus, focus + pitch] {
                if treatment.topping > 0. {
                    let mut chip = old.clone();
                    chip.extend(arc(
                        nominal,
                        primary.angle(nominal),
                        -primary.angle(nominal),
                    )?);
                    chip.extend(old.iter().rev().copied().map(mirror));
                    chip.extend(new.iter().copied().map(mirror));
                    chip.extend(arc(tip, -finished.angle(tip), finished.angle(tip))?);
                    chip.extend(new.iter().rev().copied());
                    add(chip.into_iter().map(|q| rotate(q, angle)).collect());
                } else {
                    let mut chip = old.clone();
                    chip.extend(arc(tip, primary.angle(tip), finished.angle(tip))?);
                    chip.extend(new.iter().rev().copied());
                    add(chip.iter().copied().map(|q| rotate(q, angle)).collect());
                    add(chip.into_iter().map(|q| rotate(mirror(q), angle)).collect());
                }
            }
        }
    }
    Ok(
        json!({"polygons":polygons,"target_xy":target,"direction_xy":direction,
        "normal_module_mm":m,"scope":"three tooth heads; nominal removed material in the upper working band"}),
    )
}
