# Shared Rust geometry kernel

The current source tree integrates this kernel with the desktop and browser
applications. See the [application boundary and compatibility requirements](engine-integration.md).
Python still owns application orchestration and file/UI workflows; the kernel
boundary does not make every application result exact or preserve twenty
decimal places throughout the complete export/display chain.

The crate `rust/geometry-kernel` builds a native C ABI library and a WebAssembly
module. Both accept the same versioned JSON request. Python and JavaScript
adapters transfer requests and results; the Rust operations do not call Python
to evaluate geometry. Missing libraries fail explicitly rather than selecting a
second mathematical implementation.

The opt-in `cylindrical_pair_audit` operation checks usable involute contact,
assembly/helix phases, continuous neutral clearance and both operating root
traces. It reuses the existing source curves and includes their approximation
enclosures. `cylindrical_validation.audit_design` verifies actual unchanged
components; the standalone CLI writes a report with explicit failed/unresolved
states and remaining qualification. See [scope, references and limits](cylindrical-mesh-validation.md).
It is not a complete loaded-contact, cutting or industrial conformity check.

`internal_fixed_plan` selects the explicit normal rack for fixed-axis internal
roots and records actual form limits. The same root radius reaches analytic
dimension/cache keys, profiles, measurements and exports; it is not an untracked
mesh-only edit. Paired tangent sampling has a whole-interval second-derivative
bound and material-side construction. See [fixed internal roots](fixed-internal-root.md).

Cylindrical [topping and semitopping](../tooth-tips.md) use this same kernel for
single gears, supported reducers and rack/pinion. Finished head limits and
remaining primary-flank limits are recorded separately; contact on semitopping
is excluded from effective coverage. Member/stage keys and exact input sources
reach both native and Wasm. The opt-in curved-CAD paths and continuous
`cylindrical_pair_audit` currently reject semitopping explicitly; ordinary
generation, exports and discrete triangle-based interference remain available.

## Numerical precision and sampled geometry

Exact construction reuse, compact axial checks, cap caches, sampled bounds and
cooperative request cancellation are described in
[geometry performance](geometry-performance.md). These preserve the geometric
contract and explicit resource failures; they do not add a strength module or
qualify a commercial cutting tool.

[Resident collision geometry and preview transfers](collision-reuse.md) explains
the native pose/material path, conservative BVH refits, original contact-order
fallback, backend-bound ownership and direct copying into owned preview arrays.

The analytic operations parse decimal input directly from JSON number tokens or
strings. Rational expressions use bounded arbitrary-size integer fractions;
quotient/remainder rounding applies ties to even exactly, without a binary
intermediate. This includes nominal spur radii, decimal parameter values and
rational speed relations. Trigonometric expressions calculate with 256 bits
and repeat with 512 bits. A result is
returned as a decimal string rounded to twenty places only if these two working
precisions agree at that rounding. Agreement is a numerical consistency check,
not an interval proof for every possible input or a manufacturing tolerance.

Extra decimal sources are retained in project parameters under `_decimal_inputs`.
Derived arithmetic is represented by a bounded expression tree and evaluated in
Rust from its source operands. Both the analytic result and its binary64
compatibility value are calculated from that tree, avoiding accumulation from
rounded compatibility operands. Save/load, undo and speed-only updates preserve
these sources. Exact bounds and integrality are checked separately from display
values; contradictory source/value pairs are rejected.

Sampled contours, placement, surfaces and their clearance checks use binary64
coordinates. GPU and binary STL transport use binary32. Increasing arithmetic
precision does not remove chord error, axial interpolation, quantization or
export-format limits. Each bounded solver must retain its stated threshold and
report unresolved refinement rather than silently accepting it. The analytic
precision record applies only to its named values.

`spur_total_profile_error` adds an audit-only outward interval reference to the
unchanged external cylindrical construction, including normal/transverse
conversion and independently isolated undercut trims.
`cylindrical_total_surface_error` encloses helical/double-helical sweep interiors,
source placements, resampled bores, joined apex and the existing groove/shoulder
recipe; the complete report also proves actual cap and mesh coverage.
`enclose_numeric` exposes the bounded elementary enclosures for independent checks.
The [complete-surface budget](geometric-error-budget.md) combines this source
bound with exact actual-cap coverage, placement and format-specific quantization.
Other constructions and STEP reader interpretation retain explicit unresolved
totals. This path does not replace generation or silently increase a quality limit.

Successful cylindrical analytic records are reused in a bounded, per-thread
64-entry cache keyed by exact source values, defaults, flags and the precision
contract. Failed calculations are never cached. Nearby decimal inputs that
share a binary64 presentation value remain distinct.

