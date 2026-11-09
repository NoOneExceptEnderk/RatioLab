// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
use ratiolab_geometry::request;
use serde_json::{Value, json};

fn fit(parameters: Value) -> Result<Value, String> {
    request(&json!({"protocol":1,"operation":"cad_spur_curves","parameters":parameters}))
}

#[test]
fn finer_curves_preserve_closed_continuous_topology() {
    let mut previous = 0;
    for tolerance in [0.02, 0.0001, 0.000001] {
        let result = fit(json!({"z":24,"mt":2,"tolerance_mm":tolerance})).unwrap();
        let curves = result["curves"].as_array().unwrap();
        assert!(curves.len() > previous);
        previous = curves.len();
        assert!(result["curve_interpolation_bound_mm"].as_f64().unwrap() < tolerance);
        for index in 0..curves.len() {
            let previous = &curves[(index + curves.len() - 1) % curves.len()];
            let current = &curves[index];
            let key = if previous["kind"] == "cubic" {
                "controls"
            } else {
                "endpoints"
            };
            let end = previous[key].as_array().unwrap().last().unwrap();
            let key = if current["kind"] == "cubic" {
                "controls"
            } else {
                "endpoints"
            };
            assert_eq!(end, &current[key][0]);
        }
    }
}

#[test]
fn prototype_rejects_unsupported_sources_and_unachievable_requests() {
    for parameters in [
        json!({"internal":true}),
        json!({"helix":20}),
        json!({"z":24.5}),
        json!({"z":201}),
        json!({"mt":2,"depth":1}),
        json!({"tolerance_mm":0}),
        json!({"tolerance_mm":true}),
        json!({"tolerance_mm":1e-30}),
        json!({"z":200,"tolerance_mm":1e-10}),
    ] {
        assert!(fit(parameters.clone()).is_err(), "{parameters}");
    }
}
