// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
use serde_json::{Value, json};
fn calculate(operation: &str, parameters: Value) -> Value {
    ratiolab_geometry::request(&json!({"protocol":1,"operation":operation,"parameters":parameters}))
        .unwrap()["values"]
        .clone()
}

// Independently calculated with mpmath1.3.0 at100 decimal digits, using atan2
// for the transverse angle. ISO21771:2007 nominal equations, not sampled widths.
#[test]
fn nominal_spur_and_helical_independent_decimal_benchmarks() {
    let spur = calculate("cylindrical_dimensions", json!({"teeth":24,"module":"2"}));
    assert_eq!(spur["base_radius_mm"], "22.55262289886180121730");
    assert_eq!(spur["normal_reference_arc_mm"], "3.14159265358979323846");
    let helical = calculate(
        "cylindrical_dimensions",
        json!({"teeth":12,"module":"3","helix":"30","profile_shift":"0.09809"}),
    );
    assert_eq!(helical["pitch_radius_mm"], "20.78460969082652752233");
    assert_eq!(helical["base_radius_mm"], "19.16114529928735688737");
    assert_eq!(helical["tip_radius_mm"], "24.07887969082652752233");
    assert_eq!(
        helical["transverse_pressure_angle_deg"],
        "22.79587725885847396479"
    );
}

#[test]
fn decimal_input_is_not_collapsed_to_binary64() {
    let q = calculate(
        "cylindrical_dimensions",
        json!({"teeth":24,"module":"2.00000000000000000001"}),
    );
    assert_eq!(q["pitch_radius_mm"], "24.00000000000000000012");
    let raw = ratiolab_geometry::dispatch(
        r#"{"protocol":1,"operation":"cylindrical_dimensions","parameters":{"teeth":24,"module":2.00000000000000000001}}"#,
    );
    let response: Value = serde_json::from_str(&raw).unwrap();
    assert_eq!(
        response["result"]["values"]["pitch_radius_mm"],
        "24.00000000000000000012"
    );
}

#[test]
fn signed_helix_and_internal_geometry_have_consistent_dimensions() {
    let a = calculate(
        "cylindrical_dimensions",
        json!({"teeth":54,"module":2,"helix":25,"internal":true}),
    );
    let b = calculate(
        "cylindrical_dimensions",
        json!({"teeth":54,"module":2,"helix":-25,"internal":true}),
    );
    for key in [
        "pitch_radius_mm",
        "base_radius_mm",
        "tip_radius_mm",
        "root_radius_mm",
    ] {
        assert_eq!(a[key], b[key]);
    }
    assert_eq!(
        a["twist_deg"].as_str().unwrap(),
        b["twist_deg"].as_str().unwrap().trim_start_matches('-')
    );
}

#[test]
fn inverse_involute_retains_the_small_base_circle_branch() {
    let q = calculate("inverse_involute", json!({"involute":"1e-48"}));
    assert_eq!(q["angle_rad"], "0.00000000000000014422");
    let zero = calculate("inverse_involute", json!({"involute":"0"}));
    assert_eq!(zero["angle_rad"], "0.00000000000000000000");
}

#[test]
fn invalid_domains_are_explicit_errors() {
    for p in [
        json!({"teeth":24,"module":0}),
        json!({"teeth":"24.00000000000000000001","module":2}),
        json!({"teeth":24,"module":2,"pressure":90}),
        json!({"teeth":true,"module":2}),
        json!({"teeth":24,"module":"NaN"}),
        json!({"teeth":24,"module":2,"internal":true,"profile_shift":0.1}),
    ] {
        assert!(
            ratiolab_geometry::request(
                &json!({"protocol":1,"operation":"cylindrical_dimensions","parameters":p})
            )
            .is_err()
        );
    }
}

#[test]
fn zero_extra_center_preserves_reference_backlash_exactly() {
    let q = calculate(
        "working_backlash",
        json!({"reference_center_mm":"80","transverse_pressure_deg":"20","nominal_backlash_mm":"0.15000000000000000001","extra_mm":"0"}),
    );
    assert_eq!(q["working_backlash_mm"], "0.15000000000000000001");
}
