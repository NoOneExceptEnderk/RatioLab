// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Complete transverse enclosures against exact decimal external cylindrical/rack equations.
//! This audit never changes the sampler, trim, profile or resource ceilings.
use crate::{
    enclosure::{I, J},
    precision::Result,
    profiles::{self, Point, n},
};
use num_rational::BigRational;
use serde_json::{Value, json};

fn c(x: f64) -> J {
    J::from(I::point(x))
}
fn ji(x: I) -> J {
    J::from(x)
}
fn box2(p: [J; 2]) -> [I; 2] {
    [p[0].v, p[1].v]
}
fn length(p: [I; 2]) -> I {
    let squared = p[0].square() + p[1].square();
    // A sum of squares is nonnegative even when outward expansion crosses 0.
    if !squared.valid() {
        return squared;
    }
    I::range(squared.lo.max(0.), squared.hi).sqrt()
}
fn upper_add(a: f64, b: f64) -> Result<f64> {
    (I::point(a) + I::point(b)).checked().map(|v| v.hi)
}
fn rotate(p: [J; 2], angle: J) -> [J; 2] {
    let (s, c) = (angle.sin(), angle.cos());
    [p[0] * c - p[1] * s, p[0] * s + p[1] * c]
}
#[derive(Clone)]
struct Reference {
    z: I,
    rp: I,
    cb: I,
    rb: I,
    root: I,
    tip: I,
    rho: I,
    uc: I,
    vc: I,
    offset: I,
    rotation: I,
    end: I,
    roll0: I,
    roll1: I,
    ar: I,
    at: I,
    trim: Value,
}
impl Reference {
    fn corner(&self, t: J) -> [J; 2] {
        let (s, co) = (t.sin(), t.cos());
        let v = ji(self.vc) + ji(self.rho) * s;
        let cot = co / s;
        let phi =
            ((ji(self.uc) + ji(self.rho) * co) / ji(self.cb) - v * ji(self.cb) * cot) / ji(self.rp);
        rotate(
            [v * ji(self.cb) * cot, ji(self.rp) + v],
            ji(self.rotation) - phi,
        )
    }
    fn involute(&self, t: J) -> [J; 2] {
        let (s, co) = (t.sin(), t.cos());
        rotate(
            [ji(self.rb) * (co + t * s), ji(self.rb) * (t * co - s)],
            ji(self.offset),
        )
    }
    fn residual(&self, t: J) -> J {
        let q = self.corner(t);
        let r = (q[0] * q[0] + q[1] * q[1]).sqrt();
        let roll = ((r / ji(self.rb)) * (r / ji(self.rb)) - c(1.)).sqrt();
        (q[1] / q[0]).atan() - ji(self.offset) + roll - roll.atan()
    }
    fn read(a: &Value, metadata: &Value) -> Result<Self> {
        let z = I::number(a, "z", "24")?;
        let module = I::number(a, "mt", "2")?;
        let alpha = I::number(a, "pressure", "20")? * I::pi() / I::point(180.);
        let helix = I::number(a, "helix", "0")?;
        let beta = helix * I::pi() / I::point(180.);
        let straight = beta.lo == 0. && beta.hi == 0.;
        let cb = if straight {
            I::ONE
        } else {
            beta.cos().checked()?
        };
        let at = if straight {
            alpha
        } else {
            (alpha.tan() / cb).atan().checked()?
        };
        let j = I::number(a, "backlash", "0.15")?;
        let shift = I::number(a, "shift", "0")?;
        let ha = I::number(a, "ha", "1")?;
        let hf = I::number(a, "hf", "1.25")?;
        if z.lo != z.hi
            || z.lo.fract() != 0.
            || !(3. ..=200.).contains(&z.lo)
            || module.lo <= 0.
            || alpha.lo <= 0.
            || alpha.hi >= I::pi().lo / 2.
            || helix.lo < -45.
            || helix.hi > 45.
            || cb.lo <= 0.
        {
            return Err("Total-error audit is outside its positive external-spur domain".into());
        }
        let rp = module / cb * z / I::point(2.);
        let rb = rp * at.cos();
        let root = rp - module * (hf - shift);
        let tip = rp + module * (ha + shift);
        let land =
            I::pi() * module / I::point(4.) + j * cb / I::point(4.) - hf * module * alpha.tan();
        let rho = (I::number(&json!({"x":"0.3"}), "x", "0")? * module).minimum(
            (land - I::number(&json!({"x":"0.025"}), "x", "0")? * module) * alpha.cos()
                / (I::ONE - alpha.sin()),
        );
        let uc = land - rho * (I::ONE - alpha.sin()) / alpha.cos();
        let vc = -hf * module + rho + shift * module;
        let half = I::pi() / (I::point(2.) * z) + I::point(2.) * shift * alpha.tan() / z
            - j / (I::point(4.) * rp);
        let offset = half + at.tan() - at;
        let rotation = -I::pi() / I::point(2.) + I::pi() / z;
        let ar = I::pi() / z - uc / (cb * rp);
        let mut r = Self {
            z,
            rp,
            cb,
            rb,
            root,
            tip,
            rho,
            uc,
            vc,
            offset,
            rotation,
            end: -alpha,
            roll0: I::ZERO,
            roll1: I::ZERO,
            ar,
            at: I::ZERO,
            trim: Value::Null,
        };
        for x in [rp, rb, root, tip, rho, uc, vc, offset, ar] {
            x.checked()?;
        }
        if root.lo <= 0. || rho.lo <= 0. {
            return Err("Total-error rack blank is not positive".into());
        }
        let branch = vc - rho * alpha.sin() + rp * at.sin().square();
        if branch.lo > 0. {
            if metadata["undercut_trimmed"] == true {
                return Err("Exact and sampled rack trim branches disagree".into());
            }
            r.trim = json!({"kind":"analytic_tangent","end_rad":[r.end.lo,r.end.hi]});
        } else if branch.hi < 0. {
            if metadata["undercut_trimmed"] != true {
                return Err("Exact and sampled rack trim branches disagree".into());
            }
            let t = metadata["sampling_curves"][0]["end"]
                .as_f64()
                .ok_or("Missing sampled trim parameter")?;
            let mut delta = 1e-11;
            let mut bracket = None;
            for _ in 0..25 {
                crate::protocol::control_check()?;
                let (lo, hi) = (t - delta, t + delta);
                if lo <= (-I::pi() / I::point(2.)).hi || hi >= (-alpha).lo {
                    break;
                }
                let fl = r.residual(J::variable(lo, lo)).v;
                let fr = r.residual(J::variable(hi, hi)).v;
                let derivative = r.residual(J::variable(lo, hi)).d;
                if fl.valid()
                    && fr.valid()
                    && derivative.valid()
                    && fl.hi < 0.
                    && fr.lo > 0.
                    && derivative.lo > 0.
                {
                    bracket = Some((lo, hi, fl, fr, derivative));
                    break;
                }
                delta *= 2.;
            }
            let (lo, hi, fl, fr, derivative) = bracket
                .ok_or("Total-error audit could not isolate a unique exact rack/involute trim")?;
            r.end = I::range(lo, hi);
            r.trim = json!({"kind":"isolated_exact_intersection","end_rad":[lo,hi],
                "left_residual":[fl.lo,fl.hi],"right_residual":[fr.lo,fr.hi],
                "derivative":[derivative.lo,derivative.hi],"existence":"strict sign bracket and positive whole-interval derivative"});
        } else {
            return Err("Total-error audit cannot resolve the critical undercut branch".into());
        }
        let q = box2(r.corner(ji(r.end)));
        let radius = length(q).checked()?;
        let roll = ((radius / rb).square() - I::ONE).checked()?;
        if roll.lo <= 0. {
            return Err(
                "Total-error audit cannot separate the usable involute from its base singularity"
                    .into(),
            );
        }
        r.roll0 = roll.sqrt().checked()?;
        r.roll1 = ((tip / rb).square() - I::ONE).sqrt().checked()?;
        r.at = offset - r.roll1 + r.roll1.atan();
        let start_angle = offset - r.roll0 + r.roll0.atan();
        if r.at.lo <= 0. || start_angle.hi >= (I::pi() / z).lo || r.roll1.lo <= r.roll0.hi {
            return Err(
                "Total-error audit cannot prove a separated, non-pointed involute sector".into(),
            );
        }
        Ok(r)
    }
}

