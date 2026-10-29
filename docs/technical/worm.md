# Cylindrical ZA/ZI worm and generated wheel

The screw and wheel use one shared sampled surface for preview, STL, STEP and
interference checks. The wheel flanks are generated from the matching screw
helicoid, including backlash and the swept hob-tip transition at the tooth root.
They replace the previous helical-gear surrogate. This is an ideal rigid-body
geometric construction; it does not certify manufacturing tolerances or loads.

## Dimensions and screw profiles

Lengths are millimetres; equations below use radians. The inputs are axial
module `mx`, axial pressure angle `alpha_x`, starts `s`, wheel teeth `z`, worm
pitch radius `rp = diameter/2`, total axial pair backlash `j`, and hand `h = ±1`.

```
k = mx*s/2                 screw parameter, mm/radian
L = 2*pi*k                 lead, mm/revolution
R = mx*z/2                 wheel pitch radius
a = rp + R                 nominal centre distance
gamma = atan(k/rp)        reference-cylinder lead angle
mn = mx*cos(gamma)
alpha_n = atan(tan(alpha_x)*cos(gamma))
alpha_t = atan(tan(alpha_n)/sin(gamma))
```

These conversions follow KHK, **Calculation of Gear Dimensions**, §4.6,
Tables 4.22–4.23. Its axial-module example `mx=3`, `s=2`, `z=30`, `d1=44`,
`alpha_n=20°` gives `a=67 mm` and `gamma=7.76517°`. RatioLab takes the axial
pressure angle as input, so that example requires converting the given normal
angle first. [KHK technical reference](https://khkgears.net/new/gear_knowledge/gear_technical_reference/calculation_gear_dimensions.html).

At radius `r`, the transverse half-thickness of the screw is:

```
ZA: f(r) = pi/(2*s) - j/(4*k) - (r-rp)*tan(alpha_x)/k
ZI: f(r) = pi/(2*s) - j/(4*k) + inv(rp) - inv(r)
    rb = rp*cos(alpha_t)
    inv(r) = sqrt((r/rb)^2-1) - atan(sqrt((r/rb)^2-1))
```

ZA is straight in axial section. ZI is an involute in transverse section; below
its base cylinder, the screw retains its explicit sharp radial root transition.
The axial pitch thickness is `pi*mx/2 - j/2`. Both hands, independent bores and
optional cylindrical end journals remain available. Journals must fit inside
the worm root without entering its bore.

## Wheel envelope in the application's axes

The worm rotates positively about world **+X**, the wheel about **+Z**, and the
wheel centre is `(0,-a,0)`. The signed ratio is `h*z/s`; therefore
`omega_wheel = h*s/z * omega_worm`. Reversing the input reverses both speeds;
changing hand reverses the wheel speed. No backdrivability or self-locking
conclusion follows from this relation.

Houser and Su, **Definition and Inspection of Profile and Lead of a Worm Wheel**,
Gear Technology, Nov/Dec 1999, pp. 18–19, Eq. (4), replace screw rotation by axial
translation; Eq. (5) is the common-normal condition, and Eqs. (11)–(13) map the
result into the wheel frame. RatioLab applies that construction to the ZA/ZI
surfaces above, with the following explicit coordinate conversion.
[Original article](https://www.geartechnology.com/definition-and-inspection-of-profile-and-lead-of-a-worm-wheel),
[original equations, pp. 18–19](https://ik.imagekit.io/agmamedia/gt/issues/1199x/houser.pdf).

For wheel face height `q`, take the negative-Y half of the worm cylinder:

```
y = -sqrt(r*r-q*q)
psi = -pi-asin(q/r)
u = k*(h*(psi+pi/2)-side*f_hob(r)) - thread_length/2
```

`side = ±1` selects the two flanks. The generating hob has the same lead,
pressure and flank form as the screw, but uses `+j/(4*k)` instead of
`-j/(4*k)`. This makes the wheel gap wider by the other half of the specified
pair backlash without moving the axes. Its tip extends to `rp+1.25*mx`, giving
`0.25*mx` bottom clearance beneath the actual worm tip at `rp+mx`.

With the unnormalised generator normal `(1,ny,nz)`:

```
ny = k*side*f'(r)*y/r + h*k*q/r^2
nz = k*side*f'(r)*q/r - h*k*y/r^2
X = (y+rp)/ny
phi = (u-X)/(h*k)
chi = (u-X)/R
Q = rotate_Z(-chi) * (X,y+a)
```

`Q` is a wheel-section point, `phi` the associated worm rotation and `chi` the
wheel rotation. The normal annihilates the actual relative rotational velocity:

```
(1,ny,nz) dot (mu*(y+a), -q-mu*X, y) = 0
mu = h*s/z
```

This checks the physical rotations independently of their equivalent
translation. At zero backlash the inverse physical rotation lands on the
original screw flank. With positive backlash the nominal pose centres the
clearance; either loaded flank reaches contact after taking up its allowance.
In the central ZA section, the normal is tangent to the independently known
involute base circle `R*cos(alpha_x)`.

The sharp generating-tip edge is swept from its flank characteristic to its
cylinder characteristic. Where that sweep recuts a flank, their equal-radius
intersection trims the nonphysical loop; an undercut root may overhang in polar
coordinates and is not rejected merely for that reason. The tooth blank tip is
a torus defined by the worm root-clearance cylinder `rp-mx`. This blank shape
is separate from the generated flank solution.

## Discretisation and supported domain

Corresponding sections use deterministic, bounded curve and face refinement
with a **0.005 mm sampled midpoint chord threshold**. This is a numerical
refinement criterion, not a proof of a global error bound or a machining
accuracy. The screw retains its 0.02 mm nominal angular sagitta criterion.
The same triangle diagonals, root transitions and bore loops reach every
surface consumer.

Half the wheel face width must be below `0.95*(rp-mx)`. Pointed generating-hob
tips, singular contact normals, overlapping neighbouring gaps, self-crossing
profiles, unresolved refinement or excessive bore size are rejected explicitly.
Each solid is bounded to 250,000 faces including bore walls. Finite screw
length can shorten the available contact region; no contact-ratio guarantee is
inferred from the generated infinite-helicoid envelope.

Regression checks cover ZA/ZI, both hands, starts, altered module/diameter/tooth
count, and an undercut case. They check the reference example, forward/inverse
surface mapping and common normals, then independently test literal moving
triangle-strip slices in both directions at unaligned positive/reverse phases.
A deliberately wrong wheel phase must produce an interior witness. These
samples do not establish continuous-motion clearance for every parameter set.
Strength, thermal behaviour, friction, lubrication, tooling and production
acceptance still require their own checks.
