# Surface interpolation accuracy

A qualified [external cylindrical complete-surface budget](geometric-error-budget.md)
now encloses the exact source/trim, transverse profile, grid/cleanup, filled caps,
placement and output quantization. Its scalar total names binary64 model geometry;
STL has its own bound, while STEP exchange and other families remain explicit.

This is the first part of an error budget for cylindrical geometry. It controls
the side triangles of a procedural sweep relative to its existing sampled 2D
contours. It does not establish the error of those contours against a
theoretical tooth, a manufactured flank tolerance, or a quality grade.

## Contract and reference surface

Part.surface_tolerance_mm is a positive finite length in millimetres, default
0.02 mm. The same sampled solid feeds native/browser preview, picking,
interference, STL and faceted STEP tooth surfaces. The sampler now chooses
subdivisions from this length budget instead of a fixed 6-degree increment.
Tightening the budget can increase geometry size and preparation time.

The JSON operation solid_sampling and Python solid_geometry.sampling_report
return ratiolab.surface-sampling/1 records. These separate the requested
interpolation budget, calculated bound, section count and applicability. The
Python record also retains the profile's existing chord threshold and explicitly
sets profile_error_globally_bounded to false. The existing quarter/midpoint
profile criterion is not a proved global bound. Interpolation metadata is reused
only with its immutable surface snapshot and returned as an independent copy.
CAD metadata queries the current snapshot when exporting a Part whose requested
surface tolerance has changed. A generated Design's analysis remains a snapshot
of its generation; programmatic Part edits should use sampling_report for live
inspection. Solid topology and validity checks remain separate from this bound.

For an ordinary sweep the reference is the rotation of every straight segment
of the transverse contour, with angle linear in axial position. A double helix
is split at its apex, groove endpoints and shoulders. Within each interval,
corresponding local contour vertices and holes interpolate linearly while twist
interpolates linearly. Groove endpoints and all other landmarks are retained.
Refinement preserves contour correspondence; an unexpected topology or
non-affine intermediate loop rejects this bound.

Explicit mesh faces or precomputed stations do not supply this continuous
reference. Their records have status not_evaluated and null bound/target_met;
their construction and existing sampling remain unchanged. A small requested
number does not turn an arbitrary station model into a verified surface.

## Bound, including triangle interiors

On a landmark interval write

    X(u,t) = R(theta*t) [(1-t) P0(u) + t P1(u)],   0 <= u,t <= 1,

where P0 and P1 are corresponding straight contour edges, theta is the total
twist in radians and R is rotation in the local XY plane. Local Z is affine,
so it introduces no interpolation residual. Let

- r bound the radius of all endpoint vertices;
- d bound the displacement of corresponding endpoint vertices;
- e bound the length of each edge at either endpoint;
- c bound the change of the edge vector across the interval;
- s be the operator norm mapping a local XY error into world XYZ.

With n equal axial subintervals, a bound on the corresponding-point distance is

    axial = s (r theta^2 + 2 |theta| d) / (8 n^2)
    mixed = s (|theta| e + c) / (4 n)
    interpolation error <= axial + mixed.

The axial term follows by bounding the second derivative of X in t and applying
the linear interpolation remainder. The bilinear patch between endpoint edges
differs from either diagonal's triangles by at most one quarter of the norm of
its mixed corner difference. The rotation inequality
norm((R(delta)-I)v) <= |delta| norm(v) gives the mixed term above.

The mixed term matters even when the vertex helices are well approximated:
small errors on those traces alone do not bound the interior of the triangles.
The standard second-order interpolation result is discussed in Driscoll and
Braun, [Fundamentals of Numerical Computation, 5.2](https://fncbook.com/pwlin/).
The sweep/triangle specialization above is derived for this reference surface,
not attributed to a gear standard.

Bounds and geometry are evaluated in binary64. This is an analytic interpolation
bound evaluated with floating-point arithmetic, not outward-rounded interval
arithmetic. It excludes placement roundoff, transverse profile sampling and
binary32 conversion in GPU/STL outputs. A complete gear error budget must cover
those separately; the fields must not be relabelled as total model accuracy.

## Resources and use

When the ordinary plan exceeds the 250,000-face budget, the sampler can balance
transverse and axial subdivisions. It subdivides selected **straight segments
of the existing polygon**, consistently across every landmark loop, then
re-solves the same axial and mixed interpolation bounds. This adds no analytic
tooth-curve samples and changes no nominal profile. A shorter edge reduces its
mixed bound; a few long edges no longer force dense axial rows everywhere.
Candidate plans keep the same section/face limits and include an allowance for
binary64 collinear interpolation. An invalid or exhausted plan is refused.
The bounded candidate search is a cost heuristic, not a proof of globally
minimal triangle count.

The selected immutable plan, refinement map and report share the existing
bounded surface cache. Previous successful plans retain their original geometry.
Newly feasible Fine cases have an explicit `collinear_edge_refinement` record;
their representation differs from the formerly rejected request, not its
continuous reference or requested interpolation error.

If a rigid native preview would exceed its 128 MiB packet budget only because
of dense all-zero material attributes, it can store an explicit constant-zero
attribute instead. Positions, normals, draw ranges and mesh detail are retained.
The desktop renderer uses the OpenGL constant attribute and restores the array
when switching to dynamic material maps. Actual packet bytes still obey the
same ceiling; strain-wave material data is never replaced with a constant.
The browser's separate one-million-triangle assembly limit is unchanged.
Passing the sampler's per-component limits or the desktop preview packet limit
does not guarantee that a complete Fine assembly fits that browser limit.

The sampler chooses the smallest equal subdivision count satisfying its bound.
The ordinary-sweep interval limit remains 288; double helices retain the
512-section limit. The shared 250,000-face limit is checked before constructing
the expanded sweep. An exhausted budget is an error; the engine never silently
accepts a coarser surface.

For programmatic inspection:

    from geometry import generate
    from solid_geometry import sampling_report

    design = generate('helical')
    part = design.parts[0]
    report = sampling_report(part)

Changing a Part's surface_tolerance_mm changes its exact surface-snapshot key.
It controls this interpolation component only. Independent preview/export
settings are now persisted and available in desktop/browser controls; see
[representations](geometry-representations.md). A global transverse-profile error
bound for other families and a complete STEP exchange budget remain separate work.

ISO 21771:2007 nominal relations, existing cutter constructions and analytic
decimal results are unchanged by this sampler. No manufacturing-conformity,
loaded-contact or strength claim follows from the bound.
