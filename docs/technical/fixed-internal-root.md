# Fixed-axis internal root correction

Fixed-axis internal spur, helical and double-helical pairs now construct their
pinion root together with the ring's active involute. This corrects the root
interference found by the mechanical audit without applying the planetary
planner's conservative ring-tip shortening to every standalone ring.

The pitch/base/tip/root circles, tooth count, reference tooth thickness,
backlash convention and helix law are retained when the full nominal path is
feasible. The pinion's rounded **normal generating-rack tip radius** is selected
explicitly. This radius is not the local curvature radius of the resulting gear
fillet, and the tool is not a selected commercial hob or shaper.

## Reference and sign conventions

The chosen references remain ISO 21771:2007, ISO 53:1998, ISO 1328-1:1995 and
DIN 3967:1978 within their actual scope. This change uses ISO 21771 5.4.1
(actual active/form diameters), 7.5 equation (125), 7.6 equations (128)-(130)
and 7.7 equation (135). ISO 53 5.9 notes that the actual out-of-contact root
depends on generation, shift and tooth count. A custom generating-tip radius
does not establish conformity to a particular ISO 53 basic-rack root type or
to a complete industrial accuracy/strength class.

Normal module is mn, normal pressure angle alpha_n, helix angle beta,
transverse module mt=mn/cos(beta), and
alpha_t=atan(tan(alpha_n)/cos(beta)). Axes are parallel; pinion O1=(a,0),
ring O2=(0,0), counterclockwise positive, omega2/omega1=+z1/z2. Existing
backlash is the total transverse reference pair allowance, split equally.

Let rp=mt*z1/2 and rb=rp*cos(alpha_t). The generating rack's normal tip
height is hf*mn, with hf=1.25 here. The straight flank remains unchanged.
For its circular normal tip of radius rho_n, the signed transverse roll at
the rack/involute transition follows directly from the normal-rack envelope:

```
vF = -hf*mn + rho_n*(1-sin(alpha_n))
uF = rp*sin(alpha_t) + vF/sin(alpha_t)
rF = hypot(rb,uF)
```

The helical transverse cutter section is elliptical. In particular, do not
substitute a circular transverse cutter of radius rho_n in the spur formula.
These expressions agree with the ISO rack form-diameter construction, using
the actual normal tool geometry. Positive uF is required before squaring;
squaring a negative generating roll would conceal undercut.

For the ring tip ra2, base radius rb2 and S=a*sin(alpha_t), the first nominal
pinion contact roll is `uA=sqrt(ra2^2-rb2^2)-S`. Full involute contact requires
`0 <= uF < uA` and an adequate upper ring involute limit. The feasible normal
tool radius interval is bounded by

```
rho_low  = max(0, (hf*mn-rp*sin(alpha_t)^2)/(1-sin(alpha_n)))
rho_high = (hf*mn-rp*sin(alpha_t)^2+uA*sin(alpha_t))/(1-sin(alpha_n))
```

The tip-land constraint also limits rho_high. Preserve the original tool when
its actual usable root already fits. Otherwise take the interior midpoint of
the feasible interval, leaving margin from undercut and start of active profile.
This is a documented construction choice, not an ISO-prescribed cutter radius
or manufacturing tolerance. It is independent of preview/export quality.

If no positive non-undercut tool can retain the old nominal interval, retain
the original pinion envelope and remove only the ring-tip portion that cannot
work on its usable involute. The line-of-action relation gives
`ra2_new=hypot(rb2,S+uF_actual+delta_u)`, rather than the conservative radial
extremum `a+rF`. The additional roll margin is at most 0.1% of the old usable
transverse path. Report any such relief and reject an exhausted contact domain.
The ring root can be extended toward its existing root circle when needed for
the pinion tip, using the existing tangent-blend construction. It still is not
a shaping-cutter envelope.

