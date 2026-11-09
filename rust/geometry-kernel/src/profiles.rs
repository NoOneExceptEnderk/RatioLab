// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Generated cylindrical profiles and roller offsets, in millimetres.
//! Sampled coordinates are binary64. The analytic decimal API is separate.
//! ISO21771:2007 thickness/sign conventions; rounded normal-rack envelope and
//! tangent internal blend preserve the explicitly documented construction.
use crate::precision::Result;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::f64::consts::{PI, TAU};
pub type Point = [f64; 2];
pub(crate) type CurveIntervals = Vec<(f64, f64)>;
const TOL: f64 = 0.015;
pub fn n(a: &Value, key: &str, default: f64) -> Result<f64> {
    let v = match a.get(key) {
        None | Some(Value::Null) => default,
        Some(v) if v.is_string() || v.is_object() => crate::precision::sampled_number(v)?,
        Some(v) => v
            .as_f64()
            .ok_or_else(|| format!("{key}: numeric sampled-geometry parameter required"))?,
    };
    if !v.is_finite() {
        Err(format!("{key}: finite number required"))
    } else {
        Ok(v)
    }
}
pub fn polar(r: f64, a: f64) -> Point {
    [r * a.cos(), r * a.sin()]
}
pub fn rotate(p: Point, a: f64) -> Point {
    let (c, s) = (a.cos(), a.sin());
    [p[0] * c - p[1] * s, p[0] * s + p[1] * c]
}
pub fn radius(p: Point) -> f64 {
    p[0].hypot(p[1])
}
fn angle(p: Point) -> f64 {
    p[1].atan2(p[0])
}
fn distance(p: Point, q: Point) -> f64 {
    (p[0] - q[0]).hypot(p[1] - q[1])
}
pub(crate) fn segment_distance(p: Point, a: Point, b: Point) -> f64 {
    let (dx, dy) = (b[0] - a[0], b[1] - a[1]);
    let den = dx * dx + dy * dy;
    let t = if den > 0. {
        ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / den
    } else {
        0.
    }
    .clamp(0., 1.);
    (p[0] - a[0] - t * dx).hypot(p[1] - a[1] - t * dy)
}

pub fn sample<F: Fn(f64) -> Point>(
    f: &F,
    a: f64,
    b: f64,
    tolerance: f64,
    endpoints: bool,
) -> Result<Vec<Point>> {
    sample_record(f, a, b, tolerance, endpoints, |_, _| {})
}

pub(crate) fn sample_with_domains<F: Fn(f64) -> Point>(
    f: &F,
    a: f64,
    b: f64,
    tolerance: f64,
) -> Result<(Vec<Point>, CurveIntervals)> {
    let mut domains = Vec::new();
    let points = sample_record(f, a, b, tolerance, false, |a, b| domains.push((a, b)))?;
    Ok((points, domains))
}

fn sample_record<F: Fn(f64) -> Point, G: FnMut(f64, f64)>(
    f: &F,
    a: f64,
    b: f64,
    tolerance: f64,
    endpoints: bool,
    mut record: G,
) -> Result<Vec<Point>> {
    if !a.is_finite() || !b.is_finite() || !tolerance.is_finite() || tolerance <= 0. {
        return Err("Invalid curve sampling domain".into());
    }
    fn recurse<F: Fn(f64) -> Point, G: FnMut(f64, f64)>(
        f: &F,
        a: f64,
        b: f64,
        tol: f64,
        depth: u8,
        out: &mut Vec<Point>,
        record: &mut G,
    ) -> Result<()> {
        let p = f(a);
        let q = f(b);
        let probes = [f((3. * a + b) / 4.), f((a + b) / 2.), f((a + 3. * b) / 4.)];
        if p.iter()
            .chain(q.iter())
            .chain(probes.iter().flatten())
            .any(|x| !x.is_finite())
        {
            return Err("Nonfinite generated curve point".into());
        }
        let error = probes
            .iter()
            .map(|v| segment_distance(*v, p, q))
            .fold(0., f64::max);
        if error <= tol {
            out.push(p);
            record(a, b);
            return Ok(());
        }
        // Never silently accept an unresolved segment on budget exhaustion.
        if depth >= 12 || out.len() > 262144 {
            return Err("Curve exceeds its bounded refinement limit".into());
        }
        let mid = (a + b) / 2.;
        if mid == a || mid == b {
            return Err("Curve sampling reached numerical resolution before its threshold".into());
        }
        recurse(f, a, mid, tol, depth + 1, out, record)?;
        recurse(f, mid, b, tol, depth + 1, out, record)
    }
    if endpoints {
        let p = f(a);
        let q = f(b);
        if p.iter().chain(q.iter()).any(|v| !v.is_finite()) {
            return Err("Nonfinite curve endpoint".into());
        }
        return Ok(vec![p, q]);
    }
    let mut result = Vec::new();
    recurse(f, a, b, tolerance, 0, &mut result, &mut record)?;
    result.push(f(b));
    Ok(result)
}

