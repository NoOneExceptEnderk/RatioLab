// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
import {EngineClient} from './engine-client.js';
import {BrowserDocument, automaticText, clone, downloadBlob, numberValue, storage} from './document.js';
import {ModelViewer} from './viewer.js';
import {initTools} from './tools.js';

const $ = id => document.getElementById(id);
const node = (tag, text, className) => { const n = document.createElement(tag); if (text != null) n.textContent = text; if (className) n.className = className; return n; };
const labels = {variant:'Variant', double_style:'Double helix construction', bearing_mode:'Standard fit', bearing:'NSK bearing · d × D × B', fit:'Seat dimensions', hardware_mode:'Standard hardware', hardware_screw:'Screw size', hardware_shim:'Shim thickness', hardware_retaining:'Retaining rings', hardware_keys:'Parallel keys', hardware_bolts:'Assembly bolts', hardware_shims:'Shim washers', seat_allowance:'Bearing seat allowance', shaft_allowance:'Shaft allowance', shoulder:'Bearing shoulder', io_scheme:'Input / output arrangement', io_scheme2:'Second-stage input / output', harmonic_output:'Output member', eccentric_design:'Eccentric shaft construction', configuration:'Differential configuration', output_interface:'Output connection', carrier_style:'Carrier construction', ratio_mode:'Side / output tooth ratio', worm_static_friction:'Static tooth-contact friction μ'};
const motionKeys = new Set(['input_rpm','input_b_rpm','output_difference_rpm','input_torque','efficiency','pull_force','io_scheme','io_scheme2','harmonic_output','worm_static_friction']);
const assemblyKeys = new Set(['plate','housing_wall','rim','stage_gap','carrier_bolt_diameter','spider_pin_diameter','spider_clearance','output_interface','carrier_style','eccentric_design','seat_allowance','shaft_allowance','shoulder']);
const shaftKeys = new Set(['bore','output_bore','wheel_bore','input_shaft','output_shaft','shaft_extension','journal_length','journal_diameter','output_extension','passage_diameter']);
const outputKeys = new Set(['output_count','output_radius','output_pin','flange_radius','bolt_count','bolt_diameter']);
const mainOrder = ['teeth','side_teeth','output_teeth','sun','planet','planets','sun2','planet2','pinion','wheel','pins','radius','pin_radius','eccentric','module','width','spiral_angle','width2','disc_gap','helix','gap'];
const doc = new BrowserDocument();
const events = new EventTarget();
let engine, viewer, catalog, schema, design = null, validToken = null, tab = 'dimensions', inspection = 'components';
let startup = true, generationRunning = false, generationTimer, schemaSerial = 0, operationSerial = 0, busy = false;
let playing = false, phase = 0, lastTick = 0, lastPose = 0, posePending = false, animationFrame = 0;
let poseCompletion = Promise.resolve();
let previousRevision = -1, schemaPending = false, initialClean = true, recovery = storage.readRecovery(), fatal = false;
let fields = new Map(), errors = {}, advancedOpen = false, lastFamily = null;
// Operating edits retain the last valid motion while blocking source exports.
const speedKeys = new Set(['input_rpm','input_b_rpm','output_difference_rpm']);
let rateEditing = false, rateSource = null, ratePending = false, nominalFrame = null;
let sourceParameters = null;
let activeTool = 'components';
let analysisActive = false, cancellation = null;
let rateCompletion = null, actionConfirmation = false;
const toolControllers = new Map();
const recent = () => storage.recent();
// Keep an offered recovery intact until the user explicitly restores/dismisses
// it. A fresh clean boot must not erase the previous unsaved document.
const saveRecovery = () => recovery ? true : storage.writeRecovery(doc);
const currentToken = () => doc.token();
const isCurrent = token => doc.matches(token);
const currentValid = () => !!design && !!validToken && isCurrent(validToken) && !generationRunning && !schemaPending && !busy && !fatal && !rateEditing && !ratePending;
const selectedIndices = () => [...viewer?.selected ?? []].sort((a,b) => a-b);
const familyDefinition = () => catalog?.families.find(f => f.key === doc.family);
const displayKey = key => labels[key] ?? key.replaceAll('_',' ').replace(/^./,s => s.toUpperCase());

function status(text, kind = '') { $('status-text').textContent = text; $('status-line').className = 'status-line'+(kind ? ' '+kind : ''); }
function stageMessage(title, detail, {retry = false, loading = false} = {}) {
  $('stage-message').hidden = false; $('stage-message').querySelector('strong').textContent = title;
  $('loading-detail').textContent = detail; $('stage-message').querySelector('.loading-ring').hidden = !loading; $('retry-engine').hidden = !retry;
}
function updateActions() {
  const valid = currentValid();
  const documentReady = documentActionReady();
  for (const id of ['save-document','save-as-document','export-document']) $(id).disabled = !documentReady;
  for (const id of ['show-bom','show-report']) $(id).disabled = !valid;
  if (analysisActive) for (const id of ['save-document','save-as-document','export-document','show-bom','show-report','reset-motion']) $(id).disabled = true;
  $('show-notes').disabled = !design;
  $('play-motion').disabled = analysisActive || !motionAvailable() || !design?.motion.supported || viewer?.lost;
  $('reset-motion').disabled = analysisActive || !valid || viewer?.lost;
  $('undo').disabled = !doc.past.length || busy; $('redo').disabled = !doc.future.length || busy;
  $('family').disabled = !catalog || busy; $('reset-family').disabled = !catalog || busy;
  for (const id of ['new-document','open-document','recent-documents']) $(id).disabled = !catalog || busy || actionConfirmation;
  for (const button of document.querySelectorAll('[data-export-kind]')) button.disabled = !documentReady;
  $('cancel-generation').hidden = !generationRunning;
  const title = doc.name === 'Untitled design' ? 'Untitled' : doc.name;
  $('document-name').textContent = 'RatioLab · '+title;
  $('document-state').textContent = `${title} · ${doc.dirty ? 'unsaved changes' : doc.name === 'Untitled design' ? 'not saved' : 'saved'}`;
  syncMotionControl();
  document.title = `${doc.dirty ? '• ' : ''}${doc.name} · RatioLab`;
}
function setPlaying(value) {
  if (value && !analysisActive) events.dispatchEvent(new Event('playstart'));
  playing = value && !analysisActive && motionAvailable() && design.motion.supported && !viewer?.lost;
  $('play-motion').setAttribute('aria-pressed',String(playing));
  $('play-motion').textContent = playing ? 'Pause' : phase ? 'Resume motion' : 'Start motion';
  $('playback-hint').textContent = playing ? 'Playing' : '';
  lastTick = 0;
  if (playing) { viewer.explosion = 0; $('explosion').value = '0'; viewer.render(); if (!animationFrame) animationFrame = requestAnimationFrame(tick); }
  else { cancelAnimationFrame(animationFrame); animationFrame = 0; }
}
function invalidate(message = 'Updating geometry…') {
  // Python analyses are synchronous. Stop that worker BEFORE callers queue the
  // new schema/import/generation, so a source edit cannot wait behind old work.
  if (analysisActive) { analysisActive = false; sourceParameters = null; engine.cancel('The source changed during analysis.'); }
  validToken = null; ++operationSerial; rateEditing = false; rateSource = null; ratePending = false; setPlaying(false); errors = {};
  if (generationRunning) { generationRunning = false; engine.cancel('A parameter edit superseded the active generation.'); }
  if (design?.family !== doc.family) {
    viewer?.clear(); design = null; phase = 0; renderInspection(); renderMetrics();
    $('model-meta').textContent = 'Nominal geometry · mm'; $('motion-summary').textContent = 'Waiting for valid geometry.';
  }
  $('stale-banner').hidden = !design;
  if (!design && viewer) stageMessage('Preparing model',message,{loading:true});
  status(message,'warning'); updateActions(); events.dispatchEvent(new CustomEvent('invalidate',{detail:{token:currentToken()}}));
}

