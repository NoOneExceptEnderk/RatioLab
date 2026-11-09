// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Conjugate pinion of the custom spherical/logarithmic master. Nie et al.
//! (2024) eqs.7-8 supply the envelope condition, not this master or cutter setup.
use crate::{
    bevel::{self, Profile},
    bevel_pair as bp,
    construction_interval::{I, Jet},
    geometry_data::{Construction, Part, Station},
    precision::Result,
    profiles::{Point, n},
};
use serde_json::{Value, json};
use std::{
    cell::RefCell,
    collections::{HashMap, HashSet, VecDeque},
    f64::consts::{PI, TAU},
    rc::Rc,
};
const REFINEMENT: f64 = 0.003;
struct Generator {
    v: Value,
    offset: f64,
    ratio: f64,
    outer: f64,
    hand: f64,
    cutter: Profile,
    master: Profile,
    heel: f64,
    toe: f64,
    top: f64,
    regularity: Value,
    engagement: Value,
    cache: RefCell<HashMap<[u64; 3], [f64; 4]>>,
}
impl Generator {
    fn new(v: &Value) -> Result<Self> {
        bp::validate(v)?;
        if v.get("variant").is_some_and(|v| v != "generated") {
            return Err("Unknown hypoid construction variant".into());
        }
        let offset = n(v, "offset", 2.)?;
        let zp = n(v, "pinion", 20.)?;
        let zw = n(v, "wheel", 40.)?;
        let m = n(v, "module", 2.)?;
        let width = n(v, "width", 8.)?;
        let j = n(v, "backlash", 0.15)?;
        let outer = zp.hypot(zw) * m / 2.;
        if offset.abs() > 0.06 * outer {
            return Err("Hypoid offset exceeds the supported 6% of reference cone distance; reduce offset or enlarge the gears.".into());
        }
        if width > outer / 3. || j >= 0.7 * m {
            return Err(
                "Hypoid reference width must be at most R/3 and backlash less than 0.7 module."
                    .into(),
            );
        }
        let hand = if offset >= 0. { 1. } else { -1. };
        let mut cutter = bevel::parameters(
            &json!({"teeth":zw,"mate_teeth":zp,"module":m,"pressure":n(v,"pressure",20.)?,"backlash":0.,"beta":n(v,"spiral_angle",35.)?,"hand":hand}),
        )?;
        cutter.backlash = -j;
        cutter.tip = (zw + 1.4).atan2(zp);
        let heel = m * zw / 2.;
        let toe = heel * (1. - width / outer);
        let mut g = Self {
            v: v.clone(),
            offset,
            ratio: -zw / zp,
            outer,
            hand,
            master: cutter.clone(),
            cutter,
            heel,
            toe,
            top: 0.,
            regularity: Value::Null,
            engagement: Value::Null,
            cache: RefCell::new(HashMap::new()),
        };
        g.top = g.top_angle()?;
        g.cutter.root = g.cutter.root.min(g.top - 0.25 * m / outer);
        g.master = g.cutter.clone();
        g.master.backlash = j;
        if !(0. < g.cutter.root
            && g.cutter.root < g.top
            && 0. < g.cutter.half(g.cutter.tip)
            && g.cutter.half(g.cutter.tip) < g.cutter.half(g.cutter.root)
            && g.cutter.half(g.cutter.root) < PI / zw)
        {
            return Err("Hypoid master root/tip leaves pointed or overlapping teeth.".into());
        }
        g.regularity = g.certify_regularity()?;
        g.engagement = g.certify_tracks()?;
        g.check_bores()?;
        Ok(g)
    }
    fn m(&self) -> f64 {
        n(&self.v, "module", 2.).unwrap()
    }
    fn width(&self) -> f64 {
        n(&self.v, "width", 8.).unwrap()
    }
    fn constants(&self, theta: f64, side: f64) -> Result<(f64, f64, f64, f64)> {
        if !theta.is_finite() || theta < self.cutter.base || theta >= PI / 2. || side.abs() != 1. {
            return Err("Invalid hypoid working angle or flank".into());
        }
        let (s, c) = (theta.sin(), theta.cos());
        let hp =
            -(self.cutter.base.cos().powi(2) - c * c).max(0.).sqrt() / (self.cutter.base.sin() * s);
        let nz = side * hp * s * s - self.cutter.k * s * c;
        Ok((s, c, hp, nz))
    }
    fn solve(a: f64, b: f64, c: f64, side: f64) -> Result<f64> {
        let mag = a.hypot(b);
        if a <= 0. || c.abs() >= mag * (1. - 1e-12) || !mag.is_finite() {
            return Err("Hypoid generating branch is singular or unavailable.".into());
        }
        let psi = b.atan2(a) - side * (-c / mag).acos();
        if psi.abs() >= PI / 2. - 0.01 || !psi.is_finite() {
            return Err("Hypoid generating branch leaves the supported pinion half-space.".into());
        }
        Ok(psi)
    }
    fn at_x(&self, theta: f64, x: f64, side: f64) -> Result<[f64; 4]> {
        if !x.is_finite() || x <= 0. {
            return Err("Positive hypoid axial coordinate required".into());
        }
        let key = [theta.to_bits(), x.to_bits(), side.to_bits()];
        if let Some(r) = self.cache.borrow().get(&key) {
            return Ok(*r);
        }
        crate::protocol::control_check()?;
        let (s, c, hp, nz) = self.constants(theta, side)?;
        let psi = Self::solve(
            c + self.offset * nz * s / x,
            -side * hp * s,
            s / self.ratio,
            side,
        )?;
        let r = x / (s * psi.cos());
        let y = x * psi.tan();
        let z = r * c;
        let angle = psi - self.cutter.trace(r)? - side * self.cutter.half(theta);
        let az = z.atan2(y - self.offset) - self.ratio * angle;
        let result = [(y - self.offset).hypot(z), az, r, angle];
        if self.cache.borrow().len() < 60000 {
            self.cache.borrow_mut().insert(key, result);
        }
        Ok(result)
    }
    fn at_r(&self, theta: f64, r: f64, side: f64) -> Result<[f64; 4]> {
        if !r.is_finite() || r <= 0. {
            return Err("Positive hypoid master radius required".into());
        }
        let (s, c, hp, nz) = self.constants(theta, side)?;
        let psi = Self::solve(
            c,
            -side * hp * s,
            s / self.ratio + self.offset * nz / r,
            side,
        )?;
        let x = r * s * psi.cos();
        let y = r * s * psi.sin();
        let z = r * c;
        let angle = psi - self.cutter.trace(r)? - side * self.cutter.half(theta);
        Ok([
            x,
            (y - self.offset).hypot(z),
            z.atan2(y - self.offset) - self.ratio * angle,
            angle,
        ])
    }
    fn point(&self, theta: f64, x: f64, side: f64) -> Result<[f64; 3]> {
        let [r, a, _, _] = self.at_x(theta, x, side)?;
        Ok([r * a.cos(), r * a.sin(), x])
    }
    fn top_angle(&self) -> Result<f64> {
        let x = (self.toe + self.heel) / 2.;
        let reference = (self.at_x(self.cutter.delta, x, -1.)?[0]
            + self.at_x(self.cutter.delta, x, 1.)?[0])
            / 2.;
        let target = reference + self.m() * x / self.heel;
        let mut tops = Vec::new();
        for side in [-1., 1.] {
            let mut first = None;
            for j in 0..257 {
                let t = self.cutter.base
                    + 0.0001
                    + (self.cutter.delta - self.cutter.base - 0.0001) * j as f64 / 256.;
                if let Ok(r) = self.at_x(t, x, side) {
                    first = Some((t, r[0]));
                    break;
                }
            }
            let (mut a, r) =
                first.ok_or("Hypoid pinion crest has no supported generating branch.")?;
            if r <= target {
                return Err(
                    "Hypoid pinion addendum reaches its singular generating branch.".into(),
                );
            }
            let mut b = self.cutter.delta;
            for _ in 0..52 {
                let mid = (a + b) / 2.;
                if self.at_x(mid, x, side)?[0] > target {
                    a = mid
                } else {
                    b = mid
                }
            }
            tops.push((a + b) / 2.);
        }
        Ok(tops[0].max(tops[1]))
    }
    fn jet(
        &self,
        low: f64,
        high: f64,
        side: f64,
        axial: Option<I>,
        radius: Option<f64>,
    ) -> Result<(Jet, Jet)> {
        let theta = Jet::new(I::new(low, high), I::from(1.));
        let s = theta.sin();
        let c = theta.cos();
        let hp =
            -(self.cutter.base.cos().powi(2) - c.square()).sqrt() / (self.cutter.base.sin() * s);
        let nz = side * hp * s.square() - self.cutter.k * s * c;
        let (a, c0) = if let Some(x) = axial {
            (c + self.offset * nz * s / Jet::from(x), s / self.ratio)
        } else {
            (
                c,
                s / self.ratio
                    + self.offset * nz
                        / radius.ok_or("Hypoid interval requires radius or axial interval")?,
            )
        };
        let b = -side * hp * s;
        if !a.valid() || a.v.lo <= 0. {
            return Err("Unresolved hypoid interval branch".into());
        }
        let psi = (b / a).atan() - side * (-c0 / (a.square() + b.square()).sqrt()).acos();
        let cp = psi.cos();
        if !cp.valid() || cp.v.lo <= 0. {
            return Err("Unresolved hypoid interval half-space".into());
        }
        let (r, x) = if let Some(x) = axial {
            let x = Jet::from(x);
            (x / (s * cp), x)
        } else {
            let r = Jet::from(radius.unwrap());
            (r, r * s * cp)
        };
        let y = r * s * psi.sin();
        let z = r * c;
        let generated = ((y - self.offset).square() + z.square()).sqrt();
        if !generated.valid() || !x.valid() {
            return Err("Unresolved hypoid interval denominator or transcendental branch".into());
        }
        Ok((generated, x))
    }
    fn certify_regularity(&self) -> Result<Value> {
        let mut count = 0;
        let mut upper = f64::NEG_INFINITY;
        for side in [-1., 1.] {
            let mut stack = vec![(self.top, self.cutter.tip, self.toe, self.heel, 0)];
            while let Some((lo, hi, a, b, depth)) = stack.pop() {
                crate::protocol::control_check()?;
                count += 1;
                if count > 4096 {
                    return Err(
                        "Hypoid regularity budget exhausted; reduce offset or face width.".into(),
                    );
                }
                if let Ok((r, _)) = self.jet(lo, hi, side, Some(I::new(a, b)), None) {
                    if r.d.hi < -1e-8 {
                        upper = upper.max(r.d.hi);
                        continue;
                    }
                }
                if depth >= 14 {
                    return Err("Hypoid envelope has undercut or unresolved regularity; reduce offset or face width.".into());
                }
                if (hi - lo) / (self.cutter.tip - self.top) >= (b - a) / (self.heel - self.toe) {
                    let m = (lo + hi) / 2.;
                    stack.extend([(lo, m, a, b, depth + 1), (m, hi, a, b, depth + 1)])
                } else {
                    let m = (a + b) / 2.;
                    stack.extend([(lo, hi, a, m, depth + 1), (lo, hi, m, b, depth + 1)])
                }
            }
        }
        Ok(
            json!({"method":"Outward-expanded interval first derivatives on both working rectangles","cells":count,"radial_derivative_upper_mm_per_rad":upper,
            "scope":"Numerical libm/float interval enclosure; regular analytic working flanks only, not sampled-mesh clearance"}),
        )
    }
    fn certify_tracks(&self) -> Result<Value> {
        let radius = self.outer - self.width() / 2.;
        let q = &self.cutter;
        let wheel_toe = (self.outer - self.width()) * q.delta.cos();
        let wheel_heel = self.outer * q.delta.cos();
        if radius * q.tip.cos() <= wheel_toe + 1e-8 || radius * self.top.cos() >= wheel_heel - 1e-8
        {
            return Err("No complete mean-radius hypoid contact track inside wheel caps; increase width or change tooth counts.".into());
        }
        let mut spans = Vec::new();
        let mut count = 0;
        for side in [-1., 1.] {
            let mut stack = vec![(self.top, q.tip, 0)];
            while let Some((lo, hi, depth)) = stack.pop() {
                crate::protocol::control_check()?;
                count += 1;
                if count > 2048 {
                    return Err("Hypoid contact-track budget exhausted.".into());
                }
                if let Ok((_, x)) = self.jet(lo, hi, side, None, Some(radius)) {
                    if x.v.lo > self.toe + 1e-8 && x.v.hi < self.heel - 1e-8 {
                        continue;
                    }
                }
                if depth >= 14 {
                    return Err("Hypoid contact track leaves the pinion caps or generating branch; adjust offset / width.".into());
                }
                let m = (lo + hi) / 2.;
                stack.extend([(lo, m, depth + 1), (m, hi, depth + 1)]);
            }
            let (mut low, mut high) = (f64::INFINITY, f64::NEG_INFINITY);
            for j in 0..129 {
                let t = self.top + (q.tip - self.top) * j as f64 / 128.;
                let [x, _, _, angle] = self.at_r(t, radius, side)?;
                if (self.at_x(t, x, side)?[2] - radius).abs() > 1e-8 {
                    return Err("Hypoid generation selected inconsistent envelope branches.".into());
                }
                low = low.min(angle);
                high = high.max(angle);
            }
            spans.push((high - low) / (TAU / n(&self.v, "wheel", 40.)?));
        }
        let minimum = spans[0].min(spans[1]);
        if minimum <= 1. + 1e-8 {
            return Err("Hypoid connected-track engagement below one tooth pitch; adjust tooth counts / width / spiral angle.".into());
        }
        Ok(
            json!({"phase_span_lower_bound_teeth":minimum,"flank_spans_lower_bound_teeth":spans,"mean_radius_mm":radius,"interval_cells":count,
            "method":"Continuous mean-radius tracks enclosed inside both cap intervals; conservative unwrapped phase-span lower bound",
            "scope":"Sufficient ideal engagement; not a load/contact-pattern or continuous mesh-clearance certificate"}),
        )
    }
    fn root(&self, x: f64) -> Result<f64> {
        let reference = (self.at_x(self.cutter.delta, x, -1.)?[0]
            + self.at_x(self.cutter.delta, x, 1.)?[0])
            / 2.;
        let end = self.at_x(self.cutter.tip, x, -1.)?[0].min(self.at_x(self.cutter.tip, x, 1.)?[0]);
        Ok(
            (reference - 1.25 * self.m() * x / self.heel)
                .min(end - 0.25 * self.m() * x / self.heel),
        )
    }
    fn check_bores(&self) -> Result<()> {
        let bore = n(&self.v, "bore", 0.)?;
        let limit = if bore > 0. { bore / 2. + 0.8 } else { 1e-6 };
        let mut stack = vec![(self.toe, self.heel, 0)];
        while let Some((low, high, depth)) = stack.pop() {
            crate::protocol::control_check()?;
            let bound = || -> Result<f64> {
                let mut values = Vec::new();
                for t in [self.cutter.delta, self.cutter.tip] {
                    let mut row = Vec::new();
                    for s in [-1., 1.] {
                        row.push(self.jet(t, t, s, Some(I::new(low, high)), None)?.0.v.lo)
                    }
                    values.push(row)
                }
                Ok(
                    ((values[0][0] + values[0][1]) / 2. - 1.25 * self.m() * high / self.heel)
                        .min(values[1][0].min(values[1][1]) - 0.25 * self.m() * high / self.heel),
                )
            };
            if bound().unwrap_or(f64::NEG_INFINITY) > limit {
                continue;
            }
            if self.root((low + high) / 2.)? <= limit || depth >= 10 {
                return Err(
                    "Hypoid pinion bore leaves insufficient or unresolved nominal root wall."
                        .into(),
                );
            }
            let mid = (low + high) / 2.;
            stack.extend([(low, mid, depth + 1), (mid, high, depth + 1)]);
        }
        let root = (self.outer - self.width()) * self.master.delta.cos() * self.master.root.tan();
        if root <= n(&self.v, "output_bore", 0.)? / 2. + 0.8 {
            return Err(
                "Hypoid wheel bore leaves insufficient nominal small-end root wall.".into(),
            );
        }
        Ok(())
    }
    fn outline(&self, x: f64, angles: &[f64]) -> Result<Vec<Point>> {
        if angles.len() < 2 || angles.len() > 257 {
            return Err("Hypoid flank grid exceeds its budget".into());
        }
        let teeth = n(&self.v, "pinion", 20.)? as usize;
        let pitch = TAU / teeth as f64;
        let root = self.root(x)?;
        let mut ends = [[0.; 2]; 2];
        for (i, s) in [-1., 1.].into_iter().enumerate() {
            let [r, a, _, _] = self.at_x(self.cutter.tip, x, s)?;
            ends[i] = [r, a - if s < 0. { pitch } else { 0. }];
        }
        if !(0. < ends[1][1] - ends[0][1] && ends[1][1] - ends[0][1] < pitch) {
            return Err("Hypoid tooth roots overlap the neighboring tooth.".into());
        }
        let left = self.at_x(self.top, x, -1.)?;
        let right = self.at_x(self.top, x, 1.)?;
        let la = left[1] - pitch;
        let ra = right[1];
        if !(0. < ra - la && ra - la < pitch) {
            return Err("Hypoid pinion has pointed or overlapping crests.".into());
        }
        let mut out = Vec::new();
        for tooth in 0..teeth {
            crate::protocol::control_check()?;
            let mut add = |r: f64, a: f64| {
                let t = a + tooth as f64 * pitch;
                out.push([r * t.cos(), r * t.sin()])
            };
            add(root, ends[0][1]);
            for &t in angles.iter().rev() {
                let [r, a, _, _] = self.at_x(t, x, -1.)?;
                add(r, a - pitch)
            }
            for j in 1..32 {
                let f = j as f64 / 32.;
                add(left[0] + (right[0] - left[0]) * f, la + (ra - la) * f)
            }
            for &t in angles {
                let [r, a, _, _] = self.at_x(t, x, 1.)?;
                add(r, a)
            }
            add(root, ends[1][1]);
            for j in 1..32 {
                add(
                    root,
                    ends[1][1] + (ends[0][1] + pitch - ends[1][1]) * j as f64 / 32.,
                )
            }
            if out.len() > 10000 {
                return Err("Hypoid sampled surface exceeds the shared vertex budget.".into());
            }
        }
        Ok(out)
    }
    fn grids(&self) -> Result<(Vec<f64>, Vec<f64>)> {
        let mut angles = vec![self.top, self.cutter.tip];
        let mut xs = vec![self.toe, self.heel];
        for _ in 0..12 {
            crate::protocol::control_check()?;
            let mut split = Vec::new();
            let probes = with_mids(&xs);
            for pair in angles.windows(2) {
                let (lo, hi) = (pair[0], pair[1]);
                let mut error = 0_f64;
                for &x in &probes {
                    for side in [-1., 1.] {
                        let a = self.point(lo, x, side)?;
                        let b = self.point(hi, x, side)?;
                        for f in [0.25, 0.5, 0.75] {
                            let p = self.point(lo + (hi - lo) * f, x, side)?;
                            error = error.max(
                                (p[0] - (a[0] + (b[0] - a[0]) * f))
                                    .hypot(p[1] - (a[1] + (b[1] - a[1]) * f)),
                            );
                        }
                    }
                }
                if error > REFINEMENT {
                    split.push((lo + hi) / 2.)
                }
            }
            let changed = !split.is_empty();
            angles.extend(split);
            angles.sort_by(f64::total_cmp);
            if angles.len() > 257 {
                return Err("Hypoid flank refinement budget exhausted.".into());
            }
            let vertices = n(&self.v, "pinion", 20.)? as usize * (2 * angles.len() + 64)
                + if n(&self.v, "bore", 0.)? > 0. { 96 } else { 0 };
            if vertices > 10000 || 2 * vertices * (xs.len() - 1) + 2 > 250000 {
                return Err("Hypoid sampled surface exceeds the shared vertex/face budget; reduce tooth counts / width / curvature.".into());
            }
            let outlines = xs
                .iter()
                .map(|x| self.outline(*x, &angles))
                .collect::<Result<Vec<_>>>()?;
            let mut new = Vec::new();
            for (i, pair) in xs.windows(2).enumerate() {
                let (lo, hi) = (pair[0], pair[1]);
                let mut error = 0_f64;
                for f in [0.25, 0.5, 0.75] {
                    let middle = self.outline(lo + (hi - lo) * f, &angles)?;
                    for ((p, u), v) in middle.iter().zip(&outlines[i]).zip(&outlines[i + 1]) {
                        error = error.max(
                            (p[0] - (u[0] + (v[0] - u[0]) * f))
                                .hypot(p[1] - (u[1] + (v[1] - u[1]) * f)),
                        );
                    }
                }
                if error > REFINEMENT {
                    new.push((lo + hi) / 2.)
                }
            }
            let axial_changed = !new.is_empty();
            xs.extend(new);
            xs.sort_by(f64::total_cmp);
            if xs.len() > 65 {
                return Err("Hypoid axial refinement budget exhausted.".into());
            }
            if !changed && !axial_changed {
                return Ok((angles, xs));
            }
        }
        Err("Hypoid shared surface refinement did not converge within its budget.".into())
    }
    fn info(&self) -> Value {
        json!({"offset":self.offset,"ratio":self.ratio,"outer":self.outer,"hand":self.hand,"cutter":self.cutter,"master":self.master,"heel":self.heel,"toe":self.toe,"top":self.top,"regularity":self.regularity,"engagement":self.engagement})
    }
}
pub(crate) fn with_mids(xs: &[f64]) -> Vec<f64> {
    xs.iter()
        .copied()
        .chain(xs.windows(2).map(|p| (p[0] + p[1]) / 2.))
        .collect()
}

