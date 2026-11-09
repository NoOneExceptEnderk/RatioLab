# Complete-surface error budget and applicability ledger

`geometry_error_budget.audit(design, 'export', require_total=True)` returns a
complete supported surface bound or raises `UnsupportedBudget`. Preview uses
`'preview'`. The ordinary `geometry_quality.report` includes the same ledger in
exported geometry-quality JSON. No profile, sampler, nominal dimension or quality
setting is changed by the audit.

The implemented complete proof covers unchanged external spur, helical and
double-helical gears, with or without their original concentric bore. Double
helices include joined halves and the existing separated/grooved construction. Exact decimal rational sources,
including cancellation expressions, are retained. Both ordinary rack tangency
and independently isolated undercut trims are covered when their domains can be
resolved. Arbitrary changed contours, stations/meshes, alternate root/sampling
constructions, unresolved critical branches and exhausted audit budgets do not
receive a total. Other families have an explicit unresolved ledger; their existing
per-component sweep bounds remain separate.

## Meaning of the total

The metric is **symmetric Hausdorff distance of the complete boundary surface**,
including the filled end caps and bore wall. It measures positions in mm, not
normal-angle error, volume error, gear grade or manufacturing tolerances.

| Field | Meaning |
| --- | --- |
| `status: bounded_complete_surface` | Every term in the declared binary64 model-surface chain is enclosed. |
| `total_error_bound_mm` | Upper bound for `total_error_representation: binary64_model_surface`. |
| `output_bounds.stl` | Separate bound including actual binary32 coordinate conversion; null if output topology collapses or cannot be qualified. |
| `output_bounds.preview` | Physical sampled-surface coordinates before rendering; screen projection, shader/motion arithmetic, rasterization and grid/stencil planes are excluded. |
| `output_bounds.step` | Explicitly unresolved: formatted planes/circles, trimming consistency and reader/kernel interpretation need their own exchange proof. |
| `total_error_status: not_evaluated` | A complete proof could not be obtained; the scalar total stays null and the reason is retained. |

Legacy `conditional_*_boundary_bound_mm` fields remain for compatibility. Use the
current status and `output_bounds` to interpret qualification. A conditional
fallback is not a successful complete proof. `require_total=True` fails instead
of returning that fallback.

On the default 24-tooth, module-2 spur, the complete model-surface upper bound is
about **0.01517 mm**. The unchanged Fine setting requests **0.005 mm sweep
interpolation**; straight extrusion has zero such residual. Fine therefore does
not imply a five-micrometre complete tooth. Reducing the transverse approximation
would require a separate, deliberate change to generation.

## Outward arithmetic and source construction

Rust `enclosure.rs` expands each IEEE binary64 elementary result to adjacent
representable endpoints. Rational source conversion is checked against the exact
integer fraction. Exact-zero identities avoid spurious intervals around an
absent bore. Runtime checks reject flush-to-zero/denormal-input modes.

The audit does not assume an error allowance for the host sine/cosine/atan
library. It evaluates range-reduced sine/cosine polynomials with explicit finite
Taylor remainders, and arctangent series after reciprocal/half-angle reduction.
Whole input intervals use monotonicity or the unit Lipschitz bound. Pi is enclosed
with exact rational Machin sums and the next alternating term:

```
pi = 16 atan(1/5) - 4 atan(1/239)
```

