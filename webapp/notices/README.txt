RatioLab browser runtime notices

RatioLab application code and corresponding source: GPL-3.0-only. See the
bundle's LICENSE, COPYRIGHT and source.zip. These upstream texts retain their
original copyright holders and terms; provenance.json records the exact URL,
byte count and SHA256 of each unmodified notice copied here.

Pinned runtime: Pyodide 314.0.7, containing CPython 3.14.2, built using
Emscripten 5.0.3. The six runtime file pins are in runtime.json.

Pyodide: Mozilla Public License 2.0, PYODIDE-LICENSE in this directory
(and runtime/PYODIDE-LICENSE in self-hosted bundles). The upstream
filename is LICENSE; the fetch recipe obtains it from the official GitHub
314.0.7 tag and maps it to this local name. The other five runtime files
come from the pinned jsDelivr CDN.
Source: https://github.com/pyodide/pyodide/tree/314.0.7
License: https://github.com/pyodide/pyodide/blob/314.0.7/LICENSE

CPython: CPYTHON-LICENSE and CPYTHON-NOTICES (upstream Doc/license.rst).
Source: https://github.com/python/cpython/tree/v3.14.2
License: https://github.com/python/cpython/blob/v3.14.2/LICENSE

Emscripten: EMSCRIPTEN-LICENSE and MUSL-COPYRIGHT (its bundled musl notice).
Source: https://github.com/emscripten-core/emscripten/tree/5.0.3
License: https://github.com/emscripten-core/emscripten/blob/5.0.3/LICENSE

The source build uses the upstream runtime unmodified. This notice collection
identifies the pinned runtime and preserves the listed upstream texts; it is
not a complete audit of every component embedded in the WebAssembly binary.
Runtime version changes require reviewing both file pins and notices.
