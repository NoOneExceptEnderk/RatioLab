<a id="doppia-elica-viti-cilindriche-e-strain-wave"></a>

# Double-helical gears, cylindrical worms and strain wave

Dimensional geometry and ideal motion; no strength or production-readiness certification of a complete reducer.

<a id="doppia-elica-unite-e-separate"></a>

## Double-helical: joined and separated

- **Joined helices**: zero gap, the two hands meet at the centre. One continuous body.
- **Separated helices**: adjustable central gap and continuous hub beneath the gap. One body, not two disconnected gears.

For an individual gear, the variant is selected directly. For planetary, two-stage planetary, parallel-axis, compound and internal-ring trains, the **Double-helical construction** menu appears when double-helical teeth are selected.

The gap is hidden and forced to zero for joined helices; it must be positive for separated helices. Old JSON files with `gap: 0` are recognised as joined and those with a positive gap as separated. The axial contact ratio continues to use the width of a single active half, without counting the gap as teeth. Axial-thrust cancellation requires symmetric load sharing.

## Cycloidal eccentric connection

**Integral shaft · solid eccentrics** remains the default: one functional solid
body with offset journals, including both opposing eccentrics for dual discs.
Its integrated journal is retained. Separate input/output shaft blanks and the
automatic external adapters extending them are omitted from preview, component
inventory and CAD exports. Generated keys and the dedicated printed FDM bodies
remain. Interface axes, nominal shaft diameters and required profiles are
recorded in `external_shafts`; complete actual shafts and their lengths in CAD.

