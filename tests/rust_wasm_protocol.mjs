// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
import {readFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
const [root,input] = process.argv.slice(2);
const {loadRustGeometry} = await import(pathToFileURL(root+'/webapp/rust-engine.js'));
const request = await loadRustGeometry(await readFile(root+'/target/wasm32-unknown-unknown/release/ratiolab_geometry.wasm'));
const results = JSON.parse(await readFile(input,'utf8')).map(q=>q.binary
  ? Array.from(request.buffer(JSON.stringify({protocol:1,...q})))
  : JSON.parse(request(JSON.stringify({protocol:1,...q}))));
process.stdout.write(JSON.stringify(results));
