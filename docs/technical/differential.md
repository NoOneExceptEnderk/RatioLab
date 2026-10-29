# Bevel differential

RatioLab constructs straight and logarithmic spiral bevels from exact spherical
involute working flanks. The analytic flanks satisfy the common-normal meshing
condition; preview and exports sample those surfaces into facets. Nonworking
root relief is a separate construction. Loaded contact, strength,
backdrivability, bearing capacity and continuous collision clearance require
additional engineering validation.

## Wrist coordinates and speed equations

Lengths are millimetres and rates are rpm. A and B are the two independent
input speeds about the same **world +X** direction, even though the shaft ends
face opposite sides. Their side gears have equal tooth counts Zs. The output
gear has Zo teeth and points along the carrier's +Z axis at the nominal pose.
C is carrier rotation about world +X; S is output spin relative to its moving
carrier. Rigid gears and ideal rolling without slip are assumed.

The two carrier-relative rolling constraints and their solution are:

```
Zs (A - C) + Zo S = 0
Zs (B - C) - Zo S = 0
C = (A + B) / 2
S = (Zs / Zo) (B - A) / 2
A = C - (Zo / Zs) S
B = C + (Zo / Zs) S
```

All tooth ratios are dimensionless. Equal inputs produce carrier rotation;
opposite inputs produce relative output spin. For A=12, B=-12, Zs=24 and
Zo=48, C=0 and S=-6 rpm; the inverse reconstructs both inputs. With A=0 and
B=12, the same gearing gives C=6 and S=3 rpm. The original PR2 hardware manual,
[Wrist Drivetrains and PR2 Coordinate System](https://github.com/PR2/pr2_docs/blob/master/pr2_manual/3_pr2_hardware.tex),
describes differential flex/roll actuation; its motor-facing sign conventions
must be transformed before comparing with these world-axis definitions.

The output pose is `Rx(carrier angle) Rz(relative spin angle)`, so the output
spin axis follows the carrier. Speed changes preserve the four physical angles
of A, B, C and S in the preview. Inspection and exports use the nominal model.
No single reduction ratio, combined power balance or output torque is inferred
from two prescribed input speeds.

## Classic configuration: direct carrier input and two side outputs

The **Classic** configuration uses the same cone axes and equal side tooth
counts, but the carrier is the physical input and A/B are the two side output
speeds. The perpendicular bevel is an internal spider, freely turning on a
carrier-fixed pin. There is no external perpendicular output shaft or flange.

The primary reference is MathWorks Simscape Driveline,
[Differential, Equations / Ideal Fundamental Constraints](https://www.mathworks.com/help/sdl/ref/differential.html).
Its first fundamental constraint couples both side gears to the carrier. With
equal side/spider ratios, its non-divided form is `A+B=2C`; this form also covers
equal speeds and stationary members. RatioLab drives C directly and does not
include the reference block's additional longitudinal crown/pinion drive.

Carrier speed alone does not determine both output speeds. For visualization,
the user prescribes **Delta=B-A** as a separate speed boundary condition:

```
A = C - Delta/2
B = C + Delta/2
S = (Zs / Zo) Delta/2
C = (A+B)/2
Delta = B-A
```

C, A, B and Delta use rpm about world +X. S is the internal spider's spin
relative to its carrier's moving +Z axis; Zo is now the spider tooth count.
All tooth ratios remain dimensionless. C=12/Delta=0 produces A=B=12 and S=0.
C=12/Delta=24 with equal tooth counts produces A=0, B=24 and S=12. C=0/Delta=24
produces A=-12, B=12 and S=12. C=-5/Delta=-6 gives A=-2, B=-8 and S=-3.
Both rolling constraints from the wrist equations remain satisfied.

Delta is not a second physical motor input or a load-dependent speed split.
A prescribed stationary side is not a differential lock. No traction, friction,
limited-slip behavior, output torque or power balance is inferred. Changing
Zo changes internal spider spin, while the equal-side output constraint remains
the same. Preview time follows the fastest derived member so zero carrier
speed with a nonzero prescribed difference still animates.

Both side outputs can have solid shafts, hollow shafts or drilled flanges. A
direct coaxial annular carrier mount clears output A. The side extension is
measured beyond its outer carrier interface, including the full input-mount
thickness on A. The internal spider bore equals the pin diameter plus twice
the selected positive radial running clearance. Nominal axial retainers remain
separated from the spider by the assembly clearance. These are geometric
interfaces; complete pin retention, bearing/journal design, fits and lubrication
in CAD. Hollow side passages do not establish an unobstructed through-route
across the spider and its carrier-fixed pin.

## Pitch cones and interfaces

With outer module m, the reference radii are `rs = m Zs / 2` and
`ro = m Zo / 2`. The common cone distance is `R_outer = hypot(rs, ro)`; the
perpendicular shaft cone angles are `delta_s = atan(Zs/Zo)` and
`delta_o = atan(Zo/Zs)`, summing to 90 degrees. These are the pitch-cone
relations in [KHK's dimension reference, section 4.4](https://khkgears.net/new/gear_knowledge/gear_technical_reference/calculation_gear_dimensions.html).
Face width b is measured along the cone generator and limited to
`b <= R_outer/3`; `R_inner = R_outer - b` must remain positive. Shaft radii
are checked against the small-end tooth roots.

The end faces are planes at local `Z = R_outer cos(delta)` and
`Z = (R_outer-b) cos(delta)`. Module and face width refer to the **pitch cone**.
At another polar angle theta, a vertex's actual apex distance is
`R = Z/cos(theta)`, which can extend beyond the pitch-cone reference interval.
The mating surfaces engage only where their two axial face intervals overlap;
there is no fictitious clamping of every vertex to `R_outer`. Cylindrical bores
remain circular with the same radius at every axial section.

The 1:1 preset derives Zo=Zs. Spin reduction 2:1 derives Zo=2Zs;
it changes the relative output/spider S while retaining the carrier mean equation. Custom mode preserves
both supplied counts. Output connection, carrier construction and tooth variant
are independent saved choices.

The hollow shaft has a real coaxial passage from the output gear toe to the
shaft end, with at least 1 mm radial shaft wall. This does not establish a full
cable route through the mechanism or its tilt range. Split carrier members
have open bearing-seat halves and overlapping bridge tabs in separate axial
layers, with matching joining holes. Nominal layer/ligament and clearance
checks do not establish clamping strength. Bearings are envelopes; fits,
retention, fasteners and mounting require completion in CAD.

## Spherical involute flanks and nonworking roots

The primary surface reference is Dong et al., *Spatial analysis of contact
deformation, stiffness, and flash temperature in involute gear pairs*,
[DOI 10.3389/fmech.2025.1643228](https://www.frontiersin.org/journals/mechanical-engineering/articles/10.3389/fmech.2025.1643228/full),
section 2, equation (1). Its Cartesian spherical involute can be expressed
in polar form about each gear's own shaft as follows:

```
sin(delta_b) = sin(delta) cos(alpha_t)
t = acos(cos(theta)/cos(delta_b))
inv_s(theta) = t/sin(delta_b) - atan2(sin(t), sin(delta_b) cos(t))
half(theta) = pi/(2 Z_teeth) - j/(4 r_pitch)
              + inv_s(delta) - inv_s(theta)
phi = tooth_phase + trace(R) ± half(theta)
P = R (sin(theta) cos(phi), sin(theta) sin(phi), cos(theta))
```

Angles inside these formulas are radians; UI pressure and spiral angles are
degrees. Here theta is polar angle from the gear axis, delta is pitch-cone
half-angle, delta_b is base-cone half-angle, t is the generating involute
parameter, j is the outer transverse backlash field in mm, and
`r_pitch = m Z_teeth/2`. Each member receives half the requested tangential
tooth-thickness reduction, so a mating pair has the requested nominal backlash
at the outer pitch radius. The pressure field is **transverse/spherical
alpha_t**, preserving the existing stored parameter convention. For the
logarithmic spiral's pitch angle beta, normal pressure satisfies
`tan(alpha_n) = tan(alpha_t) cos(beta)`; the same numerical value in the
transverse and normal fields would describe different spiral gears.

The meshing reference is Wang et al., *The Equation of Meshing of Spiral Bevel
Gears Manufactured by Generating-Line Method*,
[DOI 10.2174/1874155X01105010051](https://www.benthamopenarchives.com/contents/pdf/TOMEJ/TOMEJ-5-51.pdf),
section 4, equation (22): `n dot ((omega_1-omega_2) cross P) = 0`.
Both shaft axes intersect at the common apex, so no translational term occurs.
Tests solve this equation using independently finite-differenced runtime
surfaces and verify mate positions, parallel normals, and zero relative normal
velocity on both flanks, both hands, equal/unequal and odd tooth counts.
They also compare the angular involute against Dong's Cartesian equation (1).
Zero backlash is used for the nominal coincident-flank calculation; prescribed
positive backlash separates the two tooth surfaces until a flank takes up play.

The historical heel tip radius `r_pitch+m` is retained. Its polar angle is
`theta_tip = atan((Z_teeth+2)/Z_mate)`. The initial root angle is
`atan((Z_teeth-2.5)/Z_mate)`. Where necessary it is deepened to
`pi/2-theta_tip_mate-0.25 m/R_outer`, ensuring a positive angular clearance
between the root blank and the mate tip cone. Shaft-wall checks use this actual
root rather than the old nominal root radius. Below the base cone, constant
half-angle continuation joins the root; it is a nonworking sharp construction,
not a spherical involute or a generated manufacturing fillet. No reversed
involute branch is used. A mate addendum requiring below-base contact is refused
using the base-cusp limit
`theta_tip_mate < acos(sin(delta_b)^2/(cos(delta_b) tan(delta)))`.
Pointed/overlapping teeth and exhausted sampling budgets are also refused.

This is an explicit **custom planar blank**, with m defining the outer pitch
module. Its heel addendum measured normal to the pitch cone is `m cos(delta)`.
It is not the full-depth standard blank in KHK table 4.17, whose linked
dimensions include addendum `h_a=m`, tip radius `r_pitch+h_a cos(delta)` and
crown plane `Z=R_outer cos(delta)-h_a sin(delta)`. Replacing just the cone angle
while retaining the current pitch-height plane would not implement those
dimensions. RatioLab retains its existing mounting/end planes and checks the
resulting actual contact domain; some ordinary-looking high-pressure or narrow
parameter sets therefore require different dimensions, as detailed below.

### Tooth engagement and the shared face interval

Collision-free geometry alone does not ensure a tooth is available throughout
the mesh cycle. The implementation also checks complete ideal engagement on
both flanks, including both planar end caps. Parameterize the unit-sphere action
great circle by s, measured from the pitch point:

```
X = cos(delta) cos(s) - sin(alpha_t) sin(delta) sin(s)
Y = -cos(alpha_t) sin(s)
Z = sin(delta) cos(s) + sin(alpha_t) cos(delta) sin(s)
R_low  = max(R_inner cos(delta_A)/X, R_inner cos(delta_B)/Z)
R_high = min(R_outer cos(delta_A)/X, R_outer cos(delta_B)/Z)
gear_phase = s/sin(delta_b_A) - k_A ln(R/R_outer) + constant
```

Addendum-cone limits and `R_low <= R_high` bound a connected contact domain.
Each flank's unwrapped gear-phase interval must span more than one tooth pitch
`2 pi/Z_A`; reflecting the flank reverses the sign of k in this check. Its
boundary consists of `R = constant/X` or `constant/Z`, switching at s=0.
On each smooth branch, phase extrema occur at interval ends or
`tan(s+offset) = 1/(k sin(delta_b_A))`. Evaluating these analytic stationary
points and the branch junction gives the complete ideal phase span, rather
than inferring engagement from a finite number of collision-free poses.
The reported `contact_phase_span_teeth` is the smaller of the two flank spans.

For m=2 mm, 20-degree transverse pressure and zero spiral, the 24/24 pair
with 8 mm face width has span 1.19202469688 tooth pitches. A 24/48 pair
with 4 mm width gives 1.14572350061. A formerly accepted 16/60 pair with
4 mm width has only 0.76980163019 in the straight construction and 0.59766453066
on its limiting 35-degree spiral flank: these narrow cases are now rejected
because the planar caps remove part of the required contact interval. With
8 mm width, that spiral pair gives 1.14273421889. Increasing width, reducing
module or changing tooth counts can restore complete engagement when cap
trimming is the limiting factor. High transverse pressure can instead make
the addenda themselves too short: 24/24 at 30 degrees has a straight-flank
span of only 0.94630958702 even when the caps do not trim contact. Reducing
pressure, changing tooth counts or a supported spiral overlap can restore
engagement; the generator does not silently extend teeth. The outer face-width
limit `b <= R_outer/3` still applies. These are unloaded geometric engagement
spans, not load distribution or strength calculations.

The `conjugacy_verified` metadata flag is explicitly scoped to these analytic
working flanks. It does not certify the sampled mesh, nonworking root, bearings,
manufacturing process or an entire continuous motion cycle.

## Spiral trace and local handedness

The spiral variant retains the same ideal speed equations. Its pitch-cone trace
uses Cumbicus et al., *Obtaining the geometry and 5-axis machining paths for the
manufacture of spiral bevel gear*, [DOI 10.1007/s00170-025-16738-7](https://doi.org/10.1007/s00170-025-16738-7),
section 3.2, equations (8)-(9), also available in the
[author preprint](https://assets-eu.researchsquare.com/files/rs-7160715/v1_covered_95048085-0608-4839-8a8b-f1397df8ff0b.pdf).

```
theta(R) = h tan(beta) / sin(delta) * ln(R / R_outer)
R sin(delta) dtheta/dR = h tan(beta)
```

R is distance along the cone generator from the common apex, delta is the
pitch-cone half-angle, beta is an unsigned spiral angle, and h is local hand
(-1 or +1). The UI stores beta in degrees; internal trigonometry and theta
use radians. Beta here corresponds to the paper's spiral angle lambda, not
its involute parameter beta. The logarithm argument is dimensionless and
positive. The heel phase is zero; zero beta uses exactly the straight geometry.

The side gear frames are right handed, with local +Z along world +X for A and
world -X for B. Both side traces use the **same local hand h**; the output
or internal spider trace uses **-h**. Because `Zs/sin(delta_s) = Zo/sin(delta_o)`, both contact
lines satisfy `Zs theta_s(R) + Zo theta_o(R) = 0` at a shared cone distance.
Together with the spherical involutes, this preserves conjugate indexing along
the face. Assigning the same local hand to all three gears or using a twist
linear in axial Z would not implement this construction. The heel **pitch
point** has zero trace; other heel-plane vertices have the nonzero correction
`trace(R_outer cos(delta)/cos(theta))`. Omitting this angle-dependent correction
would produce incorrect spiral flanks despite correct-looking tooth traces.

All gears use matching cone-distance stations. A conservative second-derivative
bound controls the chord deviation of each sampled outer-vertex trace to
0.003 mm. For `f(R)=a R exp(i k ln(R/R_outer))`,
`|f''| = a |k| sqrt(1+k²)/R`; the maximum is bounded at R_inner and the largest
profile radius. Uniform cone-distance intervals satisfy
`max|f''| deltaR²/8 <= 0.003 mm`. Bores remain fixed circular sections.
This bound applies to corresponding sampled vertices along the axial loft;
it is separate from the section profile's quarter/midpoint refinement threshold
of 0.003 mm. Refinement compares analytic points with their chord and refuses
budget exhaustion. The profile threshold is a numerical refinement criterion,
not a proved global bound on the entire surface or an industrial flank tolerance.
Triangles between stations additionally approximate a curved two-parameter
surface. At zero or very small backlash, discretization can affect apparent
contact, so mesh intersection results must be interpreted at their stated
sampling precision rather than substituted for an analytic contact calculation.

Preview, STEP and STL consume the same section surfaces in the nominal pose.
SVG/DXF retain individual sections and placement metadata; they are not cutting
templates. Axial caps are planar, avoiding nonplanar polygon caps in faceted
STEP. Regression tests exercise actual shared meshes at independent tooth-cycle
poses for wrist/classic arrangements and both mesh sides, and include an
intentional tooth-on-tooth phase error as a collision negative control. These
finite tests establish those sampled cases; they are not complete continuous
clearance or load-capacity certification.
