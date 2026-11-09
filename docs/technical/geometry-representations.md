# Nominal geometry and representations

Each Design owns one ordered list of nominal Part constructions, from the
validated mechanical parameters. Dimensions, kinematics and engineering checks
use that source. Preview and export select their own sampled representation of
the same construction, without rebuilding mechanical geometry.

The current construction description includes local sampled transverse contours,
twist and groove landmarks, or explicit stations/mesh faces and placement. This
separation does not turn those inputs into exact theoretical CAD surfaces.
The existing transverse profile construction and accepted nominal equations are
unchanged. An [opt-in external-spur curved CAD prototype](curved-cad-prototype.md)
now evaluates continuous construction curves separately. It does not replace the
ordinary exports or qualify other families; a global engine error budget remains
separate development work.

## Independent policies

An optional project-level quality object contains preview_mm and export_mm.
Each value must be a positive finite number in millimetres. Omitted keys inherit
Part.surface_tolerance_mm, normally 0.02 mm. Existing projects with no quality
object retain that behavior. Quality is stored outside the mechanical parameters.

These are procedural sweep interpolation requests, with the scope and bounds in
[surface accuracy](surface-accuracy.md). They do not change tooth clearance,
module, dimensions, transverse profiles or solver/validity criteria. Explicit
station/mesh constructions retain their existing data and report not_evaluated
for the continuous sweep bound. There is no product floor of one micrometre;
smaller requests can be entered, but may exceed resource or numerical limits.
An exhausted resource budget produces an error rather than an accepted coarser
result. This setting alone does not establish total gear or manufacturing accuracy.

For example:

    from geometry import generate
    from geometry_quality import with_quality, representation, report, project

    nominal = generate('helical')
    configured = with_quality(nominal, dict(preview_mm=.1, export_mm=.005))
    assert configured.parts is nominal.parts
    preview = representation(configured, 'preview')
    output = representation(configured, 'export')
    quality_record = report(configured, 'export')
    saved_project = project(configured)

with_quality retains the source parts, exact dimension sources, analysis,
selected-source indices and construction token. A representation only changes
its interpolation policy; the Rust boundary freezes its geometric input into an
owned snapshot. Cache identities include that policy. A request cannot reuse a
surface sampled under another threshold.

## Consumers and persistence

- Native and browser preview use preview_mm. Surface picking follows that same
  displayed policy, so selection tests the visible mesh. Surface point
  measurements consequently describe the sampled preview; they are not exact
  CAD or minimum-clearance measurements.
- Nominal dimensions, source engineering analysis and interference checks retain
  the canonical Part construction policy. Preview detail does not weaken or
  alter those checks. The existing analysis surface_sampling record describes
  this reference policy, not every possible preview or export.
- STEP, STL, section exports and SolidCraft STEP assets use export_mm. Selected
  exports retain original source indices. CAD profile metadata queries the
  actual export snapshot. Export packages include geometry-quality.json;
  quality-configured STL exports also include it in the component folder.
- An export-only edit retains preview mesh/GPU buffers. A preview edit rebuilds
  the representation while keeping nominal construction, camera and motion phase.
  Surface points/measurements are invalidated when their sampled representation
  changes. Document/revision guards reject late asynchronous replies.
- Desktop save/open, undo/redo and recovery preserve quality. Browser documents
  and projects do the same. Legacy projects remain valid.

Desktop controls are in Export > Surface detail. Browser controls are in
View > Surface detail and the Export dialog. Presets Fast (0.1 mm), Standard
(0.02 mm) and Fine (0.005 mm) are conveniences; editable fields accept custom
values. Blank fields inherit the part policy. The labels describe interpolation
detail, not manufacturing grades.

Export geometry is generated when requested. Saving a very fine export request
does not allocate that mesh or prove that it can be produced. Failure leaves no
partially published export. Desktop preview edits are prepared transactionally;
the browser retains a visibly stale last valid preview on an unachievable request
and blocks export until the document is valid again.

## APIs

Python generate accepts an optional quality keyword. Existing lower-level
writers that accept Parts directly retain their explicit per-part policy;
Design-based writers select export quality automatically.

Browser generate/import_project accept the project quality object. The quality
RPC takes design_id and quality, validates a new representation and advances
the design lease without reconstructing the nominal assembly. Export-only
updates return buffers_retained. Failed requests retain the accepted source.

MCP project_create and project_update accept optional quality; it is a complete
replacement of the representation overrides, while parameters remains the
mechanical patch. Project update, history, save/open and exports preserve it.
Quality-only updates retain nominal Parts and use the same revision checks.
