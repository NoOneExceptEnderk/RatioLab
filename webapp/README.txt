RatioLab browser preview

Unpack the complete ZIP into a folder. With Python 3.10 or newer available,
run this command inside that folder:

    python3 serve.py

Open http://127.0.0.1:8766/ in your browser. On systems where Python is named
python, use python serve.py. Ctrl+C stops the local preview. Choose another
loopback port with --port 8767. The helper verifies the bundle file inventory
and checksums before serving and serves only listed files. Unlisted local files
are ignored and cannot be requested. It performs no
model calculations: the unchanged Python engine runs in your browser through
Pyodide/WebAssembly. Python on the local computer is only for this HTTP preview.

A browser needs WebAssembly, Web Workers and WebGL, with HTTPS or a localhost
secure context. Opening index.html directly through file:// will fail. The
self-hosted bundle includes its pinned runtime and makes no external requests
for model generation or export. Documentation links to upstream sources are
optional. For static HTTPS hosting, copy this complete folder, retain paths,
serve .mjs as text/javascript and .wasm as application/wasm, and disable any
application fallback that substitutes HTML for missing assets. No Python server
or calculation backend is needed on the host. There is no service worker.

Choose a model, edit dimensions/motion/assembly, inspect the generated model,
and export. All ten families and their supported constructions use the same
engine as desktop RatioLab. STEP/STL/SVG/DXF and full packages download through
the browser; explicit component exports keep the selected source parts. Save
and Open use desktop-compatible JSON. Recent projects and draft recovery use
this browser's local storage; download projects to keep independent copies.
Private browsing or clearing site data can remove recovery. CAD connection
bridges and the desktop MCP companion are not part of the static app.

Cancel stops the busy worker and restarts the local engine, then regenerates
the latest current parameters. Older results are discarded. If loading fails,
use Retry after checking that all bundle files are available over HTTP(S).

Measurements and interference use sampled surfaces and discrete poses. Search
ranks only the finite grid you specify; partial results retain their limits.
Working-backlash Apply follows the canonical solver's eligibility checks.
Nominal geometry and ideal motion do not certify continuous clearance,
strength, bearing life or manufacturing readiness. Read model warnings,
calculation reports and technical references before using exported designs.
Browser/OS compatibility beyond actually recorded checks is not established.

License: LICENSE (RatioLab GPL-3.0-only), COPYRIGHT, notices/README.txt and
runtime/PYODIDE-LICENSE. Readable application source and the repeatable build,
runtime-fetch and preview scripts are in source.zip. docs/web-app.md in that
archive describes the source build and static hosting recipe. Runtime source:
https://github.com/pyodide/pyodide/tree/314.0.7
https://github.com/python/cpython/tree/v3.14.2
https://github.com/emscripten-core/emscripten/tree/5.0.3
