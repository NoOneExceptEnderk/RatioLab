# Rust construction of bevel, hypoid and face pairs

The shared native/WebAssembly kernel constructs all current standalone bevel,
hypoid and face-gear variants. The Python modules retain catalog fields, project
compatibility, report wording and thin inspection adapters. They do not construct
the flanks, choose surface grids, certify numerical cells or build these meshes.
An error in Rust is reported to the caller; there is no Python geometry fallback.

| Family | Shared construction | Retained conventions and limits |
| --- | --- | --- |
| Bevel pair | Straight spherical involute, logarithmic spiral and circular developed Zerol-style lead | Planar heel/toe caps; constant cylindrical bores; opposite local trace hands; sufficient cap-aware engagement; nonworking below-base relief |
| Custom hypoid | Pinion envelope generated from the spherical/logarithmic master, with signed offset | World pinion +X through `(0,E,0)`, wheel +Z; derived hands; offset limited to 6% of reference cone distance; first-derivative and connected-track numerical checks |
| Face pair | Spur, signed helical, separated and joined double-helical pinions, with signed offset | Pinion +X through `(0,E,2rp)`, wheel +Z; positive rolling ratio; equal-count generating involute; numerical regularity, ordering, width and retained-track checks |
| Joined face transition | Upper/lower envelope, pinion cusp sweep and concave intersection trimming | Height-dependent seam anchors; a common supported annulus; zero-helix spur limit; one retained smooth complete track per flank |

The equations, manufacturing exclusions, frames and independent benchmarks are
in [bevel pairs](bevel-pair.md), [custom hypoid](hypoid.md) and
[face gears](face-gears.md). The port preserves these constructions; it does
not substitute a production cutter tooth system or add a strength qualification.

## Reference scope

The accepted ISO 21771:2007 normal/transverse cylindrical conventions remain
in use for the face pinion through the existing analytic cylindrical kernel.
That standard is not a blanket conformity claim for the custom bevel, hypoid or
face-wheel solids. Their sources are applied to the appropriate equations:

- [KHK section 4.4, table 4.17](https://www.khkgears.co.jp/gear_technology/basic_guide/khk372/): bevel reference pitch dimensions and the conservative width rule.
- [Dong et al., section 2, equation 1](https://www.frontiersin.org/journals/mechanical-engineering/articles/10.3389/fmech.2025.1643228/full): spherical involute flanks, with the lead and cap definitions documented separately.
- [Nie, Chen and Liu, equations 7–8](https://journals.sagepub.com/doi/full/10.1177/16878132241228195): coordinate transformation and normal/relative-velocity envelope condition. RatioLab's chosen master is different from the paper's manufacturing master.
- [NASA/CR2000-209909, equations 21–24 and 63–69](https://ntrs.nasa.gov/api/citations/20000027536/downloads/20000027536.pdf): involute face envelope, rolling and offset layout. The spur offset recommendation is used conservatively for the offered helical layouts as documented in the face reference.
- [NASA/CR2005-213443, equations 15–18](https://ntrs.nasa.gov/api/citations/20050080713/downloads/20050080713.pdf): helical face generating surface, rolling, transformed family and meshing condition. Its rounded shaper tip, localized contact and production setup are not inferred for the custom relief.

## Precision, transport and bounded work

Named cylindrical analytic results retain their decimal sources and the existing
high-precision agreement check. Sampled geometry uses binary64. More decimal
places in a report do not prove a smaller surface error.

The existing 0.003 mm finite refinement criteria and their stated scope remain
unchanged. Numerical interval cells expand basic operations by adjacent IEEE
values and use host libm for transcendental functions. They are distinct from
the rigorous transcendental arithmetic used by the separate cylindrical total
error audit. The joined cusp and trim are not a global interval surface proof.

Construction calls return owned coordinate blocks in
`ratiolab.geometry-buffer/1`. A face mesh uses one consecutive binary64 triangle
block; the Python adapter restores the existing mesh structure. No extra coordinate
quantization is introduced. Exact-circle provenance of the blanks/bores survives
the boundary. Preview, collision and exports consume the same constructed parts.
The native solid reader also accepts the flat triangle representation directly;
it must not silently treat a freeform wheel as its circular blank extruded through
the nominal width. Malformed or ambiguous triangle representations are refused.

Vertex, section, interval-cell, refinement and 250,000-triangle limits remain
explicit refusals. Long loops check request cancellation. Prepared generators
are private to a thread/instance, bounded to two per family, with bounded point
caches and no retained caller callbacks. A new construction clears evaluation
caches so previous diagnostic calls or cancellation cannot spend its budget.

## Verification

The independent normals, literal world velocities, signed frames, dense circle
or swept-involute oracles, wrong-phase collision controls, positive closed-solid
volumes, independent refinement probes, projects, operating edits and exports
remain in the existing bevel/hypoid/face test suites.

`test_rust_new_families.py` additionally checks that builders bypass Python
generator/station math, preserve owned data and circle provenance, retain precise
pinion analytic sources, reject bad native inputs, cancel and retry correctly,
and compare every coordinate and metadata field with actual WebAssembly output.
Native/WebAssembly agreement and finite collision samples do not establish
manufacturing tolerance, loaded contact, fatigue or industrial certification.