pub fn clean(points: Vec<Point>) -> Vec<Point> {
    let mut out = Vec::new();
    for [x, y] in points {
        // Compatibility grid of the published shared topology. This is an
        // explicit mesh quantization, never an analytic decimal precision claim.
        let p = [
            format!("{x:.9}").parse().unwrap(),
            format!("{y:.9}").parse().unwrap(),
        ];
        if out.last().is_none_or(|q| distance(p, *q) > 1e-7) {
            out.push(p);
        }
    }
    if out.len() > 1 && distance(out[0], *out.last().unwrap()) < 1e-7 {
        out.pop();
    }
    out
}

#[derive(Clone, Serialize, Deserialize)]
pub struct Rack {
    pub pitch_radius: f64,
    pub normal_module: f64,
    pub transverse_module: f64,
    pub alpha_normal: f64,
    pub alpha_transverse: f64,
    pub cos_beta: f64,
    pub tip_radius: f64,
    pub tip_center_u: f64,
    pub tip_center_v: f64,
    pub shift: f64,
    pub backlash_transverse: f64,
    pub dedendum: f64,
}
impl Rack {
    fn with_tip_radius(mut self, rho: f64) -> Result<Self> {
        let mn = self.normal_module;
        let an = self.alpha_normal;
        let land = PI * mn / 4. + self.backlash_transverse * self.cos_beta / 4.
            - self.dedendum * mn * an.tan();
        let maximum = (land - mn * 0.025) * an.cos() / (1. - an.sin());
        if !rho.is_finite() || rho <= 0. || rho > maximum {
            return Err("Normal generating-rack tip radius must be positive and preserve the tool tip land.".into());
        }
        self.tip_radius = rho;
        self.tip_center_u = land - rho * (1. - an.sin()) / an.cos();
        self.tip_center_v = -self.dedendum * mn + rho + self.shift * mn;
        Ok(self)
    }
    #[allow(
        clippy::too_many_arguments,
        reason = "Explicit normal-rack dimensions at the compatibility boundary"
    )]
    pub fn new(
        z: f64,
        mt: f64,
        pressure: f64,
        backlash: f64,
        mn: f64,
        shift: f64,
        normal: f64,
        hf: f64,
    ) -> Result<Self> {
        let at = pressure.to_radians();
        let an = normal.to_radians();
        let cb = mn / mt;
        if ![z, mt, pressure, backlash, mn, shift, normal, hf]
            .iter()
            .all(|v| v.is_finite())
            || z < 3.
            || mt <= 0.
            || mn <= 0.
            || !(0. < cb && cb <= 1.00000001 && 0. < an && an < PI / 2. && 0. < at && at < PI / 2.)
        {
            return Err("Rack envelope outside its cylindrical gear domain.".into());
        }
        let land = PI * mn / 4. + backlash * cb / 4. - hf * mn * an.tan();
        if land <= mn * 0.025 {
            return Err(
                "Impossible rack: dedendum and pressure angle eliminate the tool tip land.".into(),
            );
        }
        let rho = (0.3 * mn).min((land - mn * 0.025) * an.cos() / (1. - an.sin()));
        Ok(Self {
            pitch_radius: mt * z / 2.,
            normal_module: mn,
            transverse_module: mt,
            alpha_normal: an,
            alpha_transverse: at,
            cos_beta: cb,
            tip_radius: rho,
            tip_center_u: land - rho * (1. - an.sin()) / an.cos(),
            tip_center_v: -hf * mn + rho + shift * mn,
            shift,
            backlash_transverse: backlash,
            dedendum: hf,
        })
    }
    pub fn point(&self, t: f64) -> Point {
        let u = (self.tip_center_u + self.tip_radius * t.cos()) / self.cos_beta;
        let v = self.tip_center_v + self.tip_radius * t.sin();
        let dx = -self.tip_radius * t.sin() / self.cos_beta;
        let dy = self.tip_radius * t.cos();
        let phi = (u + v * dy / dx) / self.pitch_radius;
        rotate([u - self.pitch_radius * phi, self.pitch_radius + v], -phi)
    }
}

#[derive(Clone)]
struct Parameters {
    z: f64,
    mt: f64,
    pressure: f64,
    j: f64,
    mn: f64,
    x: f64,
    normal: f64,
    ha: f64,
    hf: f64,
    tolerance: f64,
    endpoints: bool,
    join: Option<f64>,
    tip_radius: Option<f64>,
    paired_sampling: bool,
    tips: crate::tooth_tips::Treatment,
}
impl Parameters {
    fn read(a: &Value) -> Result<Self> {
        let mt = n(a, "mt", 2.)?;
        let pressure = n(a, "pressure", 20.)?;
        let mut p = Self {
            z: n(a, "z", 24.)?,
            mt,
            pressure,
            j: n(a, "backlash", 0.15)?,
            mn: n(a, "depth", mt)?,
            x: n(a, "shift", 0.)?,
            normal: n(a, "normal_pressure", pressure)?,
            ha: n(a, "ha", 1.)?,
            hf: n(a, "hf", 1.25)?,
            tolerance: n(a, "tolerance", TOL)?,
            endpoints: a.get("endpoints").and_then(Value::as_bool).unwrap_or(false),
            join: if a
                .get("minimum_join_radius_mm")
                .is_some_and(|v| !v.is_null())
            {
                Some(n(a, "minimum_join_radius_mm", 0.)?)
            } else {
                None
            },
            tip_radius: if a.get("rack_tip_radius_mm").is_some_and(|v| !v.is_null()) {
                Some(n(a, "rack_tip_radius_mm", 0.)?)
            } else {
                None
            },
            paired_sampling: a["safe_pair_sampling"] == true,
            tips: crate::tooth_tips::Treatment::read(a)?,
        };
        if p.z < 3.
            || p.z.fract() != 0.
            || p.z > 100000.
            || p.mt <= 0.
            || p.mn <= 0.
            || p.tolerance <= 0.
        {
            return Err("Invalid cylindrical profile parameters".into());
        }
        if p.paired_sampling {
            p.tolerance = p.tolerance.min(0.005 * p.mn);
        }
        Ok(p)
    }

