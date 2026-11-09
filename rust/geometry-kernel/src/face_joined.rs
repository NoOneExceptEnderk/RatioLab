// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Child of face.rs: continuous upper/lower swept envelope and cusp/concave
//! trimming. The finite join refinement is intentionally not called certified.
use super::*;
type Candidate = (f64, usize, f64, f64);
pub(super) struct Joined {
    pub(super) mid: f64,
    pub(super) inner: f64,
    pub(super) outer: f64,
    pub(super) cusp_max: f64,
    window_cells: usize,
    cache: RefCell<HashMap<[u64; 3], Candidate>>,
    seams: RefCell<HashMap<u64, [f64; 5]>>,
}
impl Joined {
    pub(super) fn clear_evaluations(&self) {
        self.cache.borrow_mut().clear();
        self.seams.borrow_mut().clear();
    }
    pub(super) fn new(g: &Generator) -> Result<Self> {
        let mut s = Self {
            mid: (g.x0 + g.x1) / 2.,
            inner: 0.,
            outer: 1e99,
            cusp_max: 0.,
            window_cells: 0,
            cache: RefCell::new(HashMap::new()),
            seams: RefCell::new(HashMap::new()),
        };
        for side in [-1., 1.] {
            let mut stack = vec![(g.low, g.high, 0)];
            while let Some((a, b, depth)) = stack.pop() {
                crate::protocol::control_check()?;
                s.window_cells += 1;
                if s.window_cells > 4096 {
                    return Err("Joined face annular-domain budget exhausted.".into());
                }
                let bounds = || -> Result<[I; 4]> {
                    if b - a > (g.high - g.low) / 64. {
                        return Err("Refine annular boundary".into());
                    }
                    Ok([
                        g.cell(g.x0, g.x0, a, b, side, g.k)?[7],
                        g.cell(g.x1, g.x1, a, b, side, -g.k)?[7],
                        g.cell(s.mid, s.mid, a, b, side, g.k)?[7],
                        g.cell(s.mid, s.mid, a, b, side, -g.k)?[7],
                    ])
                };
                match bounds() {
                    Ok([r0, r1, a0, b0]) => {
                        s.inner = s.inner.max(r0.hi);
                        s.outer = s.outer.min(r1.lo);
                        s.cusp_max = s.cusp_max.max(a0.hi).max(b0.hi);
                    }
                    Err(_) => {
                        if depth >= 18 {
                            return Err("Joined face annular domain is unresolved; adjust width / offset / helix.".into());
                        }
                        let mid = (a + b) / 2.;
                        stack.extend([(a, mid, depth + 1), (mid, b, depth + 1)]);
                    }
                }
            }
        }
        let margin = REFINEMENT / 4.;
        s.inner += margin;
        s.outer -= margin;
        if s.outer - s.inner < g.m {
            return Err(
                "Joined face common tooth band is too narrow; adjust width / offset / helix."
                    .into(),
            );
        }
        Ok(s)
    }
    pub(super) fn inverse(
        &self,
        g: &Generator,
        r: f64,
        h: f64,
        side: f64,
        band: Band,
    ) -> Result<Option<(Contact, f64)>> {
        let [mut a, mut b, k] = band;
        if !r.is_finite() || r <= 0. || a >= b {
            return Err("Invalid joined inverse domain".into());
        }
        let ra = g.contact(a, h, side, k)?[0];
        let rb = g.contact(b, h, side, k)?[0];
        let tolerance = 1e-10 * g.m;
        if r < ra - tolerance || r > rb + tolerance {
            return Ok(None);
        }
        let mut x = (a + (b - a) * (r - ra) / (rb - ra)).clamp(a, b);
        for _ in 0..32 {
            let row = g.contact(x, h, side, k)?;
            let error = row[0] - r;
            if error.abs() < tolerance {
                return Ok(Some((row, x)));
            }
            if error < 0. {
                a = x
            } else {
                b = x
            }
            let y = row[5];
            let q = (y * y + h * h - g.rb * g.rb).sqrt();
            let fy = g.scalar(y, x, h, side, k)?[1];
            let yx = -(side * q * y / g.rb + h) / fy;
            let trial = x - error * row[0] / (x + (y + g.e) * yx);
            x = if a < trial && trial < b {
                trial
            } else {
                (a + b) / 2.
            };
        }
        Err("Joined face inverse radius did not resolve within its bracket.".into())
    }
    fn candidates(&self, g: &Generator, r: f64, h: f64, side: f64) -> Result<Vec<Candidate>> {
        let mut result = Vec::new();
        for (index, &band) in g.bands.iter().enumerate() {
            if let Some((row, x)) = self.inverse(g, r, h, side, band)? {
                result.push((row[1], index, x, row[5]))
            }
        }
        if r >= self.mid {
            let ends = [
                g.contact(self.mid, h, side, g.k)?[5],
                g.contact(self.mid, h, side, -g.k)?[5],
            ];
            for sign in [-1., 1.] {
                let y = sign * (r * r - self.mid * self.mid).max(0.).sqrt() - g.e;
                if ends[0].min(ends[1]) - 1e-9 * g.m <= y && y <= ends[0].max(ends[1]) + 1e-9 * g.m
                {
                    let row = g.coordinates(self.mid, h, side, y)?;
                    result.push((row[1], 2, self.mid, y));
                }
            }
        }
        if result.is_empty() {
            return Err("Joined face envelope has an unsupported radial gap.".into());
        }
        Ok(result)
    }
    pub(super) fn at(&self, g: &Generator, r: f64, h: f64, side: f64) -> Result<Candidate> {
        let key = [r.to_bits(), h.to_bits(), side.to_bits()];
        if let Some(row) = self.cache.borrow().get(&key) {
            return Ok(*row);
        }
        crate::protocol::control_check()?;
        if self.cache.borrow().len() >= 50000 {
            return Err("Joined face surface evaluation budget exhausted.".into());
        }
        let candidates = self.candidates(g, r, h, side)?;
        let mut result = candidates[0];
        for candidate in candidates.into_iter().skip(1) {
            if (side == 1. && candidate > result) || (side == -1. && candidate < result) {
                result = candidate
            }
        }
        self.cache.borrow_mut().insert(key, result);
        Ok(result)
    }
    pub(super) fn anchors(&self, g: &Generator, h: f64) -> Result<[f64; 5]> {
        if let Some(row) = self.seams.borrow().get(&h.to_bits()) {
            return Ok(*row);
        }
        let convex = if g.k > 0. { 1. } else { -1. };
        let other = -convex;
        let ends = [
            g.contact(self.mid, h, convex, g.k)?[0],
            g.contact(self.mid, h, convex, -g.k)?[0],
        ];
        let mut a = g.contact(self.mid, h, other, -g.k)?[0];
        let mut b = g.contact(self.mid, h, other, g.k)?[0];
        if a > b + 1e-9 * g.m {
            return Err("Joined face concave overlap is not ordered.".into());
        }
        let difference = |r| -> Result<f64> {
            let left = self
                .inverse(g, r, h, other, g.bands[0])?
                .ok_or("Joined face trim intersection left its supported halves.")?;
            let right = self
                .inverse(g, r, h, other, g.bands[1])?
                .ok_or("Joined face trim intersection left its supported halves.")?;
            Ok(left.0[1] - right.0[1])
        };
        let mut fa = difference(a)?;
        let fb = difference(b)?;
        if fa * fb > 0. && fa.abs().min(fb.abs()) > 1e-11 {
            return Err(
                "Joined face trim intersection is not bracketed; adjust offset / helix.".into(),
            );
        }
        for _ in 0..44 {
            let r = (a + b) / 2.;
            let f = difference(r)?;
            if f * fa <= 0. {
                b = r
            } else {
                a = r;
                fa = f
            }
            if b - a < 1e-10 * g.m {
                break;
            }
        }
        let mut radii = [
            ends[0].clamp(self.inner, self.outer),
            ends[1].clamp(self.inner, self.outer),
            ((a + b) / 2.).clamp(self.inner, self.outer),
        ];
        radii.sort_by(f64::total_cmp);
        let result = [self.inner, radii[0], radii[1], radii[2], self.outer];
        if self.seams.borrow().len() >= 50000 {
            return Err("Joined face seam evaluation budget exhausted.".into());
        }
        self.seams.borrow_mut().insert(h.to_bits(), result);
        Ok(result)
    }
    pub(super) fn radius(&self, g: &Generator, t: f64, h: f64) -> Result<f64> {
        if !(0. ..=4.).contains(&t) {
            return Err("Joined face parameter outside 0 to 4".into());
        }
        let anchors = self.anchors(g, h)?;
        let i = (t as usize).min(3);
        Ok(anchors[i] + (anchors[i + 1] - anchors[i]) * (t - i as f64))
    }
    fn polar(&self, g: &Generator, t: f64, h: f64, side: f64) -> Result<P3> {
        let r = self.radius(g, t, h)?;
        Ok([r, self.at(g, r, h, side)?.0, g.height - h])
    }
    pub(super) fn point(&self, g: &Generator, t: f64, h: f64, side: f64) -> Result<P3> {
        let [r, a, z] = self.polar(g, t, h, side)?;
        Ok([r * a.cos(), r * a.sin(), z])
    }
    pub(super) fn profile(
        &self,
        g: &Generator,
        t: f64,
        hs: &[f64],
        segments: usize,
    ) -> Result<Vec<P3>> {
        if hs.len() < 2 || hs.len() > 129 || !(1..=64).contains(&segments) {
            return Err("Joined face profile grid exceeds its budget".into());
        }
        let pitch = TAU / n(&g.v, "wheel", 72.)?;
        let mut out = Vec::new();
        for &h in hs.iter().rev() {
            out.push(self.polar(g, t, h, 1.)?)
        }
        let a = self.polar(g, t, g.low, 1.)?;
        let b = self.polar(g, t, g.low, -1.)?;
        for j in 1..segments {
            let f = j as f64 / segments as f64;
            out.push([a[0], a[1] + f * (b[1] + pitch - a[1]), a[2]])
        }
        for &h in hs {
            let [r, a, z] = self.polar(g, t, h, -1.)?;
            out.push([r, a + pitch, z])
        }
        let a = self.polar(g, t, g.high, -1.)?;
        let b = self.polar(g, t, g.high, 1.)?;
        for j in 1..segments {
            let f = j as f64 / segments as f64;
            out.push([a[0], a[1] + pitch + f * (b[1] - a[1]), a[2]])
        }
        if out.windows(2).any(|p| p[1][1] <= p[0][1]) {
            return Err(
                "Joined face tooth profile points or reverses; adjust width / offset / helix."
                    .into(),
            );
        }
        Ok(out
            .into_iter()
            .map(|[r, a, z]| [r * a.cos(), r * a.sin(), z])
            .collect())
    }
    pub(super) fn grids(&self, g: &Generator) -> Result<Grids> {
        let mut hs = vec![g.low, g.high];
        let mut ts = vec![0., 1., 2., 3., 4.];
        let pitch = TAU / n(&g.v, "wheel", 72.)?;
        let segments = (g.outer * pitch * pitch / (8. * REFINEMENT))
            .sqrt()
            .ceil()
            .max(4.) as usize;
        if segments > 64 {
            return Err("Joined face crest/root arc sampling budget exhausted.".into());
        }
        for _ in 0..12 {
            crate::protocol::control_check()?;
            let mut added = Vec::new();
            for pair in hs.windows(2) {
                let (a, b) = (pair[0], pair[1]);
                let mut error = 0_f64;
                for t in crate::hypoid::with_mids(&ts) {
                    for side in [-1., 1.] {
                        let p = self.point(g, t, a, side)?;
                        let q = self.point(g, t, b, side)?;
                        for f in [0.25, 0.5, 0.75] {
                            let v = self.point(g, t, a + (b - a) * f, side)?;
                            error = error.max(distance(
                                v,
                                std::array::from_fn(|i| p[i] + (q[i] - p[i]) * f),
                            ));
                        }
                    }
                }
                if error > REFINEMENT {
                    added.push((a + b) / 2.)
                }
            }
            let mut changed = !added.is_empty();
            hs.extend(added);
            hs.sort_by(f64::total_cmp);
            let mut added = Vec::new();
            let rows = ts
                .iter()
                .map(|t| self.profile(g, *t, &hs, segments))
                .collect::<Result<Vec<_>>>()?;
            for (i, pair) in ts.windows(2).enumerate() {
                let (a, b) = (pair[0], pair[1]);
                let mut error = 0_f64;
                for f in [0.25, 0.5, 0.75] {
                    let actual = self.profile(g, a + (b - a) * f, &hs, segments)?;
                    for ((v, p), q) in actual.iter().zip(&rows[i]).zip(&rows[i + 1]) {
                        error = error.max(distance(
                            *v,
                            std::array::from_fn(|i| p[i] + (q[i] - p[i]) * f),
                        ));
                    }
                }
                if error > REFINEMENT {
                    added.push((a + b) / 2.)
                }
            }
            changed |= !added.is_empty();
            ts.extend(added);
            ts.sort_by(f64::total_cmp);
            let count = n(&g.v, "wheel", 72.)? as usize * (2 * hs.len() + 2 * (segments - 1));
            if hs.len() > 129
                || ts.len() > 129
                || count > 12000
                || count * (2 * (ts.len() - 1) + 14) > 250000
            {
                return Err(
                    "Joined face refinement budget exhausted; reduce width / helix / offset."
                        .into(),
                );
            }
            if !changed {
                return Ok((hs, vec![ts], segments));
            }
        }
        Err("Joined face refinement did not converge within its budget.".into())
    }
    pub(super) fn engagement(&self, g: &Generator) -> Result<Value> {
        let mut best = [0_f64; 2];
        let mut records = Vec::new();
        let tip = g.rp + g.m;
        let mut cells = 0;
        for (band_index, &[lo, hi, k]) in g.bands.iter().enumerate() {
            let safe_lo = if band_index == 0 {
                self.inner
            } else {
                self.inner.max(self.cusp_max)
            };
            let safe_hi = if band_index == 0 {
                self.outer.min(self.mid)
            } else {
                self.outer
            };
            for f in [0.2, 0.4, 0.6, 0.8] {
                let x = lo + (hi - lo) * f;
                for (i, side) in [-1., 1.].into_iter().enumerate() {
                    let mut stack = vec![(g.low, g.high, 0)];
                    let mut good = Vec::new();
                    while let Some((a, b, depth)) = stack.pop() {
                        crate::protocol::control_check()?;
                        cells += 1;
                        if cells > 8192 {
                            return Err("Joined face engagement-domain budget exhausted.".into());
                        }
                        if let Ok(row) = g.cell(x, x, a, b, side, k) {
                            let r = row[7];
                            let r0 = g.contact(x, a, side, k)?[3];
                            let r1 = g.contact(x, b, side, k)?[3];
                            if r.hi <= safe_lo || r.lo >= safe_hi || r0 >= tip {
                                continue;
                            }
                            if r.lo > safe_lo && r.hi < safe_hi && r1 < tip {
                                good.push((a, b));
                                continue;
                            }
                        }
                        if depth >= 14 {
                            continue;
                        }
                        let mid = (a + b) / 2.;
                        stack.extend([(a, mid, depth + 1), (mid, b, depth + 1)]);
                    }
                    good.sort_by(|a, b| a.0.total_cmp(&b.0).then(a.1.total_cmp(&b.1)));
                    let mut runs: Vec<(f64, f64)> = Vec::new();
                    for (a, b) in good {
                        if let Some(last) = runs.last_mut() {
                            if a == last.1 {
                                last.1 = b;
                                continue;
                            }
                        }
                        runs.push((a, b))
                    }
                    for (a, b) in runs {
                        let span = (g.contact(x, b, side, k)?[4] - g.contact(x, a, side, k)?[4])
                            .abs()
                            / (TAU / n(&g.v, "pinion", 24.)?);
                        if span > best[i] {
                            best[i] = span;
                            records.push(json!({"side":side,"half":band_index,"x_mm":x,"height_interval_mm":[a,b],"span_teeth":span}));
                        }
                    }
                }
            }
        }
        if best[0].min(best[1]) <= 1. + 1e-7 {
            return Err("Joined face has no complete retained smooth contact track; adjust addendum / radial setting / helix / offset.".into());
        }
        Ok(
            json!({"phase_span_lower_bound_teeth":best[0].min(best[1]),"retained_tracks":records,"method":"Connected interval-enclosed actual-pinion tracks outside all cusp/trim radii","scope":"At least one complete untouched smooth track per flank; no equal loading or axial cancellation"}),
        )
    }
    pub(super) fn info(&self) -> Value {
        json!({"method":"Upper/lower envelope of two involute halves and the pinion cusp sweep; concave intersection trimming","annular_radius_mm":[self.inner,self.outer],"pinion_cusp_x_mm":self.mid,"seam_rule":"Height-dependent cusp endpoints and concave trim intersection are explicit radial grid anchors","refinement_scope":"Finite quarter/midpoint probes at 0.003 mm; smooth patches retain numerical enclosures, join is not interval-certified"})
    }
    pub(super) fn state(&self) -> Value {
        json!({"mid":self.mid,"inner":self.inner,"outer":self.outer,"cusp_max":self.cusp_max,"window_cells":self.window_cells})
    }
    pub(super) fn call(&self, g: &Generator, a: &Value, action: &str) -> Result<Value> {
        let r = n(a, "radius", self.inner)?;
        let h = n(a, "h", g.low)?;
        let side = n(a, "side", 1.)?;
        let t = n(a, "t", 0.)?;
        if side.abs() != 1. {
            return Err("Joined face flank must be -1 or +1".into());
        }
        match action {
            "joined_at" => Ok(json!(self.at(g, r, h, side)?)),
            "joined_candidates" => Ok(json!(self.candidates(g, r, h, side)?)),
            "joined_inverse" => {
                let band: Band =
                    serde_json::from_value(a["band"].clone()).map_err(|e| e.to_string())?;
                Ok(json!(self.inverse(g, r, h, side, band)?))
            }
            "joined_anchors" => Ok(json!(self.anchors(g, h)?)),
            "joined_radius" => Ok(json!(self.radius(g, t, h)?)),
            "joined_polar" => Ok(json!(self.polar(g, t, h, side)?)),
            "joined_point" => Ok(json!(self.point(g, t, h, side)?)),
            "joined_profile" => {
                let hs: Vec<f64> =
                    serde_json::from_value(a["hs"].clone()).map_err(|e| e.to_string())?;
                Ok(json!(self.profile(
                    g,
                    t,
                    &hs,
                    n(a, "segments", 4.)? as usize
                )?))
            }
            "joined_grids" => {
                let (h, x, s) = self.grids(g)?;
                Ok(json!([h, x, s]))
            }
            "joined_info" => Ok(self.info()),
            "joined_engagement" => Ok(g.engagement.clone()),
            _ => Err("Unknown joined face operation".into()),
        }
    }
}
