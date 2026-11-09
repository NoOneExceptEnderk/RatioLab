// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
use crate::{
    cylindrical,
    precision::{self, Result},
};
use serde_json::{Value, json};
use std::cell::{Cell, RefCell};
use std::collections::VecDeque;
use std::ffi::{CStr, CString, c_char};

thread_local! {
    static CONTROL_CHECK: Cell<Option<extern "C" fn() -> i32>> = const { Cell::new(None) };
    // Immutable successful records only; exact sources, defaults and contract
    // version form the key. No design/mesh handles or caller callbacks retained.
    static DIMENSIONS_CACHE: RefCell<VecDeque<(Value, Value)>> = const { RefCell::new(VecDeque::new()) };
}

fn dimensions_key(a: &Value) -> Result<Value> {
    let mut key = serde_json::Map::new();
    for (name, default) in [
        ("teeth", None),
        ("module", None),
        ("pressure", Some("20")),
        ("helix", Some("0")),
        ("profile_shift", Some("0")),
        ("addendum", Some("1")),
        ("dedendum", Some("1.25")),
        ("topping_mm", Some("0")),
        ("backlash", Some("0.15")),
        ("width", Some("10")),
    ] {
        let raw = a
            .get(name)
            .cloned()
            .unwrap_or_else(|| json!(default.unwrap_or("")));
        let value = match crate::exact::expression(&raw)? {
            Some(r) => json!([r.numer().to_string(), r.denom().to_string()]),
            None => raw,
        };
        key.insert(name.into(), value);
    }
    key.insert(
        "internal".into(),
        a.get("internal").cloned().unwrap_or(json!(false)),
    );
    key.insert(
        "cutter_allowance".into(),
        json!(a["cutter_allowance"] == true),
    );
    let radius = match a.get("rack_tip_radius_mm").filter(|v| !v.is_null()) {
        Some(raw) => match crate::exact::expression(raw)? {
            Some(r) => json!([r.numer().to_string(), r.denom().to_string()]),
            None => raw.clone(),
        },
        None => Value::Null,
    };
    key.insert("rack_tip_radius_mm".into(), radius);
    Ok(json!([
        precision::BITS,
        precision::CHECK_BITS,
        precision::DECIMAL_PLACES,
        key
    ]))
}

pub(crate) fn control_check() -> Result<()> {
    if CONTROL_CHECK.with(|c| c.get().is_some_and(|check| check() != 0)) {
        Err("Calculation cancelled by its caller".into())
    } else {
        Ok(())
    }
}

struct CheckGuard(Option<extern "C" fn() -> i32>);
impl Drop for CheckGuard {
    fn drop(&mut self) {
        CONTROL_CHECK.with(|c| c.set(self.0));
    }
}

