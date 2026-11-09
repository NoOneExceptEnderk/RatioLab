// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Owned binary results: status byte, little-endian u32 record count, records.
//! Errors use status 1 followed by UTF-8. No pointers into temporary geometry.
use crate::precision::{self, Result};
use serde_json::Value;

pub const MAX_BYTES: usize = 128 * 1024 * 1024;

fn execute(input: &[u8]) -> Result<Vec<u8>> {
    if input.len() > 64 * 1024 * 1024 {
        return Err("Input resource limit exceeded".into());
    }
    let request: Value = serde_json::from_slice(input).map_err(|e| format!("Invalid JSON: {e}"))?;
    if request["protocol"].as_u64() != Some(1) {
        return Err("Unsupported geometry protocol".into());
    }
    let op = request["operation"].as_str().ok_or("Missing operation")?;
    let a = request
        .get("parameters")
        .filter(|v| v.is_object())
        .ok_or("parameters must be an object")?;
    if op == "solid_faces_chunk" {
        return crate::surfaces::faces_packet(a);
    }
    if op == "preview_scene" {
        return crate::preview::packet(a);
    }
    if op == "web_mesh" {
        return crate::preview::web_packet(a);
    }
    if op == "collision_triangles" {
        return crate::collision::triangles_packet(a);
    }
    if op == "solid_stl_chunk" {
        return crate::surfaces::triangle_packet(a, true);
    }
    if op == "solid_triangles_chunk" {
        return crate::surfaces::triangle_packet(a, false);
    }
    // Constructors retain source expressions for named analytic metadata.
    if [
        "construction_worm",
        "construction_harmonic",
        "construction_rack",
        "construction_bevel_pair",
        "construction_hypoid",
        "construction_face",
    ]
    .contains(&op)
    {
        crate::protocol::control_check()?;
        return crate::construction::build(op, a)?.packet();
    }
    let normalized;
    let a = if precision::has_expression(a) {
        normalized = precision::sampled_arguments(a)?;
        &normalized
    } else {
        a
    };
    crate::protocol::control_check()?;
    if op == "planar_circles" {
        let specs = a["circles"]
            .as_array()
            .ok_or("Circle specification array required")?;
        if specs.len() > 4096 {
            return Err("Circle batch exceeds its resource limit".into());
        }
        let mut packet = crate::geometry_data::Packet::default();
        let rows = specs
            .iter()
            .map(|spec| packet.points(&crate::planar::circle_points(spec)?))
            .collect::<Result<Vec<_>>>()?;
        return packet.finish(serde_json::json!(rows));
    }
    if op == "solid_rings" {
        let surface = crate::surfaces::get(a)?;
        let mut packet = crate::geometry_data::Packet::default();
        let rows = surface
            .rings()?
            .iter()
            .map(|level| {
                level
                    .iter()
                    .map(|l| packet.points(l))
                    .collect::<Result<Vec<_>>>()
            })
            .collect::<Result<Vec<_>>>()?;
        return packet.finish(serde_json::json!(rows));
    }
    if op == "bevel_spiral_stations" {
        let mut packet = crate::geometry_data::Packet::default();
        let rows = crate::bevel::spiral_stations(a)?
            .iter()
            .map(|(z, outer)| Ok(serde_json::json!({"z":z,"outer":packet.points(outer)?})))
            .collect::<Result<Vec<_>>>()?;
        return packet.finish(serde_json::json!(rows));
    }
    if op == "affine_poses" {
        let matrices = crate::affine::poses(a)?;
        let mut output = Vec::with_capacity(5 + matrices.len() * 128);
        output.push(0);
        output.extend_from_slice(&(matrices.len() as u32).to_le_bytes());
        for m in matrices {
            for x in m {
                output.extend_from_slice(&x.to_le_bytes());
            }
        }
        return Ok(output);
    }
    if !["solid_triangles", "solid_stl"].contains(&op) {
        return Err(format!("Unknown binary operation: {op}"));
    }
    crate::solid::binary(a, op == "solid_stl")
}

pub fn dispatch(input: &[u8]) -> Vec<u8> {
    match std::panic::catch_unwind(|| execute(input)) {
        Ok(Ok(result)) => result,
        Ok(Err(message)) => [vec![1], message.into_bytes()].concat(),
        Err(_) => b"\x01Geometry calculation panicked".to_vec(),
    }
}
