# Geometry reuse and request cancellation

This optimization retains the existing equations, generated profiles, sample
counts, interpolation requests and resource limits. It does not replace the
corrected internal profiles with the former unpaired profiles. Exact analytic
source expressions and the independent 256/512-bit comparison remain intact.

## Immutable records and mutable application parts

`rust_geometry.cached_call` retains only plain construction results for
`gear_part` and `internal_axial_derived`. Its bounded LRU holds at most 64 records
and 8 MiB of retained input/result bytes, in addition to the existing surface
caches. The complete input snapshot preserves float bits, exact decimal
expressions, placement, phase, tool geometry, quality and topology flags.
Backend identity/epoch and protocol version are part of the key; the backend
owner stays alive with its entries. Errors and native resource handles are not
cached. A hit still checks cancellation and returns detached data, so edits to
one application's lists or metadata cannot alter later constructions.

Pickle is used solely for internally produced snapshots. No file, project or
wire pickle is loaded. Inputs are detached before a miss is evaluated. A cache
that cannot retain another record recomputes the same result; it never changes
accuracy or accepted sample counts. The separate analytic-dimensions cache
keeps its existing 64-entry limit and exact canonical keys, but promotes hits
instead of evicting frequently used entries in insertion order.

These caches benefit repeated constructions. A new physical input can still
require the complete calculation. Ordinary RPM-only motion already reuses the
accepted geometry; regeneration benchmarks are not animation frame rates.

## Axial verification beside its source sections

`internal_axial_derived` derives the same canonical satellite sections in Rust
that `solid_sections` previously exported through Python. The same radial-fan,
phase, groove and material-subset checks are applied, including partial radial
shoulders. Ring holes are consumed directly instead of being serialized into
JSON records and parsed again inside the verifier. Successful protocol records
are reusable only under the complete input key.

The explicit `internal_axial` operation remains available for literal section
tests and negative controls. The derived operation rejects substituted section
arrays rather than silently treating them as the generated construction. Its
scope remains the nominal axial subset law; it is not a loaded-contact or
manufacturing qualification.

## Surface triangulations and sampled bounds

Canonical section records are also retained by immutable surface snapshots,
under the same shared 64 MiB budget as rings and cap triangulations. Preview,
ring construction and explicit section export reuse those exact records.
An exhausted retention budget recomputes the same sections; it does not change
sampling, quality, topology or the accepted face limit.

An immutable Rust surface may retain triangulations of up to eight large faces,
indexed by their deterministic ordinal in that snapshot's face traversal.
Completed triangulations are shared between cursors with owned references.
Their storage is charged to the existing global 64 MiB surface budget. If the
budget is full, the triangulation is recomputed without changing the algorithm,
triangle order or limits. Aborted computations do not publish a partial entry.
Already triangular side strips use the same three coordinates directly; the
packet loop still checks cancellation for every output record.

`solid_bounds` visits the same sampled world-space vertices as the former Python
walk, including explicit meshes, stations, rotations, holes and all components.
Only the six extrema cross the boundary. It does not substitute ideal circles,
local-box corners or optimistic bounds, and does not compute a motion sweep.
Traversal and strict comparisons preserve the first signed zero as well.

## STEP construction and owned coordinate buffers

The faceted STEP writer emits its existing entities directly into the assembly
writer's entity namespace. Coordinates, face winding, entity order and geometry
remain the same. The redundant standalone STEP document, parsing and regular
expression renumbering pass are removed. Existing validation and atomic export
transactions remain in place. This does not promote faceted surfaces to a new
continuous CAD construction or widen the qualified CAD scope.

Binary coordinates still become the existing tuple/list application types.
Three-dimensional row conversion uses a C iterator where no request control is
active. Under request control, decoding checks between blocks of 1,024 rows.
Returned coordinates retain their own storage after native release or Wasm
memory growth; no borrowed pointer escapes.

The resident collision path now avoids face/triangle and prescribed-deformation
coordinate round trips entirely. Native preview packets also copy directly into
owned float arrays while their Rust owner remains alive, avoiding a temporary
whole-packet byte copy. Wasm retains owned-byte decoding. See
[collision and transfer reuse](collision-reuse.md) for validation, fallback,
ownership and remaining costs.

Preview byte packing writes fixed-size little-endian blocks instead of appending
four bytes for every scalar, for both desktop and browser meshes. Every computed
float retains its finite-value check, and packing adds cooperative checks at
bounded block intervals. Static material
records are positive binary32 zero by construction: their bytes are written
directly into the validated final packet, avoiding a temporary zero-filled float
vector. Prescribed wave materials keep their existing calculation and validation.
No vertices, normals, materials, draw ranges or sampling requests are discarded.

## Superseded GUI work

`control_scope` propagates a request-local check through native calls during
generation and scene preparation. A superseded request returns no prepared
design/scene, and `LatestOnly` retains its final delivery check. Nested scopes
restore the previous control, including on exceptions. Fully built immutable
cache records can remain useful; partial designs and scenes are not published.

Owned surface/cursor/collision release operations always run during cleanup,
even after cancellation. They do not inherit a check that could prevent a
`finally` block from releasing its resource. Existing explicit checks in other
operations remain active; no global reduction of callback frequency is made.

This is cooperative cancellation, not a hard real-time guarantee. JSON encoding,
memory copies and scheduling can delay observation of invalidation; measurements
must distinguish scheduled invalidation, observed invalidation and subsequent
stop latency. Native checked callbacks do not imply mid-call interruption of a
synchronous Wasm call in a browser worker.

## Remaining performance scope

| Area | Disposition |
| --- | --- |
| Repeated axial verification | Compact native derivation and exact record reuse |
| Corrected internal contours | Detached reuse of identical full constructions; cold generation retained |
| Repeated cap triangulation | Bounded snapshot cache; algorithm and triangles retained |
| Interference BVH/pose transfers | Resident facets, native material/affine poses and refitted bounds; original contact hierarchy retained lazily |
| Faceted STEP text copies | Direct entity writer; representation retained |
| Search bounds | Same sampled vertex extrema calculated in Rust |
| Binary materialization | Collision coordinate round trips and native preview packet copy removed; owned arrays/types and other buffers retained |
| Surface fingerprint/retention | Exact mutation detection and existing limits retained; no identity-only shortcut |
| Small scalar RPCs | Existing ordinary pose batch retained; no claim from scalar microbenchmarks |
| Exact dimensions cache | LRU promotion; both working precisions retained |
| SVG/DXF profile files | Existing required files and formatting retained |
| Continuous mechanical audit | Conservative opt-in work retained; no weaker clearance checks |
| Superseded preparation | Cooperative request control through generation and scene preparation |
| Callback overhead | Repeated work and duplicate trivial-triangle callbacks reduced; per-record control retained |
| Fine representation growth | Existing explicit 250,000-face/component rejection retained |

Performance reports must separate cold/warm and profiled/unprofiled work, compare
the same inputs/quality/outputs, and disclose memory and qualification limits.
Timing improvements do not establish industrial accuracy, material strength,
tool feasibility, GPU frame rates or full-period collision qualification.
