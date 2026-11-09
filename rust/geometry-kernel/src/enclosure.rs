// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Audit-only outward enclosures. No host-libm transcendental assumptions.
//! IEEE binary64 elementary operations are expanded one representable value
//! outwards. Trigonometry uses range reduction and finite Taylor remainders.
use crate::precision::Result;
use num_rational::BigRational;
use num_traits::ToPrimitive;
use serde_json::Value;
use std::ops::{Add, Div, Mul, Neg, Sub};
use std::sync::OnceLock;

// Adjacent IEEE values without raising the crate's minimum Rust version.
pub(crate) trait Outward {
    fn up(self) -> Self;
    fn down(self) -> Self;
}
impl Outward for f64 {
    fn up(self) -> Self {
        if self.is_nan() || self == f64::INFINITY {
            return self;
        }
        if self == 0. {
            return f64::from_bits(1);
        }
        f64::from_bits(if self > 0. {
            self.to_bits() + 1
        } else {
            self.to_bits() - 1
        })
    }
    fn down(self) -> Self {
        -(-self).up()
    }
}

#[derive(Clone, Copy, Debug)]
pub(crate) struct I {
    pub lo: f64,
    pub hi: f64,
}
impl I {
    pub const ZERO: Self = Self::point(0.);
    pub const ONE: Self = Self::point(1.);
    pub const fn point(x: f64) -> Self {
        Self { lo: x, hi: x }
    }
    pub fn range(lo: f64, hi: f64) -> Self {
        if !lo.is_finite() || !hi.is_finite() || lo > hi {
            Self::bad()
        } else {
            Self { lo, hi }
        }
    }
    fn bad() -> Self {
        Self::point(f64::NAN)
    }
    pub fn valid(self) -> bool {
        self.lo.is_finite() && self.hi.is_finite() && self.lo <= self.hi
    }
    pub fn checked(self) -> Result<Self> {
        if self.valid() {
            Ok(self)
        } else {
            Err("Total-error enclosure has an unresolved arithmetic domain".into())
        }
    }
    pub fn rational(q: &BigRational) -> Result<Self> {
        let x = q
            .to_f64()
            .filter(|x| x.is_finite())
            .ok_or("Exact source is outside finite interval arithmetic")?;
        let (mut lo, mut hi) = (x, x);
        for _ in 0..8 {
            if BigRational::from_float(lo).is_some_and(|v| v <= *q)
                && BigRational::from_float(hi).is_some_and(|v| v >= *q)
            {
                return Self::range(lo, hi).checked();
            }
            if BigRational::from_float(lo).is_none_or(|v| v > *q) {
                lo = lo.down();
            }
            if BigRational::from_float(hi).is_none_or(|v| v < *q) {
                hi = hi.up();
            }
        }
        Err("Could not enclose the exact rational source".into())
    }
    pub fn number(a: &Value, key: &str, default: &str) -> Result<Self> {
        let value = a
            .get(key)
            .cloned()
            .unwrap_or_else(|| Value::String(default.into()));
        Self::value(&value)
    }
    pub fn value(value: &Value) -> Result<Self> {
        let q = crate::exact::expression(value)?
            .ok_or("Total-error audit requires rational decimal input expressions")?;
        Self::rational(&q)
    }
    pub fn pi() -> Self {
        *static_pi().get_or_init(|| {
            fn atan(q: i32) -> (BigRational, BigRational) {
                let x = BigRational::new(1.into(), q.into());
                let xx = &x * &x;
                let mut term = x;
                let mut sum = BigRational::from_integer(0.into());
                for k in 0..80 {
                    let v = &term / BigRational::from_integer((2 * k + 1).into());
                    if k % 2 == 0 {
                        sum += v;
                    } else {
                        sum -= v;
                    }
                    term *= &xx;
                }
                // Even number of alternating terms: lower sum, next is positive.
                let upper = &sum + term / BigRational::from_integer(161.into());
                (sum, upper)
            }
            let (a, b) = atan(5);
            let (c, d) = atan(239);
            let sixteen = BigRational::from_integer(16.into());
            let four = BigRational::from_integer(4.into());
            let lo = Self::rational(&(&sixteen * a - &four * d)).unwrap().lo;
            let hi = Self::rational(&(sixteen * b - four * c)).unwrap().hi;
            Self::range(lo, hi)
        })
    }
    pub fn mid(self) -> f64 {
        self.lo / 2. + self.hi / 2.
    }
    pub fn magnitude(self) -> f64 {
        self.lo.abs().max(self.hi.abs())
    }
    pub fn square(self) -> Self {
        if !self.valid() {
            return Self::bad();
        }
        if self.lo == 0. && self.hi == 0. {
            return Self::ZERO;
        }
        let a = self.lo * self.lo;
        let b = self.hi * self.hi;
        let lo = if self.lo <= 0. && self.hi >= 0. {
            0.
        } else {
            a.min(b).down().max(0.)
        };
        Self::range(lo, a.max(b).up())
    }
    pub fn sqrt(self) -> Self {
        if !self.valid() || self.lo < 0. {
            return Self::bad();
        }
        if self.hi == 0. {
            return Self::ZERO;
        }
        Self::range(self.lo.sqrt().down().max(0.), self.hi.sqrt().up())
    }
    pub fn minimum(self, b: Self) -> Self {
        if !self.valid() || !b.valid() {
            return Self::bad();
        }
        Self::range(self.lo.min(b.lo), self.hi.min(b.hi))
    }
    fn point_trig(x: f64) -> (Self, Self) {
        if !x.is_finite() || x.abs() > 64. {
            return (Self::bad(), Self::bad());
        }
        let half_pi = Self::pi() / Self::point(2.);
        let k = (x / half_pi.mid()).round() as i32;
        let r = Self::point(x) - Self::point(k as f64) * half_pi;
        if r.magnitude() > 1. {
            return (Self::bad(), Self::bad());
        }
        let rr = r.square();
        let mut st = r;
        let mut ct = Self::ONE;
        let mut s = st;
        let mut c = ct;
        for k in 1..=16 {
            st = -st * rr / Self::point(((2 * k) * (2 * k + 1)) as f64);
            ct = -ct * rr / Self::point(((2 * k - 1) * (2 * k)) as f64);
            s = s + st;
            c = c + ct;
        }
        let se = (Self::point(st.magnitude()) * rr / Self::point(34. * 35.)).hi;
        let ce = (Self::point(ct.magnitude()) * rr / Self::point(33. * 34.)).hi;
        s = s + Self::range(-se, se);
        c = c + Self::range(-ce, ce);
        match k.rem_euclid(4) {
            0 => (s, c),
            1 => (c, -s),
            2 => (-s, -c),
            _ => (-c, s),
        }
    }
    pub fn trig(self) -> (Self, Self) {
        if !self.valid() {
            return (Self::bad(), Self::bad());
        }
        let m = self.mid();
        let (s, c) = Self::point_trig(m);
        let radius = (self - Self::point(m)).magnitude();
        let widen = |x: Self| {
            let y = x + Self::range(-radius, radius);
            Self::range(y.lo.max(-1.), y.hi.min(1.))
        };
        (widen(s), widen(c))
    }
    pub fn sin(self) -> Self {
        self.trig().0
    }
    pub fn cos(self) -> Self {
        self.trig().1
    }
    pub fn tan(self) -> Self {
        let (s, c) = self.trig();
        s / c
    }
    fn small_atan(x: Self) -> Self {
        let xx = x.square();
        let mut term = x;
        let mut sum = term;
        for k in 1..40 {
            term = -term * xx;
            sum = sum + term / Self::point((2 * k + 1) as f64);
        }
        let rem = (Self::point(term.magnitude()) * xx / Self::point(81.)).hi;
        sum + Self::range(-rem, rem)
    }
    fn point_atan(x: f64) -> Self {
        if !x.is_finite() {
            return Self::bad();
        }
        if x < 0. {
            return -Self::point_atan(-x);
        }
        if x > 1. {
            return Self::pi() / Self::point(2.)
                - Self::small_atan_reduced(Self::ONE / Self::point(x));
        }
        Self::small_atan_reduced(Self::point(x))
    }
    fn small_atan_reduced(x: Self) -> Self {
        if x.hi <= 0.5 {
            Self::small_atan(x)
        } else {
            Self::point(2.) * Self::small_atan(x / (Self::ONE + (Self::ONE + x.square()).sqrt()))
        }
    }
    pub fn atan(self) -> Self {
        if !self.valid() {
            return Self::bad();
        }
        Self::range(Self::point_atan(self.lo).lo, Self::point_atan(self.hi).hi)
    }
}
fn static_pi() -> &'static OnceLock<I> {
    static PI: OnceLock<I> = OnceLock::new();
    &PI
}
pub(crate) fn environment() -> Result<()> {
    let small = std::hint::black_box(f64::MIN_POSITIVE);
    let factor = std::hint::black_box(0.5);
    if small * factor == 0.
        || (std::hint::black_box(f64::from_bits(1)) + std::hint::black_box(f64::from_bits(1)))
            .to_bits()
            != 2
    {
        return Err("Total-error enclosures require IEEE gradual underflow".into());
    }
    Ok(())
}
pub(crate) fn numeric(a: &Value) -> Result<Value> {
    environment()?;
    fn operand(v: &Value) -> Result<I> {
        if let Some(rows) = v.as_array() {
            if rows.len() != 2 {
                return Err("An enclosure requires two ordered endpoints".into());
            }
            let lower =
                crate::exact::expression(&rows[0])?.ok_or("Rational interval endpoint required")?;
            let upper =
                crate::exact::expression(&rows[1])?.ok_or("Rational interval endpoint required")?;
            if lower > upper {
                return Err("Reversed exact interval endpoints".into());
            }
            return I::range(I::value(&rows[0])?.lo, I::value(&rows[1])?.hi).checked();
        }
        I::value(v)
    }
    let x = operand(&a["a"])?;
    let y = match a["function"].as_str() {
        Some("sin") => x.sin(),
        Some("cos") => x.cos(),
        Some("atan") => x.atan(),
        Some("sqrt") => x.sqrt(),
        Some("add") => x + operand(&a["b"])?,
        Some("sub") => x - operand(&a["b"])?,
        Some("mul") => x * operand(&a["b"])?,
        Some("div") => x / operand(&a["b"])?,
        _ => return Err("Unsupported outward-enclosure function".into()),
    }
    .checked()?;
    Ok(
        serde_json::json!({"lower":y.lo,"upper":y.hi,"arithmetic":"outward binary64 enclosure, explicit Taylor remainder for trigonometry"}),
    )
}
impl Add for I {
    type Output = Self;
    fn add(self, b: Self) -> Self {
        if !self.valid() || !b.valid() {
            return Self::bad();
        }
        if self.lo == 0. && self.hi == 0. {
            return b;
        }
        if b.lo == 0. && b.hi == 0. {
            return self;
        }
        Self::range((self.lo + b.lo).down(), (self.hi + b.hi).up())
    }
}
impl Neg for I {
    type Output = Self;
    fn neg(self) -> Self {
        Self {
            lo: -self.hi,
            hi: -self.lo,
        }
    }
}
impl Sub for I {
    type Output = Self;
    fn sub(self, b: Self) -> Self {
        self + (-b)
    }
}
impl Mul for I {
    type Output = Self;
    fn mul(self, b: Self) -> Self {
        if !self.valid() || !b.valid() {
            return Self::bad();
        }
        if self.lo == 0. && self.hi == 0. || b.lo == 0. && b.hi == 0. {
            return Self::ZERO;
        }
        let v = [
            self.lo * b.lo,
            self.lo * b.hi,
            self.hi * b.lo,
            self.hi * b.hi,
        ];
        let lo = v.iter().copied().fold(f64::INFINITY, f64::min).down();
        let hi = v.iter().copied().fold(f64::NEG_INFINITY, f64::max).up();
        Self::range(lo, hi)
    }
}
impl Div for I {
    type Output = Self;
    fn div(self, b: Self) -> Self {
        if !self.valid() || !b.valid() || b.lo <= 0. && b.hi >= 0. {
            return Self::bad();
        }
        if self.lo == 0. && self.hi == 0. {
            return Self::ZERO;
        }
        let values = [
            self.lo / b.lo,
            self.lo / b.hi,
            self.hi / b.lo,
            self.hi / b.hi,
        ];
        Self::range(
            values.iter().copied().fold(f64::INFINITY, f64::min).down(),
            values
                .iter()
                .copied()
                .fold(f64::NEG_INFINITY, f64::max)
                .up(),
        )
    }
}

