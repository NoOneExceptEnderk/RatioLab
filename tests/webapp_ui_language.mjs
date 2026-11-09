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
  const messages = data.translations[code];
  const expected = key => code === 'en' ? key : messages[key];
  assert.equal(translate('Normal module [mm]',code,data),expected('Normal module')+' [mm]');
  assert.equal(translate('Rotation direction',code,data),expected('Rotation direction'));
  assert.equal(translate('Three stages · double helical',code,data),
    expected('Three stages')+' · '+expected('double helical'));
  assert.equal(translate('Spiral teeth · 90° shafts',code,data),
    expected('Spiral teeth')+' · '+expected('90° shafts'));
  for (const value of ['−0,000000000003','1.25000000000001','-2.5e+12']) {
    for (const template of Object.keys(messages).filter(key => key.includes('{value}'))) {
      assert.equal(translate(template.replace('{value}',value),code,data),expected(template).replace('{value}',value));
    }
  }
}
assert.equal(translate('A↔ Language','it',data),'A↔ Lingua');
assert.equal(translate('☀ Theme','it',data),'☀ Tema');
assert.equal(translate('Face width\u2009·\u2009mm','it',data),'Larghezza dentatura\u2009·\u2009mm');
console.log('Nine-language catalog and unchanged engineering values PASS');
