# Wolfrom / 3K reducer

The supported construction uses straight cylindrical teeth, two rigidly connected
planet rims on each pin, one carrier, an input sun, a fixed first ring and an
output second ring. It is different from a carrier-output planetary gearbox.
The external motor and its drive hardware are outside this model.

## Reference model

[Singh et al., COMPAct, §II-D, equations 7–8](https://arxiv.org/html/2510.07197v1#S2.SS4)
give the compound Wolfrom ratio; §III-B equation 12 gives the pitch-centre
constraints. [Karaivanov et al., Torque Method Investigation of Wolfrom Gear
Trains, §2, figures 2–4](https://hrcak.srce.hr/en/file/434707) distinguish one-rim
and two-rim arrangements. This implementation uses the two-rim arrangement.
One-rim triple engagement, helical teeth and modified profiles require separate
geometry and assembly models.

Let S, P1, Rf, P2 and Ro be the positive integer tooth counts of the sun, first
planet rim, fixed ring, second planet rim and output ring. Lengths and modules
are in mm. All angular velocities share world +Z and use rpm; phases below are
in radians. Input/output ratio i is signed.

```
Rf = S + 2 P1
m2 = m1 (S + P1) / (Ro - P2)
a = m1 (S + P1)/2 = m2 (Ro - P2)/2

wc = ws S/(S + Rf)
wp = wc - (ws - wc) S/P1
wo = wc + (wp - wc) P2/Ro
i  = (1 + Rf/S)/(1 - Rf P2/(P1 Ro))
```

The second module is derived, rather than independently rounded or adjusted.
Both planet rims have the same absolute spin wp and orbit at wc. A negative
ratio reverses output rotation. Rf P2 = P1 Ro gives a stationary output for any
input and is rejected as a singular reducer. Zero input stops every moving
member; reversed input reverses every member.

## Equal spacing and identical compounds

For n equally spaced identical compound planets, the implementation derives
clocking from all three tooth-phase equations. In addition to n dividing S+Rf,
require n gcd(P1,P2) to divide P1 Ro + P2 S. This is a tooth-phase congruence,
not a load-sharing condition. It is more general than requiring each central
gear tooth count to be divisible by n.

For tooth-centred local +X contours, choose planet datum angles
φ10 = π + π/P1 and φ20 = π + π/P2. The fixed and output ring datums are
φf = P1 π/Rf and φo = P2 π/Ro. Solve

```
P2 k ≡ -(P1 Ro + P2 S)/n  (mod P1)
θj = 2π j/n
φ1j = φ10 + (S + P1) θj/P1 + 2π j k/P1
φ2j = φ1j + (φ20 - φ10)
```

The same relative rim offset applies to every planet. Turning a planet by one
first-rim tooth pitch does not generally preserve engagement of its second rim;
the congruence selects a compatible turn before generating geometry.

## Nominal profile scope

Both internal meshes reuse the paired planetary involute construction described
in [calculations](calculations.md). Ring tips are shortened as needed to keep
contact inside the generated planet involute; the tangent internal root blend
is not a shaping-cutter envelope. Reports retain each derived ring addendum,
usable contact interval, profile sampling threshold and the bounded transverse
polygon-clearance result. A numerical budget limit must remain visible as
unresolved. None of these checks certifies cutter access or manufacturing.

Adjacent planet tip circles, bores, axial gaps and nominal carrier/pin geometry
must fit. The model describes ideal motion and nominal solids. Strength,
durability, efficiency, elastic load distribution, bearing selection and
physical backdrivability are not predicted from a high reduction ratio. The
finite combination-search and interactive gauge tools do not currently include
this family; per-gear nominal metrology remains available in its calculation
report.

## Independent numerical example

With S=18, P1=72, Rf=162, P2=59, Ro=135 and n=3, m2/m1=45/38.
For ws=1 rpm the exact rates are wc=1/10, wp=−1/8 and wo=1/600 rpm:
i=+600. With m1=0.5 mm, a=22.5 mm and the fixed ring pitch diameter is 81 mm.
That pitch diameter is not the overall gearbox diameter. The 600:1 value is a
nominal equation benchmark; it is not a measurement of a community video.