const ANALYTIC_OPERATIONS: &[&str] = &[
    "cylindrical_dimensions",
    "involute",
    "inverse_involute",
    "working_backlash",
    "inverse_working_backlash",
    "kinematic_solve",
    "differential_rates",
    "wolfrom_dimensions",
];
const SAMPLED_OPERATIONS: &[&str] = &[
    "spur_profile_error",
    "spur_total_profile_error",
    "cylindrical_total_surface_error",
    "enclose_numeric",
    "nominal_parallel_plan",
    "parallel_rates",
    "nominal_rack_plan",
    "rack_drive_dimensions",
    "construction_rack",
    "construction_bevel_pair",
    "construction_hypoid",
    "bevel_pair_generator",
    "hypoid_generator",
    "construction_face",
    "face_generator",
    "construction_enclosure",
    "cad_rack_source",
    "cad_cylindrical_source",
    "cad_spur_curves",
    "cad_cylindrical_geometry",
    "gear_part",
    "curve_point",
    "rack_parameters",
    "rack_point",
    "tooth_thickness",
    "external_half",
    "internal_half",
    "involute_profile",
    "cycloid_profile",
    "planar_polar",
    "planar_circle",
    "planar_transform",
    "planar_circle_info",
    "planar_clean",
    "planar_contains",
    "planar_material_point",
    "planar_ellipse_axes",
    "planar_refine_angles",
    "solid_point",
    "surface_create",
    "surface_release",
    "surface_stats",
    "surface_cursor_create",
    "surface_cursor_release",
    "solid_points",
    "solid_section_loops",
    "solid_sections",
    "solid_sampling",
    "solid_section_holes",
    "solid_rings",
    "solid_faces",
    "solid_signature",
    "solid_bounds",
    "solid_triangles",
    "solid_triangulate",
    "internal_plan",
    "internal_fixed_plan",
    "internal_verify_trace",
    "internal_axial",
    "internal_axial_derived",
    "internal_verify",
    "internal_pose_clearance",
    "internal_point_segment2",
    "internal_cross",
    "internal_inside",
    "engineering_dimensions",
    "engineering_mesh",
    "cylindrical_pair_audit",
    "engineering_forces",
    "measurement_span",
    "measurement_gauges",
    "measurement_default",
    "spherical_involute",
    "bevel_parameters",
    "bevel_spiral_trace",
    "bevel_spiral_stations",
    "bevel_cone_stations",
    "bevel_split_cheek",
    "bevel_split_bridge",
    "bevel_assembly_dimensions",
    "bevel_engagement",
    "bevel_section",
    "bevel_half",
    "bevel_point",
    "bevel_section_point",
    "wave_coefficients",
    "wave_eccentric",
    "wave_map",
    "wave_unmap",
    "wave_map_batch",
    "wave_material_vertices",
    "wave_circular_spline",
    "worm_screw_profile",
    "worm_surface",
    "worm_half",
    "worm_derivative",
    "worm_generator",
    "worm_contact",
    "worm_section",
    "worm_section_curve",
    "worm_section_angle",
    "worm_section_gap",
    "worm_wheel_sections",
    "wolfrom_exact_rates",
    "wolfrom_phases",
    "validate_number",
    "numeric_compatibility",
    "numeric_batch",
    "collision_create",
    "collision_create_surface",
    "collision_pose",
    "collision_stats",
    "collision_release",
    "collision_nearest",
    "collision_contains",
    "collision_distance",
    "collision_relation",
    "collision_point_triangle",
    "collision_segments",
    "collision_triangle_distance",
    "collision_ray_triangle",
    "collision_bounds",
    "collision_box_distance",
    "affine_multiply",
    "affine_rotation",
    "affine_transform",
    "affine_orbital",
    "affine_poses",
    "construction_worm",
    "construction_harmonic",
];

fn analytic(operation: &str, a: &Value, bits: usize) -> Result<Value> {
    match operation {
        "cylindrical_dimensions" => cylindrical::dimensions(a, bits),
        "involute" => cylindrical::involute(a, bits),
        "inverse_involute" => cylindrical::inverse_involute(a, bits),
        "kinematic_solve" => crate::kinematics::solve(a, bits),
        "differential_rates" => crate::kinematics::differential(a, bits),
        "wolfrom_dimensions" => crate::kinematics::wolfrom(a, bits),
        "inverse_working_backlash" => cylindrical::inverse_backlash(a, bits),
        "working_backlash" => cylindrical::working_backlash(a, bits),
        _ => Err(format!("Unknown geometry operation: {operation}")),
    }
}

