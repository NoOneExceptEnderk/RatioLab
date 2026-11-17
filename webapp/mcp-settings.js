// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
import {UI_CATALOG} from './ui-catalog.js';

const clients = UI_CATALOG.mcp;
const fields = {command:'MCP executable', workspace:'MCP workspace'};
const pathTokens = {
  __RATIOLAB_MCP_COMMAND__:'command',
  __RATIOLAB_MCP_WORKSPACE__:'workspace',
};

function validPath(key, value) {
  if (typeof value !== 'string' || /[\x00-\x1f\x7f]/.test(value)) return false;
  return (key === 'command' && value === 'ratiolab-mcp') ||
    value.startsWith('/') || /^[a-z]:[\\/]/i.test(value) || /^\\\\[^\\/]+\\[^\\/]+/.test(value);
}

export function mcpConfiguration(client, paths) {
  if (!Object.hasOwn(clients,client) || !Object.keys(fields).every(key=>validPath(key,paths?.[key]))) return null;
  // Replace the quoted tokens once, so path contents never change the template.
  return clients[client].template.replace(/"(__RATIOLAB_MCP_COMMAND__|__RATIOLAB_MCP_WORKSPACE__)"/g,
    (_,token)=>JSON.stringify(paths[pathTokens[token]]));
}

const element = (tag, text='', className='') => {
  const node = document.createElement(tag);
  if (text) node.textContent = text;
  if (className) node.className = className;
  return node;
};

function icon(path) {
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns,'svg'), shape = document.createElementNS(ns,'path');
  svg.setAttribute('viewBox','0 0 24 24');
  svg.setAttribute('aria-hidden','true');
  shape.setAttribute('d',path);
  svg.append(shape);
  return svg;
}

export function renderMcpSettings(page, api) {
  const workspace = element('div','','mcp-workspace');
  const heading = element('h3','','mcp-workspace-heading');
  heading.append(icon('M3 7V5h6l2 2h10v12H3V7Z'),element('span','MCP workspace'));
  const inputs = {};
  const help = element('p','Enter absolute local paths. Use ratiolab-mcp for a Python wheel.','muted');
  help.id = 'mcp-path-help';
  workspace.append(heading);
  for (const [key,title] of Object.entries(fields)) {
    const label = element('label','','mcp-path');
    const input = inputs[key] = element('input');
    input.type = 'text';
    input.value = api.preferences.mcp_client_config[key];
    input.spellcheck = false;
    input.autocomplete = 'off';
    input.setAttribute('autocapitalize','off');
    input.setAttribute('aria-describedby',help.id);
    label.append(element('span',title),input);
    workspace.append(label);
  }
  workspace.append(help,element('p','Use RatioLab Desktop to register clients automatically.','muted'));
  const getPaths = () => ({command:inputs.command.value,workspace:inputs.workspace.value});
  let saved = getPaths();
  function savePaths() {
    const paths = getPaths();
    if (saved.command === paths.command && saved.workspace === paths.workspace) return;
    saved = paths;
    api.change('mcp_client_config',paths);
  }

  const directory = element('div','','mcp-directory');
  const title = element('h3','MCP clients');
  title.id = 'mcp-directory-title';
  const search = element('input');
  search.type = 'search';
  search.placeholder = 'Search clients';
  search.setAttribute('aria-label','Search clients');
  const searchBox = element('div','','mcp-search');
  searchBox.append(icon('M15.5 15.5 21 21M18 11a7 7 0 1 1-14 0 7 7 0 0 1 14 0Z'),search);
  directory.append(title,searchBox);

  const scroll = element('div','','mcp-client-scroll');
  scroll.tabIndex = 0;
  scroll.setAttribute('role','region');
  scroll.setAttribute('aria-labelledby',title.id);
  const list = element('ul','','mcp-client-list');
  const empty = element('p','No clients found','mcp-empty muted');
  empty.hidden = true;
  empty.setAttribute('role','status');
  scroll.append(list,empty);

  let pathsRevision = 0;
  const rows = Object.entries(clients).map(([id,{name,filename,guide}])=>{
    const row = element('li','','mcp-client-row');
    row.dataset.client = id;
    const title = element('div','','mcp-client-name');
    const nameLabel = element('strong',name);
    nameLabel.id = 'mcp-client-'+id;
    nameLabel.dataset.noI18n = '';
    title.append(nameLabel);
    if (filename) title.append(element('code',filename,'muted'));
    const feedback = element('div','','mcp-copy-feedback muted');
    feedback.setAttribute('role','status');
    title.append(feedback);
    const actions = element('div','','mcp-client-actions');
    if (guide) {
      const link = element('a','','mcp-icon-action');
      link.href = guide;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.title = 'Setup guide';
      link.setAttribute('aria-label','Setup guide');
      link.setAttribute('aria-describedby',nameLabel.id);
      const glyph = element('span','','mcp-guide-icon');
      glyph.setAttribute('aria-hidden','true');
      link.append(glyph);
      actions.append(link);
    }
    const copy = element('button','','flat mcp-icon-action');
    copy.type = 'button';
    copy.title = 'Copy configuration';
    copy.setAttribute('aria-label','Copy configuration');
    copy.setAttribute('aria-describedby',nameLabel.id);
    copy.append(icon('M8 8h12v12H8zM16 8V4H4v12h4'));
    actions.append(copy);
    row.append(title,actions);

    const fallback = element('textarea','','mcp-configuration');
    fallback.hidden = true;
    fallback.readOnly = true;
    fallback.rows = 3;
    fallback.setAttribute('aria-labelledby',nameLabel.id);
    row.append(fallback);
    copy.addEventListener('click',async ()=>{
      const configuration = mcpConfiguration(id,getPaths());
      if (!configuration) return;
      const revision = pathsRevision;
      let copied = false;
      try {
        await navigator.clipboard.writeText(configuration);
        copied = true;
      } catch {}
      if (revision !== pathsRevision || !page.contains(row)) return;
      feedback.textContent = copied ? 'Text copied' : 'Clipboard unavailable. Copy the configuration below.';
      fallback.hidden = copied;
      fallback.value = copied ? '' : configuration;
      if (!copied && !page.hidden && !row.hidden) {
        fallback.focus({preventScroll:true});
        fallback.select();
        scroll.scrollTop += row.getBoundingClientRect().top - scroll.getBoundingClientRect().top;
      }
    });
    list.append(row);
    return {row,copy,feedback,fallback,searchText:(name+'\n'+filename).toLowerCase()};
  });

  function updatePaths() {
    ++pathsRevision;
    const paths = getPaths();
    let valid = true;
    for (const [key,input] of Object.entries(inputs)) {
      const accepted = validPath(key,paths[key]);
      input.setAttribute('aria-invalid',String(Boolean(paths[key]) && !accepted));
      valid = valid && accepted;
    }
    for (const {copy,feedback,fallback} of rows) {
      copy.disabled = !valid;
      feedback.textContent = '';
      fallback.value = '';
      fallback.hidden = true;
    }
  }
  for (const input of Object.values(inputs)) {
    input.addEventListener('input',updatePaths);
    input.addEventListener('change',savePaths);
  }
  search.addEventListener('input',()=>{
    const query = search.value.trim().toLowerCase();
    for (const {row,searchText} of rows) row.hidden = !searchText.includes(query);
    const hasResults = rows.some(({row})=>!row.hidden);
    list.hidden = !hasResults;
    empty.hidden = hasResults;
    scroll.scrollTop = 0;
  });
  page.replaceChildren(element('h2','MCP'),workspace,directory,scroll);
  updatePaths();
  return savePaths;
}
