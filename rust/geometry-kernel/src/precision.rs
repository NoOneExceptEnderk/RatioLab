// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
use astro_float::{BigFloat, Consts, Radix, RoundingMode, ctx::Context};
use serde_json::Value;

pub const BITS: usize = 256;
pub const CHECK_BITS: usize = 512;
pub const DECIMAL_PLACES: usize = 20;
pub type Result<T> = std::result::Result<T, String>;

pub fn context(bits: usize) -> Result<Context> {
    Ok(Context::new(
        bits,
        RoundingMode::ToEven,
        Consts::new().map_err(|e| format!("Constants allocation failed: {e:?}"))?,
        -16384,
        16384,
    ))
}

pub fn number(args: &Value, key: &str, default: Option<&str>, bits: usize) -> Result<BigFloat> {
    let value = match args.get(key) {
        Some(value) => value.clone(),
        None => Value::String(
            default
                .ok_or_else(|| format!("Missing numeric parameter: {key}"))?
                .into(),
        ),
    };
    expression(&value, bits).map_err(|e| format!("{key}: {e}"))
}

fn rational_binary(r: &crate::exact::Rational, bits: usize) -> Result<BigFloat> {
    // Source spelling is bounded by exact::expression; expanded integers
    // can legitimately exceed the 512-character *input* spelling limit.
    let mut cc = Consts::new().map_err(|e| format!("Constants allocation failed: {e:?}"))?;
    let n = BigFloat::parse(
        &r.numer().to_string(),
        Radix::Dec,
        bits,
        RoundingMode::ToEven,
        &mut cc,
    );
    let d = BigFloat::parse(
        &r.denom().to_string(),
        Radix::Dec,
        bits,
        RoundingMode::ToEven,
        &mut cc,
    );
    let result = n.div(&d, bits, RoundingMode::ToEven);
    finite(&result)?;
    Ok(result)
}

/// Evaluate an immutable arithmetic source tree at the requested precision.
/// Operands are re-read for each precision; no rounded intermediate is saved.
pub fn expression(value: &Value, bits: usize) -> Result<BigFloat> {
    if let Some(r) = crate::exact::expression(value)? {
        return rational_binary(&r, bits);
    }
    fn eval(v: &Value, bits: usize, depth: usize, count: &mut usize) -> Result<BigFloat> {
        *count += 1;
        if depth > 64 || *count > 4096 {
            return Err("Numeric expression exceeds its bounded size".into());
        }
        if v.is_object()
            && let Some(r) = crate::exact::expression(v)?
        {
            return rational_binary(&r, bits);
        }
        match v {
            Value::String(s) => parse(s, bits),
            Value::Number(n) => parse(&n.to_string(), bits),
            Value::Object(o) if o.len() == 1 && o.contains_key("expression") => {
                let row = o["expression"]
                    .as_array()
                    .ok_or("Invalid numeric expression")?;
                let op = row
                    .first()
                    .and_then(Value::as_str)
                    .ok_or("Numeric operation required")?;
                if op == "neg" && row.len() == 2 {
                    return Ok(eval(&row[1], bits, depth + 1, count)?.neg());
                }
                if row.len() != 3 {
                    return Err("Invalid numeric expression arity".into());
                }
                let a = eval(&row[1], bits, depth + 1, count)?;
                let b = eval(&row[2], bits, depth + 1, count)?;
                let rm = RoundingMode::ToEven;
                let result = match op {
                    "add" => a.add(&b, bits, rm),
                    "sub" => a.sub(&b, bits, rm),
                    "mul" => a.mul(&b, bits, rm),
                    "div" => a.div(&b, bits, rm),
                    "pow" => {
                        let mut cc = Consts::new()
                            .map_err(|e| format!("Constants allocation failed: {e:?}"))?;
                        a.pow(&b, bits, rm, &mut cc)
                    }
                    _ => return Err("Unknown numeric expression operation".into()),
                };
                finite(&result)?;
                Ok(result)
            }
            _ => Err("A finite decimal number or numeric expression is required".into()),
        }
    }
    eval(value, bits, 0, &mut 0)
}