pub fn request(input: &Value) -> Result<Value> {
    if input.get("protocol").and_then(Value::as_u64) != Some(1) {
        return Err("Unsupported geometry protocol".into());
    }
    let operation = input
        .get("operation")
        .and_then(Value::as_str)
        .ok_or("Missing operation")?;
    let args = input
        .get("parameters")
        .filter(|p| p.is_object())
        .ok_or("parameters must be an object")?;
    if operation == "capabilities" {
        let operations: Vec<_> = ANALYTIC_OPERATIONS
            .iter()
            .chain(SAMPLED_OPERATIONS.iter())
            .copied()
            .collect();
        return Ok(
            json!({"protocol":1,"implementation":"Rust","phase":"in_progress","operations":operations,
            "extended_precision_operations":ANALYTIC_OPERATIONS,"decimal_places":precision::DECIMAL_PLACES,
            "binary_operations":["solid_triangles","solid_stl","affine_poses","construction_worm","construction_harmonic","construction_rack","construction_bevel_pair","construction_hypoid","construction_face","bevel_spiral_stations","planar_circles","solid_rings","solid_faces_chunk","solid_triangles_chunk","solid_stl_chunk","preview_scene","web_mesh","collision_triangles"],"geometry_format":"ratiolab.geometry-buffer/1; JSON metadata and little-endian f64 coordinate blocks",
            "binary_format":"status byte; little-endian u32 count; f64 coordinates or 50-byte STL records",
            "sampled_coordinates":"binary64; explicit chord/refinement bounds apply",
            "references":["ISO 21771:2007","ISO 53:1998"],
            "scope":"geometric constructions and nominal calculations; no conformity or manufacturing-accuracy certification"}),
        );
    }
    if !ANALYTIC_OPERATIONS.contains(&operation) && !SAMPLED_OPERATIONS.contains(&operation) {
        return Err(format!("Unknown geometry operation: {operation}"));
    }
    if operation.starts_with("surface_") {
        return crate::surfaces::call(operation, args);
    }
    if operation == "spur_profile_error" {
        return crate::error_budget::spur(args);
    }
    if operation == "spur_total_profile_error" {
        return crate::total_profile::audit(args);
    }
    if operation == "cylindrical_total_surface_error" {
        return crate::total_sweep::audit(args);
    }
    if operation == "enclose_numeric" {
        return crate::enclosure::numeric(args);
    }
    if operation == "validate_number" {
        return precision::validate_number(args);
    }
    if operation == "numeric_compatibility" {
        return Ok(json!(precision::sampled_number(&args["value"])?));
    }
    if operation == "numeric_batch" {
        return precision::numeric_batch(args);
    }
    let normalized;
    let args = if !ANALYTIC_OPERATIONS.contains(&operation)
        && ![
            "gear_part",
            "engineering_dimensions",
            "engineering_mesh",
            "cylindrical_pair_audit",
            "construction_worm",
            "construction_harmonic",
            "nominal_parallel_plan",
            "nominal_rack_plan",
            "rack_drive_dimensions",
            "construction_rack",
            "construction_bevel_pair",
            "construction_hypoid",
            "bevel_pair_generator",
            "hypoid_generator",
            "construction_face",
            "face_generator",
            "cad_rack_source",
            "cad_cylindrical_source",
        ]
        .contains(&operation)
    {
        if precision::has_expression(args) {
            normalized = precision::sampled_arguments(args)?;
            &normalized
        } else {
            args
        }
    } else {
        args
    };
    if operation == "bevel_pair_generator" {
        return crate::bevel_pair::call(args);
    }
    if operation == "hypoid_generator" {
        return crate::hypoid::call(args);
    }
    if operation == "face_generator" {
        return crate::face::call(args);
    }
    if operation == "construction_enclosure" {
        return crate::construction_interval::call(args);
    }
    if operation == "gear_part" {
        return crate::profiles::gear_part(args);
    }
    if operation == "nominal_parallel_plan" {
        return crate::nominal::parallel(args);
    }
    if operation == "parallel_rates" {
        return crate::nominal::parallel_rates(args);
    }
    if operation == "nominal_rack_plan" {
        return crate::rack_drive::plan(args);
    }
    if operation == "rack_drive_dimensions" {
        return crate::rack_drive::dimensions(args);
    }
    if operation == "cad_rack_source" {
        return crate::rack_drive::cad(args);
    }
    if operation == "cad_cylindrical_source" {
        return crate::nominal::cylindrical_source(args);
    }
    if operation.starts_with("collision_") {
        return crate::collision::call(operation, args);
    }
    if operation.starts_with("affine_") {
        return crate::affine::call(operation, args);
    }
    if operation.starts_with("construction_") {
        return crate::construction::call(operation, args);
    }
    if operation.starts_with("planar_") {
        return crate::planar::call(operation, args);
    }
    if [
        "internal_plan",
        "internal_fixed_plan",
        "internal_verify_trace",
        "internal_axial",
        "internal_axial_derived",
        "internal_verify",
        "internal_pose_clearance",
        "internal_point_segment2",
        "internal_cross",
        "internal_inside",
    ]
    .contains(&operation)
    {
        return crate::internal_mesh::call(operation, args);
    }
    if operation.starts_with("engineering_") {
        return crate::engineering::call(operation, args);
    }
    if operation == "cylindrical_pair_audit" {
        return crate::meshing::audit(args);
    }
    if operation == "wolfrom_exact_rates" {
        return crate::kinematics::exact_wolfrom(args);
    }
    if operation == "wolfrom_phases" {
        return crate::kinematics::wolfrom_phases(args);
    }
    if operation.starts_with("measurement_") {
        return crate::measurement::call(operation, args);
    }
    if operation == "cad_spur_curves" {
        return crate::cad_splines::prepare_spur(crate::cad_curves::spur(args)?);
    }
    if operation == "cad_cylindrical_geometry" {
        return crate::cad_sweeps::cylindrical(args);
    }
    if operation.starts_with("solid_") {
        if args.get("handle").is_some() || operation == "solid_bounds" {
            return crate::surfaces::solid_call(operation, args);
        }
        return crate::solid::call(operation, args);
    }
    if operation.starts_with("worm_") {
        return crate::worm::call(operation, args);
    }
    if operation == "wave_circular_spline" {
        return crate::wave_envelope::call(args);
    }
    if operation.starts_with("wave_") {
        return crate::wave::call(operation, args);
    }
    if operation.starts_with("bevel_") || operation == "spherical_involute" {
        return crate::bevel::call(operation, args);
    }
    if [
        "curve_point",
        "rack_parameters",
        "rack_point",
        "tooth_thickness",
        "external_half",
        "internal_half",
        "involute_profile",
        "cycloid_profile",
    ]
    .contains(&operation)
    {
        return crate::profiles::call(operation, args);
    }
    control_check()?;
    let cache_key = if operation == "cylindrical_dimensions" {
        let key = dimensions_key(args)?;
        // Bound retained source size as well as entry count.
        (key.to_string().len() <= 16_384).then_some(key)
    } else {
        None
    };
    if let Some(key) = &cache_key
        && let Some(result) = DIMENSIONS_CACHE.with(|cache| {
            let mut cache = cache.borrow_mut();
            let index = cache.iter().position(|(k, _)| k == key)?;
            let entry = cache.remove(index)?;
            let result = entry.1.clone();
            cache.push_back(entry);
            Some(result)
        })
    {
        return Ok(result);
    }
    let result = analytic(operation, args, precision::BITS)?;
    let checked = analytic(operation, args, precision::CHECK_BITS)?;
    if result != checked {
        return Err(
            "Numerical resolution: independent working precisions disagree at 20 decimal places"
                .into(),
        );
    }
    let record = json!({"values":result,"precision":{"working_bits":precision::BITS,"check_bits":precision::CHECK_BITS,
        "decimal_places":precision::DECIMAL_PLACES,"agreement":true,
        "scope":"analytic numerical result; does not establish sampled surface or manufacturing accuracy"}});
    if let Some(key) = cache_key {
        DIMENSIONS_CACHE.with(|cache| {
            let mut cache = cache.borrow_mut();
            if cache.len() >= 64 {
                cache.pop_front();
            }
            cache.push_back((key, record.clone()));
        });
    }
    Ok(record)
}

