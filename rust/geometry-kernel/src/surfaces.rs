// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Owned immutable sampled solids. No pointer, callback or mutable Python alias.
use crate::{
    precision::{self, Result},
    solid::{Face, P3, Part},
};
use serde_json::{Value, json};
use std::collections::HashMap;
use std::sync::{
    Arc, Mutex, OnceLock,
    atomic::{AtomicUsize, Ordering},
};

pub(crate) type Levels = Vec<Vec<Vec<P3>>>;
const MAX_BYTES: usize = 64 * 1024 * 1024;
const MAX_HANDLES: usize = 96;
const MAX_CURSORS: usize = 32;
static BYTES: AtomicUsize = AtomicUsize::new(0);
fn reserve(bytes: usize) -> bool {
    let mut current = BYTES.load(Ordering::Relaxed);
    loop {
        let Some(next) = current.checked_add(bytes).filter(|n| *n <= MAX_BYTES) else {
            return false;
        };
        match BYTES.compare_exchange_weak(current, next, Ordering::Relaxed, Ordering::Relaxed) {
            Ok(_) => return true,
            Err(actual) => current = actual,
        }
    }
}

struct SampledPlan {
    sections: Arc<Vec<crate::solid::Section>>,
    refinements: Vec<Vec<usize>>,
    report: Value,
}

pub(crate) struct Surface {
    pub part: Part,
    sections: Mutex<Option<Arc<SampledPlan>>>,
    rings: Mutex<Option<Arc<Levels>>>,
    caps: Mutex<HashMap<usize, Arc<Vec<[P3; 3]>>>>,
    charged: AtomicUsize,
}
impl Drop for Surface {
    fn drop(&mut self) {
        BYTES.fetch_sub(self.charged.load(Ordering::Relaxed), Ordering::Relaxed);
    }
}
fn loops_bytes<const N: usize>(loops: &[Vec<[f64; N]>]) -> usize {
    std::mem::size_of_val(loops) + loops.iter().map(|l| l.capacity() * N * 8).sum::<usize>()
}
fn part_bytes(p: &Part) -> usize {
    std::mem::size_of::<Surface>()
        + p.outer.capacity() * 16
        + loops_bytes(&p.holes)
        + p.frame.capacity() * 24
        + p.mesh.iter().map(|f| loops_bytes(f)).sum::<usize>()
        + p.mesh.capacity() * std::mem::size_of::<Face>()
        + p.stations.capacity() * std::mem::size_of::<crate::solid::Station>()
        + p.stations
            .iter()
            .map(|s| {
                s.outer.capacity() * 16
                    + s.holes.as_ref().map_or(0, |v| loops_bytes(v))
                    + s.material_outer.as_ref().map_or(0, |v| v.capacity() * 24)
                    + s.material_holes.as_ref().map_or(0, |v| loops_bytes(v))
            })
            .sum::<usize>()
}
impl Surface {
    fn new(part: Part, charged: usize) -> Self {
        Self {
            part,
            sections: Mutex::new(None),
            rings: Mutex::new(None),
            caps: Mutex::new(HashMap::new()),
            charged: AtomicUsize::new(charged),
        }
    }
    pub fn rings(&self) -> Result<Arc<Levels>> {
        if let Some(r) = self
            .rings
            .lock()
            .map_err(|_| "Surface lock poisoned")?
            .as_ref()
        {
            return Ok(r.clone());
        }
        crate::protocol::control_check()?;
        let plan = self.plan()?;
        let rings = Arc::new(
            self.part
                .rings_from(plan.sections.iter().cloned(), &plan.refinements)?,
        );
        crate::protocol::control_check()?;
        let bytes = std::mem::size_of::<Levels>()
            + std::mem::size_of_val(rings.as_slice())
            + rings.iter().map(|l| loops_bytes(l)).sum::<usize>();
        // A full cache never changes the geometry or the accepted sample count.
        let mut slot = self.rings.lock().map_err(|_| "Surface lock poisoned")?;
        if let Some(r) = slot.as_ref() {
            return Ok(r.clone());
        }
        if reserve(bytes) {
            self.charged.fetch_add(bytes, Ordering::Relaxed);
            *slot = Some(rings.clone());
        }
        Ok(rings)
    }

