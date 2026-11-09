# Common mathematical / CAD recipe

`ratiolab.cad-recipe/1` transfers the source construction, not preview triangles.
The editable authority is the family, canonical variant and mechanical inputs.
The shared Rust kernel derives nominal component placements, cylindrical source
curves and finite-rack dimensions. Python validates project options, preserves
decimal sources and serializes the recipe; a CAD adapter creates native features.

This initial coverage includes single cylindrical gears, two/three-stage parallel
trains and rack/pinion source recipes. It does not imply that every CAD adapter
can reconstruct every recorded variant. Unsupported constructions fail explicitly.
The existing STEP/STL paths remain available with their own approximation limits.

## Wire definition

The companion [JSON schema](cad-recipe.schema.json) describes the versioned
envelope. `cad_contract.create`, `validate`, `edit` and `evaluate_component` are
the executable contract; validation re-derives all components. Serialized derived
positions and curves are never accepted as a replacement for the source model.

- `model_revision` pins the mathematical construction, separately from the app
  version. A changed construction needs a deliberate revision/migration.
- Lengths are mm; pressure and helix inputs are degrees; tooth phases are radians.
  Frames are right-handed. Gear shafts are +Z, rack travel is +X. Placement means
  local XY coordinates, followed by world translation at the given Z level.
- Positive rotation is right-handed about +Z. Each external stage reverses sign.
  Compounds have explicit shaft and rigid-group identities, independent of names.
- `parameters` retains compatibility numbers and `_decimal_inputs` source
  strings/expression trees. A twenty-place source must not first become a JSON
  binary64 number. Integer tooth counts stay integers.
- Components identify `cylindrical_gear`, `circular_extrusion` or `rack`, their
  source parameters, placement, phase and port. Double helices retain their
  groove/variant; this is not a claim of implemented smooth CAD coverage.
- `source_sha256` identifies canonical source fields using RatioLab's sorted,
  compact, UTF-8 JSON encoder. It is not an RFC8785 digest. Other receivers should
  keep this value opaque and use the shared validator, rather than reformatting
  numbers or inventing a second canonicalizer.
- Source units, frames, references, digest and derived components must match
  regenerated values. Unsupported versions and altered records are refused.

## Accuracy and shared equations

The selected references remain ISO 21771:2007 and ISO 53:1998. The normal-system
relations and terminology are shared with the existing cylindrical kernel.
ISO 21771:2007 4.2.4/4.2.7 and 5.5 distinguish reference diameter, module and the
backlash components. ISO 53:1998 Table2 supplies the basic rack proportions;
it does not establish conformity of an arbitrary modified gear or sharp-cornered
rack blank. The KHK references and independent examples are in
[parallel](parallel.md) and [rack](rack.md).

The recipe records an independent `cad_tolerance_mm`. Preview/export interpolation
settings never select the CAD curves. Normal-system dimensions retain the
256/512-bit agreement checks and twenty-place decimal results. Source curves,
placements and CAD coordinates use binary64. Additional displayed digits do not
certify geometric, manufacturing or industrial accuracy.

`cad_cylindrical_source` derives transverse dimensions from the original normal
inputs and uses the existing rack/involute trimmed domains. It never fits a
preview contour. The continuous helical source uses the existing controlled
curve/sweep implementation. Per-component results state their interpolation
bound, resolution guard and exclusions. Requests below resolution or beyond
curve/pole/face/transport limits fail; no coarser output is substituted.

The finite rack source uses straight transverse flanks, fixed rectangular ends
and corresponding axial traces. Its sharp corners remain nominal blank geometry,
not the rounded-root manufacturing qualification of ISO53. Default sampled axial
vertex traces retain the explicit 0.003 mm bound; this does not bound the entire
triangulated tooth surface. Its working stroke and nonperiodic motion remain
separate from the CAD geometric tolerance.

## Native SolidCraft adapter

`solidcraft_recipe.compile` builds native sketches, curves and extrusions;
`connection.Client.insert_recipe` sends them transactionally. The recipe is saved
on the owned group and retains all source parameters. No STEP import, sampled
tooth polyline or preview vertices enter this path.