fn exact_fraction(a: f64, b: f64, c: f64) -> Result<I> {
    let q = |v| BigRational::from_float(v).ok_or("Nonfinite curve-domain operand");
    let numerator = q(a)? - q(b)?;
    let denominator = q(c)? - q(b)?;
    if denominator == BigRational::from_integer(0.into()) {
        return Err("Degenerate sampled curve domain".into());
    }
    I::rational(&(numerator / denominator))
}
fn old_roll(r: f64, rb: f64) -> Result<I> {
    let r = BigRational::from_float(r).ok_or("Nonfinite sampled radius")?;
    let rb = BigRational::from_float(rb).ok_or("Nonfinite sampled base radius")?;
    let q = (&r * &r - &rb * &rb) / (&rb * &rb);
    I::rational(&q)?.sqrt().checked()
}
#[derive(Clone, Copy)]
enum Kind {
    Rack,
    Involute,
    Circle(I),
}
struct Piece<'a> {
    reference: &'a Reference,
    kind: Kind,
    start: I,
    end: I,
}
impl Piece<'_> {
    fn point(&self, u: J) -> [J; 2] {
        let t = ji(self.start) + u * ji(self.end - self.start);
        match self.kind {
            Kind::Rack => self.reference.corner(t),
            Kind::Involute => self.reference.involute(t),
            Kind::Circle(radius) => [ji(radius) * t.cos(), ji(radius) * t.sin()],
        }
    }
    fn valid_reference(&self, u: I, point: [I; 2]) -> Result<()> {
        if !point.iter().all(|v| v.valid()) {
            return Err("Nonfinite total-error curve enclosure".into());
        }
        if let Kind::Rack = self.kind {
            let r = self.reference;
            let t = self.start + u * (self.end - self.start);
            let sin = t.sin();
            let v = r.vc + r.rho * sin;
            let radial = r.rp * r.rho + r.rho * v * (I::ONE - r.cb.square())
                - r.cb.square() * r.vc * v / (sin * sin.square());
            // r(t)^2' = 2 cos(t) * radial. cos(t)>=0 on the declared rack domain.
            let sector = point[0] * (I::pi() / r.z).sin() - point[1] * (I::pi() / r.z).cos();
            if !radial.valid()
                || radial.lo <= 0.
                || point[0].lo <= 0.
                || point[1].lo <= 0.
                || sector.lo <= 0.
            {
                return Err("Total-error audit cannot prove a simple monotone rack flank in its tooth sector".into());
            }
        }
        Ok(())
    }
}
fn distance_to_chord(p: [I; 2], a: Point, b: Point) -> Result<f64> {
    let mid = [p[0].mid(), p[1].mid()];
    let d = [b[0] - a[0], b[1] - a[1]];
    let den = d[0] * d[0] + d[1] * d[1];
    let u = if den > 0. {
        ((mid[0] - a[0]) * d[0] + (mid[1] - a[1]) * d[1]) / den
    } else {
        0.
    };
    let u = I::point(u.clamp(0., 1.));
    let q: [I; 2] = std::array::from_fn(|k| I::point(a[k]) + u * (I::point(b[k]) - I::point(a[k])));
    length([p[0] - q[0], p[1] - q[1]]).checked().map(|v| v.hi)
}
fn endpoint_error(p: [I; 2], q: Point) -> Result<f64> {
    length([p[0] - I::point(q[0]), p[1] - I::point(q[1])])
        .checked()
        .map(|v| v.hi)
}
fn enclosure(
    piece: &Piece<'_>,
    a: f64,
    b: f64,
    chord: [Point; 2],
    resolution: f64,
    depth: u8,
    work: &mut usize,
) -> Result<f64> {
    *work += 1;
    if *work > 131072 {
        return Err("Total-error audit exhausted its curve-cell budget".into());
    }
    if *work % 32 == 0 {
        crate::protocol::control_check()?;
    }
    let q = piece.point(J::variable(a, b));
    let h = I::point(b) - I::point(a);
    let rem = (length([q[0].dd, q[1].dd]) * h.square() / I::point(8.))
        .checked()?
        .hi;
    let validity = piece.valid_reference(I::range(a, b), box2(q));
    if rem > resolution || validity.is_err() {
        if depth >= 24 {
            return Err("Total-error audit cannot resolve a curve enclosure or sector before its depth limit".into());
        }
        let mid = (a + b) / 2.;
        if mid == a || mid == b {
            return Err("Total-error audit reached numerical resolution".into());
        }
        return Ok(
            enclosure(piece, a, mid, chord, resolution, depth + 1, work)?.max(enclosure(
                piece,
                mid,
                b,
                chord,
                resolution,
                depth + 1,
                work,
            )?),
        );
    }
    let pa = box2(piece.point(ji(I::point(a))));
    let pb = box2(piece.point(ji(I::point(b))));
    upper_add(
        distance_to_chord(pa, chord[0], chord[1])?.max(distance_to_chord(pb, chord[0], chord[1])?),
        rem,
    )
}
fn curve_point(curve: &Value, t: f64) -> Result<Point> {
    serde_json::from_value(profiles::call(
        "curve_point",
        &json!({"curve":curve,"t":t}),
    )?)
    .map_err(|e| e.to_string())
}
fn curve<'a>(reference: &'a Reference, descriptor: &Value, a: f64, b: f64) -> Result<Piece<'a>> {
    let old_start = n(descriptor, "start", 0.)?;
    let old_end = n(descriptor, "end", 0.)?;
    let kind = descriptor["kind"]
        .as_str()
        .ok_or("Missing total-error curve kind")?;
    let (kind, lo, hi, fa, fb) = match kind {
        "rack_corner" => (
            Kind::Rack,
            -I::pi() / I::point(2.),
            reference.end,
            exact_fraction(a, old_start, old_end)?,
            exact_fraction(b, old_start, old_end)?,
        ),
        "involute_flank" => {
            let rb = n(descriptor, "rb", 0.)?;
            let lo = old_roll(old_start, rb)?;
            let hi = old_roll(old_end, rb)?;
            (
                Kind::Involute,
                reference.roll0,
                reference.roll1,
                (old_roll(a, rb)? - lo) / (hi - lo),
                (old_roll(b, rb)? - lo) / (hi - lo),
            )
        }
        "circle" => {
            let root = descriptor["tag"] == "root";
            let right = descriptor["tag"] == "root_right";
            (
                Kind::Circle(if root || right {
                    reference.root
                } else {
                    reference.tip
                }),
                if root {
                    -I::pi() / reference.z
                } else if right {
                    reference.ar
                } else {
                    -reference.at
                },
                if root {
                    -reference.ar
                } else if right {
                    I::pi() / reference.z
                } else {
                    reference.at
                },
                exact_fraction(a, old_start, old_end)?,
                exact_fraction(b, old_start, old_end)?,
            )
        }
        _ => return Err("Unsupported total-error curve".into()),
    };
    let start = (lo + fa * (hi - lo)).checked()?;
    let end = (lo + fb * (hi - lo)).checked()?;
    Ok(Piece {
        reference,
        kind,
        start,
        end,
    })
}
fn sampled(
    reference: &Reference,
    descriptor: Value,
    resolution: f64,
    work: &mut usize,
) -> Result<(Vec<Point>, Value)> {
    let start = n(&descriptor, "start", 0.)?;
    let end = n(&descriptor, "end", 0.)?;
    let (points, domains) = profiles::sample_with_domains(
        &|t| curve_point(&descriptor, t).unwrap_or([f64::NAN; 2]),
        start,
        end,
        0.015,
    )?;
    let mut rows = Vec::new();
    let mut maximum: f64 = 0.;
    for (a, b) in domains {
        let p = curve_point(&descriptor, a)?;
        let q = curve_point(&descriptor, b)?;
        let piece = curve(reference, &descriptor, a, b)?;
        let pa = box2(piece.point(ji(I::ZERO)));
        let pb = box2(piece.point(ji(I::ONE)));
        let node = endpoint_error(pa, p)?.max(endpoint_error(pb, q)?);
        let bound = upper_add(
            enclosure(&piece, 0., 1., [p, q], resolution, 0, work)?,
            upper_add(node, node)?,
        )?;
        maximum = maximum.max(bound);
        rows.push(json!({"start":a,"end":b,"chord_bound_mm":bound,"endpoint_error_mm":node,
            "reference_start_rad":[piece.start.lo,piece.start.hi],"reference_end_rad":[piece.end.lo,piece.end.hi],
            "start_box":[[pa[0].lo,pa[0].hi],[pa[1].lo,pa[1].hi]],"end_box":[[pb[0].lo,pb[0].hi],[pb[1].lo,pb[1].hi]]}));
    }
    Ok((
        points,
        json!({"curve":descriptor,"intervals":rows,"chord_bound_mm":maximum}),
    ))
}
fn source_intervals(v: &Value) -> Result<Value> {
    fn recurse(v: &Value, depth: usize, count: &mut usize) -> Result<Value> {
        *count += 1;
        if depth > 32 || *count > 4096 {
            return Err("Source interval ledger exceeds its bounded size".into());
        }
        if *count % 128 == 0 {
            crate::protocol::control_check()?;
        }
        if let Some(a) = v.as_array() {
            return a
                .iter()
                .map(|v| recurse(v, depth + 1, count))
                .collect::<Result<Vec<_>>>()
                .map(Value::Array);
        }
        if let Some(m) = v.as_object()
            && !m.contains_key("expression")
        {
            return m
                .iter()
                .map(|(k, v)| Ok((k.clone(), recurse(v, depth + 1, count)?)))
                .collect::<Result<serde_json::Map<_, _>>>()
                .map(Value::Object);
        }
        let x = I::value(v)?;
        Ok(json!([x.lo, x.hi]))
    }
    recurse(v, 0, &mut 0)
}
pub(crate) fn audit(a: &Value) -> Result<Value> {
    crate::enclosure::environment()?;
    for key in ["internal", "endpoints", "safe_pair_sampling"] {
        if a.get(key).is_some_and(|v| !v.is_null() && v != false) {
            return Err(
                "Complete spur proof does not cover internal or alternate sampling constructions"
                    .into(),
            );
        }
    }
    for key in ["rack_tip_radius_mm", "minimum_join_radius_mm", "tolerance"] {
        if a.get(key).is_some_and(|v| !v.is_null()) {
            return Err(
                "Complete spur proof requires the unmodified ordinary rack and profile sampler"
                    .into(),
            );
        }
    }
    // Recreate the actual public constructor's sampled argument path, including
    // its analytic decimal record, before tracing its unchanged sampler.
    let gear = profiles::gear_part(
        &json!({"name":"Gear","z":a.get("z").cloned().unwrap_or(json!(24)),
        "m":a.get("mt").cloned().unwrap_or(json!(2)),"pressure":a.get("pressure").cloned().unwrap_or(json!(20)),
        "backlash":a.get("backlash").cloned().unwrap_or(json!(0.15)),"shift":a.get("shift").cloned().unwrap_or(json!(0)),
        "ha":a.get("ha").cloned().unwrap_or(json!(1)),"hf":a.get("hf").cloned().unwrap_or(json!(1.25)),
        "width":10,"bore":a.get("bore").cloned().unwrap_or(json!(0)),"center":[0,0],"phase":0,"helix":a.get("helix").cloned().unwrap_or(json!(0)),"internal":false,"rim":5,"zoff":0}),
    )?;
    if a.get("audit_outer").is_some_and(|v| v != &gear["outer"]) {
        return Err("Total-error source contour does not match the public constructor".into());
    }
    let values = &gear["profile_metadata"]["analytic_values"];
    let mut actual = a.clone();
    actual["mt"] = json!(
        values["transverse_module_mm"]
            .as_str()
            .ok_or("Missing actual sampled module")?
            .parse::<f64>()
            .map_err(|e| e.to_string())?
    );
    actual["pressure"] = json!(
        values["transverse_pressure_angle_deg"]
            .as_str()
            .ok_or("Missing actual sampled angle")?
            .parse::<f64>()
            .map_err(|e| e.to_string())?
    );
    actual["depth"] = a.get("mt").cloned().unwrap_or(json!(2));
    actual["normal_pressure"] = a.get("pressure").cloned().unwrap_or(json!(20));
    let metadata = profiles::cylindrical_cad_reference(&actual)?;
    let reference = Reference::read(a, &metadata)?;
    let resolution = n(a, "budget_refinement_mm", 0.0002)?;
    if resolution <= 0. || resolution > 0.01 {
        return Err(
            "Total-error refinement resolution must be positive and at most 0.01 mm".into(),
        );
    }
    let mut work = 0;
    let descriptors = metadata["sampling_curves"]
        .as_array()
        .ok_or("Missing actual curve domains")?;
    let (root, root_report) = sampled(&reference, descriptors[0].clone(), resolution, &mut work)?;
    let (flank, flank_report) = sampled(&reference, descriptors[1].clone(), resolution, &mut work)?;
    let first = root[0];
    let last = *flank.last().ok_or("Empty sampled involute")?;
    let ar = first[1].atan2(first[0]);
    let at = last[1].atan2(last[0]);
    let z = reference.z.lo;
    let root_radius = n(&metadata, "root_radius_mm", 0.)?;
    let tip_radius = n(&metadata, "tip_radius_mm", 0.)?;
    let (root_arc, root_arc_report) = sampled(
        &reference,
        json!({"kind":"circle","tag":"root","radius":root_radius,"center":[0,0],"start":-std::f64::consts::PI/z,"end":-ar}),
        resolution,
        &mut work,
    )?;
    let (tip_arc, tip_arc_report) = sampled(
        &reference,
        json!({"kind":"circle","tag":"tip","radius":tip_radius,"center":[0,0],"start":-at,"end":at}),
        resolution,
        &mut work,
    )?;
    let (root_right, root_right_report) = sampled(
        &reference,
        json!({"kind":"circle","tag":"root_right","radius":root_radius,"center":[0,0],"start":ar,"end":std::f64::consts::PI/z}),
        resolution,
        &mut work,
    )?;
    let mut half = root.clone();
    half.pop();
    half.extend_from_slice(&flank);
    let right = half.into_iter().rev().collect::<Vec<_>>();
    let mut local = root_arc[..root_arc.len() - 1].to_vec();
    local.extend(right.iter().rev().map(|q| [q[0], -q[1]]));
    local.extend_from_slice(&tip_arc[1..tip_arc.len() - 1]);
    local.extend(right);
    local.extend_from_slice(&root_right[1..]);
    let pitch = std::f64::consts::TAU / z;
    let mut raw = Vec::new();
    let mut rotation_error: f64 = 0.;
    for k in 0..z as usize {
        crate::protocol::control_check()?;
        let angle = I::point(2. * k as f64) * I::pi() / reference.z;
        let (s, c) = angle.trig();
        for p in &local {
            let q = profiles::rotate(*p, k as f64 * pitch);
            let exact = [
                I::point(p[0]) * c - I::point(p[1]) * s,
                I::point(p[0]) * s + I::point(p[1]) * c,
            ];
            rotation_error = rotation_error.max(endpoint_error(exact, q)?);
            raw.push(q);
        }
    }
    let cleaned = profiles::clean(raw.clone());
    let expected: Vec<Point> =
        serde_json::from_value(gear["outer"].clone()).map_err(|e| e.to_string())?;
    if cleaned != expected {
        return Err("Total-error trace does not match the actual public spur constructor".into());
    }
    let mut grid = Vec::new();
    let mut keep = Vec::new();
    let mut mapping = Vec::new();
    let mut grid_error: f64 = 0.;
    for p in raw {
        let q = [
            format!("{:.9}", p[0])
                .parse::<f64>()
                .map_err(|e| e.to_string())?,
            format!("{:.9}", p[1])
                .parse::<f64>()
                .map_err(|e| e.to_string())?,
        ];
        grid_error = grid_error.max(endpoint_error([I::point(p[0]), I::point(p[1])], q)?);
        if keep
            .last()
            .is_none_or(|v: &Point| (q[0] - v[0]).hypot(q[1] - v[1]) > 1e-7)
        {
            keep.push(q);
        }
        mapping.push(keep.len() - 1);
        grid.push(q);
    }
    if keep.len() > 1
        && (keep[0][0] - keep.last().unwrap()[0]).hypot(keep[0][1] - keep.last().unwrap()[1]) < 1e-7
    {
        let last = keep.len() - 1;
        keep.pop();
        for index in &mut mapping {
            if *index == last {
                *index = 0;
            }
        }
    }
    if keep != cleaned {
        return Err("Total-error cleanup trace lost vertex correspondence".into());
    }
    let mut cleanup: f64 = 0.;
    for (p, k) in grid.iter().zip(mapping) {
        cleanup = cleanup.max(endpoint_error([I::point(p[0]), I::point(p[1])], keep[k])?);
    }
    let rack_join = endpoint_error(
        [
            I::point(root.last().unwrap()[0]),
            I::point(root.last().unwrap()[1]),
        ],
        flank[0],
    )?;
    let arc_joins = [
        endpoint_error(
            [I::point(first[0]), I::point(-first[1])],
            *root_arc.last().ok_or("Empty root arc")?,
        )?,
        endpoint_error([I::point(first[0]), I::point(first[1])], root_right[0])?,
        endpoint_error([I::point(last[0]), I::point(-last[1])], tip_arc[0])?,
        endpoint_error(
            [I::point(last[0]), I::point(last[1])],
            *tip_arc.last().ok_or("Empty tip arc")?,
        )?,
    ];
    let joins = upper_add(rack_join, arc_joins.into_iter().fold(0., f64::max))?;
    let curves = vec![
        root_report,
        flank_report,
        root_arc_report,
        root_right_report,
        tip_arc_report,
    ];
    let maximum = curves
        .iter()
        .map(|v| v["chord_bound_mm"].as_f64().unwrap())
        .fold(0., f64::max);
    let total = upper_add(
        upper_add(upper_add(maximum, joins)?, rotation_error)?,
        upper_add(grid_error, cleanup)?,
    )?;
    let bore_radius = I::number(a, "bore", "0")? / I::point(2.);
    if bore_radius.lo < 0. {
        return Err("A nonnegative exact bore is required".into());
    }
    let mut bore_bound = 0.;
    let mut bore_node_error: f64 = 0.;
    let mut bore_nodes = 0;
    if bore_radius.hi > 0. {
        let loops: Vec<Vec<Point>> =
            serde_json::from_value(gear["holes"].clone()).map_err(|e| e.to_string())?;
        if bore_radius.lo <= 0. || loops.len() != 1 || bore_radius.hi >= reference.root.lo {
            return Err("Total-error audit cannot prove the nominal bore topology".into());
        }
        bore_nodes = loops[0].len();
        for (k, p) in loops[0].iter().enumerate() {
            let angle = I::point(2. * k as f64) * I::pi() / I::point(bore_nodes as f64);
            let (s, c) = angle.trig();
            bore_node_error =
                bore_node_error.max(endpoint_error([bore_radius * c, bore_radius * s], *p)?);
        }
        let sagitta = I::point(2.)
            * bore_radius
            * (I::pi() / I::point(2. * bore_nodes as f64)).sin().square();
        bore_bound = upper_add(sagitta.checked()?.hi, bore_node_error)?;
    }
    let twist_per_mm =
        (I::number(a, "helix", "0")? * I::pi() / I::point(180.)).tan() / reference.rp;
    twist_per_mm.checked()?;
    let placement = source_intervals(a.get("sources").unwrap_or(&json!({})))?;
    Ok(
        json!({"schema":"ratiolab.spur-total-profile/1","status":"outward_enclosed",
        "metric":"symmetric Hausdorff distance; complete repeated transverse source boundary",
        "reference":"exact decimal nominal external cylindrical dimensions and normal rounded-rack construction; actual usable trim isolated independently",
        "profile_bound_mm":total,"curve_source_bound_mm":maximum,"sampled_join_bound_mm":joins,
        "replication_roundoff_bound_mm":rotation_error,"coordinate_grid_bound_mm":grid_error,"cleanup_bound_mm":cleanup,
        "audit_cells":work,"trim":reference.trim,"root_radius":[reference.root.lo,reference.root.hi],
        "pitch_radius":[reference.rp.lo,reference.rp.hi],
        "twist_per_mm_rad":[twist_per_mm.lo,twist_per_mm.hi],
        "tip_radius":[reference.tip.lo,reference.tip.hi],"base_radius":[reference.rb.lo,reference.rb.hi],
        "root_roll":[reference.roll0.lo,reference.roll0.hi],"tip_roll":[reference.roll1.lo,reference.roll1.hi],
        "bore_bound_mm":bore_bound,"bore_node_error_mm":bore_node_error,"bore_radius":[bore_radius.lo,bore_radius.hi],"bore_nodes":bore_nodes,
        "source_enclosures":placement,"curves":curves,
        "arithmetic":"IEEE binary64 operations expanded outwards; rational input/PI enclosures; Taylor trigonometry with bounded remainder; no host-libm transcendental error assumption"}),
    )
}
