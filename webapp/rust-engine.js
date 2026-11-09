// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
// The same Rust request protocol as the native ctypes adapter. No Python math
// fallback: a missing/invalid kernel fails initialization visibly.
export async function loadRustGeometry(bytes) {
  const {instance} = await WebAssembly.instantiate(bytes, {});
  const kernel = instance.exports;
  for (const name of ['ratiolab_request', 'ratiolab_result_length', 'ratiolab_free', 'ratiolab_alloc', 'ratiolab_dealloc',
      'ratiolab_buffer_request', 'ratiolab_buffer_length', 'ratiolab_buffer_data', 'ratiolab_buffer_free']) {
    if (typeof kernel[name] !== 'function') throw new Error(`Rust geometry ABI missing ${name}`);
  }
  if (!(kernel.memory instanceof WebAssembly.Memory)) throw new Error('Rust geometry memory missing');
  const encoder = new TextEncoder();
  const decoder = new TextDecoder('utf-8', {fatal: true});
  const request = payload => {
    if (typeof payload !== 'string') throw new TypeError('Rust geometry request must be JSON text');
    const input = encoder.encode(payload);
    if (!input.length || input.length > 64 * 1024 * 1024) throw new Error('Rust geometry input limit exceeded');
    // Wasm i32 results carry unsigned wasm32 addresses, including the high bit.
    const source = kernel.ratiolab_alloc(input.length) >>> 0;
    if (!source) throw new Error('Cannot allocate Rust geometry request');
    let result = 0;
    try {
      new Uint8Array(kernel.memory.buffer, source, input.length).set(input);
      result = kernel.ratiolab_request(source, input.length) >>> 0;
      if (!result) throw new Error('Rust geometry returned no response');
      const length = kernel.ratiolab_result_length(result) >>> 0;
      if (length > 128 * 1024 * 1024) throw new Error('Rust geometry response limit exceeded');
      // The request can grow memory; create the view after it has completed.
      return decoder.decode(new Uint8Array(kernel.memory.buffer, result, length));
    } finally {
      if (result) kernel.ratiolab_free(result);
      kernel.ratiolab_dealloc(source, input.length);
    }
  };
  request.buffer = payload => {
    if (typeof payload !== 'string') throw new TypeError('Rust geometry request must be JSON text');
    const input = encoder.encode(payload);
    if (!input.length || input.length > 64 * 1024 * 1024) throw new Error('Rust geometry input limit exceeded');
    const source = kernel.ratiolab_alloc(input.length) >>> 0;
    if (!source) throw new Error('Cannot allocate Rust geometry request');
    let handle = 0;
    try {
      new Uint8Array(kernel.memory.buffer, source, input.length).set(input);
      handle = kernel.ratiolab_buffer_request(source, input.length) >>> 0;
      if (!handle) throw new Error('Rust geometry returned no binary response');
      const length = kernel.ratiolab_buffer_length(handle) >>> 0;
      if (length > 128 * 1024 * 1024) throw new Error('Rust geometry response limit exceeded');
      const pointer = kernel.ratiolab_buffer_data(handle) >>> 0;
      // Copy before release; no view survives native ownership or memory growth.
      return new Uint8Array(kernel.memory.buffer, pointer, length).slice();
    } finally {
      if (handle) kernel.ratiolab_buffer_free(handle);
      kernel.ratiolab_dealloc(source, input.length);
    }
  };
  const epochKey=Symbol.for('ratiolab.rust-kernel.epoch');
  globalThis[epochKey]=(globalThis[epochKey]||0)+1;
  request.epoch=globalThis[epochKey];
  return request;
}
