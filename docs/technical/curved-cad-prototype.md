# Curved spur CAD prototype

This is an **opt-in development prototype for one external spur gear**, separate
from the ordinary STEP export and its menu. It answers a bounded question: can
the current Rust construction produce curved, editable CAD faces with an
explicit approximation estimate and independently checked STEP reimport?

The additional [helical and internal cylindrical paths](curved-cylindrical-cad.md)
extend this controlled prototype with a combined whole-surface budget. The
original spur path described below retains its previous representation.

The prototype uses the existing rounded-rack envelope, useful involute domain,
profile shift and allowance conventions. It does not fit curves through the
preview vertices or smooth away an undercut. No gear equations or accepted
reference editions change: ISO 21771:2007, ISO 53:1998, ISO 1328-1:1995 and
DIN 3967:1978 retain their existing, separately documented domains. This work
does not establish general compliance with those standards or qualify a cutter.

Supported input is an unchanged, unplaced `spur` construction with 3–200 teeth,
a round concentric bore or no bore, and no added components. The existing
generator must accept the design first. Modified contours, keyways, unsupported
assemblies, explicit stations and meshes are rejected. Helical gears and the
ring of an internal pair use the separate path described above. Other families
keep their current exporters. This is not a new general CAD kernel.

## Generate and verify a sample

From a built source checkout:

```sh
PYTHONPATH=src python3 scripts/prototype-curved-cad.py work/curved-spur \
  --tolerance-mm 0.001
```

An existing RatioLab `solidcraft-riduttori/1` spur project can be supplied with
`--project path/to/model.config.json`. The new directory contains `gear.step`,
`curved-cad-info.json` and a compatible project with exact input sources and
preview/export settings preserved. Existing destinations are never overwritten;
write failures leave no published partial directory.

