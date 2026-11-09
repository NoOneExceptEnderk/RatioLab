// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Typed construction data and lossless binary64 coordinate transport.
use crate::{precision::Result, profiles::Point};
use serde::Serialize;
use serde_json::{Value, json};

#[derive(Serialize)]
pub(crate) struct Station {
    pub z: f64,
    pub outer: Vec<Point>,
    pub holes: Vec<Vec<Point>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub material_outer: Option<Vec<[f64; 3]>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub material_holes: Option<Vec<Vec<[f64; 3]>>>,
}
impl Station {
    pub fn new(z: f64, outer: Vec<Point>, holes: Vec<Vec<Point>>) -> Self {
        Self {
            z,
            outer,
            holes,
            material_outer: None,
            material_holes: None,
        }
    }
    fn packet(&self, p: &mut Packet) -> Result<Value> {
        let mut v =
            json!({"z":self.z,"outer":p.points(&self.outer)?,"holes":p.loops(&self.holes)?});
        if let Some(m) = &self.material_outer {
            v["material_outer"] = p.points(m)?;
        }
        if let Some(m) = &self.material_holes {
            v["material_holes"] = p.loops(m)?;
        }
        Ok(v)
    }
}

#[derive(Serialize)]
pub(crate) struct Part {
    pub name: String,
    pub outer: Vec<Point>,
    pub holes: Vec<Vec<Point>>,
    pub stations: Vec<Station>,
    // One contiguous block, rather than a JSON descriptor for each triangle.
    // Empty for all section-based constructions, preserving their old packets.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub mesh_triangle_points: Vec<[f64; 3]>,
    #[serde(flatten)]
    pub extra: Value,
}
impl Part {
    pub fn new(name: &str, outer: Vec<Point>, holes: Vec<Vec<Point>>, width: f64) -> Self {
        Self {
            name: name.into(),
            outer,
            holes,
            stations: Vec::new(),
            mesh_triangle_points: Vec::new(),
            extra: json!({"width":width}),
        }
    }
    fn packet(&self, p: &mut Packet) -> Result<Value> {
        let mut v = self.extra.clone();
        v["name"] = json!(self.name);
        v["outer"] = p.points(&self.outer)?;
        v["holes"] = p.loops(&self.holes)?;
        v["stations"] = json!(
            self.stations
                .iter()
                .map(|s| s.packet(p))
                .collect::<Result<Vec<_>>>()?
        );
        if !self.mesh_triangle_points.is_empty() {
            if self.mesh_triangle_points.len() % 3 != 0
                || self.mesh_triangle_points.len() / 3 > 250000
            {
                return Err("Invalid construction triangle count".into());
            }
            v["mesh_triangle_points"] = p.points(&self.mesh_triangle_points)?;
        }
        Ok(v)
    }
}

#[derive(Serialize)]
pub(crate) struct Construction {
    pub parts: Vec<Part>,
    #[serde(flatten)]
    pub extra: Value,
}
impl Construction {
    pub fn packet(&self) -> Result<Vec<u8>> {
        let mut p = Packet::default();
        let mut v = self.extra.clone();
        v["parts"] = json!(
            self.parts
                .iter()
                .map(|part| part.packet(&mut p))
                .collect::<Result<Vec<_>>>()?
        );
        p.finish(v)
    }
}

#[derive(Default)]
pub(crate) struct Packet {
    bytes: Vec<u8>,
}
impl Packet {
    pub fn points<const N: usize>(&mut self, points: &[[f64; N]]) -> Result<Value> {
        if ![2, 3].contains(&N)
            || points.len().saturating_mul(N * 8)
                > crate::buffers::MAX_BYTES.saturating_sub(self.bytes.len())
        {
            return Err("Geometry coordinate buffer exceeds its resource limit".into());
        }
        let start = self.bytes.len() / 8;
        self.bytes.reserve(points.len() * N * 8);
        // One append per checked block, preserving every binary64 bit and
        // the existing checkpoint before each group of 1024 points.
        const POINTS: usize = 1024;
        let mut bytes = [0u8; POINTS * 3 * 8];
        for block in points.chunks(POINTS) {
            crate::protocol::control_check()?;
            for (point, destination) in block.iter().zip(bytes.chunks_exact_mut(N * 8)) {
                for (x, encoded) in point.iter().zip(destination.chunks_exact_mut(8)) {
                    if !x.is_finite() {
                        return Err("Nonfinite geometry coordinate".into());
                    }
                    encoded.copy_from_slice(&x.to_le_bytes());
                }
            }
            self.bytes.extend_from_slice(&bytes[..block.len() * N * 8]);
        }
        Ok(json!({"$ratiolab.f64/1":[start,points.len(),N]}))
    }
    fn loops<const N: usize>(&mut self, loops: &[Vec<[f64; N]>]) -> Result<Value> {
        Ok(json!(
            loops
                .iter()
                .map(|l| self.points(l))
                .collect::<Result<Vec<_>>>()?
        ))
    }
    pub fn finish(self, result: Value) -> Result<Vec<u8>> {
        let metadata =
            serde_json::to_vec(&json!({"format":"ratiolab.geometry-buffer/1","result":result}))
                .map_err(|e| e.to_string())?;
        if metadata.len() > 16 * 1024 * 1024
            || 5 + metadata.len() + self.bytes.len() > crate::buffers::MAX_BYTES
        {
            return Err("Geometry result exceeds its resource limit".into());
        }
        let mut output = Vec::with_capacity(5 + metadata.len() + self.bytes.len());
        output.push(0);
        output.extend_from_slice(&(metadata.len() as u32).to_le_bytes());
        output.extend_from_slice(&metadata);
        output.extend_from_slice(&self.bytes);
        Ok(output)
    }
}

#[cfg(test)]
mod packing_tests {
    use super::*;

    fn exact_blocks<const N: usize>() {
        let pattern = [
            0.,
            -0.,
            f64::from_bits(1),
            f64::MIN_POSITIVE,
            f64::MAX,
            -3.75,
        ];
        for count in [0, 1, 1023, 1024, 1025, 2049] {
            let points: Vec<[f64; N]> = (0..count)
                .map(|i| std::array::from_fn(|j| pattern[(i * N + j) % pattern.len()]))
                .collect();
            let expected: Vec<_> = points
                .iter()
                .flatten()
                .flat_map(|x| x.to_le_bytes())
                .collect();
            let mut packet = Packet::default();
            let first = packet.points(&points).unwrap();
            let second = packet.points(&points).unwrap();
            assert_eq!(first, json!({"$ratiolab.f64/1":[0,count,N]}));
            assert_eq!(second, json!({"$ratiolab.f64/1":[count*N,count,N]}));
            assert_eq!(packet.bytes, expected.repeat(2));
        }
    }

    #[test]
    fn binary64_blocks_preserve_bits_and_offsets_for_both_coordinate_widths() {
        exact_blocks::<2>();
        exact_blocks::<3>();
    }

    #[test]
    fn nonfinite_coordinates_are_rejected_in_initial_and_later_blocks() {
        for value in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            for index in [0, 1023, 1024, 2048] {
                let mut points = vec![[0.; 3]; 2049];
                points[index][2] = value;
                assert_eq!(
                    Packet::default().points(&points).unwrap_err(),
                    "Nonfinite geometry coordinate"
                );
            }
        }
    }

    #[test]
    fn unsupported_coordinate_widths_are_rejected_before_block_writing() {
        assert!(Packet::default().points(&[[0.; 0]]).is_err());
        assert!(Packet::default().points(&[[0.; 1]]).is_err());
        assert!(Packet::default().points(&[[0.; 4]]).is_err());
    }
}
