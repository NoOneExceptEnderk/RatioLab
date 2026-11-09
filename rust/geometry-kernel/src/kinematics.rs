// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Nominal signed speed relations; no implication of physical backdrivability.
use crate::precision::{self, Result, fixed, number, positive};
use astro_float::{BigFloat, expr};
use serde_json::{Map, Value, json};
fn put(out: &mut Map<String, Value>, key: &str, v: BigFloat) -> Result<()> {
    out.insert(key.into(), json!(fixed(&v, 20)?));
    Ok(())
}
fn integer(a: &Value, key: &str) -> Result<i64> {
    let n = a[key]
        .as_i64()
        .ok_or_else(|| format!("{key} must be an integer"))?;
    if !(1..=1_000_000).contains(&n) {
        return Err(format!("{key} must be from 1 to 1000000"));
    }
    Ok(n)
}
pub fn solve(a: &Value, bits: usize) -> Result<Value> {
    let mut c = precision::context(bits)?;
    let coefficients = a["coefficients"]
        .as_object()
        .ok_or("Three-member coefficients required")?;
    let scheme: Vec<_> = a["scheme"]
        .as_str()
        .ok_or("Kinematic scheme required")?
        .split('_')
        .collect();
    if scheme.len() != 3
        || coefficients.len() != 3
        || scheme[0] == scheme[1]
        || scheme[0] == scheme[2]
        || scheme[1] == scheme[2]
        || scheme.iter().any(|k| !coefficients.contains_key(*k))
    {
        return Err("Invalid three-member input/output/fixed arrangement".into());
    }
    let source = number(&a["coefficients"], scheme[0], None, bits)?;
    let target = number(&a["coefficients"], scheme[1], None, bits)?;
    if source.cmp(&BigFloat::from_word(0, bits)) == Some(0)
        || target.cmp(&BigFloat::from_word(0, bits)) == Some(0)
    {
        return Err("Singular three-member kinematic equation".into());
    }
    let rpm = number(a, "rpm", None, bits)?;
    if let (Some(source), Some(target), Some(rpm)) = (
        crate::exact::number(&a["coefficients"], scheme[0], None)?,
        crate::exact::number(&a["coefficients"], scheme[1], None)?,
        crate::exact::number(a, "rpm", None)?,
    ) {
        let ratio = -target / source;
        let mut rates = Map::new();
        rates.insert(scheme[0].into(), json!(crate::exact::fixed(&rpm, 20)?));
        rates.insert(
            scheme[1].into(),
            json!(crate::exact::fixed(&(rpm / &ratio), 20)?),
        );
        rates.insert(
            scheme[2].into(),
            json!(crate::exact::fixed(&crate::exact::integer(0), 20)?),
        );
        return Ok(
            json!({"input":scheme[0],"output":scheme[1],"fixed":scheme[2],
            "signed_ratio":crate::exact::fixed(&ratio,20)?,"rates_rpm":rates,"coefficients":coefficients}),
        );
    }
    let ratio = expr!(-target / source, &mut c);
    let output = expr!(rpm / ratio, &mut c);
    let mut rates = Map::new();
    put(&mut rates, scheme[0], rpm)?;
    put(&mut rates, scheme[1], output)?;
    put(&mut rates, scheme[2], BigFloat::from_word(0, bits))?;
    Ok(
        json!({"input":scheme[0],"output":scheme[1],"fixed":scheme[2],"signed_ratio":fixed(&ratio,20)?,"rates_rpm":rates,"coefficients":coefficients}),
    )
}
pub fn differential(a: &Value, bits: usize) -> Result<Value> {
    let mut c = precision::context(bits)?;
    let two = BigFloat::from_word(2, bits);
    let input_a = number(a, "a", None, bits)?;
    let input_b = number(a, "b", None, bits)?;
    let side = number(a, "side_teeth", None, bits)?;
    let output = number(a, "output_teeth", None, bits)?;
    positive(&side, "side teeth", bits)?;
    positive(&output, "output teeth", bits)?;
    if let (Some(a0), Some(b), Some(s), Some(o)) = (
        crate::exact::number(a, "a", None)?,
        crate::exact::number(a, "b", None)?,
        crate::exact::number(a, "side_teeth", None)?,
        crate::exact::number(a, "output_teeth", None)?,
    ) {
        let two = crate::exact::integer(2);
        let rows = if a["classic"] == true {
            vec![
                ("side_a", &a0 - &b / &two),
                ("side_b", &a0 + &b / &two),
                ("carrier", a0),
                ("spider_spin", s / o * b / two),
            ]
        } else {
            vec![
                ("carrier", (&a0 + &b) / &two),
                ("output_spin", (&b - &a0) * s / (two * o)),
                ("input_a", a0),
                ("input_b", b),
            ]
        };
        return Ok(Value::Object(
            rows.into_iter()
                .map(|(k, v)| Ok((k.into(), json!(crate::exact::fixed(&v, 20)?))))
                .collect::<Result<_>>()?,
        ));
    }
    let mut out = Map::new();
    if a["classic"] == true {
        put(&mut out, "side_a", expr!(input_a - input_b / two, &mut c))?;
        put(&mut out, "side_b", expr!(input_a + input_b / two, &mut c))?;
        put(&mut out, "carrier", input_a)?;
        put(
            &mut out,
            "spider_spin",
            expr!(side / output * input_b / two, &mut c),
        )?;
    } else {
        put(
            &mut out,
            "carrier",
            expr!((input_a + input_b) / two, &mut c),
        )?;
        put(
            &mut out,
            "output_spin",
            expr!((input_b - input_a) * side / (two * output), &mut c),
        )?;
        put(&mut out, "input_a", input_a)?;
        put(&mut out, "input_b", input_b)?;
    }
    Ok(json!(out))
}
pub fn wolfrom(a: &Value, bits: usize) -> Result<Value> {
    let mut c = precision::context(bits)?;
    let two = BigFloat::from_word(2, bits);
    let s = integer(a, "sun")?;
    let p1 = integer(a, "planet")?;
    let p2 = integer(a, "planet2")?;
    let ro = integer(a, "output_ring")?;
    let rf = s + 2 * p1;
    let determinant = p1 * ro - rf * p2;
    if ro <= p2 {
        return Err("Wolfrom output ring teeth must exceed second planet teeth.".into());
    }
    if determinant == 0 {
        return Err("Wolfrom determinant P1*Ro−Rf*P2 is zero: the output is stationary; no finite reducer ratio exists.".into());
    }
    let sun = number(a, "sun", None, bits)?;
    let planet = number(a, "planet", None, bits)?;
    let planet2 = number(a, "planet2", None, bits)?;
    let ring = number(a, "output_ring", None, bits)?;
    let fixed_ring = BigFloat::from_i64(rf, bits);
    let det = BigFloat::from_i64(determinant, bits);
    let m = number(a, "module", None, bits)?;
    positive(&m, "module", bits)?;
    // Both rims share the helix magnitude and normal-module system. Their
    // derived module ratio and ideal speed ratios stay independent of beta.
    let beta = number(a, "helix", Some("0"), bits)?;
    let zero = BigFloat::from_word(0, bits);
    let ninety = BigFloat::from_word(90, bits);
    if beta.cmp(&ninety).unwrap() >= 0 || beta.cmp(&ninety.neg()).unwrap() <= 0 {
        return Err("Wolfrom absolute helix must be below 90 degrees".into());
    }
    let degrees = BigFloat::from_word(180, bits);
    let center_distance = expr!(
        m * (sun + planet) / (two * cos(beta * pi / degrees)),
        &mut c
    );
    let exact_rpm = a.get("rpm").map(crate::exact::expression).transpose()?;
    if let Some(m) = crate::exact::number(a, "module", None)?
        && exact_rpm.as_ref().is_none_or(Option::is_some)
    {
        use crate::exact::{fixed, integer as q};
        let ratio = q(s + rf) * q(p1) * q(ro) / (q(s) * q(determinant));
        let center = if beta.cmp(&zero) == Some(0) {
            fixed(&(&m * q(s + p1) / q(2)), 20)?
        } else {
            precision::fixed(&center_distance, 20)?
        };
        let mut out = json!({"fixed_ring_teeth":rf,"determinant":determinant,
            "module2_mm":fixed(&(&m*q(s+p1)/q(ro-p2)),20)?,
            "center_distance_mm":center,
            "signed_ratio":fixed(&ratio,20)?});
        if let Some(Some(rpm)) = exact_rpm {
            out["rates_rpm"] = json!({"sun":fixed(&rpm,20)?,"ring":fixed(&q(0),20)?,
                "carrier":fixed(&(&rpm*q(s)/q(s+rf)),20)?,
                "planet":fixed(&(&rpm*q(s)*q(p1-rf)/(q(s+rf)*q(p1))),20)?,
                "output":fixed(&(rpm/ratio),20)?});
        }
        return Ok(out);
    }
    let mut out = Map::new();
    out.insert("fixed_ring_teeth".into(), json!(rf));
    out.insert("determinant".into(), json!(determinant));
    put(
        &mut out,
        "module2_mm",
        expr!(m * (sun + planet) / (ring - planet2), &mut c),
    )?;
    put(&mut out, "center_distance_mm", center_distance)?;
    put(
        &mut out,
        "signed_ratio",
        expr!((sun + fixed_ring) * planet * ring / (sun * det), &mut c),
    )?;
    if a.get("rpm").is_some() {
        let rpm = number(a, "rpm", None, bits)?;
        let mut rates = Map::new();
        put(
            &mut rates,
            "carrier",
            expr!(rpm * sun / (sun + fixed_ring), &mut c),
        )?;
        put(
            &mut rates,
            "planet",
            expr!(
                rpm * sun * (planet - fixed_ring) / ((sun + fixed_ring) * planet),
                &mut c
            ),
        )?;
        put(
            &mut rates,
            "output",
            expr!(
                rpm * sun * det / ((sun + fixed_ring) * planet * ring),
                &mut c
            ),
        )?;
        put(&mut rates, "sun", rpm)?;
        put(&mut rates, "ring", BigFloat::from_word(0, bits))?;
        out.insert("rates_rpm".into(), json!(rates));
    }
    Ok(json!(out))
}