The Rust boundary includes tooth/rack curves, ZA/ZI envelopes, spherical bevel
sections, prescribed wave solids and immutable material maps, shared sections,
triangulation, affine poses and faceted-surface BVH queries. Python retains
application state, assembly/catalog orchestration, reports and file transports.
Standalone straight/spiral/circular bevel pairs, custom generated hypoids and all
face-gear variants also use shared Rust constructors, including numerical
regularity/contact checks, adaptive grids and joined cusp/trim surfaces. See
[the construction boundary and source scope](rust-new-families.md).
Existing metrology results derived from constructed binary64 profile intervals
remain explicitly tied to that numerical source; they do not acquire twenty
accurate decimal places merely by crossing the Rust ABI.

The opt-in `cad_spur_curves` operation reuses the existing external-spur rack and
involute recipe for bounded cubic approximation. It supplies continuous curve
domains and an explicit binary64 Hermite error estimate, separate from sampled
preview/STL geometry and analytic decimal arithmetic. The curved STEP encoder
and optional independent OCCT verifier are described in the
[curved CAD prototype](curved-cad-prototype.md). No CAD binding is a runtime
dependency and ordinary exporters retain their existing behavior.

The opt-in `cad_cylindrical_geometry` extension uses the actual external-helical
or internal-ring source construction. It bounds both profile interpolation and
axial rotation, supplies shared tensor-product spline controls, and rejects
exhausted refinement budgets. See [curved cylindrical CAD](curved-cylindrical-cad.md)
for its independent reader checks and the limits of the numerical estimate.
Both CAD paths use double interior knots for C1 continuity. Rust measures the
knot-reduction displacement and includes it in the curve/surface budget. The
independent reader compares all reconstructed Bezier span controls and positive
weights, accounting for knot-value changes as well as stored-pole movement.

Collision surfaces have explicit owned handles, closed/oriented topology and
positive-volume checks. Native long-running triangle/BVH operations poll a
synchronous cancellation/deadline callback; it is never retained after a call.
The browser uses its existing worker termination/restart cancellation. Query
work and cached surfaces have finite resource limits; exhausted searches return
an unresolved error rather than a clearance claim.

Bulk triangle coordinates and motion poses additionally use an owned binary
result ABI, shared by native and Wasm adapters. Each result starts with a status
byte, then a little-endian uint32 record count and packed float64 coordinates
or 50-byte binary STL records. Errors carry UTF-8 text after status 1. Requests
retain the versioned JSON envelope. Adapters copy results before releasing Rust
ownership; no views into freed native or growable Wasm memory escape. Output is
limited to 128 MiB per request. This removes large JSON triangle trees without
changing coordinate precision or the shared triangulation. STL files are written
in bounded blocks and replace their destination only on successful completion.
Motion plans batch all rigid poses for a phase in one call. Spiral bevel station
transforms also run as a batch. Station indices distinguish coincident axial
sections and shared outer contours with different bores.

Constructed worm/strain-wave, rack, bevel-pair, hypoid and face solids and spiral sections use typed Rust vectors
internally. Their bulk result format is `ratiolab.geometry-buffer/1`: status 0,
a little-endian uint32 metadata byte length, UTF-8 JSON metadata, then packed
little-endian float64 coordinates. Coordinate descriptors
`{"$ratiolab.f64/1": [offset, rows, columns]}` refer to scalar offsets in the
coordinate tail; columns is 2 or 3. Analytic strings and small report fields
remain in metadata. Metadata is limited to 16 MiB and the entire result to
128 MiB. The adapter validates descriptor bounds, overlap and full coverage,
and copies the owned result before freeing Rust memory. JSON operations remain
available through the same typed constructors for protocol compatibility.

Binary64 coordinate tails are appended in blocks of at most 1024 points, with
the original finite-value checks and cancellation checkpoint before each block.
Preview emission appends each complete six-float position/normal record. These
paths preserve the existing coordinate bits, record order and resource limits.
Coordinate decoding checks explicit and request-scoped cancellation callbacks
between owned blocks, and releases the native result before decoding.

Large rigid native previews may declare `material_fill: "zero"` with
`material_floats: 0`. Empty material arrays then mean the exact constant zero,
validated by the adapter and bound as a constant OpenGL attribute. Ordinary
fitting packets retain their dense layout. The same 128 MiB actual-result
ceiling applies; dynamic wave records remain dense. No coordinate is omitted.

