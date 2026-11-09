# Cylindrical pair qualification

This opt-in check examines the **unchanged nominal pair**, independently of
preview/export quality. It does not run on every GUI update. The Rust core owns
the calculation on native and Wasm targets; Python verifies the actual components
against the supported construction before requesting an audit.

Supported application models are fixed-axis parallel and internal pairs, with
spur, helical or double-helical teeth. The continuous-profile verifier currently
supports 3 to 200 teeth per member. It excludes extra cuts, component placement,
explicit meshes, other mechanisms and complete machinery. The low-level API can
also check an existing paired planetary internal profile, supplied explicitly as
`internal_plan`; this does not qualify a complete planetary assembly.

Topping is forwarded to the actual profile limits. **Semitopping is currently
unsupported by this continuous audit**, because its bounded curved-profile path
rejects that construction. This is separate from ordinary
[tooth-tip generation](../tooth-tips.md), effective primary contact calculations,
neutral internal polygon checks and discrete interference on the treated
triangles. An unsupported audit is not a clear result.

## Reference conventions

Lengths are millimetres; phases are radians, counterclockwise around +Z. For an
external pair O1=(0,0), O2=(a,0), and omega2/omega1=-z1/z2. For an internal pair
O1=(a,0), O2=(0,0), and omega2/omega1=+z1/z2. Tooth counts are positive in the
application; ISO's signed internal tooth count is translated explicitly.

`mn` is the normal module, `mt=mn/cos(beta)` the transverse module,
`alpha_t=atan(tan(alpha_n)/cos(beta))`, `rp=mt*z/2`, and
`rb=rp*cos(alpha_t)`. Profile shift is balanced, x1=-x2, for external pairs.
Internal pairs support zero shift only. The configured `j` is total transverse
pair backlash at reference distance, divided equally between the two profiles.

