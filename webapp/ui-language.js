// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
// Translate presentation nodes only. Input values and model identifiers stay canonical.
export const LANGUAGES = Object.freeze({'en':'English','it':'Italiano','es':'Español',
  'fr':'Français','de':'Deutsch','pt':'Português (Portugal)','ru':'Русский','zh-CN':'简体中文','ta':'தமிழ்'});

export function translate(text, language, catalog) {
  if (!text || language === 'en') return text;
  const messages = catalog.translations[language] ?? {};
  if (Object.hasOwn(messages,text)) return messages[text];
  for (const [source,target] of Object.entries(messages)) {
    if (!source.includes('{value}')) continue;
    const pattern = source.split('{value}').map(part => part.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('([+−\\-0-9.,eE]+)');
    const match = text.match(new RegExp('^'+pattern+'$','u'));
    if (match) return target.replace('{value}',match[1]);
  }
  const core = text.trim();
  if (!core) return text;
  if (core !== text) return text.slice(0,text.length-text.trimStart().length) + translate(core,language,catalog) + text.slice(text.trimEnd().length);
  for (const prefix of ['☀ ','☾ ','文 ', 'A↔ ', '◐ ','✓ ','‹ ','○ ','● '])
    if (core.startsWith(prefix)) return prefix + translate(core.slice(prefix.length),language,catalog);
  for (const suffix of ['…','...',':'])
    if (core.endsWith(suffix)) return translate(core.slice(0,-suffix.length),language,catalog) + suffix;
  const unit = core.match(/^(.+?)( (?:· |\[)(?:mm|°|rpm|N|N.m|N·m|%)(?:\])?)$/u);
  if (unit) return translate(unit[1],language,catalog) + unit[2];
  for (const delimiter of [' / ',' → ',' · ','\u2009·\u2009'])
    if (core.includes(delimiter)) return core.split(delimiter).map(part => translate(part,language,catalog)).join(delimiter);
  for (const prefix of ['Connect ','Create in ','Import in '])
    if (core.startsWith(prefix) && ['SolidCraft','Fusion','Autodesk Fusion'].includes(core.slice(prefix.length)))
      return translate(prefix.trim(),language,catalog)+' '+core.slice(prefix.length);
  return text;
}

export async function initLanguage(language='en', root=document.body) {
  const response = await fetch(new URL('./ui-translations.json',import.meta.url));
  if (!response.ok) throw Error('Could not load interface languages.');
  const catalog = await response.json();
  const sources = new WeakMap(), attributes = new WeakMap();
  const excluded = 'script,style,textarea,code,pre,[data-no-i18n],#document-name,#document-state';
  let current = language;
  function text(node) {
    if (!node.parentElement || node.parentElement.closest(excluded)) return;
    let record = sources.get(node);
    if (!record || node.data !== record.display) record = {source:node.data};
    record.display = translate(record.source,current,catalog);
    sources.set(node,record);
    if (node.data !== record.display) node.data = record.display;
  }
  function element(node) {
    if (node.closest(excluded)) return;
    let records = attributes.get(node);
    if (!records) { records = {}; attributes.set(node,records); }
    for (const key of ['title','aria-label','placeholder']) {
      const value = node.getAttribute(key);
      if (value == null) continue;
      let record = records[key];
      if (!record || value !== record.display) record = {source:value};
      record.display = translate(record.source,current,catalog);
      records[key] = record;
      if (value !== record.display) node.setAttribute(key,record.display);
    }
  }
  function visit(node) {
    if (node.nodeType === 3) text(node);
    else if (node.nodeType === 1) {
      element(node);
      if (!node.matches(excluded)) for (const child of node.childNodes) visit(child);
    }
  }
  function setLanguage(code) {
    if (!Object.hasOwn(LANGUAGES,code)) throw Error('Unsupported interface language');
    current = code;
    document.documentElement.lang = code;
    visit(root);
  }
  setLanguage(language);
  const observer = new MutationObserver(records => {
    for (const record of records) {
      if (record.type === 'characterData') text(record.target);
      else if (record.type === 'attributes') element(record.target);
      else for (const node of record.addedNodes) visit(node);
    }
  });
  observer.observe(root,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['title','aria-label','placeholder']});
  return {setLanguage, disconnect:() => observer.disconnect()};
}
