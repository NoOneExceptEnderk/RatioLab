// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
import {webModules} from './webapp_modules.mjs';

const graph = webModules(fileURLToPath(new URL('../',import.meta.url)));
const {mcpConfiguration} = (await graph.load('./mcp-settings.js')).namespace;
const {UI_CATALOG} = (await graph.load('./ui-catalog.js')).namespace;
const {normalizePreferences} = (await graph.load('./preferences.js')).namespace;
const {clients,cases} = JSON.parse(fs.readFileSync(0,'utf8'));
assert.deepEqual(Object.keys(UI_CATALOG.mcp),Object.keys(clients));
for (const [key,{name,filename,guide}] of Object.entries(UI_CATALOG.mcp)) {
  assert.deepEqual([name,filename,guide],clients[key]);
}
for (const {paths,expected} of cases) {
  for (const [client,configuration] of Object.entries(expected)) {
    assert.equal(mcpConfiguration(client,paths),configuration,client);
  }
  assert.deepEqual(normalizePreferences({mcp_client_config:paths}).mcp_client_config,paths);
}
const valid = cases[0].paths;
for (const [key,value] of [
  ['command',''],['command','./RatioLab-MCP'],['command','ratiolab-mcp --workspace'],
  ['command','/path\t/RatioLab-MCP'],['workspace',''],['workspace','C:Projects'],
  ['workspace','~/Projects'],['workspace','\\server'],['workspace','/tmp/\nFolder'],
]) {
  assert.equal(mcpConfiguration('codex',{...valid,[key]:value}),null);
}
assert.equal(mcpConfiguration('constructor',valid),null);
assert.deepEqual(normalizePreferences({mcp_client_config:{command:true,workspace:1}}).mcp_client_config,
                 {command:'',workspace:''});
