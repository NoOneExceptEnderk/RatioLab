# Custom generated hypoid pair

RatioLab generates a custom two-blank pair with skew axes. The wheel is the
master spherical-involute logarithmic spiral surface; the pinion is its conjugate
envelope at the specified offset. Translating an existing bevel pinion does not
produce this construction. These surfaces do not reproduce a commercial cutter,
machine setup, Gleason tooth system or standard hypoid normal-module convention.

The envelope method follows the coordinate transformation and meshing condition
in Nie, Chen and Liu (2024), *Research on noise reduction of drive axle hypoid
gear based on tooth surface mismatch modification*, “Pinion conjugated tooth
surface”, Figure 4, equations 7–8,
[DOI 10.1177/16878132241228195](https://journals.sagepub.com/doi/full/10.1177/16878132241228195).
Its manufacturing master surface is different from ours. Only the general
transformation and common-normal velocity condition are reused. The master
spherical-involute/logarithmic trace equations and their primary sources are
documented in [bevel pairs](bevel-pair.md).

## Coordinates and reference dimensions

All lengths are millimetres, internal angles radians, UI angles degrees and
operating speeds RPM. The wheel axis is world +Z through the origin. The pinion
axis is world +X through `Op = (0, E, 0)`. Their directions are 90° apart and their
shortest distance is `abs(E)`. Positive rotations follow the right-hand rule.
With wheel speed as reference, `tau = omega_p / omega_w = -zw/zp`.

Wheel reference module `m`, radius `m*zw/2`, cone angle `atan2(zw,zp)` and distance
`Ro = m*hypot(zp,zw)/2` size the chosen master blank. They are not standardized
hypoid rolling pitch dimensions. The master spiral hand follows the offset sign;
the pinion hand is derived. Flipping E mirrors the construction. At E=0 the
positive master hand is selected: this is a generated bevel limit. Approaching
zero from negative and positive offsets gives opposite-handed limits.

The master addendum coefficient is 0.7. Its root is deepened below the generating
angle of the pinion crest by `0.25*m/Ro`. The pinion crest is derived from the
mean generated reference section plus one reference module. Nonworking root
relief and crest bridges are custom. Backlash `j` thins the actual master wheel;
the virtual generating wheel uses `-j`, also thinning the generated pinion. The
nominal reference lost motion at the wheel is `j/(m*zw/2)`. This does not model
load-dependent backlash or contact deformation.

## Envelope equation

For master polar angle theta, spherical radius R and flank sign sigma, let
`phi0 = k*ln(R/Ro) + sigma*H(theta)`, where H is the master tooth half-angle.
For wheel roll phi, `P = Rz(phi)*q(theta,R,sigma)` and the pinion body point is
`FrameA^-1 * Rx(-tau*phi) * (P-Op)`. FrameA maps pinion local `(x,y,z)` to
world `(z,x,y)`. In particular the axis offset is applied before inverse rotation.

The meshing equation is `n dot (ez cross P - tau*ex cross (P-Op)) = 0`.
The term containing Op cannot be dropped. With `s=sin(theta)`, `c=cos(theta)`,

```
H' = -sqrt(cos(base)^2-c^2)/(sin(base)*s)
Nz = sigma*H'*s^2 - k*s*c
A = c + E*Nz*s/X
B = -sigma*H'*s
C = s/tau
psi = atan2(B,A) - sigma*acos(-C/hypot(A,B))
R = X/(s*cos(psi))
Y = X*tan(psi)
Z = R*c
phi = psi - phi0
pinion radius = hypot(Y-E,Z)
pinion azimuth = atan2(Z,Y-E) - tau*phi
```

X is the fixed pinion axial section. A separated real branch, positive forward
cosine and regular working flanks are required. One opposite flank belongs to
the adjacent pinion tooth; assembly subtracts its tooth period. At fixed master
radius instead, use `A=c` and `C=s/tau + E*Nz/R`. Both forms must reconstruct
the same point and branch.

## Supported domain and checks

The initial offset domain is `abs(E) <= 0.06*Ro`, pressure 17.5–25°, master spiral
25–45°, and reference width at most `Ro/3`. These limits alone do not guarantee
acceptance. Unsupported branches, pointed teeth, insufficient bore walls,
unresolved regularity/engagement and sampling budgets produce explicit errors.
The generator exports only two bored blanks. Shaft, bearing, support, retention
and lubrication design remain the user's CAD work.

First derivatives of the analytic generated radius are enclosed over both full
working rectangles `(theta,X)` with adaptive floating-point intervals. Strictly
negative radial derivative checks regularity and radial ordering of the selected
flank. Intervals expand arithmetic results with `nextafter`; transcendental
functions use the host libm. This is a numerical enclosure method, not an
exact-arithmetic or formally verified transcendental proof.

A connected track at fixed mean master radius is enclosed inside both actual
axial cap intervals and the regular generating domain. Any two attained,
unwrapped phases on that continuous track provide a conservative lower bound on
its phase span. Both flank bounds must exceed one wheel tooth pitch. This is
sufficient ideal engagement, not a loaded contact pattern, durability prediction
or continuous whole-mesh collision certificate.

Working surfaces share theta/axial grids refined using quarter/midpoint probes
at 0.003 mm. This finite refinement criterion is not a proven global surface
error, STL tolerance or manufacturing accuracy. Crest/root curves, caps and
cylindrical bores use the shared solid/export pipeline. Actual sampled pinion sections are checked for self-intersections. This finite
section check does not certify all intermediate sections. Resource budgets are
10,000 section vertices and 250,000 faces per blank. Interference inspection uses
the actual sampled solids; mating labels do not suppress detected collisions.

## Reproducible benchmark

For zp=20, zw=40, m=2, width=8, E=+2, master spiral=35°, pressure=20°, backlash=0,
at theta=1.096180105067607 and X=36.42229123600033 on flank +1:

| Quantity | Value |
| --- | ---: |
| Master radius R [mm] | 41.00992390887163 |
| Wheel phase [rad] | 0.07897272747143103 |
| Pinion radius [mm] | 18.741417383703183 |
| Pinion azimuth [rad] | 1.728877382724876 |
| Pinion phase [rad] | -0.15794545494286205 |

`tests/test_hypoid_geometry.py` independently solves the literal world-frame
common-normal velocity equation using finite-difference master normals and
bisection, then compares the transformed positions. Other checks compare
generated-surface normals, mirrored offsets, interval derivatives, several
actual moving-mesh poses, wrong-phase/omitted-offset negative controls, signed
RPM updates, project/worker parity and canonical standalone exports. Finite
examples cannot establish clearance for every supported parameter/phase.
