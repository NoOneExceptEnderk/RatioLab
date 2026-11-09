// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Column-major nominal poses: radians, world millimetres, Rodrigues rotation.
use crate::precision::Result;
use crate::profiles::n;
use serde::Deserialize;
use serde_json::{Value, json};
type P = [f64; 3];
type M = [f64; 16];
const IDENTITY: M = [
    1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1.,
];
fn bounded_coordinate(value: f64, limits: Option<[f64; 2]>) -> Result<f64> {
    if !value.is_finite() {
        return Err("Finite pose coordinate required".into());
    }
    if let Some([low, high]) = limits {
        if !low.is_finite() || !high.is_finite() || low > high {
            return Err("Invalid finite pose limits".into());
        }
        if value < low - 1e-9 || value > high + 1e-9 {
            return Err("Rack pose exceeds the finite working stroke.".into());
        }
        Ok(value.clamp(low, high))
    } else {
        Ok(value)
    }
}
fn read<X: serde::de::DeserializeOwned>(a: &Value, key: &str) -> Result<X> {
    serde_json::from_value(a[key].clone()).map_err(|_| format!("Invalid affine {key}"))
}
fn multiply(a: M, b: M) -> M {
    std::array::from_fn(|i| {
        let c = i / 4;
        let r = i % 4;
        (0..4).map(|k| a[4 * k + r] * b[4 * c + k]).sum()
    })
}
fn rotation(angle: f64, axis: P, pivot: P) -> Result<M> {
    let length = axis.iter().map(|x| x * x).sum::<f64>().sqrt();
    if !length.is_finite() || length == 0. {
        return Err("Rotation requires a finite nonzero axis".into());
    }
    let [x, y, z] = axis.map(|v| v / length);
    let c = angle.cos();
    let s = angle.sin();
    let k = 1. - c;
    let rows = [
        [c + x * x * k, x * y * k - z * s, x * z * k + y * s],
        [y * x * k + z * s, c + y * y * k, y * z * k - x * s],
        [z * x * k - y * s, z * y * k + x * s, c + z * z * k],
    ];
    let shift: P =
        std::array::from_fn(|i| pivot[i] - (0..3).map(|j| rows[i][j] * pivot[j]).sum::<f64>());
    Ok(std::array::from_fn(|i| {
        let r = i % 4;
        let col = i / 4;
        if r < 3 && col < 3 {
            rows[r][col]
        } else if col == 3 && r < 3 {
            shift[r]
        } else if r == 3 && col == 3 {
            1.
        } else {
            0.
        }
    }))
}
pub(crate) fn transform(m: M, p: P) -> P {
    std::array::from_fn(|i| (0..3).map(|j| m[4 * j + i] * p[j]).sum::<f64>() + m[12 + i])
}

#[derive(Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
enum Pose {
    Rotation {
        rate: f64,
        offset: f64,
        axis: P,
        pivot: P,
        #[serde(default)]
        limits: Option<[f64; 2]>,
    },
    Linear {
        rate: f64,
        offset: f64,
        scale: f64,
        axis: P,
        limits: [f64; 2],
    },
    Orbital {
        spin_rate: f64,
        spin_offset: f64,
        orbit_rate: f64,
        orbit_offset: f64,
        center: [f64; 2],
    },
    Differential {
        carrier_rate: f64,
        carrier_offset: f64,
        spin_rate: f64,
        spin_offset: f64,
    },
}
impl Pose {
    fn matrix(&self, phase: f64) -> Result<M> {
        let result = match *self {
            Pose::Rotation {
                rate,
                offset,
                axis,
                pivot,
                limits,
            } => {
                let theta = bounded_coordinate(rate * phase + offset, limits)?;
                rotation(theta, axis, pivot)?
            }
            Pose::Linear {
                rate,
                offset,
                scale,
                axis,
                limits,
            } => {
                if !scale.is_finite() || !axis.iter().all(|n| n.is_finite()) {
                    return Err("Invalid linear pose".into());
                }
                let distance = bounded_coordinate(rate * phase + offset, Some(limits))? * scale;
                let mut m = IDENTITY;
                for i in 0..3 {
                    m[12 + i] = axis[i] * distance;
                }
                m
            }
            Pose::Orbital {
                spin_rate,
                spin_offset,
                orbit_rate,
                orbit_offset,
                center: [x, y],
            } => {
                let orbit = orbit_rate * phase + orbit_offset;
                let mut shift = IDENTITY;
                shift[12] = x * orbit.cos() - y * orbit.sin() - x;
                shift[13] = x * orbit.sin() + y * orbit.cos() - y;
                multiply(
                    shift,
                    rotation(spin_rate * phase + spin_offset, [0., 0., 1.], [x, y, 0.])?,
                )
            }
            Pose::Differential {
                carrier_rate,
                carrier_offset,
                spin_rate,
                spin_offset,
            } => multiply(
                rotation(carrier_rate * phase + carrier_offset, [1., 0., 0.], [0.; 3])?,
                rotation(spin_rate * phase + spin_offset, [0., 0., 1.], [0.; 3])?,
            ),
        };
        if result.iter().any(|x| !x.is_finite()) {
            return Err("Nonfinite pose coordinates".into());
        }
        Ok(result)
    }
}

pub fn poses(a: &Value) -> Result<Vec<M>> {
    let phase = n(a, "phase", 0.)?;
    let rows = a["poses"].as_array().ok_or("Pose array required")?;
    if rows.len() > 10_000 {
        return Err("Pose batch exceeds its resource limit".into());
    }
    rows.iter()
        .map(|row| {
            crate::protocol::control_check()?;
            Pose::deserialize(row)
                .map_err(|e| e.to_string())?
                .matrix(phase)
        })
        .collect()
}

pub fn call(op: &str, a: &Value) -> Result<Value> {
    Ok(match op {
        "affine_poses" => json!(poses(a)?),
        "affine_multiply" => json!(multiply(read(a, "a")?, read(a, "b")?)),
        "affine_rotation" => json!(rotation(
            n(a, "angle", 0.)?,
            read(a, "axis")?,
            read(a, "pivot")?
        )?),
        "affine_transform" => {
            let m: M = read(a, "matrix")?;
            let points: Vec<P> = read(a, "points")?;
            if points.len() > 1_000_000
                || m.iter().any(|x| !x.is_finite())
                || points.iter().flatten().any(|x| !x.is_finite())
            {
                return Err("Invalid affine coordinates or resource limit".into());
            }
            let mut result = Vec::with_capacity(points.len());
            for (i, p) in points.into_iter().enumerate() {
                if i % 128 == 0 {
                    crate::protocol::control_check()?;
                }
                result.push(transform(m, p));
            }
            json!(result)
        }
        "affine_orbital" => {
            let center: [f64; 2] = read(a, "center")?;
            let [x, y] = center;
            let orbit = n(a, "orbit", 0.)?;
            let mut shift = IDENTITY;
            shift[12] = x * orbit.cos() - y * orbit.sin() - x;
            shift[13] = x * orbit.sin() + y * orbit.cos() - y;
            json!(multiply(
                shift,
                rotation(n(a, "spin", 0.)?, [0., 0., 1.], [x, y, 0.])?
            ))
        }
        _ => return Err(format!("Unknown affine operation {op}")),
    })
}