pub fn sampled_number(v: &Value) -> Result<f64> {
    let number = expression(v, CHECK_BITS)?;
    let mut cc = Consts::new().map_err(|e| format!("Constants allocation failed: {e:?}"))?;
    let text = number
        .format(Radix::Dec, RoundingMode::ToEven, &mut cc)
        .map_err(|e| format!("Sampled numeric conversion failed: {e:?}"))?;
    let value = text
        .parse::<f64>()
        .map_err(|_| "Sampled numeric conversion failed")?;
    if !value.is_finite() {
        return Err("Sampled number exceeds binary64 range".into());
    }
    if value == 0. && number.cmp(&BigFloat::from_word(0, CHECK_BITS)) != Some(0) {
        return Err("Sampled number is below binary64 resolution".into());
    }
    Ok(value)
}

pub fn sampled_arguments(v: &Value) -> Result<Value> {
    match v {
        Value::Object(o) if o.contains_key("expression") => {
            Ok(serde_json::json!(sampled_number(v)?))
        }
        Value::Object(o) => Ok(Value::Object(
            o.iter()
                .map(|(k, v)| Ok((k.clone(), sampled_arguments(v)?)))
                .collect::<Result<_>>()?,
        )),
        Value::Array(a) => Ok(Value::Array(
            a.iter().map(sampled_arguments).collect::<Result<_>>()?,
        )),
        _ => Ok(v.clone()),
    }
}

pub fn has_expression(v: &Value) -> bool {
    match v {
        Value::Object(o) => o.contains_key("expression") || o.values().any(has_expression),
        Value::Array(a) => a.iter().any(has_expression),
        _ => false,
    }
}

/// Evaluate a bounded batch of derived sources. A selector preserves Python's
/// existing min/max choice on compatibility values, then retains the chosen
/// operand's *original* source. No rounded intermediate enters another source.
pub fn numeric_batch(a: &Value) -> Result<Value> {
    use std::collections::HashMap;
    type Row = (Value, f64, bool);
    let rows = a["values"]
        .as_array()
        .ok_or("Numeric source array required")?;
    if rows.len() > 512 {
        return Err("Numeric batch exceeds its resource limit".into());
    }
    let fold = a["fold_plain_branches"] == true;
    fn resolve(
        v: &Value,
        depth: usize,
        budget: &mut usize,
        cache: &mut HashMap<String, Row>,
        fold: bool,
    ) -> Result<Row> {
        if depth > 64 || *budget == 0 {
            return Err("Numeric batch expression exceeds its bounded size".into());
        }
        *budget -= 1;
        let key = v.to_string();
        if let Some(r) = cache.get(&key) {
            return Ok(r.clone());
        }
        crate::protocol::control_check()?;
        if let Some(source) = v.get("exact") {
            if v.as_object().is_none_or(|o| o.len() != 1) {
                return Err("Invalid exact source marker".into());
            }
            let result = (source.clone(), sampled_number(source)?, false);
            cache.insert(key, result.clone());
            return Ok(result);
        }
        if let Some(row) = v.get("choose") {
            let row = row.as_array().ok_or("Invalid numeric selector")?;
            let op = row
                .first()
                .and_then(Value::as_str)
                .ok_or("Selector operation required")?;
            if v.as_object().is_none_or(|o| o.len() != 1)
                || !["min", "max"].contains(&op)
                || !(2..=33).contains(&row.len())
            {
                return Err("Invalid numeric selector operation or size".into());
            }
            let mut best = resolve(&row[1], depth + 1, budget, cache, fold)?;
            for item in &row[2..] {
                let next = resolve(item, depth + 1, budget, cache, fold)?;
                if op == "min" && next.1 < best.1 || op == "max" && next.1 > best.1 {
                    best = next;
                }
            }
            cache.insert(key, best.clone());
            return Ok(best);
        }
        let source = if let Some(row) = v.get("expression") {
            let row = row.as_array().ok_or("Invalid numeric expression")?;
            if v.as_object().is_none_or(|o| o.len() != 1) || !(2..=3).contains(&row.len()) {
                return Err("Invalid numeric expression".into());
            }
            let operands = row[1..]
                .iter()
                .map(|v| resolve(v, depth + 1, budget, cache, fold))
                .collect::<Result<Vec<_>>>()?;
            // Only graph branches that contain no exact source use the existing
            // ordinary binary64 arithmetic. Exact AST operands never do.
            if fold && operands.iter().all(|r| r.2) {
                let op = row[0].as_str().ok_or("Numeric operation required")?;
                let x = operands[0].1;
                let plain = match (op, operands.as_slice()) {
                    ("neg", [_]) => Some(-x),
                    ("add", [_, y]) => Some(x + y.1),
                    ("sub", [_, y]) => Some(x - y.1),
                    ("mul", [_, y]) => Some(x * y.1),
                    ("div", [_, y]) => Some(x / y.1),
                    _ => None,
                };
                if let Some(value) = plain {
                    if !value.is_finite() {
                        return Err("Nonfinite ordinary numeric branch".into());
                    }
                    let result = (serde_json::json!(value), value, true);
                    cache.insert(key, result.clone());
                    return Ok(result);
                }
            }
            let mut out = vec![row[0].clone()];
            out.extend(operands.into_iter().map(|r| r.0));
            serde_json::json!({"expression":out})
        } else {
            v.clone()
        };
        let value = sampled_number(&source)?;
        let plain = fold && source.is_number();
        let result = (source, value, plain);
        cache.insert(key, result.clone());
        Ok(result)
    }
    let mut budget = 65_536;
    let mut cache = HashMap::new();
    Ok(serde_json::json!(
        rows.iter()
            .map(|v| {
                let (source, value, plain) = resolve(v, 0, &mut budget, &mut cache, fold)?;
                Ok(serde_json::json!({"source":source,"value":value,"plain":plain}))
            })
            .collect::<Result<Vec<_>>>()?
    ))
}