    fn rack(&self) -> Result<Rack> {
        let tool = Rack::new(
            self.z,
            self.mt,
            self.pressure,
            self.j,
            self.mn,
            self.x,
            self.normal,
            self.hf,
        )?;
        match self.tip_radius {
            Some(rho) => tool.with_tip_radius(rho),
            None => Ok(tool),
        }
    }
}

/// Stable binary64 involute for sampled profiles; a series avoids subtracting
/// nearly equal numbers on the base-circle branch.
pub fn inv_roll(t: f64) -> f64 {
    if t.abs() < 0.125 {
        let mut term = t * t * t;
        let mut sum = term / 3.;
        let mut k = 5.;
        for _ in 0..32 {
            term *= -t * t;
            let next = term / k;
            if next.abs() < f64::EPSILON * sum.abs() {
                break;
            }
            sum += next;
            k += 2.;
        }
        sum
    } else {
        t - t.atan()
    }
}
fn inv_radius(r: f64, rb: f64) -> f64 {
    inv_roll(((r / rb).powi(2) - 1.).max(0.).sqrt())
}

pub fn thickness(a: &Value) -> Result<Value> {
    let z = n(a, "z", 24.)?;
    let mt = n(a, "mt", 2.)?;
    let mn = n(a, "mn", mt)?;
    let rp = n(a, "rp", mt * z / 2.)?;
    let rb = n(a, "rb", rp * 20f64.to_radians().cos())?;
    let tip = n(a, "tip", rp + mn)?;
    let half = n(a, "half", PI / (2. * z))?;
    let nominal = n(a, "nominal_half", half)?;
    let lower = n(a, "involute_start", rb)?;
    let upper = n(a, "involute_end", tip)?;
    let internal = a.get("internal").and_then(Value::as_bool).unwrap_or(false);
    let cb = mn / mt;
    let sign = if internal { -1. } else { 1. };
    let at_radius = |r: f64| -> Value {
        let corr = sign * (inv_radius(rp, rb) - inv_radius(r, rb));
        let nominal_angle = nominal + corr;
        let actual = half + corr;
        let usable = lower - 1e-9 <= r && r <= upper + 1e-9;
        let cb_y = 1. / (1. + (r / rp).powi(2) * (1. / cb.powi(2) - 1.).max(0.)).sqrt();
        json!({"radius_mm":r,"on_usable_involute":usable,"nominal_transverse_arc_mm":2.*r*nominal_angle,"nominal_normal_arc_mm":2.*r*nominal_angle*cb_y,
            "generated_transverse_arc_mm":usable.then_some(2.*r*actual),"generated_normal_arc_mm":usable.then_some(2.*r*actual*cb_y),
            "generated_transverse_chord_mm":usable.then_some(2.*r*actual.sin())})
    };
    let tip_result = at_radius(tip);
    Ok(
        json!({"internal":internal,"reference":at_radius(rp),"tip":tip_result,"pair_backlash_transverse_mm":4.*rp*(nominal-half),
        "per_gear_reference_reduction_transverse_mm":2.*rp*(nominal-half),
        "tip_chord_over_normal_module":tip_result["generated_transverse_chord_mm"].as_f64().map(|v|v/mn),
        "basis":"analytic involute widths before chord sampling; equal split of transverse pair backlash",
        "scope":"undeformed cylindrical involute; normal widths are helical arcs, chords are transverse; no strength or minimum safe tip thickness evaluated"}),
    )
}

#[allow(
    clippy::too_many_arguments,
    reason = "Constructed flank limits and thickness conventions travel together"
)]
fn metadata(
    p: &Parameters,
    mut m: Value,
    rp: f64,
    rb: f64,
    tip: f64,
    root: f64,
    half: f64,
    nominal: f64,
    lower: f64,
    upper: f64,
    internal: bool,
) -> Result<Value> {
    m["tooth_thickness"] = thickness(
        &json!({"z":p.z,"mt":p.mt,"mn":p.mn,"rp":rp,"rb":rb,"tip":tip,"half":half,"nominal_half":nominal,
        "involute_start":lower,"involute_end":upper,"internal":internal}),
    )?;
    m["measurement_geometry"] = json!({"teeth":p.z as u64,"reference_radius_mm":rp,"base_radius_mm":rb,"reference_half_angle_rad":half,
        "transverse_pressure_angle_rad":p.pressure.to_radians(),"helix_angle_abs_deg":(p.mn/p.mt).min(1.).acos().to_degrees(),"internal":internal,
        "involute_start_radius_mm":lower,"involute_end_radius_mm":upper,"root_radius_mm":root,"tip_radius_mm":tip,
        "scope":if internal{"undeformed cylindrical involute before chord sampling; constructed internal root blend"}else{"undeformed cylindrical involute before chord sampling"}});
    Ok(m)
}

