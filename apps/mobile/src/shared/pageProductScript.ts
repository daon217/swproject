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
}

/** 주소별로 앱에 보관하는 값 */
export interface PageScan {
  signal: boolean;
  product: PageProduct | null;
}

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
  function signal() {
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
  function send() {
    try {
      var s = signal();
      window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'kp-product', url: location.href, signal: s, product: extract(s || SHOP.test(location.hostname)) }));
    } catch (e) {}
  }
  send();
  setTimeout(send, 1500);
  setTimeout(send, 4000);
})();
true;
`;
