// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Bounded continuous separation of the actual transverse polygons. This
//! certificate excludes analytical sampling error, load and axial lofts.
use crate::{
    precision::Result,
    profiles::{Point, n, radius},
};
use serde_json::{Value, json};
use std::f64::consts::TAU;
const SCOPE: &str = "continuous separation of generated transverse polygons over one tooth period at neutral backlash; excludes analytic curve sampling error, loaded contact, CAD/STL axial interpolation, cutter and manufacturing checks";
type Box2 = [f64; 4];
#[derive(Clone)]
struct Segment {
    a: Point,
    b: Point,
    index: usize,
}
#[derive(Clone)]
struct Node {
    bounds: Box2,
    segments: Vec<Segment>,
    children: Option<(usize, usize)>,
}
struct Tree {
    nodes: Vec<Node>,
    root: usize,
}
fn bounds(a: Point, b: Point) -> Box2 {
    [
        a[0].min(b[0]),
        a[1].min(b[1]),
        a[0].max(b[0]),
        a[1].max(b[1]),
    ]
}
fn box_distance(a: Box2, b: Box2) -> f64 {
    let dx = 0f64.max(a[0] - b[2]).max(b[0] - a[2]);
    let dy = 0f64.max(a[1] - b[3]).max(b[1] - a[3]);
    dx * dx + dy * dy
}
fn cross(a: Point, b: Point, c: Point) -> f64 {
    (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
}
fn point_segment(p: Point, a: Point, b: Point) -> f64 {
    let (x, y) = (b[0] - a[0], b[1] - a[1]);
    let den = x * x + y * y;
    let t = if den > 0. {
        ((p[0] - a[0]) * x + (p[1] - a[1]) * y) / den
    } else {
        0.
    }
    .clamp(0., 1.);
    (p[0] - a[0] - t * x).powi(2) + (p[1] - a[1] - t * y).powi(2)
}
fn segment_distance(a: Point, b: Point, c: Point, d: Point) -> (f64, bool) {
    if cross(a, b, c) * cross(a, b, d) < 0. && cross(c, d, a) * cross(c, d, b) < 0. {
        return (0., true);
    }
    (
        point_segment(a, c, d)
            .min(point_segment(b, c, d))
            .min(point_segment(c, a, b))
            .min(point_segment(d, a, b)),
        false,
    )
}
fn inside(p: Point, l: &[Point]) -> bool {
    let mut result = false;
    for i in 0..l.len() {
        let a = l[i];
        let b = l[(i + 1) % l.len()];
        if (a[1] > p[1]) != (b[1] > p[1])
            && p[0] < (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1]) + a[0]
        {
            result = !result;
        }
    }
    result
}
impl Tree {
    fn new(points: &[Point]) -> Self {
        Self::selected(points, None)
    }
    fn selected(points: &[Point], selected: Option<&[usize]>) -> Self {
        fn build(nodes: &mut Vec<Node>, mut segments: Vec<Segment>) -> usize {
            let mut b = [
                f64::INFINITY,
                f64::INFINITY,
                f64::NEG_INFINITY,
                f64::NEG_INFINITY,
            ];
            for s in &segments {
                let q = bounds(s.a, s.b);
                for i in 0..2 {
                    b[i] = b[i].min(q[i]);
                    b[i + 2] = b[i + 2].max(q[i + 2]);
                }
            }
            let index = nodes.len();
            nodes.push(Node {
                bounds: b,
                segments: Vec::new(),
                children: None,
            });
            if segments.len() <= 6 {
                nodes[index].segments = segments;
            } else {
                let axis = if b[2] - b[0] >= b[3] - b[1] { 0 } else { 1 };
                segments
                    .sort_by(|a, b| (a.a[axis] + a.b[axis]).total_cmp(&(b.a[axis] + b.b[axis])));
                let right = segments.split_off(segments.len() / 2);
                let left = build(nodes, segments);
                let right = build(nodes, right);
                nodes[index].children = Some((left, right));
            }
            index
        }
        let segments = (0..points.len())
            .filter(|i| selected.is_none_or(|indices| indices.binary_search(i).is_ok()))
            .map(|i| Segment {
                a: points[i],
                b: points[(i + 1) % points.len()],
                index: i,
            })
            .collect();
        let mut nodes = Vec::new();
        let root = build(&mut nodes, segments);
        Self { nodes, root }
    }
}
fn transformed(b: Box2, cp: f64, sp: f64, tx: f64, ty: f64) -> Box2 {
    let (x, y) = ((b[0] + b[2]) / 2., (b[1] + b[3]) / 2.);
    let (hx, hy) = ((b[2] - b[0]) / 2., (b[3] - b[1]) / 2.);
    let (cx, cy) = (tx + cp * x - sp * y, ty + sp * x + cp * y);
    let (ex, ey) = (cp.abs() * hx + sp.abs() * hy, sp.abs() * hx + cp.abs() * hy);
    [cx - ex, cy - ey, cx + ex, cy + ey]
}
fn pair_nearest(
    planet: &Tree,
    ring: &Tree,
    cp: f64,
    sp: f64,
    tx: f64,
    ty: f64,
) -> (f64, Option<(usize, usize)>) {
    let transform = |q: Point| [tx + cp * q[0] - sp * q[1], ty + sp * q[0] + cp * q[1]];
    let mut cache = vec![None; planet.nodes.len()];
    let mut box_at = |index: usize| {
        if let Some(b) = cache[index] {
            b
        } else {
            let b = transformed(planet.nodes[index].bounds, cp, sp, tx, ty);
            cache[index] = Some(b);
            b
        }
    };
    let mut best = f64::INFINITY;
    let mut pending = vec![(planet.root, ring.root)];
    while let Some((ip, ir)) = pending.pop() {
        let p = &planet.nodes[ip];
        let r = &ring.nodes[ir];
        let pb = box_at(ip);
        if box_distance(pb, r.bounds) > best {
            continue;
        }
        if p.children.is_none() && r.children.is_none() {
            for s in &p.segments {
                let aa = transform(s.a);
                let bb = transform(s.b);
                let qb = bounds(aa, bb);
                if box_distance(qb, r.bounds) > best {
                    continue;
                }
                for t in &r.segments {
                    if box_distance(qb, bounds(t.a, t.b)) > best {
                        continue;
                    }
                    let (d, crossing) = segment_distance(aa, bb, t.a, t.b);
                    if crossing {
                        return (0., Some((s.index, t.index)));
                    }
                    best = best.min(d);
                }
            }
        } else {
            let mut children = match (p.children, r.children) {
                (Some((left, right)), None) => vec![(left, ir), (right, ir)],
                (None, Some((left, right))) => vec![(ip, left), (ip, right)],
                (Some((pl, pr)), Some((rl, rr))) => {
                    if (pb[2] - pb[0]) * (pb[3] - pb[1])
                        > (r.bounds[2] - r.bounds[0]) * (r.bounds[3] - r.bounds[1])
                    {
                        vec![(pl, ir), (pr, ir)]
                    } else {
                        vec![(ip, rl), (ip, rr)]
                    }
                }
                (None, None) => unreachable!("Leaf pairs are handled above"),
            };
            children.sort_by(|a, b| {
                box_distance(box_at(b.0), ring.nodes[b.1].bounds)
                    .total_cmp(&box_distance(box_at(a.0), ring.nodes[a.1].bounds))
            });
            pending.extend(children);
        }
    }
    (best.sqrt(), None)
}
fn read_points(a: &Value, key: &str) -> Result<Vec<Point>> {
    let points: Vec<Point> = serde_json::from_value(a[key].clone()).map_err(|e| e.to_string())?;
    if points.iter().flatten().any(|v| !v.is_finite()) {
        return Err("Polygon coordinates must be finite.".into());
    }
    Ok(points)
}
fn integer(a: &Value, key: &str, default: u64, max: u64) -> Result<usize> {
    let value = match a.get(key) {
        None => default,
        Some(v) => v
            .as_u64()
            .ok_or_else(|| format!("Verification {key} must be an integer between 0 and {max}."))?,
    };
    if value > max {
        return Err(format!(
            "Verification {key} must be an integer between 0 and {max}."
        ));
    }
    Ok(value as usize)
}
fn verify(a: &Value) -> Result<Value> {
    separate(a, true, None, None, 0., true)
}