fn external(p: &Parameters) -> Result<(Vec<Point>, Value)> {
    let tool = p.rack()?;
    let rp = tool.pitch_radius;
    let rb = rp * tool.alpha_transverse.cos();
    let root = rp - p.mn * (p.hf - p.x);
    let nominal_tip = rp + p.mn * (p.ha + p.x);
    let tip = p.tips.tip(nominal_tip, rp, false)?;
    if root <= 0. || tip <= rb || tip <= root {
        return Err("Impossible gear blank for the rack envelope.".into());
    }
    let nominal = PI / (2. * p.z) + 2. * p.x * tool.alpha_normal.tan() / p.z;
    let half = nominal - p.j / (4. * rp);
    let az = |r: f64| half + inv_radius(rp, rb) - inv_radius(r, rb);
    if !(0. < az(tip) && az(tip) < PI / p.z) {
        return Err("Pointed or overlapping tooth: check shift, addendum and backlash.".into());
    }
    let corner = |t: f64| rotate(tool.point(t), -PI / 2. + PI / p.z);
    let lo = -PI / 2.;
    let mut end = -tool.alpha_normal;
    let vend = tool.tip_center_v - tool.tip_radius * tool.alpha_normal.sin();
    let undercut = vend < -rp * tool.alpha_transverse.sin().powi(2) - 1e-10;
    let residual = |t: f64| {
        let q = corner(t);
        let r = radius(q);
        if r >= rb {
            Some(angle(q) - az(r))
        } else {
            None
        }
    };
    if undercut {
        if radius(corner(end)) < rb - 1e-10 {
            return Err("Rack undercut removes the usable involute flank.".into());
        }
        let (mut left, mut right) = (lo, end);
        for _ in 0..60 {
            let mid = (left + right) / 2.;
            if radius(corner(mid)) < rb {
                left = mid
            } else {
                right = mid
            }
        }
        left = right;
        right = end;
        let fl = residual(left);
        let fr = residual(right);
        if fl.is_none_or(|v| v > 1e-10) || fr.is_none_or(|v| v < -1e-10) {
            return Err("Unable to bracket the usable rack/involute intersection.".into());
        }
        for _ in 0..60 {
            let mid = (left + right) / 2.;
            if residual(mid).is_none_or(|v| v < 0.) {
                left = mid
            } else {
                right = mid
            }
        }
        end = (left + right) / 2.;
    }
    let start_r = radius(corner(end));
    if start_r >= tip - 1e-9 {
        return Err("Rack fillet reaches the tooth tip; no usable involute remains.".into());
    }
    let chamfer = p
        .tips
        .chamfer(rp, rb, half, tip, p.normal, p.mn / p.mt, false)?;
    let active_tip = chamfer.as_ref().map_or(tip, |c| c.join);
    if active_tip <= start_r {
        return Err("Semitopping reaches the generated root transition.".into());
    }
    let (mut points, root_bound) = if p.paired_sampling && !p.endpoints {
        let (points, bound) = crate::cad_curves::paired_rack_samples(
            &tool,
            -PI / 2. + PI / p.z,
            lo,
            end,
            p.tolerance,
        )?;
        (points, Some(bound))
    } else {
        (sample(&corner, lo, end, p.tolerance, p.endpoints)?, None)
    };
    points.pop();
    let checks = (0..=256)
        .map(|j| corner(lo + (end - lo) * j as f64 / 256.))
        .collect::<Vec<_>>();
    if angle(checks[0]) >= PI / p.z
        || checks.iter().any(|q| angle(*q) <= 0.)
        || checks
            .windows(2)
            .any(|q| radius(q[1]) < radius(q[0]) - 1e-9)
    {
        return Err("Rack envelope has overlapping roots or a non-simple flank.".into());
    }
    points.extend(sample(
        &|r| polar(r, az(r)),
        start_r,
        active_tip,
        p.tolerance,
        p.endpoints,
    )?);
    if let Some(c) = &chamfer {
        points.pop();
        points.extend(sample(
            &|r| polar(r, c.angle(r)),
            active_tip,
            tip,
            p.tolerance,
            p.endpoints,
        )?);
    }
    let mut m = metadata(
        p,
        json!({"method":"rounded normal rack envelope","tool":tool,"tool_units":"mm and radians; dimensionless shift/cos_beta", "generated":true,
        "undercut_trimmed":undercut,"involute_start_radius_mm":start_r,"root_radius_mm":root,"tip_radius_mm":tip,"chord_threshold_mm":p.tolerance,
        "domain":"external cylindrical; normal circular rack tip; no protuberance or tip relief",
        "sampling_curves":[{"kind":"rack_corner","tool":tool,"rotation":-PI/2.+PI/p.z,"start":lo,"end":end},
        {"kind":"involute_flank","rp":rp,"rb":rb,"half":half,"internal":false,"start":start_r,"end":active_tip}]}),
        rp,
        rb,
        tip,
        root,
        half,
        nominal,
        start_r,
        active_tip,
        false,
    )?;
    if let Some(c) = &chamfer {
        m["sampling_curves"]
            .as_array_mut()
            .unwrap()
            .push(c.recipe(active_tip, tip));
    }
    if p.tips.enabled() {
        m["involute_end_radius_mm"] = json!(active_tip);
    }
    p.tips
        .record(&mut m, nominal_tip, tip, chamfer.as_ref(), p.mn / p.mt);
    if p.paired_sampling {
        m["sampling_policy"] =
            json!("conservative tangent root; external material-side approximation");
        m["root_chord_bound_mm"] = json!(root_bound);
    }
    Ok((points, m))
}

