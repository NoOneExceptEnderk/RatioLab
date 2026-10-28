# Changelog

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
