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