/// Exact rational speed API for symbolic checks and callers supplying Fraction.
/// All integer arithmetic stays in Rust; Python only constructs the value type.
pub fn exact_wolfrom(a: &Value) -> Result<Value> {
    fn gcd(mut a: i128, mut b: i128) -> i128 {
        while b != 0 {
            let t = a % b;
            a = b;
            b = t;
        }
        a
    }
    fn rational(n: i128, d: i128) -> Result<(i128, i128)> {
        if d == 0 {
            return Err("Zero rational denominator".into());
        }
        let absn = n.checked_abs().ok_or("Rational input overflow")?;
        let absd = d.checked_abs().ok_or("Rational input overflow")?;
        let g = gcd(absn, absd);
        let sign = if d < 0 { -1 } else { 1 };
        Ok((n / g * sign, d / g * sign))
    }
    fn mul((n, d): (i128, i128), x: i128, y: i128) -> Result<(i128, i128)> {
        let g1 = gcd(
            n.checked_abs().ok_or("Rational overflow")?,
            y.checked_abs().ok_or("Rational overflow")?,
        );
        let g2 = gcd(x.checked_abs().ok_or("Rational overflow")?, d);
        rational(
            (n / g1)
                .checked_mul(x / g2)
                .ok_or("Rational numerator overflow")?,
            (d / g2)
                .checked_mul(y / g1)
                .ok_or("Rational denominator overflow")?,
        )
    }
    let s = integer(a, "sun")? as i128;
    let p1 = integer(a, "planet")? as i128;
    let p2 = integer(a, "planet2")? as i128;
    let ro = integer(a, "output_ring")? as i128;
    let read = |key: &str| -> Result<i128> {
        a[key]
            .as_str()
            .ok_or("Exact rational input must be integer text")?
            .parse()
            .map_err(|_| "Exact rational input overflow".into())
    };
    let rpm = rational(read("numerator")?, read("denominator")?)?;
    let rf = s + 2 * p1;
    let det = p1 * ro - rf * p2;
    if ro <= p2 || det == 0 {
        return Err("Invalid Wolfrom output mesh or zero determinant".into());
    }
    let values = [
        ("sun", rpm),
        ("ring", (0, 1)),
        ("carrier", mul(rpm, s, s + rf)?),
        ("planet", mul(rpm, s * (p1 - rf), (s + rf) * p1)?),
        ("output", mul(rpm, s * det, (s + rf) * p1 * ro)?),
    ];
    Ok(Value::Object(
        values
            .into_iter()
            .map(|(key, (n, d))| (key.into(), json!([n.to_string(), d.to_string()])))
            .collect(),
    ))
}