fn crossing_witness(
    points: &[Point],
    other: &[Point],
    selected: Option<&[usize]>,
    edge: usize,
    transform: impl Fn(Point) -> Point,
    margin: f64,
) -> Option<Value> {
    // A polygon crossing alone is inconclusive for enclosed source curves.
    // Two endpoints of the SAME continuous trace must straddle the mate,
    // farther from its boundary than both enclosures and the numeric guard.
    let mut candidates = vec![edge, (edge + 1) % points.len()];
    let mut left = edge;
    let mut right = (edge + 1) % points.len();
    for _ in 0..6 {
        let previous = (left + points.len() - 1) % points.len();
        if selected.is_none_or(|rows| rows.binary_search(&previous).is_ok()) {
            left = previous;
            candidates.push(left);
        }
        if selected.is_none_or(|rows| rows.binary_search(&right).is_ok()) {
            right = (right + 1) % points.len();
            candidates.push(right);
        }
    }
    let mut sides: [Option<Value>; 2] = [None, None];
    for i in candidates {
        let p = transform(points[i]);
        let distance = (0..other.len())
            .map(|j| point_segment(p, other[j], other[(j + 1) % other.len()]))
            .fold(f64::INFINITY, f64::min)
            .sqrt();
        if distance > margin {
            let side = usize::from(inside(p, other));
            sides[side] = Some(
                json!({"source_vertex":i,"point_in_mate_frame_mm":p,"distance_to_polygon_mm":distance,"inside":side==1}),
            );
        }
        if sides.iter().all(Option::is_some) {
            return Some(
                json!({"basis":"continuous source-trace endpoints straddle the mate outside the combined enclosure and numeric guard",
                "required_margin_mm":margin,"endpoints":sides}),
            );
        }
    }
    None
}