    pub(crate) fn sections(&self) -> Result<Arc<Vec<crate::solid::Section>>> {
        Ok(self.plan()?.sections.clone())
    }

    fn plan(&self) -> Result<Arc<SampledPlan>> {
        if let Some(value) = self
            .sections
            .lock()
            .map_err(|_| "Section cache lock poisoned")?
            .as_ref()
        {
            return Ok(value.clone());
        }
        crate::protocol::control_check()?;
        let sampling = crate::sampling::build(&self.part)?;
        let sections = Arc::new(sampling.sections);
        crate::protocol::control_check()?;
        let bytes = sections.capacity() * std::mem::size_of::<crate::solid::Section>()
            + sections
                .iter()
                .map(|(_, _, p)| p.capacity() * 16)
                .sum::<usize>()
            + std::mem::size_of::<SampledPlan>()
            + sampling.refinements.capacity() * std::mem::size_of::<Vec<usize>>()
            + sampling
                .refinements
                .iter()
                .map(|r| r.capacity() * std::mem::size_of::<usize>())
                .sum::<usize>()
            + sampling.report.to_string().len() * 8
            + 64;
        let plan = Arc::new(SampledPlan {
            sections,
            refinements: sampling.refinements,
            report: sampling.report,
        });
        let mut slot = self
            .sections
            .lock()
            .map_err(|_| "Section cache lock poisoned")?;
        if let Some(value) = slot.as_ref() {
            return Ok(value.clone());
        }
        if reserve(bytes) {
            self.charged.fetch_add(bytes, Ordering::Relaxed);
            *slot = Some(plan.clone());
        }
        Ok(plan)
    }

    fn triangles(&self, ordinal: usize, face: &Face) -> Result<Arc<Vec<[P3; 3]>>> {
        let cacheable = face.iter().map(Vec::len).sum::<usize>() >= 32;
        if cacheable
            && let Some(value) = self
                .caps
                .lock()
                .map_err(|_| "Cap cache lock poisoned")?
                .get(&ordinal)
        {
            return Ok(value.clone());
        }
        let triangles = Arc::new(crate::solid::triangulate(face)?);
        crate::protocol::control_check()?;
        if cacheable {
            let mut caps = self.caps.lock().map_err(|_| "Cap cache lock poisoned")?;
            if let Some(value) = caps.get(&ordinal) {
                return Ok(value.clone());
            }
            // Charge successful cap snapshots to the existing global 64 MiB
            // surface budget. A full cache recomputes, never coarsens or fails.
            let bytes = triangles.capacity() * std::mem::size_of::<[P3; 3]>() + 128;
            if caps.len() < 8 && reserve(bytes) {
                self.charged.fetch_add(bytes, Ordering::Relaxed);
                caps.insert(ordinal, triangles.clone());
            }
        }
        Ok(triangles)
    }
}
struct Cursor {
    surface: Arc<Surface>,
    levels: Arc<Levels>,
    position: crate::solid::FacePosition,
    triangles: Arc<Vec<[P3; 3]>>,
    face_ordinal: usize,
    triangle_index: usize,
    kind: String,
}
impl Cursor {
    fn new(surface: Arc<Surface>, kind: String) -> Result<Self> {
        let levels = if surface.part.mesh.is_empty() {
            surface.rings()?
        } else {
            Arc::new(Vec::new())
        };
        crate::solid::validate_levels(&surface.part, &levels)?;
        Ok(Self {
            surface,
            levels,
            position: crate::solid::FacePosition::default(),
            triangles: Arc::new(Vec::new()),
            face_ordinal: 0,
            triangle_index: 0,
            kind,
        })
    }
    fn next(&mut self) -> Option<Face> {
        let face = crate::solid::next_face(&self.surface.part, &self.levels, &mut self.position);
        if face.is_some() {
            self.face_ordinal += 1;
        }
        face
    }
    fn triangle(&mut self) -> Result<Option<[P3; 3]>> {
        loop {
            if self.triangle_index < self.triangles.len() {
                let t = self.triangles[self.triangle_index];
                self.triangle_index += 1;
                return Ok(Some(t));
            }
            let Some(face) = self.next() else {
                return Ok(None);
            };
            // The packet loop already checks each record. Preserve the exact
            // existing triangle without a redundant triangulator allocation.
            if face.len() == 1 && face[0].len() == 3 {
                return Ok(Some([face[0][0], face[0][1], face[0][2]]));
            }
            self.triangles = self.surface.triangles(self.face_ordinal - 1, &face)?;
            self.triangle_index = 0;
        }
    }
}