/// Exact compound reindex congruence; full-body phases are sampled radians.
pub fn wolfrom_phases(a: &Value) -> Result<Value> {
    fn gcd(mut a: i64, mut b: i64) -> i64 {
        while b != 0 {
            (a, b) = (b, a % b);
        }
        a
    }
    let s = integer(a, "sun")?;
    let p1 = integer(a, "planet")?;
    let p2 = integer(a, "planet2")?;
    let ro = integer(a, "output_ring")?;
    let count = integer(a, "planets")?;
    if count > 10000 {
        return Err("Wolfrom phase count exceeds its resource limit".into());
    }
    let rf = s + 2 * p1;
    let divisor = gcd(p1, p2);
    let numerator = p1 * ro + p2 * s;
    if (s + rf) % count != 0 || numerator % (count * divisor) != 0 {
        return Err("Equally spaced identical Wolfrom compounds cannot satisfy all three tooth phases: require n dividing S+Rf and n*gcd(P1,P2) dividing P1*Ro+P2*S.".into());
    }
    let modulus = p1 / divisor;
    let k1 = if modulus == 1 {
        0
    } else {
        let (mut old_r, mut r) = (p2 / divisor, modulus);
        let (mut old_s, mut s) = (1_i64, 0_i64);
        while r != 0 {
            let q = old_r / r;
            (old_r, r) = (r, old_r - q * r);
            (old_s, s) = (s, old_s - q * s);
        }
        if old_r != 1 {
            return Err("Compound reindex inverse is unavailable".into());
        }
        (-(numerator / count / divisor) * old_s.rem_euclid(modulus)).rem_euclid(modulus)
    };
    let pi = std::f64::consts::PI;
    let tau = std::f64::consts::TAU;
    let delta = pi / p2 as f64 - pi / p1 as f64;
    let compounds:Vec<_>=(0..count).map(|j|{let theta=tau*j as f64/count as f64;let phi1=(pi+pi/p1 as f64+(s+p1) as f64*theta/p1 as f64+tau*j as f64*k1 as f64/p1 as f64).rem_euclid(tau);
        json!({"index":j+1,"theta_rad":theta,"planet_phase_rad":phi1,"planet2_phase_rad":phi1+delta,"reindex":j*k1})}).collect();
    Ok(
        json!({"k1":k1,"common_clocking_rad":delta,"fixed_ring_phase_rad":p1 as f64*pi/rf as f64,"output_ring_phase_rad":p2 as f64*pi/ro as f64,"compounds":compounds,"basis":"neutral backlash; one common rigid P2-P1 clocking; full-body radians"}),
    )
}
