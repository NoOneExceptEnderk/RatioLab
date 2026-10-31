// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
// Dedicated module worker. No project data leaves this worker through fetch.
let pyodide;
let bridge;
let activeMethod = '';
const progress = (stage, detail = '') => self.postMessage({type: 'progress', stage, detail});
const errorData = (error, code = 'engine_error') => ({code, message: String(error?.message || error)});

async function fetchOK(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(`Cannot load ${new URL(url).pathname}: HTTP ${response.status}`);
  return response;
}

async function sha256(data) {
  const hash = await crypto.subtle.digest('SHA-256', data);
  return Array.from(new Uint8Array(hash), value => value.toString(16).padStart(2, '0')).join('');
}

async function initialize() {
  progress('runtime', 'Loading the pinned Python runtime');
  const configURL = new URL('./runtime.json', import.meta.url);
  const config = await (await fetchOK(configURL, {cache: 'no-cache'})).json();
  const runtimeURL = new URL(config.indexURL, configURL);
  const pinned = 'https://cdn.jsdelivr.net/pyodide/v314.0.7/full/';
  if (config.format !== 'ratiolab-web-runtime/1' || config.version !== '314.0.7' || config.module !== 'pyodide.mjs') {
    throw new Error('Unsupported runtime configuration');
  }
  if (runtimeURL.origin !== self.location.origin && !(config.allow_external === true && runtimeURL.href === pinned)) {
    throw new Error('External runtime loading requires explicit pinned CDN configuration');
  }
  // All runtime code URLs are derived from this reviewed index URL.
  const {loadPyodide} = await import(new URL('pyodide.mjs', runtimeURL).href);
  pyodide = await loadPyodide({indexURL: runtimeURL.href,
    stdout: () => {}, stderr: line => console.warn('[RatioLab Python]', line)});
  progress('engine', 'Loading the shared geometry and export engine');
  const manifest = await (await fetchOK(new URL('./bundle-manifest.json', import.meta.url), {cache: 'no-cache'})).json();
  const archive = await (await fetchOK(new URL('./engine.zip', import.meta.url))).arrayBuffer();
  const expected = manifest.files?.['engine.zip'];
  if (manifest.format !== 'ratiolab-web-bundle/1' || !expected || archive.byteLength !== expected.size || await sha256(archive) !== expected.sha256) {
    throw new Error('Engine archive does not match its bundle manifest');
  }
  pyodide.unpackArchive(archive, 'zip', {extractDir: '/ratiolab-engine'});
  pyodide.runPython("import sys; sys.path.insert(0, '/ratiolab-engine')");
  bridge = pyodide.pyimport('engine_bridge');
  bridge.set_progress((message, fraction) => self.postMessage({type: 'progress', stage: 'analysis', method: activeMethod,
    message: String(message), detail: String(message), fraction: Number(fraction)}));
  // Imports are performed before ready so missing dependencies fail at boot.
  const check = JSON.parse(bridge.dispatch('catalog', '{}'));
  if (!check.ok) throw new Error(check.error.message);
  progress('ready', 'Python engine ready');
  self.postMessage({type: 'ready', api_version: 1, runtime: {name: 'Pyodide', version: config.version, python: config.python}});
}

const ready = initialize().catch(error => {
  self.postMessage({type: 'fatal', error: errorData(error, 'initialization_failed')});
  throw error;
});
// Keep startup failures observable through the RPC channel without an unhandled rejection.
ready.catch(() => {});
let queue = Promise.resolve();
self.onmessage = event => {
  const {id, method, payload = {}} = event.data || {};
  if (!Number.isSafeInteger(id) || typeof method !== 'string') return;
  queue = queue.then(async () => {
    const buffers = [];
    let previewProxy;
    try {
      await ready;
      activeMethod = method;
      progress('operation', method);
      let body = payload;
      if (method === 'export' && payload.preview_png !== undefined) {
        const png = payload.preview_png;
        if (!(png instanceof Uint8Array) && !(png instanceof ArrayBuffer) && !Array.isArray(png)) {
          throw new Error('preview_png must contain encoded PNG bytes');
        }
        if (Array.isArray(png) && png.some(n => !Number.isInteger(n) || n < 0 || n > 255)) {
          throw new Error('preview_png has invalid bytes');
        }
        const bytes = png instanceof Uint8Array ? png : new Uint8Array(png);
        if (bytes.byteLength > 16777216) throw new Error('preview_png exceeds 16 MiB');
        previewProxy = pyodide.toPy(bytes);
        body = {...payload};
        delete body.preview_png;
      }
      const response = JSON.parse(previewProxy ? bridge.dispatch(method, JSON.stringify(body), previewProxy) : bridge.dispatch(method, JSON.stringify(body)));
      if (!response.ok) {
        self.postMessage({type: 'error', id, error: response.error});
        return;
      }
      for (let i = 0; i < response.buffer_count; i++) {
        const proxy = bridge.buffer(i);
        try {
          // Copy before transferring: never detach a WASM heap view.
          const converted = proxy.toJs();
          const bytes = converted instanceof Uint8Array ? converted.slice() : new Uint8Array(converted).slice();
          buffers.push(bytes.buffer);
        } finally {
          proxy.destroy();
        }
      }
      self.postMessage({type: 'result', id, result: {...response.result, buffers}}, buffers);
    } catch (error) {
      self.postMessage({type: 'error', id, error: errorData(error)});
    } finally {
      previewProxy?.destroy();
      bridge?.clear_buffers();
      activeMethod = '';
    }
  });
};