The [form-diameter reference](https://www.geartechnology.com/form-diameter-of-gears)
explains why the end of the usable involute matters for interference. The
[shaper-interference paper](https://www.geartechnology.com/avoiding-interference-in-shaper-cut-gears)
also distinguishes correct nominal dimensions from adequate generated root
relief. Those are supporting references; the equations above are implemented
from the actual source rack and the selected ISO edition.

## Results for the audited cases

Spur pairs, mn=2 mm, alpha_n=20 degrees, total reference backlash=0.15 mm:

| Pair | Old nominal epsilon_alpha | Old usable epsilon_alpha | Corrected usable epsilon_alpha | Ring-tip reduction |
| --- | ---: | ---: | ---: | ---: |
| 22/66 | 1.9379959042 | 1.8328541119 | 1.9379959042 | 0 mm |
| 24/72 | 1.9305748106 | 1.8434572665 | 1.9305748106 | 0 mm |
| 30/90 | 1.9209881343 | 1.8692627532 | 1.9209881343 | 0 mm |

The selected normal generating-tip radii are about 0.1386569913,
0.1663157023 and 0.2206259620 mm respectively, versus the previous 0.6 mm
virtual tip. They are recorded at the numerical boundary and in each part's
tool metadata; dimensions and actual rack undercut limits use the same radius.
Explicit decimal tool-radius inputs keep their exact sources in the analytic
cache and twenty-place dimension output. Selection of a derived profile remains
part of the binary64 geometric construction, not twenty-place physical accuracy.

## Material-side sampled profiles

Root chords can add unwanted pinion material; ring-involute chords can shrink
the void. Correct source curves alone therefore do not repair every sampled
model. Fixed internal pairs use circumscribed tangent polylines at the convex
normal-rack corner and positive-roll internal involute, plus a circumscribed
ring-tip circle. These remove material at the pinion root and ring active
flanks rather than adding it. External active-involute chords already remove
pinion material. The ring-root radial exclusion includes the ordinary circular
chord error.

For the rack corner, phi'<=0, v<0 and u'>0 prove positive curve curvature in
the source traversal: the tangent angle rate is theta_tool'-phi'>0 and its
speed never vanishes. Unsupported convexity domains are rejected. For an
internal involute parameterized by roll t, the tangent angle rate is 1.
Each interval also bounds its total tangent rotation, preventing a multiple-turn
alias from endpoint tangent tests.

The whole-interval chord error is bounded with an analytic second-derivative
bound M2; the tangent polygon's maximum deviation from that chord is computed.
Their sum, with a resolution guard, bounds the two-way approximation error.
Subdivision continues until the requested bound is met, or fails explicitly.
The paired canonical profile threshold is at most min(0.015,0.005*mn) mm.
The source curves, nominal contact calculation and existing independent axial
preview/export interpolation requests remain separate.

These bounds describe the unrounded half-profile sampler. The existing full
canonical polygon still uses its compatibility grid of 1e-9 mm and near-duplicate
cleanup at 1e-7 mm. Literal-polygon tests inspect that final geometry with an
explicit 1e-8 mm separation guard; they do not infer its clearance solely from
the ideal material-side construction or claim arbitrary polygon precision.

## Qualification and limits

The [mechanical audit](cylindrical-mesh-validation.md) verifies source curves
over a full tooth period in both operating directions. Additional tests clip
the actual sampled polygons into literal root traces and check those full
periods too; they do not replace the actual contours with another fitted curve.
The previous independent root-intrusion witness is outside the corrected pinion
material. Signed helical section phases retain the same contact law, including
the two active halves of a double helix.

The ordinary internal generator, calculation reports, project regeneration and
opt-in curved ring export use the same Rust plan. `audit_design` recomputes that
plan and rejects altered components rather than trusting stored analysis.
Manual `audit_pair` calls can still reproduce the unpaired negative control.

This is a geometric correction, not a bending/contact stress or life calculation.
Actual tooling, root strength, manufacturing tolerances, lubrication and full
loaded tip/flank interference remain separate qualification. Numerical bounds
use binary64 and explicit guards, not outward-rounded interval arithmetic.
Very small nominal root clearances must not be interpreted as permissible
manufacturing error. An unresolved audit remains unresolved; larger resource
budgets or a different physical design may be needed near limiting cases.
