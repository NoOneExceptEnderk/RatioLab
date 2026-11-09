// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Numerical, outward-expanded binary64/libm construction checks. These retain
//! the existing generator semantics, not the rigorous transcendental audit in
//! enclosure.rs. An unresolved operation poisons the cell; it cannot be accepted.
use crate::enclosure::Outward;
use serde::Serialize;
use std::f64::consts::FRAC_PI_2;
use std::ops::{Add, Div, Mul, Neg, Sub};

#[derive(Clone, Copy, Debug, Serialize)]
pub(crate) struct I {
    pub lo: f64,
    pub hi: f64,
}
impl I {
    pub fn new(lo: f64, hi: f64) -> Self {
        Self { lo, hi }
    }
    pub fn valid(self) -> bool {
        self.lo.is_finite() && self.hi.is_finite() && self.lo <= self.hi
    }
    fn bad() -> Self {
        Self::new(f64::NAN, f64::NAN)
    }
    pub fn square(self) -> Self {
        if !self.valid() {
            return Self::bad();
        }
        let (a, b) = (self.lo * self.lo, self.hi * self.hi);
        Self::new(
            if self.lo <= 0. && self.hi >= 0. {
                0.
            } else {
                a.min(b).down().max(0.)
            },
            a.max(b).up(),
        )
    }
    pub fn sqrt(self) -> Self {
        if !self.valid() || self.lo <= 0. {
            return Self::bad();
        }
        Self::new(self.lo.sqrt().down(), self.hi.sqrt().up())
    }
    pub fn sin(self) -> Self {
        if !self.valid() || self.lo <= -FRAC_PI_2 || self.hi >= FRAC_PI_2 {
            return Self::bad();
        }
        Self::new(self.lo.sin().down(), self.hi.sin().up())
    }
    pub fn cos(self) -> Self {
        if !self.valid() || self.lo <= -FRAC_PI_2 || self.hi >= FRAC_PI_2 {
            return Self::bad();
        }
        let (a, b) = (self.lo.cos(), self.hi.cos());
        Self::new(
            a.min(b).down(),
            if self.lo <= 0. && self.hi >= 0. {
                1_f64.up()
            } else {
                a.max(b).up()
            },
        )
    }
    pub fn acos(self) -> Self {
        if !self.valid() || self.lo <= -1. || self.hi >= 1. {
            return Self::bad();
        }
        Self::new(self.hi.acos().down(), self.lo.acos().up())
    }
    pub fn atan(self) -> Self {
        if !self.valid() {
            return Self::bad();
        }
        Self::new(self.lo.atan().down(), self.hi.atan().up())
    }
    pub fn abs_upper(self) -> f64 {
        self.lo.abs().max(self.hi.abs())
    }
}
impl From<f64> for I {
    fn from(x: f64) -> Self {
        Self::new(x, x)
    }
}
impl Add for I {
    type Output = Self;
    fn add(self, b: Self) -> Self {
        if !self.valid() || !b.valid() {
            return Self::bad();
        }
        Self::new((self.lo + b.lo).down(), (self.hi + b.hi).up())
    }
}
impl Neg for I {
    type Output = Self;
    fn neg(self) -> Self {
        Self::new(-self.hi, -self.lo)
    }
}
impl Sub for I {
    type Output = Self;
    fn sub(self, b: Self) -> Self {
        self + -b
    }
}
impl Mul for I {
    type Output = Self;
    fn mul(self, b: Self) -> Self {
        if !self.valid() || !b.valid() {
            return Self::bad();
        }
        let v = [
            self.lo * b.lo,
            self.lo * b.hi,
            self.hi * b.lo,
            self.hi * b.hi,
        ];
        Self::new(
            v.into_iter().fold(f64::INFINITY, f64::min).down(),
            v.into_iter().fold(f64::NEG_INFINITY, f64::max).up(),
        )
    }
}
impl Div for I {
    type Output = Self;
    fn div(self, b: Self) -> Self {
        if !b.valid() || b.lo <= 0. && b.hi >= 0. {
            return Self::bad();
        }
        self * Self::new((1. / b.hi).down(), (1. / b.lo).up())
    }
}
macro_rules! scalar_ops {
    ($t:ty) => {
        impl Add<f64> for $t {
            type Output = Self;
            fn add(self, b: f64) -> Self {
                self + Self::from(b)
            }
        }
        impl Add<$t> for f64 {
            type Output = $t;
            fn add(self, b: $t) -> $t {
                <$t>::from(self) + b
            }
        }
        impl Sub<f64> for $t {
            type Output = Self;
            fn sub(self, b: f64) -> Self {
                self - Self::from(b)
            }
        }
        impl Sub<$t> for f64 {
            type Output = $t;
            fn sub(self, b: $t) -> $t {
                <$t>::from(self) - b
            }
        }
        impl Mul<f64> for $t {
            type Output = Self;
            fn mul(self, b: f64) -> Self {
                self * Self::from(b)
            }
        }
        impl Mul<$t> for f64 {
            type Output = $t;
            fn mul(self, b: $t) -> $t {
                <$t>::from(self) * b
            }
        }
        impl Div<f64> for $t {
            type Output = Self;
            fn div(self, b: f64) -> Self {
                self / Self::from(b)
            }
        }
        impl Div<$t> for f64 {
            type Output = $t;
            fn div(self, b: $t) -> $t {
                <$t>::from(self) / b
            }
        }
    };
}
scalar_ops!(I);

