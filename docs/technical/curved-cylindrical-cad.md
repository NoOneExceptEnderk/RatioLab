# Controlled helical and internal CAD surfaces

The [curved CAD prototype](curved-cad-prototype.md) also supports a single
external helical gear and the ring component of an internal spur/helical pair.
It remains an opt-in development path. The ordinary exporters, preview controls
and all other mechanism families retain their existing behavior.

```sh
PYTHONPATH=src python3 scripts/prototype-curved-cad.py work/curved-helical \
  --family helical --tolerance-mm 0.001
PYTHONPATH=src python3 scripts/prototype-curved-cad.py work/curved-ring \
  --project path/to/internal-helical.config.json --tolerance-mm 0.001
python scripts/verify-curved-cad.py work/curved-helical work/curved-helical-checked
```

Use an actual existing RatioLab project path for the second command. An internal
project exports **its ring only**, source component 2, including the original
tooth phase. The saved project still regenerates the complete source pair.
`curved-cad-info.json` records that scope explicitly. The nominal component is
checked against a fresh construction; edited contours, extra cuts, altered
circle provenance, unsupported placement and double helices are rejected.

The optional OCCT verifier and distribution boundaries are unchanged: it is a
development tool, not an application dependency. No source approximation is
accepted more coarsely when its refinement or allocation budget is exhausted.

## Nominal construction and axes

Input module `mn` and pressure angle `alpha_n` are normal quantities. The source
engine supplies `mt = mn/cos(beta)`,
`tan(alpha_t) = tan(alpha_n)/cos(beta)` and reference radius `rp = z mt/2`.
Its total twist is `theta = width tan(beta)/rp`, in radians. Positions are
millimetres, the axis is +Z and positive twist is the program's existing
counterclockwise section rotation about +Z. Reversing beta reverses twist;
normal dimensions and the transverse profile remain unchanged.