function linkedFields() {
  const out = new Set(), v = doc.draft?.options ?? {}, mode = v.bearing_mode ?? 'manual', f = doc.family;
  if (mode !== 'manual') {
    if (['spur','helical','double','parallel','internal'].includes(f) || f === 'planetary' && mode === 'shaft') out.add('bore');
    if (f === 'parallel') out.add('output_bore');
    if (f === 'cycloidal') for (const key of mode === 'gear' ? ['bore'] : ['input_shaft','output_shaft']) out.add(key);
  }
  if (f === 'cycloidal' && v.eccentric_design === 'fdm_bolted') out.add('bore');
  if (f === 'differential' && v.ratio_mode !== 'custom') out.add('output_teeth');
  if (v.fit === 'nominal') { out.add('seat_allowance'); out.add('shaft_allowance'); }
  return out;
}
function linkedDescription(key) {
  if (key === 'output_teeth') return 'Derived from the selected tooth ratio.';
  if (['seat_allowance','shaft_allowance'].includes(key)) return 'Nominal fit uses zero allowance.';
  if (doc.family === 'cycloidal' && doc.draft.options.eccentric_design === 'fdm_bolted' && key === 'bore') return 'Linked to the printed shaft bearing seat.';
  return `Linked to bearing ${doc.draft.options.bearing} and its fit.`;
}
function classify(spec) {
  const key = spec.key;
  if (motionKeys.has(key)) return ['motion', ['input_torque','efficiency','pull_force'].includes(key) ? 'Nominal operating loads' : 'Drive connections'];
  if (key.startsWith('hardware_')) return ['assembly','Standard hardware'];
  if (key.startsWith('bearing') || key === 'fit' || ['seat_allowance','shaft_allowance','shoulder'].includes(key)) return ['assembly','Bearings & fits'];
  if (assemblyKeys.has(key) || key.startsWith('print_')) return ['assembly', key === 'eccentric_design' ? 'Eccentric shaft construction' : 'Housing & flanges'];
  if (spec.advanced) return ['dimensions','Advanced · profile & clearances'];
  if (shaftKeys.has(key)) return ['dimensions','Shafts & bores'];
  if (outputKeys.has(key)) return ['dimensions','Output connection'];
  return ['dimensions','Main geometry'];
}
function optionDisabled(spec, value) {
  const options = doc.draft.options;
  const ioDefault = schema.options.find(f => f.key === 'io_scheme')?.default;
  const alternative = ['planetary','cycloidal'].includes(doc.family) && (options.io_scheme !== ioDefault || doc.family === 'planetary' && ['two_stage','two_stage_double'].includes(options.variant) && options.io_scheme2 !== ioDefault);
  if (spec.key === 'bearing_mode') return value !== 'manual' && (!schema.bearing_supported || alternative) || value === 'gear' && ['parallel','internal'].includes(doc.family);
  if (spec.key === 'hardware_mode') return value !== 'none' && (!schema.hardware_supported || alternative);
  return false;
}
function changeOption(key, value) {
  const values = {[key]:value};
  if (doc.family === 'double' && key === 'variant') values.double_style = value;
  if (doc.family === 'harmonic') {
    if (key === 'harmonic_output') values.io_scheme = value === 'circular' ? 'wave_circular_flex' : 'wave_flex_circular';
    if (key === 'io_scheme') values.harmonic_output = value.split('_')[1] === 'circular' ? 'circular' : 'flex';
  }
  doc.editOptions(values);
}
function helpDetails(spec) {
  if (!spec.help) return null;
  const details = node('details',null,'field-help'), summary = node('summary','i');
  summary.setAttribute('aria-label',`Help: ${spec.help.title}`); details.append(summary);
  const copy = node('div',null,'help-copy'); copy.append(node('strong',spec.help.title),node('p',spec.help.meaning),node('p',spec.help.effect));
  details.append(copy); return details;
}
let overlayPlacementFrame = 0;
function resetOverlayPlacement(copy) {
  for (const property of ['position','left','right','top','bottom','width']) copy.style.removeProperty(property);
}
function placeFloatingOverlays() {
  overlayPlacementFrame = 0;
  const margin = 8, width = document.documentElement.clientWidth, height = window.innerHeight;
  for (const copy of document.querySelectorAll('.popover[open]>.popover-body, .field .field-help[open]>.help-copy, #motion-help .field-help[open]>.help-copy')) {
    // Measure the normal anchor first so a menu keeps its usual placement
    // whenever it fits, including after scrolling or changing text size.
    resetOverlayPlacement(copy);
    const rect = copy.getBoundingClientRect();
    const x = Math.max(margin,Math.min(rect.left,width-margin-rect.width))-rect.left;
    const field = copy.closest('.field');
    if (field) {
      // Escape the parameter panel's scrolling clip while retaining the row's
      // horizontal anchor and measured width. Prefer above when below is full.
      const above = field.getBoundingClientRect().top-rect.height;
      const preferredTop = rect.bottom > height-margin && above >= margin ? above : rect.top;
      copy.style.position = 'fixed'; copy.style.left = `${rect.left+x}px`; copy.style.right = 'auto';
      copy.style.top = `${Math.max(margin,Math.min(preferredTop,height-margin-rect.height))}px`;
      copy.style.bottom = 'auto'; copy.style.width = `${rect.width}px`;
      continue;
    }
    const y = Math.max(margin,Math.min(rect.top,height-margin-rect.height))-rect.top;
    // Move the actual box: a transform can retain its original scroll overflow.
    if (x) { copy.style.left = `${copy.offsetLeft+x}px`; copy.style.right = 'auto'; copy.style.width = `${rect.width}px`; }
    if (y) { copy.style.top = `${copy.offsetTop+y}px`; copy.style.bottom = 'auto'; }
  }
}
function scheduleOverlayPlacement() {
  if (!overlayPlacementFrame) overlayPlacementFrame = requestAnimationFrame(placeFloatingOverlays);
}
function makeField(spec, {top = false} = {}) {
  const key = spec.key, linked = linkedFields().has(key), row = node('div',null,'field'); row.dataset.field = key;
  const heading = node('div',null,'field-top'); const labelText = top ? (key === 'variant' ? 'Variant' : key === 'configuration' ? 'Configuration' : labels[key] ?? displayKey(key)) : spec.label ?? labels[key] ?? displayKey(key);
  const unitMatch = labelText.match(/\[([^\]]+)\]/), caption = labelText.replace(/\s*\[[^\]]+\]/,'').split(' (')[0];
  const label = node('label',caption); label.htmlFor = `parameter-${key}`; heading.append(label); row.append(heading);
  let input;
  if (spec.type === 'choice') {
    input = node('select');
    for (const choice of spec.choices) {
      let title = choice.label;
      if (key === 'ratio_mode' && doc.draft.options.configuration === 'classic') title = title.replace('output','spider').replace('Relative spin','Spider spin');
      const option = node('option',title); option.value = choice.value; option.disabled = optionDisabled(spec,choice.value); input.append(option);
    }
    input.value = doc.draft.options[key];
    input.addEventListener('change',() => changeOption(key,input.value));
  } else if (spec.type === 'boolean') {
    input = node('input'); input.type = 'checkbox'; input.checked = doc.draft.options[key];
    if (key === 'hardware_bolts' && ['parallel','internal'].includes(doc.family)) { input.disabled = true; input.title = 'Automatic assembly bolts are unavailable for this fixed-axis construction.'; }
    input.addEventListener('change',() => changeOption(key,input.checked));
  } else {
    input = node('input'); input.type = 'text'; input.inputMode = spec.type === 'integer' ? 'numeric' : 'decimal'; input.autocomplete = 'off'; input.spellcheck = false;
    input.value = linked && validToken && isCurrent(validToken) && Object.hasOwn(design.values,key) ? automaticText(design.values[key]) : doc.entries[key]?.text ?? ''; input.readOnly = linked;
    input.setAttribute('aria-invalid',String(!!errors[key]));
    input.title = `${caption}${spec.minimum != null ? ' · minimum '+spec.minimum : ''}${spec.maximum != null ? ', maximum '+spec.maximum : ''}`;
    input.addEventListener('input',() => { doc.editNumber(key,input.value); applyFieldErrors(); });
    input.addEventListener('keydown',event => { if (event.key === 'Enter') { event.preventDefault(); clearTimeout(generationTimer); scheduleGeneration(0); } });
    const wrap = node('div',null,'field-input'), spin = node('div',null,'numeric-control'); spin.append(input);
    if (!linked) for (const delta of [-1,1]) {
      const button = node('button',delta < 0 ? '−' : '+'); button.type = 'button';
      button.setAttribute('aria-label',`${delta < 0 ? 'Decrease' : 'Increase'} ${caption}`); button.disabled = busy || schemaPending;
      button.addEventListener('click',() => {
        const parsed = numberValue(doc.entries[key],spec); if (parsed.error || parsed.omitted) { input.focus(); return; }
        const value = Math.max(spec.minimum ?? -Infinity,Math.min(spec.maximum ?? Infinity,parsed.value+delta*(spec.step ?? 1)));
        doc.checkpoint(`${doc.family}:${key}:step`); doc.entries[key] = {text:automaticText(value),exact:value,typed:false}; doc.changed();
      }); spin.append(button);
    }
    wrap.append(spin,node('span',unitMatch?.[1] ?? (key === 'worm_static_friction' ? 'μ' : ''),'unit')); row.append(wrap);
    if (linked) {
      const note = node('div',null,'linked-note'); note.append(node('span',linkedDescription(key)+' '));
      const source = node('button','Change source…','text-button'); source.addEventListener('click',() => {
        const sourceKey = key === 'output_teeth' ? 'ratio_mode' : ['seat_allowance','shaft_allowance'].includes(key) ? 'fit' : doc.family === 'cycloidal' && doc.draft.options.eccentric_design === 'fdm_bolted' ? 'eccentric_design' : 'bearing_mode';
        switchTab(sourceKey === 'ratio_mode' ? 'dimensions' : 'assembly'); $(`parameter-${sourceKey}`)?.focus();
      }); note.append(source); row.append(note);
    }
  }
  input.id = `parameter-${key}`; input.dataset.key = key;
  const help = helpDetails(spec); if (help) heading.append(help);
  if (spec.type === 'choice') row.append(input);
  if (spec.type === 'boolean') heading.append(input);
  const feedback = node('div',errors[key] ?? '','field-error'); feedback.id = `error-${key}`; feedback.hidden = !errors[key]; row.append(feedback); input.setAttribute('aria-describedby',feedback.id);
  if (key.startsWith('hardware_') && key !== 'hardware_mode' && doc.draft.options.hardware_mode === 'none') input.disabled = true;
  if (['bearing','fit','shoulder','seat_allowance','shaft_allowance'].includes(key) && doc.draft.options.bearing_mode === 'manual') input.disabled = true;
  if (key === 'double_style' && !['double','two_stage_double'].includes(doc.draft.options.variant) && doc.family !== 'double') { input.disabled = true; input.title = 'Select a double helical construction to use this option.'; }
  if (key === 'double_style' && doc.family === 'double') { input.disabled = true; input.value = doc.draft.options.variant; input.title = 'Defined by the construction selected above.'; }
  if (key === 'io_scheme2' && !['two_stage','two_stage_double'].includes(doc.draft.options.variant)) { input.disabled = true; input.title = 'Available for a two-stage construction.'; }
  if (busy || schemaPending) input.disabled = true;
  fields.set(key,{spec,input,feedback,row}); return row;
}
function renderFields() {
  if (!schema || !doc.draft) return;
  const container = $('parameters'), top = $('variant-fields'), scroll = container.scrollTop, focused = document.activeElement?.dataset.key;
  const selection = document.activeElement?.selectionStart, selectionEnd = document.activeElement?.selectionEnd;
  fields = new Map(); container.replaceChildren(); top.replaceChildren();
  for (const spec of schema.options.filter(f => f.key === 'variant')) top.append(makeField(spec,{top:true}));
  const groups = new Map();
  const specs = [...schema.fields,...schema.options.filter(f => f.key !== 'variant')];
  const order = ['configuration','ratio_mode','double_style',...mainOrder];
  specs.sort((a,b) => { const ia = order.indexOf(a.key), ib = order.indexOf(b.key); return (ia < 0 ? 100 : ia)-(ib < 0 ? 100 : ib); });
  for (const spec of specs) {
    if (spec.key === 'input_rpm' || spec.key === 'harmonic_output' || spec.key === 'io_scheme2' && !['two_stage','two_stage_double'].includes(doc.draft.options.variant) || spec.key === 'double_style' && (doc.family === 'double' || !['double','two_stage_double'].includes(doc.draft.options.variant)) || spec.inactive || spec.key.startsWith('print_') && doc.draft.options.eccentric_design !== 'fdm_bolted') continue;
    const [page, group] = classify(spec); if (page !== tab) continue;
    if (!groups.has(group)) {
      let section, target;
      if (['Advanced · profile & clearances','Nominal operating loads','Drive connections','Bearings & fits','Standard hardware','Housing & flanges','Eccentric shaft construction'].includes(group)) {
        section = node('details'); section.open = group.startsWith('Advanced') ? advancedOpen : !['Nominal operating loads','Standard hardware','Eccentric shaft construction'].includes(group);
        section.append(node('summary',group)); target = node('div',null,'field-group'); section.append(target);
        if (group.startsWith('Advanced')) section.addEventListener('toggle',() => { advancedOpen = section.open; });
      } else { section = target = node('div',null,'field-group'); target.append(node('h3',group)); }
      groups.set(group,target); container.append(section);
    }
    if (spec.key === 'io_scheme' || spec.key === 'io_scheme2') groups.get(group).append(makeDriveConnections(spec));
    else if (spec.key === 'configuration' || spec.key === 'ratio_mode' || spec.key === 'double_style') {
      const field = makeField(spec), firstGroup = [...container.children].find(child => !child.classList.contains('field')); container.insertBefore(field,firstGroup ?? null);
    } else if (!(doc.draft.options.bearing_mode === 'manual' && ['bearing','fit','shoulder','seat_allowance','shaft_allowance'].includes(spec.key)) && !(doc.draft.options.hardware_mode === 'none' && spec.key.startsWith('hardware_') && spec.key !== 'hardware_mode')) groups.get(group).append(makeField(spec));
    if (spec.key === 'planets' || spec.key === 'pins') {
      const derived = node('div',null,'derived-row');
      const value = design && validToken && isCurrent(validToken) && design.family === doc.family ? spec.key === 'planets' ? design.values.sun+2*design.values.planet : design.values.pins-1 : null;
      derived.append(node('span',spec.key === 'planets' ? 'Ring teeth · derived' : 'Disc lobes · derived'),node('output',value == null ? '—' : String(value)));
      derived.title = 'Calculated from the current tooth counts; edit the source geometry above.'; groups.get(group).append(derived);
    }
  }
  if (!container.children.length) container.append(node('p','No additional parameters for this model.','empty-state'));
  if (tab === 'motion') {
    const note = node('p',doc.family === 'differential' ? doc.draft.options.configuration === 'classic' ? 'Set carrier input C in the motion bar. Prescribe B−A here to explore the two outputs; this is a speed boundary condition, not another motor.' : 'Input A is set in the motion bar. Set input B here. Both signs use the same world +X direction; the shafts face opposite sides.' : 'Set input speed and playback in the motion bar. Operating assumptions are not allowable loads.','subtle'); container.prepend(note);
    if (doc.family === 'differential') appendMotionDemos(container);
  }
  if (focused && fields.has(focused)) {
    const input = fields.get(focused).input; input.focus({preventScroll:true});
    if (input.type === 'text' && selection != null) input.setSelectionRange(selection,selectionEnd);
  }
  container.scrollTop = scroll; syncMotionControl();
}
function applyFieldErrors() {
  if (!schema || !doc.draft) return;
  const parsed = doc.values(schema,linkedFields()); errors = {...errors,...parsed.errors};
  for (const [key, field] of fields) {
    field.input.setAttribute('aria-invalid',String(!!errors[key])); field.feedback.textContent = errors[key] ?? ''; field.feedback.hidden = !errors[key];
  }
}
function switchTab(name) {
  tab = name;
  for (const button of document.querySelectorAll('[data-tab]')) { const active = button.dataset.tab === name; button.setAttribute('aria-selected',String(active)); button.tabIndex = active ? 0 : -1; }
  $('parameters').setAttribute('aria-labelledby',`tab-${name}`); renderFields(); $('parameters').scrollTop = 0;
}
function chooseInspection(name) {
  if (name === 'results') return showDocuments('report');
  if (name === 'notes') return showNotes();
  if (activeTool !== name) events.dispatchEvent(new CustomEvent('toolswitch',{detail:{key:name}}));
  inspection = name; activeTool = name;
  $('tool-dock').hidden = false; $('inspection-panel').setAttribute('aria-label',name === 'components' ? 'Components' : 'Analysis tools');
  for (const button of document.querySelectorAll('[data-inspection]')) { const active = button.dataset.inspection === name; button.setAttribute('aria-pressed',String(active)); button.tabIndex = active ? 0 : -1; }
  renderInspection();
}
function updateFamilyHeader() {
  const family = familyDefinition(); $('family').value = doc.family; $('family-description').textContent = family.description; $('family').title = family.description; $('model-title').textContent = family.label;
}
async function refreshSchema() {
  const serial = ++schemaSerial, token = currentToken(), family = doc.family;
  schemaPending = true; updateActions();
  try {
    const result = await engine.request('schema',{family,parameters:{...doc.draft.options}});
    if (serial !== schemaSerial || !isCurrent(token)) return false;
    schema = result; doc.ensure(schema); schemaPending = false; renderFields(); return true;
  } catch (error) {
    if (serial === schemaSerial && isCurrent(token) && error.name !== 'AbortError') { schemaPending = false; status(error.message,'error'); handleFatal(error); }
    return false;
  }
}
function scheduleGeneration(delay = 300) {
  clearTimeout(generationTimer); if (!catalog || startup || busy) return;
  generationTimer = setTimeout(() => generateCurrent(),delay);
}
async function generateCurrent() {
  if (!schema || busy || startup || schemaPending) return;
  if (rateEditing && rateSource === design) return commitRates();
  const token = currentToken(), family = doc.family, parsed = doc.values(schema,linkedFields());
  errors = parsed.errors; applyFieldErrors();
  if (Object.keys(errors).length) {
    const field = Object.keys(errors)[0]; status(`${fields.get(field)?.spec.label ?? displayKey(field)}: ${errors[field]} Export is blocked.`,'error');
    if (!design) stageMessage('Check the parameters','Complete the highlighted fields to generate a model.'); updateActions(); return;
  }
  generationRunning = true; updateActions(); status('Generating geometry…','warning');
  const serial = ++operationSerial;
  try {
    sourceParameters = null; // Generation invalidates the worker's previous source, even if it fails.
    const result = await engine.request('generate',{family,parameters:parsed.values});
    if (serial !== operationSerial || !isCurrent(token)) return;
    generationRunning = false; fatal = false; rateEditing = false; rateSource = null; nominalFrame = null; doc.normalize(result.values,schema);
    const changedFamily = lastFamily !== family;
    if (changedFamily) { viewer.supports = family === 'differential'; viewer.housing = false; }
    viewer.setDesign(result,{fit: changedFamily || !design}); design = result; lastFamily = family; rememberSourceParameters();
    validToken = token; phase = 0; $('motion-phase').textContent = '0.00 rad';
    if (changedFamily) { viewer.supports = family === 'differential'; $('show-supports').checked = viewer.supports; viewer.housing = false; $('show-housing').checked = false; }
    $('stage-message').hidden = true; $('stale-banner').hidden = true;
    $('model-meta').textContent = `${result.triangle_count.toLocaleString()} triangles · nominal geometry · mm`;
    $('motion-summary').textContent = result.motion.message;
    renderFields(); renderMetrics(); renderInspection(); updateActions();
    if (initialClean) { initialClean = false; doc.markSaved(); } else saveRecovery();
    status('✓ Geometry generated');
    events.dispatchEvent(new CustomEvent('design',{detail:{design:result,token:clone(token)}}));
    if (await requestPose(0)) nominalFrame = clone(viewer.frame);
  } catch (error) {
    if (serial !== operationSerial || !isCurrent(token) || error.name === 'AbortError') return;
    generationRunning = false; validToken = null; setPlaying(false);
    status(error.message+' Export is blocked.','error');
    const spec = [...schema.fields,...schema.options].find(f => error.message.toLowerCase().includes(f.key.toLowerCase()) || f.label && error.message.toLowerCase().includes(f.label.toLowerCase()));
    if (spec) { errors[spec.key] = error.message; applyFieldErrors(); }
    if (!design) stageMessage('This configuration needs attention',error.message,{retry:!!engine.failure});
    $('stale-banner').hidden = !design; handleFatal(error); updateActions();
  }
}
function handleFatal(error) {
  if (!engine?.failure) return;
  fatal = true; validToken = null; setPlaying(false); stageMessage('The calculation engine stopped',error.message,{retry:true}); updateActions();
}
async function onDocumentChange() {
  updateActions(); saveRecovery();
  if (doc.revision === previousRevision || startup) return;
  previousRevision = doc.revision; initialClean = false;
  if (!analysisActive && isSpeedEdit()) {
    clearTimeout(generationTimer); validToken = null; rateEditing = true; rateSource = design; ++operationSerial;
    events.dispatchEvent(new CustomEvent('invalidate',{detail:{token:currentToken()}}));
    errors = doc.values(schema,linkedFields()).errors; applyFieldErrors(); syncMotionControl(); updateActions();
    status(Object.keys(errors).length ? 'Complete the input speed. Export is blocked.' : 'Input speed edited · press Enter or leave the field to apply.','warning');
    if (document.activeElement !== $('motion-rpm')) scheduleGeneration();
    return;
  }
  invalidate();
  const family = familyDefinition(); if (!family) return;
  schema = family; doc.ensure(schema); updateFamilyHeader();
  // Schema replies carry the same identity/revision guard as geometry replies.
  // A later keystroke starts its own schema request, so a stale schema cannot
  // replace labels, defaults, context drafts or edit text.
  const refreshed = await refreshSchema(); if (refreshed) scheduleGeneration();
}