pub(crate) fn check_contour(points: &[Point]) -> Result<()> {
    if points.len() < 3 || points.len() > 10000 || points.iter().flatten().any(|x| !x.is_finite()) {
        return Err("Invalid hypoid sampled contour".into());
    }
    let mut unique = HashSet::new();
    for [x, y] in points {
        let bits = |v: f64| if v == 0. { 0 } else { v.to_bits() };
        if !unique.insert((bits(*x), bits(*y))) {
            return Err("Hypoid sampled section has duplicate vertices.".into());
        }
    }
    let mut segs = Vec::new();
    let count = points.len();
    for i in 0..count {
        let (a, b) = (points[i], points[(i + 1) % count]);
        segs.push((
            a[0].min(b[0]),
            a[0].max(b[0]),
            a[1].min(b[1]),
            a[1].max(b[1]),
            i,
            a,
            b,
        ))
    }
    segs.sort_by(|a, b| {
        a.0.total_cmp(&b.0)
            .then(a.1.total_cmp(&b.1))
            .then(a.2.total_cmp(&b.2))
            .then(a.3.total_cmp(&b.3))
            .then(a.4.cmp(&b.4))
    });
    let mut active: Vec<usize> = Vec::new();
    for (i, row) in segs.iter().enumerate() {
        if i % 128 == 0 {
            crate::protocol::control_check()?
        }
        active.retain(|j| segs[*j].1 >= row.0);
        for &j in &active {
            let prev = &segs[j];
            let gap = (row.4 + count - prev.4) % count;
            if gap == 1 || gap == count - 1 || prev.2 > row.3 || prev.3 < row.2 {
                continue;
            }
            if crate::solid::intersects(row.5, row.6, prev.5, prev.6) {
                return Err("Hypoid sampled pinion section intersects itself; adjust offset / tooth counts / spiral angle.".into());
            }
        }
        active.push(i);
    }
    Ok(())
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
    g.cache.borrow_mut().clear();
    let (angles, xs) = g.grids()?;
    let contours = xs
        .iter()
        .map(|x| g.outline(*x, &angles))
        .collect::<Result<Vec<_>>>()?;
    let holes = bp::bores(n(v, "bore", 0.)? / 2.)?;
    for c in &contours {
        check_contour(c)?
    }
    if 2 * (contours[0].len() + holes.iter().map(Vec::len).sum::<usize>()) * (xs.len() - 1) + 2
        > 250000
    {
        return Err("Hypoid pinion exceeds the shared face budget; reduce tooth counts / width / curvature.".into());
    }
    let mut p = Part::new(
        "Hypoid_pinion",
        contours.last().unwrap().clone(),
        holes.clone(),
        g.heel - g.toe,
    );
    p.extra["z"] = json!(g.toe);
    if n(v, "bore", 0.)? > 0. {
        p.extra["bore_circle_radius"] = json!(n(v, "bore", 0.)? / 2.);
    }
    let mut frame = bp::PINION_FRAME;
    frame[0][1] = g.offset;
    p.extra["frame"] = json!(frame);
    p.stations = xs
        .iter()
        .zip(contours)
        .enumerate()
        .map(|(i, (x, c))| {
            Station::new(
                if i == 0 {
                    0.
                } else if i == xs.len() - 1 {
                    g.heel - g.toe
                } else {
                    x - g.toe
                },
                c,
                holes.clone(),
            )
        })
        .collect();
    let q = &g.master;
    let heel = g.outer * q.delta.cos();
    let toe = (g.outer - g.width()) * q.delta.cos();
    let outer = bevel::section(q, heel, 0., REFINEMENT)?;
    let bores = bp::bores(n(v, "output_bore", 0.)? / 2.)?;
    let (radii, _) = bp::stations(std::slice::from_ref(q), g.width())?;
    if 2 * (outer.len() + bores.iter().map(Vec::len).sum::<usize>()) * (radii.len() - 1) + 2
        > 250000
    {
        return Err("Hypoid master wheel exceeds the shared face budget; reduce tooth counts / width / spiral angle.".into());
    }
    let mut w = Part::new("Hypoid_wheel", outer.clone(), bores.clone(), heel - toe);
    w.extra["z"] = json!(toe);
    if n(v, "output_bore", 0.)? > 0. {
        w.extra["bore_circle_radius"] = json!(n(v, "output_bore", 0.)? / 2.);
    }
    w.stations = radii
        .iter()
        .enumerate()
        .map(|(i, r)| {
            Ok(Station::new(
                if i == 0 {
                    0.
                } else if i == radii.len() - 1 {
                    heel - toe
                } else {
                    r * q.delta.cos() - toe
                },
                if *r == g.outer {
                    outer.clone()
                } else {
                    bp::curved_section(q, &outer, *r)?
                },
                bores.clone(),
            ))
        })
        .collect::<Result<_>>()?;
    for (part, member, axis, color, method) in [
        (
            &mut p,
            "A",
            "World +X through (0, offset, 0)",
            [0.96, 0.66, 0.33],
            "Conjugate pinion envelope of custom spherical spiral master",
        ),
        (
            &mut w,
            "B",
            "World +Z through origin",
            [0.23, 0.75, 0.65],
            "Custom spherical spiral master wheel",
        ),
    ] {
        part.extra["port"] = json!({"member":member,"axis":axis});
        part.extra["color"] = json!(color);
        part.extra["profile_metadata"] = json!({"hypoid_profile":{"method":method,"reference_doi":"10.1177/16878132241228195","reference_equations":"Conjugated surface section, equations 7–8","refinement_threshold_mm":REFINEMENT,"refinement_scope":"Finite quarter/midpoint probes, not a global surface-error or manufacturing bound"}});
    }
    Ok(Construction {
        parts: vec![p, w],
        extra: json!({"analysis":{"signed_ratio":g.ratio,"hypoid":{"offset_mm":g.offset,"shaft_angle_deg":90,"reference_distance_mm":g.outer,"reference_wheel_module_mm":g.m(),"master_reference_cone_angle_deg":q.delta.to_degrees(),"master_spiral_hand":g.hand,"pinion_derived_hand":-g.hand,"master_addendum_coefficient":0.7,"master_root_angle_deg":q.root.to_degrees(),"pinion_generating_angle_interval_rad":[g.top,q.tip],"regularity":g.regularity,"engagement":g.engagement,"pinion_axial_stations_mm":xs,"master_cone_stations_mm":radii,"rolling_equation":"pinion_teeth * pinion_rpm + wheel_teeth * wheel_rpm = 0","construction":"Custom conjugate envelope, not a translated bevel pair or commercial cutter design"}}}),
    })
}
pub fn call(a: &Value) -> Result<Value> {
    if a["action"] == "check_contour" {
        let p: Vec<Point> =
            serde_json::from_value(a["points"].clone()).map_err(|e| e.to_string())?;
        check_contour(&p)?;
        return Ok(Value::Null);
    }
    let g = prepared(&a["values"])?;
    let side = n(a, "side", 1.)?;
    match a["action"].as_str().unwrap_or("prepare") {
        "prepare" => Ok(g.info()),
        "check_bores" => {
            g.check_bores()?;
            Ok(Value::Null)
        }
        "top_angle" => Ok(json!(g.top_angle()?)),
        "constants" => {
            let (s, c, h, nz) = g.constants(n(a, "theta", g.top)?, side)?;
            Ok(json!([s, c, h, nz]))
        }
        "solve_branch" => Ok(json!(Generator::solve(
            n(a, "A", 0.)?,
            n(a, "B", 0.)?,
            n(a, "C", 0.)?,
            side
        )?)),
        "at_x" => Ok(json!(g.at_x(
            n(a, "theta", g.top)?,
            n(a, "x", g.toe)?,
            side
        )?)),
        "at_r" => Ok(json!(g.at_r(
            n(a, "theta", g.top)?,
            n(a, "radius", g.outer)?,
            side
        )?)),
        "point" => Ok(json!(g.point(
            n(a, "theta", g.top)?,
            n(a, "x", g.toe)?,
            side
        )?)),
        "root" => Ok(json!(g.root(n(a, "x", g.toe)?)?)),
        "grids" => {
            let (t, x) = g.grids()?;
            Ok(json!([t, x]))
        }
        "outline" => {
            let t: Vec<f64> =
                serde_json::from_value(a["angles"].clone()).map_err(|e| e.to_string())?;
            Ok(json!(g.outline(n(a, "x", g.toe)?, &t)?))
        }
        "jet" => {
            let axial = if a["axial"].is_array() {
                Some(I::new(n_index(&a["axial"], 0)?, n_index(&a["axial"], 1)?))
            } else {
                None
            };
            let radius = if a["radius"].is_null() {
                None
            } else {
                Some(n(a, "radius", 0.)?)
            };
            let (r, x) = g.jet(
                n(a, "low", g.top)?,
                n(a, "high", g.top)?,
                side,
                axial,
                radius,
            )?;
            Ok(json!([r, x]))
        }
        _ => Err("Unknown hypoid generator operation".into()),
    }
}
fn n_index(a: &Value, i: usize) -> Result<f64> {
    let x = a[i].as_f64().ok_or("Finite interval endpoint required")?;
    if !x.is_finite() {
        return Err("Finite interval endpoint required".into());
    }
    Ok(x)
}
