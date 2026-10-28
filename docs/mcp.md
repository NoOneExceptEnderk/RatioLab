# RatioLab tools for agents

RatioLab includes a local MCP server and a Python headless service. They use the same generators, project history, BOM, geometric analysis and exporters as the desktop application. They require no GTK, Cairo, OpenGL context, CAD installation, API key or network service. The server opens no listening socket and makes no network requests. The workspace is an explicit filesystem grant supplied when starting the server.

## Start the server

From a source checkout, with Python 3.10 or newer:

```sh
PYTHONPATH=src python -m ratiolab_mcp --workspace /absolute/path/to/projects
```

From an installed Python wheel:

```sh
ratiolab-mcp --workspace /absolute/path/to/projects
```

The application also accepts `ratiolab --mcp --workspace /absolute/path/to/projects`. Native bundles contain a separate console companion, which preserves stdin/stdout even on Windows:

- Linux: `/absolute/path/to/RatioLab/RatioLab-MCP --workspace /absolute/projects`
- Windows 11: `"C:\Path\RatioLab\RatioLab-MCP.exe" --workspace "C:\Users\Name\RatioLab projects"`
- macOS: `/Applications/RatioLab.app/Contents/MacOS/RatioLab-MCP --workspace /absolute/projects`

Use the companion executable for native bundles. The Windows desktop GUI executable is windowed and does not provide the MCP standard streams. Keep stdout exclusively for newline-delimited UTF-8 JSON-RPC; diagnostics belong to stderr. Closing stdin shuts down the server. The server may create the explicitly requested workspace directory if it does not exist.

A generic MCP client configuration is:

```json
{
  "mcpServers": {
    "ratiolab": {
      "command": "/absolute/path/to/RatioLab-MCP",
      "args": ["--workspace", "/absolute/path/to/projects"]
    }
  }
}
```

For a source installation, use the absolute Python executable as `command` and `args: ["-m", "ratiolab_mcp", "--workspace", "/absolute/projects"]`; that interpreter must have RatioLab installed or run with the checkout on its module path. On Windows, escape backslashes in JSON or use forward slashes in absolute executable/workspace paths.

For Codex, the corresponding configuration is:

```toml
[mcp_servers.ratiolab]
command = "/absolute/path/to/RatioLab-MCP"
args = ["--workspace", "/absolute/path/to/projects"]
tool_timeout_sec = 60
```