**D-shaped cam bores · external shaft** generates only the matching D-shaped
openings. Enter the external shaft diameter and radial flat depth. The initial
cut is `x = radius − flat_depth`, with intersections
`y = ±sqrt(radius² − x²)`. Diameter alone does not specify a universal D-flat:
match the actual shaft drawing ([Ruland](https://www.ruland.com/cc-coupling-d-shafts)).
No intermediate insert or separate reference shaft is generated.

**Keyed cam bores · external shaft** generates a through keyway and one
square-ended key per cam. The external shaft needs its corresponding keyway;
its required dimensions are recorded, rather than generating a shaft body.
Supported nominal diameters are 6, 8, 10 and 12 mm. For Ø6 the nominal key is
2 × 2 mm, with shaft depth 1.2 mm and hub depth 1 mm: radial head clearance is
1.2 + 1 − 2 = 0.2 mm. The reference is the
[Ganter DIN 6885-1 extract](https://www.ganternorm.com/fileadmin/user_upload/downloads/technischer%20anhang/technical_information/6885-1.pdf),
columns `d`, `b`, `h`, `t4` (shaft) and `t2` (hub). Catalog key lengths leave at
least 0.5 mm at each cam end; disc thickness must be at least 9 mm.

The **DIN keyway presets** select the bore/key connection and mating shaft
diameter. They are available in desktop, browser schema and headless discovery.
Each proposal is checked with the ordinary generator against the current disc,
eccentricity, seat, bearing links and other construction settings. An unavailable
proposal shows its reason and cannot be applied. Presets do not resize the seat,
disc, output holes or tooth profile. These are nominal geometric checks, not
load sizing or a certification of an industrial assembly. For an explicit
starting example, the desktop's **Apply example keyed dimensions** button sets
shaft Ø6, disc seat Ø18 and thickness 10 mm, with manual bearings. That example
is separate from the DIN presets and changes those dimensions only on request.

Both bore types share one input-axis clocking datum: zero points to world +X,
positive angles toward +Y. Disc profiles and opposing eccentric phases are
unchanged. Nonnegative diametral bore allowance adds half its value radially;
the D-flat moves outward by the same amount. Key widths stay nominal. Allowance
that removes profile engagement is rejected. The sampled cam must retain a
nominal 0.5 mm wall; this is a construction guard, not strength sizing. Complete
axial retention, actual fits and the external coupling in CAD. No ISO fit-class
or complete-assembly conformity is claimed.

**Separate bored cams · CAD fixing required** retains plain circular cam bores,
with their shaft bodies now omitted too. The bore alone does not define fixing:
complete anti-rotation and axial retention in CAD. Saved `eccentric_design:
standard` projects keep the plain bore choice; projects without an explicit
construction setting use the integral default. Regeneration uses the current
shaft-free component inventory; existing exported files are not changed.

**FDM · printed shaft + 2 through bolts** retains its dedicated printed bodies,
bearing seats, bolt pattern and compatibility restrictions. Its separate output
shaft reference is omitted; the nominal interface to that externally supplied
shaft is retained. These choices are CAD geometry, not a manufacturing-ready
complete assembly.

**Direct D-shaft · matching cam bores** generates the mating shaft and D-shaped
cam bores, with no intermediate insert. Enter the shaft diameter and radial flat
depth. Before clocking the cut is `x = radius − flat_depth`; its intersections
with the circle are `y = ±sqrt(radius² − x²)`. The lower bearing journal remains
round. There is no universal D-flat dimension implied by a shaft diameter;
match the actual shaft drawing ([Ruland](https://www.ruland.com/cc-coupling-d-shafts)).

**Direct keyed shaft · matching keyways** generates a shaft pocket, matching
through keyway in each cam and one square-ended key per cam. Supported nominal
shaft diameters are 6, 8, 10 and 12 mm, using the existing local key catalog.
For example Ø6 uses a 2 × 2 mm key, shaft depth 1.2 mm and hub depth 1 mm;
the nominal radial head clearance is 1.2 + 1 − 2 = 0.2 mm. The source is the
[Ganter DIN 6885-1 extract](https://www.ganternorm.com/fileadmin/user_upload/downloads/technischer%20anhang/technical_information/6885-1.pdf),
columns `d`, `b`, `h`, `t4` (shaft) and `t2` (hub). Catalog lengths are selected
below disc thickness with at least 0.5 mm axial margin at each cam end. Disc
thickness must be at least 9 mm. The desktop's explicit compatible-dimensions
button sets shaft Ø6, disc seat Ø18 and thickness 10 mm, with manual bearings;
selecting the keyed option alone does not silently change these dimensions.

Both direct connections share one input-axis clocking datum: zero points to
world +X and positive angles turn toward +Y. Opposing eccentric offsets and
cycloidal disc phases remain unchanged. Nonnegative diametral bore allowance
adds half its value radially; the D-flat shifts outward by that amount too.
Key widths stay nominal. Allowances that remove profile engagement are rejected.
The sampled cam must retain a nominal 0.5 mm wall around the bore/keyway; this
is a construction guard, not strength sizing. Neither a D shape nor a parallel
key retains a cam axially: complete retention, actual fits and the external
coupling in CAD. No ISO fit-class or complete-assembly conformity is claimed.

## Planetary paired internal contact

All five planetary variants use the same paired internal construction, including
each distinct stage of a two-stage model. The ring addendum is derived from the
actual mating planet's involute start, and the ring blend is kept outside the
planet's radial reach. Reports expose the significant ring-tip shortening and
the continuous transverse polygon clearance status. See the [construction,
equations, numerical verification and limits](calculations.md#paired-planetary-rings).

Saved projects keep their tooth counts, dimensions, RPM and existing schema.
Regenerating an older planetary project deliberately changes its inner ring
contour, identified in metadata by `planetary_paired_involute_v1`; previously
exported meshes or CAD bodies are unaffected. Sun and planet profiles, reference
circles and outer housing dimensions retain their former construction.
Standalone internal pairs retain their previous geometry and warnings.

A clear status covers the generated unloaded neutral-backlash transverse
polygons over their full phase period. Matching helix phase ratios and groove
material subsets extend this result to ideal transverse sections of helical and
double-helical variants, including both hands. It does not certify unsampled
analytic curves or interpolation between exported CAD/STL stations. Zero/tiny
backlash, touching boundaries or exhausted verification limits remain unresolved;
a detected proper polygon collision rejects generation. The ring remains a
nominal involute/tangent construction, not a pinion-cutter envelope or a claim of
manufacturing readiness, strength or load sharing.

## Cylindrical worm: ZA and ZI

ZA retains straight axial screw flanks; ZI retains a transverse involute screw.
The wheel now uses the matching helicoid envelope, including the swept hob-tip
root transition and backlash, rather than a helical-gear surrogate. Both hands,
1–4 starts, separate bores and optional journals remain available. Unsupported
or unresolved geometries are rejected explicitly.

See the [worm equations, original references, supported domain and numerical
validation](worm.md). The ideal rigid generated envelope and discrete clearance
checks do not certify a manufactured transmission, strength or self locking.

<a id="strain-wave-cup-flat-cup-e-silk-hat"></a>

## Strain wave: cup, flat cup and silk hat

The previous geometry was a simple deformed ring. The following are now available:

- **Cup**: cup-shaped body with an annular diaphragm at the bottom.
- **Flat cup**: the same cup architecture, with reduced and adjustable initial length.
- **Silk hat**: open body with an outward-facing annular flange.

Cup and flat cup include an output bore independent of the cam bore. Silk hat allows the radial flange width to be selected. The flexible body is always **one solid** comprising wall, diaphragm/flange and toothed band; the section gradually transitions from circular to deformed. Wall thickness, body length and diaphragm/flange thickness are distinct.

These architectures are documented in the [official Harmonic Drive Systems models: CSF, CSD and SHF](https://www.hds.co.jp/english/products/model/). The names describe the architecture; dimensions of a specific commercial product are not reproduced and order codes are not assigned.

The pitch ellipse uses a = rp + amplitude; b is solved numerically so that the perimeter is 2πrp. The independent check uses 4096 points. Tooth pitch is now uniform along the pitch-line arc, solving the integral of elliptical speed with eight harmonics and Newton inversion. Radial offsets of the reference profile become offsets along the local ellipse normal, orienting the teeth. The axial transition interpolates the circular and elliptical maps; motion uses identical immutable material coordinates and coefficients in the shader. The numerically verified domain is q=(a²−b²)/(a²+b²)≤0,25. The ring is generated from the matching complete tooth sweep under this map; perimeter and pitch conservation alone are not its conjugacy check. Deformation remains prescribed, without an elastic solution.

The wave generator and its bearing envelope follow the deformed cavity with explicit thickness and radial clearances. The bearing is classified as an **envelope to be defined**, not a catalogue purchase. The flexible tooth reference is mapped with the local ellipse normal; the rigid ring uses its full generated outer swept envelope, including all branches and corners. Reference backlash and derived numerical enclosure relief are reported separately. This does not reproduce an industrial S-tooth profile or establish fatigue capacity. See [the equations, original references, sampled verification and remaining limits](strain-wave.md).

<a id="due-schemi-cinematici"></a>

### Two kinematic arrangements

With zf teeth on the flexspline and zc = zf + 2 on the ring, input at the wave generator:

```
Fixed ring, flexspline output: i = zf / (zf − zc) = −zf/2
Fixed flexspline, ring output: i = zc / (zc − zf) = +(zf+2)/2
```

The geometry is the same; the constraint, output, signed ratio and calculation report change. Constraints are described without creating automatic kinematic joints in CAD. Source: [Harmonic Drive LLC, Engineering Data, pages 10–11 on ratios and configurations](https://global.harmonicdrive.net/_hd/content/documents1/CSG-CSF_GearUnits.pdf).

**Pancake is not a synonym for flat cup**: it is a distinct architecture with two circular splines. It is documented in the same source, but is not simulated by renaming a short cup. It is not included in the variants of this revision.

<a id="verifiche-e-file"></a>

## Checks and files

Tests: `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test*.py'`. Checks cover ZA profiles, thicknesses, mirrored hands, continuity, journal limits, wave perimeter, ratios, clearances and preview/STEP face identity, including left-handed ZI and silk hat. The bill of materials accounts for axial sections in the part code and envelope, to distinguish flanges of different dimensions.

Configurations in [`examples/`](../../examples/). Bills of materials, reports and CAD documents are created in the export folder selected by the user. For nominal loads, units and general limits, see [CALCULATIONS.md](calculations.md).


## Cylindrical topping and semitopping

For controls, complete example projects, an illustrated comparison and report
interpretation, see the [tooth-tip user guide](../tooth-tips.md).

The shared native/WebAssembly Rust kernel supports independent tip treatments
for single spur/helical/double-helical gears, each member and stage of parallel,
internal, planetary and Wolfrom reducers, and both the pinion and finite rack.
Repeated planets share their rim settings. Topping and semitopping can be combined.
They are disabled by zero removal/height; legacy nominal geometry is preserved.

`topping_mm` is radial material removal from the existing nominal head, after
profile shift or the derived paired-ring shortening. It decreases an external
tip radius, increases an internal tip radius, or lowers the rack head. It does
not change roots, reference pitch, tooth count or shaft speeds. It specifies
the finished geometric limit, rather than simulating a production hobbing setup.

`semitopping_mm` is the radial height measured from that finished head to the
unchanged primary flank. `semitopping_angle_deg` is the pressure angle of a
virtual generating ramp in the normal rack plane, not an axial-face bevel angle.
For cylindrical teeth it produces a secondary involute; finite rack ramps are
straight. Internal profiles remain nominal constructions with a tangent root
blend, not a qualified pinion-cutter envelope. Double helices retain their
existing trace, continuous core and optional groove.

### Reference, equations and limits

Primary references:

- [ASH Gear, Gear Hobbing Guide, page 2](https://www.ashgear.com/wp-content/uploads/2025/11/ash-gear-hobbing-guide.pdf#page=2), definitions of topping and semi-topping.
- [KHK Technical Reference, section 3.7, figures 3.11-3.12](https://www.khkgears.co.jp/files/libs/3046/202508062248126215.pdf), tip-corner treatment and the loss of useful addendum/contact. Its illustrative size is not an automatic default here.
- [OPEO, Generation of semi-topping profiles, 18 January 2021 / 24 January 2026](https://opeo.jp/library/onepoint/mech_elem/gear/semi-topping/), secondary involute generated using the ramp angle as the cutter pressure angle. The following equations express that construction in RatioLab coordinates.

Lengths are mm, internal angles radians, UI angles degrees, positive rotation
about local +Z. Use sign s=+1 for external teeth and s=-1 for internal teeth.
Let rp be reference radius, ra0 the existing nominal tip radius, t topping
removal, h semitopping radial height, beta helix angle, alphaKn the normal ramp
angle, and A0(r) the original positive half-tooth angle. Then:

```text
ra = ra0 - s*t
rj = ra - s*h
alphaKt = atan(tan(alphaKn)/cos(beta))
bk = rp*cos(alphaKt)
Ib(r) = sqrt((r/b)^2-1) - atan(sqrt((r/b)^2-1))
AK(r) = A0(rj) + s*(Ibk(rj) - Ibk(r))
P(r) = (r*cos(AK(r)), r*sin(AK(r)))
```

The join is position-continuous; the deliberately changed slope forms the
head corner. Normal conversion is shared by both helix hands. The primary
flank remains unchanged up to rj. The mirrored flank and circular top land
complete each tooth. Rack half-width is `w(y)=pt/4-j/4-y*tan(alpha_t)` up to
its join height yj; above yj it is `w(yj)-(y-yj)*tan(alphaKt)`.

Removal and height must be nonnegative and leave a positive top land and a
working addendum before the reference pitch surface. An enabled ramp angle
must exceed the normal working pressure angle. The finished primary intervals
feed metrology and effective contact: external upper limit rj, internal lower
limit rj, and rack working head yj. Contact on semitopping is not counted.
Modified pairs with an effective total contact ratio of one or less are
rejected; rack transverse engagement must remain above one. Existing other
construction, resource and interference limits still apply.

Sampling, ordinary STEP/STL/SVG/DXF, preview and collision queries consume the
same modified nominal geometry. JSON projects/history retain the controls and
exact decimal sources; the dimensions cache includes topping. Calculation
JSON/text reports expose finished and active tip limits separately. The opt-in
curved-CAD prototype rejects semitopping explicitly; ordinary STEP remains
available. Nominal profile geometry and contact coverage do not establish
strength, loaded contact or manufacturing suitability.
