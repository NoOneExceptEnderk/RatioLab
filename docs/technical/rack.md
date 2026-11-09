# Finite rack and pinion

Three tooth types share the same geometry and motion/export pipeline: spur,
helical and double helical. Double helices can join or be separated by a relieved
groove, with a continuous pinion core and rack base. The pinion is the rotary
input. Linear input/reversed member roles are not offered in this version.

## Reference equations and frames

Primary reference: KHK, *Calculation of Gear Dimensions*, section 4.1(3),
Table 4.5, Figure 4.3 and equation 4.2 for spur racks; section 4.3(3), Table 4.13
and equation 4.18 for normal-system helical racks.
[Official technical reference](https://khkgears.net/new/gear_knowledge/gear_technical_reference/calculation_gear_dimensions.html).

Lengths are millimetres, internal angles radians, UI pressure/helix angles
degrees, input speed RPM. Normal module mn and pressure alpha_n are shared:

```
mt = mn / cos(beta)
alpha_t = atan(tan(alpha_n) / cos(beta))
pt = pi * mt
rp = mt * pinion_teeth / 2
travel_per_revolution = pt * pinion_teeth = 2*pi*rp
x = rp * pinion_angle
linear_speed_mm_s = 2*pi*rp * input_rpm / 60
```

The rack pitch line is world Y=0, teeth point toward +Y and travel is along +X.
The pinion shaft is +Z through (0,rp). Right-hand positive pinion rotation drives
positive rack translation. The lower pinion surface has matching axial trace
`x(z)=rp*phi(z)`, where `phi(z)=z*tan(beta)/rp`. The derived rack has the opposite
conventional hand to the pinion: matching traces incline in the same world
direction at their common contact region. Do not independently assign rack hand.
Double helices reverse this slope in the second working half.

This is a rotary-to-linear conversion. No dimensionless reduction ratio, rack
output RPM or output torque is reported. Nominal output force is input torque
divided by reference radius, with the selected assumed efficiency. It is not an
allowable load or linear-guide friction model.

## Tooth and blank construction

Pinion working flanks reuse the existing cylindrical involute and trimmed rounded
rack-tool root envelope at zero profile shift. With zero tip treatments, the
finite rack has straight
transverse flanks with nominal sharp corners, addendum mn, dedendum 1.25mn and
the specified base thickness below the roots. Reference pair backlash j is split:
pinion reference tooth arc and rack reference tooth thickness each decrease by j/2.
Rack tooth half-width at height y is `pt/4 - j/4 - y*tan(alpha_t)`.

Independent [topping and semitopping](../tooth-tips.md) controls are available
for the pinion and rack. Topping lowers the rack head; its semitopping ramp
joins the unchanged straight flank. Effective engagement uses the rack's
remaining working height and the pinion's remaining primary involute, excluding
chamfer contact. Reference pitch and travel per revolution remain unchanged.

Every requested rack tooth is complete. Fixed rectangular end planes include
additional untoothed lands accommodating axial sweep; total physical base length
is `(rack_teeth+1)*pt + abs(helix_sweep)`. The rack tooth count controls length in
whole pitches; base thickness does not add guides, shafts, holes or hardware.

Explicit, corresponding axial sections follow the pinion working helices and
its optional relieved central transitions. Rack sections follow the same axial
levels, trace displacement and relief fraction. The groove relief is nonworking
nominal geometry. In each pinion interval, the underlying defined section is
`R(phi0+f*delta_phi)*(q0+f*delta_q)`. Its second derivative norm is bounded by
`Rmax*delta_phi^2 + 2*abs(delta_q)*abs(delta_phi)`. Subdivision limits the axial
vertex-trace chord error to 0.003 mm using that bound. This does not bound total
involute profile sampling error, whole triangulated working surfaces or
manufacturing accuracy. Transverse pinion profiles retain their existing finite
0.015 mm adaptive chord criterion. Surface budgets remain 250,000 faces per part.

## Compatibility and finite stroke

Pointed or overlapping rack teeth, inadequate pinion bore walls, unusable
pinion contact, insufficient engagement and exhausted mesh budgets are refused.
The rack-tip approach coordinate must be positive, and its contact radius must
stay above the pinion's actual trimmed involute start. The nominal transverse
contact ratio is the available line-of-action length divided by transverse base
pitch and must exceed one. No strength or elastic-contact result is implied.

The conservative symmetric travel excludes the horizontal reference pinion
footprint, the full helix sweep and one rack pitch from each end of the reference
toothed interval. It is a supported preview stroke, not a mechanical end stop.
Tip treatments remove material but do not expand this established working stroke.
Both members stop together at its boundary. Reversing RPM continues from the
same angle/displacement; zero RPM retains the current position. Initial pose
returns to nominal geometry. Programmatic poses outside the working stroke are
rejected. The finite rack has no rotary repetition period; interference analysis
samples its bounded working stroke instead. Such discrete tests do not certify
continuous clearance at every parameter and position.

Complete physical linear guides, mounting, pinion shaft/bearings, retention,
lubrication and end stops in CAD. The generator exports two blanks; supports and
their quantities are not inferred.

## Independent benchmark and tests

KHK Table 4.13 uses mn=2.5, alpha_n=20°, beta=10°57′49″, z=20: reference diameter
50.92956 mm, transverse pressure 20.34160° and approximately 160 mm per pinion
revolution. With pitch-line height 27.5 mm, mounting distance is 52.965 mm.
The spur default mn=2,z=24 gives 48*pi mm/rev and 30.159289474462 mm/s at 12 RPM.

`tests/test_rack_geometry.py` compares these independent published examples,
solves the literal common-normal relative-velocity equation on an independently
constructed involute, compares rack flank positions/normals, and exercises actual
shared moving meshes with wrong-direction collision controls. It also covers
the zero-helix limit, closed solids, bores/end planes, signed/stationary RPM,
retained geometry/continuous poses, invalid geometry, projects, worker parity and
standalone STEP/STL/profile exports. Native and browser checks are separate from
these equations and sampled-solid tests.
