# RatioLab documentation

Start with the [user guide](user-guide.md), the [planetary tutorial](tutorials/planetary-gear-generator.md)
or the [cycloidal tutorial](tutorials/cycloidal-drive-generator.md).

These guides describe the current source tree. A downloaded installer, a locally
built desktop app and the hosted browser app can contain different changes.
Check the running version and its release notes when a control is missing.
Building a checkout does not update an existing installation or publish the web
app. The [changelog](../CHANGELOG.md) keeps pending changes under Unreleased.

## Find a task

| I want to… | Read |
|---|---|
| Install, update or troubleshoot launch | [Installation](installation.md) · [Updates](updates.md) |
| Choose a model and edit its dimensions | [Workspace and catalog](user-guide.md#workspace) |
| Trim or chamfer cylindrical tooth heads | [Topping and semitopping](tooth-tips.md) |
| Change themes, text size or language | [Desktop preferences](preferences.md) |
| Use CAD-style mouse gestures or assign keys | [Keyboard and mouse controls](keyboard-shortcuts.md) |
| Set speeds, scrub a pose or inspect motion | [Preview and motion](user-guide.md#preview-and-motion) · [Input/output connections](user-guide.md#input-and-output-connections) |
| Save projects, recover drafts or choose an export | [Save, load and export](user-guide.md#save-load-and-export) |
| Follow illustrated Tools exercises in all nine interface languages | [Step-by-step Tools guides](tutorials/tools.md) |
| Measure surfaces or export selected components | [Components and measurements](user-guide.md#components-and-surface-measurements) |
| Prepare production and inspection PDFs for a part | [Component sheets](component-sheets.md) |
| Inspect tooth thickness, spans or gauge dimensions | [Theoretical gear metrology](user-guide.md#theoretical-gear-metrology) |
| Search a finite set of geometric combinations | [Combination search](user-guide.md#find-geometric-combinations) |
| Propose a centre distance for working backlash | [Working-backlash solver](user-guide.md#solve-working-backlash) |
| Check sampled interference | [Interference workflow](user-guide.md#preview-and-motion) |
| Use the browser or exchange desktop projects | [Browser guide](web-app.md) |
| Work with an agent or automate exports | [MCP and headless service](mcp.md) |
| Transfer to CAD | [SolidCraft](user-guide.md#create-in-solidcraft) · [Autodesk Fusion](fusion360.md) |

## Understand a construction

| Topic | Reference |
|---|---|
| Cylindrical, internal and planetary tooth profiles | [Variants](technical/variants.md) · [Fixed internal roots](technical/fixed-internal-root.md) |
| Parallel stages, helices and folded shaft layouts | [Parallel reducers](technical/parallel.md) |
| Compound planet rims and two rings | [Wolfrom / 3K](technical/wolfrom.md) |
| Finite rotary-to-linear travel | [Rack and pinion](technical/rack.md) |
| Cycloidal shaft/cam construction | [Printed eccentric construction](technical/printed-shaft.md) |
| Worm and prescribed strain-wave envelopes | [Worm](technical/worm.md) · [Strain wave](technical/strain-wave.md) |
| Intersecting or offset shaft directions | [Bevel pair](technical/bevel-pair.md) · [Hypoid](technical/hypoid.md) · [Face gear](technical/face-gears.md) · [Differential](technical/differential.md) |
| Nominal dimensions, contact, metrology and assumed loads | [Calculations](technical/calculations.md) · [Kinematics](technical/kinematics.md) |
| Bearings, hardware and drive interfaces | [Hardware](technical/hardware.md) · [Input/output models](technical/io-models.md) |

## Develop or inspect exported geometry

- [Development and native packaging](development.md), [contribution conventions](../CONTRIBUTING.md).
- [Shared native/Wasm Rust kernel](technical/rust-kernel.md) and [application boundary](technical/engine-integration.md).
- [Preview/export representations](technical/geometry-representations.md),
  [surface interpolation](technical/surface-accuracy.md) and [geometric error budgets](technical/geometric-error-budget.md).
- [Mathematical CAD recipes](technical/mathematical-cad-contract.md),
  [curved spur prototype](technical/curved-cad-prototype.md) and
  [curved cylindrical prototype](technical/curved-cylindrical-cad.md).

Construction checks, sampled clearance and nominal calculations have different
scopes. Each reference states its supported inputs and unresolved cases; a
generated model or a clear sampled result does not establish strength, service
life, production-tool feasibility or manufacturing accuracy.