async function requestPose(nextPhase) {
  if (!motionAvailable() || ratePending || posePending || viewer?.captureBusy) return false;
  const token = currentToken(), current = design; posePending = true;
  let finishPose; const completion = poseCompletion = new Promise(resolve => { finishPose = resolve; });
  try {
    const result = await engine.request('pose',{design_id:current.design_id,phases:[nextPhase]});
    if (!isCurrent(token) || design !== current || !motionAvailable() || busy || viewer.captureBusy) return false;
    viewer.applyFrame(result.frames[0]); phase = nextPhase; $('motion-phase').textContent = `${phase.toFixed(2)} rad`; return true;
  } catch (error) {
    if (isCurrent(token) && design === current && error.name !== 'AbortError') { setPlaying(false); status('Motion stopped: '+error.message,'error'); handleFatal(error); }
    return false;
  } finally { if (poseCompletion === completion) posePending = false; finishPose(); }
}
function tick(time) {
  animationFrame = 0; if (!playing) return;
  if (!lastTick) lastTick = time;
  // Advance only the amount actually displayed; dropping worker frames does
  // not queue unbounded RPCs or introduce a fake independent gear animation.
  if (!ratePending && !posePending && time-lastPose >= 1000/30) {
    const elapsed = Math.min(.15,(time-lastTick)/1000); lastTick = time; lastPose = time;
    const motion = design.motion;
    const moving = [...Object.values(motion.rates),...Object.values(motion.angular_rates),...motion.coordinates.map(c => c.rate)].flat(Infinity).some(rate => typeof rate === 'number' && rate !== 0);
    const rate = moving ? motion.phase_radians_per_second * Number($('playback-speed').value) : 0;
    if (rate !== 0) requestPose(phase+elapsed*rate);
  }
  animationFrame = requestAnimationFrame(tick);
}
// A raw RPM draft is a document edit, but it does not invalidate the displayed
// physical geometry. Only exports and analyses wait for its explicit commit.
function motionAvailable() {
  return !!design && !fatal && !busy && !generationRunning && !schemaPending &&
    (currentValid() || rateEditing && rateSource === design);
}
function rememberSourceParameters() {
  // The editable schema may retain dormant variant choices (for example
  // parallel/spur's double_style) which canonical generation intentionally omits.
  // Retain the exact normalized document snapshot that generated this source;
  // never treat an arbitrary absent canonical key as safe to ignore.
  sourceParameters = {identity:doc.identity,family:doc.family,values:clone(doc.values(schema,linkedFields()).values)};
}
function isSpeedEdit() {
  if (!design || !schema || schemaPending || generationRunning || busy || fatal || design.family !== doc.family ||
      sourceParameters?.identity !== doc.identity || sourceParameters.family !== doc.family) return false;
  const parsed = doc.values(schema,linkedFields());
  if (Object.keys(parsed.errors).some(key => !speedKeys.has(key))) return false;
  const keys = new Set([...Object.keys(parsed.values),...Object.keys(sourceParameters.values)]);
  return [...keys].every(key => speedKeys.has(key) || Object.hasOwn(parsed.values,key) &&
    Object.hasOwn(sourceParameters.values,key) && parsed.values[key] === sourceParameters.values[key]);
}
const scaleRPM = value => Math.sign(value)*Math.log1p(Math.abs(value));
const unscaleRPM = value => Math.sign(value)*Math.expm1(Math.abs(value));
function syncMotionControl() {
  const spec = schema?.fields.find(f => f.key === 'input_rpm');
  const input = $('motion-rpm'); input.disabled = !spec || busy || schemaPending;
  if (!spec || !doc.draft) return;
  input.value = doc.entries.input_rpm?.text ?? '';
  const helpKey = `${doc.family}:${doc.draft.options.configuration ?? ''}`;
  if ($('motion-help').dataset.key !== helpKey) {
    $('motion-help').replaceChildren(); const help = helpDetails(spec); if (help) $('motion-help').append(help); $('motion-help').dataset.key = helpKey;
  }
  const parsed = numberValue(doc.entries.input_rpm,spec), error = parsed.error;
  input.setAttribute('aria-invalid',String(!!error)); $('motion-error').textContent = error ?? ''; $('motion-error').hidden = !error;
  const low = spec.minimum ?? 0, high = spec.maximum ?? 100000, value = parsed.value ?? design?.values.input_rpm ?? spec.default;
  $('rpm-slider').min = scaleRPM(low); $('rpm-slider').max = scaleRPM(high); $('rpm-slider').value = scaleRPM(value);
  for (const id of ['rpm-minus','rpm-plus','rpm-slider']) $(id).disabled = input.disabled || ratePending;
  $('motion-caption').textContent = doc.family === 'differential' ? doc.draft.options.configuration === 'classic' ? 'Carrier input speed' : 'Input A speed' : doc.family === 'planetary' && ['two_stage','two_stage_double'].includes(doc.draft.options.variant) ? 'Input speed · stage 1' : 'Input speed';
}
function editSpeed(value) {
  const spec = schema?.fields.find(f => f.key === 'input_rpm'); if (!spec || busy || ratePending) return;
  doc.editNumber('input_rpm',String(Math.max(spec.minimum ?? 0,Math.min(spec.maximum ?? 100000,value))));
  clearTimeout(generationTimer); commitRates();
}
function commitRates() {
  // Blur and a document command can confirm the same edit in one event turn.
  if (rateCompletion) return rateCompletion;
  const completion = performRateCommit();
  rateCompletion = completion.finally(() => { rateCompletion = null; });
  return rateCompletion;
}
async function performRateCommit() {
  clearTimeout(generationTimer);
  if (!rateEditing || ratePending || rateSource !== design || busy) return false;
  const parsed = doc.values(schema,linkedFields()); errors = parsed.errors; applyFieldErrors(); syncMotionControl();
  if (Object.keys(errors).length) { status('Complete the input speed. Export is blocked.','error'); updateActions(); return false; }
  const source = design, token = currentToken();
  // Drain the single outstanding pose before choosing the exact displayed
  // phase. No frame is advanced while the rates request is in flight.
  ratePending = true; updateActions();
  try {
    await poseCompletion;
    // The parsed values belong to this exact revision, including while a pose
    // drains. A later keystroke must never be normalized from an earlier patch.
    if (!isCurrent(token) || !rateEditing || rateSource !== source || design !== source) return false;
    const patch = {};
    for (const key of speedKeys) if (Object.hasOwn(parsed.values,key)) patch[key] = parsed.values[key];
    const result = await engine.request('rates',{design_id:source.design_id,rpm_patch:patch,phase});
    if (rateSource !== source || design !== source) return false;
    // Retain packed CPU buffers, GPU resources, selection and the exact current
    // matrix/deformation frame. The canonical plan now continues from that pose.
    const {ports,buffers,...metadata} = result; Object.assign(source,metadata);
    for (const {index,port} of ports) source.parts[index].port = port;
    viewer.design = source;
    ratePending = false; lastTick = 0;
    if (isCurrent(token)) {
      doc.normalize(result.values,schema); rememberSourceParameters(); validToken = token; rateEditing = false; rateSource = null;
      $('stale-banner').hidden = true; renderFields(); status('Geometry generated'); saveRecovery();
      events.dispatchEvent(new CustomEvent('design',{detail:{design:source,token:currentToken()}}));
    } else if (document.activeElement !== $('motion-rpm')) scheduleGeneration(0);
    renderMetrics(); renderInspection(); updateActions(); return true;
  } catch (error) {
    if (design === source && rateSource === source && error.name !== 'AbortError') {
      status(error.message+' Export is blocked.','error'); handleFatal(error);
      $('motion-error').textContent = error.message; $('motion-error').hidden = false;
    }
    return false;
  } finally { ratePending = false; updateActions(); }
}
async function resetMotion() {
  if (!currentValid()) return false;
  const source = design, token = currentToken(); setPlaying(false); busy = true; ++operationSerial;
  events.dispatchEvent(new CustomEvent('invalidate',{detail:{token}})); updateActions();
  try {
    const result = await engine.request('motion_reset',{design_id:source.design_id});
    if (!isCurrent(token) || source !== design) return false;
    const {buffers,...metadata} = result; Object.assign(source,metadata); viewer.design = source; phase = 0;
    const pose = await engine.request('pose',{design_id:source.design_id,phases:[0]});
    if (!isCurrent(token) || source !== design) return false;
    viewer.applyFrame(pose.frames[0]); nominalFrame = clone(pose.frames[0]); $('motion-phase').textContent = '0.00 rad';
    $('play-motion').textContent = 'Start motion'; status('Initial pose'); return true;
  } catch (error) { if (error.name !== 'AbortError') { status(error.message,'error'); handleFatal(error); } return false; }
  finally {
    busy = false; updateActions();
    if (source === design && isCurrent(token)) events.dispatchEvent(new CustomEvent('design',{detail:{design,token:currentToken()}}));
  }
}
function appendMotionDemos(container) {
  const classic = doc.draft.options.configuration === 'classic', row = node('div',null,'motion-demos');
  const choices = classic ? [['Equal',12,0],['A held',12,24],['Counterrotate',0,24]] : [['Tilt',12,12],['Spin',12,-12],['Combined',12,0]];
  for (const [title,a,b] of choices) {
    const button = node('button',title); button.disabled = !currentValid();
    button.addEventListener('click',() => {
      doc.checkpoint();
      for (const [key,value] of [['input_rpm',a],[classic ? 'output_difference_rpm' : 'input_b_rpm',b]]) doc.entries[key] = {text:String(value),exact:value,typed:false};
      doc.changed(); commitRates();
    }); row.append(button);
  }
  container.append(row);
}
function makeDriveConnections(spec) {
  const body = node('div',null,'drive-connections'), active = doc.draft.options[spec.key];
  const triples = spec.choices.every(choice => choice.value.split('_').length === 3);
  if (!triples) {
    for (const choice of spec.choices) {
      const label = node('label',null,'check-control'), radio = node('input'); radio.type = 'radio'; radio.name = spec.key; radio.checked = choice.value === active; radio.disabled = busy || schemaPending;
      radio.addEventListener('change',() => { if (radio.checked) changeOption(spec.key,choice.value); }); label.append(radio,node('span',choice.label)); body.append(label);
    }
    return body;
  }
  const names = {};
  for (const choice of spec.choices) {
    const members = choice.value.split('_'), captions = choice.label.split(/ → | · /);
    if (captions.length === 3) members.forEach((member,i) => names[member] = i === 2 ? captions[i].replace(/ fixed$/,'') : captions[i]);
  }
  const [source,target,fixed] = active.split('_');
  if (spec.key === 'io_scheme2' || doc.family === 'planetary' && ['two_stage','two_stage_double'].includes(doc.draft.options.variant)) body.append(node('h3',spec.key === 'io_scheme2' ? 'Stage 2' : 'Stage 1'));
  for (const [role,title,current] of [['input','1 · Motor',source],['output','2 · Output',target]]) {
    const row = node('label',null,'io-role io-'+role), select = node('select'); row.append(node('span',title),select);
    const values = [...new Set(spec.choices.filter(choice => role === 'input' || choice.value.split('_')[0] === source).map(choice => choice.value.split('_')[role === 'input' ? 0 : 1]))];
    for (const value of values) { const option = node('option',names[value] ?? displayKey(value)); option.value = value; select.append(option); }
    select.value = current; select.disabled = busy || schemaPending || role === 'input' && doc.family === 'cycloidal' && doc.draft.options.eccentric_design === 'fdm_bolted';
    select.addEventListener('change',() => {
      const candidates = spec.choices.filter(choice => choice.value.split('_')[role === 'input' ? 0 : 1] === select.value);
      const next = candidates.find(choice => choice.value.split('_')[role === 'input' ? 1 : 0] === (role === 'input' ? target : source)) ?? candidates[0];
      if (next) changeOption(spec.key,next.value);
    }); body.append(row);
  }
  const fixedRow = node('div',null,'io-role'); fixedRow.append(node('span','3 · Fixed to frame'),node('strong',names[fixed] ?? displayKey(fixed))); body.append(fixedRow);
  const swap = node('button','Swap input and output'); swap.disabled = busy || schemaPending || doc.family === 'cycloidal' && doc.draft.options.eccentric_design === 'fdm_bolted';
  swap.addEventListener('click',() => changeOption(spec.key,[target,source,fixed].join('_'))); body.append(swap);
  const result = design?.analysis.kinematics?.stage_results?.[spec.key === 'io_scheme2' ? 1 : 0];
  if (result && currentValid()) body.append(node('p',`Ratio ${signed(result.signed_ratio,4)} : 1 · output ${automaticText(result.rates_rpm[result.output])} rpm`,'subtle'));
  const reset = node('button','Reset default arrangement','flat'); reset.addEventListener('click',() => changeOption(spec.key,spec.default)); body.append(reset);
  return body;
}
function selectView(name) {
  viewer.setView(name);
}
function closeToolDock() {
  $('tool-dock').hidden = true; $('tools-menu-extension').closest('details').querySelector('summary').focus({preventScroll:true});
  events.dispatchEvent(new Event('toolclose'));
}
function setDockPanel(key,body,{title = key} = {}) {
  if (activeTool !== key) events.dispatchEvent(new CustomEvent('toolswitch',{detail:{key}}));
  activeTool = key; inspection = key; $('tool-dock').hidden = false;
  $('inspection-panel').replaceChildren(body); $('inspection-panel').setAttribute('aria-label',title);
  for (const button of $('tool-dock-tabs').querySelectorAll('[data-tool],[data-inspection]')) button.setAttribute('aria-pressed',String((button.dataset.tool ?? button.dataset.inspection) === key));
  return $('inspection-panel');
}
function openTool(key) {
  if (key === 'components') return chooseInspection('components');
  toolControllers.get(key)?.open();
}
function registerTool(key,{label = key,open}) {
  if (typeof open !== 'function') throw Error('A tool requires an open callback.');
  toolControllers.set(key,{open});
  let button = $('tools-menu-extension').querySelector(`[data-tool="${key}"]`);
  if (!button) { button = node('button',label); button.dataset.tool = key; button.addEventListener('click',() => openTool(key)); $('tools-menu-extension').append(button); }
  button.textContent = label; button.disabled = false;
  for (const tab of $('tool-dock-tabs').querySelectorAll('[data-tool]')) if (tab.dataset.tool === key) tab.disabled = false;
}
async function showDocuments(kind) {
  if (!currentValid()) return;
  const token = currentToken(), id = design.design_id;
  try {
    events.dispatchEvent(new CustomEvent('querybegin',{detail:{method:'documents'}}));
    const result = await engine.request('documents',{design_id:id});
    if (!currentValid() || !isCurrent(token) || design.design_id !== id) return;
    const body = node('pre',kind === 'bom' ? result.data.bom_text : result.data.report_text,'document-text');
    const answer = await dialog(kind === 'bom' ? 'Bill of materials' : 'Calculation report',body,[{label:'Close',value:null},{label:'Download…',value:'download',primary:true}]);
    if (answer && currentValid() && isCurrent(token) && design.design_id === id) runExport(kind);
  } catch (error) { if (isCurrent(token) && error.name !== 'AbortError') { status(error.message,'error'); handleFatal(error); } }
}
function showNotes() {
  if (!design) return;
  const body = node('div');
  if (!currentValid()) body.append(node('p','These notes describe the last valid preview.','note-warning'));
  appendMessages(body,'Construction warnings',design.warnings,true); appendMessages(body,'Requirements',design.requirements,true);
  appendMessages(body,'Model notes',design.notes); appendMessages(body,'Accuracy & limits',design.limitations);
  return dialog('Model notes',body);
}
async function cancelOperations() {
  if (cancellation) return cancellation;
  analysisActive = false;
  clearTimeout(generationTimer); ++schemaSerial; ++operationSerial; setPlaying(false);
  generationRunning = false; rateEditing = false; rateSource = null; ratePending = false; schemaPending = false; busy = false;
  validToken = null; fatal = false; posePending = false;
  sourceParameters = null; engine.cancel('The active operation was cancelled.');
  $('stale-banner').hidden = !design; status('Operation cancelled · restoring the current source…','warning'); updateActions();
  events.dispatchEvent(new CustomEvent('invalidate',{detail:{token:currentToken()}}));
  // Regenerate the existing drafts with no document edit/history transaction.
  // Invalid drafts remain invalid; cancellation cannot silently accept them.
  const token = currentToken(), serial = operationSerial;
  cancellation = (async () => {
    try {
      await engine.ready;
      if (!isCurrent(token) || serial !== operationSerial) return;
      // Cancellation during a family/schema edit must rebuild that schema first.
      if (await refreshSchema()) await generateCurrent();
    } catch (error) { if (isCurrent(token) && serial === operationSerial) handleFatal(error); }
    finally { cancellation = null; }
  })();
  return cancellation;
}

