// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const module=new vm.SourceTextModule(fs.readFileSync(new URL('../webapp/ui-language.js',import.meta.url),'utf8'));
await module.link(()=>{throw Error('Unexpected translation dependency');});await module.evaluate();
const catalog=JSON.parse(fs.readFileSync(new URL('../src/ratiolab_resources/ui-translations.json',import.meta.url)));
const cases=JSON.parse(fs.readFileSync(process.argv[2]));
for(const [raw,languages] of cases)for(const [code,expected] of Object.entries(languages))
  assert.equal(module.namespace.translate(raw,code,catalog),expected,code+' '+JSON.stringify(raw));
console.log(cases.length+' technical templates agree across Python and JavaScript in all nine languages');
