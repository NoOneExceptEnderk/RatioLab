// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Analytic interpolation bound for the existing piecewise polygon sweep.
//! This does not bound the sampled profile's error against a theoretical tooth.
use crate::{
    precision::Result,
    profiles::{Point, radius},
    solid::{Part, Section},
};
use serde_json::{Value, json};

pub(crate) fn default_tolerance() -> f64 {
    0.02
}
const MAX_SECTIONS: usize = 512;
const MAX_FACES: usize = 250_000;
const SCOPE: &str = "side-triangle interpolation relative to the piecewise affine-contour, linear-twist sweep of the existing sampled 2D loops; excludes analytic tooth-profile error, placement roundoff, binary32 quantization, contact and manufacturing accuracy";

pub(crate) struct Sampling {
    pub sections: Vec<Section>,
    pub report: Value,
    pub refinements: Vec<Vec<usize>>,
}
#[derive(Clone, Copy)]
struct Bound {
    axial: f64,
    mixed: f64,
}
impl Bound {
    fn at(self, intervals: usize) -> (f64, f64) {
        let n = intervals as f64;
        (self.axial / (n * n), self.mixed / n)
    }
    fn total(self, intervals: usize) -> f64 {
        let (a, b) = self.at(intervals);
        a + b
    }
    fn intervals(self, tolerance: f64, budget: usize) -> Result<usize> {
        if !self.axial.is_finite() || !self.mixed.is_finite() {
            return Err("Nonfinite sweep interpolation bound".into());
        }
        if budget == 0 || self.total(budget) > tolerance {
            return Err(format!(
                "Surface refinement exceeds its section budget before the requested {tolerance} mm interpolation threshold; no coarser surface accepted."
            ));
        }
        let (mut lo, mut hi) = (1, budget);
        while lo < hi {
            let mid = lo + (hi - lo) / 2;
            if self.total(mid) <= tolerance {
                hi = mid;
            } else {
                lo = mid + 1;
            }
        }
        Ok(lo)
    }
}
fn distance(a: Point, b: Point) -> f64 {
    (a[0] - b[0]).hypot(a[1] - b[1])
}
fn sub(a: Point, b: Point) -> Point {
    [a[0] - b[0], a[1] - b[1]]
}
fn frame_scale(p: &Part) -> Result<f64> {
    if p.frame.is_empty() {
        return Ok(1.);
    }
    // Operator norm of the 3x2 map of a local XY error into world XYZ.
    let dot = |a: [f64; 3], b: [f64; 3]| a.into_iter().zip(b).map(|(x, y)| x * y).sum::<f64>();
    let magnitude = p.frame[1]
        .into_iter()
        .chain(p.frame[2])
        .map(f64::abs)
        .fold(0., f64::max);
    if magnitude == 0. {
        return Ok(0.);
    }
    let a = p.frame[1].map(|x| x / magnitude);
    let b = p.frame[2].map(|x| x / magnitude);
    let x = dot(a, a);
    let y = dot(b, b);
    let xy = dot(a, b);
    let scale = magnitude * ((x + y + (x - y).hypot(2. * xy)) / 2.).sqrt();
    if !scale.is_finite() {
        return Err("Nonfinite sweep placement scale".into());
    }
    Ok(scale)
}
fn interval_bound(a: &[Vec<Point>], b: &[Vec<Point>], angle: f64, scale: f64) -> Result<Bound> {
    if a.len() != b.len() || a.iter().zip(b).any(|(x, y)| x.len() != y.len()) {
        return Err("Sweep landmark vertex correspondence mismatch".into());
    }
    let (mut r, mut edge, mut displacement, mut edge_change): (f64, f64, f64, f64) =
        (0., 0., 0., 0.);
    for (a, b) in a.iter().zip(b) {
        for i in 0..a.len() {
            if i % 1024 == 0 {
                crate::protocol::control_check()?;
            }
            let j = (i + 1) % a.len();
            r = r.max(radius(a[i])).max(radius(b[i]));
            edge = edge.max(distance(a[i], a[j])).max(distance(b[i], b[j]));
            displacement = displacement.max(distance(a[i], b[i]));
            edge_change = edge_change.max(distance(sub(a[j], a[i]), sub(b[j], b[i])));
        }
    }
    // X(u,t)=R(theta*t)[(1-t)P0(u)+t*P1(u)], with P affine in u.
    // Linear axial interpolation has error <= sup|X_tt|/8. The difference
    // between its bilinear quad and either diagonal's triangles is <= |M|/4.
    // On n equal subdivisions:
    //   axial <= scale*(r*theta^2 + 2*|theta|*displacement)/(8*n^2)
    //   mixed <= scale*(|theta|*edge + edge_change)/(4*n).
    // The mixed term is essential: accurate vertex traces alone do not bound
    // the interiors of the side triangles.
    let theta = angle.abs().to_radians();
    Ok(Bound {
        axial: scale * (r * theta * theta + 2. * theta * displacement) / 8.,
        mixed: scale * (theta * edge + edge_change) / 4.,
    })
}
fn lerp(a: f64, b: f64, t: f64) -> f64 {
    if a == b { a } else { a + (b - a) * t }
}
fn check_affine_loops(
    actual: &[Vec<Point>],
    a: &[Vec<Point>],
    b: &[Vec<Point>],
    t: f64,
) -> Result<()> {
    if actual.len() != a.len() || actual.iter().zip(a).any(|(x, y)| x.len() != y.len()) {
        return Err("Intermediate sweep topology changed; interpolation bound unavailable".into());
    }
    for ((actual, a), b) in actual.iter().zip(a).zip(b) {
        for ((q, a), b) in actual.iter().zip(a).zip(b) {
            let expected = [lerp(a[0], b[0], t), lerp(a[1], b[1], t)];
            let roundoff = 64. * f64::EPSILON * radius(*q).max(radius(expected)).max(1.);
            if distance(*q, expected) > roundoff {
                return Err("Intermediate loops do not follow the declared affine sweep; interpolation bound unavailable".into());
            }
        }
    }
    Ok(())
}
pub(crate) fn refine_loops(
    loops: Vec<Vec<Point>>,
    splits: &[Vec<usize>],
) -> Result<Vec<Vec<Point>>> {
    if splits.is_empty() {
        return Ok(loops);
    }
    if loops.len() != splits.len() {
        return Err("Collinear refinement loop correspondence mismatch".into());
    }
    loops
        .into_iter()
        .zip(splits)
        .map(|(points, counts)| {
            if points.len() != counts.len() || counts.iter().any(|n| *n == 0 || *n > 1024) {
                return Err("Invalid collinear refinement correspondence".into());
            }
            let count = counts.iter().sum::<usize>();
            if count > MAX_FACES / 2 {
                return Err("Collinear refinement exceeds its vertex budget".into());
            }
            let mut result = Vec::with_capacity(count);
            for (i, subdivisions) in counts.iter().enumerate() {
                if i % 1024 == 0 {
                    crate::protocol::control_check()?;
                }
                let a = points[i];
                let b = points[(i + 1) % points.len()];
                result.push(a);
                for j in 1..*subdivisions {
                    let t = j as f64 / *subdivisions as f64;
                    result.push([lerp(a[0], b[0], t), lerp(a[1], b[1], t)]);
                }
            }
            Ok(result)
        })
        .collect()
}