#[derive(Clone, Copy, Debug, Serialize)]
pub(crate) struct Jet {
    pub v: I,
    pub d: I,
}
impl Jet {
    pub fn new(v: I, d: I) -> Self {
        Self { v, d }
    }
    pub fn square(self) -> Self {
        Self::new(self.v.square(), 2. * self.v * self.d)
    }
    pub fn sqrt(self) -> Self {
        let v = self.v.sqrt();
        Self::new(v, self.d / (2. * v))
    }
    pub fn sin(self) -> Self {
        Self::new(self.v.sin(), self.v.cos() * self.d)
    }
    pub fn cos(self) -> Self {
        Self::new(self.v.cos(), -self.v.sin() * self.d)
    }
    pub fn acos(self) -> Self {
        Self::new(self.v.acos(), -self.d / (1. - self.v.square()).sqrt())
    }
    pub fn atan(self) -> Self {
        Self::new(self.v.atan(), self.d / (1. + self.v.square()))
    }
    pub fn valid(self) -> bool {
        self.v.valid() && self.d.valid()
    }
}
impl From<f64> for Jet {
    fn from(x: f64) -> Self {
        Self::new(x.into(), 0_f64.into())
    }
}
impl From<I> for Jet {
    fn from(x: I) -> Self {
        Self::new(x, 0_f64.into())
    }
}
impl Neg for Jet {
    type Output = Self;
    fn neg(self) -> Self {
        Self::new(-self.v, -self.d)
    }
}
impl Add for Jet {
    type Output = Self;
    fn add(self, b: Self) -> Self {
        Self::new(self.v + b.v, self.d + b.d)
    }
}
impl Sub for Jet {
    type Output = Self;
    fn sub(self, b: Self) -> Self {
        self + -b
    }
}
impl Mul for Jet {
    type Output = Self;
    fn mul(self, b: Self) -> Self {
        Self::new(self.v * b.v, self.d * b.v + self.v * b.d)
    }
}
impl Div for Jet {
    type Output = Self;
    fn div(self, b: Self) -> Self {
        Self::new(self.v / b.v, (self.d * b.v - self.v * b.d) / b.v.square())
    }
}
scalar_ops!(Jet);

pub fn call(a: &serde_json::Value) -> crate::precision::Result<serde_json::Value> {
    use serde_json::{Value, json};
    let read = |v: &Value| -> crate::precision::Result<I> {
        let lo = crate::profiles::n(v, "lo", f64::NAN)?;
        let hi = crate::profiles::n(v, "hi", lo)?;
        let i = I::new(lo, hi);
        if !i.valid() {
            return Err("Invalid construction interval".into());
        }
        Ok(i)
    };
    let op = a["action"].as_str().ok_or("Missing enclosure action")?;
    if a["jet"] == true {
        let r = |v: &Value| -> crate::precision::Result<Jet> {
            Ok(Jet::new(read(&v["v"])?, read(&v["d"])?))
        };
        let x = r(&a["lhs"])?;
        let b = if a["rhs"].is_null() {
            Jet::from(0.)
        } else {
            r(&a["rhs"])?
        };
        let y = match op {
            "add" => x + b,
            "sub" => x - b,
            "mul" => x * b,
            "div" => x / b,
            "neg" => -x,
            "square" => x.square(),
            "sqrt" => x.sqrt(),
            "sin" => x.sin(),
            "cos" => x.cos(),
            "acos" => x.acos(),
            "atan" => x.atan(),
            _ => return Err("Unknown enclosure action".into()),
        };
        if !y.valid() {
            return Err("Unresolved construction interval branch or denominator".into());
        }
        Ok(json!(y))
    } else {
        let x = read(&a["lhs"])?;
        let b = if a["rhs"].is_null() {
            I::from(0.)
        } else {
            read(&a["rhs"])?
        };
        let y = match op {
            "add" => x + b,
            "sub" => x - b,
            "mul" => x * b,
            "div" => x / b,
            "neg" => -x,
            "square" => x.square(),
            "sqrt" => x.sqrt(),
            "sin" => x.sin(),
            "cos" => x.cos(),
            "acos" => x.acos(),
            "atan" => x.atan(),
            _ => return Err("Unknown enclosure action".into()),
        };
        if !y.valid() {
            return Err("Unresolved construction interval branch or denominator".into());
        }
        Ok(json!(y))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn unresolved_cells_cannot_become_finite_through_min_or_multiply() {
        for bad in [
            I::new(-1., 1.).sqrt(),
            I::from(1.) / I::new(-1., 1.),
            I::new(1., 2.).acos(),
        ] {
            assert!(!bad.valid());
            assert!(!(bad * 0. + 1.).valid());
            assert!(!bad.square().valid());
        }
    }
    #[test]
    fn zero_crossing_and_jet_enclose_independent_derivatives() {
        let x = Jet::new(I::new(-0.1, 0.2), I::from(1.));
        let y = x.sin() * x.square();
        for t in [-0.1_f64, 0., 0.2] {
            let v = t.sin() * t * t;
            let d = t.cos() * t * t + 2. * t * t.sin();
            assert!(y.v.lo <= v && v <= y.v.hi);
            assert!(y.d.lo <= d && d <= y.d.hi);
        }
    }
}
