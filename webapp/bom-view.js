// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
import {ModelViewer} from './viewer.js';
import {rgb, themePalette, viewPalette} from './themes.js';

const labels = {buy:'Buy', make:'Make', define:'Select part', interface:'CAD interface'};

function element(tag, content, className) {
  const result = document.createElement(tag);
  if (content != null) result.textContent = content;
  if (className) result.className = className;
  return result;
}

export function buildBomPanel(data, design, preferences, palette) {
  const body = element('div', null, 'bom-panel');
  const heading = element('p', [data.family_label, data.variant].filter(Boolean).join(' · '), 'bom-caption');
  body.append(heading);
  const main = element('div', null, 'bom-main');
  const viewport = element('div', null, 'bom-viewport');
  const toolbar = element('div', null, 'bom-viewbar');
  const legend = element('span', null, 'bom-legend');
  toolbar.append(legend);
  const canvas = element('canvas');
  canvas.id = 'bom-preview';
  canvas.tabIndex = 0;
  canvas.setAttribute('aria-label', 'Bill of materials preview');
  canvas.setAttribute('aria-description', 'Drag to rotate. Use the arrow keys to turn and plus or minus to zoom.');
  const viewFooter = element('div', null, 'bom-view-footer');
  const selectedName = element('span', null, 'bom-active-component');
  const notice = element('span');
  notice.setAttribute('role', 'status');
  viewFooter.append(selectedName, notice);
  viewport.append(toolbar, canvas, viewFooter);

  const tablePanel = element('div', null, 'bom-table-panel');
  const scroll = element('div', null, 'bom-table-scroll');
  const table = element('table');
  table.setAttribute('aria-label', 'Additional components and CAD interfaces');
  const header = element('tr');
  for (const text of ['Component', 'Qty', 'Size / reference']) {
    const cell = element('th', text);
    cell.scope = 'col';
    header.append(cell);
  }
  const head = element('thead');
  head.append(header);
  const rows = element('tbody');
  rows.id = 'bom-rows';
  table.append(head, rows);
  scroll.append(table);
  tablePanel.append(scroll);
  if (!data.rows.some(row => row.quantity !== null)) {
    tablePanel.append(element('p', 'No extra parts specified for this configuration.', 'bom-caption'));
  }
  tablePanel.append(element('p', 'Dimensions are nominal.', 'bom-caption'));
  main.append(viewport, tablePanel);
  body.append(main);

  const details = element('div', null, 'bom-details');
  details.id = 'bom-details';
  details.setAttribute('aria-live', 'polite');
  const group = element('small');
  const part = element('h3');
  const count = element('p', null, 'bom-count');
  const description = element('p');
  const first = element('div');
  first.append(group, part, count, description);
  const cad = element('p');
  const second = element('div', null, 'bom-cad');
  second.append(element('h3', 'To complete in CAD'), cad);
  details.append(first, second);
  body.append(details);
  if (data.requirements.length) {
    const more = element('details', null, 'bom-requirements');
    const list = element('ul');
    list.append(...data.requirements.map(message => element('li', message)));
    more.append(element('summary', 'Assembly requirements'), list);
    body.append(more);
  }

  let view;
  const byIndex = new Map(), entries = [];
  const shown = new Set(data.context_indices);
  const context = design.parts.filter(part => shown.has(part.index));
  for (const item of data.rows) {
    const row = element('tr');
    const name = element('th');
    name.scope = 'row';
    const choose = element('button', item.label);
    choose.type = 'button';
    choose.setAttribute('aria-controls', ['bom-details', 'bom-preview'].join(' '));
    name.append(choose, element('small', labels[item.status]));
    const size = element('td', item.code || item.dimensions);
    if (item.code) size.append(element('small', item.dimensions));
    const quantity = element('td', item.quantity ?? '—', 'bom-quantity');
    if (item.quantity === null) quantity.setAttribute('aria-label', 'Quantity to define');
    row.append(name, quantity, size);
    const index = entries.length;
    row.addEventListener('click', () => select(index));
    rows.append(row);
    entries.push({row, choose, item});
    for (const component of item.indices) byIndex.set(component, index);
  }

  function select(index) {
    const {item} = entries[index];
    view?.setSelection(item.indices);
    for (const [position, {row, choose}] of entries.entries()) {
      const selected = index === position;
      row.classList.toggle('bom-selected', selected);
      choose.setAttribute('aria-pressed', String(selected));
    }
    legend.textContent = item.group;
    selectedName.textContent = item.label;
    group.textContent = item.group;
    part.textContent = item.label;
    count.textContent = item.count_basis;
    count.hidden = !item.count_basis;
    description.textContent = item.detail;
    cad.textContent = item.cad;
  }

  if (entries.length) select(0);

  function start() {
    try {
      view = new ModelViewer(canvas, {guides:false});
      view.supports = view.housing = true;
      view.contextOpacity = .15;
      view.pickableIndices = new Set(byIndex.keys());
      view.zoomSpeed = preferences.zoom_speed;
      view.rotationSpeed = preferences.rotation_speed;
      view.invertZoom = preferences.invert_zoom;
      view.mouseNavigation = preferences.mouse_navigation;
      const {theme, theme_customizations:customization} = preferences;
      const preset = viewPalette(theme, customization, null, {customized:false});
      const defaults = palette.selection.every((value, i) => value === preset.selection[i]);
      view.selectionColor = defaults ? rgb(themePalette(theme, customization).accent) : palette.selection;
      view.setDesign({...design, parts:context});
      if (entries.length) view.setSelection(entries[0].item.indices);
      canvas.addEventListener('keydown', event => {
        if (event.key === 'Home') {
          event.preventDefault();
          view.fit();
        }
      }, {signal:view.events.signal});
      view.addEventListener('context', ({detail}) => {
        notice.textContent = detail.lost ? 'The 3D preview is unavailable. The bill of materials remains usable.' : '';
      });
      view.addEventListener('surfaceclick', ({detail}) => {
        const component = view.pickComponent(detail.clientX, detail.clientY);
        const index = byIndex.get(component);
        if (index === undefined) return;
        select(index);
        entries[index].row.scrollIntoView({block:'nearest', inline:'nearest'});
      });
    } catch (error) {
      view?.dispose();
      view = null;
      canvas.hidden = true;
      notice.textContent = 'The 3D preview is unavailable. The bill of materials remains usable.';
    }
  }
  return {body, start, dispose() { view?.dispose(); view = null; }};
}
