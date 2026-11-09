// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Matching ZA/ZI helicoid envelope and sharp hob-tip sweeps.
//! Houser & Su (1999), equations 4,5,11-13; frames in docs/technical/worm.md.
use crate::{
    precision::Result,
    profiles::{Point, inv_roll, n, polar, radius, rotate},
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::BTreeMap;
use std::f64::consts::{PI, TAU};
const CHORD: f64 = 0.005;
#[derive(Clone, Serialize, Deserialize)]
pub struct Worm {
    module: f64,
    starts: u32,
    teeth: u32,
    rp: f64,
    k: f64,
    #[serde(rename = "R")]
    r: f64,
    a: f64,
    hand: f64,
    length: f64,
    backlash: f64,
    variant: String,
    alpha: f64,
    gamma: f64,
    rb: f64,
    tip: f64,
    root: f64,
    hob_tip: f64,
    reference: f64,
}
impl Worm {
    fn new(v: &Value) -> Result<Self> {
        let m = n(v, "module", 2.)?;
        let starts = n(v, "starts", 1.)?;
        let teeth = n(v, "teeth", 30.)?;
        let rp = n(v, "diameter", 20.)? / 2.;
        let hand = n(v, "worm_hand", 1.)?;
        let length = n(v, "length", 24.)?;
        let backlash = n(v, "backlash", 0.15)?;
        let variant = v["variant"].as_str().unwrap_or("za").to_string();
        let alpha = n(v, "pressure", 20.)?.to_radians();
        if !(m > 0.
            && rp > 0.
            && (1. ..=100.).contains(&starts)
            && starts.fract() == 0.
            && (3. ..=100000.).contains(&teeth)
            && teeth.fract() == 0.
            && [-1., 1.].contains(&hand)
            && length > 0.
            && backlash >= 0.
            && 0. < alpha
            && alpha < PI / 2.
            && ["za", "zi"].contains(&variant.as_str()))
        {
            return Err("Invalid cylindrical worm parameters".into());
        }
        let k = m * starts / 2.;
        let r = m * teeth / 2.;
        let a = rp + r;
        let gamma = (k / rp).atan();
        let rb = rp * (alpha.tan() / gamma.tan()).atan().cos();
        Ok(Self {
            module: m,
            starts: starts as u32,
            teeth: teeth as u32,
            rp,
            k,
            r,
            a,
            hand,
            length,
            backlash,
            variant,
            alpha,
            gamma,
            rb,
            tip: rp + m,
            root: rp - 1.25 * m,
            hob_tip: rp + 1.25 * m,
            reference: PI / 2. + (hand * k * PI / 2. + length / 2.) / r,
        })
    }
    fn half(&self, r: f64, cutter: bool) -> f64 {
        let half = PI / (2. * self.starts as f64)
            + if cutter {
                self.backlash / (4. * self.k)
            } else {
                -self.backlash / (4. * self.k)
            };
        if self.variant == "za" {
            half - (r - self.rp) * self.alpha.tan() / self.k
        } else {
            let inv = |r: f64| inv_roll(((r / self.rb).powi(2) - 1.).max(0.).sqrt());
            half + inv(self.rp) - inv(r)
        }
    }
    fn derivative(&self, r: f64) -> f64 {
        if self.variant == "za" {
            -self.alpha.tan() / self.k
        } else {
            -(r * r - self.rb * self.rb).max(0.).sqrt() / (self.rb * r)
        }
    }
    fn generator(&self, r: f64, h: f64, side: i32) -> Result<([f64; 3], [f64; 3])> {
        if r <= h.abs() || ![-1, 1].contains(&side) {
            return Err("Worm cutter point outside its radial domain".into());
        }
        let y = -(r * r - h * h).sqrt();
        let psi = -PI - (h / r).asin();
        let side = side as f64;
        let u =
            self.k * (self.hand * (psi + PI / 2.) - side * self.half(r, true)) - self.length / 2.;
        let derivative = self.derivative(r);
        let ny = self.k * side * derivative * y / r + self.hand * self.k * h / r.powi(2);
        let nz = self.k * side * derivative * h / r - self.hand * self.k * y / r.powi(2);
        Ok(([u, y, h], [1., ny, nz]))
    }
    fn contact(&self, r: f64, h: f64, side: i32) -> Result<(Point, [f64; 3], [f64; 3], f64)> {
        let (original, normal) = self.generator(r, h, side)?;
        let [u, y, _] = original;
        if normal[1].abs() < 1e-10 {
            return Err("Worm wheel envelope has a singular contact normal; reduce face width or lead angle.".into());
        }
        let x = (y + self.rp) / normal[1];
        let phi = (u - x) / (self.hand * self.k);
        let angle = (u - x) / self.r;
        Ok((
            [
                x * angle.cos() + (self.a + y) * angle.sin(),
                -x * angle.sin() + (self.a + y) * angle.cos(),
            ],
            original,
            normal,
            phi,
        ))
    }
}
#[derive(Clone, Serialize, Deserialize)]
pub struct Section {
    surface: Worm,
    height: f64,
    outer_radius: f64,
    root_radius: f64,
    starts: BTreeMap<i32, f64>,
    ends: BTreeMap<i32, Point>,
    flank_ends: BTreeMap<i32, f64>,
    undercut: bool,
}
impl Section {
    fn new(s: Worm, q: f64) -> Result<Self> {
        let mut result = Self {
            outer_radius: s.a - ((s.rp - s.module).powi(2) - q * q).sqrt(),
            root_radius: s.a - (s.hob_tip.powi(2) - q * q).sqrt(),
            starts: BTreeMap::new(),
            ends: BTreeMap::new(),
            flank_ends: [(-1, s.hob_tip), (1, s.hob_tip)].into(),
            undercut: false,
            surface: s,
            height: q,
        };
        let s = &result.surface;
        for side in [-1, 1] {
            let minimum = (q.abs() + 1e-7).max(s.root).max(if s.variant == "zi" {
                s.rb * (1. + 1e-8)
            } else {
                0.
            });
            let mut previous = s.hob_tip;
            let (candidate, _, normal, _) = s.contact(previous, q, side)?;
            let mut previous_normal = normal[1];
            let mut last = radius(candidate) - result.outer_radius;
            let mut bracket = None;
            for i in 1..=64 {
                let r = s.hob_tip + (minimum - s.hob_tip) * i as f64 / 64.;
                let (candidate, _, normal, _) = s.contact(r, q, side)?;
                if previous_normal * normal[1] <= 0. {
                    return Err("Worm wheel contact normal crosses a singularity; reduce width or lead angle.".into());
                }
                previous_normal = normal[1];
                let value = radius(candidate) - result.outer_radius;
                if value >= 0. && last < 0. {
                    bracket = Some((r, previous));
                    break;
                }
                previous = r;
                last = value;
            }
            let(mut lo,mut hi)=bracket.ok_or("Worm wheel tip cannot meet the usable generated flank; reduce width or lead angle.")?;
            for _ in 0..42 {
                let mid = (lo + hi) / 2.;
                if radius(s.contact(mid, q, side)?.0) > result.outer_radius {
                    lo = mid
                } else {
                    hi = mid
                }
            }
            result.starts.insert(side, (lo + hi) / 2.);
            let (_, original, normal, _) = s.contact(s.hob_tip, q, side)?;
            result
                .ends
                .insert(side, [(original[1] + s.rp) / normal[1], original[0]]);
        }
        for side in [-1, 1] {
            result.trim(side)?;
        }
        if result.angle(result.flank(1, 0.)?) - result.angle(result.flank(-1, 0.)?)
            >= TAU / result.surface.teeth as f64 - 1e-7
        {
            return Err("Worm wheel tooth gaps overlap at the face edge; reduce width, pressure angle or backlash.".into());
        }
        Ok(result)
    }
    fn angle(&self, p: Point) -> f64 {
        let r = self.surface.reference;
        r + (p[1].atan2(p[0]) - r + PI).rem_euclid(TAU) - PI
    }
    fn flank(&self, side: i32, t: f64) -> Result<Point> {
        let start = *self.starts.get(&side).ok_or("Invalid worm flank side")?;
        let end = *self
            .flank_ends
            .get(&side)
            .ok_or("Invalid worm flank side")?;
        Ok(self
            .surface
            .contact(start + (end - start) * t, self.height, side)?
            .0)
    }
    fn fillet(&self, side: i32, t: f64) -> Point {
        let [end, u] = self.ends[&side];
        let x = end * (1. - t);
        let a = (u - x) / self.surface.r;
        [
            x * a.cos() + self.root_radius * a.sin(),
            -x * a.sin() + self.root_radius * a.cos(),
        ]
    }
    fn arc(&self, root: bool, t: f64) -> Result<Point> {
        let (lo, hi, r) = if root {
            (
                self.angle(self.fillet(-1, 1.)),
                self.angle(self.fillet(1, 1.)),
                self.root_radius,
            )
        } else {
            (
                self.angle(self.flank(1, 0.)?),
                self.angle(self.flank(-1, 0.)?) + TAU / self.surface.teeth as f64,
                self.outer_radius,
            )
        };
        Ok(polar(r, lo + (hi - lo) * t))
    }
    fn curve(&self, index: usize, t: f64) -> Result<Point> {
        match index {
            0 => self.flank(-1, t),
            1 => Ok(self.fillet(-1, t)),
            2 => self.arc(true, t),
            3 => Ok(self.fillet(1, 1. - t)),
            4 => self.flank(1, 1. - t),
            5 => self.arc(false, t),
            _ => Err("Unknown wheel curve".into()),
        }
    }
    fn gap(&self, counts: &[usize; 6]) -> Result<Vec<Point>> {
        let mut out = Vec::new();
        for (i, count) in counts.iter().enumerate() {
            for j in 0..*count {
                out.push(self.curve(i, j as f64 / *count as f64)?);
            }
        }
        Ok(out)
    }
    fn difference(&self, side: i32, t: f64) -> Result<Option<(f64, f64)>> {
        let p = self.flank(side, t)?;
        let square = p[0] * p[0] + p[1] * p[1] - self.root_radius.powi(2);
        if square < 0. {
            return Ok(None);
        }
        let xend = self.ends[&side][0];
        let x = xend.signum() * square.sqrt();
        let f = 1. - x / xend;
        if !(0. ..=1.).contains(&f) {
            return Ok(None);
        }
        Ok(Some((self.angle(p) - self.angle(self.fillet(side, f)), f)))
    }
    fn trim(&mut self, side: i32) -> Result<()> {
        let [xend, u] = self.ends[&side];
        if xend.abs() < 1e-12 {
            return Ok(());
        }
        let radius2 = |t: f64| -> Result<f64> {
            let p = self.flank(side, t)?;
            Ok(p[0] * p[0] + p[1] * p[1])
        };
        let (mut lo, mut hi) = (0., 1.);
        for _ in 0..45 {
            let left = (2. * lo + hi) / 3.;
            let right = (lo + 2. * hi) / 3.;
            if radius2(left)? < radius2(right)? {
                hi = right
            } else {
                lo = left
            }
        }
        let minimum = (lo + hi) / 2.;
        let edge = xend * xend + self.root_radius.powi(2);
        let mut grid: Vec<f64> = (0..64)
            .map(|j| j as f64 / 64.)
            .chain((1..22).map(|j| 1. - 2f64.powi(-j)))
            .collect();
        if radius2(minimum)? < edge - 1e-10 {
            lo = 0.;
            hi = minimum;
            for _ in 0..42 {
                let mid = (lo + hi) / 2.;
                if radius2(mid)? > edge {
                    lo = mid
                } else {
                    hi = mid
                }
            }
            let entry = (lo + hi) / 2.;
            grid.extend([entry + (1. - entry) * 1e-7, (entry + minimum) / 2., minimum]);
        }
        grid.sort_by(f64::total_cmp);
        grid.dedup();
        let mut previous: Option<(f64, f64)> = None;
        let mut bracket = None;
        for t in grid {
            if let Some((value, _)) = self.difference(side, t)? {
                if let Some((pt, pv)) = previous {
                    if value * pv < 0. {
                        bracket = Some((pt, t));
                        break;
                    }
                }
                if value.abs() > 1e-12 {
                    previous = Some((t, value));
                }
            }
        }
        let Some((mut lo, mut hi)) = bracket else {
            return Ok(());
        };
        let mut flo = self
            .difference(side, lo)?
            .ok_or("Lost worm undercut bracket")?
            .0;
        for _ in 0..45 {
            let mid = (lo + hi) / 2.;
            let fm = self
                .difference(side, mid)?
                .ok_or("Lost worm undercut bracket")?
                .0;
            if fm * flo > 0. {
                lo = mid;
                flo = fm
            } else {
                hi = mid
            }
        }
        let t = (lo + hi) / 2.;
        let (_, fraction) = self
            .difference(side, t)?
            .ok_or("Lost worm undercut solution")?;
        if t > 1. - 1e-6 {
            return Ok(());
        }
        let p = self.flank(side, t)?;
        let q = self.fillet(side, fraction);
        if (p[0] - q[0]).hypot(p[1] - q[1]) > 1e-7 {
            return Err(
                "Unable to resolve worm wheel undercut transition within numerical tolerance."
                    .into(),
            );
        }
        let start = self.starts[&side];
        self.flank_ends
            .insert(side, start + (self.surface.hob_tip - start) * t);
        self.ends.insert(side, [xend * (1. - fraction), u]);
        self.undercut = true;
        Ok(())
    }
}
fn chord(p: Point, a: Point, b: Point) -> f64 {
    let (dx, dy) = (b[0] - a[0], b[1] - a[1]);
    let norm = dx * dx + dy * dy;
    let t = if norm > 0. {
        ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / norm
    } else {
        0.
    }
    .clamp(0., 1.);
    (p[0] - a[0] - t * dx).hypot(p[1] - a[1] - t * dy)
}
fn crossing(a: Point, b: Point, c: Point, d: Point) -> bool {
    if (0..2)
        .any(|i| a[i].max(b[i]) < c[i].min(d[i]) - 1e-9 || c[i].max(d[i]) < a[i].min(b[i]) - 1e-9)
    {
        return false;
    }
    let side = |p: Point, q: Point, r: Point| {
        (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    };
    side(a, b, c) * side(a, b, d) < -1e-16 && side(c, d, a) * side(c, d, b) < -1e-16
}
#[derive(Serialize)]
pub(crate) struct WheelSections {
    pub sections: Vec<(f64, Vec<Point>)>,
    pub metadata: Value,
}
pub(crate) fn wheel(v: &Value, hole_vertices: usize) -> Result<WheelSections> {
    let s = Worm::new(v)?;
    let width = n(v, "width", 10.)?;
    if width <= 0. || s.rp <= s.module || width / 2. >= 0.95 * (s.rp - s.module) {
        return Err("Wheel too wide for the usable worm root-clearance cylinder (half width < 0.95 (rp - mx)).".into());
    }
    if s.half(s.hob_tip, true) <= 0. {
        return Err(
            "Worm wheel generating hob has a pointed tip; reduce pressure angle or module.".into(),
        );
    }
    let mut cache: Vec<(f64, Section)> = Vec::new();
    let mut section = |q: f64| -> Result<Section> {
        if let Some((_, p)) = cache.iter().find(|(h, _)| *h == q) {
            return Ok(p.clone());
        }
        let p = Section::new(s.clone(), q)?;
        cache.push((q, p.clone()));
        Ok(p)
    };
    let probes: Result<Vec<_>> = (0..5)
        .map(|j| section(width * (j as f64 / 4. - 0.5)))
        .collect();
    let probes = probes?;
    let mut counts = [8, 4, 4, 4, 8, 4];
    for (i, curve_count) in counts.iter_mut().enumerate() {
        let mut resolved = false;
        for _ in 0..6 {
            let count = *curve_count;
            let mut error = 0f64;
            for p in &probes {
                for j in 0..count {
                    error = error.max(chord(
                        p.curve(i, (j as f64 + 0.5) / count as f64)?,
                        p.curve(i, j as f64 / count as f64)?,
                        p.curve(i, (j + 1) as f64 / count as f64)?,
                    ));
                }
            }
            if error <= CHORD {
                resolved = true;
                break;
            }
            *curve_count *= 2;
        }
        if !resolved {
            return Err("Worm wheel flank exceeds the bounded curve refinement limit.".into());
        }
    }
    let mut levels = vec![-width / 2., 0., width / 2.];
    let mut resolved = false;
    for _ in 0..7 {
        let mut refined = vec![levels[0]];
        let mut changed = false;
        for pair in levels.windows(2) {
            let (lo, hi) = (pair[0], pair[1]);
            let a = section(lo)?.gap(&counts)?;
            let b = section(hi)?.gap(&counts)?;
            let c = section((lo + hi) / 2.)?.gap(&counts)?;
            let error = a
                .iter()
                .zip(b.iter())
                .zip(c.iter())
                .map(|((x, y), z)| (z[0] - (x[0] + y[0]) / 2.).hypot(z[1] - (x[1] + y[1]) / 2.))
                .fold(0., f64::max);
            if error > CHORD {
                refined.push((lo + hi) / 2.);
                changed = true;
            }
            refined.push(hi);
        }
        levels = refined;
        if 2 * (counts.iter().sum::<usize>() * s.teeth as usize + hole_vertices)
            * (levels.len() - 1)
            + 2
            > 250000
        {
            return Err(
                "Worm wheel too detailed (250,000 face limit): reduce width or tooth count.".into(),
            );
        }
        if !changed {
            resolved = true;
            break;
        }
    }
    if !resolved {
        return Err("Worm wheel exceeds the bounded face refinement limit.".into());
    }
    let mut result = Vec::new();
    let mut undercut = false;
    for q in &levels {
        let sec = section(*q)?;
        undercut |= sec.undercut;
        let gap = sec.gap(&counts)?;
        let pitch = TAU / s.teeth as f64;
        let mut chain = gap.clone();
        chain.extend(gap.iter().map(|p| rotate(*p, pitch)));
        chain.push(rotate(gap[0], 2. * pitch));
        for i in 0..gap.len() {
            for j in i + 2..chain.len() - 1 {
                if crossing(chain[i], chain[i + 1], chain[j], chain[j + 1]) {
                    return Err(
                        "Worm wheel generated contour crosses itself; reduce width or lead angle."
                            .into(),
                    );
                }
            }
        }
        let points: Vec<_> = (0..s.teeth)
            .flat_map(|tooth| {
                gap.iter()
                    .map(move |p| rotate(*p, TAU * tooth as f64 / s.teeth as f64))
            })
            .collect();
        result.push((*q, points));
    }
    Ok(WheelSections {
        sections: result,
        metadata: json!({"method":"matching ZA/ZI helicoid envelope with swept hob-tip transitions","conjugate":true,"centre_distance_mm":s.a,"reference_wheel_radius_mm":s.r,
        "generating_hob_tip_radius_mm":s.hob_tip,"root_clearance_mm":0.25*s.module,"pair_axial_backlash_mm":s.backlash,"chord_threshold_mm":CHORD,"undercut_trimmed":undercut,
        "section_count":levels.len(),"points_per_tooth":counts.iter().sum::<usize>(),"domain":"Ideal rigid cylindrical screw; sampled envelope, no strength or manufacturing certification"}),
    })
}
pub fn call(op: &str, a: &Value) -> Result<Value> {
    if op == "worm_screw_profile" {
        return screw_profile(a);
    }
    if op == "worm_wheel_sections" {
        let h = a["hole_vertices"].as_u64().unwrap_or(0);
        if h > 1000000 {
            return Err("Hole vertex limit exceeded".into());
        }
        return serde_json::to_value(wheel(&a["values"], h as usize)?).map_err(|e| e.to_string());
    }
    if op == "worm_section" {
        return Ok(json!(Section::new(
            Worm::new(&a["values"])?,
            n(a, "height", 0.)?
        )?));
    }
    if op == "worm_section_angle" {
        let section: Section =
            serde_json::from_value(a["section"].clone()).map_err(|e| e.to_string())?;
        let p: Point = serde_json::from_value(a["point"].clone()).map_err(|e| e.to_string())?;
        return Ok(json!(section.angle(p)));
    }
    if op == "worm_section_gap" {
        let section: Section =
            serde_json::from_value(a["section"].clone()).map_err(|e| e.to_string())?;
        let counts: [usize; 6] =
            serde_json::from_value(a["counts"].clone()).map_err(|e| e.to_string())?;
        if counts.iter().any(|n| *n == 0 || *n > 100000) {
            return Err("Invalid wheel curve count".into());
        }
        return Ok(json!(section.gap(&counts)?));
    }
    if op == "worm_section_curve" {
        let section: Section =
            serde_json::from_value(a["section"].clone()).map_err(|e| e.to_string())?;
        return Ok(json!(section.curve(
            a["index"].as_u64().ok_or("Curve index required")? as usize,
            n(a, "t", 0.)?
        )?));
    }
    let s = Worm::new(&a["values"])?;
    let r = n(a, "radius", s.rp)?;
    let height = n(a, "height", 0.)?;
    let side = n(a, "side", 1.)?;
    match op {
        "worm_surface" => Ok(json!(s)),
        "worm_half" => Ok(json!(s.half(r, a["cutter"].as_bool().unwrap_or(false)))),
        "worm_derivative" => Ok(json!(s.derivative(r))),
        "worm_generator" => Ok(json!(s.generator(r, height, side as i32)?)),
        "worm_contact" => Ok(json!(s.contact(r, height, side as i32)?)),
        _ => Err("Unknown worm operation".into()),
    }
}

/// The screw's cross-section and explicit root runout, before axial twisting.
pub fn screw_profile(a: &Value) -> Result<Value> {
    use crate::profiles::{clean, sample};
    let starts = n(a, "starts", 1.)?;
    let m = n(a, "module", 2.)?;
    let rp = n(a, "diameter", 20.)? / 2.;
    let pressure = n(a, "pressure", 20.)?.to_radians();
    let backlash = n(a, "backlash", 0.15)?;
    if starts < 1.
        || starts > 100.
        || starts.fract() != 0.
        || m <= 0.
        || rp <= 1.25 * m
        || backlash < 0.
    {
        return Err("Invalid cylindrical screw profile domain".into());
    }
    let variant = a["variant"].as_str().unwrap_or("za");
    let root = rp - 1.25 * m;
    let tip = rp + m;
    let k = m * starts / 2.;
    let pitch = TAU / starts;
    let rb = rp * pressure.cos();
    let inv = |r: f64| inv_roll(((r / rb).powi(2) - 1.).max(0.).sqrt());
    let half = |r: f64| {
        if variant == "za" {
            PI / (2. * starts) - (r - rp) * pressure.tan() / k - backlash / (4. * k)
        } else {
            PI / (2. * starts) - backlash / (4. * rp) + inv(rp) - inv(r)
        }
    };
    let start = if variant == "za" { root } else { root.max(rb) };
    if half(tip) <= 0. || half(start) >= pitch / 2. {
        return Err(if variant == "za" {
            "Profilo ZA appuntito o fianchi sovrapposti: controllare angolo, modulo e clearance."
        } else {
            "Impossible ZI screw flank thickness."
        }
        .into());
    }
    let mut points = Vec::new();
    let add = |out: &mut Vec<Point>, mut segment: Vec<Point>, trim: bool| {
        if trim {
            segment.pop();
        }
        out.extend(segment);
    };
    for j in 0..starts as usize {
        let a = j as f64 * pitch;
        let ar = half(start);
        let at = half(tip);
        add(
            &mut points,
            sample(&|q| polar(root, a + q), -pitch / 2., -ar, 0.015, false)?,
            true,
        );
        if variant == "zi" {
            points.push(polar(root, a - ar));
        }
        add(
            &mut points,
            sample(&|r| polar(r, a - half(r)), start, tip, 0.015, false)?,
            true,
        );
        add(
            &mut points,
            sample(&|q| polar(tip, a + q), -at, at, 0.015, false)?,
            true,
        );
        add(
            &mut points,
            sample(&|r| polar(r, a + half(r)), tip, start, 0.015, false)?,
            variant == "za",
        );
        if variant == "zi" {
            points.push(polar(root, a + ar));
            let arc = sample(&|q| polar(root, a + q), ar, pitch / 2., 0.015, false)?;
            points.extend_from_slice(&arc[1..]);
        } else {
            add(
                &mut points,
                sample(&|q| polar(root, a + q), ar, pitch / 2., 0.015, false)?,
                true,
            );
        }
    }
    Ok(json!(clean(points)))
}