function renderMetrics() {
  const cards = $('metric-cards'); cards.replaceChildren();
  if (!design) return;
  const a = design.analysis, v = design.values; let items;
  // Presentation mirrors result_controls.items; all values come from the engine.
  if (design.family === 'differential') {
    const q = a.kinematics.rates_rpm;
    items = v.configuration === 'classic' ? [
      ['Carrier input',signed(q.carrier,3),'rpm',`Prescribed B−A: ${signed(v.output_difference_rpm)} rpm`],
      ['Side output A',signed(q.side_a,3),'rpm','About world +X'],['Side output B',signed(q.side_b,3),'rpm','About world +X']
    ] : [['Carrier tilt',signed(q.carrier,3),'rpm','About the common input axis'],['Output spin',signed(q.output_spin,3),'rpm','Relative to the moving carrier'],['Input speeds A / B',`${signed(q.input_a)} / ${signed(q.input_b)}`,'rpm','Both signs measured about world +X']];
  } else if (a.signed_ratio == null) {
    items = [['Pitch diameter',(2*a.gear.pitch_radius).toFixed(3),'mm','Reference pitch circle'],['Tooth count',String(v.teeth),'',`Normal module ${automaticText(v.module)} mm`],['Face width',automaticText(v.width),'mm','Axial gear width']];
  } else {
    items = [['Effective ratio',signed(a.signed_ratio,4),':1',a.signed_ratio > 0 ? 'Same rotation direction' : 'Opposite rotation direction'],['Output speed',a.output.rpm.toFixed(2),'rpm',`At ${automaticText(a.input.rpm)} rpm input`]];
    const housing = design.metrics.join(' · ').match(/housing (?:diameter |Ø )([0-9.]+) mm/i);
    if (housing) items.push(['Housing diameter',housing[1],'mm','Nominal housing envelope']);
    else if (a.center_distance_mm != null || a.meshes?.length) items.push(['Centre distance',(a.center_distance_mm ?? a.meshes[0].center_distance_mm).toFixed(3),'mm','Axis spacing']);
    else items.push(['Flexible body length',automaticText(v.cup_length),'mm','Prescribed flexible-body geometry']);
  }
  for (const [title,value,unit,detail] of items) {
    const card = node('div'), line = node('div',null,'result-value'); line.append(node('strong',value));
    if (unit) line.append(node('span',unit,'result-unit'));
    card.append(node('span',title,'result-title'),line,node('span',detail,'result-detail')); cards.append(card);
  }
  const warnings = design.warnings ?? [];
  $('warning-bar').hidden = !warnings.length;
  $('warning-text').textContent = warnings.length ? 'Geometry warning: '+warnings[0]+' See the calculation report.' : '';
}
function signed(value, precision = null) {
  return (value >= 0 ? '+' : '')+(precision ? Number(value.toPrecision(precision)).toString() : String(value));
}
function analysisTree(value, depth = 0) {
  const root = node('div',null,'analysis-tree');
  if (value == null || typeof value !== 'object') { root.textContent = typeof value === 'number' ? automaticText(value) : String(value ?? '—'); return root; }
  for (const [key,item] of Object.entries(value)) {
    if (item != null && typeof item === 'object') {
      const details = node('details'); details.append(node('summary',displayKey(key)));
      let expanded = false;
      details.addEventListener('toggle',() => { if (details.open && !expanded) { expanded = true; details.append(analysisTree(item,depth+1)); } });
      root.append(details);
    }
    else { const row = node('div',null,'analysis-row'); row.append(node('span',displayKey(key)),node('span',typeof item === 'number' ? automaticText(item) : String(item ?? '—'))); root.append(row); }
  }
  return root;
}
function appendMessages(target, title, values, warning = false) {
  if (!values?.length) return;
  const section = node('div',null,'notes-group'); section.append(node('h3',title));
  for (const value of values) {
    if (typeof value === 'string') section.append(node('p',value,warning ? 'note-warning' : ''));
    else section.append(analysisTree(value));
  }
  target.append(section);
}
function renderInspection() {
  const panel = $('inspection-panel'); $('component-count').textContent = `${design?.parts.length ?? 0} components`;
  if (activeTool !== 'components' && activeTool !== 'tools') return;
  panel.replaceChildren();
  $('note-count').textContent = design ? design.warnings.length+design.requirements.length+design.notes.length : 0;
  if (inspection === 'tools') {
    const content = node('div',null,'results-list');
    const extension = node('div'); extension.id = 'analysis-tools-extension'; content.append(extension); panel.append(content); events.dispatchEvent(new Event('tools')); return;
  }
  if (!design) { panel.append(node('p','Generate a design to inspect its components and calculations.','empty-state')); return; }
  if (inspection === 'components') {
    const actions = node('div',null,'component-actions'), all = node('button','Select all','text-button'), clear = node('button','Clear selection','text-button');
    all.addEventListener('click',() => { viewer.setSelection(design.parts.map(p => p.index)); renderInspection(); });
    clear.addEventListener('click',() => { viewer.setSelection([]); renderInspection(); });
    actions.append(all,clear,node('span',`${viewer.selected.size} selected · selection defines export scope`)); panel.append(actions);
    const head = node('div',null,'component-row header'); head.append(node('span','SEL'),node('span','VIEW'),node('span','COMPONENT'),node('span','ROLE'),node('span','ENVELOPE · MM')); panel.append(head);
    for (const part of design.parts) {
      const row = node('div',null,'component-row'+(viewer.selected.has(part.index) ? ' selected' : ''));
      const checkbox = node('input'); checkbox.type = 'checkbox'; checkbox.checked = viewer.selected.has(part.index); checkbox.setAttribute('aria-label',`Select ${part.name}`);
      checkbox.addEventListener('change',() => { const selection = new Set(viewer.selected); if (checkbox.checked) selection.add(part.index); else selection.delete(part.index); viewer.setSelection(selection); renderInspection(); });
      const visible = !viewer.hidden.has(part.index), eye = node('button',visible ? '◉' : '○','visibility'); eye.setAttribute('aria-pressed',String(visible)); eye.setAttribute('aria-label',`${visible ? 'Hide' : 'Show'} ${part.name}`);
      eye.title = viewer.isVisible(part) ? 'Visible' : 'Hidden by component or support/housing filter';
      eye.addEventListener('click',() => { viewer.setVisibility(part.index,!visible); renderInspection(); });
      const name = node('span',part.name.replaceAll('_',' '),'component-name'); name.title = part.name;
      const size = part.bounds_mm.minimum.map((v,i) => Number((part.bounds_mm.maximum[i]-v).toFixed(2))).join(' × ');
      row.append(checkbox,eye,name,node('span',displayKey(part.role),'component-role'),node('span',size,'component-size')); panel.append(row);
    }
    events.dispatchEvent(new CustomEvent('components',{detail:{panel}}));
  } else if (inspection === 'results') {
    const content = node('div',null,'results-list');
    if (!currentValid()) content.append(node('p','These calculations describe the last valid preview.','note-warning'));
    content.append(node('h3','Canonical calculation results')); const list = node('ul'); for (const metric of design.metrics) list.append(node('li',metric)); content.append(list);
    const details = node('details'); details.append(node('summary','Detailed calculation data'),analysisTree(design.analysis)); content.append(details);
    const button = node('button','Download calculation report'); button.dataset.exportKind = 'report'; button.disabled = !currentValid(); button.addEventListener('click',() => runExport('report')); content.append(button); panel.append(content);
  } else {
    const content = node('div',null,'results-list');
    appendMessages(content,'Construction warnings',design.warnings,true); appendMessages(content,'Requirements',design.requirements,true); appendMessages(content,'Model notes',design.notes); appendMessages(content,'Accuracy & limits',design.limitations);
    panel.append(content);
  }
}

