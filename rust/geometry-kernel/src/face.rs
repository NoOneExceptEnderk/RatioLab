// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Equal-count involute pinion envelope, NASA/CR2000-209909 eqs.21-24,63-69
//! and NASA/CR2005-213443 eqs.15-18. Custom crest/root and joined cusp trimming;
//! numerical float/libm enclosures are not a manufacturing certification.
use crate::{
    bevel_pair as bp,
    construction_interval::I,
    geometry_data::{Construction, Part, Station},
    precision::Result,
    profiles::{Point, n, radius, rotate},
};
use serde_json::{Value, json};
use std::{
    cell::RefCell,
    collections::{HashMap, VecDeque},
    f64::consts::{PI, TAU},
    rc::Rc,
};
const REFINEMENT: f64 = 0.003;
#[path = "face_joined.rs"]
mod joined;
use joined::Joined;
type P3 = [f64; 3];
type Band = [f64; 3];
type Contact = [f64; 6];
type Cell = [I; 8];
type Grids = (Vec<f64>, Vec<Vec<f64>>, usize);
pub(super) struct Generator {
    v: Value,
    e: f64,
    m: f64,
    g: f64,
    joined: bool,
    beta: f64,
    rp: f64,
    reference: f64,
    alpha: f64,
    rb: f64,
    k: f64,
    height: f64,
    low: f64,
    high: f64,
    root_z: f64,
    x0: f64,
    x1: f64,
    start: f64,
    pinion: Value,
    bands: Vec<Band>,
    certificates: Vec<Value>,
    outer: f64,
    engagement: Value,
    joined_surface: Option<Joined>,
    cache: RefCell<HashMap<[u64; 4], [f64; 2]>>,
}
impl Generator {
    fn clear_evaluations(&self) {
        self.cache.borrow_mut().clear();
        if let Some(s) = &self.joined_surface {
            s.clear_evaluations()
        }
    }
    fn new(v: &Value) -> Result<Self> {
        bp::validate(v)?;
        let m = n(v, "module", 2.)?;
        let e = n(v, "offset", 0.)?;
        let zp = n(v, "pinion", 24.)?;
        let zw = n(v, "wheel", 72.)?;
        let g = zp / zw;
        let variant = v["variant"].as_str().unwrap_or("spur");
        if !["spur", "helical", "double_helical"].contains(&variant) {
            return Err("Unknown face gear variant".into());
        }
        if g >= 1. {
            return Err("Face wheel must have more teeth than its pinion.".into());
        }
        let beta = if variant == "spur" {
            0.
        } else {
            n(v, "helix", 15.)?
        };
        if beta.abs() > 45. {
            return Err("Face pinion helix outside the supported domain".into());
        }
        let joined = variant == "double_helical" && v["double_style"] == "joined";
        if variant == "double_helical"
            && !["joined", "separated"].contains(&v["double_style"].as_str().unwrap_or(""))
        {
            return Err("Unknown double face helix style".into());
        }
        let rp = m * zp / (2. * beta.to_radians().cos());
        let reference = rp / g;
        if e.abs() >= reference / 2. {
            return Err("Face shaft offset must be smaller than half the reference wheel radius; reduce offset or enlarge the gears.".into());
        }
        let alpha = (n(v, "pressure", 20.)?.to_radians().tan() / beta.to_radians().cos()).atan();
        let rb = rp * alpha.cos();
        let k = beta.to_radians().tan() / rp;
        let height = 2. * rp;
        let add = n(v, "face_addendum", 0.65)?;
        let base = n(v, "base", 6.)?;
        if add <= 0. || base <= 0. || n(v, "radial_setting", 4.)? < 0. {
            return Err(
                "Positive face backing/addendum and nonnegative radial setting required".into(),
            );
        }
        let low = rp - add * m;
        let high = rp + 1.25 * m;
        let root_z = height - high;
        let x0 = reference + n(v, "radial_setting", 4.)?;
        let width = n(v, "width", 8.)?;
        let x1 = x0 + width;
        if low <= rb + 0.025 * m {
            return Err("Face crest reaches the pinion base-cylinder branch; reduce face addendum or increase pinion teeth / pressure.".into());
        }
        if n(v, "backlash", 0.15)? >= 0.7 * m {
            return Err("Face pair backlash must be below 0.7 normal module.".into());
        }
        // Carry source numbers to the existing decimal analytic core. Only sampled
        // envelope coordinates cross to binary64; analytic metadata keeps its API.
        let raw = |key: &str, default: f64| v.get(key).cloned().unwrap_or(json!(default));
        let mut pinion = crate::profiles::gear_part(
            &json!({"name":"Face_pinion","z":raw("pinion",24.),"m":raw("module",2.),"pressure":raw("pressure",20.),"backlash":raw("backlash",0.15),"width":raw("width",8.),"bore":raw("bore",0.),"center":[0.,0.],"phase":-PI/2.,"helix":if variant=="spur"{json!(0.)}else{raw("helix",15.)},"internal":false,"rim":5.,"zoff":x0,"shift":0.,"ha":1.,"hf":1.25,"minimum_join_radius_mm":null,"cutter_allowance":false,"rack_tip_radius_mm":null,"safe_pair_sampling":false}),
        )?;
        pinion["frame"] = json!([[0., e, height], [0., 1., 0.], [0., 0., 1.], [1., 0., 0.]]);
        let start = n(
            &pinion["profile_metadata"]["tooth_profile"],
            "involute_start_radius_mm",
            0.,
        )?;
        let mut bands = vec![[x0, x1, k]];
        if variant == "double_helical" {
            let gap = n(v, "gap", 0.)?;
            let half = (width - gap) / 2.;
            if gap < 0. || (!joined && gap < m) || half <= 1. {
                return Err("Double face gears require separated bands: gap at least one normal module and more than 1 mm per half.".into());
            }
            let points: Vec<Point> =
                serde_json::from_value(pinion["outer"].clone()).map_err(|e| e.to_string())?;
            let core = points
                .iter()
                .map(|p| radius(*p))
                .fold(f64::INFINITY, f64::min)
                * 0.96;
            pinion["double"] = json!(true);
            pinion["gap"] = json!(gap);
            pinion["core_radius"] = json!(core);
            if n(v, "bore", 0.)? / 2. >= core - 0.25 {
                return Err("Pinion bore reaches the continuous double-helix core.".into());
            }
            let shoulder = 0.15_f64.min(half * 0.08).min(gap * 0.2);
            bands = vec![
                [x0, x0 + half - shoulder, k],
                [x1 - half + shoulder, x1, -k],
            ];
            if joined && k == 0. {
                bands = vec![[x0, x1, 0.]]
            }
        }
        let mut result = Self {
            v: v.clone(),
            e,
            m,
            g,
            joined,
            beta,
            rp,
            reference,
            alpha,
            rb,
            k,
            height,
            low,
            high,
            root_z,
            x0,
            x1,
            start,
            pinion,
            bands,
            certificates: Vec::new(),
            outer: 0.,
            engagement: Value::Null,
            joined_surface: None,
            cache: RefCell::new(HashMap::new()),
        };
        for &band in &result.bands {
            result.certificates.push(result.certify(band)?)
        }
        result.outer = result
            .certificates
            .iter()
            .map(|q| q["radius_upper_mm"].as_f64().unwrap())
            .fold(0., f64::max)
            + m;
        if n(v, "output_bore", 0.)? / 2. >= x0 - 0.8 {
            return Err(
                "Face wheel bore reaches the tooth band; reduce bore / increase radial setting."
                    .into(),
            );
        }
        if !joined
            && result.bands.len() > 1
            && n(&result.certificates[0], "radius_upper_mm", 0.)? + 0.25 * m >= result.bands[1][0]
        {
            return Err("Mapped double face-gear bands overlap; increase central relief or reduce band width / helix.".into());
        }
        result.check_widths()?;
        if joined && k != 0. {
            let surface = Joined::new(&result)?;
            result.engagement = surface.engagement(&result)?;
            result.joined_surface = Some(surface)
        } else {
            result.engagement = result.engagement()?
        }
        Ok(result)
    }
    fn twist(&self, x: f64) -> f64 {
        self.k
            * if self.bands.len() > 1 {
                (x - self.x0).min(self.x1 - x)
            } else {
                x - self.x0
            }
    }
    fn scalar(&self, y: f64, x: f64, h: f64, side: f64, k: f64) -> Result<[f64; 2]> {
        if ![y, x, h, side, k].iter().all(|p| p.is_finite())
            || side.abs() != 1.
            || x <= 0.
            || h <= 0.
        {
            return Err("Invalid face envelope coordinate or flank".into());
        }
        let s = y * y + h * h;
        let q = (s - self.rb * self.rb).sqrt();
        if q <= 0. || !q.is_finite() {
            return Err("Face envelope reaches the base-cylinder branch".into());
        }
        let f = k * s * (y + self.e) + side * x * q * y / self.rb + x * h - s / self.g;
        let d = k * (3. * y * y + h * h + 2. * self.e * y) + side * x * (q + y * y / q) / self.rb
            - 2. * y / self.g;
        if !f.is_finite() || !d.is_finite() {
            return Err("Nonfinite face envelope scalar or derivative".into());
        }
        Ok([f, d])
    }
    fn solve(&self, x: f64, h: f64, side: f64, k: f64) -> Result<[f64; 2]> {
        let key = [x.to_bits(), h.to_bits(), side.to_bits(), k.to_bits()];
        if let Some(row) = self.cache.borrow().get(&key) {
            return Ok(*row);
        }
        crate::protocol::control_check()?;
        let mut y = 0.;
        for _ in 0..45 {
            let [f, d] = self.scalar(y, x, h, side, k)?;
            if side * d <= 1e-8 {
                return Err("Face generating branch is singular; increase radial setting / reduce helix or width.".into());
            }
            if f.abs() < 1e-12 * self.rp * self.reference {
                let r = [y, d];
                if self.cache.borrow().len() < 100000 {
                    self.cache.borrow_mut().insert(key, r);
                }
                return Ok(r);
            }
            let mut step = (f / d).clamp(-self.rp * 0.2, self.rp * 0.2);
            let mut accepted = false;
            for _ in 0..20 {
                let trial = y - step;
                let [ff, dd] = self.scalar(trial, x, h, side, k)?;
                if trial.abs() < self.rp * 0.75 && side * dd > 1e-8 && ff.abs() < f.abs() {
                    y = trial;
                    accepted = true;
                    break;
                }
                step *= 0.5;
            }
            if !accepted {
                break;
            }
        }
        Err("Face envelope root did not resolve on its separated branch; adjust radial setting / width / helix.".into())
    }
    fn coordinates(&self, x: f64, h: f64, side: f64, y: f64) -> Result<Contact> {
        self.scalar(y, x, h, side, 0.)?;
        let r = y.hypot(h);
        let t = ((r / self.rb).powi(2) - 1.).sqrt();
        let half = PI / (2. * n(&self.v, "pinion", 24.)?)
            + n(&self.v, "backlash", 0.15)? / (4. * self.rp)
            + self.alpha.tan()
            - self.alpha
            - (t - t.atan());
        let phase = (-h).atan2(y) + PI / 2. - side * half - self.twist(x);
        let theta = (y + self.e).atan2(x) - self.g * phase;
        Ok([x.hypot(y + self.e), theta, self.height - h, r, phase, y])
    }
    fn contact(&self, x: f64, h: f64, side: f64, k: f64) -> Result<Contact> {
        self.coordinates(x, h, side, self.solve(x, h, side, k)?[0])
    }
    fn point(&self, x: f64, h: f64, side: f64, k: f64) -> Result<P3> {
        let [r, a, z, _, _, _] = self.contact(x, h, side, k)?;
        Ok([r * a.cos(), r * a.sin(), z])
    }
    fn enclosure(&self, x: I, h: I, y: I, side: f64, k: f64) -> Cell {
        let s = y.square() + h.square();
        let q = (s - self.rb * self.rb).sqrt();
        let u = if self.e != 0. { y + self.e } else { y };
        let f = k * s * u + side * x * q * y / self.rb + x * h - s / self.g;
        let fy =
            k * (if self.e != 0. {
                3. * y.square() + h.square() + 2. * self.e * y
            } else {
                3. * y.square() + h.square()
            }) + side * x * (q + y.square() / q) / self.rb
                - 2. * y / self.g;
        let fx = side * q * y / self.rb + h;
        let fh = 2. * k * h * u + side * x * h * y / (self.rb * q) + x - 2. * h / self.g;
        let yx = -fx / fy;
        let yh = -fh / fy;
        let phix = (h + side * q * y / self.rb) * yx / s - k;
        let phih = (h * yh - y + side * q * (y * yh + h) / self.rb) / s;
        let ax = (x * yx - u) / (x.square() + u.square()) - self.g * phix;
        let ah = x * yh / (x.square() + u.square()) - self.g * phih;
        let ah_at_radius = ah - ax * u * yh / (x + u * yx);
        [
            f,
            fy,
            x + u * yx,
            y * yh + h,
            ah,
            ax,
            ah_at_radius,
            (x.square() + u.square()).sqrt(),
        ]
    }
    fn cell(&self, a: f64, b: f64, c: f64, d: f64, side: f64, k: f64) -> Result<Cell> {
        if a > b || c > d || side.abs() != 1. || ![a, b, c, d, k].iter().all(|v| v.is_finite()) {
            return Err("Invalid face enclosure rectangle".into());
        }
        let x = (a + b) / 2.;
        let h = (c + d) / 2.;
        let [yc, dc] = self.solve(x, h, side, k)?;
        let mut ys = Vec::new();
        for xx in [a, b] {
            for hh in [c, d] {
                ys.push(self.solve(xx, hh, side, k)?[0])
            }
        }
        let ymin = ys.iter().copied().fold(f64::INFINITY, f64::min);
        let ymax = ys.iter().copied().fold(f64::NEG_INFINITY, f64::max);
        let pad = (ymax - ymin) * 0.35 + 0.01 * self.m;
        let y = I::new(ymin.min(yc) - pad, ymax.max(yc) + pad);
        let xx = I::new(a, b);
        let hh = I::new(c, d);
        let row = self.enclosure(xx, hh, y, side, k);
        let s0 = yc * yc + hh.square();
        let q0 = (s0 - self.rb * self.rb).sqrt();
        let fx0 = side * q0 * yc / self.rb + hh;
        let fh0 = 2. * k * hh * (yc + self.e) + side * xx * hh * yc / (self.rb * q0) + xx
            - 2. * hh / self.g;
        let center = self.enclosure(x.into(), h.into(), yc.into(), side, k)[0];
        let f0 = center + fx0 * (xx - x) + fh0 * (hh - h);
        let mapped = yc - f0 / dc + (1. - row[1] / dc) * (y - yc);
        if !mapped.valid() || !(y.lo < mapped.lo && mapped.hi < y.hi) {
            return Err("Unresolved parameterized Krawczyk cell".into());
        }
        let row = self.enclosure(xx, hh, mapped, side, k);
        if row.iter().any(|r| !r.valid())
            || (row[1] * side).lo <= 1e-8
            || row[2].lo <= 1e-8
            || row[3].lo <= 1e-8
            || (row[4] * side).hi >= -1e-9
            || (row[6] * side).hi >= -1e-9
        {
            return Err("Unresolved face surface regularity / ordering".into());
        }
        if (mapped.square() + hh.square()).sqrt().lo < self.start + 1e-7 {
            return Err("Face working surface reaches the pinion root transition".into());
        }
        Ok(row)
    }
    fn certify(&self, band: Band) -> Result<Value> {
        let [lo, hi, k] = band;
        let (mut count, mut radius, mut minimum, mut radial_min, mut angle_max) =
            (0, 0_f64, 1e99_f64, 1e99_f64, 0_f64);
        for side in [-1., 1.] {
            let mut stack = vec![(lo, hi, self.low, self.high, 0)];
            while let Some((a, b, c, d, depth)) = stack.pop() {
                crate::protocol::control_check()?;
                count += 1;
                if count > 8192 {
                    return Err(
                        "Face regularity budget exhausted; reduce band width / addendum / helix."
                            .into(),
                    );
                }
                if let Ok(row) = self.cell(a, b, c, d, side, k) {
                    radius = radius.max(row[7].hi);
                    minimum = minimum.min((row[1] * side).lo);
                    radial_min = radial_min.min((row[2] / row[7]).lo);
                    angle_max = angle_max.max(row[5].abs_upper());
                    continue;
                }
                if depth >= 16 {
                    return Err("Face envelope has undercut or unresolved regularity; adjust radial setting, width or face addendum.".into());
                }
                if (b - a) / (hi - lo) >= (d - c) / (self.high - self.low) {
                    let mid = (a + b) / 2.;
                    stack.extend([(a, mid, c, d, depth + 1), (mid, b, c, d, depth + 1)])
                } else {
                    let mid = (c + d) / 2.;
                    stack.extend([(a, b, c, mid, depth + 1), (a, b, mid, d, depth + 1)])
                }
            }
        }
        Ok(
            json!({"cells":count,"radius_upper_mm":radius,"separated_root_derivative_lower":minimum,"radial_derivative_lower":radial_min,"angular_axial_derivative_abs_upper":angle_max,
            "method":"Parameterized Krawczyk root enclosure and implicit first derivatives","scope":"Outward-expanded float/libm numerical enclosures; analytic flanks, not continuous sampled-solid clearance"}),
        )
    }
    fn check_widths(&self) -> Result<()> {
        let pitch = TAU / n(&self.v, "wheel", 72.)?;
        let mut count = 0;
        for (&[lo, hi, k], cert) in self.bands.iter().zip(&self.certificates) {
            let mut stack = vec![(lo, hi, 0)];
            while let Some((a, b, depth)) = stack.pop() {
                crate::protocol::control_check()?;
                count += 1;
                let mut valid = true;
                for h in [self.low, self.high] {
                    let mid = (a + b) / 2.;
                    let gap = self.contact(mid, h, 1., k)?[1] - self.contact(mid, h, -1., k)?[1];
                    let check = || -> Result<bool> {
                        let rows = [
                            self.cell(a, b, h, h, -1., k)?,
                            self.cell(a, b, h, h, 1., k)?,
                        ];
                        let mut bound =
                            (rows[0][5].abs_upper() + rows[1][5].abs_upper()) * (b - a) / 2.;
                        let delta = rows[1][7] - rows[0][7];
                        bound += delta.abs_upper()
                            * n(cert, "angular_axial_derivative_abs_upper", 0.)?
                            / n(cert, "radial_derivative_lower", 0.)?;
                        Ok(gap - bound > 1e-7 && gap + bound < pitch - 1e-7)
                    };
                    valid &= check().unwrap_or(false);
                }
                if valid {
                    continue;
                }
                if depth >= 12 || count > 4096 {
                    return Err("Face teeth are pointed / overlapping or unresolved; reduce band width or radial setting.".into());
                }
                let mid = (a + b) / 2.;
                stack.extend([(a, mid, depth + 1), (mid, b, depth + 1)]);
            }
        }
        Ok(())
    }
    fn engagement(&self) -> Result<Value> {
        let mut rows = Vec::new();
        let mut best = [0_f64; 2];
        let tip = self.rp + self.m;
        for &[lo, hi, k] in &self.bands {
            let mut spans = [0_f64; 2];
            for f in [0.001, 0.25, 0.5, 0.75, 0.999] {
                let x = lo + (hi - lo) * f;
                for (i, side) in [-1., 1.].into_iter().enumerate() {
                    if self.contact(x, self.low, side, k)?[3] >= tip {
                        continue;
                    }
                    let (mut a, mut b, mut end) = (self.low, self.high, self.high);
                    if self.contact(x, b, side, k)?[3] > tip {
                        for _ in 0..48 {
                            let mid = (a + b) / 2.;
                            if self.contact(x, mid, side, k)?[3] < tip {
                                a = mid
                            } else {
                                b = mid
                            }
                        }
                        end = (a + b) / 2.;
                    }
                    let span = (self.contact(x, end, side, k)?[4]
                        - self.contact(x, self.low, side, k)?[4])
                        .abs()
                        / (TAU / n(&self.v, "pinion", 24.)?);
                    spans[i] = spans[i].max(span);
                    best[i] = best[i].max(span);
                }
            }
            rows.push(spans);
        }
        if best[0].min(best[1]) <= 1. + 1e-7 {
            return Err("Face pair has no complete connected ideal contact track; reduce radial setting / helix or adjust face addendum.".into());
        }
        Ok(
            json!({"phase_span_lower_bound_teeth":best[0].min(best[1]),"band_flank_spans_lower_bound_teeth":rows,
            "method":"Endpoint phase span of connected in-cap, radius-monotone tracks on the actual usable pinion involute",
            "scope":"At least one complete track per flank; equal sharing / axial cancellation between double bands is not established"}),
        )
    }
}

