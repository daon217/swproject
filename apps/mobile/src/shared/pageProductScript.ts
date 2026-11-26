// [임시] WebView에 주입해 지금 페이지의 상품명·가격을 읽고 앱으로 보내는 스크립트.
// Hermes는 함수 소스를 보관하지 않아 문자열로 둔다. 로직은 apps/extension/src/shared/pageProduct.ts와 같다.
// 상품 표시 여부(signal)도 함께 보낸다. 쇼핑몰이 아닌 사이트는 signal이 있을 때만 캡처하고,
// og:title·h1·문서 제목으로 상품명을 대신 채우는 처리도 쇼핑몰이거나 signal이 있을 때만 한다.
// 가격이 늦게 그려지는 페이지가 많아 0초·1.5초·4초에 세 번 보낸다. 앱은 마지막으로 받은 값을 쓴다.

import { SHOP_HOSTS } from './pageFilter';

export interface PageProduct {
  name: string;
  /** 숫자 문자열(쉼표 없음). 못 읽으면 null */
  price: string | null;
  currency: string;
}

export interface PageProductMessage {
  type: 'kp-product';
  url: string;
  /** 페이지에 상품 표시가 있는지(구조화 데이터·상품 메타 태그·가격 마크업) */
  signal: boolean;
  product: PageProduct | null;
  /** 페이지 상품명·카테고리·경로로 본 식품 여부(확실할 때만 'food') */
  domain?: 'food' | null;
}

/** 주소별로 앱에 보관하는 값 */
export interface PageScan {
  signal: boolean;
  product: PageProduct | null;
  /** 확실할 때만 'food'. 아니면 null(서버가 캡처로 판단) */
  domain: 'food' | null;
}

// 식품 판별 단어(확장 pageProduct.ts FOOD_WORDS·NON_FOOD_WORDS와 같다. 애매하면 판단하지 않는다).
// 화면 캡처 OCR이 리뷰 문장을 상품명으로 읽어 식품을 일반 상품으로 판단하는 문제를 막는다.
export const FOOD_WORDS = /라면|과자|스낵|쿠키|비스킷|초콜릿|초코|젤리|사탕|캔디|아이스크림|케이크|만두|국수|파스타|우동|냉면|짜장|짬뽕|즉석밥|햇반|도시락|밀키트|반찬|김치|소스|양념|간장|된장|고추장|케첩|마요네즈|드레싱|식용유|참기름|우유|두유|요거트|요구르트|치즈|버터|분유|커피|원두|음료|주스|탄산|생수|녹차|홍차|티백|견과|땅콩|아몬드|호두|캐슈|시리얼|그래놀라|오트밀|소시지|베이컨|참치|어묵|두부|계란|달걀|정육|한우|돼지고기|닭가슴살|닭고기|소고기|현미|잡곡|메밀|보리|귀리|대두|잼|스프레드|땅콩버터|피넛버터|과일|사과|딸기|복숭아|오징어|새우|멸치|찌개|갈비탕|곰탕|설렁탕|삼계탕|감자탕|육개장|국밥|떡볶이|돈까스|돈가스|치킨까스|생선까스|볶음밥|식품|간식|영양제|홍삼|프로틴|건강기능식품|가공식품|신선식품|생수·음료|커피·차/;
export const NON_FOOD_WORDS = /화장품|스킨|토너|로션|에센스|세럼|앰플|선크림|썬크림|클렌징|폼클렌저|샴푸|린스|컨디셔너|트리트먼트|바디워시|핸드크림|립밤|립스틱|파운데이션|쿠션|마스크팩|향수|세제|섬유유연제|치약|커피머신|커피메이커|커피포트|에스프레소머신|믹서기|블렌더|착즙기|원액기|그라인더|우유거품기|에어프라이어(?!용)|전자레인지(?!용)|냉장고|토스터기|전기밥솥|밥솥|보관용기|밀폐용기|텀블러|프라이팬|냄비|햄스터|사료|반려|강아지|고양이|애견|애묘|오픈소스|소스코드|리소스|아두이노|라즈베리|개발보드|노트북|컴퓨터|그래픽카드|메인보드|프로세서|CPU|SSD|HDD|키보드|마우스|모니터|프린터|케이블|충전기|이어폰|헤드폰|스피커|스마트폰|태블릿|패딩|자켓|재킷|티셔츠|바지|신발|운동화|가방|의류/;

// 상품 표시(구조화 데이터)가 없는 국내 쇼핑몰용 보조 판단(확장 pageProduct.ts hasCommerceSignal과 같다).
// 상품 상세처럼 보이는 주소 + 구매 버튼 + 가격이 모두 있을 때만 상품 페이지로 본다(목록·검색 화면 제외).
export const PRODUCT_URL_HINT = /(goods|product|item|detail|prd|view)/i;
export const PRODUCT_QUERY_HINT = /(product_?no|goods_?no|goods_?code|item_?(id|no)|prd_?no|[?&]no=\d|[?&]pno=\d)/i;
export const LIST_PATH = /(list|search|category|catalog|cart|basket|order|event|board|review)/i;
export const BUY_TEXT = /바로\s*구매|구매\s*하기|장바구니|buy\s*now|add\s*to\s*(cart|bag)/i;
export const PRICE_TEXT = /\d[\d,]{2,}\s*원|₩\s*\d|\d{1,3}(,\d{3})+/;