Or register the same command with `codex mcp add ratiolab -- /absolute/path/to/RatioLab-MCP --workspace /absolute/projects`. These are examples; installing RatioLab does not edit personal client configurations. See the [official Codex MCP configuration guide](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

## Tools and a normal workflow

The stable tool names are prefixed with `ratiolab.`. Every project operation uses the explicit opaque `handle` and integer `revision` returned by the preceding operation. Component positions are **1-based source indices**, tied to that revision.

| Tool | Arguments | Result/purpose |
| --- | --- | --- |
| `discover` | optional `family`, `variant`, `double_style`, `parameters` | Nine families and server limits, or contextual numeric fields/defaults, variants, I/O schemes, bearing/hardware options and named presets. |
| `project_create` | `family`, optional `parameters` | Generate and validate a new in-memory project. |
| `project_open` | `path` | Import a complete UTF-8 JSON configuration from the workspace. |
| `project_list` | none | Refresh live handles, revisions, canonical parameters and save status. |
| `project_update` | `handle`, `revision`, `parameters` | Validate/generate a parameter patch before committing it atomically. |
| `project_history` | `handle`, `revision`, `action: "undo"` or `"redo"` | Restore one validated `Document` state; advance the revision. |
| `project_save` | `handle`, `revision`, `path`, optional `overwrite: false` | Atomically save a compatible JSON project. |
| `project_close` | `handle`, `revision` | Discard the handle and unsaved in-memory edits; preserve disk files. |
| `project_describe` | `handle`, `revision`, optional `components` | Component names/indices, profile provenance, nominal bounds, calculations, warnings and limitations. |
| `bom` | `handle`, `revision`, optional `components` | Real grouped BOM, machining, procurement and source-model analysis. |
| `export` | `handle`, `revision`, `path`, optional `kind`, `components` | New export directory with a checksum manifest. |
| `search` | `handle`, `revision`, `axes`, optional `settings` | Finite ratio/envelope combination search, with explicit partial coverage. |
| `interference` | `handle`, `revision`, optional `settings` | Discrete, resource-bounded interference analysis with explicit unsupported/incomplete coverage. |

For example, first call `discover({"family":"parallel"})`, then `project_create({"family":"parallel","parameters":{"pinion":20,"wheel":60}})`. Retain the returned handle/revision and use them for `project_describe`, `bom` and `export`. A search can use `axes: {"wheel":[60,66]}` with `settings: {"target":3,"tolerance_percent":0}`. Search proposals do not mutate the project: explicitly apply a chosen parameter patch with `project_update` and the current revision.

Use `discover({"family":"cycloidal","parameters":{"eccentric_design":"fdm_bolted"}})` for the printable shaft preset. It returns canonical defaults including input shaft 17 mm, width 16 mm and the bearing-linked bore, together with `named_presets.fdm_bolted`. Field `default` reflects the selected options; `nominal_default` is the unlinked generic field default. The core may derive bores, widths, seats, fit allowances and I/O values from other options. Always use the returned canonical parameters rather than assuming the requested patch remains unchanged.

A parameter update may keep the same revision when it produces no semantic change. Saving advances the revision because the document's path/clean state changes. Undo/redo is limited by the existing `Document` history (201 states). Handles and unsaved states live only for the current server process; persist important projects with `project_save`. Restarting the server does not restore unsaved handles automatically.

## Files and exports

Paths supplied to tools must be relative to the granted workspace and use `/` separators, for example `projects/gear.json` or `exports/reducer v2`. Absolute paths, `..`, hidden names, symlinks, Windows junctions/reparse points, device names, alternate streams and ambiguous Windows spellings are rejected. Imports reject hard-linked and special files, including FIFOs. Only complete `solidcraft-riduttori/1` JSON configurations are imported. CAD scripts, Python, recovery files, selected-export configurations and arbitrary CAD files are not executed or imported as projects.

A new save uses atomic exclusive publication. An existing file is preserved unless `overwrite: true` is explicitly supplied, the path is this handle's previously opened/saved file, and its current SHA-256 still matches what this handle read/wrote. A changed file causes `conflict`; reopen it or choose a new name. Export destinations must always be new directories, including when an existing directory is empty.

Export kinds are `step`, `stl`, `svg`, `dxf`, `profiles` and `package` (the default). SVG/DXF requests emit both companion formats plus `profiles.json` so metadata references remain valid. Every export includes the BOM, source parameters, engineering reports, limitations and a SHA-256 manifest. STEP is an actual standalone CAD document; STL uses the unchanged shared sampled geometry. Neither requires SolidCraft.

A `package` is labelled `ratiolab-headless-export/1` and contains STEP, STL, SVG/DXF sections, BOM/reports, `model.config.json`, `model.script.json`, STEP assets and a manifest. CAD script asset paths are relative to the package. **No PNG or GUI screenshot is generated or claimed.** It is intentionally distinct from the desktop application's complete package with a captured preview.

Pass `components: [2]` to inspect/export only source component 2. The service converts that public selection to the existing internal subset API, preserves the original 1-based source positions, and records `index_base: 1` in the scope and manifest. `selection.json` names the exact source components. Source calculations/parameters remain available for reference; they are not a newly inferred reduced assembly. A selected package is explicitly marked `complete_assembly: false`; its source configuration is not accepted as a full project import, because regenerating it would regenerate the full source assembly.

## Resource limits and cancellation

Default limits are discoverable and enforced by the service/transport:

- 1 MiB per input JSON message/configuration and 2 MiB per tool response, including its text and structured copies.
- 32 live projects, 128 generated components, two active workers and eight queued tool calls.
- 30 seconds per operation; search permits at most 1,000 candidates, 50 retained proposals, eight axes and 100 explicit values per axis.
- Interference permits at most 48 poses and 120,000 triangles. Its requested time/pose/triangle budgets may be lowered, never raised beyond server limits.
- 128 MiB per export and a bounded response inventory. No directory is published after a detected budget/cancellation failure.

These are cooperative limits. The existing generator, a triangulation or an exporter unit may finish before cancellation/time limits can be observed; this is not a preemptive CPU/memory sandbox. Search and interference preserve their genuine partial/unsupported coverage rather than claiming completion. A client cancels an in-flight stdio request using `notifications/cancelled` with `requestId`. The input reader continues receiving cancellation while a worker computes, and sends no further response for a cancelled call. Mutations and export publication check cancellation before commit.

Closing stdin cancels active/queued requests and exits promptly. A non-preemptible unit may still be finishing when process shutdown ends its daemon worker; an unpublished temporary directory can remain after forced interruption. Normal failure/cancellation cleans its staging files. Hidden `.ratiolab-agent-*` directories are reserved for private staging and cannot be addressed through tools.

The workspace must be controlled by the person configuring the server. Path validation, no-follow imports, fingerprints and transactional publication prevent accidental traversal and overwrites. They are **not an OS security sandbox** against another user/process maliciously restructuring the workspace during a filesystem call. Use a dedicated directory and normal OS permissions; do not share it with untrusted filesystem writers.

Errors from tools have `isError: true` and matching JSON in `structuredContent.error` and the text content block: `code`, `message`, and `details`. Expected codes include `invalid_arguments`, `invalid_parameters`, `invalid_geometry`, `unsafe_path`, `not_found`, `already_exists`, `invalid_json`, `invalid_format`, `unknown_project`, `stale_revision`, `conflict`, `resource_limit`, `budget_exceeded` and `cancelled`. Protocol/framing/schema errors use JSON-RPC errors instead. An input with no readable request ID gets an error response with `id: null`; valid notifications never get responses.

## Protocol and implementation scope

The server implements the tools subset of two official MCP revisions:

- [2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning): modern stateless requests, mandatory `server/discover`, per-request `_meta` protocol version/client capabilities, `resultType: "complete"`, server identity metadata, and explicit cache fields on discover/list results.
- [2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle): legacy `initialize` → `notifications/initialized`, tools and `ping`. Handshake negotiation returns only the actually implemented 2025-11-25 revision.

Modern requests carry `_meta["io.modelcontextprotocol/protocolVersion"]: "2026-07-28"` and `_meta["io.modelcontextprotocol/clientCapabilities"]: {}` on **every request**. Missing fields are invalid parameters; a different modern revision receives the defined `UnsupportedProtocolVersion` error with the supported versions. Discovery and tools/list return `ttlMs: 0`, `cacheScope: "private"`. The deterministic tool list fits in one page; no cursor is issued.

Only `tools: {}` is advertised. Resources, prompts, HTTP transports, subscriptions, sampling, elicitation, tasks and multi-round-trip inputs are not implemented or advertised. There are no callbacks that send agent requests to the client. Refer to the official [stdio framing/cancellation rules](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio) and [tool result contract](https://modelcontextprotocol.io/specification/2026-07-28/server/tools).

A small standard-library adapter keeps the application Python 3.10 compatible and offline, without pulling the current Python SDK's Python 3.11+ requirement and web-stack dependencies into native installers. The official SDK is used independently for compatibility testing, rather than being required to run the server. `ratiolab_agent.AgentService(absolute_workspace)` also exposes the same operations directly to trusted local Python callers; call `close()` when finished.

## Verification

Run the focused regressions with `python -m unittest test_agent test_mcp`. They exercise every family/variant's canonical round trip, FDM preset discovery, actual STEP/STL/SVG/DXF/package output and hashes, source component 2, JSON persistence/history, stale concurrent edits, filesystem restrictions, cancellation before publication, protocol errors, bounded queues, EOF shutdown and a real subprocess. The stdio tests use portable reader threads and queues, including on Windows.

The build also runs `scripts/check-installed-mcp.py` against the actual installed console companion, verifying both protocol eras and real file output. Official Python SDK v1 and v2 clients are independent development checks; successful source tests alone do not prove that a newly built installer has passed its native run.