impl Generator {
    fn profile(&self, x: f64, hs: &[f64], k: f64, segments: usize) -> Result<Vec<P3>> {
        if hs.len() < 2 || hs.len() > 129 || !(1..=64).contains(&segments) {
            return Err("Face profile grid exceeds its budget".into());
        }
        let pitch = TAU / n(&self.v, "wheel", 72.)?;
        let mut out = Vec::new();
        for &h in hs.iter().rev() {
            let q = self.contact(x, h, 1., k)?;
            out.push([q[0], q[1], q[2]])
        }
        let a = self.contact(x, self.low, 1., k)?;
        let b = self.contact(x, self.low, -1., k)?;
        for j in 1..segments {
            let f = j as f64 / segments as f64;
            out.push([
                a[0] + f * (b[0] - a[0]),
                a[1] + f * (b[1] + pitch - a[1]),
                a[2],
            ])
        }
        for &h in hs {
            let [r, t, z, _, _, _] = self.contact(x, h, -1., k)?;
            out.push([r, t + pitch, z])
        }
        let a = self.contact(x, self.high, -1., k)?;
        let b = self.contact(x, self.high, 1., k)?;
        for j in 1..segments {
            let f = j as f64 / segments as f64;
            out.push([
                a[0] + f * (b[0] - a[0]),
                a[1] + pitch + f * (b[1] - a[1]),
                a[2],
            ])
        }
        if out.windows(2).any(|p| p[1][1] <= p[0][1]) {
            return Err(
                "Face sampled profile is not ordered; adjust radial setting / helix / width."
                    .into(),
            );
        }
        Ok(out
            .into_iter()
            .map(|[r, t, z]| [r * t.cos(), r * t.sin(), z])
            .collect())
    }
    fn grids(&self) -> Result<Grids> {
        let mut hs = vec![self.low, self.high];
        let mut grids: Vec<Vec<f64>> = self.bands.iter().map(|p| vec![p[0], p[1]]).collect();
        let pitch = TAU / n(&self.v, "wheel", 72.)?;
        let delta = self
            .certificates
            .iter()
            .zip(&self.bands)
            .map(|(q, b)| q["radius_upper_mm"].as_f64().unwrap() - b[0])
            .fold(f64::NEG_INFINITY, f64::max);
        let segments = ((self.outer * pitch * pitch + 2. * delta * pitch) / (8. * REFINEMENT))
            .sqrt()
            .ceil()
            .max(4.) as usize;
        if segments > 64 {
            return Err("Face crest/root arc sampling budget exhausted.".into());
        }
        for _ in 0..12 {
            crate::protocol::control_check()?;
            let mut split = Vec::new();
            for p in hs.windows(2) {
                let (a, b) = (p[0], p[1]);
                let mut error = 0_f64;
                for (xs, band) in grids.iter().zip(&self.bands) {
                    for x in crate::hypoid::with_mids(xs) {
                        for side in [-1., 1.] {
                            let p = self.point(x, a, side, band[2])?;
                            let q = self.point(x, b, side, band[2])?;
                            for f in [0.25, 0.5, 0.75] {
                                let actual = self.point(x, a + (b - a) * f, side, band[2])?;
                                error = error.max(deviation(actual, p, q, f));
                            }
                        }
                    }
                }
                if error > REFINEMENT {
                    split.push((a + b) / 2.)
                }
            }
            let mut changed = !split.is_empty();
            hs.extend(split);
            hs.sort_by(f64::total_cmp);
            if hs.len() > 129 {
                return Err("Face profile refinement budget exhausted.".into());
            }
            for (xs, band) in grids.iter_mut().zip(&self.bands) {
                let mut additions = Vec::new();
                let k = band[2];
                let rows = xs
                    .iter()
                    .map(|x| self.profile(*x, &hs, k, segments))
                    .collect::<Result<Vec<_>>>()?;
                for (i, p) in xs.windows(2).enumerate() {
                    let (a, b) = (p[0], p[1]);
                    let mut error = 0_f64;
                    for f in [0.25, 0.5, 0.75] {
                        let actual = self.profile(a + (b - a) * f, &hs, k, segments)?;
                        for ((v, p), q) in actual.iter().zip(&rows[i]).zip(&rows[i + 1]) {
                            error = error.max(deviation(*v, *p, *q, f));
                        }
                    }
                    if error > REFINEMENT {
                        additions.push((a + b) / 2.)
                    }
                }
                changed |= !additions.is_empty();
                xs.extend(additions);
                xs.sort_by(f64::total_cmp);
                if xs.len() > 65 {
                    return Err("Face band refinement budget exhausted.".into());
                }
            }
            let count = n(&self.v, "wheel", 72.)? as usize * (2 * hs.len() + 2 * (segments - 1));
            if count > 12000
                || count
                    * (2 * grids.iter().map(|q| q.len() - 1).sum::<usize>() + 4 * grids.len() + 10)
                    > 250000
            {
                return Err(
                    "Face shared surface budget exhausted; reduce teeth / width / curvature."
                        .into(),
                );
            }
            if !changed {
                return Ok((hs, grids, segments));
            }
        }
        Err("Face surface refinement did not converge within its budget.".into())
    }
    fn mesh(
        &self,
        hs: &[f64],
        grids: &[Vec<f64>],
        segments: usize,
        use_joined: bool,
    ) -> Result<(Vec<P3>, f64)> {
        if hs.len() < 2
            || hs.len() > 129
            || grids.is_empty()
            || grids.len() > 2
            || grids.iter().any(|g| g.len() < 2 || g.len() > 129)
            || !(1..=64).contains(&segments)
        {
            return Err("Invalid face mesh grid or budget".into());
        }
        let bottom = self.root_z - n(&self.v, "base", 6.)?;
        let root = self.root_z - bottom;
        let teeth = n(&self.v, "wheel", 72.)? as usize;
        let pitch = TAU / teeth as f64;
        let perimeter = teeth * (2 * hs.len() + 2 * (segments - 1));
        let estimated = perimeter
            * (2 * grids.iter().map(|g| g.len() - 1).sum::<usize>() + 4 * grids.len() + 10);
        if perimeter > 12000 || estimated > 250000 {
            return Err(
                "Face shared surface budget exhausted; reduce teeth / width / curvature.".into(),
            );
        }
        let mut bands = Vec::new();
        for (xs, band) in grids.iter().zip(&self.bands) {
            let mut rows = Vec::new();
            for &x in xs {
                crate::protocol::control_check()?;
                let one = if use_joined {
                    self.joined_surface
                        .as_ref()
                        .ok_or("No joined face surface")?
                        .profile(self, x, hs, segments)?
                } else {
                    self.profile(x, hs, band[2], segments)?
                };
                if one.len() * teeth > 12000 {
                    return Err("Face perimeter exceeds shared vertex budget".into());
                }
                let mut contour = Vec::with_capacity(one.len() * teeth);
                for t in 0..teeth {
                    let (c, s) = ((t as f64 * pitch).cos(), (t as f64 * pitch).sin());
                    contour.extend(
                        one.iter()
                            .map(|p| [p[0] * c - p[1] * s, p[0] * s + p[1] * c, p[2] - bottom]),
                    );
                }
                rows.push(contour);
            }
            bands.push(rows);
        }
        let mut mesh = Vec::new();
        for rows in &bands {
            for p in rows.windows(2) {
                strip(&mut mesh, &p[0], &p[1])?
            }
            strip(&mut mesh, &atz(&rows[0], root), &rows[0])?;
            let last = rows.last().unwrap();
            strip(&mut mesh, last, &atz(last, root))?;
        }
        for p in bands.windows(2) {
            strip(
                &mut mesh,
                &atz(p[0].last().unwrap(), root),
                &atz(&p[1][0], root),
            )?
        }
        let inner = atz(&bands[0][0], root);
        let outer = atz(bands.last().unwrap().last().unwrap(), root);
        let circle_at = |points: &[P3], r: f64, z: f64| {
            points
                .iter()
                .map(|p| {
                    let d = p[0].hypot(p[1]);
                    [r * p[0] / d, r * p[1] / d, z]
                })
                .collect::<Vec<_>>()
        };
        let bore = circle_at(&inner, n(&self.v, "output_bore", 0.)? / 2., root);
        let rim = circle_at(&outer, self.outer, root);
        let bottomrim = atz(&rim, 0.);
        let bottombore = atz(&bore, 0.);
        strip(&mut mesh, &bore, &inner)?;
        strip(&mut mesh, &outer, &rim)?;
        strip(&mut mesh, &bottomrim, &bottombore)?;
        strip(&mut mesh, &rim, &bottomrim)?;
        strip(&mut mesh, &bottombore, &bore)?;
        Ok((mesh, bottom))
    }
    fn info(&self) -> Value {
        json!({"e":self.e,"m":self.m,"g":self.g,"joined":self.joined,"beta":self.beta,"rp":self.rp,"ref":self.reference,"alpha":self.alpha,"rb":self.rb,"k":self.k,"height":self.height,"low":self.low,"high":self.high,"root_z":self.root_z,"x0":self.x0,"x1":self.x1,"pinion":self.pinion,"start":self.start,"bands":self.bands,"certificates":self.certificates,"outer":self.outer,"engagement":self.engagement,"joined_surface":self.joined_surface.as_ref().map(Joined::state)})
    }
}
fn deviation(v: P3, p: P3, q: P3, f: f64) -> f64 {
    (0..3)
        .map(|i| (v[i] - p[i] - (q[i] - p[i]) * f).powi(2))
        .sum::<f64>()
        .sqrt()
}
fn distance(a: P3, b: P3) -> f64 {
    (0..3).map(|i| (a[i] - b[i]).powi(2)).sum::<f64>().sqrt()
}
fn atz(points: &[P3], z: f64) -> Vec<P3> {
    points.iter().map(|p| [p[0], p[1], z]).collect()
}
fn strip(mesh: &mut Vec<P3>, a: &[P3], b: &[P3]) -> Result<()> {
    if a.len() != b.len() || a.len() < 3 {
        return Err("Noncorresponding face strip".into());
    }
    for j in 0..a.len() {
        if j % 256 == 0 {
            crate::protocol::control_check()?
        }
        let k = (j + 1) % a.len();
        let mut clean = Vec::new();
        for p in [a[j], b[j], b[k], a[k]] {
            if clean.last() != Some(&p) {
                clean.push(p)
            }
        }
        if clean.len() > 1 && clean.first() == clean.last() {
            clean.pop();
        }
        for pair in clean[1..].windows(2) {
            let p = clean[0];
            let u = std::array::from_fn::<_, 3, _>(|i| pair[0][i] - p[i]);
            let v = std::array::from_fn::<_, 3, _>(|i| pair[1][i] - p[i]);
            let n = crate::solid::cross(u, v);
            if n.iter().map(|x| x * x).sum::<f64>() > 1e-24 {
                if mesh.len() / 3 >= 250000 {
                    return Err("Face wheel exceeds the 250,000 shared triangle budget.".into());
                }
                mesh.extend([p, pair[0], pair[1]]);
            }
        }
    }
    Ok(())
}

