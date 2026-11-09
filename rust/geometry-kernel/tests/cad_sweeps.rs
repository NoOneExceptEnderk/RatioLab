// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
use ratiolab_geometry::request;
use serde_json::{Value, json};

fn sweep(parameters: Value) -> Result<Value, String> {
    request(&json!({"protocol":1,"operation":"cad_cylindrical_geometry","parameters":parameters}))
}

#[test]
fn tensor_sweep_budgets_cover_profile_and_axial_interpolation() {
    for internal in [false, true] {
        let result=sweep(json!({"z":66,"mt":2.128355544951824,"depth":2,
            "pressure":21.172832185162978,"normal_pressure":20,"width":25,"twist_deg":11,
            "internal":internal,"circular_radius_mm":if internal{77.74}else{3.},"tolerance_mm":0.001})).unwrap();
        let bound = result["sweep"]["surface_interpolation_bound_mm"]
            .as_f64()
            .unwrap();
        let profile = result["sweep"]["profile_bound_mm"].as_f64().unwrap();
        let axial = result["sweep"]["axial_bound_mm"].as_f64().unwrap();
        assert!(axial > 0. && bound < 0.001 && bound >= profile && bound >= axial);
        assert_eq!(result["internal"], internal);
        for patch in result["patches"].as_array().unwrap() {
            let poles = patch["poles"].as_array().unwrap();
            for row in poles {
                let row = row.as_array().unwrap();
                assert_eq!(row[0][2], 0.);
                assert_eq!(row.last().unwrap()[2], 25.);
            }
            assert!(patch["weights"].as_array().unwrap().iter().all(|row| {
                row.as_array()
                    .unwrap()
                    .iter()
                    .all(|w| w.as_f64().unwrap() > 0.)
            }));
        }
    }
}

#[test]
fn zero_twist_has_no_axial_approximation_error() {
    let result =
        sweep(json!({"z":24,"mt":2,"width":10,"twist_deg":0,"circular_radius_mm":3})).unwrap();
    assert_eq!(result["sweep"]["axial_bound_mm"], 0.);
    assert_eq!(result["sweep"]["intervals"], 1);
}

#[test]
fn invalid_blanks_and_exhausted_surfaces_are_rejected() {
    for parameters in [
        json!({"width":-1}),
        json!({"internal":true,"z":66,"circular_radius_mm":1}),
        json!({"z":24,"twist_deg":180,"tolerance_mm":1e-6}),
        json!({"tolerance_mm":1e-30}),
    ] {
        assert!(sweep(parameters.clone()).is_err(), "{parameters}");
    }
}