// One application dialog owns focus and the modal action lifecycle. No native
// confirm() boxes, implicit document replacement or automatic recovery import.
function dialog(title, body, actions = [{label:'Close',value:null}], {dismiss = true} = {}) {
  const modal = $('app-dialog'); if (modal.open) modal.finish?.(null);
  $('dialog-title').textContent = title; $('dialog-body').replaceChildren(typeof body === 'string' ? node('p',body) : body); $('dialog-actions').replaceChildren();
  return new Promise(resolve => {
    let done = false;
    const finish = value => { if (done) return; done = true; modal.removeEventListener('cancel',cancel); modal.finish = null; if (modal.open) modal.close(); resolve(value); };
    const cancel = event => { event.preventDefault(); if (dismiss) finish(null); };
    for (const action of actions) { const button = node('button',action.label,action.primary ? 'primary' : ''); button.disabled = !!action.disabled; button.addEventListener('click',() => finish(action.value)); $('dialog-actions').append(button); }
    $('dialog-close').onclick = () => { if (dismiss) finish(null); }; $('dialog-close').hidden = !dismiss;
    // Only finish() closes this dialog. Listening to the asynchronous native
    // close event would let a previous dialog's queued event close its successor.
    modal.finish = finish; modal.addEventListener('cancel',cancel); modal.showModal();
  });
}
function documentShortcut(event) {
  if (!(event.ctrlKey || event.metaKey) || $('app-dialog').open) return;
  const key = event.key.toLowerCase();
  if (key === 's') { event.preventDefault(); saveProject({saveAs:event.shiftKey}); }
  if (key === 'n') { event.preventDefault(); newDocument(); }
  if (key === 'o') { event.preventDefault(); if (!busy && !actionConfirmation && catalog) $('project-file').click(); }
  if (key === 'z' || key === 'y') {
    // Let text controls keep the browser's own text-edit undo history.
    const target = event.target;
    if (target?.isContentEditable || target?.tagName === 'TEXTAREA' || target?.tagName === 'INPUT' && !['button','checkbox','radio','range','submit'].includes(target.type)) return;
    event.preventDefault(); if (!busy && !actionConfirmation) { if (event.shiftKey || key === 'y') doc.redo(); else doc.undo(); }
  }
}
async function protectChanges() {
  if (!doc.dirty) return true;
  const token = currentToken(), source = design;
  const choice = await dialog('Keep your current design?', 'This design has unsaved changes. Save a project file before replacing it, or discard these changes.',[{label:'Cancel',value:'cancel'},{label:'Discard changes',value:'discard'},{label:'Save project',value:'save',primary:true,disabled:!documentActionReady()}]);
  if (!isCurrent(token) || source !== design || busy || actionConfirmation) return false;
  if (choice === 'save') return await saveProject();
  return choice === 'discard';
}
function projectCheck(project) {
  if (!project || project.format !== 'solidcraft-riduttori/1' || Object.hasOwn(project,'selected_export') || !catalog.families.some(f => f.key === project.family) || !project.parameters || typeof project.parameters !== 'object' || Array.isArray(project.parameters)) throw Error('Choose a complete RatioLab project JSON file. Selected-export snapshots cannot replace a complete project.');
}
async function openProject(project, name) {
  if (!catalog || busy || actionConfirmation) return false;
  try { projectCheck(project); } catch (error) { await dialog('Project could not be opened',error.message); return false; }
  if (!await protectChanges()) return false;
  const token = currentToken(); clearTimeout(generationTimer); invalidate('Opening project…'); busy = true; renderFields(); updateActions();
  const serial = ++operationSerial;
  try {
    sourceParameters = null;
    const result = await engine.request('import_project',{project});
    if (!isCurrent(token) || serial !== operationSerial) return false;
    const nextSchema = await engine.request('schema',{family:result.family,parameters:result.values});
    if (!isCurrent(token) || serial !== operationSerial) return false;
    startup = true; schema = nextSchema; doc.replace(result.family,schema,result.values,name); previousRevision = doc.revision; initialClean = false; startup = false;
    rateEditing = false; rateSource = null; nominalFrame = null; viewer.supports = result.family === 'differential'; viewer.housing = false; viewer.setDesign(result,{fit:true}); design = result; lastFamily = result.family; phase = 0; validToken = currentToken(); rememberSourceParameters();
    viewer.supports = result.family === 'differential'; viewer.housing = false; $('show-supports').checked = viewer.supports; $('show-housing').checked = false;
    busy = false; schemaPending = false; updateFamilyHeader(); renderFields(); renderMetrics(); renderInspection(); updateActions();
    $('stage-message').hidden = true; $('stale-banner').hidden = true; $('motion-summary').textContent = result.motion.message;
    $('model-meta').textContent = `${result.triangle_count.toLocaleString()} triangles · nominal geometry · mm`;
    doc.markSaved(); storage.remember(name,{format:catalog.project_format,family:result.family,parameters:clone(result.values)}); status(`Opened ${name}${result.ignored_parameters?.length ? ` · ignored ${result.ignored_parameters.length} obsolete or unknown settings` : ''}`); events.dispatchEvent(new CustomEvent('design',{detail:{design,token:currentToken()}})); if (await requestPose(0)) nominalFrame = clone(viewer.frame); return true;
  } catch (error) {
    if (serial !== operationSerial || !isCurrent(token)) return false;
    busy = false; schemaPending = false; handleFatal(error); renderFields(); updateActions();
    if (error.name !== 'AbortError') await dialog('Project could not be opened',`${error.message} Your document has been kept.`);
    // Import invalidates the worker's active model before validation; rebuild
    // the preserved document to restore exports, without accepting the import.
    if (isCurrent(token) && !fatal) scheduleGeneration(0); return false;
  }
}
async function newDocument() {
  if (!catalog || busy || actionConfirmation || !await protectChanges()) return;
  clearTimeout(generationTimer); invalidate('Starting a new design…');
  startup = true; schema = catalog.families.find(f => f.key === 'parallel'); doc.replace(schema.key,schema); previousRevision = doc.revision; initialClean = true; startup = false;
  viewer.clear(); design = null; phase = 0; schemaPending = false; updateFamilyHeader(); renderFields(); renderInspection(); renderMetrics(); if (!recovery) storage.clearRecovery();
  if (await refreshSchema()) scheduleGeneration(0);
}
function documentActionReady() {
  if (analysisActive || actionConfirmation || busy || fatal || generationRunning || schemaPending) return false;
  if (currentValid()) return true;
  return !!design && rateEditing && rateSource === design && !!schema && !Object.keys(doc.values(schema,linkedFields()).errors).length;
}
function documentSnapshotMatches({token,current,operation}) {
  return isCurrent(token) && design === current && operationSerial === operation && !!validToken && isCurrent(validToken) &&
    !rateEditing && !ratePending && !generationRunning && !schemaPending && !fatal && !analysisActive;
}
async function confirmDocumentAction() {
  if (analysisActive || actionConfirmation || busy || fatal || generationRunning || schemaPending || !design) return null;
  const snapshot = {token:currentToken(),current:design,operation:operationSerial};
  actionConfirmation = true; updateActions();
  try {
    if (rateEditing || ratePending) await commitRates();
    return documentSnapshotMatches(snapshot) ? snapshot : null;
  } finally { actionConfirmation = false; updateActions(); }
}
async function saveProject({saveAs = false} = {}) {
  const snapshot = await confirmDocumentAction(); if (!snapshot || busy || !documentSnapshotMatches(snapshot)) return false;
  const {token,current} = snapshot;
  busy = true; renderFields(); updateActions();
  try {
    const result = await engine.request('export',{design_id:current.design_id,kind:'project'});
    if (!documentSnapshotMatches(snapshot)) return false;
    let name = doc.name === 'Untitled design' ? `${doc.family}.config.json` : doc.name.endsWith('.json') ? doc.name : doc.name+'.config.json';
    if (saveAs) {
      const body = node('label',null,'dialog-field'), input = node('input'); input.type = 'text'; input.value = name; body.append(node('span','Project filename'),input);
      if (await dialog('Save project as',body,[{label:'Cancel',value:null},{label:'Save',value:'save',primary:true}]) !== 'save' || !documentSnapshotMatches(snapshot)) return false;
      name = input.value.trim(); if (!name) return false; if (!name.endsWith('.json')) name += '.config.json';
    }
    downloadBlob(new Blob([result.buffers[result.buffer]],{type:result.mime}),name);
    const project = {format:catalog.project_format,family:current.family,parameters:clone(current.values)};
    doc.markSaved(name); storage.remember(name,project); status('Project download prepared · keep the file to reopen it later.'); return true;
  } catch (error) { if (isCurrent(token) && error.name !== 'AbortError') { status(error.message,'error'); handleFatal(error); } return false; }
  finally { busy = false; renderFields(); updateActions(); }
}
async function exportDialog() {
  const snapshot = await confirmDocumentAction(); if (!snapshot || busy || !documentSnapshotMatches(snapshot)) return;
  const body = node('div'), group = node('label',null,'dialog-field'), format = node('select');
  format.id = 'export-format'; group.htmlFor = format.id; group.append(node('span','Export format'),format);
  for (const [key,label] of [['step','STEP · CAD solids + metadata'],['stl','STL · printable meshes + metadata'],['profiles','SVG + DXF · planar profiles'],['bom','Component list · CSV + JSON'],['report','Calculation report · TXT + JSON'],['package','Complete package · all formats + preview'],['project','Project · editable RatioLab JSON']]) { const option = node('option',label); option.value = key; format.append(option); }
  body.append(group);
  const selection = selectedIndices(), scope = node('label',null,'check-control'), checkbox = node('input'); checkbox.id = 'export-selection'; checkbox.type = 'checkbox'; checkbox.checked = !!selection.length; checkbox.disabled = !selection.length;
  scope.append(checkbox,node('span',`Export selected components only (${selection.length} selected)`)); body.append(scope);
  const note = node('p',`The project format always saves the complete source configuration. Geometry and calculation exports can describe an explicit component subset. Exports use nominal coordinates, independently of section, explosion and playback.`,'export-scope'); body.append(note);
  const packageNote = node('p','Complete packages capture your real nominal preview using this camera and visible components. Selected packages capture only the selected subset.','dialog-warning'); body.append(packageNote);
  format.addEventListener('change',() => { checkbox.disabled = format.value === 'project' || !selection.length; if (format.value === 'project') checkbox.checked = false; });
  const choice = await dialog('Export your design',body,[{label:'Cancel',value:null},{label:'Download export',value:'export',primary:true}]);
  if (choice && documentSnapshotMatches(snapshot) && !busy) await runExport(format.value,checkbox.checked ? selection : null);
}
async function runExport(kind, indices = null) {
  if (kind === 'project') return saveProject();
  const snapshot = await confirmDocumentAction(); if (!snapshot || busy || !documentSnapshotMatches(snapshot)) return false;
  const {token,current} = snapshot; busy = true; setPlaying(false); updateActions(); renderFields(); status(`Preparing ${kind} export…`,'warning');
  try {
    const payload = {design_id:current.design_id,kind}; if (indices?.length) payload.indices = indices;
    if (kind === 'package') {
      // Rates can add phase offsets. Preserve the generation-time construction
      // frame rather than mistaking the updated plan's phase zero for nominal.
      if (!nominalFrame) throw Error('Wait for the initial model frame before capturing a package.');
      payload.preview_png = await viewer.captureNominal(nominalFrame,indices);
      if (!documentSnapshotMatches(snapshot)) return false;
    }
    const result = await engine.request('export',payload);
    if (!documentSnapshotMatches(snapshot)) return false;
    downloadBlob(new Blob([result.buffers[result.buffer]],{type:result.mime}),result.name);
    status(`${result.name} · ${(result.bytes/1024).toFixed(1)} KiB · ${indices?.length ? indices.length+' selected components' : 'complete design'} download prepared.`); return true;
  } catch (error) { if (isCurrent(token) && error.name !== 'AbortError') { status(error.message,'error'); handleFatal(error); } return false; }
  finally { busy = false; renderFields(); updateActions(); renderInspection(); }
}
async function recentDialog() {
  const items = recent(), body = node('div');
  if (!items.length) body.append(node('p','Saved and opened projects will appear here. This list is stored in this browser.'));
  for (const [i,item] of items.entries()) {
    const row = node('div',null,'recent-row'), info = node('div'); info.append(node('strong',item.name),node('p',new Date(item.time).toLocaleString()));
    const button = node('button','Open'); button.addEventListener('click',() => $('app-dialog').finish?.(i)); row.append(info,button); body.append(row);
  }
  const index = await dialog('Recent projects',body);
  if (typeof index === 'number' && items[index]) await openProject(items[index].project,items[index].name);
}
async function recoverDocument() {
  if (!recovery || !catalog || busy) return;
  const body = node('div'); body.append(node('p',`${recovery.name} · ${new Date(recovery.time).toLocaleString()}`),node('p','Restore the unsaved parameter drafts from this browser. Invalid or incomplete entries remain available for correction.'));
  if (await dialog('Recover an unsaved design',body,[{label:'Cancel',value:null},{label:'Restore draft',value:'recover',primary:true}]) !== 'recover') return;
  if (!await protectChanges()) return;
  const savedRecovery = recovery;
  try {
    const family = catalog.families.find(f => f.key === savedRecovery.state.family); if (!family) throw Error('The recovery uses an unsupported model.');
    clearTimeout(generationTimer); invalidate('Restoring parameter drafts…'); startup = true; schema = family;
    doc.replace(family.key,schema,{},savedRecovery.name,{recovery:savedRecovery}); previousRevision = doc.revision; initialClean = false; startup = false;
    recovery = null; $('recovery-banner').hidden = true; updateFamilyHeader();
    if (await refreshSchema()) { renderFields(); scheduleGeneration(0); }
  } catch (error) { startup = false; status('Recovery could not be restored: '+error.message,'error'); }
}
async function showHelp() {
  const body = node('div');
  body.append(node('h3','Choose · configure · preview · export'),node('p','Choose a model and construction, then edit Dimensions, Motion and Assembly. Every numeric field accepts decimal points or commas. Incomplete and invalid entries remain visible; exports wait for a valid matching model.'),node('p','Drag the preview to orbit, scroll to zoom, or use Fit. With the canvas focused, arrow keys orbit and + / − zoom. Supports and Housing filter canonical component roles. Section removes the positive-Y half without adding a cap. Explosion is an inspection view and clears when motion starts.'),node('h3','Documents & downloads'),node('p','Save downloads a desktop-compatible JSON project. Recent projects and unsaved draft recovery stay in this browser. New or Open asks before discarding unsaved work. Browser storage may be cleared by private browsing or site-data settings; keep downloaded project files.'),node('h3','Accuracy & sources'),node('p','RatioLab generates nominal dimensions and ideal motion. Sampled surfaces and prescribed strain-wave deformation do not establish continuous clearance, strength, bearing life or manufacturing readiness. Read model warnings and requirements before using exported geometry.'));
  const links = node('p');
  for (const [title,url] of [['Technical references','https://github.com/NoOneExceptEnderk/RatioLab/tree/main/docs/technical'],['Usage','README.txt'],['Corresponding source','source.zip'],['License','LICENSE'],['Runtime notices','notices/README.txt']]) { const a = node('a',title); a.href = url; if (url.startsWith('http')) { a.target = '_blank'; a.rel = 'noopener'; } links.append(a,document.createTextNode(' · ')); }
  body.append(links); await dialog('Using RatioLab in your browser',body);
}
async function boot({retry = false} = {}) {
  startup = true; fatal = false; validToken = null; setPlaying(false); updateActions();
  if (retry) { sourceParameters = null; engine.cancel('Restart requested'); }
  stageMessage('Preparing your workspace','Loading the local calculation engine…',{loading:true});
  try {
    await engine.ready; catalog = await engine.request('catalog');
    $('family').replaceChildren(); for (const family of catalog.families) { const option = node('option',family.label); option.value = family.key; $('family').append(option); }
    if (!catalog.families.some(f => f.key === doc.family)) throw Error('The current model is missing from the catalog.');
    schema = familyDefinition(); doc.ensure(schema); startup = false; previousRevision = doc.revision; updateFamilyHeader();
    if (recovery) $('recovery-banner').hidden = false;
    if (await refreshSchema()) { renderFields(); updateActions(); scheduleGeneration(0); }
  } catch (error) { startup = false; fatal = true; stageMessage('RatioLab could not start',error.message,{retry:true}); status(error.message,'error'); updateActions(); }
}

