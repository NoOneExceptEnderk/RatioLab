# Rust engine integration and application boundaries

The current source tree uses the shared Rust kernel in the desktop application
and the browser. Native code loads through a C ABI; the browser loads the same
crate as WebAssembly. Python retains application orchestration, GTK, persistence,
reports and export-file workflows. This describes source behavior, separately
from the version present in an installed or hosted build.

A Git HEAD alone does not identify a dirty checkout. Before reconciling parallel
work, preserve its file content and review shared modules; replacing one complete
source directory with another can discard interface or engine changes.

## Boundaries to preserve

| Area | Compatibility requirement |
| --- | --- |
| Input normalization | Preserve I/O, printed shaft, variant, catalog/hardware and geometric validation order. Forward exact decimal sources and derived expression trees to the Rust boundary. |
| Family construction | Preserve parameters, units, frames, tooth indexing, body order, source indices, ports and construction assumptions. Rust operations must have native/Wasm parity and independent numerical/geometry checks. |
| Precision | Named analytic records retain their twenty-place agreement checks. Sampled geometry stays explicitly binary64; STL/GPU quantization and representation bounds remain separate. |
| Quality | Retain independent preview/export settings, project/history persistence, explicit unsupported sources and resource failures. Quality does not change the nominal tooth or validity rules. |
| Motion | Preserve shaft groups, ratio signs, pose continuity on RPM edits, finite rack limits and original deformation/material references. Geometry and contact cannot be inferred from speed equations. |
| UI | Preserve current layout, catalog, navigation and controls while changing engine calls. Geometry work does not authorize replacing interface workflows. |
| Async work | Retain document identity/revision gates, latest request ownership, cooperative cancellation, late-result rejection and unconditional native cleanup. |
| Export/CAD | Retain source indices, transactions, exact source metadata and current CAD connection. Optional prototypes are not automatic product routes. |
| Packaging | Match Python adapter, native library, Wasm and explicit browser module closure. Test the actual installed renderer separately before an authorized release. |

## Execution ownership

All catalog families use the shared Rust operations with Python application
adapters. Keeping an adapter module does not mean its tooth-construction
equations still execute in Python.

| Construction or workflow | Current ownership |
| --- | --- |
| Cylindrical, planetary, internal, cycloidal, strain-wave, worm, differential, Wolfrom, multistage parallel and rack geometry | Rust geometry/numerical operations; Python validation, component/catalog orchestration and model descriptions. |
| Straight, spiral and circular Zerol-style bevel pairs | Shared Rust constructors and trace/engagement operations; Python profile adapters and result presentation. |
| Hypoid and face gears, including offsets and joined/separated double helices | Shared Rust envelope construction, regularity/contact checks and adaptive surfaces; Python result/assembly adapters. |
| Topping and semitopping | Rust finished limits, secondary involutes or straight rack ramps, and effective primary contact; Python member/stage controls and exact-source transport. |
| Preview, motion and interference | Rust shared surface/pose/query operations with Python desktop scheduling and rendering; JavaScript/browser adapters use Wasm. |
| Projects, preferences and exports | Application-level validation/history and file transactions remain in Python/JavaScript. Rendered buffers and export encoders retain their declared numerical formats. |

There is one selected construction for each case. A missing library or Rust
error never silently selects a different Python geometry algorithm. Distinct
trace laws and constructions remain explicit; an adapter must preserve them
when serializing a request. See [new-family boundaries](rust-new-families.md)
and [the kernel protocol and precision contract](rust-kernel.md).

Projects retain `solidcraft-riduttori/1`, optional independent representation
settings and exact decimal source maps. Imported precise sources are validated
and preserved through save/reopen. Existing explicit meshes/stations retain
their construction limits; the adjustable sweep setting does not refine those
generators or establish their total geometric error.

The complete surface-position error budget remains limited to the qualified
single external spur/helical/double-helical constructions described in
[the error-budget documentation](geometric-error-budget.md). Other families,
assemblies and STEP reader tolerances remain explicitly unqualified. Neither
integration nor passing functional tests establishes industrial conformity,
tool feasibility, strength or manufacturing accuracy.

Before porting a distinct mechanism, retain its exact references and domains,
coordinate conventions, limiting cases, independent benchmarks, expected
interference behavior, tests and explicit manufacturing limits. Review the
meaning of module, pressure/spiral angle, cutter assumptions and contact
quantities separately for each mechanism; cylindrical ISO relations alone
do not qualify a hypoid or face-gear surface.

## Integration checks

1. Compare content snapshots against their common ancestry and current local
   changes. Separate mathematical adapters, intentional geometric changes and
   interface/resource changes; reconcile each shared module deliberately.
2. Check preserved existing families and newly ported mechanisms with one
   normalization/construction contract. Document construction ownership and
   do not select a second mathematical implementation after an engine error.
3. Run `scripts/check-rust-engine.py` and its isolated GUI suite. Extend their
   reviewed module list for new mechanisms; required native/Wasm checks and
   missing coverage must fail rather than turn into successful skips.
4. Recheck original outputs where geometry is preserved. For intentional
   sampling/construction changes, compare against the declared continuous
   reference, error components, topology and resource constraints.
5. Verify saved projects, quality/history, RPM continuity, selection, exports,
   browser module closure and real rendering using isolated profiles. Source,
   installed application, browser bundle and released artifacts are distinct.

New source changes arriving during this process require a refreshed inventory.
Building native/Wasm products, updating an installed desktop copy and publishing
a release or hosted app are separate operations; passing source tests alone
does not establish any of those delivery states.