pub fn validate_number(a: &Value) -> Result<Value> {
    let bits = 2048;
    let v = number(a, "value", None, bits)?;
    let lower = number(a, "lower", None, bits)?;
    let upper = number(a, "upper", None, bits)?;
    let exact = crate::exact::number(a, "value", None)?;
    let outside = if let (Some(v), Some(lo), Some(hi)) = (
        &exact,
        crate::exact::number(a, "lower", None)?,
        crate::exact::number(a, "upper", None)?,
    ) {
        v < &lo || v > &hi
    } else {
        v.cmp(&lower).unwrap() < 0 || v.cmp(&upper).unwrap() > 0
    };
    if outside {
        return Err("Numeric value is outside its parameter bounds".into());
    }
    if a["integer"] == true {
        if exact.as_ref().is_some_and(|r| !r.is_integer()) {
            return Err("An integer is required".into());
        }
        let integer = fixed(&v, 0)?;
        let checked = parse(&integer, bits)?;
        if v.cmp(&checked) != Some(0) {
            return Err("An integer is required".into());
        }
    }
    if let Some(compatibility) = a.get("compatibility_value") {
        let expected = compatibility
            .as_f64()
            .ok_or("Finite compatibility value required")?;
        if sampled_number(&a["value"])? != expected {
            return Err("Decimal source does not match its numeric compatibility value".into());
        }
    }
    Ok(Value::Bool(true))
}

pub fn parse(text: &str, bits: usize) -> Result<BigFloat> {
    if text.len() > 512
        || text.is_empty()
        || text.trim() != text
        || !text
            .bytes()
            .all(|c| c.is_ascii_digit() || b"+-.eE".contains(&c))
    {
        return Err("Invalid decimal spelling or input length".into());
    }
    if let Some((_, exponent)) = text.split_once(['e', 'E']) {
        let exponent: i32 = exponent.parse().map_err(|_| "Invalid decimal exponent")?;
        if !(-4096..=4096).contains(&exponent) {
            return Err("Decimal exponent exceeds the numerical input domain".into());
        }
    }
    let mut constants = Consts::new().map_err(|e| format!("Constants allocation failed: {e:?}"))?;
    let n = BigFloat::parse(text, Radix::Dec, bits, RoundingMode::ToEven, &mut constants);
    finite(&n)?;
    Ok(n)
}

pub fn finite(n: &BigFloat) -> Result<()> {
    if n.is_nan() || n.is_inf() {
        Err("Nonfinite or unresolved numerical result".into())
    } else {
        Ok(())
    }
}

