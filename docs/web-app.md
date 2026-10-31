# RatioLab in a browser

The browser app uses RatioLab's unchanged Python generation, motion, analysis
and export modules through Pyodide in a Web Worker. It provides the desktop
workspace and ten model families with browser downloads and local project
recovery. CAD connection bridges and the desktop MCP companion are excluded.
Calculations happen in the browser; there is no calculation backend.

Open the [web app](https://ratiolab.dev/app/) without installing the desktop
program. The native installers linked in the main README remain separate
downloads for desktop use and CAD integrations. Verification covers the tested
flows; it does not establish compatibility with every browser, operating system
or graphics driver.

## Build and open locally

Use Python 3.10 or newer for these stdlib-only commands, from the checkout or
an extracted `source.zip`. No Node, npm, GTK or native CAD libraries are needed.
Only the first command accesses the network, fetching six exact pinned files:

```sh
python3 scripts/fetch-web-runtime.py
python3 scripts/fetch-web-runtime.py --check-only
python3 scripts/build-webapp.py --runtime-dir work/webapp-runtime
python3 scripts/serve-webapp.py
```

Open [the local preview](http://127.0.0.1:8766/). Ctrl+C stops it. Change the
loopback port with `--port 8767`; change its bundle with `--directory PATH`.
The default output is `work/webapp-dist`; the default runtime cache is
`work/webapp-runtime`. Both stay outside source distributions. An existing cache
can be selected explicitly with `fetch-web-runtime.py --directory PATH` and
`build-webapp.py --runtime-dir PATH`. `--check-only` never fetches or writes.
The fetcher downloads the five runtime files from the pinned jsDelivr CDN and
Pyodide's `LICENSE` from the official GitHub `314.0.7` tag. Each file has one
fixed URL; redirects are rejected. It checks exact sizes and SHA256 against
`webapp/runtime.json`; valid files are reused. Edited or foreign target files
and symlinks are preserved by failing instead of replacing them. Remove or move an unwanted file yourself
before retrying. Unrelated cache metadata is retained.

The build and preview commands never fetch dependencies. The builder has an
explicit source/asset list, deterministic ZIP contents and a checksum manifest.
It refuses to replace a foreign output directory or a bundle with extra/edited
files. Choose another `--output PATH` to retain a modified bundle. Native wheels
remain native application packages; source distributions include the web source,
recipe and tests, but no downloaded runtime binaries.

For a portable copy, retain the entire built folder. It includes `README.txt`,
`serve.py`, licenses, notices and readable corresponding source in `source.zip`.
After unpacking a complete portable ZIP, run `python3 serve.py` inside its folder
(or `python serve.py` if that is your interpreter's name). The preview helper
verifies every manifest file and rejects symlinks in listed paths before opening
its loopback HTTP server. It serves listed files only, with no directory listing.

A browser needs WebAssembly, Web Workers, WebGL and a secure context: HTTPS or
localhost. Opening `index.html` through `file://` fails. Python on your computer
is required only for building or the local HTTP preview, not by a user visiting
an already hosted static app.

## Use the workspace

Choose a family/construction, edit Dimensions, Motion and Assembly, and inspect
the live model. Precise numeric fields accept decimal points or commas;
incomplete entries remain visible and block exports until valid. Orbit, zoom,
Fit, animation, exploded/section views and component selection are available.

Save/Open use desktop-compatible JSON; Save As and exports prepare browser
downloads instead of native destination dialogs. Full and selected components
can be exported as STEP/STL/SVG/DXF; complete packages include the preview PNG,
reports and a checksum inventory. Keep downloaded JSON files: recent projects
and unsaved draft recovery are local to this browser/origin, and private browsing
or cleared site data can remove them. Undo/Redo preserve document edits.

Tools include component surface measurements, theoretical gear metrology,
finite combination search, discrete interference and working-backlash proposals.
Search results require explicit Apply; a changed source invalidates old results.
Cancel terminates the busy worker, restarts the engine and regenerates the latest
current parameters. Retry restarts a failed load after missing/blocked bundle
files have been corrected.

Geometry, ideal motion, construction warnings and analysis limits remain those
of the canonical engine. Measurements use sampled surfaces; interference uses
discrete poses and reports incomplete coverage. Finite search ranks only the
specified domain. Working-backlash Apply follows solver eligibility, and an
incomplete proposal remains ineligible. None establishes continuous clearance,
strength, bearing life or manufacturing readiness. Read the generated reports,
model warnings and [technical references](https://github.com/NoOneExceptEnderk/RatioLab/tree/main/docs/technical) before using exports.

## Static HTTPS hosting

The public website build composes the complete self-hosted app at `_site/app/`.
Run `bash website/build.sh` from the source checkout to build both the website
and app, using verified public desktop-release data and the pinned runtime.
For a prepared offline environment, use `--offline --web-runtime-dir PATH`.
See the [website build guide](https://github.com/NoOneExceptEnderk/RatioLab/blob/main/website/README.md)
for the existing Cloudflare Pages configuration and checks. Building does not
itself publish a deployment.

Copy the complete self-hosted output folder to a static HTTPS host, preserving
relative paths. No Python, API endpoint or server computation is required there.
Serve `.mjs`/`.js` as `text/javascript` and `.wasm` as `application/wasm`.
Missing assets must return an error, rather than an HTML application fallback.
Retain licenses, notices and `source.zip` with the app. This recipe does not
publish or configure any host.

The self-hosted runtime performs no external fetches during operation. It does
need the locally served runtime files on load; this app has no service worker
or guaranteed offline reload. Optional help/source links open external sites.
The explicit developer option `--external-runtime` instead references the pinned
CDN and requires external access; it is not the portable self-hosted recipe.

## Runtime and source notices

The pinned runtime is Pyodide **314.0.7** with CPython **3.14.2**. The upstream
Pyodide `LICENSE` is explicitly stored as `runtime/PYODIDE-LICENSE` (MPL 2.0).
`webapp/notices/` preserves CPython's LICENSE and Doc/license.rst and Emscripten
5.0.3's LICENSE and bundled musl COPYRIGHT. Its `provenance.json` records exact
URLs, sizes and hashes. These copies identify the pinned runtime and its listed
notices; they are not an exhaustive audit of the WebAssembly binary.

RatioLab is [GPL-3.0-only](../LICENSE); the bundle includes readable application
source, all browser build/fetch/serve scripts and this recipe in `source.zip`.
The runtime is supplied unmodified. Its corresponding upstream sources are
[Pyodide 314.0.7](https://github.com/pyodide/pyodide/tree/314.0.7),
[CPython 3.14.2](https://github.com/python/cpython/tree/v3.14.2) and
[Emscripten 5.0.3](https://github.com/emscripten-core/emscripten/tree/5.0.3).
See [Pyodide's license](https://github.com/pyodide/pyodide/blob/314.0.7/LICENSE),
[CPython's license](https://github.com/python/cpython/blob/v3.14.2/LICENSE) and
the bundled `notices/README.txt` for the preserved texts and provenance.