fn internal(p: &Parameters) -> Result<(Vec<Point>, Value)> {
    if p.tip_radius.is_some() {
        return Err(
            "A generating-rack tip radius applies to external gears, not internal rings.".into(),
        );
    }
    if p.x != 0. {
        return Err("Shifted internal rings require a dedicated shaping cutter model.".into());
    }
    let rp = p.mt * p.z / 2.;
    let rb = rp * p.pressure.to_radians().cos();
    let root = rp + p.hf * p.mn;
    let nominal_tip = rp - p.ha * p.mn;
    let tip = p.tips.tip(nominal_tip, rp, true)?;
    let half = PI / (2. * p.z) - p.j / (4. * rp);
    let az = |r: f64| half + inv_radius(r, rb) - inv_radius(rp, rb);
    if tip <= rb || az(tip) <= 0. || az(root) >= PI / p.z {
        return Err("Internal ring outside the unshifted involute construction domain.".into());
    }
    let chamfer = p
        .tips
        .chamfer(rp, rb, half, tip, p.normal, p.mn / p.mt, true)?;
    let active_tip = chamfer.as_ref().map_or(tip, |c| c.join);
    let nominal_rho = (0.3 * p.mn).min(0.2 * (root - nominal_tip));
    let solve = |rho: f64| -> Option<[f64; 5]> {
        let center = |r: f64| {
            let q = az(r);
            let derivative = (r * r - rb * rb).max(0.).sqrt() / (rb * r);
            let tx = q.cos() - r * q.sin() * derivative;
            let ty = q.sin() + r * q.cos() * derivative;
            let norm = tx.hypot(ty);
            [r * q.cos() - rho * ty / norm, r * q.sin() + rho * tx / norm]
        };
        let (mut left, mut right) = (nominal_tip, root);
        if radius(center(left)) >= root - rho {
            return None;
        }
        for _ in 0..50 {
            let mid = (left + right) / 2.;
            if radius(center(mid)) > root - rho {
                right = mid
            } else {
                left = mid
            }
        }
        let join = (left + right) / 2.;
        let [cx, cy] = center(join);
        let q = az(join);
        let t0 = (join * q.sin() - cy).atan2(join * q.cos() - cx);
        let mut t1 = cy.atan2(cx);
        while t1 < t0 {
            t1 += TAU;
        }
        Some([join, cx, cy, t0, t1])
    };
    let fits = |s: Option<[f64; 5]>| {
        s.is_some_and(|s| {
            s[0] > tip + 1e-7 && 0. < s[4] - s[3] && s[4] - s[3] < PI && s[4] < PI / p.z - 1e-8
        })
    };
    let mut rho = nominal_rho;
    let mut solution = solve(rho);
    if !fits(solution) {
        let (mut left, mut right) = (0., nominal_rho);
        for _ in 0..45 {
            let mid = (left + right) / 2.;
            if fits(solve(mid)) {
                left = mid
            } else {
                right = mid
            }
        }
        rho = 0.9 * left;
        if rho < 1e-6f64.max(p.mn * 1e-6) {
            return Err("Internal ring has no resolvable tangent root blend.".into());
        }
        solution = solve(rho);
        if !fits(solution) {
            return Err("Unable to construct a simple internal root blend.".into());
        }
    }
    if let Some(join) = p.join {
        if join >= root || join <= tip {
            return Err("Paired ring blend join is outside the available radial domain.".into());
        }
        if solution.unwrap()[0] < join {
            let (mut low, mut high) = (1e-8f64.max(p.mn * 1e-8), rho);
            let near = solve(low);
            if !fits(near) || near.unwrap()[0] < join {
                return Err(
                    "Paired ring has no resolvable blend with the requested radial margin.".into(),
                );
            }
            for _ in 0..50 {
                let mid = (low + high) / 2.;
                let trial = solve(mid);
                if fits(trial) && trial.unwrap()[0] >= join {
                    low = mid
                } else {
                    high = mid
                }
            }
            rho = low;
            solution = solve(rho);
        }
    }
    let [join, cx, cy, t0, t1] = solution.ok_or("No internal blend solution")?;
    if p.join.is_some() && (t1 - t0 >= PI || (t1 - cy.atan2(cx)).sin().abs() > 1e-8) {
        return Err("Paired ring blend is not radially monotone.".into());
    }
    let (mut points, mut flank_bound) = if p.paired_sampling && !p.endpoints {
        let (points, bound) = crate::cad_curves::paired_internal_samples(
            rb,
            half - inv_radius(rp, rb),
            active_tip,
            join,
            p.tolerance,
        )?;
        (points, Some(bound))
    } else {
        (
            sample(
                &|r| polar(r, az(r)),
                active_tip,
                join,
                p.tolerance,
                p.endpoints,
            )?,
            None,
        )
    };
    if active_tip >= join {
        return Err("Semitopping reaches the internal root blend.".into());
    }
    if let Some(c) = &chamfer {
        let mut segment = if p.paired_sampling && !p.endpoints {
            let (points, bound) = crate::cad_curves::paired_internal_samples(
                c.base,
                c.half - inv_radius(rp, c.base),
                tip,
                active_tip,
                p.tolerance,
            )?;
            flank_bound = Some(flank_bound.unwrap_or(0.).max(bound));
            points
        } else {
            sample(
                &|r| polar(r, c.angle(r)),
                tip,
                active_tip,
                p.tolerance,
                p.endpoints,
            )?
        };
        segment.pop();
        segment.extend(points);
        points = segment;
    }
    points.pop();
    let arc = sample(
        &|t| [cx + rho * t.cos(), cy + rho * t.sin()],
        t0,
        t1,
        p.tolerance,
        p.endpoints,
    )?;
    if p.join.is_some()
        && arc
            .windows(2)
            .any(|q| segment_distance([0., 0.], q[0], q[1]) < join - 1e-8)
    {
        return Err("Sampled paired ring blend violates its radial exclusion.".into());
    }
    points.extend(arc);
    let mut m = metadata(
        p,
        json!({"method":"tangent circular internal root construction","generated":false,"blend_radius_mm":rho,"nominal_blend_radius_mm":nominal_rho,
        "blend_radius_adapted":rho<nominal_rho,"involute_end_radius_mm":join,"root_radius_mm":root,"tip_radius_mm":tip,"chord_threshold_mm":p.tolerance,
        "domain":"unshifted internal involute; pinion-cutter envelope/interference unverified",
        "sampling_curves":[{"kind":"involute_flank","rp":rp,"rb":rb,"half":half,"internal":true,"start":active_tip,"end":join},
        {"kind":"circle","center":[cx,cy],"radius":rho,"start":t0,"end":t1}]}),
        rp,
        rb,
        tip,
        root,
        half,
        PI / (2. * p.z),
        active_tip,
        join,
        true,
    )?;
    if let Some(c) = &chamfer {
        m["sampling_curves"]
            .as_array_mut()
            .unwrap()
            .insert(0, c.recipe(tip, active_tip));
    }
    if p.tips.enabled() {
        m["involute_start_radius_mm"] = json!(active_tip);
    }
    p.tips
        .record(&mut m, nominal_tip, tip, chamfer.as_ref(), p.mn / p.mt);
    if p.paired_sampling {
        m["sampling_policy"] = json!(
            "circumscribed positive-roll involute and tip; internal material-side approximation"
        );
        m["flank_chord_bound_mm"] = json!(flank_bound);
    }
    Ok((points, m))
}