export const PAGE_PRODUCT_SCRIPT = `
(function () {
  if (window.__kpProductInjected) return;
  window.__kpProductInjected = true;
  function clean(s) { return String(s == null ? '' : s).replace(/\\s+/g, ' ').trim(); }
  function num(s) { var m = String(s == null ? '' : s).replace(/,/g, '').match(/\\d+(\\.\\d+)?/); return m ? m[0] : null; }
  function meta(p) { var el = document.querySelector('meta[property="' + p + '"], meta[name="' + p + '"], meta[itemprop="' + p + '"]'); return el ? el.getAttribute('content') || '' : ''; }
  var SHOP = new RegExp(${JSON.stringify(SHOP_HOSTS.source)}, 'i');
  function ldNodes() {
    var nodes = [];
    document.querySelectorAll('script[type="application/ld+json"]').forEach(function (el) {
      try {
        var j = JSON.parse(el.textContent || '');
        [].concat(j).forEach(function (x) { if (x && Array.isArray(x['@graph'])) nodes = nodes.concat(x['@graph']); else if (x) nodes.push(x); });
      } catch (e) {}
    });
    return nodes;
  }
  function isProduct(n) { var t = [].concat(n && n['@type']); return t.indexOf('Product') >= 0 || t.indexOf('ProductGroup') >= 0; }
  var URL_HINT = new RegExp(${JSON.stringify(PRODUCT_URL_HINT.source)}, 'i');
  var QUERY_HINT = new RegExp(${JSON.stringify(PRODUCT_QUERY_HINT.source)}, 'i');
  var LIST = new RegExp(${JSON.stringify(LIST_PATH.source)}, 'i');
  var BUY = new RegExp(${JSON.stringify(BUY_TEXT.source)}, 'i');
  var PRICE = new RegExp(${JSON.stringify(PRICE_TEXT.source)});
  function commerce() {
    if (!(URL_HINT.test(location.pathname) || QUERY_HINT.test(location.search)) || LIST.test(location.pathname)) return false;
    var els = Array.prototype.slice.call(document.querySelectorAll('button, a, input[type="button"], input[type="submit"]'), 0, 400);
    var canBuy = els.some(function (el) { return BUY.test(el.value || el.textContent || ''); });
    return canBuy && PRICE.test(((document.body && document.body.innerText) || '').slice(0, 20000));
  }
  function signal() {
    if (commerce()) return true;
    if (ldNodes().some(isProduct)) return true;
    if (/product/i.test(meta('og:type'))) return true;
    if (document.querySelector('meta[property="product:price:amount"], meta[property="og:price:amount"]')) return true;
    return !!document.querySelector('[itemtype*="schema.org/Product" i], [itemprop="price"]');
  }
  function extract(fallback) {
    var name = '', price = null, currency = '';
    var product = ldNodes().find(isProduct);
    if (product) {
      name = clean(product.name);
      var offer = [].concat(product.offers || [])[0];
      if (offer) {
        price = num(offer.price != null ? offer.price : offer.lowPrice != null ? offer.lowPrice : offer.priceSpecification && offer.priceSpecification.price);
        currency = clean(offer.priceCurrency);
      }
    }
    if (!name && fallback) name = clean(meta('og:title'));
    if (!price) price = num(meta('product:price:amount') || meta('og:price:amount') || meta('price'));
    if (!currency) currency = clean(meta('product:price:currency') || meta('og:price:currency') || meta('priceCurrency'));
    if (!name && fallback) { var h1 = document.querySelector('h1'); name = clean(h1 && h1.textContent) || clean(document.title); }
    if (!price) {
      var els = Array.prototype.slice.call(document.querySelectorAll('[itemprop="price"], [class*="price" i], [id*="price" i], .a-price .a-offscreen'), 0, 60);
      for (var i = 0; i < els.length; i++) {
        var text = clean(els[i].getAttribute('content') || els[i].textContent);
        if (/(\\d[\\d,]{2,}\\s*원|[$€£¥₩]\\s*\\d)/.test(text) || els[i].getAttribute('itemprop') === 'price') {
          price = num(text);
          if (!currency) currency = /\\$/.test(text) ? 'USD' : /€/.test(text) ? 'EUR' : /£/.test(text) ? 'GBP' : '';
          if (price) break;
        }
      }
    }
    name = name.replace(/\\s+[:|]\\s+[^:|]+$/, '').slice(0, 80);
    return name ? { name: name, price: price, currency: currency || 'KRW' } : null;
  }
  var FOOD = new RegExp(${JSON.stringify(FOOD_WORDS.source)});
  var NON_FOOD = new RegExp(${JSON.stringify(NON_FOOD_WORDS.source)});
  function domain() {
    var parts = [];
    ldNodes().forEach(function (n) {
      if (isProduct(n)) parts.push(String(n.name || ''), String(n.category || ''));
      if ([].concat(n && n['@type']).indexOf('BreadcrumbList') >= 0) {
        [].concat(n.itemListElement || []).forEach(function (it) { parts.push(String((it && (it.name || (it.item && it.item.name))) || '')); });
      }
    });
    parts.push(meta('og:title'), meta('product:category'), document.title || '');
    var text = clean(parts.join(' '));
    if (!text || NON_FOOD.test(text)) return null;
    return FOOD.test(text) ? 'food' : null;
  }
  function send() {
    try {
      var s = signal();
      var shop = SHOP.test(location.hostname);
      window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'kp-product', url: location.href, signal: s, product: extract(s || shop), domain: s || shop ? domain() : null }));
    } catch (e) {}
  }
  send();
  setTimeout(send, 1500);
  setTimeout(send, 4000);
})();
true;
`;
