# Bevel gear pair

The **Bevel gear pair** family creates two bored gear blanks on intersecting
shafts at **90°**, with straight, logarithmic spiral or circular Zerol-style tooth
traces. Tooth counts, outer module, pitch-cone face width,
transverse pressure angle, outer tangential backlash and both bores are editable.
Input and output can be swapped. Shafts, supports, bearing seats, fasteners and
axial retention are completed in CAD. No automatic stock hardware is inferred.

## Frames, pitch cones and rolling

The common cone apex is the world origin. The pinion's positive local Z axis is
world **+X**, with local X/Y along world +Y/+Z. The wheel frame is world XYZ,
with its positive shaft along **+Z**. Positive speeds are right-hand rotations
about those two axes. Lengths use mm, UI angles degrees, internal angles radians,
and speeds rpm. Rigid bodies and ideal rolling without slip are assumed.

For tooth counts `zp, zw`, outer module `m`, shaft angle `Sigma=90°` and face
width `b`, the pitch-cone equations are:

```
rp = m zp / 2                  rw = m zw / 2
delta_p = atan2(zp, zw)         delta_w = pi/2 - delta_p
R = hypot(rp, rw)              R_inner = R - b
zp omega_p + zw omega_w = 0
i_forward = omega_p / omega_w = -zw/zp
i_reverse = omega_w / omega_p = -zp/zw
```

