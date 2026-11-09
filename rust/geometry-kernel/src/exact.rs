// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Bounded exact rational arithmetic for decimal sources and rational formulae.
//! Round once, by quotient/remainder, including exact halfway decimal cases.
use crate::precision::Result;
use num_bigint::BigInt;
use num_rational::BigRational;
use num_traits::{One, Signed, ToPrimitive, Zero};
use serde_json::Value;

pub type Rational = BigRational;
const MAX_BITS: u64 = 65_536;

fn bounded(r: Rational) -> Result<Rational> {
    if r.numer().bits() > MAX_BITS || r.denom().bits() > MAX_BITS {
        return Err("Exact numeric expression exceeds its integer resource limit".into());
    }
    Ok(r)
}

fn decimal(s: &str) -> Result<Rational> {
    if s.is_empty() || s.len() > 512 || s.trim() != s {
        return Err("Invalid decimal spelling or input length".into());
    }
    let (mantissa, exponent) = match s.split_once(['e', 'E']) {
        Some((m, e)) => (m, e.parse::<i32>().map_err(|_| "Invalid decimal exponent")?),
        None => (s, 0),
    };
    if !(-4096..=4096).contains(&exponent) {
        return Err("Decimal exponent exceeds the numerical input domain".into());
    }
    let negative = mantissa.starts_with('-');
    let unsigned = mantissa.strip_prefix(['-', '+']).unwrap_or(mantissa);
    let mut digits = String::new();
    let mut dot = false;
    let mut scale = -exponent;
    for b in unsigned.bytes() {
        if b == b'.' && !dot {
            dot = true;
        } else if b.is_ascii_digit() {
            digits.push(b as char);
            if dot {
                scale += 1;
            }
        } else {
            return Err("Invalid decimal spelling".into());
        }
    }
    let mut n = BigInt::parse_bytes(digits.as_bytes(), 10).ok_or("Invalid decimal digits")?;
    if negative {
        n = -n;
    }
    let ten = BigInt::from(10);
    bounded(if scale >= 0 {
        Rational::new(n, ten.pow(scale as u32))
    } else {
        Rational::from_integer(n * ten.pow((-scale) as u32))
    })
}

/// None denotes a nonrational operation (a fractional power); never a bad input.
pub fn expression(v: &Value) -> Result<Option<Rational>> {
    fn eval(v: &Value, depth: usize, count: &mut usize) -> Result<Option<Rational>> {
        *count += 1;
        if depth > 64 || *count > 4096 {
            return Err("Numeric expression exceeds its bounded size".into());
        }
        match v {
            Value::String(s) => Ok(Some(decimal(s)?)),
            Value::Number(n) => Ok(Some(decimal(&n.to_string())?)),
            Value::Object(o) if o.len() == 1 && o.contains_key("expression") => {
                let row = o["expression"]
                    .as_array()
                    .ok_or("Invalid numeric expression")?;
                let op = row
                    .first()
                    .and_then(Value::as_str)
                    .ok_or("Numeric operation required")?;
                if op == "neg" && row.len() == 2 {
                    return Ok(eval(&row[1], depth + 1, count)?.map(|r| -r));
                }
                if row.len() != 3 || !["add", "sub", "mul", "div", "pow"].contains(&op) {
                    return Err("Invalid numeric expression operation or arity".into());
                }
                let a = eval(&row[1], depth + 1, count)?;
                let b = eval(&row[2], depth + 1, count)?;
                let (Some(mut a), Some(mut b)) = (a, b) else {
                    return Ok(None);
                };
                let r = match op {
                    "add" => a + b,
                    "sub" => a - b,
                    "mul" => a * b,
                    "div" => {
                        if b.is_zero() {
                            return Err("Zero rational denominator".into());
                        }
                        a / b
                    }
                    "pow" => {
                        if !b.is_integer() {
                            // Perfect rational roots stay exact too. Routing
                            // 4^(1/2) through ln/exp can keep refining a result
                            // exactly on a binary rounding boundary forever.
                            let Some(degree) = b.denom().to_u32().filter(|d| *d <= 4096) else {
                                return Ok(None);
                            };
                            if a.is_negative() {
                                return Ok(None);
                            }
                            let nr = a.numer().nth_root(degree);
                            let dr = a.denom().nth_root(degree);
                            if nr.pow(degree) != *a.numer() || dr.pow(degree) != *a.denom() {
                                return Ok(None);
                            }
                            a = Rational::new(nr, dr);
                            b = Rational::from_integer(b.numer().clone());
                        }
                        let e = b
                            .to_integer()
                            .to_i32()
                            .ok_or("Numeric power exceeds its bound")?;
                        let size = a.numer().bits().max(a.denom().bits());
                        if e.unsigned_abs() > 4096
                            || size.saturating_mul(e.unsigned_abs() as u64) > MAX_BITS
                        {
                            return Err("Numeric power exceeds its bound".into());
                        }
                        if a.is_zero() && e < 0 {
                            return Err("Zero rational denominator".into());
                        }
                        a.pow(e)
                    }
                    _ => unreachable!(),
                };
                Ok(Some(bounded(r)?))
            }
            _ => Err("A finite decimal number or numeric expression is required".into()),
        }
    }
    eval(v, 0, &mut 0)
}

