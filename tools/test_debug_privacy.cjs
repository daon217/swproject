// Run from apps/extension after npm ci; exercise the actual log sanitizer.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require(path.join(process.cwd(), 'node_modules/typescript'));
const source = fs.readFileSync('src/shared/debug.ts', 'utf8')
  .replace("import.meta.env.VITE_DEBUG_LOG === 'true'", 'false');
const code = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const exportsObject = {};
let logged = false;
vm.runInNewContext(code, { exports: exportsObject, Blob, FormData, Error,
  console: { log() { logged = true; } } });
const { redact, dlog } = exportsObject;
const sensitive = { password: 'private', access_token: 'private', login_id: 'private',
  birth_date: 'private', allergies: ['private'], body: 'private', ingredient_filter: 'private' };
assert.ok(!JSON.stringify(redact({ nested: sensitive })).includes('private'));
let deep = { token: 'private' };
for (let i = 0; i < 10; i++) deep = { child: deep };
assert.ok(!JSON.stringify(redact(deep)).includes('private'));
const form = new FormData();
form.append('password', 'private');
form.append('image', new Blob(['private'], { type: 'image/png' }));
assert.ok(!JSON.stringify(redact(form)).includes('private'));
assert.ok(!JSON.stringify(redact('data:image/png;base64,private')).includes('private'));
assert.equal(redact({ state: 'completed' }).state, 'completed');
dlog('test', 'disabled', sensitive);
assert.equal(logged, false);
console.log('PASS: debug disabled by default; nested secrets, FormData, images and depth overflow redacted');