pub fn involute_profile(a: &Value) -> Result<Value> {
    let mut p = Parameters::read(a)?;
    p.endpoints = false;
    let is_internal = a.get("internal").and_then(Value::as_bool).unwrap_or(false);
    let (flank, mut metadata) = if is_internal {
        internal(&p)?
    } else {
        external(&p)?
    };
    metadata.as_object_mut().unwrap().remove("sampling_curves");
    let root = metadata["root_radius_mm"].as_f64().unwrap();
    let tip = metadata["tip_radius_mm"].as_f64().unwrap();
    let pitch = TAU / p.z;
    let at = angle(flank[if is_internal { 0 } else { flank.len() - 1 }]);
    let ar = angle(flank[if is_internal { flank.len() - 1 } else { 0 }]);
    let right = if is_internal {
        flank
    } else {
        flank.into_iter().rev().collect()
    };
    let left_arc = sample(&|q| polar(root, q), -pitch / 2., -ar, p.tolerance, false)?;
    let right_arc = sample(&|q| polar(root, q), ar, pitch / 2., p.tolerance, false)?;
    if is_internal && p.join.is_some() {
        let join = metadata["involute_end_radius_mm"].as_f64().unwrap();
        if [&left_arc, &right_arc].iter().any(|arc| {
            arc.windows(2)
                .any(|q| segment_distance([0., 0.], q[0], q[1]) < join - 1e-8)
        }) {
            return Err("Paired ring root chord violates its radial exclusion.".into());
        }
    }
    let mut tip_arc = sample(&|q| polar(tip, q), -at, at, p.tolerance, false)?;
    if is_internal && (p.join.is_some() || p.paired_sampling) {
        let mut circ = vec![tip_arc[0]];
        for q in tip_arc.windows(2) {
            let (a, b) = (angle(q[0]), angle(q[1]));
            circ.push(polar(tip / ((b - a) / 2.).cos(), (a + b) / 2.));
            circ.push(q[1]);
        }
        tip_arc = circ;
        metadata["tip_sampling"] =
            json!("circumscribed tangent segments; radial exclusion preserved");
    }
    let mut local = left_arc[..left_arc.len() - 1].to_vec();
    local.extend(right.iter().rev().map(|q| [q[0], -q[1]]));
    local.extend_from_slice(&tip_arc[1..tip_arc.len() - 1]);
    local.extend(right);
    local.extend_from_slice(&right_arc[1..]);
    if local.len() * p.z as usize > 1000000 {
        return Err("Cylindrical profile exceeds its vertex limit".into());
    }
    let points = (0..p.z as usize)
        .flat_map(|k| local.iter().map(move |q| rotate(*q, k as f64 * pitch)))
        .collect();
    Ok(json!({"points":clean(points),"metadata":metadata}))
}