fn pinion_stations(p: &Value) -> Result<Vec<Station>> {
    let source = crate::solid::Part::read(p)?;
    // Legacy rack._stations starts from profile_sections(), i.e. the shared
    // full-side sampler, including its axial shoulder/triangle refinements.
    // Using nominal landmarks here would omit those groove transition sections.
    let rows = source.sections()?;
    let mut result = Vec::new();
    let perimeter = source.outer.len() + source.holes.iter().map(Vec::len).sum::<usize>();
    for ((a, aa, oa), (b, ab, ob)) in rows.iter().zip(&rows[1..]) {
        let radius = oa.iter().chain(ob).map(|p| radius(*p)).fold(0., f64::max);
        let delta = oa
            .iter()
            .zip(ob)
            .map(|(u, v)| (v[0] - u[0]).hypot(v[1] - u[1]))
            .fold(0., f64::max);
        let angle = (ab - aa).to_radians();
        let count = ((radius * angle * angle + 2. * delta * angle.abs()) / (8. * REFINEMENT))
            .sqrt()
            .ceil()
            .max(1.) as usize;
        if count > 125000 || 2 * perimeter * (result.len() + count) + 2 > 250000 {
            return Err(
                "Rack pinion surface budget exhausted; reduce teeth / face width / helix.".into(),
            );
        }
        for j in 0..count {
            crate::protocol::control_check()?;
            let f = j as f64 / count as f64;
            let z = a + (b - a) * f;
            let turn = aa + (ab - aa) * f;
            let outer = oa
                .iter()
                .zip(ob)
                .map(|(u, v)| {
                    rotate(
                        [u[0] + (v[0] - u[0]) * f, u[1] + (v[1] - u[1]) * f],
                        turn.to_radians(),
                    )
                })
                .collect();
            result.push(Station::new(z, outer, source.holes.clone()));
        }
    }
    let (z, a, outer) = rows.last().ok_or("Missing face pinion sections")?;
    result.push(Station::new(
        *z,
        outer.iter().map(|p| rotate(*p, a.to_radians())).collect(),
        source.holes.clone(),
    ));
    Ok(result)
}
thread_local! {static CACHE:RefCell<VecDeque<(String,Rc<Generator>)>>=const{RefCell::new(VecDeque::new())};}
fn prepared(v: &Value) -> Result<Rc<Generator>> {
    crate::protocol::control_check()?;
    let key = v.to_string();
    if key.len() > 32768 {
        return Ok(Rc::new(Generator::new(v)?));
    }
    if let Some(g) = CACHE.with(|c| {
        let mut c = c.borrow_mut();
        let i = c.iter().position(|(k, _)| *k == key)?;
        let row = c.remove(i)?;
        let g = Rc::clone(&row.1);
        c.push_back(row);
        Some(g)
    }) {
        return Ok(g);
    }
    let g = Rc::new(Generator::new(v)?);
    crate::protocol::control_check()?;
    CACHE.with(|c| {
        let mut c = c.borrow_mut();
        while c.len() >= 2 {
            c.pop_front();
        }
        c.push_back((key, Rc::clone(&g)));
    });
    Ok(g)
}

