// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
// Translate presentation nodes only. Input values and model identifiers stay canonical.
export const LANGUAGES = Object.freeze({'en':'English','it':'Italiano','es':'Español',
  'fr':'Français','de':'Deutsch','pt':'Português (Portugal)','ru':'Русский','zh-CN':'简体中文','ta':'தமிழ்'});

const templateCache = new WeakMap();
const placeholder = /\{(value|arg\d+|message\d+)\}/gu;
const escapePattern = value => value.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
function templatesFor(messages) {
  if (templateCache.has(messages)) return templateCache.get(messages);
  const buckets = new Map();
  for (const [source,target] of Object.entries(messages)) {
    const fields = [...source.matchAll(placeholder)];
    if (!fields.length || !/[A-Za-z]{3}/u.test(source.replace(placeholder,''))) continue;
    const chunks=[], names=new Set(); let position=0;
    for (const field of fields) {
      chunks.push(escapePattern(source.slice(position,field.index)));
      const name=field[1];
      if (names.has(name)) chunks.push('\\k<'+name+'>');
      else { names.add(name); chunks.push('(?<'+name+'>'+(name==='value'?'[+−\\-0-9.,eE]+':'.*?')+')'); }
      position=field.index+field[0].length;
    }
    chunks.push(escapePattern(source.slice(position)));
    const prefix=source.slice(0,fields[0].index), key=prefix.slice(0,1);
    if (!buckets.has(key)) buckets.set(key,[]);
    buckets.get(key).push({prefix,pattern:new RegExp('^'+chunks.join('')+'$','su'),target,literalLength:source.replace(placeholder,'').length});
  }
  for (const entries of buckets.values()) entries.sort((a,b)=>b.prefix.length-a.prefix.length||b.literalLength-a.literalLength);
  templateCache.set(messages,buckets); return buckets;
}

export function translate(text, language, catalog) {
  if (!text) return text;
  const messages = catalog.translations[language] ?? {};
  if (Object.hasOwn(messages,text)) return messages[text];
  const templates=templatesFor(messages);
  for (const {prefix,pattern,target} of [...templates.get(text.slice(0,1))??[],...templates.get('')??[]]) {
    if (prefix && !text.startsWith(prefix)) continue;
    const match=pattern.exec(text);
    if (match) return target.replace(placeholder,(_,name)=>name.startsWith('message')?translate(match.groups[name],language,catalog):match.groups[name]);
  }
  const core = text.trim();
  if (!core) return text;
  if (core !== text) return text.slice(0,text.length-text.trimStart().length) + translate(core,language,catalog) + text.slice(text.trimEnd().length);
  if (core.includes('\n')) return core.split('\n').map(line=>translate(line,language,catalog)).join('\n');
  const capitalized=core.slice(0,1).toUpperCase()+core.slice(1).toLowerCase();
  if (core[0]===core[0].toLowerCase() && Object.hasOwn(messages,capitalized)) return messages[capitalized];
  for (const prefix of ['☀ ','☾ ','文 ', 'A↔ ', '◐ ','✓ ','‹ ','○ ','● ','- ','• '])
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
  const excluded = 'script,style,textarea,code,pre:not([data-localize-report]),[data-no-i18n],#document-name,#document-state';
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
    for (const key of ['title','aria-label','aria-description','placeholder','alt']) {
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
    document.dispatchEvent(new CustomEvent('ratiolab-language-change',{detail:code}));
  }
  setLanguage(language);
  const observer = new MutationObserver(records => {
    for (const record of records) {
      if (record.type === 'characterData') text(record.target);
      else if (record.type === 'attributes') element(record.target);
      else for (const node of record.addedNodes) visit(node);
    }
  });
  observer.observe(root,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['title','aria-label','aria-description','placeholder','alt']});
  return {setLanguage, disconnect:() => observer.disconnect()};
}