/// Reuse the actual external construction and its trimmed domains for the
/// bounded CAD prototype. The ordinary sampled profile contract is unchanged.
pub(crate) fn external_cad_reference(a: &Value) -> Result<Value> {
    let p = Parameters::read(a)?;
    if a["internal"] == true
        || (p.mn - p.mt).abs() > 4. * f64::EPSILON * p.mt
        || p.normal != p.pressure
    {
        return Err("Curved CAD prototype supports external spur gears only.".into());
    }
    let (_, metadata) = external(&p)?;
    Ok(metadata)
}

/// Preserve the existing normal-rack or tangent internal-blend construction.
/// This exposes its actual trimmed analytic domains without changing ordinary
/// sampled profiles or treating the internal blend as a cutter envelope.
pub(crate) fn cylindrical_cad_reference(a: &Value) -> Result<Value> {
    let p = Parameters::read(a)?;
    let (_, metadata) = if a["internal"] == true {
        internal(&p)?
    } else {
        external(&p)?
    };
    Ok(metadata)
}

pub fn cycloid_profile(a: &Value) -> Result<Value> {
    let count = n(a, "n", 16.)?;
    let r = n(a, "radius", 40.)?;
    let e = n(a, "eccentricity", 1.2)?;
    let pin = n(a, "pin", 3.)?;
    let clearance = n(a, "clearance", 0.)?;
    let tolerance = n(a, "tolerance", 0.01)?;
    if count < 3.
        || count.fract() != 0.
        || count > 10000.
        || r <= 0.
        || e <= 0.
        || pin <= 0.
        || clearance < 0.
    {
        return Err("Invalid cycloidal profile parameters".into());
    }
    if e * count >= r * 0.9 {
        return Err("Eccentricity eccessiva: usare e × N / R < 0,90.".into());
    }
    let evaluate = |t: f64| -> (Point, f64) {
        let (x, y) = (
            r * t.cos() - e * (count * t).cos(),
            r * t.sin() - e * (count * t).sin(),
        );
        let (dx, dy) = (
            -r * t.sin() + e * count * (count * t).sin(),
            r * t.cos() - e * count * (count * t).cos(),
        );
        let (ddx, ddy) = (
            -r * t.cos() + e * count * count * (count * t).cos(),
            -r * t.sin() + e * count * count * (count * t).sin(),
        );
        let speed = dx.hypot(dy);
        (
            [
                x - (pin + clearance) * dy / speed,
                y + (pin + clearance) * dx / speed,
            ],
            (dx * ddy - dy * ddx) / speed.powi(3),
        )
    };
    let probes = 4096usize.max(count as usize * 64);
    let mut curvature = f64::INFINITY;
    for j in 0..probes {
        let k = evaluate(TAU * j as f64 / probes as f64).1;
        if k > 0. {
            curvature = curvature.min(1. / k);
        }
    }
    if pin + clearance >= curvature * 0.98 {
        return Err("Cycloidal offset has cusps: reduce roller radius or eccentricity.".into());
    }
    if 2. * pin >= 2. * r * (PI / count).sin() {
        return Err("Ring rollers overlap.".into());
    }
    let samples = n(a, "samples", 0.)? as usize;
    let mut points = Vec::new();
    if samples > 1000000 {
        return Err("Cycloidal profile exceeds its vertex limit".into());
    }
    if samples > 0 {
        for j in 0..samples {
            points.push(evaluate(TAU * j as f64 / samples as f64).0);
        }
    } else {
        for j in 0..count as usize * 8 {
            let f = |t| evaluate(t).0;
            let mut segment = sample(
                &f,
                TAU * j as f64 / (count * 8.),
                TAU * (j + 1) as f64 / (count * 8.),
                tolerance,
                false,
            )?;
            segment.pop();
            points.extend(segment);
        }
    }
    Ok(json!({"points":clean(points)}))
}