pub(crate) fn build(v: &Value) -> Result<Construction> {
    let g = prepared(v)?;
    // Evaluation budgets belong to this construction, not to previous callers
    // of the read-only diagnostic API or an interrupted earlier build.
    g.clear_evaluations();
    let (hs, xs, segments) = if let Some(s) = &g.joined_surface {
        s.grids(&g)?
    } else {
        g.grids()?
    };
    let (mesh, bottom) = g.mesh(&hs, &xs, segments, g.joined_surface.is_some())?;
    let triangles = mesh.len() / 3;
    let source = crate::solid::Part::read(&g.pinion)?;
    let mut pinion = Part::new("Face_pinion", source.outer, source.holes, source.width);
    let mut extra = g.pinion.as_object().unwrap().clone();
    for key in ["outer", "holes", "outer_circle_radius"] {
        extra.remove(key);
    }
    pinion.extra = Value::Object(extra);
    pinion.stations = pinion_stations(&g.pinion)?;
    pinion.extra["color"] = json!([0.96, 0.66, 0.33]);
    let mut wheel = Part::new(
        "Face_wheel",
        bp::circle(g.outer)?,
        bp::bores(n(v, "output_bore", 0.)? / 2.)?,
        g.height - g.low - bottom,
    );
    wheel.extra["z"] = json!(bottom);
    wheel.extra["color"] = json!([0.23, 0.75, 0.65]);
    wheel.mesh_triangle_points = mesh;
    wheel.extra["outer_circle_radius"] = json!(g.outer);
    if n(v, "output_bore", 0.)? > 0. {
        wheel.extra["bore_circle_radius"] = json!(n(v, "output_bore", 0.)? / 2.);
    }
    for (p, member, axis) in [
        (
            &mut pinion,
            "A",
            if g.e != 0. {
                "World +X through (0, offset, 2rp)"
            } else {
                "World +X through (0, 0, 2rp)"
            },
        ),
        (&mut wheel, "B", "World +Z through origin"),
    ] {
        p.extra["port"] = json!({"member":member,"axis":axis});
        if p.extra["profile_metadata"].is_null() {
            p.extra["profile_metadata"] = json!({})
        }
        p.extra["profile_metadata"]["face_profile"] = json!({"method":"Generated equal-count involute pinion envelope","reference":"NASA/CR2000-209909 eq21–24; NASA/CR2005-213443 eq15–18","refinement_threshold_mm":REFINEMENT,"refinement_scope":"Finite quarter/midpoint working-surface probes; not global manufacturing accuracy"});
    }
    let mut info = json!({"shaft_angle_deg":90,"shaft_offset_mm":g.e,"shortest_axis_distance_mm":g.e.abs(),"axis_intersection_mm":if g.e==0.{Some([0.,0.,g.height])}else{None},"pinion_axis_origin_mm":[0.,g.e,g.height],
        "pinion_reference_radius_mm":g.rp,"wheel_reference_radius_mm":g.reference,"blank_outer_radius_mm":g.outer,"band_axial_intervals_mm":g.bands.iter().map(|p|[p[0],p[1]]).collect::<Vec<_>>(),"height_parameter_interval_mm":[g.low,g.high],"face_addendum_coefficient":n(v,"face_addendum",0.65)?,"base_thickness_mm":n(v,"base",6.)?,"regularity":g.certificates,"engagement":g.engagement,"height_grid_mm":hs,"axial_grids_mm":xs,"tooth_width_check":"Conservative angular separation including an equal-radius correction for asymmetric flanks","face_mesh_triangles":triangles,"construction":"Orthogonal equal-count pinion envelope; custom stub crest/root relief","double_style":v.get("double_style"),"tooth_band_count":if g.joined{1}else{g.bands.len()},"rolling_equation":"wheel_rpm / pinion_rpm = pinion_teeth / wheel_teeth about the stated right-hand axes"});
    if g.joined {
        info["joined_transition"] = if let Some(s) = &g.joined_surface {
            s.info()
        } else {
            json!({"method":"Zero-helix continuous spur limit"})
        };
        if let Some(s) = &g.joined_surface {
            info["axial_grids_mm"] = Value::Null;
            info["joined_transition"]["parameter_grid"] = json!(xs[0]);
            let radii = hs
                .iter()
                .map(|h| {
                    xs[0]
                        .iter()
                        .map(|t| s.radius(&g, *t, *h))
                        .collect::<Result<Vec<_>>>()
                })
                .collect::<Result<Vec<_>>>()?;
            info["joined_transition"]["radial_grids_by_height_mm"] = json!(radii);
        }
    }
    Ok(Construction {
        parts: vec![pinion, wheel],
        extra: json!({"analysis":{"signed_ratio":1./g.g,"face_gear":info}}),
    })
}