Initial native coverage is **straight extrusions**: external spur gears, spur
parallel multistage assemblies with their shafts/hubs, and spur rack/pinion.
Native helical sweeps, double-helix relief and other families are explicitly
unqualified by this adapter. The common source recipe may still represent them;
the adapter refuses the operation before changing the CAD document. Smooth
source helical geometry remains available through `evaluate_component` and the
bounded cylindrical prototypes, with their declared scope.

SolidCraft does not provide a native RatioLab tooth-generator callback. Editing
module, tooth count, pressure or other source inputs therefore means editing the
recipe in RatioLab and rebuilding its native curves/features. This is external
parametric regeneration, not automatic gear regeneration from an arbitrary CAD
user parameter, and not attributes attached to an imported mesh.

Compilation and capability checks precede CAD changes. Replacement requires an
existing group with a valid RatioLab-owned recipe; display-name similarity is
insufficient. A checkpoint spans construction, timeline/closed-volume checks and
old-group deletion. CAD errors/warnings or failed body checks restore the former
document. Unrelated components and their native operations are preserved.

SolidCraft sketch point/curve limits and the 16 MiB local request budget are
retained. A native kernel may impose further boundary limits. These are reported
as errors, not bypassed by reducing accuracy or importing a faceted substitute.

## Fewer native curves with a controlled error

Some CAD sketch interfaces accept a clamped open-uniform cubic spline but cannot
take a custom knot vector. Sending every cubic Hermite interval separately can
exhaust the target's boundary budget. The native adapter uses **complete cubic
interpolation of the continuous source**, with exact source endpoint derivatives.
There is no interpolation of sampled preview vertices.

For a source interval with uniform knot spacing `h`, let `M4` bound the Euclidean
norm of the fourth derivative throughout that interval. Interior spline derivatives
satisfy `d[i-1]+4*d[i]+d[i+1]=3*(f[i+1]-f[i-1])/h`. Taylor bounds on positions and
derivatives give a residual at most `7*M4*h^3/12` when inserting true derivatives.
Diagonal dominance bounds the derivative error by `7*M4*h^3/24`. Relative to the
exact-derivative cubic Hermite pieces, the two derivative bases have total absolute
weight at most `1/4`, giving an additional `7*M4*h^4/96`. Including the conservative
vector Hermite remainder gives:

```
error <= (sqrt(2)/384 + 7/96) * M4*h^4 < M4*h^4/8
```

The core selects spacing with the larger right-hand bound, solves the tridiagonal
interpolation problem in the open-uniform basis, and retains exact endpoint
positions/tangents. Long or strongly varying domains split rather than exceeding
the pole budget. Endpoint joins have a separately checked displacement and error
allowance. The knot convention is four repeated end knots, simple internal knots
`j/n`, where `n=control_count-3`; no target-specific gear formula is involved.

These are analytic binary64 bounds, not certified interval arithmetic. Tests use
independent de Boor evaluation and direct continuous-source points. Target-CAD
reconstruction also requires independent geometric checks: source bounds alone
cannot prove the reader's knot convention or eventual BRep accuracy.

SolidCraft can split or change this spline basis during native processing and
STEP export. `source_interpolation_bound_mm` describes the submitted source
construction; it is not a certified bound for a CAD reader or a round-trip STEP.
Independent target checks must retain that distinction.

## Reproducible use on an isolated source checkout

```
python3 scripts/cad-recipe.py create examples/spur.config.json /tmp/gear.recipe.json --tolerance-mm .001
python3 scripts/cad-recipe.py prepare /tmp/gear.recipe.json /tmp/gear.commands.json
python3 scripts/cad-recipe.py send /tmp/gear.recipe.json
```

The last command explicitly changes the connected local SolidCraft document.
`SOLIDCRAFT_CONTROL_DIR` can select its token directory. To regenerate, write a
JSON changes object, use `edit recipe changes output`, then `send output --replace
GROUP_NAME`, using the returned owned group. No publishing or CAD application
installation is involved. A successful CAD operation still does not establish
tooth-root strength, cutter feasibility, loaded contact or overall ISO conformity.
