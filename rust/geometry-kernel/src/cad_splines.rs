// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! C1 encoding of Hermite chains. Removing each triple interior knot retains
//! the two adjacent tangent handles. Knot insertion reconstructs the join as
//! (1-alpha)*left_handle+alpha*right_handle. Only endpoint Bezier controls move;
//! positive Bernstein weights bound the entire change by their maximum motion.
use crate::precision::Result;
use crate::profiles::{Point, n};
use serde_json::{Value, json};

pub struct Chain<const D: usize> {
    pub points: Vec<[f64; D]>,
    pub mults: Vec<usize>,
    pub bound: f64,
}

pub fn compact<const D: usize>(points: &[[f64; D]], knots: &[f64]) -> Result<Chain<D>> {
    if knots.len() < 2
        || points.len() != 3 * (knots.len() - 1) + 1
        || knots
            .windows(2)
            .any(|k| !k[0].is_finite() || !k[1].is_finite() || k[1] <= k[0])
        || points.iter().flatten().any(|v| !v.is_finite())
    {
        return Err("Invalid cubic CAD chain.".into());
    }
    let mut bound: f64 = 0.;
    let mut out = vec![points[0]];
    for i in 0..knots.len() - 1 {
        crate::protocol::control_check()?;
        out.extend_from_slice(&points[3 * i + 1..3 * i + 3]);
        if i > 0 {
            let alpha = (knots[i] - knots[i - 1]) / (knots[i + 1] - knots[i - 1]);
            let squared = (0..D)
                .map(|d| {
                    let q = (1. - alpha) * points[3 * i - 1][d] + alpha * points[3 * i + 1][d];
                    (q - points[3 * i][d]).powi(2)
                })
                .sum::<f64>();
            bound = bound.max(squared.sqrt());
        }
    }
    out.push(*points.last().unwrap());
    let mut mults = vec![2; knots.len()];
    mults[0] = 4;
    *mults.last_mut().unwrap() = 4;
    Ok(Chain {
        points: out,
        mults,
        bound: bound * (1. + 64. * f64::EPSILON),
    })
}

pub fn groups(rows: &[Value]) -> Vec<(usize, usize)> {
    let mut out: Vec<(usize, usize)> = Vec::new();
    for (i, row) in rows.iter().enumerate() {
        let extend = out.last().is_some_and(|(first, _)| {
            row["kind"] == "cubic"
                && rows[*first]["kind"] == row["kind"]
                && rows[*first]["source"] == row["source"]
                && rows[*first]["mirror"] == row["mirror"]
                && rows[*first]["rotation_rad"] == row["rotation_rad"]
        });
        if extend {
            out.last_mut().unwrap().1 += 1;
        } else {
            out.push((i, 1));
        }
    }
    out
}

pub fn prepare_spur(mut profile: Value) -> Result<Value> {
    let rows = profile["curves"].as_array().unwrap();
    let mut patches = Vec::new();
    let mut bound: f64 = 0.;
    for (first, count) in groups(rows) {
        let group = &rows[first..first + count];
        let mut patch = json!({"first_curve":first,"curve_count":count});
        if group[0]["kind"] == "cubic" {
            let a = group[0]["domain"][0].as_f64().unwrap();
            let b = group.last().unwrap()["domain"][1].as_f64().unwrap();
            let mut points: Vec<Point> =
                vec![serde_json::from_value(group[0]["controls"][0].clone()).unwrap()];
            let mut knots = vec![0.];
            for row in group {
                let p: Vec<Point> = serde_json::from_value(row["controls"].clone()).unwrap();
                points.extend_from_slice(&p[1..]);
                knots.push((row["domain"][1].as_f64().unwrap() - a) / (b - a));
            }
            let chain = compact(&points, &knots)?;
            bound = bound.max(chain.bound);
            patch["poles"] = json!(chain.points);
            patch["knots"] = json!(knots);
            patch["multiplicities"] = json!(chain.mults);
            patch["c1_reconstruction_bound_mm"] = json!(chain.bound);
        }
        patches.push(patch);
    }
    let guard = n(&profile, "resolution_guard_mm", 0.)?;
    let total = n(&profile, "curve_interpolation_bound_mm", 0.)? + bound;
    if bound > guard || total + guard >= n(&profile, "requested_curve_mm", 0.)? {
        return Err("CAD C1 reconstruction exceeds the available curve error budget.".into());
    }
    profile["cad_patches"] = json!(patches);
    profile["c1_reconstruction_bound_mm"] = json!(bound);
    profile["curve_interpolation_bound_mm"] = json!(total);
    Ok(profile)
}

#[cfg(test)]
mod tests {
    use super::compact;
    #[test]
    fn nonuniform_join_is_reconstructed_with_a_measured_whole_curve_bound() {
        let points = [
            [0., 0.],
            [1., 0.],
            [2., 0.],
            [3.1, 0.],
            [5., 0.],
            [6., 0.],
            [7., 0.],
        ];
        let result = compact(&points, &[0., 1., 3.]).unwrap();
        assert_eq!(
            result.points,
            vec![
                points[0], points[1], points[2], points[4], points[5], points[6]
            ]
        );
        assert_eq!(result.mults, vec![4, 2, 4]);
        assert!((result.bound - 0.1).abs() < 1e-14);
    }
    #[test]
    fn invalid_chain_domains_and_nonfinite_controls_are_rejected() {
        assert!(compact(&[[0., 0.]; 4], &[0., 0.]).is_err());
        assert!(compact(&[[f64::NAN, 0.]; 4], &[0., 1.]).is_err());
        assert!(compact(&[[0., 0.]; 3], &[0., 1.]).is_err());
    }
}
