# Desktop keyboard and mouse controls

Open **Settings → Controls** to select a preset or record your own keys. Changes
apply immediately and are saved separately from projects. Applying a preset
replaces both the active key map and mouse navigation. You can select **Mouse
navigation** independently to keep your custom keys. Individual reset buttons
restore that preset's key assignment. Clearing a command disables its shortcut.
**Restore RatioLab controls** resets both mappings. Sensitivities and the zoom
direction are preserved. Existing profiles without a mouse preference retain
RatioLab navigation until a preset or mouse profile is explicitly selected.

Project commands use a modifier such as Ctrl/Alt or a function key. View commands
can use plain keys or two-key sequences and work when the 3D preview or cube has
focus. This keeps letters and numbers available for parameter entry. Escape,
F1, text editing/navigation keys and the existing Alt+1/2/3 tool shortcuts remain
reserved. Duplicate assignments and overlapping sequence prefixes are rejected.
The recorder suspends application shortcuts while listening. Closing it without
Apply keeps the previous assignment. A failed preference write keeps the new
keys usable for the session and displays the normal preference-save notice.

## CAD-inspired presets

These presets adapt shared commands. Mappings not listed below retain RatioLab
defaults; they do not imply that the CAD applications have those defaults.
All CAD presets use Ctrl+Y for Redo; RatioLab also accepts Ctrl+Shift+Z by default.
The documented Windows combinations are used for these desktop presets.

| View command | RatioLab | FreeCAD | Fusion | SOLIDWORKS | Inventor | SolidCraft |
|---|---|---|---|---|---|---|
| Fit model | F | V, then F | F6 | F | Home | F6 |
| Isometric | Home | 0 | — | Ctrl+7 | F6 | Ctrl+7 |
| Front | 1 | 1 | — | Ctrl+1 | — | Ctrl+1 |
| Back | 2 | 4 | — | Ctrl+2 | — | Ctrl+2 |
| Left | 4 | 6 | — | Ctrl+3 | — | Ctrl+3 |
| Right | 3 | 3 | — | Ctrl+4 | — | Ctrl+4 |
| Top | 5 | 2 | — | Ctrl+5 | — | Ctrl+5 |
| Bottom | 6 | 5 | — | Ctrl+6 | — | Ctrl+6 |

The view names refer to RatioLab's existing Z-up camera directions. Numeric
and named keys remain distinct; key sequences allow up to 1.2 seconds between
strokes. Changing focus or the key map cancels a pending sequence.

## Mouse navigation

Middle means pressing the scroll wheel as a button. Drag while holding the
indicated button and modifiers. Scrolling the wheel zooms in every profile.

| Preset | Orbit | Pan | Zoom |
|---|---|---|---|
| RatioLab | Left drag | Right drag | Wheel |
| FreeCAD (CAD) | Hold middle, then hold left or right and drag | Middle drag | Wheel |
| Fusion | Shift + middle drag | Middle drag | Wheel |
| SOLIDWORKS | Middle drag | Ctrl + middle drag | Wheel or Shift + middle drag vertically |
| Inventor | Shift + middle drag | Middle drag (also Ctrl + middle) | Wheel |
| SolidCraft | Right drag or Shift + middle drag | Middle drag | Wheel |

For FreeCAD's right-button alternative, orbiting can continue after releasing
the middle button while keeping the right button held. The **Pan** tool allows
left-button panning in every profile. The orientation cube keeps its direct
click/drag controls, and double-click in the preview still fits the model.

These profiles adapt the principal mouse gestures to RatioLab's existing camera;
CAD-specific pivot selection, snapping and other navigation modes are not
replicated. Navigation changes only the view, without editing geometry, motion
parameters or project history.

## References

- FreeCAD's official documentation: [Fit all](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Std_ViewFitAll.md),
  [Isometric](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Std_ViewIsometric.md)
  and [3D navigation](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Manual_Navigating_in_the_3D_view.md).
  Mouse gestures use its default [CAD navigation style](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Mouse_navigation.md).
- Autodesk Fusion: [shortcut guide](https://www.autodesk.com/shortcuts/fusion-360)
  and [Fit in the Design workspace](https://help.autodesk.com/view/fusion360/ENU/?caas=caas%2Fsfdcarticles%2Fsfdcarticles%2FHow-to-Zoom-to-fit-to-an-assembly-in-Fusion-360.html).
- SOLIDWORKS: [official view shortcut reference](https://blogs.solidworks.com/products/solidworks/how-do-i-manipulate-my-model-view-let-me-count-the-ways/).
  Mouse gestures follow the [middle mouse button reference](https://help.solidworks.com/2025/english/SolidWorks/sldworks/r_Middle_Mouse_Button.htm).
- Inventor: [predefined shortcuts](https://help.autodesk.com/cloudhelp/2026/ENU/Inventor-Help/files/GUID-428B9A8E-E513-44C8-888A-F6048AE89F8E.htm)
  and [shortcut guide, View section](https://www.autodesk.com/content/dam/autodesk/www/campaigns/inventor-resource/Inventor-Keyboard-Shortcuts-Guide.pdf).
  See also [mouse navigation](https://help.autodesk.com/cloudhelp/2025/ENU/Inventor-Help/files/GUID-502A514C-19D6-4BB2-BF1D-EA497BDAAD2C.htm).
- SolidCraft: the installed command catalog returned by `solidcraft-cli commands`
  (`edit.undo`, `edit.redo`, `file.new`, `file.save`, `file.save_as`, `view.fit`
  and `view.front/back/left/right/top/bottom/isometric`), checked 6 November 2026.
  Mouse controls follow the [UI guide](https://docs.solidcraft.io/guide/ui-tour.html)
  and [navigation protocol](https://github.com/tangency-labs/solidcraft/blob/main/docs/control-protocol.md).

Mouse references checked 6 November 2026.
