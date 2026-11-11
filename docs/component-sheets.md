# Component production and inspection sheets

The desktop app can export two printable A4 PDFs for one selected component.
This feature describes the current source tree; an existing installation or
hosted browser can contain an earlier version.

Try the [demonstration project](../examples/spur-component-sheets.config.json)
to inspect a filled sheet. Its company and example axial limits are illustrative
entries, not recommended specifications for a physical part.

## Create a component sheet

1. Open **Tools → Components / measure… → Parts** and select exactly one part.
2. Choose **PDF sheets…** (production / inspection).
3. In **Production**, enter the company, customer, order and author. These four
   fields are shared by the component sheets in this project. Enter the selected
   part's code, drawing revision/reference, lot and quantity, material, blank,
   treatment, finish, operations and notes as required by your company.
4. In **Inspection**, review the automatically listed characteristics. Enter
   absolute minimum and maximum limits, method, instrument ID and datum/drawing
   reference. A blank limit remains undefined; RatioLab does not infer limits
   from display precision, backlash or surface interpolation settings.
5. Add company characteristics when the drawing requires other checks. Their
   names, nominal values, units, limits and methods are company-authored data.
   Remove a custom characteristic with its **Remove characteristic** button.
6. Choose **Apply to project** to store the entries, or **Export PDFs** to apply
   them and export both documents. **Cancel** and the window close button discard
   unapplied edits. Save the project with **File → Save** to retain applied data
   in its JSON file.

Applied fields participate in project dirty state, undo/redo and interrupted
session recovery. New/opened projects receive their own fields. The editor
rejects an Apply if another action has replaced or changed its document.

## Exported files

The normal exports folder receives a new component directory containing:

- `production.pdf`: project/part identification, company specifications,
  supported nominal dimensions, a reference profile where available, and the
  company's operations, notes and production release space.
- `inspection.pdf`: identification, the listed characteristics and limits,
  contact setup, instrument/datum fields, three blank reading cells per
  characteristic, disposition and review spaces.
- `sheet-data.json`: the exact input snapshot, document revision, geometry
  fingerprint and UTC generation timestamp for that export.

PDF headings, instructions and automatically generated characteristic names and
contact descriptions follow the interface language selected when **Export PDFs**
is pressed. The chosen language is recorded as `language` in `sheet-data.json`;
changing the interface while export runs does not change that export. This does
not change the project's company data or the language policy of other reports.
Company text, custom characteristics, notes, instrument/drawing references and
numeric values are preserved as entered, with Unicode font fallback. The PDFs are
printable documents; company fields are edited in RatioLab, rather than PDF form
widgets. The three reading cells can record repeat readings or samples identified
by the company; no sampling plan is prescribed and no pass/fail is calculated.
Both PDFs and their snapshot publish together. An export failure leaves no
partially completed directory, and existing exports are never replaced.

## Automatic dimensions and supported measurements

The production sheet also includes available tooth counts, normal module,
pressure angle, helix-angle magnitude, profile shift and theoretical reference
diameter. These descriptive data are not automatically added as acceptance checks.

Only dimensions with existing construction provenance are listed automatically:

- Local axial sweep/station length for parts without an explicit mesh.
- Circular-hole diameters where intact analytic circle provenance is retained.
- Tooth-tip diameter for supported cylindrical involute profiles.
- The recommended Wildhaber span when an existing usable span is available.
- The existing theoretical over/between-gauge dimension when supported.

Calculated nominal dimensions and contact setups cannot be overwritten in the
editor. The original profile supplies the number of teeth for a span and the
diameter/type and arrangement for gauge measurements. The default gauge diameter
is theoretical; it is not a selected commercial instrument. Approve physical
access and contact setup against the company drawing. A company-specific gauge
setup can be documented as a custom characteristic using independently approved
nominal data. See [gear metrology](technical/calculations.md) for domains and
limitations. No missing measurement is synthesized for an unsupported family.

A profile reference is the component's local XY contour or its first explicit
section. It is not an orthographic, dimensioned manufacturing drawing, and it
does not define a datum system. Company specifications and approved drawings
remain responsible for manufacturing requirements and acceptance criteria.

## Geometry changes and project exchange

Component entries are associated with their family and source component name.
They retain the normalized source geometry fingerprint reviewed at Apply. A
geometry/configuration change retains those entries but requires review and a
new Apply before export; the dialog explains this and refreshes automatic nominal
values. Disappeared automatic characteristics are not carried into a new sheet.
Speed-only and preview/export interpolation changes do not require this review.
Switching to another component never transfers its individual specifications.

The optional top-level `component_sheets` field is preserved in JSON project
save/open, desktop packages, the current browser import/save and headless MCP
open/update/history/save. Browser and MCP preserve it without providing the
desktop sheet editor or PDF export action. Older versions may ignore this field;
retain the original project before exchanging it with an older application.

The feature adds no process planning, tolerance selection, gear quality grading,
strength assessment, measurement certification or standards-conformity claim.
Material, treatments, operations and limits are company-entered specifications,
not calculations performed by RatioLab.
