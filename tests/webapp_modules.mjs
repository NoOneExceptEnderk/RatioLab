// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
// Load the actual ES module dependency graph in the existing VM test harness.
import fs from 'node:fs';
import vm from 'node:vm';
export function webModules(root,overrides={}) {
  const modules={...overrides};
  const resolve=name=>{
    if(!/^\.\/[a-z-]+\.js$/.test(name))throw Error('Unexpected web module: '+name);
    return modules[name]??=(new vm.SourceTextModule(fs.readFileSync(root+'webapp/'+name.slice(2),'utf8'),{identifier:name}));
  };
  async function load(name){const m=resolve(name);if(m.status==='unlinked')await m.link(resolve);if(m.status==='linked')await m.evaluate();return m;}
  return {modules,load,resolve};
}
