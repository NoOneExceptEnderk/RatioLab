// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Nominal cylindrical geometry, ISO 21771:2007, 4.2, 4.3 and 4.7.
//! Positive physical tooth counts; internal/external sign is explicit.
use crate::precision::{self, Result, fixed, nonnegative, number, positive};
use astro_float::{BigFloat, expr};
use serde_json::{Map, Value, json};

fn put(out: &mut Map<String, Value>, name: &str, value: BigFloat) -> Result<()> {
    out.insert(
        name.into(),
        Value::String(fixed(&value, precision::DECIMAL_PLACES)?),
    );
    Ok(())
}

pub fn dimensions(a: &Value, bits: usize) -> Result<Value> {
    let mut c = precision::context(bits)?;
    let two = BigFloat::from_word(2, bits);
    let degrees = BigFloat::from_word(180, bits);
    let z = number(a, "teeth", None, bits)?;
    let mn = number(a, "module", None, bits)?;
    let pressure = number(a, "pressure", Some("20"), bits)?;
    let beta = number(a, "helix", Some("0"), bits)?;
    let shift = number(a, "profile_shift", Some("0"), bits)?;
    let ha = number(a, "addendum", Some("1"), bits)?;
    let hf = number(a, "dedendum", Some("1.25"), bits)?;
    let backlash = number(a, "backlash", Some("0.15"), bits)?;
    let width = number(a, "width", Some("10"), bits)?;
    let topping = number(a, "topping_mm", Some("0"), bits)?;
    nonnegative(&topping, "topping_mm", bits)?;
    let internal = match a.get("internal") {
        None => false,
        Some(Value::Bool(v)) => *v,
        _ => return Err("internal must be boolean".into()),
    };
    for (v, n) in [
        (&mn, "module"),
        (&ha, "addendum"),
        (&hf, "dedendum"),
        (&width, "width"),
    ] {
        positive(v, n, bits)?;
    }
    if a["cutter_allowance"] != true {
        nonnegative(&backlash, "backlash", bits)?;
    }
    let z_integer = fixed(&z, 0)?
        .parse::<u64>()
        .map_err(|_| "Invalid tooth count")?;
    if !(3..=1_000_000).contains(&z_integer)
        || z.cmp(&BigFloat::from_u64(z_integer, bits)) != Some(0)
    {
        return Err("teeth must be an integer from 3 to 1000000".into());
    }
    let zero = BigFloat::from_word(0, bits);
    let ninety = BigFloat::from_word(90, bits);
    if pressure.cmp(&zero).unwrap() <= 0
        || pressure.cmp(&ninety).unwrap() >= 0
        || beta.cmp(&ninety).unwrap() >= 0
        || beta.cmp(&ninety.neg()).unwrap() <= 0
    {
        return Err(
            "Pressure must be between 0 and 90 degrees and absolute helix below 90 degrees".into(),
        );
    }
    if internal && shift.cmp(&zero) != Some(0) {
        return Err("Shifted internal rings require a dedicated construction".into());
    }
    let an = expr!(pressure * pi / degrees, &mut c);
    let br = expr!(beta * pi / degrees, &mut c);
    let cb = expr!(cos(br), &mut c);
    let mt = expr!(mn / cb, &mut c);
    let at = expr!(atan(tan(an) / cb), &mut c);
    let rp = expr!(mt * z / two, &mut c);
    let rb = expr!(rp * cos(at), &mut c);
    let tip = if internal {
        expr!(rp - mn * ha + topping, &mut c)
    } else {
        expr!(rp + mn * (ha + shift) - topping, &mut c)
    };
    if topping.cmp(&zero) != Some(0)
        && if internal {
            tip.cmp(&rp).is_none_or(|v| v >= 0)
        } else {
            tip.cmp(&rp).is_none_or(|v| v <= 0)
        }
    {
        return Err(
            "Topping must leave a positive addendum above the reference pitch surface.".into(),
        );
    }
    let root = if internal {
        expr!(rp + mn * hf, &mut c)
    } else {
        expr!(rp - mn * (hf - shift), &mut c)
    };
    positive(&tip, "tip radius", bits)?;
    positive(&root, "root radius", bits)?;
    let nominal = expr!(mn * (pi / two + two * shift * tan(an)), &mut c);
    let generated = expr!(nominal - backlash * cb / two, &mut c);
    positive(&generated, "reference tooth thickness with allowance", bits)?;
    let one = BigFloat::from_word(1, bits);
    let four = BigFloat::from_word(4, bits);
    let preferred = precision::parse("0.3", bits)?;
    let minimum_land = precision::parse("0.025", bits)?;
    let land = expr!(
        pi * mn / four + backlash * cb / four - hf * mn * tan(an),
        &mut c
    );
    let usable_land = expr!(minimum_land * mn, &mut c);
    if land.cmp(&usable_land).unwrap() <= 0 {
        return Err(
            "Impossible rack: dedendum and pressure angle eliminate the tool tip land.".into(),
        );
    }
    let rho_preferred = expr!(preferred * mn, &mut c);
    let rho_fit = expr!((land - usable_land) * cos(an) / (one - sin(an)), &mut c);
    let mut rho = if rho_preferred.cmp(&rho_fit).unwrap() <= 0 {
        rho_preferred
    } else {
        rho_fit
    };
    let custom_rho = a.get("rack_tip_radius_mm").is_some_and(|v| !v.is_null());
    if custom_rho {
        if internal {
            return Err(
                "A generating-rack tip radius applies to external gears, not internal rings."
                    .into(),
            );
        }
        rho = number(a, "rack_tip_radius_mm", None, bits)?;
        positive(&rho, "normal generating-rack tip radius", bits)?;
        let maximum = expr!((land - usable_land) * cos(an) / (one - sin(an)), &mut c);
        if rho.cmp(&maximum).unwrap() > 0 {
            return Err(
                "Normal generating-rack tip radius must preserve the tool tip land.".into(),
            );
        }
    }
    let virtual_teeth = expr!(z / (cb * cb * cb), &mut c);
    let rack_min = expr!(
        (hf * mn - rho * (one - sin(an)) - rp * sin(at) * sin(at)) / mn,
        &mut c
    );
    let min_shift = expr!(ha - virtual_teeth * sin(an) * sin(an) / two, &mut c);
    let mut out = Map::new();
    if custom_rho {
        out.insert(
            "generating_rack_normal_tip_radius_mm".into(),
            json!(fixed(&rho, precision::DECIMAL_PLACES)?),
        );
    }
    for (name, value) in [
        ("virtual_teeth", virtual_teeth),
        ("minimum_shift", min_shift),
        ("rack_minimum_shift", rack_min),
        ("normal_module_mm", mn.clone()),
        ("transverse_module_mm", mt),
        (
            "transverse_pressure_angle_deg",
            expr!(at * degrees / pi, &mut c),
        ),
        ("pitch_radius_mm", rp.clone()),
        ("base_radius_mm", rb),
        ("tip_radius_mm", tip),
        ("root_radius_mm", root),
        ("normal_reference_arc_mm", nominal.clone()),
        ("normal_reference_arc_with_allowance_mm", generated.clone()),
        ("transverse_reference_arc_mm", expr!(nominal / cb, &mut c)),
        (
            "transverse_reference_arc_with_allowance_mm",
            expr!(generated / cb, &mut c),
        ),
        (
            "transverse_base_pitch_mm",
            expr!(pi * mn * cos(at) / cb, &mut c),
        ),
        (
            "twist_deg",
            expr!(width * tan(br) / rp * degrees / pi, &mut c),
        ),
    ] {
        put(&mut out, name, value)?;
    }
    exact_dimensions(a, &mut out)?;
    Ok(Value::Object(out))
}

