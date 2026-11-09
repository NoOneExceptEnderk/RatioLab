# Resident collision geometry and owned preview transfers

The discrete interference checker consumes the existing shared facets inside
Rust. Preparation no longer exports every face/triangle to Python and sends
the same coordinates back as JSON. The literal face traversal, triangulation,
holes, sample counts and interpolation requests are retained. Exact part-content
fingerprints still invalidate changed source geometry or decimal expressions.

## Poses and conservative queries

Each pose applies the same binary64 affine function to the original world
vertices inside the kernel. It does not repeatedly transform a preceding pose
or introduce an inverse-frame approximation. The complete world-space finite,
closed-edge, orientation, positive-volume and thin-triangle checks still run.
Custom, reflected or singular transforms do not bypass these checks under an
assumption that an input matrix must be rigid.

The existing BVH partition is shared through immutable leaf indices. Bounds
are refitted from the actual transformed triangles, then combined from children
upward. They are not estimates from ideal circles or transformed box corners.
Exact vertex-membership keys are retained with the mesh instead of being rebuilt
for every pair. Nearest, ray and containment calculations keep the established
triangle primitives and conservative unresolved outcomes.

The bounded contact-witness search depends on traversal order. Near contact,
the original world-sorted hierarchy is therefore built lazily for that pose and
reused by subsequent pairs. The `tolerance + 1e-8 mm` branch selects this fallback;
the final relation still uses the original requested tolerance and witness law.
Farther separated minima can return a different equally valid pair of closest
points on parallel faces/edges. Tests compare distances and actual witness
membership rather than demanding a unique witness where none exists.

All pairs remain eligible for checking, including expected interfaces and
components of the same nominal member. This is still a discrete diagnostic,
not continuous, loaded-contact or manufacturing qualification.

## Prescribed deformation

Strain-wave preparation validates the same original material-reference rows
and nominal reconstruction. Every pose maps those immutable rows with the
existing Fourier/ellipse function before applying the affine matrix. Axes,
pitch radius, length and diaphragm must exactly match the validated metadata.
Unknown, stale, conflicting, missing or nonfinite references/deformations fail.
Every shared triangle vertex needs an original material reference.

The nominal reconstruction guard remains 1e-7 mm, a protocol consistency check,
not a manufacturing-accuracy claim. No new elastic solution or tooth equation
is introduced. Python no longer receives and retransmits the material-point
arrays at each pose.

## Ownership and cancellation

Collision handles are bound to the native library/Wasm instance that created
them. A pose owns its world geometry and retains the shared partition indices
after its source handle is released. Cross-backend pair queries are rejected.
Python materializes an owned tuple of triangle coordinates only when a caller
explicitly requests it; ordinary interference preparation uses small handles,
matrices, deformation parameters and result records.

Completed poses and base meshes are explicitly closed on success, cancellation,
unsupported geometry and exceptions. Cancellation is checked after a newly
created handle is adopted so its owner can release it before propagating the
original exception. Resource-release operations bypass cancelled request scopes.
The existing native handle/triangle/work limits and face/assembly budgets remain;
no partial or coarser geometry is accepted to accelerate a check.

For desktop preview, the binary packet is validated while its Rust owner is
alive. Coordinates copy directly into owned Python float arrays, avoiding a
temporary full-packet `bytes` allocation. Temporary ctypes views are released
even when copying raises. Only the owned arrays and metadata escape. Active
request controls check between 4 MiB blocks; native result memory is freed on
every exit. Without active control, each array uses a single copy.

Wasm retains its owned-byte decoding path, avoiding views that could outlive
`memory.grow`. Native checked callbacks do not imply mid-call interruption of a
synchronous Wasm request. Array types, float bits, scene metadata, normals,
materials and draw ranges remain unchanged.

## Costs that remain

Refitting, full world validation, difficult narrow-phase queries, contact
hierarchy fallback and quadratic pair counts still consume time. Retained
vertex keys and possible canonical nodes trade memory for repeated work; a
triangle/handle limit is not a process RSS cap. The broader renderer still uses
expanded normal/material buffers, and other geometry APIs still create their
existing owned lists or byte arrays. Existing exact fingerprint/cache budgets
are unchanged. Performance evidence must distinguish these costs from the
removed coordinate round trips and must compare identical coverage and quality.
