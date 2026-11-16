// [임시] WebView에 주입해 지금 페이지의 상품명·가격을 읽고 앱으로 보내는 스크립트.
// Hermes는 함수 소스를 보관하지 않아 문자열로 둔다. 로직은 apps/extension/src/shared/pageProduct.ts와 같다.
// 가격이 늦게 그려지는 페이지가 많아 0초·1.5초·4초에 세 번 보낸다. 앱은 마지막으로 받은 값을 쓴다.

export interface PageProduct {
  name: string;
  /** 숫자 문자열(쉼표 없음). 못 읽으면 null */
  price: string | null;
  currency: string;
}

export interface PageProductMessage {
  type: 'kp-product';
  url: string;
  product: PageProduct | null;
}

export const PAGE_PRODUCT_SCRIPT = `
(function () {
  if (window.__kpProductInjected) return;
  window.__kpProductInjected = true;
  function clean(s) { return String(s == null ? '' : s).replace(/\\s+/g, ' ').trim(); }
  function num(s) { var m = String(s == null ? '' : s).replace(/,/g, '').match(/\\d+(\\.\\d+)?/); return m ? m[0] : null; }
  function meta(p) { var el = document.querySelector('meta[property="' + p + '"], meta[name="' + p + '"], meta[itemprop="' + p + '"]'); return el ? el.getAttribute('content') || '' : ''; }
  function extract() {
    var name = '', price = null, currency = '';
    var nodes = [];
    document.querySelectorAll('script[type="application/ld+json"]').forEach(function (el) {
      try {
        var j = JSON.parse(el.textContent || '');
        [].concat(j).forEach(function (x) { if (x && Array.isArray(x['@graph'])) nodes = nodes.concat(x['@graph']); else if (x) nodes.push(x); });
      } catch (e) {}
    });
    var product = nodes.find(function (n) { return [].concat(n['@type']).indexOf('Product') >= 0; });
    if (product) {
      name = clean(product.name);
      var offer = [].concat(product.offers || [])[0];
      if (offer) {
        price = num(offer.price != null ? offer.price : offer.lowPrice != null ? offer.lowPrice : offer.priceSpecification && offer.priceSpecification.price);
        currency = clean(offer.priceCurrency);
      }
    }
    if (!name) name = clean(meta('og:title'));
    if (!price) price = num(meta('product:price:amount') || meta('og:price:amount') || meta('price'));
    if (!currency) currency = clean(meta('product:price:currency') || meta('og:price:currency') || meta('priceCurrency'));
    if (!name) { var h1 = document.querySelector('h1'); name = clean(h1 && h1.textContent) || clean(document.title); }
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
      window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'kp-product', url: location.href, product: extract() }));
    } catch (e) {}
  }
  send();
  setTimeout(send, 1500);
  setTimeout(send, 4000);
})();
true;
`;