#[derive(Clone, Copy, Debug)]
pub(crate) struct J {
    pub v: I,
    pub d: I,
    pub dd: I,
}
impl From<I> for J {
    fn from(v: I) -> Self {
        Self {
            v,
            d: I::ZERO,
            dd: I::ZERO,
        }
    }
}
impl J {
    pub fn variable(lo: f64, hi: f64) -> Self {
        Self {
            v: I::range(lo, hi),
            d: I::ONE,
            dd: I::ZERO,
        }
    }
    pub fn sin(self) -> Self {
        let (s, c) = self.v.trig();
        Self {
            v: s,
            d: c * self.d,
            dd: c * self.dd - s * self.d.square(),
        }
    }
    pub fn cos(self) -> Self {
        let (s, c) = self.v.trig();
        Self {
            v: c,
            d: -s * self.d,
            dd: -s * self.dd - c * self.d.square(),
        }
    }
    fn reciprocal(self) -> Self {
        let v = I::ONE / self.v;
        Self {
            v,
            d: -self.d * v.square(),
            dd: I::point(2.) * self.d.square() * v * v.square() - self.dd * v.square(),
        }
    }
    pub fn sqrt(self) -> Self {
        let v = self.v.sqrt();
        let derivative = I::ONE / (I::point(2.) * v);
        Self {
            v,
            d: derivative * self.d,
            dd: derivative * self.dd - self.d.square() / (I::point(4.) * v * v.square()),
        }
    }
    pub fn atan(self) -> Self {
        let den = I::ONE + self.v.square();
        Self {
            v: self.v.atan(),
            d: self.d / den,
            dd: self.dd / den - I::point(2.) * self.v * self.d.square() / den.square(),
        }
    }
}
impl Add for J {
    type Output = Self;
    fn add(self, b: Self) -> Self {
        Self {
            v: self.v + b.v,
            d: self.d + b.d,
            dd: self.dd + b.dd,
        }
    }
}
impl Neg for J {
    type Output = Self;
    fn neg(self) -> Self {
        Self {
            v: -self.v,
            d: -self.d,
            dd: -self.dd,
        }
    }
}
impl Sub for J {
    type Output = Self;
    fn sub(self, b: Self) -> Self {
        self + (-b)
    }
}
impl Mul for J {
    type Output = Self;
    fn mul(self, b: Self) -> Self {
        Self {
            v: self.v * b.v,
            d: self.d * b.v + self.v * b.d,
            dd: self.dd * b.v + I::point(2.) * self.d * b.d + self.v * b.dd,
        }
    }
}
#[allow(
    clippy::suspicious_arithmetic_impl,
    reason = "Second-order interval division is multiplication by the differentiated reciprocal"
)]
impl Div for J {
    type Output = Self;
    fn div(self, b: Self) -> Self {
        self * b.reciprocal()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn exact_rational_endpoints_and_subnormals() {
        for text in ["0.1", "2.00000000000000000001", "1e-320", "-1e-320"] {
            let v = serde_json::json!({"x":text});
            let q = crate::exact::expression(&v["x"]).unwrap().unwrap();
            let b = I::number(&v, "x", "0").unwrap();
            assert!(
                BigRational::from_float(b.lo).unwrap() <= q
                    && BigRational::from_float(b.hi).unwrap() >= q
            );
        }
        assert!(!(I::ONE / I::range(-1., 1.)).valid());
        assert!((I::point(f64::from_bits(1)) * I::point(0.5)).hi > 0.);
    }
    #[test]
    fn elementary_and_derivative_enclosures() {
        let p = I::pi();
        assert!(p.lo <= std::f64::consts::PI && p.hi > std::f64::consts::PI);
        for x in [-6., -1., -0.2, 0., 0.7, 1.5, 6.] {
            let i = I::point(x);
            let (s, c) = i.trig();
            assert!(s.lo <= x.sin() && s.hi >= x.sin());
            assert!(c.lo <= x.cos() && c.hi >= x.cos());
            let a = i.atan();
            assert!(a.lo <= x.atan() && a.hi >= x.atan());
            let j = J::variable(x, x).sin();
            assert!(j.d.lo <= x.cos() && j.d.hi >= x.cos());
            assert!(j.dd.lo <= -x.sin() && j.dd.hi >= -x.sin());
        }
        let q = I::range(-2., 3.).square();
        assert_eq!(q.lo, 0.);
        assert!(q.hi >= 9.);
    }
}
