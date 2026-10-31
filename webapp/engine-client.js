// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
/** RPC client. Cancellation destroys the worker and its active design/cache. */
export class EngineError extends Error {
  constructor(error) {
    super(error.message);
    this.name = 'EngineError';
    this.code = error.code;
  }
}

function cancelled(message = 'The Python operation was cancelled') {
  return new DOMException(message, 'AbortError');
}

export class EngineClient extends EventTarget {
  constructor({workerURL = new URL('./worker.js', import.meta.url), onProgress} = {}) {
    super();
    this.workerURL = workerURL;
    this.onProgress = onProgress;
    this.pending = new Map();
    this.sequence = 0;
    this.epoch = 0;
    this.disposed = false;
    this._start();
  }

  _start() {
    const epoch = ++this.epoch;
    this.failure = null;
    this.generationPending = null;
    this.ready = new Promise((resolve, reject) => {
      this.resolveReady = resolve;
      this.rejectReady = reject;
    });
    this.ready.catch(() => {});
    this.worker = new Worker(this.workerURL, {type: 'module', name: 'ratiolab-python'});
    this.worker.onmessage = ({data}) => {
      if (epoch !== this.epoch || this.disposed) return;
      if (data.type === 'progress') {
        this.onProgress?.(data);
        this.dispatchEvent(new CustomEvent('progress', {detail: data}));
      } else if (data.type === 'ready') {
        this.resolveReady(data);
      } else if (data.type === 'fatal') {
        this._fail(new EngineError(data.error));
      } else {
        const operation = this.pending.get(data.id);
        if (!operation || operation.epoch !== epoch) return;
        this.pending.delete(data.id);
        if (this.generationPending === data.id) this.generationPending = null;
        if (data.type === 'result') operation.resolve(data.result);
        else if (data.type === 'error') operation.reject(new EngineError(data.error));
      }
    };
    this.worker.onerror = event => {
      if (epoch === this.epoch) this._fail(new EngineError({code: 'worker_failed', message: event.message || 'Python worker failed'}));
    };
    this.worker.onmessageerror = () => {
      if (epoch === this.epoch) this._fail(new EngineError({code: 'worker_failed', message: 'Python worker returned an unreadable message'}));
    };
  }

  _fail(error) {
    this.failure = error;
    this.rejectReady(error);
    for (const operation of this.pending.values()) operation.reject(error);
    this.pending.clear();
    this.generationPending = null;
    this.worker.terminate();
  }

  request(method, payload = {}) {
    if (this.disposed) return Promise.reject(cancelled('The engine client is closed'));
    if (this.failure) return Promise.reject(this.failure);
    let snapshot;
    try { snapshot = structuredClone(payload); }
    catch (error) { return Promise.reject(error); }
    const generates = method === 'generate' || method === 'import_project';
    // Superseded synchronous Python work cannot be preempted by another message.
    if (generates && this.generationPending !== null) this.cancel('A newer design superseded this operation');
    const id = ++this.sequence;
    const epoch = this.epoch;
    if (generates) this.generationPending = id;
    return new Promise((resolve, reject) => {
      this.pending.set(id, {resolve, reject, epoch, method});
      this.ready.then(() => {
        if (epoch === this.epoch && this.pending.has(id)) {
          // Payload was snapshotted at request time; callers retain document revision.
          try { this.worker.postMessage({id, method, payload: snapshot}); }
          catch (error) {
            this.pending.delete(id);
            if (this.generationPending === id) this.generationPending = null;
            reject(error);
          }
        }
      }, error => {
        if (this.pending.delete(id)) reject(error);
      });
    });
  }

  cancel(message) {
    if (this.disposed) return;
    this._fail(cancelled(message));
    this._start();
  }

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    ++this.epoch;
    this._fail(cancelled('The engine client is closed'));
  }
}
