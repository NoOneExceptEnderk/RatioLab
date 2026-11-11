// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
/** Browser document data only: no generated mesh, worker state or rounded values. */
export const clone = value => structuredClone(value);
export const automaticText = value => {
  if (value == null) return '';
  if (!Number.isFinite(value)) return String(value);
  const text = value.toFixed(6);
  return Number(text) === 0 && value !== 0 ? value.toExponential(6).replace(/\.?0+e/, 'e') : String(Number(text));
};
export const SOURCE_KEY = '_decimal_inputs';
export const automatic = (value, source) => ({text: automaticText(value), exact: value, typed: false, ...(source === undefined ? {} : {source})});
const decimalIdentity = text => {
  let value=String(text).trim().replace(',', '.').toLowerCase();
  const match=value.match(/^([+-]?)(\d*\.?\d+)(?:e([+-]?\d+))?$/);
  if (!match) return null;
  const exponent=Number(match[3] || 0); if (!Number.isSafeInteger(exponent) || Math.abs(exponent)>4096) return null;
  const mantissa=match[2], dot=mantissa.indexOf('.');
  let digits=mantissa.replace('.','').replace(/^0+/,''), power=exponent-(dot<0?0:mantissa.length-dot-1);
  if (!digits) return '0';
  while (digits.endsWith('0')) { digits=digits.slice(0,-1); ++power; }
  return (match[1]==='-'?'-':'')+digits+'e'+power;
};
export function numberValue(entry, spec) {
  if (!entry) return {error: 'Enter a value.'};
  const text = entry.text.trim();
  if (spec.optional && !text) return {omitted: true};
  if (!/^[+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+)(?:e[+-]?\d+)?$/i.test(text)) return {error: 'Enter a complete number.'};
  const value = !entry.typed && entry.exact != null ? entry.exact : Number(text.replace(',', '.'));
  if (!Number.isFinite(value)) return {error: 'Enter a finite number.'};
  if (spec.type === 'integer' && !Number.isInteger(value)) return {error: 'Enter a whole number.'};
  if (spec.minimum != null && value < spec.minimum || spec.maximum != null && value > spec.maximum) {
    return {error: `Use ${spec.minimum ?? '−∞'} to ${spec.maximum ?? '∞'}.`};
  }
  return {value};
}

const id = () => globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
const contextKey = options => ['variant', 'double_style', 'configuration', 'ratio_mode',
  'bearing_mode', 'fit', 'eccentric_design', 'hardware_mode'].map(key => options[key] ?? '').join('|');
const numeric = schema => [...schema.fields, ...schema.options.filter(f => f.type === 'number' || f.type === 'integer')];
const fingerprint = state => JSON.stringify(state);

