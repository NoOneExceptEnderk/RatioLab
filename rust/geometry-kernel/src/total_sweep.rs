// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Audit only: exact-source external helices, including the existing groove.
//! This consumes the unchanged sampler; it never chooses a coarser surface.
use crate::{
    enclosure::{I, J},
    precision::Result,
    profiles::Point,
    sampling,
    solid::Part,
};
use num_rational::BigRational;
use serde_json::{Value, json};

type P = [I; 2];
type Loops = Vec<Vec<P>>;
struct Landmark {
    z: I,
    angle: I,
    loops: Loops,
}
fn decimal(s: &str) -> Result<I> {
    I::value(&json!(s))
}
fn interval(v: &Value) -> Result<I> {
    let a = v
        .as_array()
        .filter(|a| a.len() == 2)
        .ok_or("Missing source interval")?;
    I::range(
        a[0].as_f64().ok_or("Invalid interval endpoint")?,
        a[1].as_f64().ok_or("Invalid interval endpoint")?,
    )
    .checked()
}
fn point(q: Point) -> P {
    q.map(I::point)
}
fn sub(a: P, b: P) -> P {
    [a[0] - b[0], a[1] - b[1]]
}
fn norm(q: P) -> Result<I> {
    let r = (q[0].square() + q[1].square()).checked()?;
    I::range(r.lo.max(0.), r.hi).sqrt().checked()
}
fn fraction(j: usize, n: usize) -> Result<I> {
    I::rational(&BigRational::new(j.into(), n.into()))
}
fn lerp(a: I, b: I, t: I) -> I {
    if a.lo == b.lo && a.hi == b.hi {
        a
    } else {
        a + (b - a) * t
    }
}
fn blend(a: &Loops, b: &Loops, t: I) -> Loops {
    a.iter()
        .zip(b)
        .map(|(a, b)| {
            a.iter()
                .zip(b)
                .map(|(a, b)| [lerp(a[0], b[0], t), lerp(a[1], b[1], t)])
                .collect()
        })
        .collect()
}
fn refine(loops: Loops, counts: &[Vec<usize>]) -> Result<Loops> {
    if counts.is_empty() {
        return Ok(loops);
    }
    if loops.len() != counts.len() {
        return Err("Outward refinement loop mismatch".into());
    }
    loops
        .into_iter()
        .zip(counts)
        .map(|(points, counts)| {
            if points.len() != counts.len() {
                return Err("Outward refinement vertex mismatch".into());
            }
            let mut result = Vec::new();
            for (i, n) in counts.iter().enumerate() {
                if *n == 0 || *n > 1024 {
                    return Err("Invalid outward refinement count".into());
                }
                let a = points[i];
                let b = points[(i + 1) % points.len()];
                for j in 0..*n {
                    let t = fraction(j, *n)?;
                    result.push([lerp(a[0], b[0], t), lerp(a[1], b[1], t)]);
                }
            }
            Ok(result)
        })
        .collect()
}
fn groove_map(q: P, a: I, b: I) -> Result<P> {
    let r = norm(q)?;
    if r.lo <= 0. {
        return Err("Groove reference meets its polar singularity".into());
    }
    let factor = a / r + b;
    Ok([q[0] * factor, q[1] * factor])
}
fn groove_curve(x: P, y: P, t: J, a: I, b: I) -> Result<[J; 2]> {
    let q: [J; 2] = std::array::from_fn(|k| J::from(x[k]) + t * J::from(y[k] - x[k]));
    let r = (q[0] * q[0] + q[1] * q[1]).sqrt();
    if r.v.lo <= 0. || !r.v.valid() {
        return Err("Groove chord cannot be separated from its polar singularity".into());
    }
    let f = J::from(a) / r + J::from(b);
    Ok([q[0] * f, q[1] * f])
}
fn groove_chord_bound(outer: &[Point], a: I, b: I) -> Result<f64> {
    // Enclose G(P(u)) against the SAME endpoint chord. Eight audit-only
    // cells tighten the proof without adding any geometry or interpolation.
    let mut maximum: f64 = 0.;
    for i in 0..outer.len() {
        if i % 32 == 0 {
            crate::protocol::control_check()?;
        }
        let x = point(outer[i]);
        let y = point(outer[(i + 1) % outer.len()]);
        let ga = groove_map(x, a, b)?;
        let gb = groove_map(y, a, b)?;
        let whole = groove_curve(x, y, J::variable(0., 1.), a, b)?;
        let original = (norm([whole[0].dd, whole[1].dd])? / I::point(8.))
            .checked()?
            .hi;
        let mut refined: f64 = 0.;
        for j in 0..8 {
            let lo = j as f64 / 8.;
            let hi = (j + 1) as f64 / 8.;
            let curve = groove_curve(x, y, J::variable(lo, hi), a, b)?;
            let remainder =
                norm([curve[0].dd, curve[1].dd])? * I::point(0.125).square() / I::point(8.);
            let mut endpoints: f64 = 0.;
            for t in [lo, hi] {
                let actual = groove_curve(x, y, J::variable(t, t), a, b)?;
                let target: P = std::array::from_fn(|k| lerp(ga[k], gb[k], I::point(t)));
                endpoints =
                    endpoints.max(norm([actual[0].v - target[0], actual[1].v - target[1]])?.hi);
            }
            refined = refined.max((I::point(endpoints) + remainder).checked()?.hi);
        }
        maximum = maximum.max(original.min(refined));
    }
    Ok(maximum)
}
fn bore_bound(loops: &[Vec<Point>], radius: I) -> Result<f64> {
    if radius.lo == 0. && radius.hi == 0. {
        if loops.len() != 1 {
            return Err("Absent nominal bore has sampled holes".into());
        }
        return Ok(0.);
    }
    if radius.lo <= 0. || loops.len() != 2 {
        return Err("Only the original concentric bore is qualified".into());
    }
    let hole = &loops[1];
    let mut node: f64 = 0.;
    let mut sagitta: f64 = 0.;
    for i in 0..hole.len() {
        let p = point(hole[i]);
        let q = point(hole[(i + 1) % hole.len()]);
        let r = norm(p)?;
        let s = norm(q)?;
        if r.lo <= 0. || s.lo <= 0. {
            return Err("Bore point meets the origin".into());
        }
        let error = radius - r;
        node = node.max(error.lo.abs()).max(error.hi.abs());
        let u = [p[0] / r, p[1] / r];
        let v = [q[0] / s, q[1] / s];
        if (u[0] * v[1] - u[1] * v[0]).checked()?.hi >= 0.
            || (u[0] * v[0] + u[1] * v[1]).checked()?.lo <= 0.
        {
            return Err("Bore minor-arc correspondence is unresolved".into());
        }
        let h = norm(sub(u, v))?;
        let rem = radius * (I::ONE - (I::ONE - h.square() / I::point(4.)).sqrt());
        sagitta = sagitta.max(rem.checked()?.hi);
    }
    (I::point(node) + I::point(sagitta)).checked().map(|v| v.hi)
}
struct Pose {
    width: I,
    center: P,
    z: I,
    frame: Vec<[I; 3]>,
    axis_x: bool,
}
impl Pose {
    fn read(s: &Value, axis_x: bool) -> Result<Self> {
        let frame = s["frame"]
            .as_array()
            .ok_or("Missing source frame")?
            .iter()
            .map(|row| Ok([interval(&row[0])?, interval(&row[1])?, interval(&row[2])?]))
            .collect::<Result<Vec<_>>>()?;
        if !frame.is_empty() && frame.len() != 4 {
            return Err("Incomplete source frame".into());
        }
        Ok(Self {
            width: interval(&s["width"])?,
            center: [interval(&s["center"][0])?, interval(&s["center"][1])?],
            z: interval(&s["z"])?,
            frame,
            axis_x,
        })
    }
    fn world(&self, xy: P, z: I) -> [I; 3] {
        let x = xy[0] + self.center[0];
        let y = xy[1] + self.center[1];
        let z = z + self.z;
        if !self.frame.is_empty() {
            return std::array::from_fn(|i| {
                self.frame[0][i]
                    + x * self.frame[1][i]
                    + y * self.frame[2][i]
                    + z * self.frame[3][i]
            });
        }
        if self.axis_x {
            [
                z - self.width / I::point(2.),
                y + self.center[1],
                -x + self.z,
            ]
        } else {
            [x, y, z]
        }
    }
}
fn interpolation(a: &Landmark, b: &Landmark, n: usize) -> Result<(f64, f64)> {
    let (mut radius, mut edge, mut displacement, mut change): (f64, f64, f64, f64) =
        (0., 0., 0., 0.);
    for (a, b) in a.loops.iter().zip(&b.loops) {
        if a.len() != b.len() {
            return Err("Ideal sweep loop correspondence changed".into());
        }
        for i in 0..a.len() {
            let j = (i + 1) % a.len();
            radius = radius.max(norm(a[i])?.hi).max(norm(b[i])?.hi);
            let ea = sub(a[j], a[i]);
            let eb = sub(b[j], b[i]);
            edge = edge.max(norm(ea)?.hi).max(norm(eb)?.hi);
            displacement = displacement.max(norm(sub(a[i], b[i]))?.hi);
            change = change.max(norm(sub(ea, eb))?.hi);
        }
    }
    let angle = (b.angle - a.angle).checked()?;
    let theta = I::point(angle.lo.abs().max(angle.hi.abs()));
    let n = I::point(n as f64);
    let axial = (I::point(radius) * theta.square() + I::point(2.) * theta * I::point(displacement))
        / (I::point(8.) * n.square());
    let mixed = (theta * I::point(edge) + I::point(change)) / (I::point(4.) * n);
    Ok((axial.checked()?.hi, mixed.checked()?.hi))
}
pub(crate) fn audit(a: &Value) -> Result<Value> {
    let p = Part::read(&a["part"])?;
    if p.internal || !p.stations.is_empty() || !p.mesh.is_empty() || p.alternate_diagonal {
        return Err(
            "Complete cylindrical sweep proof requires unchanged external section construction"
                .into(),
        );
    }
    let mut args = a.clone();
    args["audit_outer"] = json!(p.outer);
    // Bore coordinates are enclosed from the actual resampled loop below.
    // Native and JavaScript libm may differ by an ulp; a prototype-bit equality
    // is neither necessary nor a substitute for that measured enclosure.
    let profile = crate::total_profile::audit(&args)?;
    let pose = Pose::read(&profile["source_enclosures"], p.axis_x)?;
    let width = pose.width;
    let gap = I::number(a, "gap", "0")?;
    let k = interval(&profile["twist_per_mm_rad"])?;
    if width.lo <= 0. || gap.lo < 0. || gap.hi >= width.lo {
        return Err("Unresolved exact width or groove".into());
    }
    let root = interval(&profile["root_radius"])?;
    let e = profile["profile_bound_mm"]
        .as_f64()
        .ok_or("Missing transverse bound")?;
    let raw = p.loops(p.outer.clone(), 0., 0)?;
    if raw[0] != p.outer {
        return Err("Outer circle recognition changed the source tooth contour".into());
    }
    let base: Loops = raw
        .iter()
        .map(|l| l.iter().map(|q| point(*q)).collect())
        .collect();
    let mut groove_error = 0.;
    let mut lipschitz = 1.;
    let landmark = |z, angle, loops| Landmark { z, angle, loops };
    let mut landmarks;
    if !p.double {
        if p.gap != 0. {
            return Err("A single helix cannot declare a groove".into());
        }
        landmarks = vec![
            landmark(I::ZERO, I::ZERO, base.clone()),
            landmark(width, k * width, base.clone()),
        ];
    } else {
        let h = (width - gap) / I::point(2.);
        let peak = k * h;
        let has_gap = gap.lo > 0.;
        if has_gap != (p.gap > 0.) || (!has_gap && gap.hi != 0.) {
            return Err("Exact and sampled groove branches disagree".into());
        }
        let shoulder = if has_gap {
            decimal(".15")?
                .minimum(h * decimal(".08")?)
                .minimum(gap * decimal(".2")?)
        } else {
            I::ZERO
        };
        let end = h - shoulder;
        if end.lo <= 0. {
            return Err("Exact double-helix flank width is unresolved".into());
        }
        landmarks = vec![
            landmark(I::ZERO, I::ZERO, base.clone()),
            landmark(end, k * end, base.clone()),
        ];
        if has_gap {
            let aa = decimal(".959")? * root;
            let bb = decimal(".001")?;
            let rmin = (root - I::point(e)).checked()?;
            if rmin.lo <= 0. {
                return Err("Profile error reaches the groove singularity".into());
            }
            // |x/|x|-y/|y|| <= |x-y|/min(|x|,|y|). This also propagates
            // the profile correspondence through every shoulder blend.
            lipschitz = (aa / I::point(rmin.lo) + bb).checked()?.hi.max(1.);
            groove_error = groove_chord_bound(&p.outer, aa, bb)?;
            let mut core = base.clone();
            core[0] = base[0]
                .iter()
                .map(|q| groove_map(*q, aa, bb))
                .collect::<Result<Vec<_>>>()?;
            landmarks.push(landmark(h, peak, core.clone()));
            landmarks.push(landmark(h + gap, peak, core));
            landmarks.push(landmark(
                h + gap + shoulder,
                peak - k * shoulder,
                base.clone(),
            ));
            let bore = interval(&profile["bore_radius"])?;
            if bore.hi >= (decimal(".96")? * root).lo {
                return Err("Nominal bore meets the groove core".into());
            }
        }
        landmarks.push(landmark(width, I::ZERO, base));
    }
    let plan = sampling::build(&p)?;
    let intervals = plan.report["intervals"]
        .as_array()
        .ok_or("Missing sweep plan intervals")?;
    if intervals.len() + 1 != landmarks.len() {
        return Err("Actual and ideal sweep landmarks disagree".into());
    }
    for l in &mut landmarks {
        l.loops = refine(std::mem::take(&mut l.loops), &plan.refinements)?;
    }
    let mut error: f64 = 0.;
    let mut maximum: f64 = 0.;
    let mut index = 0;
    let mut rows = Vec::new();
    for (i, pair) in landmarks.windows(2).enumerate() {
        let n = intervals[i]["intervals"]
            .as_u64()
            .filter(|n| *n > 0 && *n <= 512)
            .ok_or("Invalid actual sweep count")? as usize;
        let (axial, mixed) = interpolation(&pair[0], &pair[1], n)?;
        maximum = maximum.max((I::point(axial) + I::point(mixed)).checked()?.hi);
        rows.push(json!({"intervals":n,"start_z":[pair[0].z.lo,pair[0].z.hi],"end_z":[pair[1].z.lo,pair[1].z.hi],
            "start_angle_rad":[pair[0].angle.lo,pair[0].angle.hi],"end_angle_rad":[pair[1].angle.lo,pair[1].angle.hi],
            "vertex_trace_bound_mm":axial,"triangle_interior_bound_mm":mixed}));
        for j in usize::from(i > 0)..=n {
            crate::protocol::control_check()?;
            let t = fraction(j, n)?;
            let z = lerp(pair[0].z, pair[1].z, t);
            let angle = lerp(pair[0].angle, pair[1].angle, t);
            let (s, c) = angle.trig();
            let ideal = blend(&pair[0].loops, &pair[1].loops, t);
            let (actual_z, actual_angle, outer) =
                plan.sections.get(index).ok_or("Actual sweep ended early")?;
            let actual = sampling::refine_loops(
                p.loops(outer.clone(), *actual_z, index)?,
                &plan.refinements,
            )?;
            if actual.len() != ideal.len() {
                return Err("Intermediate loop count changed".into());
            }
            for (a, b) in actual.iter().zip(&ideal) {
                if a.len() != b.len() {
                    return Err("Intermediate vertex count changed".into());
                }
                for (node, (q, r)) in a.iter().zip(b).enumerate() {
                    if node % 256 == 0 {
                        crate::protocol::control_check()?;
                    }
                    let exact = pose.world([r[0] * c - r[1] * s, r[0] * s + r[1] * c], z);
                    let actual = p.point(*q, *actual_z, actual_angle.to_radians());
                    let residual: [I; 3] = std::array::from_fn(|k| exact[k] - I::point(actual[k]));
                    let square = residual
                        .into_iter()
                        .fold(I::ZERO, |a, b| a + b.square())
                        .checked()?;
                    error = error.max(I::range(square.lo.max(0.), square.hi).sqrt().checked()?.hi);
                }
            }
            index += 1;
        }
    }
    if index != plan.sections.len() {
        return Err("Actual sweep contains unaccounted sections".into());
    }
    let (z, _, outer) = &plan.sections[0];
    let cap_loops = sampling::refine_loops(p.loops(outer.clone(), *z, 0)?, &plan.refinements)?;
    let bore = bore_bound(&raw, interval(&profile["bore_radius"])?)?;
    let transverse = (I::point(e) * I::point(lipschitz) + I::point(groove_error))
        .checked()?
        .hi
        .max(bore);
    Ok(
        json!({"schema":"ratiolab.cylindrical-total-sweep/1","status":"outward_enclosed",
        "source_profile":profile,"transverse_and_groove_bound_mm":transverse,
        "resampled_bore_bound_mm":bore,"groove_map_lipschitz":lipschitz,"groove_chord_bound_mm":groove_error,
        "sweep_interpolation_mm":maximum,"placement_and_source_dimensions_mm":error,
        "section_count":index,"intervals":rows,"cap_local_loops":cap_loops,"collinear_refinement":!plan.refinements.is_empty(),
        "reference":"exact normal/transverse cylindrical sources; linear twist on each declared interval; G(q)=(.959*r_root+.001*|q|)*q/|q| at the existing central groove, affine shoulders",
        "coverage":"side-surface enclosure and actual vertex placements; complete caps and mesh connectivity must also be proved by the caller"}),
    )
}