/// Decimal input and rational identities must not be rounded through binary
/// approximations at a decimal half. Transcendental fields retain both checks.
fn exact_dimensions(a: &Value, out: &mut Map<String, Value>) -> Result<()> {
    use crate::exact::{fixed, integer, number};
    use num_traits::Zero;
    let mn = number(a, "module", None)?;
    if let Some(m) = &mn {
        out.insert("normal_module_mm".into(), json!(fixed(m, 20)?));
    }
    let (Some(m), Some(z), Some(beta), Some(x), Some(ha), Some(hf)) = (
        mn,
        number(a, "teeth", None)?,
        number(a, "helix", Some("0"))?,
        number(a, "profile_shift", Some("0"))?,
        number(a, "addendum", Some("1"))?,
        number(a, "dedendum", Some("1.25"))?,
    ) else {
        return Ok(());
    };
    // cos(0)=1 and cos(+-60deg)=1/2 are exact rational identities.
    let cb = if beta.is_zero() {
        integer(1)
    } else if beta == integer(60) || beta == integer(-60) {
        integer(1) / integer(2)
    } else {
        return Ok(());
    };
    let mt = &m / &cb;
    let rp = &mt * &z / integer(2);
    let internal = a["internal"] == true;
    let Some(topping) = number(a, "topping_mm", Some("0"))? else {
        return Ok(());
    };
    let tip = if internal {
        &rp - &m * ha + topping
    } else {
        &rp + &m * (ha + &x) - topping
    };
    let root = if internal {
        &rp + &m * hf
    } else {
        &rp - &m * (hf - &x)
    };
    for (key, value) in [
        ("transverse_module_mm", mt),
        ("pitch_radius_mm", rp),
        ("tip_radius_mm", tip),
        ("root_radius_mm", root),
        ("virtual_teeth", z / (&cb * &cb * &cb)),
    ] {
        out.insert(key.into(), json!(fixed(&value, 20)?));
    }
    if beta.is_zero() {
        if let Some(pressure) = number(a, "pressure", Some("20"))? {
            out.insert(
                "transverse_pressure_angle_deg".into(),
                json!(fixed(&pressure, 20)?),
            );
        }
        out.insert("twist_deg".into(), json!(fixed(&integer(0), 20)?));
    }
    Ok(())
}

