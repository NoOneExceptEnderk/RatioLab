# Autodesk Fusion integration

RatioLab can send the current model directly to an open Autodesk Fusion design.
The **CAD integrations** menu contains separate SolidCraft and Fusion controls.
Fusion uses the included **RatioLabBridge** Python add-in and a local authenticated
connection. No cloud upload or external Python installation is needed by the bridge.

The updated Windows and Linux installers include this integration. Live Fusion
2705.1.30 imports have been tested on Windows. Linux can connect to community
Wine ports as described below. Native macOS Fusion and Fusion-under-Wine
validation remain pending; a successful application CI check does not establish
Fusion interoperability on those platforms.

## First connection

1. Start Autodesk Fusion and open an editable design. Recent Fusion versions offer
   **Hybrid design**, which supports the internal components created by RatioLab.
2. In RatioLab, open **CAD integrations → Install Fusion add-in**. The status line
   shows the installation folder.
3. In Fusion, open **Utilities → Scripts and Add-Ins**. Run **RatioLabBridge**.
   If Fusion was already open and the add-in is missing from the list, choose
   **+ → Script or add-in from device** and select the installed `RatioLabBridge`
   folder. Optionally enable **Run on startup** in Fusion.
4. In RatioLab, choose **Connect / check Fusion**, then **Create in Fusion**.
   Finish any active sketch or command in Fusion before sending.

The add-in is installed per user:

- Windows: `%APPDATA%/Autodesk/Autodesk Fusion 360/API/AddIns/RatioLabBridge`.
- macOS: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/RatioLabBridge`.
- Linux/Wine: the selected Wine user's Windows add-in folder inside `drive_c`.

Stop the add-in before updating it, then run it again. RatioLab preserves add-in
files that have been edited locally rather than silently replacing them.

## Linux with Fusion under Wine

Run the native Linux version of RatioLab alongside your existing community
Fusion installation. Use the same **Install Fusion add-in**, **Connect / check
Fusion** and **Create in Fusion** commands. RatioLab does not install or change
Wine, Fusion, graphics drivers or the port's launch scripts.

Common prefix locations are detected, including the
[cryinkfly installer](https://github.com/cryinkfly/Autodesk-Fusion-360-for-Linux)
layout `~/.autodesk_fusion/wineprefixes/default`, its legacy
`~/.fusion360/wineprefixes/default` layout, and the Wine Flatpak prefix at
`~/.var/app/org.winehq.Wine/data/wineprefixes/fusion360`.
For a custom Wine/Proton/Bottles installation, or when multiple installations
are found, explicitly select the existing prefix when launching RatioLab:

```sh
RATIOLAB_FUSION_WINEPREFIX="/absolute/path/to/prefix" ratiolab
```

For the default bundled `.run` installation, replace `ratiolab` with
`"${XDG_DATA_HOME:-$HOME/.local/share}/ratiolab/app/RatioLab"`; for a Debian
package, use `/opt/ratiolab/RatioLab`. `WINEPREFIX` is also accepted.
If the prefix has several Windows user profiles, select the actual Fusion
profile with `RATIOLAB_FUSION_WINEUSER`, using the directory name under
`drive_c/users`. Missing or ambiguous installations produce a setup message;
RatioLab does not choose an arbitrary profile.

The add-in and its session endpoint live inside the selected prefix's Windows
user profile. Transfers retain the original export package and stage a second
verified copy under that profile's `AppData/Local/RatioLab/fusion-imports`.
Fusion receives a Windows `C:\users\...` path, so disabled Z: mappings and
Wine filesystem sandboxing do not require exposing the Linux export directory.
Both programs must share localhost networking and the host must be able to
read and write the selected prefix. Keep the staged package until import finishes.

Automated tests cover prefix selection, paths and authenticated transfer.
They do not establish that every Wine/Proton version or community Fusion port
can run the Fusion SDK. No platform check blocks Linux users from trying it.

## What Fusion receives

Each send creates a unique top-level RatioLab component in the active document,
with individual child components in their nominal assembly positions. The bridge
imports **STEP BRep solids**, checks their solid status, dimensions and volume in
millimetres, and applies the preview's support/housing visibility. Component names,
roles, source parameters, RGB metadata, notes and the bill of materials accompany
the imported model. Existing Fusion objects remain in the document.

The parameter definitions remain editable in RatioLab. Imported STEP solids do
**not** reproduce RatioLab's generation logic as native Fusion timeline features,
constraints, joints or an automatically regenerating parameter table. Change the
RatioLab model and send again to create another component. Sampled teeth and
freeform surfaces retain the approximation limits described in the calculation
and STEP export reports.

RatioLab retains a `fusion-<family>-<uuid>` transfer folder in the export directory,
including hashed component STEP files, a manifest, parameter JSON and BOM files.
Keep it until Fusion finishes importing. Fusion documents are saved by Fusion;
the integration does not automatically save or upload them.

## Failure handling

An active-document change, sketch editing or another command rejects the import
before modelling. The bridge verifies the package before importing and removes
only its newly created RatioLab group if an import or geometry check fails.
If cleanup cannot be confirmed, the error asks you to inspect the Fusion document.

A connection timeout can occur while Fusion is still processing. Inspect Fusion
before sending again: an explicit second send creates a new group. The bridge
keeps request IDs for its running session so the same request cannot import twice.

The bridge listens only on `127.0.0.1`, chooses an available port and keeps its
session credential in the user's RatioLab data directory. It accepts status and
verified model-import requests; it does not expose arbitrary Python execution.
Stopping the add-in closes the listener and removes its session endpoint.

Fusion's SDK runs within Fusion; all CAD calls are dispatched to its main thread
using Autodesk's [CustomEvent mechanism](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/CustomEventSample_Sample.htm).
See Autodesk's [add-in installation guide](https://help.autodesk.com/view/fusion360/ENU/?caas=caas%2Fsfdcarticles%2Fsfdcarticles%2FHow-to-install-an-ADD-IN-and-Script-in-Fusion-360.html)
for the host application workflow.
