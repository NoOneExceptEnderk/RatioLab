<a id="modelli-adattati-ai-collegamenti-di-ingresso-e-uscita"></a>

# Models adapted to input and output connections

The **Drive · input and output** panel also modifies the geometric connections of alternative arrangements. The base configurations retain the existing models and compatibility.

<a id="cosa-cambia"></a>

## What changes

| Family | Adaptation of alternative arrangements |
|---|---|
| Planetary, including double-helical | Shafts and retainers that assumed a fixed ring are removed; independent hubs for the sun, carrier and ring. Carrier passages leave the central shaft clear. Old covers that would intersect the new mounts are removed |
| Two-stage planetary | Output of the first stage and input of the second connected by two hubs and an intermediate plate: the connection changes with the selected members. External mounts and fixed members remain independent |
| Single-/double-disc cycloidal | Connections to the eccentric shaft, pin flange and ring housing. Incompatible old shafts and covers are removed for the moving housing. The roller seat follows the ring member |
| Harmonic, cup/flat cup/hat | Flexspline mount only on the bottom/diaphragm or rigid flange; generator shaft and annular ring mount on the open side. The flexible toothed part is not treated as a rigid hub |


<a id="come-leggere-gli-attacchi"></a>

## Reading the mounts

- Orange: input, flange with **4 nominal holes**.
- Green: output, flange with **6 nominal holes**.
- Grey: member to be fixed, flange with **8 nominal holes**.

Hubs touch the face of the indicated member or occupy its bore as a nominal shaft. Coaxial connections use distinct radial bands and axial positions. The extension comes from the family's shaft dimension, where present, or from 8 mm; flanges and walls come from the model dimensions. The geometry follows parameter changes.

When you choose a new arrangement with adapted mounts, **Supports** is enabled to show them. You can hide them again. Preview, STEP, STL and bill of materials use the same solids; JSON and metadata retain the existing arrangement identifiers. The JSON report contains `mount_interfaces`, with member, role, supporting part, axis and dimensions; `interstage_mounting` describes the connection between the two stages.

Alternative planetary and cycloidal arrangements require manual dimensions and automatic hardware disabled: the old standard seats assume a fixed ring. The panel provides a button for switching to manual dimensions.

<a id="limiti-meccanici"></a>

## Mechanical limits

Worm wheel input is checked against the explicit static tooth friction and
reference-cylinder geometry. Known static self-locking requests are refused;
unknown friction remains an explicitly indeterminate ideal relation. Output-driven
strain-wave arrangements require measured hardware breakaway data before a
physical conclusion can be drawn. The shared check also applies to configuration
files and headless operations. See the [criterion and limits](calculations.md#static-worm-backdrivability).

These are **nominal mounts**, not industrial joints already sized for service. The holes are actually present, but do not represent a selection of commercial bolts. Torque transfer between shaft and hub (key, spline, clamping or another method) remains to be defined, together with tolerances, bearings, axial retainers and frame. Contact between two solids does not automatically create a CAD constraint.

Fixed flanges require an external frame; moving housings require suitable supports. Load capacity, fatigue, stiffness and the complete swept envelope are not verified. The geometric check concerns the reference pose.

<a id="riferimenti"></a>

## References