pub(crate) fn build(p: &Part) -> Result<Sampling> {
    match build_refined(p, &[]) {
        Ok(plan) => Ok(plan),
        Err(error) if error.starts_with("Surface refinement requires more than 250000 faces") => {
            optimize(p)?.ok_or(error)
        }
        Err(error) => Err(error),
    }
}

fn optimize(p: &Part) -> Result<Option<Sampling>> {
    let landmarks = p.sweep_landmarks()?;
    let loops = landmarks
        .iter()
        .map(|(z, _, outer)| p.loops(outer.clone(), *z, 0))
        .collect::<Result<Vec<_>>>()?;
    let scale = frame_scale(p)?;
    let mut bounds = Vec::new();
    let mut old_counts = Vec::new();
    for (i, pair) in landmarks.windows(2).enumerate() {
        let angle = pair[1].1 - pair[0].1;
        let bound = interval_bound(&loops[i], &loops[i + 1], angle, scale)?;
        old_counts.push(
            bound
                .intervals(p.surface_tolerance_mm, MAX_SECTIONS - 1)
                .unwrap_or(MAX_SECTIONS),
        );
        bounds.push(bound);
    }
    let original = loops[0].iter().map(Vec::len).sum::<usize>();
    let mut best: Option<Sampling> = None;
    // Fractional factors matter near a face-budget boundary: splitting only
    // the few limiting edges can save one axial layer across every tooth.
    let factors = (1..=64)
        .map(|i| 1. + i as f64 / 32.)
        .chain([4., 6., 8., 12., 16., 24., 32.]);
    for factor in factors {
        crate::protocol::control_check()?;
        let mut splits = loops[0]
            .iter()
            .map(|l| vec![1usize; l.len()])
            .collect::<Vec<_>>();
        for (i, pair) in landmarks.windows(2).enumerate() {
            // Do not subdivide a circle merely to improve an already short
            // interval whose count is dominated by its axial curvature term.
            if old_counts[i] <= 4 || bounds[i].mixed == 0. {
                continue;
            }
            let target = bounds[i].mixed / factor;
            let theta = (pair[1].1 - pair[0].1).abs().to_radians();
            for ((a, b), counts) in loops[i].iter().zip(&loops[i + 1]).zip(&mut splits) {
                for j in 0..a.len() {
                    let k = (j + 1) % a.len();
                    let edge = distance(a[j], a[k]).max(distance(b[j], b[k]));
                    let change = distance(sub(a[k], a[j]), sub(b[k], b[j]));
                    let needed = (scale * (theta * edge + change) / (4. * target)).ceil() as usize;
                    counts[j] = counts[j].max(needed.max(1));
                }
            }
        }
        let refined = splits.iter().flatten().sum::<usize>();
        if refined.saturating_mul(2 * (landmarks.len() - 1)) + 2 > MAX_FACES {
            continue;
        }
        match build_refined(p, &splits) {
            Ok(mut plan) => {
                plan.report["collinear_edge_refinement"] = json!({"original_vertices_per_section":original,
                    "refined_vertices_per_section":refined,"method":"straight segments of the same piecewise affine contour; no new tooth-curve samples"});
                let faces = plan.report["side_faces_upper_bound"].as_u64().unwrap();
                if best.as_ref().is_none_or(|old| {
                    faces < old.report["side_faces_upper_bound"].as_u64().unwrap()
                }) {
                    best = Some(plan);
                }
            }
            Err(error)
                if error.starts_with("Surface refinement")
                    || error.starts_with("Collinear refinement exceeds") => {}
            Err(error) => return Err(error),
        }
    }
    Ok(best)
}