These conventions retain the accepted ISO 21771:2007 and related reference
editions in [calculations](calculations.md), without a claim of complete
standards conformity. A separate dimensional check is supplied by KHK's
[ABC's of Gears, Part B, equations (2.13)–(2.14)](https://khkgears.us/media/fqrlut1m/abcs-of-gearing-b.pdf):
`mn=2`, `z=30`, `beta=15 degrees` gives `d=62.1165708246 mm`.
The exporter uses the dimensions and trimmed domains already calculated by the
engine; it does not implement a second mechanical model.

The internal cavity uses the **existing tangent circular root construction**,
including its adapted blend radius. It is not a pinion-cutter envelope. Shifted
internal gears, cutter interference, manufacturing readiness and loaded contact
are outside this prototype. Exact circular root blends do not qualify the
underlying construction mechanically.

## External helical rack derivatives

The root remains the existing envelope of a rounded **normal** rack. Its
transverse corner is elliptical when beta is nonzero. Differentiating the spur
special case would therefore be incorrect. For the original tool recipe let
`c = mn/mt`, `A = rho (1/c-c)` and `q(t)=cot(t)`:

```text
phi(t) = (uc/c + A cos(t) - c vc q(t)) / rp
g(t) = (c (vc q(t) + rho cos(t)), rp + vc + rho sin(t))
C(t) = R(rotation - phi(t)) g(t)
```

This is an algebraic reduction of `Rack::point`, which still supplies endpoint
positions. On `-pi/2 <= a <= t <= b < 0`, use the same `Qk` cotangent derivative
bounds as the spur prototype. The bounds change to

```text
pk = (abs(A) + c abs(vc) Qk) / rp
G0 = hypot(c abs(vc) Q, rp + abs(vc)) + rho
Gk = c abs(vc) Qk + rho, k=1..4.
```

The unchanged rotating-product derivative estimate then bounds `C''''`. At
beta=0, `c=1` and `A=0`, recovering the spur construction. Internal involute
roll curves use the opposite angular involute sign, with exact circular blends.
Independent checks evaluate the original rolling-rack formula and fourth
derivatives at high precision, rather than differentiating the simplified code.

## Whole-surface error budget

Let `C(u)` denote a continuous source contour, and `B(u)` its bounded cubic
approximation, or its rational circular arc. The nominal surface is

```text
F(u,t) = (R(theta t) C(u), width t), 0 <= t <= 1.
```

Approximate the rotation operator with cubic Hermite interpolation `R_H(t)` on
each axial interval. Apply that **same linear operator to every profile control
point**. This gives a tensor-product B-spline surface; circular U curves have
degree 2 and positive rational weights, while cubic profile curves have degree
3. V has degree 3, and its Z coordinate is linear up to the explicitly bounded
C1 reconstruction roundoff below. No surface is fitted through
sampled sections. Shared section intervals and pole rows give identical boundary
trajectories on adjacent faces.

If `Ep` bounds `C-B` and `rmax` bounds the norm of all profile control points,
positive rational weights give the convex-hull bound `norm(B(u)) <= rmax`.
For axial interval size `h`, use

```text
Ez <= 1.415 rmax theta^4 h^4 / 384
norm(F - (R_H B, width t)) <= Ep + Ez.
```

The first error is rotated by the true orthogonal operator; it is not amplified.
The second is the Hermite remainder of a rotated point. This estimate covers
the entire tensor interior, including both parameter directions. It does not
merely compare end sections or a few points on vertex trajectories.

The basis and convex-hull reasoning follow standard tensor-product surface
properties; see [Michigan Tech, Bezier surface properties](https://pages.mtu.edu/~shene/COURSES/cs3621/NOTES/surface/bezier-properties.html)
and [Patrikalakis, Maekawa and Cho, MIT, section 1.4.4](https://web.mit.edu/hyperbook/Patrikalakis-Maekawa-Cho/node19.html).
The scalar Hermite remainder and conservative vector factor are documented in
the spur prototype. A rational arc's positive weights preserve its geometry
under the linear rotation operator.

`requested_surface_mm` is the total approximation request for this prototype.
The report separates `profile_bound_mm`, `axial_bound_mm`, their sum and a
scale-dependent resolution guard. Limits are 32,768 profile pieces, 256 axial
intervals and 500,000 surface poles. These are explicit prototype resource
budgets, not manufacturing tolerances or a one-micrometre product floor.
Requests below numerical resolution or beyond those budgets raise an error.
Project `quality.preview_mm` and `quality.export_mm` keep their existing,
separate procedural-sweep interpolation meaning.

All bounds are analytic estimates evaluated in binary64, not certified interval
arithmetic. Evaluation roundoff, STEP-reader operations, physical profile
qualification and manufacturing error remain separately stated limits.

## STEP and numerical verification

### C1 continuity for CAD Boolean operations

The first prototype collected cubic Hermite pieces with triple interior knots.
Although their tangent handles came from the same analytic derivative, a cubic
B-spline with triple knots is classified as C0 by the CAD kernel. FreeCAD 1.1.4
with OCCT 7.8.1 rejected that representation in its strict Boolean argument
check. BRep validity and a successful test cut alone did not reveal this limit.

The Rust encoder now uses **double interior knots**, giving C1 continuity. For
adjacent spans of lengths `hL,hR`, retain the incoming and outgoing tangent
handles `L,R` and reconstruct the shared point as

```text
alpha = hL/(hL+hR)
Pnew = (1-alpha) L + alpha R.
```

Knot insertion recovers the original Bezier handles and only replaces the join
point. The maximum displacement of these endpoint controls bounds the change
over the whole chain by positivity of the Bernstein basis. The encoder measures
that displacement, rejects it if it exceeds the numerical guard, and adds it
to the profile error budget. The same construction in the common rotation/Z
chain adds `max(rmax,width)*delta` to the axial budget. The source curves and
their mechanical equations are unchanged. This is a bounded knot reduction,
not a fit through sampled vertices. It reduces a chain of `n` cubics from
`3n+1` to `2n+2` stored poles, with the same spans and side faces.

See [Michigan Tech, B-spline continuity](https://pages.mtu.edu/~shene/COURSES/cs3621/NOTES/spline/B-spline/bspline-curve-prop.html)
and [knot insertion](https://pages.mtu.edu/~shene/COURSES/cs3621/NOTES/spline/B-spline/single-insertion.html).
The estimates remain numerical binary64 bounds, not certified interval arithmetic.

### Independent import checks

Nonzero-twist sides are polynomial or rational `B_SPLINE_SURFACE_WITH_KNOTS`.
At zero twist the writer retains linear extrusions and cylinders. The external
bore or internal ring's outside cylinder remains analytic in both cases. Every
topological edge is shared with opposite winding. Internal cavity sides and cap
holes reverse the material boundary consistently. The existing STEP path for
the original external spur prototype is retained.

The independent OCCT verifier checks solid validity, shared geometry, surface
types, base profiles and interior probes in **each axial span**, then repeats
after OCCT write/read and performs a Boolean through-hole edit in known solid
material. The source project and operating state remain intact. It also checks
the complete imported spline control nets and positive weights after independent
OCCT conversion of every span to Bezier form. This also accounts for rounding
of knot values: with C1 knots, unchanged stored poles alone do not bound the
shape if the knot values change. If Bezier poles
move by at most `delta`, and relative weight changes after a common scale
normalization are bounded by `eta<1`, then

```text
reader_surface_bound <= delta + 2 Rmax eta/(1-eta).
```

This follows from positive normalized rational coefficients: their L1 change is
at most `2 eta/(1-eta)`. The verifier requires the controlled span decomposition
and C1 continuity, and checks every reconstructed pole and weight, rather than
inferring surface preservation solely from samples. It adds the resulting
numerical encoding estimate when checking the remaining approximation margin.
This covers the controlled spline surfaces; it is not an interval certificate
for every trimmed BRep boundary, reader tolerance, or an arbitrary imported CAD.

A negative control changes an interior surface pole without changing its boundary
curves: the BRep can remain valid, but the accuracy verification must reject it.

The volume check must also account for the rotation approximation. In general
`R_H` is slightly nonorthogonal between endpoints. If its scalar components are
`a(t),b(t)`, every transverse area scales by `a(t)^2+b(t)^2`. The verifier
integrates this degree-six polynomial times the derivative of the reconstructed
Z coordinate as a degree-eight Bernstein polynomial independently. It subtracts an analytic
bore for an external gear, or subtracts the swept cavity from an analytic outside
cylinder for a ring. Assuming constant area would confuse an approximation
effect with a serializer or kernel error.

These checks qualify the named cylindrical prototype relative to its existing
source construction. They do not establish conjugacy, cutter-generated roots,
strength, manufacturing readiness or compatibility with every CAD reader.
The emitted file is neutral STEP Part 21 with the `CONFIG_CONTROL_DESIGN`
(AP203) schema, in millimetres; no target CAD is a runtime dependency. The
controlled-source checker expects the original surface kinds and span layout.
A CAD may legitimately merge faces or replace an extrusion with a NURBS surface;
a layout mismatch alone does not establish deformation. Application exchange
tests need independent geometric comparisons as well as versioned topology
checks. A symmetric-difference volume is useful evidence, but does not certify
a global millimetre tolerance or preservation of native gear feature history.
No Fusion, GearTrax or Gleason GUI import, Windows/macOS run or frozen-app
installation is implied. A user-facing rollout, double helices and other
mechanism families require their own scoped integration and qualification.