/// Shared BVH/motion bound for constructed cylindrical boundaries. Optional
/// subsets test open root traces against the complete mating boundary. Their
/// distance check deliberately has no whole-body containment interpretation.
pub(crate) fn separate(
    a: &Value,
    internal: bool,
    selected_p: Option<&[usize]>,
    selected_r: Option<&[usize]>,
    enclosure: f64,
    containment: bool,
) -> Result<Value> {
    let zp = n(a, "zp", 1.)?;
    let zr = n(a, "zr", 1.)?;
    let phase_p = n(a, "phaseP", 0.)?;
    let phase_r = n(a, "phaseR", 0.)?;
    let center = n(a, "center_distance_mm", 0.)?;
    let guard = n(a, "numeric_guard_mm", 1e-7)?;
    let budget = integer(
        a,
        "budget",
        4096,
        if enclosure > 0. || selected_p.is_some() || selected_r.is_some() {
            16_384
        } else {
            4096
        },
    )?;
    let max_depth = integer(a, "max_depth", 20, 20)?;
    if zp <= 0. || zr <= 0. || guard <= 0. || !enclosure.is_finite() || enclosure < 0. {
        return Err("Invalid internal polygon verification domain.".into());
    }
    let period = TAU / zp;
    let ratio = (if internal { 1. } else { -1. }) * zp / zr;
    let mut result = json!({"status":"unresolved","scope":SCOPE,"phase_period_rad":period,"ratio":ratio,"numeric_guard_mm":guard,
        "certified_separation_lower_bound_mm":null,"observed_minimum_distance_mm":null,"evaluated_intervals":0,"max_depth":0,"budget":budget,"failure_reason":null});
    if a.get("backlash_mm").is_some_and(|v| !v.is_null()) && n(a, "backlash_mm", 0.)? <= 4. * guard
    {
        result["failure_reason"] =
            json!("Zero or numerically tiny backlash cannot certify strict separation.");
        return Ok(result);
    }
    let planet = read_points(a, "planet_loop")?;
    let ring = read_points(a, "ring_void")?;
    let limit = if enclosure > 0. { 240000 } else { 30000 };
    if planet.len() < 3 || ring.len() < 3 || planet.len() + ring.len() > limit {
        result["failure_reason"] = json!("Unsupported contour complexity.");
        return Ok(result);
    }
    for (indices, size) in [(selected_p, planet.len()), (selected_r, ring.len())] {
        if indices.is_some_and(|rows| {
            rows.is_empty()
                || rows.iter().any(|&i| i >= size)
                || rows.windows(2).any(|v| v[0] >= v[1])
        }) {
            return Err("Boundary subsets must contain sorted unique segment indices.".into());
        }
    }
    let pt = Tree::selected(&planet, selected_p);
    let rt = Tree::selected(&ring, selected_r);
    let speed = (center * ratio).abs()
        + (1. - ratio).abs() * planet.iter().map(|p| radius(*p)).fold(0., f64::max);
    let mut pending = vec![(0., period, 0)];
    let mut lower = f64::INFINITY;
    let mut observed = f64::INFINITY;
    let mut evaluated = 0;
    let mut depth_seen = 0;
    while !pending.is_empty() {
        crate::protocol::control_check()?;
        if evaluated >= budget {
            result["failure_reason"] = json!("Interval evaluation budget exhausted.");
            break;
        }
        let (start, end, depth) = pending.pop().unwrap();
        let q = (start + end) / 2.;
        let ap = phase_p + q;
        let ar = phase_r + ratio * q;
        let (cp, sp) = ((ap - ar).cos(), (ap - ar).sin());
        let origin = if internal { center } else { -center };
        let (tx, ty) = (origin * ar.cos(), -origin * ar.sin());
        let (distance, witness) = pair_nearest(&pt, &rt, cp, sp, tx, ty);
        let p = planet[0];
        let point = [tx + cp * p[0] - sp * p[1], ty + sp * p[0] + cp * p[1]];
        let status = if witness.is_some() {
            "collision"
        } else if distance <= guard + enclosure {
            "unresolved"
        } else if !containment {
            "clear"
        } else if internal {
            if inside(point, &ring) {
                "clear"
            } else {
                "collision"
            }
        } else {
            let q = [ring[0][0] - tx, ring[0][1] - ty];
            let q = [cp * q[0] + sp * q[1], -sp * q[0] + cp * q[1]];
            if inside(point, &ring) || inside(q, &planet) {
                "collision"
            } else {
                "clear"
            }
        };
        observed = observed.min(distance);
        evaluated += 1;
        depth_seen = depth_seen.max(depth);
        if status == "collision" {
            let mut w = json!({"phase_planet_rad":ap,"phase_ring_rad":ar});
            if let Some((i, j)) = witness {
                w["planet_segment"] = json!(i);
                w["ring_segment"] = json!(j);
            }
            if enclosure > 0. {
                let proof = witness.and_then(|(i, j)| {
                    let first = if selected_r.is_none() {
                        crossing_witness(
                            &planet,
                            &ring,
                            selected_p,
                            i,
                            |p| [tx + cp * p[0] - sp * p[1], ty + sp * p[0] + cp * p[1]],
                            enclosure + guard,
                        )
                    } else {
                        None
                    };
                    first.or_else(|| {
                        if selected_p.is_none() {
                            crossing_witness(
                                &ring,
                                &planet,
                                selected_r,
                                j,
                                |p| {
                                    [
                                        cp * (p[0] - tx) + sp * (p[1] - ty),
                                        -sp * (p[0] - tx) + cp * (p[1] - ty),
                                    ]
                                },
                                enclosure + guard,
                            )
                        } else {
                            None
                        }
                    })
                });
                if let Some(proof) = proof {
                    result["status"] = json!("collision");
                    result["failure_reason"] =
                        json!("Source boundaries cross outside the approximation enclosure.");
                    w["source_crossing"] = proof;
                } else {
                    result["failure_reason"] = json!(
                        "Approximation boundaries intersect or containment fails; an analytic collision is not established by this witness."
                    );
                }
                result["witness"] = w;
                break;
            }
            result["status"] = json!("collision");
            result["failure_reason"] = json!("Boundary crossing or failed containment.");
            result["witness"] = w;
            break;
        }
        let bound = speed * (end - start) / 2.;
        if status == "clear" && distance > bound + guard + enclosure {
            lower = lower.min(distance - bound - enclosure);
            continue;
        }
        if depth >= max_depth || distance <= guard + enclosure {
            result["failure_reason"] = json!("Touch, tiny separation or subdivision depth limit.");
            break;
        }
        pending.push((q, end, depth + 1));
        pending.push((start, q, depth + 1));
    }
    if pending.is_empty() && result["failure_reason"].is_null() {
        result["status"] = json!("clear");
        result["certified_separation_lower_bound_mm"] = json!(lower);
    }
    result["observed_minimum_distance_mm"] = if observed.is_finite() {
        json!(observed)
    } else {
        Value::Null
    };
    result["evaluated_intervals"] = json!(evaluated);
    result["max_depth"] = json!(depth_seen);
    Ok(result)
}

