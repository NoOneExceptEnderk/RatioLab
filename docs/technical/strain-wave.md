# Strain-wave ring generated for a prescribed deformation

RatioLab generates the rigid circular spline from the complete swept outline
of the matching flexible tooth reference. The deformation remains a prescribed
pitch-arc/ellipse map. It is a geometric model, not a prediction of elastic
shape, stresses, fatigue, loaded contact or manufacturing tolerances.

## Reference and coordinate conventions

Yu and Ting, **Application of Finite Element Analysis for the Strain Wave Gear
Tooth Surfaces Design and Modification**, Gear Solutions, 15 September 2019,
**Kinematic Model**, printed p. 37 (unnumbered speed-ratio equation): select tooth motion, transform a complete flexible tooth
profile through that motion, then find the envelope of the trajectories. Their
**Compliant Cup Deformation** and **Loaded Tooth Contact Pattern** sections
separately address elastic deformation and longitudinal modification. RatioLab
uses their envelope construction principle with its own prescribed map and
reference tooth; it does not reproduce their double-circular tooth profile,
finite element results, contact ratio or prototype performance.
[Original article](https://gearsolutions.com/features/application-of-finite-element-analysis-for-the-strain-wave-gear-tooth-surfaces-design-and-modification/).

All rotations are positive about world **+Z**. Internal equations use radians;
lengths and normal offsets use millimetres. With `zf` flex teeth and `zc=zf+2`
ring teeth, the nominal member equation is:

```
2*omega_wave + zf*omega_flex - zc*omega_ring = 0
```

Fixed ring gives `omega_flex=-2/zf*omega_wave`. Fixed flex gives
`omega_ring=2/zc*omega_wave`. Subtracting the ring rotation reduces either
configuration to the same relative tooth motion, so both output choices use
the same generated ring. A negative phase reverses that relative motion.

## Prescribed pitch-arc/normal map

The reference pitch radius is `rp=m*zf/2`. The chosen amplitude sets ellipse
semiaxis `a=rp+amplitude`; `b` is solved so its perimeter is `2*pi*rp`. Uniform
material angle `u` means pitch arc length divided by `rp`, not ellipse polar
angle. Eight Fourier modes integrate the ellipse speed; CPU and GLSL use the
same coefficients and Newton inversion:

```
xi(t) = t + sum(c[k]*sin(2*k*t), k=1..8)
xi = u + flex_angle - wave_angle
E(t,d) = (a*cos(t),b*sin(t)) + d*unit(cos(t)/a,sin(t)/b)
P = rotate_Z(wave_angle)*E(t,d)
```

`d` is the reference radial offset from the undeformed pitch circle. The tooth
band uses full deformation. The cup wall blends continuously from a circular
base to that band using an immutable per-vertex weight; cup, flat cup and hat
retain their continuous body, diaphragm or flange and independent output bore.

## Complete outer swept envelope

Let `g=zc/zf`. In the fixed-ring frame, `xi=u-g*psi`, where `psi` is the wave
angle. Eliminating `psi` gives every trajectory point as:

```
psi = (u-xi(t))/g
ring_angle = u/g + arg(E(t,d)) - xi(t)/g
radius = length(E(t,d))
```

A material tooth shift `u+2*pi/zf` shifts the ring angle by `2*pi/zc`.
Likewise, `t+pi` shifts it by one ring pitch. Thus one complete reference tooth
and a half-turn of ellipse parameter cover all ring teeth and phases.

The solver retains **all** trajectory branches, reference edges and corners.
It samples the two-parameter reference/trajectory grid, including both edge
directions and patch diagonals, and takes the maximum radial intersection at
each fixed ring angle. Keeping only the largest-radius branch for each
reference point is incorrect and is not used. Adaptive doubled-grid comparison
must converge within a measured 0.002 mm radial change, subject to a bounded
grid size; unresolved cases fail explicitly.

The ring has 128 angular cells per tooth, starts at `-pi/zc`, and contains
exactly `128*zc` cyclic hole vertices without a duplicated endpoint. Its outer
wall leaves the chosen rim thickness outside the largest cavity radius.

### Numerical enclosure and physical backlash

The actual flexible reference tooth is thinned by half the specified pair
backlash. The generating reference is instead thickened by that half, using
the same rack-generated tooth form. This is a **reference tooth-thickness
allowance**; the application does not equate it to loaded rotational lost
motion of an elastic reducer.

Numerical enclosure is calculated separately. For a cell with angle step `h`
and endpoint radii `Ra,Rb`, a chord's inverse radial distance at angle `theta`
is:

```
A = sin(theta_b-theta)/sin(h)
B = sin(theta-theta_a)/sin(h)
1/R(theta) = A/Ra + B/Rb
```

Each interior sampled grid vertex `(theta,r)` requires cell scale
`max(1,r*(A/Ra+B/Rb))`. Each endpoint receives the larger adjacent cell scale.
The resulting chord half-plane contains every clipped sampled segment because
its boundary crossings are already bounded and its interior endpoints satisfy
the same half-plane inequality. This preserves branches and corners without
adding an arbitrary clearance or changing the wave amplitude.

The maximum additional radial relief and measured refinement change are
reported separately in `wave_mapping.ring_envelope` and calculation reports.
This encloses the sampled sweep patches; it is not a mathematical global bound
for the continuous nonlinear deformation between all grid points. Independent
off-grid checks retain that distinction. Small sub-threshold penetrations can
remain between the different sampled polygons; they are subject to the
interference check's stated geometric tolerance.

## Moving interference checks and validation

The checker uses each station's immutable material coordinates, validates that
they reconstruct the nominal shared vertices within `1e-7 mm`, and evaluates
the same CPU map afresh at each pose. Triangle connectivity and triangle count
are retained, including cap and bore vertices. Unknown/malformed deformation,
stale references, unsupported warps and invalid posed surfaces remain explicit
failures. Cancellation, timing, phase coverage and triangle limits apply to the
full moving assembly; no expected interface suppresses a collision pair.

Regression tests independently move literal tooth-polygon edges against the
actual ring polygon at unaligned positive and reverse phases, including both
output choices, several feasible tooth counts/amplitudes and all body variants.
Zero-backlash tests require useful flank proximity with a nonzero normal torque
arm; tip or root tangency alone is insufficient. A deliberately wrong ring
phase must create an interior witness. These are sampled geometric checks,
not an elastic solution or a continuous clearance certificate. Real bearings,
supports, fatigue fillets, tooling, lubrication and production acceptance still
need their own engineering checks.