The identity can be checked using `(5+i)^4 (239-i) = 114244 (1+i)` and the positive
first-quadrant branch. Eighty rational terms per arctangent give an enclosure
before conversion to binary64. Trigonometric series and addition identities are
listed in [NIST DLMF 4.19](https://dlmf.nist.gov/4.19) and
[4.24](https://dlmf.nist.gov/4.24). These are numerical-analysis tools, not gear
standard tolerances. The outward inclusion principle is described by Kearfott in
[Interval Arithmetic Basics](https://interval.louisiana.edu/GLOBSOL/whatisop/node6.html).

The reference uses the existing ISO 21771:2007 nominal conventions and rounded
normal-rack construction from [calculations](calculations.md): mm, radians,
positive local Z, the original backlash split, shift, addendum/dedendum and
land-limited tool radius. No new cutter qualification or rack type is asserted.
The interval reference starts from the exact input sources, rather than freezing
already rounded tool coefficients.

For undercut, the sampled solver result only seeds an independent bracket.
Strict opposite residual signs establish an exact intersection; a strictly
positive interval derivative proves uniqueness throughout that bracket.
Unresolved critical cases are refused. See the sign/derivative root-isolation
principle in the [FLINT root-isolation documentation](https://fredrikj.net/fdoc/html/algorithms/ball-arithmetic/real-root-isolation.html).
Normal tangent domains use the original analytic join.
The isolated trim is the branch selected by the existing construction, not a
separate proof that an arbitrary physical generating-tool process selects it.

## Profile and repetition

The audit traces the actual public constructor, including its analytic decimal
record and the original sampler's accepted intervals. It reconstructs the raw
profile and requires its cleaned coordinates to match that constructor exactly.
Sampling thresholds and vertex order remain unchanged.

Second-order interval automatic differentiation encloses each curve's second
derivative. On an audit subinterval of length h, the endpoint interpolant has
error at most `M2 h^2 / 8`. This is the linear interpolation remainder in every
unit direction; see [Driscoll and Braun, section 5.2](https://fncbook.com/pwlin/)
for the piecewise-linear convergence principle. Involute roll parameterization
avoids a radial second-derivative singularity at the base. Actual source endpoint
errors and the uncertainty in the exact trim/domain are included.

Distance to a fixed chord is convex and 1-Lipschitz. Endpoint distance enclosures
plus the second-derivative remainder bound every source point against that
original chord. Endpoint perturbations supply the reverse direction; the code
adds two endpoint-error bounds. Audit refinement changes no geometry.

Both root arcs, the tip arc, reflected flanks and every repeated tooth are
covered. Repetition error is measured against exact-angle interval rotations of
each actual raw node. The coordinate grid and each discarded-node mapping are
then checked explicitly; no unquantified library-trigonometry margin or assumed
odd/even library symmetry supplies the result. Bounded refinement, depth, source
expression and vertex limits fail explicitly.

## Helical and double-helical surfaces

Inputs retain **normal** module `mn` and pressure angle `an`. The audit derives
`mt=mn/cos(beta)`, `at=atan(tan(an)/cos(beta))` and `rp=z*mt/2` with outward
intervals. The rack corner keeps the same normal-plane tool: its transverse
coordinate is `u=(uc+rho*cos(t))/cos(beta)`, with normal depth `v=vc+rho*sin(t)`.
It is not a straight-spur section rotated afterward. Both handedness signs use
the same transverse reference; the signed twist rate is `tan(beta)/rp` rad/mm.
See [Jönköping University, equations 9.4.1–9.4.3](https://mechanics.ju.se/MachineElements/herringbone-gears.html)
for lead, opposite halves and the normal/transverse conversion. These relations
use the ISO 21771:2007 conventions already chosen in this project; this is not
an ISO conformity assessment.

For one reference interval, `X(u,t)=R(theta(t))*((1-t)*P0(u)+t*P1(u))`, with
straight polygon edge coordinate `u`, affine axial coordinate `t` and linear
angle. Let `r` bound endpoint radii, `D` the largest endpoint displacement,
`L` the largest edge length, `C` the largest change of an edge vector, and
`Theta` the absolute interval rotation in radians. On `n` equal subdivisions:

```
axial <= (r*Theta^2 + 2*Theta*D)/(8*n^2)
mixed <= (Theta*L + C)/(4*n)
sweep <= axial + mixed
```

The first term follows from the second derivative in `t`. The difference between
the bilinear quad and either diagonal's triangles is the mixed corner difference
multiplied by a factor at most `1/4`; its norm is bounded by `Theta*L+C` on each
subinterval. This is a derivation for the declared sweep, not a gear tolerance
specified by ISO. The audit encloses these terms outward and checks every real
vertex against the exact-source section, including rational `j/n`, source width,
lead, placement and floating collinear-refinement coordinates. It never promotes
the older binary64 sampling estimate to an outward proof.

For a double helix, `h=(width-gap)/2`, with shoulder width
`min(.15, .08*h, .2*gap)` mm when the gap is positive. Each analytic piece is
audited separately, including the twist reversal, shoulder boundaries and both
groove boundaries. The existing groove reference is explicitly

```
G(q) = (.959*r_root + .001*|q|)*q/|q|
```

This retains the generator's slightly varying-radius core; it is not relabelled
as a perfect circular machining groove. Its nominal core datum is `.96*r_root`.
The actual sampled minimum used by the generator, actual polar conversions and
rounded shoulder decisions are compared with this exact-source reference.
The profile error propagates through the radial map using
`|x/|x|-y/|y|| <= |x-y|/min(|x|,|y|)`. The groove chord adds a separate bound for
`G` along each original polygon edge, using its enclosed second derivative and
eight audit cells against the same fixed chord. This changes no geometry. Affine
shoulder blends preserve the resulting bound. An unresolved polar singularity,
bore/core separation, source branch or audit domain refuses a total.

The bore bound is recomputed from the **actual resampled loop**: radial endpoint
residuals plus the exact-circle minor-arc sagitta. The original 96-node bore's
bound is not assumed to cover a differently resampled representation. Native
and JavaScript trigonometry can differ in their last binary bit: the bore proof
measures the actual radial residual instead of demanding bit equality with a
second prototype. Original circular provenance is still required by the public
report, and cap/topology/quantization checks still inspect the actual mesh.

## Filled caps and actual mesh coverage

A boundary-distance estimate alone does not certify a filled face. The reference
rack is proved radially monotone within its tooth sector, the involute occupies
the following radial domain, and the bore is separated from the root. The
actual polygon uses exact rational segment predicates to reject crossings,
touching/nested holes and incorrect winding.

For each curve/chord pair, append the bounded endpoint connectors. Projection
onto the chord gives a continuous homotopy fixing its endpoints. It remains in
the calculated tube of both boundaries; endpoint connectors are covered by the
extra endpoint allowance. These piecewise homotopies glue around the closed
loops. Winding cannot change outside that tube, so the filled cap regions obey
the same bound. The bore follows the corresponding circle/polygon homotopy.
This is the cap specialization used here, not a general CAD theorem claimed
for arbitrary curves or topology changes.

The audit then inspects the **actual shared triangle stream**. Exact local
orientation, equality of the triangle boundary chain and equality of signed
area prove that the caps cover the polygon and its hole without overlap. Every
side quad must have its two adjacent-source triangles and adjacent axial levels.
Only the two end levels may contain caps; no ring may be skipped. Every mesh edge must be
paired once in each direction. Added/displaced vertices, missing caps, reversed
triangles or a filled bore prevent a complete total.

## Placement and output

The exact declared affine coefficients and source width are enclosed, and their
placed boundary vertices are compared with actual binary64 vertices using exact
rational interval propagation. Convexity propagates the vertex allowance through
triangles. A positive nonsingular placement is required. The conservative XY
operator bound propagates the transverse error; it need not be the smallest
possible norm. Declared frame coefficients are the reference, not an independent
claim about any upstream construction that failed to retain its source.

STL adds the measured coordinate conversion residual of those actual vertices.
The binary32 connectivity is checked for vertex collapse and exactly collinear
triangles; binary64 collinearity is also rejected. Exact dyadic integer predicates
avoid costly repeated fraction reductions on large meshes. The bound concerns complete surface positions; it does not claim
normal-angle or load/contact accuracy. Exact closure and cap coverage do not
replace a global three-dimensional self-intersection check; the error metric
compares the actual triangle-surface sets. STEP vertex-text residuals remain in the
component ledger but are not relabelled as a complete exchanged-model bound.

## Independent checks and limits

The required native/Wasm suite checks elementary enclosures against exact
fractions and independent 140-digit evaluations, source curves and trim against
an independent 120-digit moving-rack/polar-involute oracle, actual STL coordinates,
full-surface and filled-cap witnesses. Missing/reversed cap triangles, filled
holes, huge translations, unresolved inputs and artificially reduced bounds are
negative controls. The same operations run in actual JavaScript/Rust Wasm.

This is a derived enclosure algorithm with exact topology checks and numerical
regressions. It is not a proof-assistant verification of the implementation,
industrial conformity certificate, strength analysis or manufacturing guarantee.
A null total for another construction remains a real limitation, not zero error.
