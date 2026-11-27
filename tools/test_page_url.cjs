// Run from apps/extension after npm ci; same-page URL comparison used before showing an analysis result.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require(path.join(process.cwd(), 'node_modules/typescript'));
const code = ts.transpileModule(fs.readFileSync('src/shared/pageFilter.ts', 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const exportsObject = {};
vm.runInNewContext(code, { exports: exportsObject, URL, URLSearchParams });
const { sameUrl } = exportsObject;

// 쿠팡이 로드 뒤 ':'를 '%3A'로 다시 써서 결과가 버려지고 '분석 중'에 멈췄던 실제 주소.
const base = 'https://www.coupang.com/vp/products/7764368375?vendorItemId=4686502744&searchId=feed-1-3.33.14';
assert.ok(sameUrl(base + ':personalized_ads', base + '%3Apersonalized_ads'));
assert.ok(sameUrl(base, base));
// 진짜 다른 페이지는 계속 다르게 본다(상품 번호가 쿼리에 있는 쇼핑몰, 다른 경로, 값 안의 & 인코딩).
assert.ok(!sameUrl('https://www.hnsmall.com/display/goods.do?goods_code=1', 'https://www.hnsmall.com/display/goods.do?goods_code=2'));
assert.ok(!sameUrl(base, 'https://www.coupang.com/vp/products/1?vendorItemId=4686502744'));
assert.ok(!sameUrl('https://a.test/p?q=a%26b', 'https://a.test/p?q=a&b'));
assert.ok(!sameUrl(base, undefined) && !sameUrl(null, base));
console.log('PASS: same page across URL re-encoding; different products stay different');