pub fn call(a: &Value) -> Result<Value> {
    let g = prepared(&a["values"])?;
    let action = a["action"].as_str().unwrap_or("prepare");
    let side = n(a, "side", 1.)?;
    let x = n(a, "x", g.x0)?;
    let h = n(a, "h", g.low)?;
    let k = n(a, "k", g.k)?;
    if action.starts_with("joined_") {
        return g
            .joined_surface
            .as_ref()
            .ok_or("No joined face surface")?
            .call(&g, a, action);
    }
    match action {
        "prepare" => {
            g.clear_evaluations();
            Ok(g.info())
        }
        "twist" => Ok(json!(g.twist(x))),
        "enclosure" => {
            let read = |v: &Value| -> Result<I> {
                let p = I::new(n(v, "lo", 0.)?, n(v, "hi", 0.)?);
                if !p.valid() {
                    return Err("Invalid face interval".into());
                }
                Ok(p)
            };
            let row = g.enclosure(read(&a["X"])?, read(&a["H"])?, read(&a["Y"])?, side, k);
            if row.iter().any(|i| !i.valid()) {
                return Err("Unresolved face enclosure".into());
            }
            Ok(json!(row))
        }
        "certify" => {
            let b: Band = serde_json::from_value(a["band"].clone()).map_err(|e| e.to_string())?;
            if !b.iter().all(|x| x.is_finite()) || b[0] <= 0. || b[0] >= b[1] {
                return Err("Invalid face band".into());
            }
            g.certify(b)
        }
        "check_widths" => {
            g.check_widths()?;
            Ok(Value::Null)
        }
        "engagement" => g.engagement(),
        "scalar" => Ok(json!(g.scalar(n(a, "y", 0.)?, x, h, side, k)?)),
        "solve" => Ok(json!(g.solve(x, h, side, k)?)),
        "coordinates" => Ok(json!(g.coordinates(x, h, side, n(a, "y", 0.)?)?)),
        "contact" => Ok(json!(g.contact(x, h, side, k)?)),
        "point" => Ok(json!(g.point(x, h, side, k)?)),
        "cell" => Ok(json!(g.cell(
            n(a, "a", x)?,
            n(a, "b", x)?,
            n(a, "c", h)?,
            n(a, "d", h)?,
            side,
            k
        )?)),
        "profile" => {
            let hs: Vec<f64> =
                serde_json::from_value(a["hs"].clone()).map_err(|e| e.to_string())?;
            Ok(json!(g.profile(
                x,
                &hs,
                k,
                n(a, "segments", 4.)? as usize
            )?))
        }
        "grids" => {
            let (h, x, s) = g.grids()?;
            Ok(json!([h, x, s]))
        }
        "mesh" => {
            let hs: Vec<f64> =
                serde_json::from_value(a["hs"].clone()).map_err(|e| e.to_string())?;
            let grids: Vec<Vec<f64>> =
                serde_json::from_value(a["grids"].clone()).map_err(|e| e.to_string())?;
            let (p, b) = g.mesh(
                &hs,
                &grids,
                n(a, "segments", 4.)? as usize,
                a["joined"].as_bool().unwrap_or(false),
            )?;
            Ok(json!([
                p.chunks_exact(3).map(|t| vec![t]).collect::<Vec<_>>(),
                b
            ]))
        }
        _ => Err("Unknown face generator operation".into()),
    }
}