fn half(args: &Value, internal: bool) -> Result<Value> {
    let mut metadata = crate::profiles::call(
        if internal {
            "internal_half"
        } else {
            "external_half"
        },
        args,
    )?["metadata"]
        .clone();
    metadata.as_object_mut().unwrap().remove("sampling_curves");
    Ok(metadata)
}
fn field(v: &Value, k: &str) -> f64 {
    v[k].as_f64().expect("constructed profile scalar")
}

/// Match actual ISO21771:2007 5.4.1/7.6 form domains, not unrelated radial
/// extrema. The normal generating rack remains explicit; no selected cutter
/// or bending-strength qualification is implied by this geometric construction.
fn fixed_plan(a: &Value) -> Result<Value> {
    let zp = n(a, "zp", 22.)?;
    let zr = n(a, "zr", 66.)?;
    let mn = n(a, "mn", 2.)?;
    let alpha_deg = n(a, "alpha_n", 20.)?;
    let beta_deg = n(a, "beta", 0.)?;
    let an = alpha_deg.to_radians();
    let beta = beta_deg.to_radians();
    let backlash = n(a, "backlash", 0.15)?;
    if zp.fract() != 0.
        || zr.fract() != 0.
        || zp < 3.
        || zr - zp <= 9.
        || mn <= 0.
        || backlash < 0.
        || !(0. < an
            && an < std::f64::consts::FRAC_PI_2
            && beta.abs() < std::f64::consts::FRAC_PI_2)
    {
        return Err(
            "Unsupported fixed internal pair dimensions or closely spaced tooth counts.".into(),
        );
    }
    let mt = mn / beta.cos();
    let at = (an.tan() / beta.cos()).atan();
    let rp = mt * zp / 2.;
    let rr = mt * zr / 2.;
    let bp = rp * at.cos();
    let br = rr * at.cos();
    let center = rr - rp;
    let span = center * at.sin();
    let nominal_tip = rr - mn;
    if nominal_tip <= br {
        return Err("Internal tip circle is below its base circle.".into());
    }
    let roll = |r: f64, b: f64| ((r - b) * (r + b)).max(0.).sqrt();
    let required = roll(nominal_tip, br) - span;
    if required <= 0. {
        return Err("Internal involute interference at the pinion: increase pinion tooth count or redesign the pair.".into());
    }
    let mut pinion_args = json!({"z":zp,"mt":mt,"pressure":at.to_degrees(),"depth":mn,"normal_pressure":alpha_deg,
        "backlash":backlash,"ha":1.,"hf":1.25,"shift":0.,"endpoints":true});
    let original = half(&pinion_args, false)?;
    let old_start = roll(field(&original, "involute_start_radius_mm"), bp);
    let default_rho = field(&original["tool"], "tip_radius");
    // Signed generating roll: uF=rp*sin(at)
    // -(hf*mn-rho_n*(1-sin(an)))/sin(at). The normal circular tip has an
    // elliptical helical transverse section; it is not replaced with a circle.
    let denominator = 1. - an.sin();
    let lower_rho = ((1.25 * mn - rp * at.sin().powi(2)) / denominator).max(0.);
    let upper_rho = (1.25 * mn - rp * at.sin().powi(2) + required * at.sin()) / denominator;
    let land = std::f64::consts::PI * mn / 4. + backlash * beta.cos() / 4. - 1.25 * mn * an.tan();
    let fit = (land - 0.025 * mn) * an.cos() / denominator;
    let upper = upper_rho.min(fit);
    let guard = 4096. * f64::EPSILON * rr.max(1.);
    let mut selected = None;
    let mut pinion = original.clone();
    if old_start >= required - guard && upper > lower_rho + guard {
        // Midpoint of the feasible interval leaves a positive roll margin
        // from both undercut and the active profile. Independent of quality.
        let rho = (lower_rho + upper) / 2.;
        pinion_args["rack_tip_radius_mm"] = json!(rho);
        pinion = half(&pinion_args, false)?;
        if pinion["undercut_trimmed"] == true {
            return Err("Paired normal rack unexpectedly requires undercut trimming.".into());
        }
        selected = Some(rho);
    }
    let start = field(&pinion, "involute_start_radius_mm");
    let start_roll = roll(start, bp);
    let tip = rp + mn;
    let high = roll(tip, bp);
    // If a positive non-undercut tool cannot retain the old nominal path,
    // remove only its unusable part using the ISO line-of-action relation.
    let low = if start_roll >= required - guard {
        start_roll + (0.01 * mn).min((high - start_roll).max(0.) * 0.001)
    } else {
        required
    };
    let ring_tip = if low > required {
        br.hypot(span + low)
    } else {
        nominal_tip
    };
    let ha = if ring_tip == nominal_tip {
        1.
    } else {
        (rr - ring_tip) / mn
    };
    if !(0. < ha && ha <= 1.) || high <= low {
        return Err("No usable fixed internal contact interval remains.".into());
    }
    let mut ring_args = json!({"z":zr,"mt":mt,"pressure":at.to_degrees(),"depth":mn,"backlash":backlash,
        "ha":ha,"hf":1.25,"endpoints":true,"internal":true});
    let mut ring = half(&ring_args, true)?;
    let paired_chord = 0.015_f64.min(0.005 * mn);
    let minimum = center + tip + 4. * paired_chord;
    let minimum_join = if field(&ring, "involute_end_radius_mm") < minimum {
        ring_args["minimum_join_radius_mm"] = json!(minimum);
        ring = half(&ring_args, true)?;
        Some(minimum)
    } else {
        None
    };
    let join = field(&ring, "involute_end_radius_mm");
    let ring_high = roll(join, br);
    if high + span > ring_high + guard {
        return Err("Fixed internal pair extends outside its usable ring involute.".into());
    }
    let base_pitch = std::f64::consts::PI * mt * at.cos();
    Ok(json!({"construction_version":"fixed_internal_rack_pair_v1",
        "construction_inputs":{"zp":zp as u64,"zr":zr as u64,"mn":mn,"alpha_n_deg":alpha_deg,"beta_deg":beta_deg,"backlash_mm":backlash},
        "pinion_rack_tip_radius_mm":selected,"default_pinion_rack_tip_radius_mm":default_rho,
        "feasible_nonundercut_normal_rack_radius_interval_mm":[lower_rho,upper],
        "pinion_profile":pinion,"ring_profile":ring,"ring_addendum_coefficient":ha,"ring_dedendum_coefficient":1.25,
        "ring_tip_radius_mm":ring_tip,"ring_tip_relief_mm":ring_tip-nominal_tip,"ring_root_radius_mm":rr+1.25*mn,
        "minimum_join_radius_mm":minimum_join,"ring_join_radius_mm":join,"center_distance_mm":center,
        "nominal_pinion_roll_min_mm":required,"actual_pinion_roll_min_mm":low,"pinion_involute_start_roll_mm":start_roll,
        "pinion_roll_margin_mm":low-start_roll,"ring_roll_margin_mm":ring_high-span-high,
        "nominal_contact_preserved":ring_tip==nominal_tip,"contact_transverse":(high-low)/base_pitch,
        "baseline_nominal_contact_transverse":(high-required)/base_pitch,
        "baseline_usable_contact_transverse":(high-required.max(old_start)).max(0.)/base_pitch,
        "safe_pair_sampling":true,"paired_profile_chord_threshold_mm":paired_chord,
        "verification":{"status":"construction_checked","scope":"ISO active/form involute domains and actual normal-rack geometry; continuous clearance is a separate audit; no selected cutter, strength or manufacturing qualification"}}))
}
fn plan(a: &Value) -> Result<Value> {
    let zp = n(a, "zp", 18.)?;
    let zr = n(a, "zr", 54.)?;
    let mn = n(a, "mn", 2.)?;
    let an = n(a, "alpha_n", 20.)?;
    let beta = n(a, "beta", 0.)?;
    let backlash = n(a, "backlash", 0.15)?;
    let tol = n(a, "tolerance", 0.015)?;
    let budget = integer(a, "budget", 1024, 4096)?;
    if tol != 0.015 {
        return Err("Only the shared 0.015 mm profile chord threshold is supported.".into());
    }
    if mn <= 0. || zp <= 0. || zr <= zp || backlash < 0. {
        return Err("Invalid planetary internal pair dimensions.".into());
    }
    let mt = mn / beta.to_radians().cos();
    let at = (an.to_radians().tan() / beta.to_radians().cos()).atan();
    let rp = mt * zp / 2.;
    let rr = mt * zr / 2.;
    let center = rr - rp;
    let bp = rp * at.cos();
    let br = rr * at.cos();
    let args = json!({"z":zp,"mt":mt,"pressure":at.to_degrees(),"backlash":backlash,"depth":mn,"shift":0.,"normal_pressure":an,"ha":1.,"hf":1.25,"endpoints":true});
    let planet_info = half(&args, false)?;
    let start = field(&planet_info, "involute_start_radius_mm");
    let tip = rp + mn;
    let delta = (0.05 * mn).max(4. * tol);
    if delta >= 0.25 * mn {
        return Err(
            "Module too small for the paired radial margin at the current chord threshold.".into(),
        );
    }
    let rt = (rr - mn).max(center + start + delta);
    let ha = (rr - rt) / mn;
    if !(0. < ha && ha <= 1.) || rt <= br {
        return Err("Paired ring tip cannot fit the usable involute domain.".into());
    }
    let min_join = center + tip + delta;
    let ring_args = json!({"z":zr,"mt":mt,"pressure":at.to_degrees(),"backlash":backlash,"depth":mn,"ha":ha,"hf":1.25,"endpoints":true,"minimum_join_radius_mm":min_join,"internal":true});
    let ring_info = half(&ring_args, true)?;
    let join = field(&ring_info, "involute_end_radius_mm");
    let span = center * at.sin();
    let low = (rt * rt - br * br).sqrt() - span;
    let high = (tip * tip - bp * bp).sqrt();
    let lower_roll = (start * start - bp * bp).max(0.).sqrt();
    let upper_roll = (join * join - br * br).sqrt();
    let ea = (high - low) / (std::f64::consts::PI * mt * at.cos());
    if low < lower_roll - 1e-8 || high + span > upper_roll + 1e-8 || ea < 1. {
        return Err("Paired planetary full nominal contact interval is outside usable involutes or below one transverse contact ratio.".into());
    }
    let planet = crate::profiles::involute_profile(&args)?["points"].clone();
    let ring = crate::profiles::involute_profile(&ring_args)?["points"].clone();
    let pp: Vec<Point> = serde_json::from_value(planet.clone()).map_err(|e| e.to_string())?;
    let rrpoints: Vec<Point> = serde_json::from_value(ring.clone()).map_err(|e| e.to_string())?;
    let actual_min = (0..rrpoints.len())
        .map(|i| point_segment([0., 0.], rrpoints[i], rrpoints[(i + 1) % rrpoints.len()]).sqrt())
        .fold(f64::INFINITY, f64::min);
    let actual_max = pp.iter().map(|p| radius(*p)).fold(0., f64::max);
    if actual_min < center + start + delta - 1e-8 || actual_max > tip + 1e-8 {
        return Err("Generated polygons violate the paired radial exclusions.".into());
    }
    let phase_p = std::f64::consts::PI / zp + std::f64::consts::PI;
    let phase_r = (zp * phase_p - std::f64::consts::PI) / zr;
    let verified = verify(
        &json!({"planet_loop":planet,"ring_void":ring,"phaseP":phase_p,"phaseR":phase_r,"zp":zp,"zr":zr,"center_distance_mm":center,"budget":budget,"backlash_mm":backlash}),
    )?;
    if verified["status"] == "collision" {
        return Err(format!(
            "Paired planetary polygon collision: {}",
            verified["witness"]
        ));
    }
    Ok(
        json!({"construction_version":"planetary_paired_involute_v1","construction_inputs":{"zp":zp as u64,"zr":zr as u64,"mn":mn,"alpha_n_deg":an,"beta_deg":beta,"backlash_mm":backlash},
        "ring_addendum_coefficient":ha,"ring_dedendum_coefficient":1.25,"ring_tip_relief_mm":rt-(rr-mn),"actual_ring_min_radius_mm":actual_min,"actual_planet_max_radius_mm":actual_max,
        "delta_mm":delta,"planet_involute_start_radius_mm":start,"planet_tip_radius_mm":tip,"ring_tip_radius_mm":rt,"ring_root_radius_mm":rr+1.25*mn,"ring_join_radius_mm":join,"minimum_join_radius_mm":min_join,
        "ring_blend_radius_mm":ring_info["blend_radius_mm"],"planet_root_exclusion_margin_mm":rt-center-start,"ring_root_exclusion_margin_mm":join-center-tip,
        "nominal_planet_roll_min_mm":low,"nominal_planet_roll_max_mm":high,"planet_roll_margin_mm":low-lower_roll,"ring_roll_margin_mm":upper_roll-high-span,"contact_transverse":ea,"center_distance_mm":center,
        "planet_profile":planet_info,"ring_profile":ring_info,"verification":verified}),
    )
}
fn axial(a: &Value, derive_planet: bool) -> Result<Value> {
    let planet = &a["planet"];
    let ring = &a["ring"];
    let zp = n(a, "zp", 18.)?;
    let zr = n(a, "zr", 54.)?;
    if !planet["stations"].as_array().is_some_and(|p| p.is_empty())
        || !ring["stations"].as_array().is_some_and(|p| p.is_empty())
        || planet["width"] != ring["width"]
        || planet["double"] != ring["double"]
        || planet["gap"] != ring["gap"]
    {
        return Ok(json!(
            "Unsupported axial placement or section construction."
        ));
    }
    if (n(ring, "twist", 0.)? - zp / zr * n(planet, "twist", 0.)?).abs() > 1e-9 {
        return Ok(json!(
            "Internal helical section phases do not preserve the mesh ratio."
        ));
    }
    if planet["double"] == true {
        let outer: Vec<Point> =
            serde_json::from_value(planet["outer"].clone()).map_err(|e| e.to_string())?;
        let hole: Vec<Point> =
            serde_json::from_value(ring["holes"][0].clone()).map_err(|e| e.to_string())?;
        if outer.len() < 3 || hole.len() < 3 {
            return Err("Invalid axial pair contour".into());
        }
        let fan = |l: &[Point]| {
            (0..l.len()).all(|i| cross([0., 0.], l[i], l[(i + 1) % l.len()]) >= -1e-9)
        };
        if !fan(&outer) || !fan(&hole) {
            return Ok(json!(
                "Unsupported axial profile without a radial triangle fan."
            ));
        }
        if !inside([0., 0.], &outer) || !inside([0., 0.], &hole) {
            return Ok(json!("Unsupported noncentral axial profile."));
        }
        let same = |l: &[Point], r: &[Point]| {
            l.len() == r.len()
                && l.iter().zip(r.iter()).all(|(p, q)| {
                    // An absolute transverse-distance guard in mm, not an
                    // angular tolerance whose displacement grows with radius.
                    (p[0] * q[1] - p[1] * q[0]).abs() <= 1e-9 * radius(*q)
                        && p[0] * q[0] + p[1] * q[1] > 0.
                })
        };
        let planet_sections = if derive_planet {
            if a.get("planet_sections").is_some() || a.get("ring_sections").is_some() {
                return Err("Derived axial checks do not accept substituted sections.".into());
            }
            crate::solid::Part::read(planet)?
                .sections()?
                .into_iter()
                .filter_map(|(_, _, contour)| (contour != outer).then_some(contour))
                .collect::<Vec<_>>()
        } else {
            a["planet_sections"]
                .as_array()
                .ok_or("Planet section records required")?
                .iter()
                .filter(|row| row["base"] != true)
                .map(|row| read_points(row, "outer"))
                .collect::<Result<Vec<_>>>()?
        };
        for l in &planet_sections {
            crate::protocol::control_check()?;
            // The checked central radial fan is the union of triangles O,A,B.
            // Matching positive rays with no vertex farther out puts every
            // new triangle inside its original convex triangle. This includes
            // partial shoulders, not only a core inside the root incircle.
            if !same(l, &outer)
                || l.iter()
                    .zip(&outer)
                    .any(|(p, q)| radius(*p) > radius(*q) + 1e-9)
            {
                return Ok(json!(
                    "Planet groove core is not a certified material subset."
                ));
            }
        }
        let ring_sections = if a.get("ring_sections").is_some() {
            a["ring_sections"]
                .as_array()
                .ok_or("Ring section records required")?
                .iter()
                .map(|row| read_points(row, "hole"))
                .collect::<Result<Vec<_>>>()?
        } else {
            let part = crate::solid::Part::read(ring)?;
            part.sections()?
                .iter()
                .enumerate()
                .map(|(i, (z, _, _))| {
                    part.holes_at(*z, i)?
                        .into_iter()
                        .next()
                        .ok_or("Internal gear has no hole".into())
                })
                .collect::<Result<Vec<_>>>()?
        };
        for l in &ring_sections {
            crate::protocol::control_check()?;
            if l.len() != hole.len() {
                return Ok(json!("Unsupported ring groove contour."));
            }
            if l.iter()
                .zip(hole.iter())
                .flat_map(|(a, b)| a.iter().zip(b.iter()).map(|(x, y)| (x - y).abs()))
                .fold(0., f64::max)
                < 1e-8
            {
                continue;
            }
            if !same(l, &hole) || !inside([0., 0.], l) {
                return Ok(json!("Unsupported ring groove contour."));
            }
            // The dual fan inclusion enlarges the verified void throughout
            // both shoulders: every original fan triangle stays inside the
            // triangle on the same two rays with larger endpoint radii.
            if l.iter()
                .zip(&hole)
                .any(|(p, q)| radius(*p) < radius(*q) - 1e-9)
            {
                return Ok(json!(
                    "Ring groove is not a certified enlargement of the verified void."
                ));
            }
        }
    }
    Ok(Value::Null)
}
pub fn call(op: &str, a: &Value) -> Result<Value> {
    if op == "internal_verify_trace" {
        let indices: Vec<usize> =
            serde_json::from_value(a["segments"].clone()).map_err(|e| e.to_string())?;
        let member = n(a, "root_member", 1.)?;
        if member != 1. && member != 2. {
            return Err("Root trace member must be 1 or 2.".into());
        }
        let mut result = separate(
            a,
            true,
            if member == 1. { Some(&indices) } else { None },
            if member == 2. { Some(&indices) } else { None },
            0.,
            false,
        )?;
        result["scope"] = json!(
            "continuous separation of supplied polygon trace segments from the complete mate boundary; no source-curve enclosure or full loaded-flank qualification"
        );
        Ok(result)
    } else {
        call_existing(op, a)
    }
}
fn call_existing(op: &str, a: &Value) -> Result<Value> {
    if op == "internal_fixed_plan" {
        return fixed_plan(a);
    }
    if op == "internal_plan" {
        return plan(a);
    }
    if op == "internal_axial" || op == "internal_axial_derived" {
        return axial(a, op == "internal_axial_derived");
    }
    if ["internal_point_segment2", "internal_cross"].contains(&op) {
        let p: Point = serde_json::from_value(a["p"].clone()).map_err(|e| e.to_string())?;
        let q: Point = serde_json::from_value(a["a"].clone()).map_err(|e| e.to_string())?;
        let r: Point = serde_json::from_value(a["b"].clone()).map_err(|e| e.to_string())?;
        return Ok(json!(if op == "internal_cross" {
            cross(p, q, r)
        } else {
            point_segment(p, q, r)
        }));
    }
    if op == "internal_inside" {
        let p: Point = serde_json::from_value(a["point"].clone()).map_err(|e| e.to_string())?;
        let l = read_points(a, "loop")?;
        return Ok(json!(inside(p, &l)));
    }
    if op == "internal_verify" {
        return verify(a);
    }
    let planet = read_points(a, "planet")?;
    let ring = read_points(a, "ring")?;
    if planet.len() < 3 || ring.len() < 3 || planet.len() + ring.len() > 30000 {
        return Err("Unsupported contour complexity.".into());
    }
    let (d, w) = pair_nearest(&Tree::new(&planet), &Tree::new(&ring), 1., 0., 0., 0.);
    if let Some((i, j)) = w {
        return Ok(json!(["collision",0.,{"planet_segment":i,"ring_segment":j}]));
    }
    if d <= 1e-10 {
        return Ok(json!(["unresolved", d, {}]));
    }
    if !inside(planet[0], &ring) {
        return Ok(json!(["collision",d,{"reason":"planet outside ring void"}]));
    }
    Ok(json!(["clear", d, {}]))
}

#[cfg(test)]
mod enclosure_tests {
    use super::*;
    #[test]
    fn crossing_requires_opposite_source_sides_outside_the_error_tube() {
        let first = [[-0.5, 0.], [1.5, 0.], [1.5, 2.]];
        let other = [[-1., -1.], [1., -1.], [1., 1.], [-1., 1.]];
        let identity = |p| p;
        assert!(crossing_witness(&first, &other, Some(&[0]), 0, identity, 0.2).is_some());
        assert!(crossing_witness(&first, &other, Some(&[0]), 0, identity, 0.6).is_none());
        // A chord can cross twice with both source endpoints outside. This
        // conservative witness must remain inconclusive in that case.
        let twice = [[-2., 0.], [2., 0.], [2., 2.]];
        assert!(crossing_witness(&twice, &other, Some(&[0]), 0, identity, 0.1).is_none());
    }
}
