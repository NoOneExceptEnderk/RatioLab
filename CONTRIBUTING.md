# Contributing to RatioLab

Use English for contributor documentation, code comments and docstrings. Keep
changes focused and describe the behavior changed, its limits and the checks
actually run. See [development guide](docs/development.md) for Python and native GTK setup.
Code contributions use GPL-3.0-only; see [LICENSE](LICENSE).

## Repository layout

- `src/` contains the application modules, which retain their top-level import
  names. `src/ratiolab_resources/` holds the runtime catalogs and branding.
- `tests/` contains the test suite and is included only in source distributions.
- `docs/` contains user, installation, development and technical documentation.
- `scripts/`, `packaging/` and `build-support/` contain distribution tooling.
  The build copies the canonical documentation and legal notices into the wheel.
- Local exports, preferences, credentials, agent notes and working directories
  stay outside published source and build artifacts.

Module filenames below refer to `src/`.

## Architecture and ownership

- `geometry.py` validates parameters and builds `Design`/`Part` objects. Family
  construction lives in `assemblies.py`, `geartrains.py`, `special_drives.py`
  and related geometry modules. `engineering.py` and `kinematics.py` calculate
  nominal results and member speeds; the GUI displays those results.
- `app.py`, `*_ui.py`, controls and `preview3d.py` own GTK widgets, user actions
  and rendering. Keep GTK/OpenGL imports out of the headless geometry,
  analysis, persistence and export modules.
- `project_document.py` owns document history and recovery data;
  `project_ui.py` connects it to the desktop. `ratiolab_agent.py` exposes
  workspace-confined headless operations and `ratiolab_mcp.py` adapts them to
  stdio MCP. See [MCP guide](docs/mcp.md) for the public service contract.
- Export modules consume generated designs. `selected_export.py` copies an
  explicit subset; regenerating that subset would reintroduce omitted parts.
  `connection.py` handles the optional SolidCraft connection.

## Geometry conventions

Lengths and world coordinates are in millimetres. Parameter fields such as
pressure, helix and `Part.twist` use degrees; trigonometric helpers, profile
phase and motion phase use radians. `profile_sections()` returns section
angles in degrees, converted at the surface boundary. Operating quantities
use N, N·m, rpm and W; the signed transmission ratio is input speed/output
speed. See [calculations](docs/technical/calculations.md), [kinematics](docs/technical/kinematics.md)
and [io models](docs/technical/io-models.md) before changing those conventions.

`Part` contours are local XY loops. Width and section levels run along local
Z before placement by `solid_geometry.point()`. Preserve loop correspondence
between adjacent sections and the outer/hole winding enforced by
`section_loops()`. `Design.parts` order supplies internal zero-based indices
for motion, picking and controllers. Export source positions are one-based;
selected exports retain their original positions through `source_indices`.
Part names also identify constructed members in some motion and interface
rules, so changes to names or ordering need more than a display review.

`profile_sections()` and `solid_geometry.faces()` define the shared sampled
surfaces used by preview, STL, picking and interference. Keep one geometry
path. Standalone STEP may promote circles/cylinders only when explicit
`CircleProfile` construction provenance is intact and its placement qualifies;
an arbitrary polygon that happens to be equiradial is insufficient. Analytic
STEP bounds and sampled mesh bounds can therefore differ slightly. Sampling
thresholds describe numerical construction, not manufacturing tolerances.
See [variants](docs/technical/variants.md) for the worm and strain wave study limits.

## Preserve these invariants

- Keep normalization in the generator: I/O compatibility and printed-shaft
  preparation precede variant/style handling; bearing catalog dimensions then
  hardware dimensions are resolved before numeric and geometric validation.
  Derived dimensions must reach every consumer through the validated design.
- Finish pending edits and normalization before taking an asynchronous
  snapshot. Worker threads receive copied data and return through GTK's main
  loop. Check document identity/revision, run serial and current snapshot before
  accepting callbacks or applying a proposal; cancellation alone cannot reject
  a late answer from a non-preemptible operation.
- Interference checks are discrete, conservative surface checks. Keep expected
  interface labels separate from pair testing; they never suppress a collision.
  Report unsupported deformation, unresolved contact and incomplete coverage.
  A sampled clear result is not a continuous-motion or strength guarantee.
- Combination search enumerates explicit finite grids, keeping all other
  normalized parameters fixed. Revalidate generated candidates and report
  resource-limited runs as partial. Ranking is limited to that finite domain.
- Use `export_transaction.py` for staged export publication. Writers complete
  inside a sibling staging directory before publication; existing export
  directories are not replaced. Keep package references relative so moving a
  package preserves its assets. Use the document persistence helper for JSON
  files that intentionally replace a prior version.
- MCP stdout carries protocol messages only. Preserve bounded input/work queues,
  cooperative cancellation, explicit project revisions and workspace path
  checks when adding a tool. The headless service must remain usable without
  GTK, a display, a CAD installation or network access.

## Verification

After setting up the source environment in the [development guide](docs/development.md),
run relevant tests from the repository root, then the complete suite:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_geometry.py'
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'
```

Use the interpreter that can load the installed native bindings. GUI and
OpenGL checks need a working desktop or the supported test display setup;
report skips and unavailable graphics explicitly. Run desktop checks in the
normal application environment; use software-rendering overrides only when
deliberately verifying that configuration. Add regression coverage for changed
behavior and describe the checks and relevant limitations in your pull request.
