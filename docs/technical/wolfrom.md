# Wolfrom / 3K reducer

The supported construction uses spur, single-helical or double-helical cylindrical
teeth, two rigidly connected
planet rims on each pin, one carrier, an input sun, a fixed first ring and an
output second ring. It is different from a carrier-output planetary gearbox.
The external motor and its drive hardware are outside this model.

## Reference model

[Singh et al., COMPAct, §II-D, equations 7–8](https://arxiv.org/html/2510.07197v1#S2.SS4)
give the compound Wolfrom ratio; §III-B equation 12 gives the pitch-centre
constraints. [Karaivanov et al., Torque Method Investigation of Wolfrom Gear
Trains, §2, figures 2–4](https://hrcak.srce.hr/en/file/434707) distinguish one-rim
and two-rim arrangements. This implementation uses the two-rim arrangement.
One-rim triple engagement and alternative working-profile systems require separate
geometry and assembly models.

Let S, P1, Rf, P2 and Ro be the positive integer tooth counts of the sun, first
planet rim, fixed ring, second planet rim and output ring. Lengths and modules
are in mm. All angular velocities share world +Z and use rpm; phases below are
in radians. Input/output ratio i is signed.

```
Rf = S + 2 P1
m2 = m1 (S + P1) / (Ro - P2)
a = m1 (S + P1)/(2 cos β) = m2 (Ro - P2)/(2 cos β)

wc = ws S/(S + Rf)
wp = wc - (ws - wc) S/P1
wo = wc + (wp - wc) P2/Ro
i  = (1 + Rf/S)/(1 - Rf P2/(P1 Ro))
```

The second module is derived, rather than independently rounded or adjusted.
Both modules and the entered pressure angle are normal quantities. Spur uses
β = 0. Both layers share the same helix magnitude, so the cosine cancels from
the derived module ratio and all speed equations remain unchanged.
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

The sun, both planet rims and both rings have independent
[topping and semitopping](../tooth-tips.md) settings. Repeated compounds share
their corresponding rim settings. `planet2_` identifies the second rim, and
`output_ring_` identifies the output ring; these are not second-stage fields.
Treatments retain the pitch-centre/module relation and ideal speed equations
while reducing the primary working interval used by each affected mesh.

### Helix and axial phase conventions

The [TBK manufacturer's manual, §§5.2.3–5.2.4](https://www.tbksoft.com/fileadmin/dokumente/tbk/etc/HTMLHandbuch/en/HTMLHandbuchch5.html)
requires opposite hands for external parallel-axis meshes and the same hand for
internal meshes. The normal/transverse conversion follows the shared
[cylindrical equations](calculations.md#cylindrical-teeth-normal-and-transverse-geometry):
mt = mn/cos β, αt = atan(tan αn/cos β), pitch radius r = mt Z/2.
The centre-distance equation above follows by equating the external S/P1 sum
and each internal ring/planet radius difference. At β = 20°, m1 = 0.5 mm and
18/72/162, 59/135 teeth, m2 = 45/76 mm, a = 23.943999880708 mm and i = +600.
As β approaches zero this becomes the original a = 22.5 mm spur design.

The sun has selected signed β; both compound rims and rings have −β. Each layer
has its own lower-face datum. With local axial position u in mm, the section
rotation is δ(u) = u tan β/r radians (with the member's signed β).
Thus S δs + P1 δp1 = 0, P1 δp1 − Rf δf = 0 and
P2 δp2 − Ro δo = 0 at every corresponding section. These identities preserve
the transverse assembly congruences throughout each layer. The common compound
clocking is between the two lower-face datums; the two sweeps need not form one
continuous helix across the hub. Independent face widths remain supported.

Double helices use the existing symmetric section construction within **each**
layer. Choose joined helices (zero groove) or separated helices (a common positive
groove g). Each layer's active half-width is (b − g)/2; the overlap contact ratio
uses one half. The inter-layer gap is a separate parameter. The opposing section
phases preserve the same identities, and both internal pairs must pass the common
axial-phase and groove-material-subset checks as well as transverse clearance.
Single-helical axial thrust requires external bearing design. Double-helical
thrust cancellation assumes symmetric loading; this model does not verify it.

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