/// The interference checker consumes the exact shared facets without exporting
/// and reparsing their coordinates. Its existing face/assembly limits still apply.
pub(crate) fn collision_triangles(a: &Value, limit: usize) -> Result<Vec<[P3; 3]>> {
    let mut cursor = Cursor::new(get(a)?, "triangles".into())?;
    let mut result = Vec::new();
    while let Some(face) = cursor.next() {
        crate::protocol::control_check()?;
        if face.iter().map(Vec::len).sum::<usize>() > 40_000 {
            return Err("Face vertex limit (40000) exceeded".into());
        }
        if face.len() == 1 && face[0].len() == 3 {
            if result.len() >= limit {
                return Err("Assembly triangle limit exceeded".into());
            }
            result.push([face[0][0], face[0][1], face[0][2]]);
            continue;
        }
        let triangles = cursor.surface.triangles(cursor.face_ordinal - 1, &face)?;
        if result.len() + triangles.len() > limit {
            return Err("Assembly triangle limit exceeded".into());
        }
        for (i, triangle) in triangles.iter().enumerate() {
            if i % 128 == 0 {
                crate::protocol::control_check()?;
            }
            result.push(*triangle);
        }
    }
    Ok(result)
}
#[derive(Default)]
struct Registry {
    next: u64,
    surfaces: HashMap<u64, Arc<Surface>>,
    cursors: HashMap<u64, Arc<Mutex<Option<Cursor>>>>,
}
impl Registry {
    fn id(&mut self) -> Result<u64> {
        self.next = self
            .next
            .checked_add(1)
            .filter(|n| *n < (1u64 << 53))
            .ok_or("Surface handle space exhausted")?;
        Ok(self.next)
    }
}
fn registry() -> &'static Mutex<Registry> {
    static REGISTRY: OnceLock<Mutex<Registry>> = OnceLock::new();
    REGISTRY.get_or_init(|| Mutex::new(Registry::default()))
}
fn handle(a: &Value) -> Result<u64> {
    a["handle"]
        .as_u64()
        .filter(|h| *h > 0)
        .ok_or("Invalid surface handle".into())
}
pub(crate) fn get(a: &Value) -> Result<Arc<Surface>> {
    if a.get("handle").is_some() {
        registry()
            .lock()
            .map_err(|_| "Surface registry poisoned")?
            .surfaces
            .get(&handle(a)?)
            .cloned()
            .ok_or("Unknown or released surface handle".into())
    } else {
        Ok(Arc::new(Surface::new(Part::read(&a["part"])?, 0)))
    }
}
pub(crate) fn call(op: &str, a: &Value) -> Result<Value> {
    match op {
        "surface_create" => {
            let normalized = precision::sampled_arguments(&a["part"])?;
            let part = Part::read(&normalized)?;
            let bytes = part_bytes(&part);
            crate::protocol::control_check()?;
            let mut r = registry().lock().map_err(|_| "Surface registry poisoned")?;
            if r.surfaces.len() >= MAX_HANDLES || !reserve(bytes) {
                return Ok(json!({"handle":null,"retry":bytes<=MAX_BYTES}));
            }
            let id = match r.id() {
                Ok(id) => id,
                Err(e) => {
                    BYTES.fetch_sub(bytes, Ordering::Relaxed);
                    return Err(e);
                }
            };
            r.surfaces.insert(id, Arc::new(Surface::new(part, bytes)));
            Ok(json!({"handle":id}))
        }
        "surface_release" => {
            registry()
                .lock()
                .map_err(|_| "Surface registry poisoned")?
                .surfaces
                .remove(&handle(a)?);
            Ok(Value::Null)
        }
        "surface_stats" => {
            let r = registry().lock().map_err(|_| "Surface registry poisoned")?;
            Ok(
                json!({"surfaces":r.surfaces.len(),"cursors":r.cursors.len(),"bytes":BYTES.load(Ordering::Relaxed),
                "max_bytes":MAX_BYTES,"max_surfaces":MAX_HANDLES,"max_cursors":MAX_CURSORS}),
            )
        }
        "surface_cursor_create" => {
            let normalized = precision::sampled_arguments(a)?;
            let kind = a["kind"].as_str().unwrap_or("faces");
            if !["faces", "triangles"].contains(&kind) {
                return Err("Invalid surface cursor kind".into());
            }
            let cursor = Cursor::new(get(&normalized)?, kind.into())?;
            let mut r = registry().lock().map_err(|_| "Surface registry poisoned")?;
            if r.cursors.len() >= MAX_CURSORS {
                return Err("Surface cursor resource limit exceeded".into());
            }
            let id = r.id()?;
            r.cursors.insert(id, Arc::new(Mutex::new(Some(cursor))));
            Ok(json!({"handle":id}))
        }
        "surface_cursor_release" => {
            registry()
                .lock()
                .map_err(|_| "Surface registry poisoned")?
                .cursors
                .remove(&handle(a)?);
            Ok(Value::Null)
        }
        _ => Err("Unknown surface operation".into()),
    }
}
pub(crate) fn solid_call(op: &str, a: &Value) -> Result<Value> {
    let surface = get(a)?;
    if op == "solid_sampling" {
        return Ok(surface.plan()?.report.clone());
    }
    if op == "solid_sections" {
        return Ok(json!(surface.sections()?.iter().map(|(z,angle,outer)| {
            let base=*outer==surface.part.outer;
            json!({"z":z,"angle":angle,"base":base,"outer":if base{Value::Null}else{json!(outer)}})
        }).collect::<Vec<_>>()));
    }
    if op == "solid_bounds" {
        let mut low = [f64::INFINITY; 3];
        let mut high = [f64::NEG_INFINITY; 3];
        let mut include = |point: P3| -> Result<()> {
            for axis in 0..3 {
                let value = point[axis];
                if !value.is_finite() {
                    return Err("Non-finite nominal geometry.".into());
                }
                // Keep traversal and strict comparisons identical to Python,
                // including the first signed zero rather than f64::min's rule.
                if value < low[axis] {
                    low[axis] = value;
                }
                if value > high[axis] {
                    high[axis] = value;
                }
            }
            Ok(())
        };
        if surface.part.mesh.is_empty() {
            for level in surface.rings()?.iter() {
                crate::protocol::control_check()?;
                for contour in level {
                    for point in contour {
                        include(*point)?;
                    }
                }
            }
        } else {
            for face in &surface.part.mesh {
                crate::protocol::control_check()?;
                for contour in face {
                    for p in contour {
                        include(surface.part.point([p[0], p[1]], p[2], 0.))?;
                    }
                }
            }
        }
        if !low.iter().chain(&high).all(|q| q.is_finite()) {
            return Err("No finite solid geometry.".into());
        }
        return Ok(json!([low, high]));
    }
    if op == "solid_rings" {
        return Ok(json!(surface.rings()?.as_ref()));
    }
    if op == "solid_signature" {
        let levels = if surface.part.mesh.is_empty() {
            surface.rings()?
        } else {
            Arc::new(Vec::new())
        };
        return crate::solid::signature_faces(crate::solid::Faces::new(&surface.part, levels)?);
    }
    crate::solid::call_part(op, a, &surface.part)
}
pub(crate) fn triangle_packet(a: &Value, stl: bool) -> Result<Vec<u8>> {
    let id = handle(a)?;
    let entry = registry()
        .lock()
        .map_err(|_| "Surface registry poisoned")?
        .cursors
        .get(&id)
        .cloned()
        .ok_or("Unknown or released surface cursor")?;
    let mut cursor = entry
        .lock()
        .map_err(|_| "Surface cursor poisoned")?
        .take()
        .ok_or("Surface cursor is busy")?;
    let result = (|| {
        if cursor.kind != "triangles" {
            return Err("Surface cursor kind mismatch".into());
        }
        let limit = a["limit"].as_u64().unwrap_or(4096);
        if !(1..=16384).contains(&limit) {
            return Err("Invalid triangle chunk size".into());
        }
        let mut output = vec![0; 5];
        let mut count = 0;
        let mut done = false;
        for _ in 0..limit {
            crate::protocol::control_check()?;
            let Some(triangle) = cursor.triangle()? else {
                done = true;
                break;
            };
            crate::solid::append_triangle(&mut output, triangle, stl, &mut count)?;
        }
        output[1..5].copy_from_slice(&count.to_le_bytes());
        Ok((output, done))
    })();
    match result {
        Ok((packet, done)) => {
            if done {
                registry()
                    .lock()
                    .map_err(|_| "Surface registry poisoned")?
                    .cursors
                    .remove(&id);
            } else {
                *entry.lock().map_err(|_| "Surface cursor poisoned")? = Some(cursor);
            }
            Ok(packet)
        }
        Err(error) => {
            registry()
                .lock()
                .map_err(|_| "Surface registry poisoned")?
                .cursors
                .remove(&id);
            Err(error)
        }
    }
}
pub(crate) fn faces_packet(a: &Value) -> Result<Vec<u8>> {
    let id = handle(a)?;
    let entry = registry()
        .lock()
        .map_err(|_| "Surface registry poisoned")?
        .cursors
        .get(&id)
        .cloned()
        .ok_or("Unknown or released surface cursor")?;
    let mut cursor = entry
        .lock()
        .map_err(|_| "Surface cursor poisoned")?
        .take()
        .ok_or("Surface cursor is busy")?;
    let result = (|| {
        if cursor.kind != "faces" {
            return Err("Surface cursor kind mismatch".into());
        }
        let count = a["limit"].as_u64().unwrap_or(1024);
        if !(1..=4096).contains(&count) {
            return Err("Invalid surface chunk size".into());
        }
        let mut packet = crate::geometry_data::Packet::default();
        let mut rows = Vec::new();
        let mut done = false;
        for _ in 0..count {
            crate::protocol::control_check()?;
            let Some(face) = cursor.next() else {
                done = true;
                break;
            };
            rows.push(
                face.iter()
                    .map(|l| packet.points(l))
                    .collect::<Result<Vec<_>>>()?,
            );
        }
        Ok((packet.finish(json!({"faces":rows,"done":done}))?, done))
    })();
    match result {
        Ok((packet, done)) => {
            if done {
                registry()
                    .lock()
                    .map_err(|_| "Surface registry poisoned")?
                    .cursors
                    .remove(&id);
            } else {
                *entry.lock().map_err(|_| "Surface cursor poisoned")? = Some(cursor);
            }
            Ok(packet)
        }
        Err(error) => {
            registry()
                .lock()
                .map_err(|_| "Surface registry poisoned")?
                .cursors
                .remove(&id);
            Err(error)
        }
    }
}
