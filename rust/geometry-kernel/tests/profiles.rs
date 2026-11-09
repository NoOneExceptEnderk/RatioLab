// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
use ratiolab_geometry::{
    profiles::{inv_roll, sample},
    request,
};
use serde_json::json;
use std::f64::consts::PI;
#[test]
fn refinement_exhaustion_is_an_error_not_an_accepted_triangle() {
    let f = |t: f64| [t, t * t];
    assert!(sample(&f, 0., 1., 1e-30, false).is_err());
    let points = sample(&f, 0., 1., 0.001, false).unwrap();
    assert!(points.len() > 10);
    for pair in points.windows(2) {
        let x = (pair[0][0] + pair[1][0]) / 2.;
        let chord = (pair[0][1] + pair[1][1]) / 2.;
        assert!((chord - x * x).abs() <= 0.00101);
    }
}
#[test]
fn stable_involute_resolves_the_near_base_branch() {
    let t = 1e-8;
    let value = inv_roll(t);
    assert!((value / t.powi(3) - 1. / 3.).abs() < 1e-15);
    assert_eq!(inv_roll(0.), 0.);
}
#[test]
fn internal_tip_is_on_the_void_side_and_external_tip_on_the_material_side() {
    for internal in [false, true] {
        let q=request(&json!({"protocol":1,"operation":"involute_profile","parameters":{"z":72,"mt":2,"internal":internal}})).unwrap();
        let points = q["points"].as_array().unwrap();
        let radii: Vec<_> = points
            .iter()
            .map(|p| p[0].as_f64().unwrap().hypot(p[1].as_f64().unwrap()))
            .collect();
        let min = radii.iter().copied().fold(f64::INFINITY, f64::min);
        let max = radii.iter().copied().fold(0., f64::max);
        assert!((min - if internal { 70. } else { 69.5 }).abs() < 1e-7);
        assert!((max - if internal { 74.5 } else { 74. }).abs() < 1e-7);
        let tooth = &q["metadata"]["tooth_thickness"];
        assert!((tooth["pair_backlash_transverse_mm"].as_f64().unwrap() - 0.15).abs() < 1e-12);
    }
}
#[test]
fn planar_annulus_caps_keep_the_hole_and_boundary_orientation() {
    let circle = |r: f64, reverse: bool| {
        (0..24)
            .map(|i| {
                let a = if reverse { -1. } else { 1. } * 2. * PI * i as f64 / 24.;
                [r * a.cos(), r * a.sin(), 0.]
            })
            .collect::<Vec<_>>()
    };
    let outer = circle(10., false);
    let inner = circle(4., true);
    let r = request(
        &json!({"protocol":1,"operation":"solid_triangulate","parameters":{"face":[outer,inner]}}),
    )
    .unwrap();
    let mut total = 0.;
    for tri in r.as_array().unwrap() {
        let p: Vec<[f64; 3]> = serde_json::from_value(tri.clone()).unwrap();
        let area = ((p[1][0] - p[0][0]) * (p[2][1] - p[0][1])
            - (p[1][1] - p[0][1]) * (p[2][0] - p[0][0]))
            / 2.;
        assert!(area > 0.);
        total += area;
        let center = [
            (p[0][0] + p[1][0] + p[2][0]) / 3.,
            (p[0][1] + p[1][1] + p[2][1]) / 3.,
        ];
        assert!(center[0].hypot(center[1]) >= 4. * (PI / 24.).cos() - 1e-10);
    }
    let exact_polygon_area = 24. * (2. * PI / 24.).sin() / 2. * (100. - 16.);
    assert!((total - exact_polygon_area).abs() < 1e-10);
}
#[test]
fn synchronous_abi_frees_its_results_and_reports_invalid_requests() {
    let data = br#"{"protocol":1,"operation":"capabilities","parameters":{}}"#;
    for _ in 0..100 {
        unsafe {
            let result = ratiolab_geometry::protocol::ratiolab_request(data.as_ptr(), data.len());
            assert!(!result.is_null());
            let len = ratiolab_geometry::protocol::ratiolab_result_length(result);
            let out = std::slice::from_raw_parts(result as *const u8, len);
            let q: serde_json::Value = serde_json::from_slice(out).unwrap();
            assert_eq!(q["ok"], true);
            ratiolab_geometry::protocol::ratiolab_free(result);
        }
    }
    let result: serde_json::Value =
        serde_json::from_str(&ratiolab_geometry::dispatch("garbage")).unwrap();
    assert_eq!(result["ok"], false);
}

#[test]
fn internal_half_dispatch_does_not_enter_the_clearance_namespace() {
    let r =
        request(&json!({"protocol":1,"operation":"internal_half","parameters":{"z":72,"mt":2}}))
            .unwrap();
    assert_eq!(r["metadata"]["generated"], false);
    assert!(r["points"].as_array().unwrap().len() > 4);
    let bad = request(&json!({"protocol":1,"operation":"internal_unknown","parameters":{}}));
    assert!(bad.unwrap_err().contains("Unknown geometry operation"));
}

#[test]
fn generating_reference_allowance_is_explicit_and_not_a_negative_pair_backlash() {
    let params = json!({"teeth":60,"module":2,"backlash":-0.15});
    assert!(
        request(&json!({"protocol":1,"operation":"cylindrical_dimensions","parameters":params}))
            .is_err()
    );
    let mut cutter = params;
    cutter["cutter_allowance"] = json!(true);
    let r =
        request(&json!({"protocol":1,"operation":"cylindrical_dimensions","parameters":cutter}))
            .unwrap();
    assert_eq!(
        r["values"]["normal_reference_arc_with_allowance_mm"],
        "3.21659265358979323846"
    );
}