function setup() {
  try { viewer = new ModelViewer($('model-canvas')); }
  catch (error) { stageMessage('3D preview unavailable',error.message); status(error.message,'error'); return; }
  viewer.addEventListener('context',({detail}) => {
    if (detail.lost) { setPlaying(false); stageMessage('Graphics context lost','The browser will try to restore the preview.'); }
    else { $('stage-message').hidden = !!design; status('Graphics context restored.'); }
    updateActions();
  });
  viewer.addEventListener('error',({detail}) => { setPlaying(false); stageMessage('Preview unavailable',detail.message); status(detail.message,'error'); });
  viewer.addEventListener('camera',({detail}) => {
    const name = detail?.view;
    $('view-label').textContent = name ? name.toUpperCase() : 'CUSTOM VIEW';
    for (const [id,key] of [['isometric-view','isometric'],['top-view','top'],['front-view','front']]) $(id).setAttribute('aria-pressed',String(key === name));
  });
  engine = new EngineClient({onProgress: event => {
    if (['runtime','engine'].includes(event.stage)) { if (!$('stage-message').hidden) $('loading-detail').textContent = event.detail || (event.stage === 'runtime' ? 'Loading the local calculation engine…' : 'Preparing geometry modules…'); }
    // Pose RPCs produce operation events too; never replace useful document
    // status thirty times per second with worker plumbing.
  }});
  doc.addEventListener('change',onDocumentChange);
  $('family').addEventListener('change',() => doc.selectFamily($('family').value,catalog.families.find(f => f.key === $('family').value)));
  for (const b of document.querySelectorAll('[data-tab]')) b.addEventListener('click',() => switchTab(b.dataset.tab));
  for (const b of document.querySelectorAll('[data-inspection]')) b.addEventListener('click',() => chooseInspection(b.dataset.inspection));
  for (const list of document.querySelectorAll('[role=tablist]')) list.addEventListener('keydown',event => {
    if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
    const tabs = [...list.querySelectorAll('[role=tab]')], active = tabs.indexOf(document.activeElement); if (active < 0) return;
    event.preventDefault(); const i = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length-1 : (active+(event.key === 'ArrowRight' ? 1 : -1)+tabs.length)%tabs.length;
    tabs[i].click(); tabs[i].focus();
  });
  $('new-document').addEventListener('click',newDocument); $('open-document').addEventListener('click',() => { if (!busy && catalog) $('project-file').click(); });
  $('project-file').addEventListener('change',async () => {
    const file = $('project-file').files[0]; $('project-file').value = ''; if (!file) return;
    if (file.size > 1048576) { await dialog('Project could not be opened','Project JSON is limited to 1 MiB.'); return; }
    const token = currentToken();
    try { const project = JSON.parse(await file.text()); if (isCurrent(token)) await openProject(project,file.name); }
    catch (error) { if (isCurrent(token)) await dialog('Project could not be opened',error.message); }
  });
  $('save-document').addEventListener('click',() => saveProject()); $('save-as-document').addEventListener('click',() => saveProject({saveAs:true})); $('export-document').addEventListener('click',exportDialog); $('recent-documents').addEventListener('click',recentDialog);
  $('undo').addEventListener('click',() => { if (!busy) doc.undo(); }); $('redo').addEventListener('click',() => { if (!busy) doc.redo(); });
  $('reset-family').addEventListener('click',async () => {
    if (await dialog('Reset this model?','Restore this model’s default dimensions and construction. Other model drafts are kept. You can Undo this change.',[{label:'Cancel',value:null},{label:'Reset model',value:'reset',primary:true}]) !== 'reset') return;
    doc.checkpoint(); delete doc.state.families[doc.family]; schema = familyDefinition(); doc.ensure(schema); doc.changed();
  });
  $('retry-engine').addEventListener('click',() => boot({retry:true}));
  $('cancel-generation').addEventListener('click',cancelOperations);
  $('help').addEventListener('click',showHelp); $('recover-document').addEventListener('click',recoverDocument); $('dismiss-recovery').addEventListener('click',() => { recovery = null; storage.clearRecovery(); saveRecovery(); $('recovery-banner').hidden = true; });
  $('fit-view').addEventListener('click',() => viewer.fit());
  for (const [id,key] of [['show-supports','supports'],['show-housing','housing'],['section-view','section']]) $(id).addEventListener('change',() => { viewer[key] = $(id).checked; if (key !== 'section') viewer.updateFraming(); viewer.render(); renderInspection(); });
  $('explosion').addEventListener('input',() => { setPlaying(false); viewer.explosion = Number($('explosion').value); viewer.render(); });
  $('play-motion').addEventListener('click',() => setPlaying(!playing)); $('reset-motion').addEventListener('click',resetMotion);
  $('motion-rpm').addEventListener('input',() => doc.editNumber('input_rpm',$('motion-rpm').value));
  $('motion-rpm').addEventListener('keydown',event => { if (event.key === 'Enter') { event.preventDefault(); commitRates(); } });
  $('motion-rpm').addEventListener('blur',() => { if (rateEditing) commitRates(); });
  $('rpm-slider').addEventListener('input',() => editSpeed(Math.round(unscaleRPM(Number($('rpm-slider').value)))));
  for (const [id,delta] of [['rpm-minus',-1],['rpm-plus',1]]) $(id).addEventListener('click',() => editSpeed((design?.values.input_rpm ?? 0)+delta));
  $('front-view').addEventListener('click',() => selectView('front'));
  for (const [id,name] of [['isometric-view','isometric'],['top-view','top']]) $(id).addEventListener('click',() => selectView(name));
  $('text-size').addEventListener('change',() => { document.documentElement.style.setProperty('--text-scale',$('text-size').value); scheduleOverlayPlacement(); });
  $('close-tool-dock').addEventListener('click',closeToolDock);
  for (const button of document.querySelectorAll('[data-tool]')) button.addEventListener('click',() => openTool(button.dataset.tool));
  $('pick-mode').addEventListener('change',() => { if ($('pick-mode').value !== 'navigate') openTool('components'); events.dispatchEvent(new CustomEvent('pickmode',{detail:{mode:$('pick-mode').value}})); });
  $('show-bom').addEventListener('click',() => showDocuments('bom')); $('show-report').addEventListener('click',() => showDocuments('report')); $('show-notes').addEventListener('click',showNotes); $('warning-details').addEventListener('click',showNotes);
  document.addEventListener('click',event => { for (const menu of document.querySelectorAll('.popover[open]')) if (!menu.contains(event.target) || event.target.closest('button') && !event.target.closest('.motion-palette')) menu.open = false; });
  document.addEventListener('toggle',event => {
    if (!event.target.open) {
      const copy = event.target.querySelector(':scope>.popover-body, :scope>.help-copy');
      if (copy) resetOverlayPlacement(copy);
    }
    scheduleOverlayPlacement();
  },true);
  document.addEventListener('scroll',scheduleOverlayPlacement,true);
  window.addEventListener('resize',scheduleOverlayPlacement);
  document.addEventListener('keydown',event => { if (event.key === 'Escape' && !$('app-dialog').open) { closeToolDock(); for (const menu of document.querySelectorAll('.popover[open]')) menu.open = false; } });
  $('playback-speed').addEventListener('change',() => { lastTick = 0; });
  document.addEventListener('visibilitychange',() => { if (document.hidden) setPlaying(false); });
  window.addEventListener('beforeunload',event => { saveRecovery(); if (doc.dirty) { event.preventDefault(); event.returnValue = ''; } });
  window.addEventListener('pagehide',() => { saveRecovery(); setPlaying(false); });
  document.addEventListener('keydown',documentShortcut);
  // W3 extension boundary. Callers must retain the snapshot token and recheck
  // matches() after every await. No analysis result may outlive invalidation.
  const api = {
    events, engine, viewer, document:doc,
    snapshot() { return currentValid() ? {token:{...currentToken(),operation:operationSerial,designId:design.design_id},design,phase,parameters:clone(design.values),family:doc.family,indices:selectedIndices()} : null; },
    matches(token) { return currentValid() && isCurrent(token) && (token.operation == null || token.operation === operationSerial) && (token.designId == null || token.designId === design.design_id); },
    async request(method,payload = {}) { const snapshot = this.snapshot(); if (!snapshot) throw Error('Wait for a valid current model.'); if (['documents','metrology','search','interference','backlash'].includes(method)) events.dispatchEvent(new CustomEvent('querybegin',{detail:{method}})); const result = await engine.request(method,{design_id:snapshot.design.design_id,...payload}); if (!this.matches(snapshot.token)) throw new DOMException('The document changed.','AbortError'); return result; },
    applyParameters(values) {
      if (!currentValid()) throw Error('Wait for a valid current model.');
      const definitions = new Map([...schema.fields,...schema.options].map(f => [f.key,f]));
      for (const [key,value] of Object.entries(values)) {
        const field = definitions.get(key); if (!field) throw Error('Unknown parameter: '+key);
        if (field.type === 'choice' && !field.choices.some(c => c.value === value) || field.type === 'boolean' && typeof value !== 'boolean' || ['number','integer'].includes(field.type) && (typeof value !== 'number' || !Number.isFinite(value))) throw Error('Invalid parameter value: '+key);
      }
      doc.checkpoint();
      const numbers = clone(doc.entries);
      for (const [key,value] of Object.entries(values)) {
        const field = definitions.get(key);
        if (['choice','boolean'].includes(field.type)) doc.draft.options[key] = value;
        else numbers[key] = {text:automaticText(value),exact:value,typed:false};
      }
      // ensure() selects or creates the context after option changes; preserve
      // this explicit transaction's numeric proposal in that target context.
      doc.ensure(schema); Object.assign(doc.entries,numbers);
      doc.changed();
    },
    requestPose, setPlaying, showDialog:dialog, downloadBlob, cancelOperations,
    async pauseForAnalysis() { setPlaying(false); await poseCompletion; },
    setAnalysisActive(value) { analysisActive = !!value; if (value) setPlaying(false); updateActions(); },
    restoreInspection(frame,savedPhase,selection) { setPlaying(false); viewer.applyFrame(frame); phase = savedPhase; $('motion-phase').textContent = `${phase.toFixed(2)} rad`; viewer.setSelection(selection); renderInspection(); },
    openTool, closeToolDock, setDockPanel, registerTool,
    get pickMode() { return $('pick-mode').value; },
    get nominalFrame() { return nominalFrame ? clone(nominalFrame) : null; },
    get playing() { return playing; },
    get toolsMenu() { return $('tools-menu-extension'); },
    get dock() { return $('tool-dock'); },
    refreshInspection:renderInspection, chooseInspection,
    get schema() { return schema; }, get catalog() { return catalog; },
  };
  globalThis.ratiolab = api; initTools(api); boot();
}
setup();
