# Printed cycloidal eccentric shaft with two through bolts

Select **Cycloidal reducer → Eccentric shaft construction → FDM · printed shaft + 2 through bolts**. This control is available for the cycloidal reducer. Entering FDM mode preserves the entered input shaft diameter and disc thickness; incompatible values are reported instead of silently replaced. **Apply compatible FDM dimensions** explicitly sets the starting 17 mm printed input journal, 16 mm discs and default bolt/fit allowances. The dedicated NSK 6804 seat is linked to its 32 mm outside diameter plus the chosen allowance. Eccentric input supports either **Pin flange output / fixed Ring** or **Ring / housing output / fixed Pin flange**. An already selected housing output is preserved when entering FDM mode. Other driving members require the standard shaft construction.

This is an original prototype construction developed for this generator. The cited projects informed the research; none validates the strength or performance of this particular two-bolt shaft.

## Construction and torque path

The metal reinforcement is a **pair of parallel axial M3 bolts**, not a single central bolt used as a free axle. Their axes are at `(0, +4.8)` and `(0, −3.8)` mm in the initial shaft frame, 8.6 mm apart. Both holes pass through every printed shaft segment. The separated axes resist relative rotation through bolt-to-hole bearing contact, even without relying solely on clamp friction. Clearance introduces finite angular play; this is not a zero-backlash connection or a rated key/spline replacement.

The asymmetric pattern also indexes assembly: the two printed pieces cannot simply be flipped 180° on the bolt pattern. The dual disc build has opposing eccentric centres at `(+e, 0)` and `(−e, 0)`. Both bolts rotate with the eccentric member, and retain those locations relative to every printed segment throughout the animation.

The printed stack is intentionally separable so real bearing inner rings can slide onto the journals:

- **Single disc:** input journal / first eccentric base and a removable end cap.
- **Dual disc:** the same base, a second eccentric segment that also retains the first bearing, and a removable end cap.

Each cam has a lower shoulder. The following segment or cap retains the bearing from the other side. The journal stops 0.12 mm short of the bearing upper face so nominal clamping reaches the bearing inner ring before the printed journal end bottoms out. This relief requires measurement and calibration on the actual print; it is not a preload specification.

Upper bolt heads and washers sit in recessed cap pockets below the end of the disc stack, leaving clearance to the output flange. Lower washers and nuts are accessible outside the input end. There is no central reinforcement bolt.

## Starting dimensions and hardware

| Item | Single disc | Dual disc |
|---|---:|---:|
| Printed shaft pieces | 2 | 3 |
| Steel socket head cap screws | 2 × M3×30, ISO 4762 | 2 × M3×45, ISO 4762 |
| Hex nuts | 2 × M3, ISO 4032 | 2 × M3, ISO 4032 |
| Flat washers | 4 × M3, ISO 7089 | 4 × M3, ISO 7089 |
| Eccentric bearings | 1 × NSK 6804 | 2 × NSK 6804 |
| Bearing dimensions | 20 × 32 × 7 mm | 20 × 32 × 7 mm |
| Printed input journal | Ø17 mm | Ø17 mm |
| Printed eccentric journals | Ø19.85 mm | Ø19.85 mm |
| Disc bearing seats | Ø32.20 mm | Ø32.20 mm |
| Bolt clearance holes | Ø3.35 mm | Ø3.35 mm |
| Initial eccentricity | 1.2 mm | 1.2 mm, opposing phases |
| Disc thickness | 16 mm | 16 mm each |

Screw lengths are selected from the existing hardware length list to engage the full nut and leave at least two thread pitches beyond it. They are recalculated when the stack changes. Standard designations identify hardware types, not a chosen manufacturer SKU or strength class. Screw threads and socket recesses are simplified reference geometry.

Dimensions exposes bolt spacing, diametral hole clearance, bearing seat allowance, journal clearance and a minimum printed wall criterion. The 6804 seat diameter is derived from its outside diameter and the selected allowance. Validation rejects insufficient walls, overlapping head pockets, an oversized input journal, insufficient disc thickness and an unsupported screw length. The cap has a 1.5 mm floor and the entered minimum wall cannot exceed it.

The normal automatic bearing/hardware panels are hidden in FDM mode because this construction includes its own eccentric bearings and two-bolt stack. General automatic hardware and arrangements driven by members other than the eccentric are rejected for this option. Both supported output choices are exposed directly in the Motor and load panel; reversing the input/output roles requires the standard construction.

## Ring / housing output

In **Motor and load**, set **Motor: Eccentric**, **Output: Ring / housing**. The panel then shows **Pin flange** fixed to the frame. Single and dual discs are supported.

The housing-output arrangement retains the complete two-bolt input shaft and its removable bearing retainers. It adds an annular output sleeve connected to the existing upper housing cover, followed by a flange with six nominal M3 clearance holes. The fixed pin-carrier shaft is extended through the clear central opening to a separate stationary flange with eight M3 clearance holes. No solid central input adapter is added through the two bolt passages.