pub fn gear_part(a: &Value) -> Result<Value> {
    let dimensions = crate::protocol::request(
        &json!({"protocol":1,"operation":"cylindrical_dimensions","parameters":{
        "teeth":a["z"],"module":a["m"],"pressure":a["pressure"],"helix":a["helix"],"profile_shift":a["shift"],
        "addendum":a["ha"],"dedendum":a["hf"],"backlash":a["backlash"],"width":a["width"],"internal":a["internal"],"rack_tip_radius_mm":a["rack_tip_radius_mm"],"topping_mm":crate::nominal::raw(a,"topping_mm",0.),"cutter_allowance":a["cutter_allowance"].as_bool().unwrap_or(false)}}),
    )?;
    let values = &dimensions["values"];
    let scalar = |key: &str| -> Result<f64> {
        values[key]
            .as_str()
            .ok_or("Missing analytic dimension")?
            .parse()
            .map_err(|_| "Invalid sampled dimension".into())
    };
    let mt = scalar("transverse_module_mm")?;
    let at = scalar("transverse_pressure_angle_deg")?;
    let internal = a["internal"].as_bool().unwrap_or(false);
    let m = n(a, "m", 2.)?;
    let phase = n(a, "phase", 0.)?;
    let bore = n(a, "bore", 0.)?;
    let rim = n(a, "rim", 5.)?;
    if bore < 0. || rim <= 0. {
        return Err("Invalid bore or ring rim".into());
    }
    let mut args = a.clone();
    args["mt"] = json!(mt);
    args["pressure"] = json!(at);
    args["depth"] = json!(m);
    args["normal_pressure"] = a["pressure"].clone();
    let generated = involute_profile(&args)?;
    let outline: Vec<Point> =
        serde_json::from_value(generated["points"].clone()).map_err(|e| e.to_string())?;
    let outline: Vec<Point> = outline.into_iter().map(|p| rotate(p, phase)).collect();
    if !internal
        && bore / 2.
            >= outline
                .iter()
                .map(|p| radius(*p))
                .fold(f64::INFINITY, f64::min)
                - 0.25
    {
        return Err(format!(
            "{}: bore too large for the tooth root diameter.",
            a["name"].as_str().unwrap_or("Gear")
        ));
    }
    let outer_radius = scalar("root_radius_mm")? + rim;
    let circle = |r: f64| {
        (0..96)
            .map(|j| polar(r, TAU * j as f64 / 96.))
            .collect::<Vec<_>>()
    };
    let outer = if internal {
        circle(outer_radius)
    } else {
        outline.clone()
    };
    let holes = if internal {
        vec![outline]
    } else if bore > 0. {
        vec![circle(bore / 2.)]
    } else {
        Vec::new()
    };
    Ok(
        json!({"outer":outer,"holes":holes,"width":n(a,"width",10.)?,"z":n(a,"zoff",0.)?,"center":crate::precision::sampled_arguments(&a["center"])?,"twist":scalar("twist_deg")?,"internal":internal,
        "profile_metadata":{"tooth_profile":generated["metadata"],"analytic_values":values,"analytic_precision":dimensions["precision"]},
        "outer_circle_radius":if internal{Some(outer_radius)}else{None},"bore_circle_radius":if !internal&&bore>0.{Some(bore/2.)}else{None}}),
    )
}
pub fn call(operation: &str, a: &Value) -> Result<Value> {
    match operation {
        "rack_parameters" => {
            let p = Parameters::read(a)?;
            Ok(serde_json::to_value(p.rack()?).map_err(|e| e.to_string())?)
        }
        "curve_point" => {
            let curve = &a["curve"];
            let t = n(a, "t", 0.)?;
            let q = match curve["kind"].as_str() {
                Some("rack_corner") => {
                    let tool: Rack =
                        serde_json::from_value(curve["tool"].clone()).map_err(|e| e.to_string())?;
                    rotate(tool.point(t), n(curve, "rotation", 0.)?)
                }
                Some("involute_flank") => {
                    let rp = n(curve, "rp", 1.)?;
                    let rb = n(curve, "rb", 1.)?;
                    let half = n(curve, "half", 0.)?;
                    let sign = if curve["internal"] == true { -1. } else { 1. };
                    polar(t, half + sign * (inv_radius(rp, rb) - inv_radius(t, rb)))
                }
                Some("circle") => {
                    let center: Point = serde_json::from_value(curve["center"].clone())
                        .map_err(|e| e.to_string())?;
                    let r = n(curve, "radius", 1.)?;
                    let q = polar(r, t);
                    [center[0] + q[0], center[1] + q[1]]
                }
                _ => return Err("Unknown sampling curve".into()),
            };
            if q.iter().any(|v| !v.is_finite()) {
                return Err("Nonfinite curve point".into());
            }
            Ok(json!(q))
        }
        "rack_point" => {
            let tool: Rack =
                serde_json::from_value(a["tool"].clone()).map_err(|e| e.to_string())?;
            Ok(json!(tool.point(n(a, "t", 0.)?)))
        }
        "tooth_thickness" => thickness(a),
        "external_half" | "internal_half" => {
            let p = Parameters::read(a)?;
            let (points, metadata) = if operation == "external_half" {
                external(&p)?
            } else {
                internal(&p)?
            };
            Ok(json!({"points":points,"metadata":metadata}))
        }
        "involute_profile" => involute_profile(a),
        "cycloid_profile" => cycloid_profile(a),
        _ => Err(format!("Unknown profile operation: {operation}")),
    }
}
