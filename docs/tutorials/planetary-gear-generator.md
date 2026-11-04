# Planetary gear generator: a 4:1 worked example

Generate a planetary gear set with RatioLab, inspect its motion and export the
geometry as STEP or STL. This free, open-source example works in the browser
and in the desktop app. The project below contains the actual parameters used
for this guide, so you can start with a complete design.

[Download the planetary project](../../examples/planetary-browser-guide.config.json)
or [open the web app](https://ratiolab.dev/app/).

![Generated top-view profiles of an 18-tooth sun, three 18-tooth planets and a 54-tooth internal ring. Supporting parts are hidden.](../../assets/planetary-guide.svg)

## Open the example

1. Download the project JSON using the link above.
2. Open RatioLab in your browser, or launch the desktop app.
3. In the browser, choose **Project → Open project…** and select the JSON file.
   On desktop, use **Open project**. Save any existing work before replacing it.
4. Inspect the generated planetary assembly. The illustration above hides the
   supporting parts to make the gear profiles easier to see; the project retains
   the complete model.

## Understand the parameters

| Parameter | Example value | What it controls |
| --- | --- | --- |
| Construction | Single stage, spur | One planetary stage with straight teeth |
| Sun teeth | 18 | Teeth on the central input gear |
| Planet teeth | 18 | Teeth on each planet |
| Number of planets | 3 | Equally spaced planet gears |
| Ring teeth | 54, derived | The internal ring for this sun and planet combination |
| Module | 2 mm | Nominal tooth size |
| Face width | 10 mm | Axial width of the gears |
| Input speed | 60 rpm | Prescribed speed of the sun |

For this single-stage arrangement, the ring tooth count is derived from
`18 + 2 × 18 = 54`. With the ring fixed, sun input and carrier output, the ideal
reduction is `1 + 54 / 18 = 4`. The carrier therefore turns at **15 rpm** for a
60 rpm sun input, in the same direction about the common axis.

## Preview and change the design

Use the motion controls to play and pause the mechanism. Orbit the model to see
the sun, planets and carrier. The carrier carries the planet axes around the sun;
the planets also spin about their own axes.

As a first edit, change the module from **2 mm to 2.5 mm**, keeping the tooth
counts unchanged. The gears become larger, while the ideal **4:1** reduction stays
the same. Review the regenerated model and any validation messages before export.

## Export STEP or STL

Choose **Export** and select the available STEP or STL option. STEP is useful for
continuing the design in CAD; STL exports the triangulated surfaces. Check the
component selection and scope in the export dialog before saving.

You can also save the modified project as JSON and reopen it later in RatioLab.
The [user guide](../user-guide.md) explains project handling and export options;
the [browser guide](../web-app.md) covers browser requirements and limits.

## What this example establishes

This is nominal gear geometry with prescribed, ideal kinematic motion. Its ratio
does not establish a load rating, service life or manufacturing readiness.
See the [calculation references](../technical/calculations.md) and
[motion conventions](../technical/kinematics.md) for the model's scope.

Continue with the [cycloidal drive example](cycloidal-drive-generator.md) to
explore a different way to obtain a reduction.
