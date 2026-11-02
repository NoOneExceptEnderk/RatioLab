// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source = new URL('../webapp/ui-language.js',import.meta.url);
const module = new vm.SourceTextModule(fs.readFileSync(source,'utf8'));
await module.link(()=>{throw Error('Unexpected localization dependency');}); await module.evaluate();
const data = JSON.parse(fs.readFileSync(new URL('../src/ratiolab_resources/ui-translations.json',import.meta.url)));
const {LANGUAGES,translate} = module.namespace;
assert.deepEqual(LANGUAGES,data.languages);
for (const code of Object.keys(LANGUAGES)) {
  for (const raw of ['2.000000000012345','−0,000000000003','M3×12','N·m','user-design.json','  \n']) assert.equal(translate(raw,code,data),raw);
  assert.ok(translate('At 1500.00000000001 rpm input',code,data).includes('1500.00000000001'));
  assert.ok(translate('Face width · mm',code,data).endsWith(' · mm'));
}
assert.equal(translate('A↔ Language','it',data),'A↔ Lingua');
assert.equal(translate('☀ Theme','it',data),'☀ Tema');
assert.equal(translate('Face width\u2009·\u2009mm','it',data),'Larghezza dentatura\u2009·\u2009mm');
console.log('Nine-language catalog and unchanged engineering values PASS');
