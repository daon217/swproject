// Run from apps/extension or apps/mobile after npm ci. Transpile the actual TS modules.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require(path.join(process.cwd(), 'node_modules/typescript'));
const data = new Map();
const storage = {
  getItem: async (key, fallback) => data.has(key) ? structuredClone(data.get(key)) : fallback,
  setItem: async (key, value) => { data.set(key, structuredClone(value)); },
  removeItem: async key => { data.delete(key); },
};
const modules = new Map();
function load(name) {
  if(name === './storage') return storage;
  if(modules.has(name)) return modules.get(name);
  const source = fs.readFileSync(path.join(process.cwd(), 'src/shared', name + '.ts'), 'utf8');
  const code = ts.transpileModule(source, {compilerOptions:{module:ts.ModuleKind.CommonJS, target:ts.ScriptTarget.ES2022}}).outputText;
  const exports = {};
  vm.runInNewContext(code,{exports, require:load, URL, Date, Map, Promise, encodeURIComponent});
  modules.set(name, exports); return exports;
}
(async()=>{
  const a=load('./accountData'), s=load('./shortcuts'), v=load('./validation');
  assert.match(v.loginIdError('user name'), /공백/);
  assert.equal(v.loginIdError('user123'), undefined);
  assert.match(v.passwordError('1234567'), /현재 7자/);
  assert.equal(v.passwordError('12345678'), undefined);
  assert.equal(v.passwordError('😀'.repeat(8)), undefined);
  assert.ok(v.passwordError('a'.repeat(129)));
  assert.ok(v.signupErrors({id:'test123',pw:'abcdefgh',pw2:'different'}).pw2);
  data.set('kp.shortcuts',[{id:'legacy',name:'unknown owner'}]);
  assert.equal((await s.loadShortcuts('B')).some(x=>x.id==='legacy'),false);
  await s.saveShortcuts([{id:'private',name:'A only',url:'https://example.com'}],'A');
  assert.equal((await s.loadShortcuts('A'))[0].name,'A only');
  assert.equal((await s.loadShortcuts('B')).some(x=>x.id==='private'),false);
  assert.equal((await s.loadShortcuts()).some(x=>x.id==='private'),false);
  await s.saveShortcuts([{id:'guest'}]);
  assert.equal(data.has(a.accountKey('undefined','shortcuts')),false);
  assert.equal(a.historyUrl('https://example.com/item?token=secret#secret'),'https://example.com/item');
  assert.equal(a.historyUrl('https://user:pass@example.com/item'),null);
  assert.equal(a.historyUrl('javascript:alert(1)'),null);
  assert.equal(a.historyUrl('https://example.com/oauth/callback?code=secret'),null);
  await Promise.all(Array.from({length:60},(_,i)=>a.recordVisit('A',`https://example.com/item/${i}`)));
  assert.equal((await a.loadVisits('A')).length,50);
  assert.equal((await a.loadVisits('B')).length,0);
  await a.recordVisit('A','https://example.com/item/59');
  assert.equal((await a.loadVisits('A')).length,50);
  data.set(a.accountKey('B','visits'),[{url:'https://example.com/expired',at:Date.now()-31*86400000}]);
  assert.equal((await a.loadVisits('B')).length,0);
  assert.equal(data.get(a.accountKey('B','visits')).length,0);
  await a.clearVisits('A'); assert.equal((await a.loadVisits('A')).length,0);
  assert.equal((await s.loadShortcuts('A'))[0].name,'A only');
  await a.clearAccountData('A'); assert.equal(data.has(a.accountKey('A','shortcuts')),false);
  console.log('PASS: live validation, account isolation, guest/legacy exclusion, URL sanitization, concurrent history limit, retention, deletion');
})().catch(e=>{console.error(e);process.exitCode=1;});