For independent validation, use a separate development Python environment with
`cadquery-ocp-novtk==8.0.1.1.0` and its matching proxy wheel. These are the
[upstream OCP build variants](https://github.com/CadQuery/ocp-build-system), not
RatioLab runtime requirements. Neither package is imported or bundled by the
application, browser engine, wheel or native build.

```sh
python scripts/verify-curved-cad.py work/curved-spur work/curved-spur-verified
```

The verifier reads the emitted file using OCCT, independently measures it,
rewrites and reimports it, and cuts a small through-hole in the root annulus to
check editability. The output includes a detailed `verification.json` and the
OCCT roundtrip STEP. Passing this check does not establish import into every CAD
application. No Fusion, GearTrax or Gleason GUI import is implied.

## Reference curves and conventions

All lengths are millimetres. The gear axis is +Z; a transverse contour winds
counterclockwise viewed from +Z. The solid occupies `0 <= z <= width`. A curve
is extruded along +Z with no axial approximation. The two sides of each tooth
are reflected and rotated copies of the original positive-angle construction.
Trimmed root/involute domains come directly from `profiles.rs::external`; a
second intersection solver or alternate root construction is not introduced.

For base radius `rb` and involute roll `t`, the positive-angle flank is

```text
C(t) = R(delta) rb (cos(t) + t sin(t), t cos(t) - sin(t))
delta = reference_half_angle + inv(alpha_t)
C'(t) = R(delta) rb t (cos(t), -sin(t))
||C''''(t)|| = rb sqrt(9 + t^2)
```

`R` is a planar rotation. This Cartesian roll form equals the existing polar
form `r = rb sqrt(1+t^2)`, `angle = delta - (t-atan(t))`.

For the spur rack, let `rp` be pitch radius, `rho` rack corner radius, and
`uc, vc` the rack corner centre. These values are the existing tool recipe in
the report, not inferred dimensions. On its trimmed domain within
`[-pi/2, 0)`, put `q = cot(t)`:

```text
phi(t) = (uc - vc q) / rp
g(t) = (vc q + rho cos(t), rp + vc + rho sin(t))
C(t) = R(rotation - phi(t)) g(t)
```

This is an algebraic reduction of the existing rolling-rack formula for
`cos_beta = 1`. Endpoint positions are still evaluated by the existing
`Rack::point`; the reduced form supplies its analytic tangent and a derivative
bound. The original rolling-rack formula is evaluated separately by the Python
verifier. Real cutter envelope validity, relief and loaded contact remain
separate mechanical questions.

## Continuous approximation estimate

Each segment uses endpoint position and first derivative, with Hermite-to-Bezier
controls `P0=C(a)`, `P1=C(a)+(b-a)C'(a)/3`,
`P2=C(b)-(b-a)C'(b)/3`, `P3=C(b)`. For a scalar C4 function the classical
Hermite remainder is at most `M4 |b-a|^4 / 384`; see
[Amos Ron, CS412 lecture 13, pp. 1–2](https://pages.cs.wisc.edu/~holzer/cs412/lecture13.pdf).
Bounding both coordinate fourth derivatives by a vector-norm bound introduces
the conservative factor `sqrt(2)`. The implementation uses `1.415 > sqrt(2)`
and a small evaluation margin. It refines from this whole-interval estimate,
not from a few sampled midpoint distances.

The involute fourth-derivative bound is given above. For a rack segment
`-pi/2 <= a <= t <= b < 0`, use `Q=1/abs(b) >= abs(cot(t))` since
`tan(x) >= x` on `[0,pi/2)`. Absolute bounds for derivatives of `q` are

```text
Q1 = 1+Q^2
Q2 = 2 Q (1+Q^2)
Q3 = 2 (1+Q^2) (1+3Q^2)
Q4 = 8 Q (1+Q^2) (2+3Q^2)
```

With `pk=abs(vc) Qk/rp`, bounds for derivatives of the rotating factor are
`E1=p1`, `E2=p2+p1^2`, `E3=p3+3p1p2+p1^3`, and
`E4=p4+4p1p3+3p2^2+6p1^2p2+p1^4`. Bounds for derivatives of `g` are
`G0=hypot(abs(vc)Q,rp+abs(vc))+rho` and `Gk=abs(vc)Qk+rho` for k=1..4.
Leibniz's rule then gives

```text
M4 <= G4 + 4 G3 E1 + 6 G2 E2 + 4 G1 E3 + G0 E4.
```

The same profile approximation estimate applies to the exact linear extrusion:
adding an identical Z coordinate does not increase the transverse distance.
Circles are exported analytically, including the round bore. Shared endpoint
coordinates remove topological cracks; their measured displacement is added to
the recorded estimate. Larger-than-guard joins are rejected.

**This is an analytic estimate evaluated in binary64, not an outward-rounded
interval certificate.** It excludes evaluation/placement roundoff, STEP-reader
operations and manufacturing error. A scale-dependent numerical guard rejects
requests below this prototype's numerical resolution. No arbitrary one-micrometre
floor is imposed. Depth 20, 32,768 edges/pieces and the tooth-count limit are
explicit prototype resource bounds; exhaustion raises an error instead of
accepting a coarser result. `tolerance_mm` here controls the continuous tooth
curves; project `quality.export_mm` still controls the separate procedural-sweep
representation described in [geometry representations](geometry-representations.md).

## STEP representation and independent checks

Adjacent cubics on one original flank or root are assembled into one nonrational
cubic B-spline with the original parameter intervals as knot spans. This is a
bounded C1 representation using double interior knots. Rust measures the
endpoint-control displacement caused by knot reduction and includes it in the
curve error budget; it does not fit a new curve through sampled vertices. See
[the C1 construction](curved-cylindrical-cad.md#c1-continuity-for-cad-boolean-operations).
Constructed root/involute patch boundaries remain unchanged. There are seven curved side patches per tooth, independent
of the number of approximation pieces, plus the bore and two end planes.

Spline sides use `SURFACE_OF_LINEAR_EXTRUSION`; circular sides are cylinders.
Topological edges are shared by adjacent faces. The periodic bore has an explicit
line seam shared in opposite directions; the reader need not fit its own seam.
Coordinates are serialized with binary64 roundtrip precision. Neither decimal
count nor the STEP uncertainty declaration is an accuracy certificate.

The [OCCT STEP reader](https://dev.opencascade.org/doc/refman/html/class_s_t_e_p_control___reader.html)
and [BRep checker](https://dev.opencascade.org/doc/refman/html/class_b_rep_check___analyzer.html)
are used independently of the Rust transport and application generators to check:

- One non-null, valid solid, with exact curve-on-surface validation enabled,
  two planar end faces and the expected curved spline/cylinder sides.
- Imported edge tolerances, bounds and axial thickness in millimetres.
- Source-to-import curve samples at 33 positions per elementary piece, with
  separate theoretical-curve and serialization deviations. These are numerical
  probes, not a measured global Hausdorff certificate.
- Nine interior probes per side patch, projected onto its bounded imported
  surface and classified inside the trimmed face.
- Volume against an independent polynomial line integral of the cubic contour,
  circular sectors and analytic bore, using
  [span-aware Gauss-Kronrod integration](https://dev.opencascade.org/doc/refman/html/class_b_rep_g_prop.html).
  The ordinary Gauss overload gave a representation-dependent volume in the
  initial merged-spline experiment, despite matching curve geometry. Its value
  must not be treated as proof of geometric change or ignored without comparison.
- The same checks after an OCCT STEP write/read, and a Boolean through-hole cut
  that leaves one valid solid with the expected volume reduction.

A deliberately displaced spline control point is a negative control: the
original approximation record must not allow the modified STEP to pass.

## Dependency decision

Retain **OCCT as an optional development validator**, and keep the small curved
encoder and curve calculations in RatioLab's existing Python/Rust/Wasm stack.
This is the bounded prototype decision, not a commitment to replacing a complete
CAD kernel. The prototype requires no new Cargo or runtime Python dependency,
no C++/Python ABI binding in the shipped app and no second CAD Wasm payload.
Native/wheel and real Pyodide/Wasm checks must exercise the same encoder before
any user-facing rollout.

Embedding OCP or OCCT in the product would require separate native-platform and
Wasm builds, resource/cancellation integration, distribution and notices work.
The upstream [OCP wrapper](https://github.com/CadQuery/OCP) and
[OCCT license/exception](https://github.com/Open-Cascade-SAS/OCCT/blob/V8_0_1/OCCT_LGPL_EXCEPTION.txt)
are distinct components; this prototype does not distribute either. A full
runtime-kernel decision should follow evidence from additional surface families
and target CAD readers, rather than making the application depend on a large
binding merely to export this one supported construction.

The cylindrical extension qualifies the existing helical sweep and internal
tangent-blend representations under its own limits. Mechanical qualification of
roots/contact, double helices, other families and a controlled product
integration remain separate work. No global industrial accuracy is established.
