# Desktop preferences

Open **Settings** in the toolbar or press **Ctrl+,**. The left sidebar contains
**Appearance**, **Controls**, **Model precision** and **General**. Workspace
preferences apply immediately and belong to the user profile. Model precision
belongs to the current project and requires **Apply**; closing before applying
leaves the project's accepted precision unchanged.

This page describes the desktop Settings editor in the current source tree.
The browser has its own [theme/language controls](web-app.md#use-the-workspace)
and does not offer the desktop theme-file editor or customizable CAD presets.

## Appearance

1. Select **Dark** or **Light** under **Color mode**. Appearance controls are
   collected here; the main toolbar has no separate Theme switch.
2. Choose a preview card: **RatioLab**, **Slate**, **Nord** or **Warm**.
3. Expand **Interface colors** or **3D view colors** to customize that palette.
4. Use a color picker or enter `#RRGGBB`. Press Enter or leave the field to
   confirm typed text. Invalid text shows an error and leaves the accepted color.

Interface roles cover the window, panels/buttons, input fields, primary and
secondary text, accent color and dividers. Related hover/focus colors are
derived by the editor. View roles cover background, grid, orientation labels
and selected-component highlighting. Model part colors retain their existing
meaning.

The app remembers the selected palette independently for dark and light modes.
Edits also belong to one **mode and preset**: changing a dark Nord color does
not alter light Nord or the other presets. Switching palettes preserves edits.

| Reset action | Result |
|---|---|
| Arrow beside a color | Remove that color's override for the current mode/preset. |
| **Restore preset colors** | Remove all overrides for the current mode/preset. |
| Reset on an imported palette | Return to its imported baseline colors. |

Choose **Text size** at 100%, 125% or 150% to enlarge interface text. Long
parameter lists and Settings pages scroll; this setting does not scale model
dimensions, the export units or the operating speed.

## Export and import a theme

**Export theme…** saves the palette currently displayed, including its edits,
as a local JSON file. **Import theme…** opens a RatioLab theme file, activates
its declared light/dark mode and makes it the imported palette for that mode.
There is one imported palette slot per mode; importing another theme for the
same mode replaces that slot and its edits. Export a palette first if you want
to retain a separate copy.

The file chooser appears inside Settings. Choose a local file and **Save** or
**Open**, or **Cancel** to return without a file operation. Theme files contain
appearance colors; they do not transfer keyboard bindings, mouse navigation,
text size, language, project geometry or operating data.

The format identifier is `ratiolab-theme/1`. It records a name, `dark`/`light`
mode, interface `colors` and `viewport` colors. Unknown fields, unsupported
color names, invalid colors or a file larger than 128 KiB are rejected before
replacing the active imported palette. Use the editor's export for a complete
file; a RatioLab project JSON is a different format.

## Controls

**Apply preset** sets both the keyboard map and mouse navigation to RatioLab,
FreeCAD, Fusion, SOLIDWORKS, Inventor or SolidCraft. Choosing a preset in the
list alone does not apply it. These adapt shared commands and gestures; they
do not reproduce every behavior of the named CAD programs.

Choose **Mouse navigation** separately to keep your custom keyboard bindings.
The description shows the active orbit/pan/zoom gestures. Zoom and orbit
sensitivity each offer 0.5×, 1× and 2×; **Invert zoom direction** reverses wheel
zoom. Applying a preset preserves these sensitivity and direction choices.

Click a shortcut row to record keys. **Apply** confirms a valid assignment;
closing the recorder or pressing Escape cancels. View commands can use a
two-key sequence. Duplicate keys, reserved keys and overlapping sequence
prefixes are rejected. Per-command reset restores that command's active
preset binding; **Clear shortcut** disables it. **Restore RatioLab controls**
resets both keyboard and mouse mappings while retaining sensitivities.
See the [complete gesture tables and key rules](keyboard-shortcuts.md).

## Model precision and geometric deviation

Choose **Fast**, **Standard** or **Fine** in the comparison table to fill both
interpolation fields. Their requested thresholds are **0.1 mm (100 µm)**,
**0.02 mm (20 µm)** and **0.005 mm (5 µm)**. **Part default** clears both
overrides. Edit **Preview** and **Export** independently for custom values;
blank fields inherit each part's existing construction policy. Press **Apply**
to accept the change. Export-only changes retain the displayed mesh. Preview
changes prepare a new mesh while preserving nominal parameters and parts.
The project, Undo/Redo and recovery retain both settings.

Bounds are calculated asynchronously for the current model, each preset, part
defaults and both draft fields. Viewing or comparing them does not edit the
project. The comparison separates:

- **Requested interpolation**: the chosen threshold, not a total accuracy claim.
- **Sweep error bound**: the verified surface-interpolation bound relative to
  the existing sampled contours. Straight extrusion can have zero sweep error
  while the tooth-profile error remains nonzero.
- **Complete model bound**: a verified complete boundary-surface bound before
  rendering/file conversion, only for constructions covered by the existing
  [error-budget audit](technical/geometric-error-budget.md). **Not bounded**
  means that no verified complete bound is available, rather than zero error.

Displayed upper bounds round upward and show millimetres and micrometres.
For example, the default straight gear retains a complete model bound of about
0.01517 mm at all three presets: its fixed transverse profile is independent of
the sweep threshold. Fixed meshes/stations and other sampled profiles likewise
retain their existing construction. Lower requests can create much larger meshes;
the existing face limits and refusal behavior remain in force.

Expand **Precision limits** for scope. These values describe geometric
approximation, not elastic deformation, load capacity or manufacturing
tolerances. STL/preview coordinate conversion and STEP exchange have separate
qualification; no complete STEP error is asserted here. See
[surface representations](technical/geometry-representations.md) and the
[OCCT explanation of linear mesh deflection](https://www.occt3d.com/dev/doc/overview/html/occt_user_guides__mesh.html)
for the distinction between tessellation controls and geometric construction.

The existing **Export > Surface detail** entry opens the same editor and
comparison; it does not define a second precision policy.

## General and persistence

**Language** changes interface text; parameter keys, units and saved project
identifiers remain canonical. **Parameter hover help** controls passive help;
the information buttons and **F1** remain available when hover help is off.
**Release notes and updates…** opens the existing [desktop update flow](updates.md).

Preferences are saved in `ui-preferences.json` in the platform's
[user configuration directory](development.md#user-data-and-existing-configurations).
A write failure keeps accepted settings usable for the current session and
shows a save notice. Closing Settings does not roll back those session choices.
Save a model with the normal project commands; exporting a theme does not save
the current design.