export class BrowserDocument extends EventTarget {
  constructor() {
    super();
    this.identity = id(); this.revision = 0; this.name = 'Untitled design';
    this.state = {family: 'parallel', families: {}};
    this.past = []; this.future = []; this.saved = fingerprint(this.state); this.coalesce = null;
  }
  get family() { return this.state.family; }
  get dirty() { return fingerprint(this.state) !== this.saved; }
  token() { return {identity: this.identity, revision: this.revision}; }
  matches(token) { return token.identity === this.identity && token.revision === this.revision; }
  barrier() { this.coalesce = null; }
  get draft() { return this.state.families[this.family]; }
  get entries() { return this.draft.contexts[contextKey(this.draft.options)]; }
  checkpoint(key = null) {
    const now = performance.now();
    if (!key || this.coalesce?.key !== key || now - this.coalesce.time > 700) {
      this.past.push(clone(this.state)); if (this.past.length > 200) this.past.shift();
    }
    this.coalesce = key ? {key, time: now} : null;
    this.future = []; ++this.revision;
  }
  changed() { this.dispatchEvent(new Event('change')); }
  ensure(schema, initial = {}) {
    let draft = this.draft;
    if (!draft) {
      draft = this.state.families[this.family] = {options: {}, contexts: {}};
      for (const f of schema.options) if (f.type !== 'number' && f.type !== 'integer') draft.options[f.key] = initial[f.key] ?? f.default;
    }
    const key = contextKey(draft.options);
    const entries = draft.contexts[key] ??= {};
    for (const f of numeric(schema)) {
      if (!Object.hasOwn(entries, f.key)) entries[f.key] = automatic(initial[f.key] ?? schema.defaults[f.key] ?? f.default, initial[SOURCE_KEY]?.[f.key]);
    }
    return draft;
  }
  selectModel(family, schema, options = {}, prepareEntries = () => {}) {
    if (family === this.family && Object.entries(options).every(([key,value])=>this.draft.options[key]===value)) return;
    this.checkpoint(); this.state.family = family; this.ensure(schema);
    const old = clone(this.entries); Object.assign(this.draft.options,options);
    const next = contextKey(this.draft.options);
    if (!this.draft.contexts[next]) this.draft.contexts[next] = old;
    prepareEntries(this.entries);
    this.changed();
  }
  selectFamily(family, schema) {
    this.checkpoint(); this.state.family = family; this.ensure(schema); this.changed();
  }
  editNumber(key, text) {
    this.checkpoint(`${this.family}:${contextKey(this.draft.options)}:${key}`);
    this.entries[key] = {text, typed: true}; this.changed();
  }
  editOption(key, value) {
    this.editOptions({[key]: value});
  }
  editOptions(values) {
    this.checkpoint();
    const old = clone(this.entries); Object.assign(this.draft.options, values);
    // Keep a separate draft for each mechanically distinct variant. Common raw
    // values seed a first visit; later visits restore exactly their own text.
    const next = contextKey(this.draft.options);
    if (!this.draft.contexts[next]) this.draft.contexts[next] = old;
    this.changed();
  }
  values(schema, linked = new Set()) {
    const values = {...this.draft.options}, errors = {}, sources = {};
    for (const f of numeric(schema)) {
      if (f.inactive) continue;
      const result = numberValue(this.entries[f.key], f);
      if (result.error && !linked.has(f.key)) errors[f.key] = result.error;
      else if (!result.omitted && !result.error) {
        values[f.key] = result.value;
        const entry=this.entries[f.key];
        if (!entry.typed && entry.source !== undefined) sources[f.key]=clone(entry.source);
        else if (entry.typed && decimalIdentity(entry.text)!==decimalIdentity(String(result.value))) sources[f.key]=entry.text.trim().replace(',', '.');
      }
    }
    if (Object.keys(sources).length) values[SOURCE_KEY]=sources;
    return {values, errors};
  }
  normalize(values, schema) {
    // Called only for a matching successful generation. Equal typed values keep
    // all entered digits; only canonical linked/derived changes become automatic.
    for (const f of numeric(schema)) {
      if (!Object.hasOwn(values, f.key)) continue;
      const old = this.entries[f.key], parsed = numberValue(old, f);
      if (parsed.error && old?.typed) continue;
      const source=values[SOURCE_KEY]?.[f.key];
      if (parsed.value !== values[f.key] || !old?.typed && JSON.stringify(old?.source)!==JSON.stringify(source)) {
        this.entries[f.key] = automatic(values[f.key],source);
      }
    }
  }
  undo() {
    if (!this.past.length) return false;
    this.future.push(clone(this.state)); this.state = this.past.pop();
    ++this.revision; this.coalesce = null; this.changed(); return true;
  }
  redo() {
    if (!this.future.length) return false;
    this.past.push(clone(this.state)); this.state = this.future.pop();
    ++this.revision; this.coalesce = null; this.changed(); return true;
  }
  replace(family, schema, values = {}, name = 'Untitled design', {recovery, quality, component_sheets} = {}) {
    this.identity = id(); ++this.revision; this.name = name;
    this.state = recovery ? clone(recovery.state) : {family, families: {}};
    if (!recovery && quality && Object.keys(quality).length) this.state.quality=clone(quality);
    if (!recovery && component_sheets && Object.keys(component_sheets).length) this.state.component_sheets=clone(component_sheets);
    this.ensure(schema, values); this.past = []; this.future = []; this.coalesce = null;
    this.saved = recovery ? recovery.saved : fingerprint(this.state); this.changed();
  }
  setQuality(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value) || Object.entries(value).some(([key,v]) => !['preview_mm','export_mm'].includes(key) || typeof v !== 'number' || !Number.isFinite(v) || v <= 0)) throw Error('Surface thresholds must be positive finite numbers in mm.');
    if (JSON.stringify(value)===JSON.stringify(this.state.quality || {})) return false;
    this.checkpoint();
    if (Object.keys(value).length) this.state.quality=clone(value); else delete this.state.quality;
    this.changed();return true;
  }
  markSaved(name = this.name) { this.name = name; this.saved = fingerprint(this.state); this.changed(); }
  recovery() { return {format: 'ratiolab-browser-recovery/1', name: this.name, state: clone(this.state), saved: this.saved, time: Date.now()}; }
}

const RECOVERY = 'ratiolab.web.recovery.v1', RECENT = 'ratiolab.web.recent.v1';
export const storage = {
  readRecovery() { try { const r = JSON.parse(localStorage.getItem(RECOVERY)); return r?.format === 'ratiolab-browser-recovery/1' && r.state?.family && r.state?.families && typeof r.saved === 'string' ? r : null; } catch { return null; } },
  writeRecovery(document) { try { if (document.dirty) localStorage.setItem(RECOVERY, JSON.stringify(document.recovery())); else localStorage.removeItem(RECOVERY); return true; } catch { return false; } },
  clearRecovery() { try { localStorage.removeItem(RECOVERY); } catch {} },
  recent() { try { const r = JSON.parse(localStorage.getItem(RECENT)); return Array.isArray(r) ? r.slice(0, 8).filter(x => x.project?.format === 'solidcraft-riduttori/1') : []; } catch { return []; } },
  remember(name, project) { try { const recent = this.recent().filter(x => x.name !== name); recent.unshift({name, project, time: Date.now()}); localStorage.setItem(RECENT, JSON.stringify(recent.slice(0, 8))); } catch {} },
};

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob), a = document.createElement('a');
  a.href = url; a.download = filename; a.hidden = true; document.body.append(a); a.click(); a.remove();
  // Browser download managers may read the object asynchronously.
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}
