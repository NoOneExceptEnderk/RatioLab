<a id="doppia-elica-viti-cilindriche-e-strain-wave"></a>

# Double-helical gears, cylindrical worms and strain wave

Dimensional geometry and ideal motion; no strength or production-readiness certification of a complete reducer.

<a id="doppia-elica-unite-e-separate"></a>

## Double-helical: joined and separated

- **Joined helices**: zero gap, the two hands meet at the centre. One continuous body.
- **Separated helices**: adjustable central gap and continuous hub beneath the gap. One body, not two disconnected gears.

For an individual gear, the variant is selected directly. For planetary, two-stage planetary, parallel-axis, compound and internal-ring trains, the **Double-helical construction** menu appears when double-helical teeth are selected.

The gap is hidden and forced to zero for joined helices; it must be positive for separated helices. Old JSON files with `gap: 0` are recognised as joined and those with a positive gap as separated. The axial contact ratio continues to use the width of a single active half, without counting the gap as teeth. Axial-thrust cancellation requires symmetric load sharing.

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