pub fn positive(n: &BigFloat, name: &str, bits: usize) -> Result<()> {
    finite(n)?;
    if n.cmp(&BigFloat::from_word(0, bits)).unwrap_or(0) <= 0 {
        Err(format!("{name} must be positive"))
    } else {
        Ok(())
    }
}

pub fn nonnegative(n: &BigFloat, name: &str, bits: usize) -> Result<()> {
    finite(n)?;
    if n.cmp(&BigFloat::from_word(0, bits)).unwrap_or(-1) < 0 {
        Err(format!("{name} must be nonnegative"))
    } else {
        Ok(())
    }
}

/// Round the decimal representation directly, without a binary64 intermediate.
/// This formats a number; it is not a bound on a sampled surface.
pub fn fixed(n: &BigFloat, places: usize) -> Result<String> {
    finite(n)?;
    let mut cc = Consts::new().map_err(|e| format!("Constants allocation failed: {e:?}"))?;
    let raw = n
        .format(Radix::Dec, RoundingMode::ToEven, &mut cc)
        .map_err(|e| format!("Decimal conversion failed: {e:?}"))?;
    fixed_text(&raw, places)
}

fn fixed_text(raw: &str, places: usize) -> Result<String> {
    let negative = raw.starts_with('-');
    let unsigned = raw.trim_start_matches(['-', '+']);
    let (mantissa, exponent) = if let Some((a, b)) = unsigned.split_once(['e', 'E']) {
        (a, b.parse::<i32>().map_err(|_| "Invalid decimal exponent")?)
    } else {
        (unsigned, 0)
    };
    let whole = mantissa.find('.').unwrap_or(mantissa.len()) as i32;
    let digits: Vec<u8> = mantissa.bytes().filter(|c| *c != b'.').collect();
    if digits.is_empty() || !digits.iter().all(u8::is_ascii_digit) {
        return Err("Invalid formatted decimal result".into());
    }
    let keep = whole + exponent + places as i32;
    if keep.abs() > 4096 || places > 256 {
        return Err("Decimal output exceeds its bound".into());
    }
    let mut rounded = if keep <= 0 {
        vec![b'0']
    } else {
        (0..keep as usize)
            .map(|i| *digits.get(i).unwrap_or(&b'0'))
            .collect::<Vec<_>>()
    };
    let first_discarded = if keep < 0 {
        b'0'
    } else {
        *digits.get(keep as usize).unwrap_or(&b'0')
    };
    let tail_nonzero = keep >= 0 && digits.iter().skip(keep as usize + 1).any(|c| *c != b'0');
    let odd = (rounded.last().unwrap() - b'0') % 2 == 1;
    if first_discarded > b'5' || first_discarded == b'5' && (tail_nonzero || odd) {
        let mut i = rounded.len();
        loop {
            if i == 0 {
                rounded.insert(0, b'1');
                break;
            }
            i -= 1;
            if rounded[i] < b'9' {
                rounded[i] += 1;
                break;
            }
            rounded[i] = b'0';
        }
    }
    while rounded.len() <= places {
        rounded.insert(0, b'0');
    }
    let split = rounded.len() - places;
    let mut text = String::from_utf8(rounded).map_err(|_| "Invalid decimal digits")?;
    if places > 0 {
        text.insert(split, '.');
    }
    // Canonical negative zero is deliberately suppressed.
    if negative && text.bytes().any(|c| c.is_ascii_digit() && c != b'0') {
        text.insert(0, '-');
    }
    Ok(text)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn direct_decimal_rounding_boundaries() {
        for (input, places, expected) in [
            ("1.2345e+2", 2, "123.45"),
            ("9.9995e-1", 3, "1.000"),
            ("-4e-30", 20, "0.00000000000000000000"),
            ("0.5", 0, "0"),
            ("1.5", 0, "2"),
            ("2.5", 0, "2"),
            ("5.001e-21", 20, "0.00000000000000000001"),
            ("5e-21", 20, "0.00000000000000000000"),
        ] {
            assert_eq!(fixed_text(input, places).unwrap(), expected, "{input}");
        }
    }
}
