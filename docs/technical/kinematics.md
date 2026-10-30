<a id="modalità-cinematica"></a>

# Kinematic mode

Above the 3D viewer, **Start motion / Pause** and **Initial pose** are directly accessible. Press the speed-value button and **Adjust**: a compact CAD-style palette opens, with a grey header, close button, status, **Start / Pause / Resume**, return to the initial pose and an **Input RPM** slider. It stays open while you orbit the model; closing it does not stop motion. Details are expandable.



Playback uses the actual RPM: 60 rpm corresponds to one input revolution per second. Ratios and directions remain those of the selected arrangement. At high speeds, screen sampling can make teeth appear stationary or reversed: lower the RPM to inspect motion. With all inputs at zero, the model stays still.



Invalid parameters stop animation; correct them to restart it. Start disables the exploded view. Camera, section and visibility remain available during motion.

<a id="movimenti-rappresentati"></a>

## Represented motions

- Gears, trains, worm and reducers: member rotations with their own speeds and axes.
- Cycloidal: eccentric orbit and disc rotation. The disc is an internal orbiting member, even when the output is fixed.
- Harmonic: prescribed flexspline deformation with uniform pitch along the elliptical arc and teeth oriented along the local normal, oriented by the wave generator, with material rotation and the cup bottom rigidly connected to the flange. This does not represent an elastic analysis.


<a id="esportazione"></a>

## Export

Animation changes only preview rendering: geometry, parameters, bill of materials and CAD commands retain the assembly pose. STEP and STL remain consistent with the nominal model. **Export files… → Complete package** restores the initial pose before also saving the PNG.

This is a kinematic visualisation: it does not check collisions throughout the cycle, conjugate contact, loads, elasticity, friction or life; it does not create animated joints in the SolidCraft document.

The generated strain-wave ring and its discrete moving-surface checks are described
in the [strain-wave reference](strain-wave.md). Starting animation alone does not
run interference checks.