pub fn involute(a: &Value, bits: usize) -> Result<Value> {
    let mut c = precision::context(bits)?;
    let two = BigFloat::from_word(2, bits);
    let alpha = number(a, "angle_rad", None, bits)?;
    let zero = BigFloat::from_word(0, bits);
    let bound = expr!(pi / two, &mut c);
    if alpha.cmp(&zero).unwrap() < 0 || alpha.cmp(&bound).unwrap() >= 0 {
        return Err("Involute angle outside [0,pi/2)".into());
    }
    Ok(json!({"involute":fixed(&expr!(tan(alpha)-alpha,&mut c),precision::DECIMAL_PLACES)?}))
}

pub fn inverse_involute(a: &Value, bits: usize) -> Result<Value> {
    let mut c = precision::context(bits)?;
    let two = BigFloat::from_word(2, bits);
    let target = number(a, "involute", None, bits)?;
    nonnegative(&target, "involute", bits)?;
    let mut lo = BigFloat::from_word(0, bits);
    let mut hi = expr!(pi / two, &mut c);
    for _ in 0..bits + 32 {
        let mid = expr!((lo + hi) / two, &mut c);
        if mid.cmp(&lo) == Some(0) || mid.cmp(&hi) == Some(0) {
            break;
        }
        let value = expr!(tan(mid) - mid, &mut c);
        precision::finite(&value)?;
        if value.cmp(&target).unwrap() < 0 {
            lo = mid;
        } else {
            hi = mid;
        }
    }
    let alpha = expr!((lo + hi) / two, &mut c);
    Ok(json!({"angle_rad":fixed(&alpha,precision::DECIMAL_PLACES)?}))
}

pub fn working_backlash(a: &Value, bits: usize) -> Result<Value> {
    let mut c = precision::context(bits)?;
    let two = BigFloat::from_word(2, bits);
    let a0 = number(a, "reference_center_mm", None, bits)?;
    let pressure = number(a, "transverse_pressure_deg", None, bits)?;
    let j = number(a, "nominal_backlash_mm", None, bits)?;
    let extra = number(a, "extra_mm", Some("0"), bits)?;
    positive(&a0, "reference center", bits)?;
    positive(&pressure, "transverse pressure", bits)?;
    nonnegative(&j, "nominal backlash", bits)?;
    nonnegative(&extra, "extra center distance", bits)?;
    if pressure.cmp(&BigFloat::from_word(90, bits)).unwrap() >= 0 {
        return Err("Pressure must be below 90 degrees".into());
    }
    let degrees = BigFloat::from_word(180, bits);
    let at = expr!(pressure * pi / degrees, &mut c);
    let distance = expr!(a0 + extra, &mut c);
    let aw = expr!(acos(a0 * cos(at) / distance), &mut c);
    let value = expr!(
        j * distance / a0 + two * distance * ((tan(aw) - aw) - (tan(at) - at)),
        &mut c
    );
    Ok(json!({"working_backlash_mm":fixed(&value,precision::DECIMAL_PLACES)?}))
}

