// [임시] 지금 보고 있는 쇼핑몰 페이지에서 상품명·가격을 읽는다.
// 서버 분석(OCR)이 붙기 전까지 플로팅 카드에 실제 상품 정보를 보여주기 위한 임시 기능이다.
// 순서: JSON-LD Product → og/product 메타 태그 → h1·가격 요소. 사이트마다 구조가 달라 못 읽을 수 있다.
// 같은 로직이 apps/mobile/src/shared/pageProductScript.ts(WebView 주입 문자열)에도 있다. 고치면 같이 고친다.

export interface PageProduct {
  name: string;
  /** 숫자 문자열(쉼표 없음). 못 읽으면 null */
  price: string | null;
  currency: string;
}

export function extractPageProduct(doc: Document = document): PageProduct | null {
  const clean = (s: unknown) => String(s ?? '').replace(/\s+/g, ' ').trim();
  const num = (s: unknown) => {
    const m = String(s ?? '').replace(/,/g, '').match(/\d+(\.\d+)?/);
    return m ? m[0] : null;
  };
  const meta = (p: string) => doc.querySelector(`meta[property="${p}"], meta[name="${p}"], meta[itemprop="${p}"]`)?.getAttribute('content') ?? '';

  let name = '';
  let price: string | null = null;
  let currency = '';

  // 1) JSON-LD (네이버 스마트스토어·쿠팡 등 다수 쇼핑몰)
  const nodes: Record<string, unknown>[] = [];
  doc.querySelectorAll('script[type="application/ld+json"]').forEach((el) => {
    try {
      const j = JSON.parse(el.textContent || '');
      for (const x of Array.isArray(j) ? j : [j]) {
        if (x && Array.isArray(x['@graph'])) nodes.push(...x['@graph']);
        else if (x) nodes.push(x);
      }
    } catch {
      /* 잘못된 JSON-LD는 건너뛴다 */
    }
  });
  const product = nodes.find((n) => ([] as unknown[]).concat(n['@type']).includes('Product'));
  if (product) {
    name = clean(product.name);
    const offer = ([] as Record<string, unknown>[]).concat((product.offers as Record<string, unknown>) ?? [])[0];
    if (offer) {
      const spec = offer.priceSpecification as Record<string, unknown> | undefined;
      price = num(offer.price ?? offer.lowPrice ?? spec?.price);
      currency = clean(offer.priceCurrency);
    }
  }

  // 2) 메타 태그
  if (!name) name = clean(meta('og:title'));
  if (!price) price = num(meta('product:price:amount') || meta('og:price:amount') || meta('price'));
  if (!currency) currency = clean(meta('product:price:currency') || meta('og:price:currency') || meta('priceCurrency'));

  // 3) 화면 요소
  if (!name) name = clean(doc.querySelector('h1')?.textContent) || clean(doc.title);
  if (!price) {
    const els = doc.querySelectorAll('[itemprop="price"], [class*="price" i], [id*="price" i], .a-price .a-offscreen');
    for (const el of Array.from(els).slice(0, 60)) {
      const text = clean(el.getAttribute('content') || el.textContent);
      if (/(\d[\d,]{2,}\s*원|[$€£¥₩]\s*\d)/.test(text) || el.getAttribute('itemprop') === 'price') {
        price = num(text);
        if (!currency) currency = /\$/.test(text) ? 'USD' : /€/.test(text) ? 'EUR' : /£/.test(text) ? 'GBP' : '';
        if (price) break;
      }
    }
  }

  // 사이트 이름 꼬리(" : 스토어명", " | 쇼핑몰") 제거
  name = name.replace(/\s+[:|]\s+[^:|]+$/, '').slice(0, 80);
  if (!name) return null;
  return { name, price, currency: currency || 'KRW' };
}
