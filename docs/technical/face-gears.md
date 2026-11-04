# Orthogonal face-gear pairs

RatioLab generates a face wheel conjugate to a cylindrical involute pinion with
90° shaft directions and an adjustable signed shaft offset. Zero offset gives
intersecting axes; nonzero offset gives skew axes. Tooth types are spur, helical and double helical with
joined or separated working bands. The face teeth are an envelope of the moving pinion,
not cylindrical teeth copied or twisted around a disc.

## Primary references and construction scope

The generating principle follows Litvin and coauthors:

- [NASA/CR-2000-209909](https://ntrs.nasa.gov/api/citations/20000027536/downloads/20000027536.pdf),
  Part 1, sections 1.4–1.7: involute shaper equations 19–20, transformed surface
  and meshing equations 21–22, rotation ratio equation 24, and singularity/pointing
  conditions. Part 2, section 2.1, equations 63–69 covers offset spur face gears;
  sections 2.2–2.3 discuss axes of meshing and asymmetric pointing limits.
- [NASA/CR-2005-213443](https://ntrs.nasa.gov/api/citations/20050080713/downloads/20050080713.pdf),
  sections 2–3: screw involute and normal equations 1–4, face generation equations
  15–18, and avoidance of singularities and pointing, equations 19–23.

Here the virtual generating pinion has the same tooth count and nominal geometry
as the mating pinion, with a reference thickness allowance. Perfect aligned
working surfaces therefore have ideal line contact. The industrial localization
obtained with a different shaper tooth count or modified pinion is not reproduced.
Face crest height and nonworking root extension are custom nominal constructions;
this is not a stock-compatible industrial cutter design or a loaded-contact model.

A further primary reference is [Fu et al., Scientific Reports, DOI
10.1038/s41598-025-29441-0](https://www.nature.com/articles/s41598-025-29441-0),
section “The principle of TCA for INOPS helical face gear transmission”, figures
1–2 and equations 1–4, which treats offset helical face gears. This implementation
uses the involute envelope and relative velocity, without the paper’s loaded
contact, profile shifts or nonorthogonal shaft-angle model.

## Units, axes and dimensions

Lengths are mm, internal angles radians, UI pressure/helix angles degrees and
operating speeds RPM. For normal module mn, normal pressure alpha_n, signed pinion
helix beta and tooth counts zp/zw:

```
mt = mn / cos(beta)
alpha_t = atan(tan(alpha_n) / cos(beta))
rp = mt*zp/2
Rref = mt*zw/2
g = wheel_angular_speed / pinion_angular_speed = zp/zw
H = 2*rp
```

The face wheel axis is world +Z through the origin. Pinion +X passes through
`Op=(0,E,H)`, where E is the signed **shaft offset** in world Y. Their shortest
distance is `abs(E)`; directions remain 90°. At E=0 they intersect at `(0,0,H)`.
E differs from radial setting along world X.
Pinion local XYZ maps to world YZX, with origin Op. Positive rotations follow the
right-hand rule; the input/output ratio is positive `zw/zp` in these frames.
The sign must not be copied from the separate bevel-pair convention.

The pinion axial interval is `X0=Rref+radial_setting` through `X1=X0+width`.
Thus width is measured along the pinion shaft, rather than being an exact annular
radial width. Generated radial band ends can curve slightly. The backing remains
circular, with extra untoothed inner/outer lands and an independently sized bore.
Backing thickness is measured below the face tooth roots.

## Conjugate envelope in these coordinates

Let sigma be flank sign, r pinion cylindrical radius and phiX(X) the pinion's
axial twist. With base radius `rb=rp*cos(alpha_t)`, the thickened virtual pinion
has half tooth angle

```
Hhalf(r) = pi/(2*zp) + j/(4*rp) + inv(alpha_t) - inv(acos(rb/r))
inv(a) = tan(a)-a
a0 = -pi/2 + sigma*Hhalf(r) + phiX(X)
```

The actual pinion instead uses `-j/(4*rp)`. This splits reference tangential pair
backlash j equally between pinion thinning and enlargement of generated face
spaces. It does not represent bearing clearance or loaded deformation.

For pinion roll phi, world point P and wheel body point W are

```
P = Op + Rx(phi)*(X, r*cos(a0), r*sin(a0))
W = Rz(-g*phi)*P
n dot (ex cross (P-Op) - g*ez cross P) = 0
```

For fixed X and positive height parameter `h=H-Pz`, write `Y=Py-E`, `S=Y²+h²`,
`q=sqrt(S-rb²)` and `k=d(phiX)/dX`. The meshing equation becomes

```
F = k*S*(Y+E) + sigma*X*q*Y/rb + X*h - S/g = 0
FY = k*(3*Y²+h²+2*E*Y) + sigma*X*(q+Y²/q)/rb - 2*Y/g
r = sqrt(S)
phi = atan2(-h,Y) + pi/2 - sigma*Hhalf(r) - phiX(X)
wheel_radius = hypot(X,Y+E)
wheel_angle = atan2(Y+E,X) - g*phi
wheel_height = H-h
```

The selected branch is separated with `sign(FY)=sigma`. Opposite generating
pinion flanks bound a **space** in the face wheel. Material is assembled between
one space side and the neighboring space side, adding a wheel tooth period.
Both placement and envelope change with offset. Translating only the old pinion
while retaining its old face wheel does not construct a matching pair.

Face crest uses `hmin=rp-face_addendum*mn`, default coefficient 0.65. Root plane
uses `hmax=rp+1.25*mn`. Working contact stays on the actual pinion usable involute
through its tip `rp+mn`. Beyond that physical tip the virtual involute continues
to define nonworking root clearance. This continuation is not a rounded
shaper-tip-generated face root fillet. Pinion roots retain the existing rounded
rack-tool construction and trimming.

## Double-helical construction

**Joined** is the default for a newly selected double-helical face pinion. It
produces one continuous face tooth band. **Separated** exposes the central groove
width and retains the previous two-band construction. A saved project with a
positive groove and no style field keeps its separated geometry when loaded.
The pinion remains one solid in either construction.

For joined teeth, set `xm=(X0+X1)/2` and
`phiX(X)=k*min(X-X0,X1-X)`. The two involute halves have slopes +k and -k.
The pinion cusp generates a small additional surface on the convex flank;
overlapping concave envelopes are trimmed at their intersection. Their endpoints
cannot simply be glued together or bridged with a flat artificial tooth.

A useful derivation takes fixed wheel radius R and height parameter h. For a
generating world angle psi:

```
X = R*cos(psi)
Y = R*sin(psi)-E
r = hypot(Y,h)
phi = atan2(-h,Y)+pi/2-sigma*Hhalf(r)-phiX(X)
theta = psi-g*phi
```

A moving generating tooth sweeps a space between the minimum theta for sigma=-1
and maximum theta for sigma=+1. Smooth candidates obey the original F=0 on their
respective halves. Cusp candidates have `X=xm` and
`Y=±sqrt(R²-xm²)-E`, between the limiting smooth contact coordinates. Select the
lower/upper envelope. Where smooth envelopes overlap, their equal-theta
intersection is the concave trim crease. Changing helix hand swaps which flank
uses the cusp-generated region. The k=0 limit is the continuous spur surface.

Joined teeth use a common circular annulus inside all supported inner and outer
pinion-span limits, enclosed across the full height range. Its radial width can
be smaller than the pinion axial width. Height-dependent cusp endpoints and the
concave intersection are explicit anchors of the radial mesh grid. Each smooth
surface retains the existing numerical enclosures; cusp/trim solves and finite
refinement are not an interval certificate for the whole joined surface.

Connected ideal contact is checked on untouched smooth tracks with whole
interval enclosures, outside every cusp/trim radius and inside the actual usable
pinion involute. Phase spans are sufficient lower bounds for those continuous
tracks. They do not establish equal band loading or net axial cancellation.

Separated helices retain a central groove and short relieved transitions. Only
the unchanged working portions generate their two radial tooth bands. Relief
must be at least one normal module, leaving more than 1 mm per pinion half;
mapped bands must remain separated. Both constructions use one common backing.

## Domain and numerical checks

The generator refuses base-cylinder branch crossings, inadequate pinion core or
bore walls, unresolved roots, singular/undercut surfaces, pointed/overlapping
teeth, mapped band overlap, inadequate ideal engagement and exhausted budgets.
Changing radial setting, width, addendum and helix can move a configuration
outside the supported domain; displayed parameter ranges do not guarantee every
combination is valid.

Supported absolute offset is below `Rref/2`. NASA’s spur layout recommendation
in Part 2 equation 69 gives `abs(E) < m*zw/4`; the reference-radius bound is also
used conservatively for the offered helical types. It does not establish helical
sliding losses or thermal limits. Regularity, pointing and engagement can impose
tighter limits, especially when offset and helix signs combine.

Parameterized Krawczyk cells enclose the chosen scalar root over both full
`(X,h)` rectangles. Implicit derivatives check separated roots, positive generated
radial ordering, monotone pinion radius along each height track and ordered
flank angles at fixed axial position and at fixed generated radius. The latter
ensures that angular separation between the opposite radial graphs decreases
toward the roots, so the root/crest width checks cover the intermediate heights.
Root/crest space widths are checked over X using enclosed angle
derivatives. Opposite offset/helical flanks can have different radii at equal X.
The angular-width bound includes the maximum angular axial derivative divided
by the minimum positive radial axial derivative, multiplied by an enclosed
opposite-flank radial difference. This conservatively corrects the comparison
to equal generated radius; equal-X angles alone would be insufficient.
Arithmetic intervals expand with `nextafter`; transcendental
evaluation uses host libm. These are numerical enclosures, not exact arithmetic
or formally verified transcendental proofs.

The monotone radius defines connected in-cap tracks lying on the actual usable
pinion flank. Endpoint phase differences are conservative lower bounds on the
unwrapped phase span of those continuous tracks. The pair requires more than one
tooth pitch for each flank. This is sufficient ideal engagement, not a loaded
contact pattern or continuous whole-mesh clearance certificate.

Face geometry uses common adaptive height/axial grids with finite quarter/midpoint
probes at 0.003 mm, plus bounded sampling of the defined crest/root arcs. These
criteria do not certify global working-surface or manufacturing accuracy.
Transverse pinion profiles retain their existing finite adaptive criterion.
Actual explicit triangles define both preview and faceted STEP/STL surfaces;
the face wheel is limited to 250,000 triangles. Cylindrical bores are nominally
circular but faceted in this freeform wheel. Its freeform surface is not exported
as a misleading extrudible 2D tooth profile; profile exports identify that limit.

Complete shafts, bearing seats, supports, retention and lubrication in CAD.
No strength, wear, durability, allowable load, industrial conformity or universal
collision-free parameter/phase result is implied.

## Reproducible independent checks

At mn=2, zp=24, zw=72, alpha_n=20°, beta=0, j=0, X=72 and h=24, the exact pitch
benchmark gives `Y=0`, `r=24`, wheel radius 72 and world point `(72,0,24)`.
For flank +1, pinion phase is `-pi/48` and wheel body angle `pi/144`.
With E=10 at the same X/h, the exact spur benchmark instead gives world point
`(72,10,24)`, wheel radius `sqrt(5284)`, unchanged pinion phase and wheel angle
`atan2(10,72)+pi/144`. The shortest axis distance is 10 mm.
The offset benchmark fixture uses a 3 mm band width to remain within the
supported blank domain; the analytic reference pitch point is evaluated
independently of the selected band's axial position.

`tests/test_face_herringbone.py` independently samples the full moving involute
to check the upper/lower swept envelope, checks cusp normals against the limiting
normal cone, and verifies concave intersections. Solid containment distinguishes
real central tooth material from the old groove. Moving meshes, reverse/stopped
input, worker/project paths and exports are checked separately.

`tests/test_face_gears.py` also constructs an independent involute, obtains its
normal by finite differences and solves the literal world-frame velocity condition
for roll by bisection. It compares positions and generated-surface normals for
both helix hands and both double bands, tests the wrong rotation sign, checks
implicit derivatives and independent refinement probes, and exercises closed
moving shared solids with a wrong-phase collision control. Separate tests cover
projects, zero/reversed speeds, retained buffers/pose continuity, worker parity,
finite search and canonical exports. Native GTK/OpenGL and actual browser checks
remain separate evidence from these analytic and finite sampled-solid checks.