pub fn dispatch(input: &str) -> String {
    let result = std::panic::catch_unwind(|| -> Result<Value> {
        if input.len() > 64 * 1024 * 1024 {
            return Err("Input resource limit exceeded".into());
        }
        let value: Value = serde_json::from_str(input).map_err(|e| format!("Invalid JSON: {e}"))?;
        request(&value)
    });
    let value = match result {
        Ok(Ok(result)) => json!({"ok":true,"result":result}),
        Ok(Err(message)) => json!({"ok":false,"error":{"code":"geometry_error","message":message}}),
        Err(_) => {
            json!({"ok":false,"error":{"code":"internal_error","message":"Geometry calculation panicked"}})
        }
    };
    value.to_string()
}

/// Execute a UTF-8 JSON request without embedding a Python runtime.
///
/// # Safety
/// `data` must point to `length` readable bytes for the duration of this call,
/// or be null. The caller must release the returned owned C string exactly once
/// with `ratiolab_free`, and must not modify it while another call reads it.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn ratiolab_request(data: *const u8, length: usize) -> *mut c_char {
    let output = if data.is_null() || length > 64 * 1024 * 1024 {
        "{\"ok\":false,\"error\":{\"code\":\"invalid_buffer\",\"message\":\"Invalid input buffer\"}}".to_owned()
    } else {
        let bytes = unsafe { std::slice::from_raw_parts(data, length) };
        match std::str::from_utf8(bytes) {
            Ok(s) => dispatch(s),
            Err(_) => {
                "{\"ok\":false,\"error\":{\"code\":\"invalid_utf8\",\"message\":\"Invalid UTF-8\"}}"
                    .into()
            }
        }
    };
    CString::new(output)
        .expect("JSON strings contain no unescaped NUL")
        .into_raw()
}