The output sleeve starts at the cover end face, above all discs, output pins, ring rollers and the printed eccentric stack. Its central opening clears the fixed coaxial shaft. The frame flange lies axially beyond the rotating output flange. The existing covers and tubular housing stay with the rotating roller ring; the output pins and their flange remain stationary. Enable **Housing** to show the complete rotating body. The added output flange and the printed shaft remain visible when Supports is disabled.

With N ring rollers, eccentric input and a fixed pin carrier, the ideal ratio is **+N:1**. With the default 16 rollers, 1500 rpm input gives 93.75 rpm housing output in the same direction. This differs from the fixed-ring / pin-flange-output arrangement, which has ratio −(N−1):1.

Attach an annular load adapter to the rotating flange and the frame to the separate stationary flange. The interface holes are nominal clearances; attachment screws, the external frame and actual support-bearing selection/retention remain to be specified. These interfaces do not establish a load rating.

## Assembly and printing

1. Make a small calibration print for the selected polymer, printer and orientation. Measure the bearing seats, journals and both bolt holes. The starting allowances describe geometry, not guaranteed as-printed fits.
2. Slide the first 6804 onto the open first eccentric journal and seat it against its shoulder. Fit the first cycloidal disc around the bearing outer ring.
3. For the dual build, add the indexed second printed segment, its bearing and the second disc. The eccentric centres must be opposite. Confirm both bolt paths align before inserting the bolts.
4. Fit the final cap. Insert the two steel bolts with upper washers, then fit the lower washers and nuts. Confirm the cap bears on the intended inner rings and no printed journal end has bottomed out prematurely.
5. Tighten gradually and alternately while checking free motion. Determine tightening torque and retained clamping force experimentally for the polymer and hardware. Check that the bearing outer rings are adequately located in the discs.

Use component selection and STL export for the **printed shaft parts only**. Choose placement, final print orientation, supports, perimeters and local fill in the slicer. Layers, shrinkage and polymer creep affect the shaft; the steel pair does not remove those effects. Commercial bearings, bolts, washers and nuts in the complete assembly STL are reference parts and must be purchased, not printed.

The motor coupling is not universal: design it for the printed Ø17 mm input journal or the asymmetric two-bolt pattern. Neither reinforcement bolt is the rotation axis. Remaining input/output support bearing envelopes, external couplings, seals and load paths still require completion. No allowable torque, fatigue life or stiffness increase is assigned to this prototype without physical testing.

## Example configurations and verification

Open one of the configurations in the repository's [`examples/`](../../examples/):

- [Single disc](../../examples/cycloidal-fdm-single.config.json) or [dual disc](../../examples/cycloidal-fdm-dual.config.json).
- Housing-output [single disc](../../examples/cycloidal-fdm-housing-single.config.json) or [dual disc](../../examples/cycloidal-fdm-housing-dual.config.json).

Use **Export…** to generate your own STL, STEP, component lists and calculation
reports. Generated models and internal verification records are not repository
assets.

The dedicated tests check closed, oriented solids and watertight STL with real holes; coaxial bolt passages through all segments; asymmetry against inverted assembly; opposing bearing centres; accessible journal ends; shoulder and cap placement; purchased quantities; full nut engagement; invalid dimensions; JSON roundtrip; and preservation of fixed hardware in saved configurations. GTK/OpenGL checks cover the selector, single/dual variants, loading, visibility without Supports and playback. Tests validate geometry and assembly relationships, not physical strength or bearing preload.

## Research sources

Sources consulted on 24 October 2026:

- [University of Waterloo Robotics Design Team — eccentric shaft prototype](https://uwaterloo.atlassian.net/wiki/spaces/UWRT/pages/33962263427/Cycloidal%2BDrive%2B-%2BRev%2B1%2BPrototype%2BJournal): modular motor adapter and eccentric cams, with a double-D section for rotational location. It does not use this generator’s pair of axial tie bolts.
- [How To Mechatronics — CNC versus printed cycloidal drive](https://howtomechatronics.com/projects/cnc-machined-vs-3d-printed-cycloidal-drive-designing-testing/): a built dual-disc design with metal eccentric bearings, pins and assembly fasteners. The shaft layout and bearing sizes differ from this implementation.
- [Tom Ilan — printed cycloidal gearbox](https://github.com/tom-ilan/cycloidal_gearbox): proposes screws with metal coverings as an improvement to **output pins**; this is not evidence for the capacity of the present eccentric shaft.
- [NSK — 6804 product data](https://www.nsk.com/in-en/engineering/products/bearings/ball-bearings/deep-groove-ball-bearings/single-row-deep-groove-ball-bearings/6804-apn.html?___store=in) and [NSK bearing replacement guide](https://www.nskautomation.com/nsk-literature/ball-and-roller-bearings/NSK-Bearing-Linear-Replacement-Guide.pdf): 20 mm bore, 32 mm outside diameter and 7 mm width, with a 22 mm minimum shaft shoulder diameter. The prototype uses Ø22.4 mm shoulders; actual fits, chamfers and axial retention must be checked against the chosen bearing and print.
