import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
const manifest=JSON.parse(readFileSync(new URL('./manifest.json',import.meta.url),'utf8'));
assert.equal(manifest.manifest_version,3);
assert.deepEqual(manifest.host_permissions,['http://127.0.0.1/*']);
assert.equal(manifest.permissions,undefined);
for (const name of ['popup.html','popup.js']) assert.ok(readFileSync(new URL(name,import.meta.url)).length);
console.log('MV3 development manifest and popup assets OK');
