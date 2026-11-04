# Changelog

Versioned source entries do not imply that downloadable installers are available.
See [GitHub releases](https://github.com/NoOneExceptEnderk/RatioLab/releases) for
published packages and their verification results.

## Unreleased

## 0.2.0 — 2026-11-04

### Added

- Add two- and three-stage parallel-shaft reducers with spur, helical and
  joined/separated double-helical teeth. Provide independent stage-count and
  tooth-type selectors, per-stage dimensions, helix/groove controls, compound
  intermediate shafts and signed planar centre-line turns. Preserve legacy
  variants, shaft-based motion, reverse operation, finite search and exports;
  reject nonmating swept-envelope overlap. Automatic bearing seats and standard
  hardware remain limited to single-stage pairs.

- Add standalone bevel pairs on 90° intersecting shafts with straight,
  logarithmic spiral and circular Zerol-style tooth traces, independent bores,
  reversible ports and shared preview/export surfaces. Use spherical involute
  working flanks with bounded engagement and trace checks. The curved traces
  are custom constructions, not industrial Gleason octoidal cutter geometry.

- Add custom generated hypoid pairs with signed shaft offset, a conjugate pinion
  envelope, reversible ports and shared desktop/browser/export surfaces. Limit
  offset to 6% of the reference distance and refuse unresolved branch, regularity,
  root-wall or connected engagement checks. This is a custom master-wheel system,
  without industrial cutter or strength/manufacturing certification.

- Add finite rack-and-pinion drives with spur, helical and joined/separated
  double helices. Share surfaces across previews and exports; report linear
  speed, travel per revolution and a conservative finite stroke. Stop animation
  at the stroke limit and preserve position on signed RPM edits. Interference
  sampling covers the finite stroke without claiming a rotary period.

- Add generated face-gear pairs with spur, helical and joined/separated
  double-helical pinions, 90° shaft directions and signed shaft offset. Expose
  radial setting, crest, bore and backing dimensions. Generate the matching
  wheel envelope and joined pinion-cusp transition; trim concave intersections
  and retain independent separated-groove controls and old positive-groove
  projects. Apply envelope, regularity, pointing and bounded engagement checks.
  Equal-count generation, crest and nonworking root relief remain nominal
  constructions, without industrial localization, loaded-contact or strength
  qualification.

### Changed

- Describe browser and desktop gear generation in search and social metadata.
- Add downloadable planetary and cycloidal worked examples, real profile illustrations, and discoverable browser and current model guides.

- Clarify Motion controls in desktop and browser with full-width input/output
  selectors for multi-member mechanisms, distinct fixed-member panels and a
  compact transport/rate bar. Keep all Wolfrom member speeds in Motion details
  beside a visible nominal-output readout; preserve all I/O schemes, rate drafts
  and apply-on-release slider behavior.

- Preview RPM values while dragging the desktop/browser speed slider; apply
  only the final choice on pointer/key release as one Undo step. Preserve the
  applied speed during dragging and confirm pending choices for Save/Export.

- Replace the family dropdown with a searchable illustrated model catalog and
  variant selection before applying. Browse or cancel without changing the
  project; apply a family and its variants as one undoable action in desktop
  and browser. Centre thumbnails on the nominal mechanism without exploded
  padding, and open the catalog through the compact four-square outline icon.

- Integrate direct input/output member cards with the compact sidebar and live
  variant summary. Preserve all supported three-member/stage permutations,
  fixed topologies, physical refusals, precise drafts and history. Keep model
  reset in the Project menu and return desktop launches to the workspace even
  when the optional catalog was previously left open.

- Share compact choice menus across desktop model, motion, I/O, export and tools.
  Preserve search where supported, keyboard navigation and selection models;
  size menus to translated contents, open below their fields and scroll long
  lists within viewport bounds. Browser menus omit repeated titles and close
  buttons; retain the shared palette and active-control highlighting.

- Replace preview axes and the View camera panel with an interactive orientation
  cube in browser and desktop: face, edge and corner snaps, dragging, Home, Fit
  and Pan. Right mouse drag pans without rotating or selecting components.
  Keep section, supports, housing, interaction and continuous explosion in a
  compact Display menu, preserving picking and measurement markers.

- Remove model-header and parameter question-mark icons while retaining
  contextual hover/F1 help, original schematics and native field controls.
  Enlarge the model selector hit area within the existing sidebar. Thicken
  hover-card outlines inward without changing their outer size or palette.

### Fixed

- Keep the illustrated model selector visibly highlighted without hovering in
  both browser and desktop workspaces. Match the compact reference card with a
  60-pixel minimum height, readable name/variant spacing and the existing fixed
  thumbnail, without widening the sidebar.

- Use the approved cube-and-chain icon for CAD connections on desktop and web.

- Align the desktop Initial pose icon with the browser's circular return arrow.

- Keep the Components status summary visible when closing and reopening its
  tool panel, rather than leaving the shared label in the retired panel.

- Include the orientation-cube modules in Python wheels and the CJK font
  collection in source archives. Check lazy local runtime dependencies and the
  complete source font payload, licences and provenance when verifying builds.

- Smooth browser motion using display cadence and one canonical pose request at
  a time. Retain the latest RPM and phase slider edits during worker updates;
  keep continuous slider positions while rounding RPM values and preserve
  explicitly typed precision. Desktop rate edits retain BOM/result widgets;
  phase text no longer refreshes at the model's frame rate.

- Reuse nominal component bounds, BOM identities and component-list widgets
  during RPM-only edits, including heavy paused Wolfrom models. Keep the
  existing 3D frame when a paused speed change preserves its displayed pose;
  invalidate cached details when geometry changes.

### Verification

- Extend installed-runtime catalog checks and agent project round trips to all
  fifteen families, including joined/separated double-helical face gears.

## 0.1.16 — 2026-11-02

### Changed

- Replace Appearance with a direct Theme on/off switch and a Language menu on desktop
  and web. Theme offers light and dark palettes with a contrast symbol;
  Language uses a matching local globe outline on both platforms. Interface
  labels use the nine documentation languages and persist independently of model
  values, numeric precision, projects and history. Bundle Chinese/Tamil fonts.
  Untranslated technical explanations and calculation reports retain English.

- Place compact family/variant controls above the horizontal Dimensions, Motion
  and Assembly navigation bar in the browser and desktop app, without redundant
  Model/Define headings.

- Fit the browser workspace to computer and tablet viewports with internal pane
  scrolling, while retaining natural page scrolling on phones.

- Center parameter information symbols with local vector icons and remove the
  general Help toolbar button.

- Align the desktop and browser workspace with compact paired dimensions, a
  Project menu and a separate history, theme and language toolbar. Give the preview its full
  width, with View and Tools in
  translucent overlays and prominent family-specific results above motion controls.
  Keep analysis tools, component measurements, reports and model notes accessible.
  Use compact numeric fields with units in their labels and adjacent help icons;
  keep paired fields aligned with bundled fonts and enlarged text, with consistent
  disclosure spacing. Use separate icon buttons for View and Tools; keep desktop
  toolbar and tool-list symbols available without relying on system icon themes.
  Align the CAD split action with the workspace preview, then compact the result
  strip and motion controls into two rows while retaining prominent results.
  Keep tools usable with enlarged text and show full status
  tooltips only when their visible text is truncated.
- Add the desktop CAD Connections split button, switching its main action to the
  successfully connected CAD while retaining connection selection and readiness
  checks. Place eligible versioned update notices beside it. Use a compact CAD
  chooser with the complete setup and connection status available separately.
- Replace bulky parameter help with a shared adjacent hover guide, also available
  for Model & dimensions, retaining original schematics and optional expansion.

### Fixed

- Refresh the bundled font cache when its font payload changes, including
  upgrades with normalized installer timestamps, so Chinese and Tamil glyphs
  remain available in existing desktop installations.

- Keep I/O actions, section titles and sidebar navigation within the chosen
  sidebar width, including enlarged text.
- Wait for native frames between panel transitions in the full GUI self-test,
  preventing a Wayland input-context crash during rapid panel checks.

## 0.1.15 — 2026-11-01

### Fixed

- Keep runtime self-tests from mutating the native process environment after GTK
  may have started font workers. Isolate application preferences and exports
  through a temporary Python environment mapping, restoring it on success or
  failure. This removes a demonstrated concurrent environment-read failure
  mechanism in Linux installer preflight checks.
- Run regression checks for environment stability, temporary profile isolation
  and failure recovery in each native platform CI job.

## 0.1.14 — 2026-10-31

### Changed

- Make Update now download, verify, install in the existing location and request
  reopening through the document Save / Discard / Cancel guard. Windows uses
  Setup progress without a wizard; Debian/Ubuntu packages request system
  authorization; writable standard macOS Applications installations use verified
  replacement with a retained backup until runtime checks pass. Unsupported or
  protected installations keep an explicit manual download option.
- Show the current installation type, readable published notes and numbered
  version history in Updates. Keep the development Unreleased section out of
  that history and show the actual update outcome once after reopening.
- Keep export completion visible with its output name and an Open folder action
  bound to that export's destination. Show failures and cancellations inline;
  earlier successful results remain explicitly labelled Last export.
- Expand Components, Search or Check to use the workspace area and restore the
  previous layout without losing component selections or tool inputs.
- Use readable component names in the list and selection summary, retaining
  original names, roles and BOM codes in selected details. Preserve source
  indices, stage/layer distinctions and all exported identities.

### Fixed

- Allow manual release checks from source checkouts and retain an explicit
  automatic-check preference, while respecting disabled checks at launch.
- Protect Linux installation markers and the managed default application folder
  against permissive umasks so the native updater recognizes new and upgraded
  installations. Preserve projects and custom parent-directory permissions.
- Keep component selections and isolated views when changing only RPM. Clear
  revision-bound measurements and discard selections when geometry or the
  document changes.
- Prepare geometry and preview scenes away from the GTK thread for ordinary
  dimension edits. Discard obsolete requests and apply only the latest valid
  document state, keeping controls responsive while preparation finishes.

## 0.1.13 — 2026-10-31

### Added

- Add a nominal two-rim spur Wolfrom / 3K reducer to the desktop and clientside
  browser, with sun input, fixed first ring and second-ring output. Derive the
  second module, validate identical compound-planet clocking and usable paired
  involute contact, and animate signed member speeds with continuous RPM changes.
- Include compound hubs and carrier geometry, precise derived dimensions,
  illustrated parameter help, projects, shared exports and a nominal 600:1
  example. Incompatible Wolfrom drafts retain the last valid model and raw
  input/history while exports and motion stay blocked until repair.

## 0.1.12 — 2026-10-31

### Added

- Add manual desktop update checks with visible progress, up-to-date and error
  results, plus a persistent automatic-check preference. Manual checks can show
  skipped releases and work when automatic checking is off, while respecting
  update policy and GitHub rate limits.
- Add cancellable in-app package downloads verified against the same release's
  SHA256SUMS. Update now prepares a native handoff and uses Save / Discard /
  Cancel before closing for Linux per-user bundle or Windows Setup updates.
  macOS opens the verified DMG; Debian packages use the system installer.
  Source, Python and unmarked portable installations retain manual updates.

## 0.1.11 — 2026-10-31

### Added

- Add persistent Light and Dark desktop themes in View, applied immediately to
  the workspace, dialogs and 3D preview. Changing text size keeps the selected
  theme.
- Replace the desktop preview's Exploded toggle with a continuous Explode slider
  from 0 to 1, with picking at fractional poses and exact preview-state
  restoration. Changing the amount pauses motion and clears measurement points;
  starting motion or choosing Initial pose returns to the assembled pose.
  Geometry exports and package previews retain nominal assembly coordinates.

### Fixed

- Derive planetary ring tooth height and root clearance from the actual mating
  planet profile, keeping the complete nominal contact path on usable involutes.
  Tooth counts, ratios, sun/planet profiles and outer assembly dimensions stay
  unchanged; regenerating older projects intentionally produces the corrected
  inner ring contour. Reports expose the derived geometry and contact ratio.
- Check planetary transverse polygons over their full neutral-backlash tooth
  period with bounded continuous phase subdivision and cached geometry results.
  Keep unresolved clearance visible, including zero/tiny-backlash and exhausted
  checks, and reject detected collisions. These checks do not certify unsampled
  curves, exported 3D interpolation, loaded contact or manufacturing tooling.

## 0.1.10 — 2026-10-31

### Added

- Open the browser workspace from the homepage and compose its pinned,
  self-hosted runtime in the website build, with verified bundle contents and
  deployment cache and MIME settings.
- Add a static browser engine using the existing Python generators in a Pyodide
  worker, with packed preview geometry, canonical motion queries, compatible
  projects and standalone export downloads. Pin a self-hostable runtime and
  build only reviewed headless modules with corresponding source.
- Add a browser design workspace with parameter editing, generated WebGL preview,
  canonical animation, project history and local recovery, component selection
  and nominal preview capture for export packages.
- Add browser metrology, finite search, discrete interference and working
  backlash tools, with explicit proposal checks, sampled surface measurements,
  revision-bound query downloads and speed-only updates that reuse surfaces.
- Include pinned-runtime fetching, a verified local static preview helper,
  portable source recipes and runtime notices with the browser bundle.
- Link the browser Export controls to desktop downloads for CAD integrations,
  with a callout that wraps at narrow widths and larger text sizes.

### Fixed

- Keep browser help and menus within the window, prevent clipped parameter
  help, and retain readable motion controls at narrow widths or larger text.
- Apply joined double-helical search proposals through freshly validated changed
  fields, preserve locked input precision and retain query results if Apply fails.
- Reset browser zoom with Fit and keep named-view indicators consistent with
  keyboard orbit and the F shortcut.
- Import legacy browser projects while discarding obsolete settings, confirm
  pending RPM before document downloads, and reject stale asynchronous saves
  and analysis proposals without replacing newer input.
- Render coupled differential member speeds, equations and axis references in
  component-list reports, fixing BOM and complete-package exports for wrist
  and classic configurations without changing their calculations.

## Installer publication recovery — 2026-10-31

- Repair native 0.1.9 diagnostic and self-test reports by separating JSON output
  from warning/error logs, preserving callback failures and strict GUI checks.
- Retain separate Linux installed-GUI diagnostics in CI verification artifacts.
- This packaging-only recovery keeps source version 0.1.9; it does not include
  the browser application or other pending development changes.

## 0.1.9 — 2026-10-30

- Add offline parameter guides with family-specific explanations, units and
  original diagrams, available from labels by hover or keyboard, with a
  keep-open option and expandable **Show diagram** illustrations.
- Adjust live motion speeds without rebuilding geometry or re-uploading the
  preview meshes, preserving accumulated poses through speed changes and stops.
  Group slider adjustments into one Undo step and retain precise numeric entry.
- Add theoretical gear metrology over/between balls or axial rollers for external
  and internal spur involutes, with separate TXT/JSON query exports. Include tooth
  thickness and usable external-spur Wildhaber spans in calculation reports;
  helical gauge measurements remain unsupported.
- Solve working transverse tangential backlash by centre-distance adjustment for
  parallel external spur, helical and double-helical pairs. Preview regenerated
  proposals with discrete interference checks, then explicitly apply the centre
  distance as one Undo step; sampled checks do not establish continuous clearance.

- Screen wheel-driven worm configurations with an explicit static tooth friction
  coefficient and reference-cylinder geometry; refuse a known static self-locking
  request while preserving the valid design. Explain indeterminate and potentially
  backdrivable cases separately, including output-driven strain-wave arrangements.

- Remove redundant leading and trailing zeros when numeric input is confirmed.
  Automatic values display up to six decimal places, using scientific notation
  for very small values; explicitly entered precision is preserved.
- Preserve exact numeric values in calculations, saved projects and history,
  including manual values restored after exploring derived presets. Commit
  pending numeric edits before opening project replacement or save dialogs.

## 0.1.8 — 2026-10-30

- Add canonical URLs, social previews and structured search metadata using the
  actual public release, plus a generated sitemap and crawler discovery file.
- Use consistent directory links and provide a noindex 404 page with working
  assets for missing nested addresses.

## 0.1.7 — 2026-10-30

- Refine the homepage workspace composition with a prominent framed application
  screenshot, a pale download section and structured model and project resources.

## 0.1.6 — 2026-10-30

- Add content-based CSS and JavaScript URLs to generated pages so browser
  caches refresh when website assets or the documentation search index change.

## 0.1.5 — 2026-10-30

- Replace promotional homepage cards with the actual desktop workspace,
  compact downloads and a factual inventory of models and tools.
- Remove lower-homepage scroll reveals and reading progress decoration.

## 0.1.4 — 2026-10-30

- Add maintained responsive public website sources, with five interactive
  mechanism examples, platform-specific downloads and community links.
- Build the website and its search index directly from the canonical English
  documentation, preserving legacy heading links without a second docs snapshot.
- Add an isolated static-site build and website CI that validate the latest
  public stable release and its uploaded installer assets before updating links.

## 0.1.3 — 2026-10-30

- Write release-verification fixture sources as explicit UTF-8 bytes so Windows
  newline conversion cannot make them differ from the fixture archives. The
  production artifact verifier retains its exact byte comparisons.
- Update current release and download references to 0.1.3. Native package
  availability and platform verification still depend on the release CI results.

## 0.1.2 — 2026-10-30

- Correct installed GUI and MCP verification to require the complete ten-family
  catalog, including the bevel differential, and reject missing, duplicate or
  substituted family IDs.
- Verify the packaged changelog and its exact source contents while retaining
  strict resource inventories and excluding private updater state.
- Use Cairo for the GTK shell on hosted macOS CI runners after a compositor
  stall. Native OpenGL preview checks and their deadlines remain unchanged;
  the next CI run must establish whether this resolves the runner timeout.
- Align current download links and installation documentation with the stable
  release. Platform checks and signing limitations remain explicit; availability
  of native packages depends on their release build and verification results.

## 0.1.1 — 2026-10-30

### Added

- Bevel differentials with wrist and classic configurations, straight or spiral
  teeth, solid/hollow/flanged connections, open or split carriers and tooth-ratio
  presets. External belts, pulleys and motors remain part of the user's CAD work.
- Independent signed wrist inputs and a classic carrier input with a prescribed
  side-speed difference, with matching motion, saved projects, MCP parameters and
  STEP/STL/profile exports.
- Automatic release checks and a conditional **Update to [version]** button,
  with release notes and the appropriate platform download. The button appears
  only for a newer eligible GitHub release; checks do not open unsolicited dialogs.

### Changed

- Worm wheels now use the matching ZA/ZI screw envelope, including backlash and
  the swept generating-tip root transition.
- Bevel working flanks use spherical involutes and optional logarithmic spiral
  traces. The generator checks the root domain and availability of ideal tooth
  engagement, rejecting unsupported combinations.
- Strain-wave circular splines now use the full swept matching tooth outline
  under the prescribed ellipse pitch-arc/normal deformation. Numerical enclosure
  relief is reported separately from reference tooth backlash. Discrete
  interference checks now evaluate the actual moving flexspline surfaces.
- Combination-search controls show the current model, editable parameter ranges,
  finite search size and resource limits, with clearer proposal comparisons and
  invalidation when the model changes.
- Reference equations, coordinate conventions, supported domains and numerical
  limitations are documented for the new and revised mechanisms.

### Fixed

- Speed-only edits and temporary export/inspection poses preserve differential
  motion continuity and restore the active motion plan.
- Hiding supports keeps the driving cycloidal eccentric visible while hiding its
  bearing envelope.
- Application icons, native window identity and launcher resources are consistent
  across source, wheel and native packaging layouts.
- Obsolete unconditional concept/study banners are replaced by notices based on
  generated-model metadata; actual geometry warnings remain visible.
- Exact sampled-surface distance searches prune triangle pairs using cached
  bounds and projection lower bounds, without omitting components or poses.

Geometric and kinematic checks do not certify elastic response, strength, service
life or continuous clearance. Strain-wave deformation is prescribed. Bevel gears
use the documented custom planar blank.

## Windows and Linux Fusion update — 2026-10-29

Updated Windows and Linux downloads in Preview 2; macOS downloads retain their
original Preview 2 build.

- Add an optional Autodesk Fusion connection through the bundled RatioLabBridge
  add-in: authenticated local communication, per-component STEP import, source
  parameters/BOM metadata, unit/solid checks and cleanup of a failed new group.
- Add Fusion setup, connection and creation controls beside SolidCraft in the
  CAD integrations menu. Imported solids retain RatioLab parameters as metadata;
  native Fusion timeline regeneration is not provided.
- Connect the native Linux app to community Fusion installations under Wine,
  with prefix/profile discovery and verified transfer files inside the Wine
  C: drive. Wine runtime and Fusion compatibility depend on the community port.

## 0.1.0 Preview 2 — 2026-10-28

- Application source, automated tests and documentation now have dedicated
  `src/`, `tests/` and `docs/` directories. Public imports and saved project formats
  remain compatible.
- README and installation guide lead with platform-specific bundled downloads.
  Developer setup and the detailed user manual have separate pages.
- Internal working notes and agent instructions are excluded from public sources.
- Canonical branding/catalog resources have one maintained location; packaging,
  launchers and native builds follow the new source layout.


## 0.1.0 Preview 1 — 2026-10-28

First public preview of RatioLab, a parametric gear and reducer generator.

- Nine gear/reducer families, a GTK 4 workspace and an animated 3D viewport.
- Standalone STEP, STL and SVG/DXF exports, complete portable packages and BOMs.
- Projects with Undo/Redo, recent files, atomic saves and recovery.
- Generated tooth-root profiles and geometric worm/strain-wave study models.
- Discrete interference/distance analysis and finite parameter searches.
- Component selection, isolation, sampled surface measurements and subset exports.
- An offline MCP companion with 13 tools for agent workflows.
- Bundled installers for Linux x86-64, Windows 11 x86-64, and macOS 15+
  on Intel and Apple Silicon. See [installation](docs/installation.md) for exact requirements.
- GNU GPL version 3 only, with attribution to NoOneExceptEnderk.
- English repository/example filenames and exported report suffixes; English
  source comments and a contributor guide. Earlier project formats remain readable.
- English preference filenames with fallback to earlier installation settings.
- Completed-frame synchronization and responsive export completion on busy
  software-rendering main loops.

This preview has sampled/concept geometry and no load-capacity certification.
Windows Setup has no publisher signature; macOS uses ad hoc signing without
Apple notarization. Automated checks do not cover every user's GPU or driver.