/// Execute a request with a cooperative native cancellation/deadline callback.
///
/// # Safety
/// The input/result ownership rules of `ratiolab_request` apply. `check` must
/// remain callable on this thread until this synchronous function returns; a
/// nonzero return requests cancellation. No callback or context is retained.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn ratiolab_request_checked(
    data: *const u8,
    length: usize,
    check: Option<extern "C" fn() -> i32>,
) -> *mut c_char {
    let previous = CONTROL_CHECK.with(|c| c.replace(check));
    let _guard = CheckGuard(previous);
    unsafe { ratiolab_request(data, length) }
}
/// Return the byte length of a kernel-owned result, excluding its NUL.
///
/// # Safety
/// `data` must be null or an unmodified, live result from `ratiolab_request`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn ratiolab_result_length(data: *const c_char) -> usize {
    if data.is_null() {
        0
    } else {
        unsafe { CStr::from_ptr(data) }.to_bytes().len()
    }
}
/// Release one kernel-owned result.
///
/// # Safety
/// `data` must be null or a live result from `ratiolab_request`. Release it once,
/// with no concurrent reads or outstanding references to its contents.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn ratiolab_free(data: *mut c_char) {
    if !data.is_null() {
        drop(unsafe { CString::from_raw(data) });
    }
}
#[unsafe(no_mangle)]
pub extern "C" fn ratiolab_alloc(length: usize) -> *mut u8 {
    if length == 0 || length > 64 * 1024 * 1024 {
        return std::ptr::null_mut();
    }
    Box::into_raw(vec![0u8; length].into_boxed_slice()) as *mut u8
}
/// Release a byte buffer allocated by `ratiolab_alloc`.
///
/// # Safety
/// `data` must be null or a live allocation returned by `ratiolab_alloc(length)`.
/// Supply its original length, release it once, and retain no live references.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn ratiolab_dealloc(data: *mut u8, length: usize) {
    if !data.is_null() && length > 0 && length <= 64 * 1024 * 1024 {
        drop(unsafe { Box::from_raw(std::ptr::slice_from_raw_parts_mut(data, length)) });
    }
}

/// Return an owned binary result handle. Release exactly once with buffer_free.
/// # Safety
/// The input must be null or point to `length` readable bytes during this call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn ratiolab_buffer_request(data: *const u8, length: usize) -> *mut Vec<u8> {
    let result = if data.is_null() || length > 64 * 1024 * 1024 {
        b"\x01Invalid input buffer".to_vec()
    } else {
        crate::buffers::dispatch(unsafe { std::slice::from_raw_parts(data, length) })
    };
    Box::into_raw(Box::new(result))
}

/// Synchronous cancellable binary request; retains no callback.
/// # Safety
/// Input rules of buffer_request apply; check must remain callable until return.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn ratiolab_buffer_request_checked(
    data: *const u8,
    length: usize,
    check: Option<extern "C" fn() -> i32>,
) -> *mut Vec<u8> {
    let previous = CONTROL_CHECK.with(|c| c.replace(check));
    let _guard = CheckGuard(previous);
    unsafe { ratiolab_buffer_request(data, length) }
}

/// # Safety
/// Supply a null or live binary result handle; retain it while reading the bytes.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn ratiolab_buffer_data(handle: *const Vec<u8>) -> *const u8 {
    if handle.is_null() {
        std::ptr::null()
    } else {
        unsafe { &*handle }.as_ptr()
    }
}
/// # Safety
/// Supply a null or live binary result handle.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn ratiolab_buffer_length(handle: *const Vec<u8>) -> usize {
    if handle.is_null() {
        0
    } else {
        unsafe { &*handle }.len()
    }
}
/// # Safety
/// Supply null or a live binary result handle, once, with no outstanding reads.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn ratiolab_buffer_free(handle: *mut Vec<u8>) {
    if !handle.is_null() {
        drop(unsafe { Box::from_raw(handle) });
    }
}

#[cfg(test)]
mod cache_tests {
    use super::*;
    #[test]
    fn repeated_exact_dimension_key_survives_more_than_one_cache_capacity() {
        DIMENSIONS_CACHE.with(|c| c.borrow_mut().clear());
        let parameters = json!({"teeth":24,"module":"2.00000000000000000001"});
        let key = dimensions_key(&parameters).unwrap();
        let original = request(
            &json!({"protocol":1,"operation":"cylindrical_dimensions","parameters":parameters}),
        )
        .unwrap();
        for i in 1..=80 {
            request(&json!({"protocol":1,"operation":"cylindrical_dimensions","parameters":{"teeth":24,"module":format!("2.{i:05}")}})).unwrap();
            if i % 8 == 0 {
                assert_eq!(request(&json!({"protocol":1,"operation":"cylindrical_dimensions","parameters":parameters})).unwrap(),original);
            }
        }
        DIMENSIONS_CACHE.with(|c| {
            let cache = c.borrow();
            assert_eq!(cache.len(), 64);
            assert_eq!(cache.back().unwrap().0, key);
        });
    }
}