These pitch dimensions follow [KHK Gear Technical Reference section 4.4,
standard straight bevel table 4.17, items 5–8](https://www.khkgears.co.jp/gear_technology/basic_guide/khk372/).
The general cone-angle equation there reduces to the expression above at 90°.
Face width is conservatively limited to both `R/3` and `10m`.
For KHK's `zp=20, zw=40, m=3`, `R=67.08203932499 mm` and the cone angles
are `26.56505117708° / 63.43494882292°`. Forward input 1500 rpm gives wheel
−750 rpm; reverse wheel input 1500 rpm gives pinion −3000 rpm. Equal counts
give 45°/45° and ratio −1. Zero input stops both members; a negative input
reverses both. These signed ratios use separate shaft directions, not a shared
observation direction. Efficiency is an operating assumption for the nominal
torque/power estimate; no allowable torque is calculated.

## Working flanks, indexing and blank limits

The pair reuses the spherical involute working flanks described in the
[bevel differential reference](differential.md#spherical-involute-flanks-and-nonworking-roots).
The primary surface reference is [Dong et al., section 2 equation (1)](https://www.frontiersin.org/journals/mechanical-engineering/articles/10.3389/fmech.2025.1643228/full).
With pitch angle `delta` and transverse pressure `alpha`, the base cone satisfies
`sin(delta_b)=sin(delta) cos(alpha)`. The straight variant uses zero spiral trace.
At the nominal pose, wheel tooth phase is zero and pinion tooth phase is
`pi/2-pi/zp`, putting its space on the shared pitch generator. The rolling
constraint maintains the indexing for even and odd tooth counts.

Both working flanks satisfy the analytic meshing condition
`n dot ((omega_p - omega_w) cross P)=0`, with angular velocities expressed as
world vectors. This is [Wang et al., section 4 equation (22)](https://www.benthamopenarchives.com/contents/pdf/TOMEJ/TOMEJ-5-51.pdf),
without translation because the axes intersect. Independent finite-difference
surface-normal tests exercise this condition and mating positions on both flanks.

**The blanks are custom planar constructions, not KHK standard full-depth
blanks or generated Gleason/Klingelnberg cutter geometry.** The retained outer
tip radius is `rp+m`, with planar ends at local axial positions
`R cos(delta)` and `(R-b) cos(delta)`. The spherical distance of another vertex
on those planes is `axial_z/cos(theta)`, not necessarily `R`. Below the base
cone, root relief is a nonworking constant-half-angle continuation; it can be
deepened to clear the mate tip. No cutter fillet or root-strength claim is made.

Each gear receives half the outer tangential tooth-thickness allowance. Inner
sections shrink in proportion to cone distance, while cylindrical bores keep
their diameter. Bores must leave at least 0.8 mm nominal radial material to
the actual small-end root. Zero bore creates a solid blank. The generator
rejects below-base working contact, pointed/overlapping tooth profiles and
cap-trimmed ideal contact phase spans of one tooth pitch or less. The reported
phase span includes both planar end caps; it is not a loaded contact ratio.

Preview, STEP and STL use the same sampled surfaces. The 0.003 mm adaptive
profile-refinement threshold is a numerical criterion, not a global surface
accuracy bound or manufacturing tolerance. SVG/DXF export planar sections and
placement information, not cutting developments. Regression checks sample
multiple independent cycle poses and include a deliberate half-tooth indexing
error as a collision negative control. These checks do not certify continuous
clearance, loaded contact, root strength, wear or service life.

## Spiral trace

Select **Spiral teeth** to expose unsigned `spiral_angle` (0–45°) and pinion
`spiral_hand` (−1 or +1). The mate uses the opposite local hand. At actual
distance `r` from the apex, each member's local shaft azimuth follows

```
theta(r) = h tan(beta) / sin(delta) * ln(r/R)
```

This follows [Cumbicus et al., section 3.2, equations (8)–(9)](https://assets-eu.researchsquare.com/files/rs-7160715/v1_covered_95048085-0608-4839-8a8b-f1397df8ff0b.pdf).
Here beta is the pitch-cone spiral angle, not pressure angle; h is local hand.
Because `zp/sin(delta_p)=zw/sin(delta_w)`, the weighted traces and their radial
derivatives cancel between the members. Together with the spherical involutes,
this preserves the common-normal rolling condition. Zero angle produces exactly
the original straight surfaces. Changing hand mirrors tooth geometry; changing
RPM sign or input/output roles independently changes the motion.

The analytic cap-aware contact-phase extrema calculation from the differential
reference remains in use for this logarithmic construction. It tests both flanks.

## Circular Zerol-style trace

Select **Zerol-style · circular trace** to expose `trace_radius` in mm and the
pinion local trace hand. The mean spiral angle is fixed at zero while the lead
remains curved. [Gleason, section 11.1](https://www.gleason.com/gear-technology-solutions/files/basic-html/page156.html)
describes a circular lead on the developed cone, tangent to a generator at the
mean position, with an industrial octoidal tooth profile. RatioLab implements
that circular lead constraint with its **custom spherical involute flanks**;
it does not reproduce Gleason octoids, cutter settings, crowning or manufacturing
interchangeability. The UI deliberately labels the construction **Zerol-style**.

For mean pitch distance `Rm=R-b/2` and developed circle radius `rho`, choose a
circle `(x-Rm)^2+(y-h rho)^2=rho^2` in the developed cone plane. With polar
radius r and developed angle u, solving the circle and anchoring at the heel gives

```
D(r) = (r²+Rm²)/(2r)            A = hypot(Rm,rho)
u(r) = atan2(rho,Rm) - acos(D(r)/A)
theta(r) = h [u(r)-u(R)] / sin(delta)
```

The slope vanishes at `r=Rm`, so the local pitch spiral angle
`atan(r sin(delta) dtheta/dr)` is zero there. The curve has nonzero curvature.
The mate shares Rm and rho with opposite hand, preserving weighted trace and
slope cancellation. All actual flank-vertex distances must satisfy `D<A` with
a numerical margin; invalid or unresolved arcs are refused. Larger radii flatten
the curve, approaching the straight limit. This radius is a geometric parameter,
not an inferred manufacturing cutter selection.

For this variable-inclination trace, engagement is reported as a **conservative
lower bound**, not exact phase extrema. The shared planar caps and addenda define
a connected domain in action angle and radius. The unwrapped phase on either
flank is continuous on that domain. Therefore every phase between any two valid
sample values is attained; a sampled span greater than one tooth pitch is a
sufficient ideal engagement test. Missing an extremum can cause a conservative
rejection, not enlarge the accepted lower bound. Both flanks must pass, with a
numerical guard. This is independent of loaded tooth contact or strength.

## Curved surface sampling

At pitch distance S, each corresponding heel-profile vertex is scaled by S/R
and rotated by `theta(C S)-theta(C R)`, where
`C=cos(delta)/cos(vertex_polar_angle)`. Circular traces require this
**vertex-specific** rotation: a uniform twist of an entire section would describe
the wrong surface. Bores remain fixed circular cylinders through all sections.

Common axial stations satisfy the interpolation bound
`max|f''| (delta S)^2/8 <= 0.003 mm` for the corresponding vertex traces
`f(S)=a S exp(i theta(C S))`. For the logarithmic trace,
`|f''|=a |k| sqrt(1+k²)/S`. For circular traces the implementation bounds
`a [2C |theta'| + S C² (|theta''|+theta'²)]` over the complete actual-radius
interval, including vertices beyond the pitch-cone heel radius. It refuses more
than 128 intervals or 250,000 side faces per part. The bound applies to the
sampled vertex traces; the full two-parameter tooth surface, normals and physical
manufacturing accuracy are not certified by it.

Saved projects contain only the fields active for their tooth type. Straight
projects remain compatible and retain their original geometry. No variant adds
shaft offset: hypoid pairs are outside this implementation.