The planetary layout builds a bounded batch of derived arithmetic sources.
Rust evaluates exact operands from the complete source tree; cancellation is
not accumulated through binary64 compatibility values. Min/max retains the
existing compatibility-value branch selection, including first-operand ties.
Branches containing no exact source keep their ordinary binary64 operation
order; exact subtrees are marked and never folded through that path. Selected
sources return in the existing arithmetic AST format, without internal graph
markers. The batch has at most 512 results and 65,536 traversed nodes; the
existing per-expression bounds still apply. Independent planetary support
circles are filled together before the completed design is returned, with
separate mutable contours and their original circle provenance.

The original local-to-world frame, handedness, shared surface winding, actual
holes and usable involute limits remain part of the interface. Strain-wave motion
remains a prescribed map; internal cylindrical fillets remain tangent circular
constructions rather than pinion-cutter envelopes. A generating reference can
use an explicitly signed cutter allowance; a physical pair's backlash remains
nonnegative.

Procedural cylindrical sweeps now choose axial subdivisions from an analytic
interpolation-error bound in millimetres, including triangle interiors. They
retain their existing sampled transverse profiles. The default
surface_tolerance_mm is 0.02 mm; it is a surface-interpolation budget, not an
overall gear tolerance. Explicit station/mesh constructions require their own
continuous reference and receive no new bound. See
[surface accuracy](surface-accuracy.md) for the reference, derivation and limits.

## Surface ownership and display buffers

Mutable application parts are transferred as immutable Rust surface snapshots.
The Python cache keys the complete content, including nested contours, float
bits and exact decimal expressions, together with the native library or Wasm
instance identity. A coordinate or source change invalidates the snapshot even
when the binary64 display value is unchanged. Its internal pickle bytes are
created and consumed in memory by this adapter only; they are not a project,
file or wire format and are never loaded from external input.

Python retains at most 64 cache entries and 16 MiB of snapshot keys. Rust limits
retained typed surfaces and section rings to a 64 MiB allocation budget, 96
surface handles and 32 active streaming cursors. These limits describe retained
cache data, not total process memory. If a snapshot does not fit, the same Rust
operations accept an uncached part; geometry and accepted sample counts remain
unchanged. Handles stay bound to their creating backend, and active owners or
cursors keep their snapshot alive after cache eviction. Cancellation and early
iterator closure release cursor resources.

Face, triangle and STL cursors return bounded pages from the same ordered
surface iterator. STEP point and face passes reuse one snapshot. The native
`ratiolab.preview-buffer/1` result contains scene metadata, then binary32
position/normal vertices and material coordinates. The browser
`ratiolab.web-mesh-buffer/1` result contains metadata, separate binary32
positions and normals, and optional strain-wave material coordinates. Both use
the status/metadata-length envelope of the geometry-buffer ABI. Their adapters
check lengths and copy owned data before freeing Rust memory.

Display preparation retains the existing face order, cap construction, normal
arithmetic, deformation map and browser triangle limit. It neither resamples
teeth nor changes solver tolerances. These transport and caching optimizations
do not extend the analytic precision contract to GPU or STL coordinates.

## References

ISO 21771:2007 is the selected edition for cylindrical terminology and nominal
geometry: sections 4.2/4.3 for reference dimensions and normal/transverse
relations, 4.7 for tooth widths, and Annex A.2 and A.5–A.7 for supported theoretical
span and gauge measurements. Positive physical radii/counts are used together
with an explicit internal flag. Supported measurements must lie on the actual
usable involute, excluding the generated root or constructed blend.
Relevant nominal relations include reference diameter (1), involute function
(18), base diameter (19), transverse tooth thickness (39), and its normal
counterpart (49). These use normal module in millimetres, normal/transverse
pressure angles, helix angle and profile shift with the stated ISO conventions.

ISO 53:1998 defines a reference basic rack. It does not define the actual
cutting tool. The existing rounded-rack tool and its land-limited radius are
recorded as a construction, without labelling every generated tooth as a
particular standard rack type.

ISO 1328-1:1995 and DIN 3967:1978 are reference material for industrial deviations
and backlash/tolerances. They do not turn a chosen number of arithmetic decimal
places into an accuracy grade. No conformity, strength or production-tool
certification is implied. Separate sources and limits for conical, worm,
cycloidal and strain-wave models remain in the corresponding technical pages.

## Building and checking

Use the pinned toolchain in `rust-toolchain.toml` and a native C linker:

```sh
python3 scripts/build-rust-engine.py --target all
cargo test --workspace --locked
cargo clippy --workspace --all-targets --locked -- -D warnings
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_rust_kernel.py'
```

The build collects the locked Rust dependency notices and the Rust standard
library notices under `target/ratiolab-rust-notices`. Native and browser bundles
include them alongside the compiled kernel and corresponding source/build
recipes. Building does not install, publish or update an existing application.
