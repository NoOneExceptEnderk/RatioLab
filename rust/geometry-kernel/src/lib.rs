// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! One numerical core for the desktop and browser adapters.
//! Lengths are millimetres. JSON decimal strings preserve the caller's input.

pub mod buffers;
pub mod cad_curves;
mod cad_splines;
mod cad_sweeps;
pub mod cylindrical;
mod diagnostic;
mod enclosure;
mod error_budget;
pub mod exact;
mod geometry_data;
pub mod precision;
pub mod profiles;
pub mod protocol;
mod tooth_tips;
mod total_profile;
mod total_sweep;
pub use protocol::{dispatch, request};

pub mod bevel;
mod bevel_pair;
mod construction_interval;
mod face;
mod hypoid;
pub mod wave;

pub mod wave_envelope;

pub mod worm;

mod preview;
mod sampling;
pub mod solid;
mod surfaces;

pub mod measurement;

pub mod kinematics;

pub mod engineering;
mod meshing;

pub mod internal_mesh;

pub mod affine;
pub mod collision;
pub mod construction;
mod nominal;
pub mod planar;
mod rack_drive;