fn build_refined(p: &Part, refinements: &[Vec<usize>]) -> Result<Sampling> {
    let landmarks = p.sweep_landmarks()?;
    if !p.mesh.is_empty() || !p.stations.is_empty() {
        return Ok(Sampling {
            report: json!({"schema":"ratiolab.surface-sampling/1","status":"not_evaluated",
                "reference":if !p.mesh.is_empty(){"explicit_mesh"}else{"explicit_stations"},
                "requested_interpolation_mm":p.surface_tolerance_mm,"interpolation_bound_mm":Value::Null,
                "target_met":Value::Null,"section_count":landmarks.len(),"scope":SCOPE,
                "reason":"A continuous reference surface must be supplied by this construction; existing stations/mesh are retained."}),
            sections: landmarks,
            refinements: Vec::new(),
        });
    }
    let scale = frame_scale(p)?;
    let loops = landmarks
        .iter()
        .map(|(z, _, outer)| refine_loops(p.loops(outer.clone(), *z, 0)?, refinements))
        .collect::<Result<Vec<_>>>()?;
    let rounding = if refinements.is_empty() {
        0.
    } else {
        let extent = scale
            * loops
                .iter()
                .flatten()
                .flatten()
                .map(|p| radius(*p))
                .fold(0., f64::max);
        let error = extent * (64. * f64::EPSILON);
        if extent > 0. && error == 0. {
            f64::from_bits(1)
        } else {
            error
        }
    };
    let tolerance = p.surface_tolerance_mm - rounding;
    if tolerance <= 0. {
        return Err("Surface refinement reached numerical resolution before its threshold".into());
    }
    let budget = if p.double { MAX_SECTIONS - 1 } else { 288 };
    let mut plans = Vec::new();
    let (mut intervals, mut faces) = (0usize, 2usize);
    let mut maximum: f64 = 0.;
    let mut maximum_axial: f64 = 0.;
    let mut maximum_mixed: f64 = 0.;
    for (i, pair) in landmarks.windows(2).enumerate() {
        crate::protocol::control_check()?;
        let bound = interval_bound(&loops[i], &loops[i + 1], pair[1].1 - pair[0].1, scale)?;
        let n = bound.intervals(tolerance, budget.saturating_sub(intervals))?;
        intervals += n;
        let vertices = loops[i].iter().map(Vec::len).sum::<usize>();
        faces = vertices
            .checked_mul(n)
            .and_then(|q| q.checked_mul(2))
            .and_then(|q| q.checked_add(faces))
            .ok_or("Sweep face count overflow")?;
        if faces > MAX_FACES {
            return Err(format!(
                "Surface refinement requires more than {MAX_FACES} faces at the requested {} mm interpolation threshold; no coarser surface accepted.",
                p.surface_tolerance_mm
            ));
        }
        let (axial, mixed) = bound.at(n);
        maximum = maximum.max(axial + mixed + rounding);
        maximum_axial = maximum_axial.max(axial);
        maximum_mixed = maximum_mixed.max(mixed);
        plans.push((
            n,
            json!({"start_z_mm":pair[0].0,"end_z_mm":pair[1].0,
            "start_angle_deg":pair[0].1,"end_angle_deg":pair[1].1,"intervals":n,
            "vertex_trace_bound_mm":axial,"triangle_interior_bound_mm":mixed,
            "interpolation_bound_mm":axial+mixed+rounding}),
        ));
    }
    let mut sections = Vec::with_capacity(intervals + 1);
    sections.push(landmarks[0].clone());
    for (i, (pair, (n, _))) in landmarks.windows(2).zip(&plans).enumerate() {
        let (a, b) = (&pair[0], &pair[1]);
        for j in 1..=*n {
            crate::protocol::control_check()?;
            if j == *n {
                sections.push(b.clone());
                continue;
            }
            let t = j as f64 / *n as f64;
            let outer = if a.2 == b.2 {
                a.2.clone()
            } else {
                a.2.iter()
                    .zip(&b.2)
                    .map(|(a, b)| [lerp(a[0], b[0], t), lerp(a[1], b[1], t)])
                    .collect()
            };
            let z = lerp(a.0, b.0, t);
            // Circle recognition/resampling and groove holes are shared with
            // all surface consumers. Refuse a changed topology/non-affine
            // construction rather than attaching this bound to another shape.
            if loops[i] != loops[i + 1] {
                check_affine_loops(
                    &refine_loops(p.loops(outer.clone(), z, 0)?, refinements)?,
                    &loops[i],
                    &loops[i + 1],
                    t,
                )?;
            }
            sections.push((z, lerp(a.1, b.1, t), outer));
        }
    }
    let mut report = json!({"schema":"ratiolab.surface-sampling/1","status":"bounded",
            "reference":"piecewise_twisted_sampled_contours",
            "requested_interpolation_mm":p.surface_tolerance_mm,
            "interpolation_bound_mm":maximum,"target_met":maximum<=p.surface_tolerance_mm,
            "vertex_trace_bound_mm":maximum_axial,"triangle_interior_bound_mm":maximum_mixed,
            "section_count":sections.len(),"side_faces_upper_bound":faces,
            "placement_error_scale":scale,"intervals":plans.into_iter().map(|(_,r)|r).collect::<Vec<_>>(),
            "arithmetic":"analytic interpolation bound evaluated in binary64, not outward-rounded interval arithmetic",
            "scope":SCOPE});
    if !refinements.is_empty() {
        report["collinear_refinement_roundoff_bound_mm"] = json!(rounding);
    }
    Ok(Sampling {
        report,
        sections,
        refinements: refinements.to_vec(),
    })
}