Sources: ISO 21771:2007, 4.3.7, 5.2-5.5.
The [MIT 2.007 lecture, slides 8-20](https://ocw.mit.edu/courses/2-007-design-and-manufacturing-i-spring-2009/resources/mit2_007s09_lec12/)
independently explains conjugate action, line of action, interference and contact
ratio. No text or standards tables are embedded in the implementation.

## Available contact and backlash

Use the actual usable involute limits after rack-envelope trimming or internal
tangent-circle blending, rather than extending involutes through the fillets.
Let `u1=sqrt(r1^2-rb1^2)` and `u2=sqrt(r2^2-rb2^2)` be roll lengths, and let
`S=a*sin(alpha_w)`, where `cos(alpha_w)=a0*cos(alpha_t)/a`.

* External: u1+u2=S; intersect both usable roll intervals through this relation.
* Internal: u2=u1+S; intersect the actual pinion and ring intervals.

The intersection length divided by `pb=pi*mt*cos(alpha_t)` gives usable
transverse contact ratio. The continuous axial phase sweep adds
`b_active*abs(sin(beta))/(pi*mn)`; a double helix uses one active half,
`b_active=(width-gap)/2`, including when gap=0. Coverage below one period fails.
These interval relations cover all identical nominal teeth through a full
rotation, rather than testing only selected frames. References: ISO 21771:2007
5.4.1, equations (64)-(70), and 5.4.7, equations (88)-(97).

Coverage alone is insufficient. Even when usable contact ratio exceeds one,
the nominal tip-to-tip path may extend into a non-involute root. The ordinary
engineering report now identifies this separately. It does not declare such
root geometry acceptable merely because enough involute length remains.

Subtract the **actual two tooth arcs at their working radii** from the working
transverse pitch to obtain working backlash:

```
external: a0=rp1+rp2; jw=j*a/a0 + 2*a*(inv(alpha_w)-inv(alpha_t))
internal: a0=rp2-rp1; jw=j*a/a0 - 2*a*(inv(alpha_w)-inv(alpha_t))
inv(alpha)=tan(alpha)-alpha
```

Thus increased centre distance closes the internal pair. Previously its report
omitted this term. Negative internal working backlash is now rejected. Backlash
definitions follow ISO 21771:2007 5.5.1-5.5.2, equations (100)-(103); the formulas
above follow by transporting the existing involute tooth widths. Independent
tests subtract the arcs directly, with either helix hand and centre-distance
changes of both signs. This is circumferential backlash, not normal clearance.

At neutral backlash the phase relation is phi2+(z1/z2)*phi1=pi+pi/z2 for the
external pair, and phi2-(z1/z2)*phi1=pi/z2 for the internal pair, modulo a wheel
tooth period. The allowable half-band is jw/(2*rw2). Helical section phases
must preserve the same signed ratio at every height. The audit checks these
conditions before expensive clearance work and reports the two operating-flank
phase offsets separately from the free-backlash placement.

## Continuous clearance with a profile enclosure

The source boundary is the existing continuous rack/involute recipe or internal
involute/tangent-circle recipe. It is approximated by the already bounded cubic
Hermite curves. Each cubic is flattened only when its four difference controls
against the linear chord give a sufficient **whole-interval** Bernstein hull
bound. Exact circle sagitta bounds cover circular pieces. Fitting, join and
resolution errors are included; the sum of both members' enclosures is subtracted
from every reported separation bound. The nominal profile is not changed.

In the second member's rotating frame a point on member 1 moves no faster than

```
V = a*abs(omega2/omega1) + abs(1-omega2/omega1)*max_radius1
```

For a time/angle interval of half-width h, separation at its midpoint must exceed
V*h plus the two profile enclosures and the numeric guard. Otherwise subdivide.
One full tooth period is covered. This reuses the previous planetary BVH and
motion bound, with signed external/internal kinematics.

The check examines the two full boundaries at the supplied free-backlash phase.
It also closes either operating flank and tests each member's **root circles and
fillets** against the mate's full boundary over the period. It does not mistake
the positive neutral gap for evidence about operating roots. The common helical
phase relation extends these transverse statements to all identical ideal active
sections; CAD/STL loft interpolation and groove shoulders are excluded.

A polygon crossing inside the approximation tube is inconclusive. A source
crossing is reported only if endpoints of the same continuous source trace lie
on opposite sides, each farther from the mate than the combined enclosure and
guard. The report retains these witnesses. Touch, insufficient accuracy and
exhausted budgets stay unresolved. This is binary64 analytic bounding with
explicit guards, **not an outward-rounded interval-arithmetic certificate**.

The manual-pair default enclosure request is 0.0001 mm per member. For actual
fixed internal designs the automatic request is min(0.0001,5e-6*mn) mm, with
16,384 intervals available per check; external designs default to 4,096.
A custom positive finite
request may be coarser or finer. Limits are 120,000 polygon points per member,
the inherited 32,768 fitted-curve-piece limit, and at most 16,384 intervals/depth
20 per continuous check. No result is silently coarsened to meet those limits.
Input phases must be within four revolutions of zero; reduce larger phases by
whole revolutions before requesting the audit, so interval evaluation does not
lose its angular increments to large-number rounding.
The request is an algorithmic enclosure, not a manufacturing tolerance.

## Status and remaining qualification

* `failed`: incompatible phase/helix, insufficient usable coverage or a source
  crossing established outside the enclosure.
* `unresolved`: a covered check cannot be decided within the requested enclosure,
  strict-separation requirement or resource budget. Zero backlash is not a
  strict-separation success.
* `passed_with_limits`: all **covered** checks passed. The `unqualified` list
  remains present and must travel with the result.

Full loaded tip/flank interference, elastic contact, actual cutting-tool
geometry, cutting/trimming/assembly interference, manufacturing tolerances,
strength, durability and lubrication remain outside this check. Internal roots
remain a tangent-circle construction, not a shaping-cutter envelope. ISO 53,
ISO 1328-1 and DIN 3967 do not become a full conformity claim because a numerical
check passed. [KHK's internal-ring design article](https://khkgears.us/media/beqhhrye/gear-solutions_khk_internal-ring-gears-design-and-considerations.pdf)
distinguishes involute, trochoid and trimming interference; its 20-degree
standard-tooth count guidance must not be generalized to all tools and angles.

The initial audit exposed actual limitations of the former unpaired standalone internal profiles.
Independent 100-digit evaluation of the unpaired 30/90, mn=2 mm, 20-degree spur
example finds about 0.00852925714828 mm radial intrusion of a pinion root into
the ring involute at an operating flank; the 24/72 example gives about
0.01932127146936 mm. These are counterexamples, not maximum-interference values.
They use direct rolling-rack and polar-involute equations, with the recorded
binary64 construction parameters, without CAD fitting. The existing planetary
paired tip/root exclusions remove these counterexamples and pass the covered
continuous checks. They reduce contact ratio and alter the ring geometry.
Those conservative candidates were diagnostic comparisons. The subsequent
[fixed internal correction](fixed-internal-root.md) pairs the pinion generating
rack with the active ring involute and preserves full nominal contact in the
audited cases, without the conservative tip shortening. Actual design audits
use the corrected source; manual unpaired calls retain the negative controls.

## Use

```
python3 scripts/validate-cylindrical-mesh.py audit.json --family parallel
python3 scripts/validate-cylindrical-mesh.py audit.json --project saved.config.json
```

Existing report files are never replaced. Exit 0 means the covered checks passed
with the printed limitations; exit 2 means failed/unresolved. Python callers use
`cylindrical_validation.audit_design(design)` for actual component provenance,
or `audit_pair(...)` for an explicitly specified ideal pair. The same
`cylindrical_pair_audit` Rust protocol operation runs in native and Wasm builds.
There is no automatic GUI/export gate or new CAD dependency.