/// Bounded nonlinear centre-distance inversion. The compatibility adapter may
/// request the published boundary roundoff allowance; the decimal API defaults
/// to an exact reachable-domain check.
pub fn inverse_backlash(a: &Value, bits: usize) -> Result<Value> {
    let mut c = precision::context(bits)?;
    let two = BigFloat::from_word(2, bits);
    let degrees = BigFloat::from_word(180, bits);
    let a0 = number(a, "reference_center_mm", None, bits)?;
    let pressure = number(a, "transverse_pressure_deg", None, bits)?;
    let j = number(a, "nominal_backlash_mm", None, bits)?;
    let target = number(a, "desired_backlash_mm", None, bits)?;
    let mut lo = number(a, "minimum_extra_mm", Some("0"), bits)?;
    let mut hi = number(a, "maximum_extra_mm", Some("5"), bits)?;
    positive(&a0, "Reference centre distance", bits)?;
    positive(&pressure, "Transverse pressure angle", bits)?;
    if pressure.cmp(&BigFloat::from_word(90, bits)).unwrap() >= 0 {
        return Err("Transverse pressure angle must be less than 90 degrees.".into());
    }
    for (v, key) in [
        (&j, "Nominal pair backlash"),
        (&target, "Desired working transverse tangential backlash"),
        (&lo, "Minimum centre increase"),
        (&hi, "Maximum centre increase"),
    ] {
        nonnegative(v, key, bits)?;
    }
    if hi.cmp(&lo).unwrap() < 0 {
        return Err("Centre distance bounds are reversed.".into());
    }
    let at = expr!(pressure * pi / degrees, &mut c);
    let inv_at = expr!(tan(at) - at, &mut c);
    let calc =
        |extra: &BigFloat, mut c: &mut astro_float::ctx::Context| -> Result<(BigFloat, BigFloat)> {
            let distance = expr!(a0 + extra, c);
            let aw = expr!(acos(a0 * cos(at) / distance), c);
            let increment = expr!((tan(aw) - aw) - inv_at, c);
            let value = expr!(j * distance / a0 + two * distance * increment, c);
            let derivative = expr!(j / a0 + two * increment + two * tan(aw), c);
            precision::finite(&value)?;
            precision::finite(&derivative)?;
            Ok((value, derivative))
        };
    let lower = calc(&lo, &mut c)?.0;
    let upper = calc(&hi, &mut c)?.0;
    let mut tolerance = BigFloat::from_word(0, bits);
    if a["compatibility_roundoff"] == true {
        let one = BigFloat::from_word(1, bits);
        let scale = if upper.cmp(&one).unwrap() > 0 {
            upper.clone()
        } else {
            one
        };
        let epsilon = precision::parse("1e-12", bits)?;
        tolerance = expr!(epsilon * scale, &mut c);
    }
    if target.cmp(&expr!(lower - tolerance, &mut c)).unwrap() < 0 {
        return Err(format!(
            "Desired backlash is below the reachable baseline {} mm; negative centre increase is unsupported.",
            fixed(&lower, 20)?
        ));
    }
    if target.cmp(&expr!(upper + tolerance, &mut c)).unwrap() > 0 {
        return Err(format!(
            "Desired backlash exceeds {} mm at the parameter limit {} mm.",
            fixed(&upper, 20)?,
            fixed(&hi, 20)?
        ));
    }
    if target.cmp(&expr!(lower + tolerance, &mut c)).unwrap() <= 0 {
        return Ok(json!({"extra_mm":fixed(&lo,20)?}));
    }
    if target.cmp(&expr!(upper - tolerance, &mut c)).unwrap() >= 0 {
        return Ok(json!({"extra_mm":fixed(&hi,20)?}));
    }
    let mut x = expr!((lo + hi) / two, &mut c);
    for _ in 0..bits + 32 {
        let (value, derivative) = calc(&x, &mut c)?;
        if value.cmp(&target).unwrap() < 0 {
            lo = x.clone()
        } else {
            hi = x.clone()
        }
        let candidate = expr!(x - (value - target) / derivative, &mut c);
        let next = if candidate.cmp(&lo).is_some_and(|s| s > 0)
            && candidate.cmp(&hi).is_some_and(|s| s < 0)
        {
            candidate
        } else {
            expr!((lo + hi) / two, &mut c)
        };
        if next.cmp(&lo) == Some(0) || next.cmp(&hi) == Some(0) {
            break;
        }
        x = next;
    }
    Ok(json!({"extra_mm":fixed(&expr!((lo+hi)/two,&mut c),20)?}))
}