pub fn number(a: &Value, key: &str, default: Option<&str>) -> Result<Option<Rational>> {
    match a.get(key) {
        Some(v) => expression(v),
        None => expression(&Value::String(
            default
                .ok_or_else(|| format!("Missing numeric parameter: {key}"))?
                .into(),
        )),
    }
}

pub fn integer(n: i64) -> Rational {
    Rational::from_integer(n.into())
}

pub fn fixed(r: &Rational, places: usize) -> Result<String> {
    if places > 256 {
        return Err("Decimal output exceeds its bound".into());
    }
    let n = r.numer().abs() * BigInt::from(10).pow(places as u32);
    let d = r.denom();
    let mut q = &n / d;
    let remainder = n % d;
    let twice = remainder * 2;
    if twice > *d || twice == *d && (&q % 2u8) == BigInt::one() {
        q += 1;
    }
    let mut text = q.to_str_radix(10);
    if text.len() > 4096 {
        return Err("Decimal output exceeds its bound".into());
    }
    if text.len() <= places {
        text = "0".repeat(places + 1 - text.len()) + &text;
    }
    if places > 0 {
        text.insert(text.len() - places, '.');
    }
    if r.is_negative() && !q.is_zero() {
        text.insert(0, '-');
    }
    Ok(text)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    #[test]
    fn exact_ties_signs_cancellation_and_nonterminating_division() {
        for (input, expected) in [
            ("2.625000000000000000875", "2.62500000000000000088"),
            ("87.900000000000000007325", "87.90000000000000000732"),
            ("-2.625000000000000000875", "-2.62500000000000000088"),
            ("-5e-21", "0.00000000000000000000"),
        ] {
            assert_eq!(fixed(&decimal(input).unwrap(), 20).unwrap(), expected);
        }
        let v = json!({"expression":["sub",{"expression":["add","1e200","2.00000000000000000001"]},"1e200"]});
        assert_eq!(
            fixed(&expression(&v).unwrap().unwrap(), 20).unwrap(),
            "2.00000000000000000001"
        );
        assert_eq!(
            fixed(&(integer(1) / integer(3)), 20).unwrap(),
            "0.33333333333333333333"
        );
        assert!(expression(&json!({"expression":["div",1,0]})).is_err());
        assert_eq!(
            expression(&json!({"expression":["pow",4,"0.5"]})).unwrap(),
            Some(integer(2))
        );
        assert!(expression(&json!({"expression":["pow",10,4096]})).is_ok());
        assert!(expression(&json!({"expression":["pow","1e4096",4096]})).is_err());
    }
}
