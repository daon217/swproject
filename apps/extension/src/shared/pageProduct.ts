// [임시] 지금 보고 있는 쇼핑몰 페이지에서 상품명·가격을 읽는다.
// 서버 분석(OCR)이 붙기 전까지 플로팅 카드에 실제 상품 정보를 보여주기 위한 임시 기능이다.
// 순서: JSON-LD Product → og/product 메타 태그 → h1·가격 요소. 사이트마다 구조가 달라 못 읽을 수 있다.
// 쇼핑몰이 아닌 사이트에서는 페이지에 상품 표시(hasProductSignal)가 있을 때만 캡처하고,
// h1·문서 제목으로 상품명을 대신 채우는 처리도 쇼핑몰이거나 상품 표시가 있을 때만 한다.
// 같은 로직이 apps/mobile/src/shared/pageProductScript.ts(WebView 주입 문자열)에도 있다. 고치면 같이 고친다.

import { isShopHost } from './pageFilter';

export interface PageProduct {
  name: string;
  /** 숫자 문자열(쉼표 없음). 못 읽으면 null */
  price: string | null;
  currency: string;
}

/** content script → background 응답 */
export interface PageScan {
  /** 페이지에 상품 표시가 있는지(구조화 데이터·상품 메타 태그·가격 마크업) */
  signal: boolean;
  product: PageProduct | null;
  /** 페이지 자체 정보(상품명·카테고리·경로)로 본 식품 여부. 확실할 때만 'food', 아니면 null(서버가 판단) */
  domain: 'food' | null;
}

// 식품 판별 단어. 서버 분석 작업자(services/dev_runtime/analysis_worker.py FOOD_TITLE·NON_FOOD)를 바탕으로 하되,
// 페이지 제목·경로에서 쓰므로 더 엄격하다: 다른 말에 섞이기 쉬운 한 글자(빵·떡·껌·햄·쌀)는 빼고,
// '오픈소스'의 '소스'처럼 식품이 아닌 말과 전자·패션 상품 단어가 있으면 식품으로 보지 않는다.
// 틀리면 일반 상품 페이지에 식품 알레르기가 뜨므로, 애매하면 판단하지 않고(null) 서버에 맡긴다.
// 화면 캡처 OCR은 리뷰 문장 등을 상품명으로 잘못 읽을 수 있어, 페이지에 적힌 상품명·카테고리로 먼저 판단한다.
// 같은 로직이 apps/mobile/src/shared/pageProductScript.ts(WebView 주입 문자열)에도 있다. 고치면 같이 고친다.
export const FOOD_WORDS =
  /라면|과자|스낵|쿠키|비스킷|초콜릿|초코|젤리|사탕|캔디|아이스크림|케이크|만두|국수|파스타|우동|냉면|짜장|짬뽕|즉석밥|햇반|도시락|밀키트|반찬|김치|소스|양념|간장|된장|고추장|케첩|마요네즈|드레싱|식용유|참기름|우유|두유|요거트|요구르트|치즈|버터|분유|커피|원두|음료|주스|탄산|생수|녹차|홍차|티백|견과|땅콩|아몬드|호두|캐슈|시리얼|그래놀라|오트밀|소시지|베이컨|참치|어묵|두부|계란|달걀|정육|한우|돼지고기|닭가슴살|닭고기|소고기|현미|잡곡|과일|사과|딸기|복숭아|오징어|새우|멸치|식품|간식|영양제|홍삼|프로틴|건강기능식품|가공식품|신선식품|생수·음료|커피·차/;
export const NON_FOOD_WORDS =
  /화장품|스킨|토너|로션|에센스|세럼|앰플|선크림|썬크림|클렌징|폼클렌저|샴푸|린스|컨디셔너|트리트먼트|바디워시|핸드크림|립밤|립스틱|파운데이션|쿠션|마스크팩|향수|세제|섬유유연제|치약|커피머신|커피메이커|커피포트|에스프레소머신|믹서기|블렌더|착즙기|원액기|그라인더|우유거품기|에어프라이어|전자레인지|냉장고|토스터기|전기밥솥|밥솥|보관용기|밀폐용기|텀블러|프라이팬|냄비|햄스터|사료|반려|강아지|고양이|애견|애묘|오픈소스|소스코드|리소스|아두이노|라즈베리|개발보드|노트북|컴퓨터|그래픽카드|메인보드|프로세서|CPU|SSD|HDD|키보드|마우스|모니터|프린터|케이블|충전기|이어폰|헤드폰|스피커|스마트폰|태블릿|패딩|자켓|재킷|티셔츠|바지|신발|운동화|가방|의류/;

/** 페이지의 상품명·카테고리·경로(breadcrumb)·제목으로 식품인지 본다. 식품이 아닌 단어가 있으면 판단하지 않는다. */
export function pageDomain(doc: Document = document): 'food' | null {
  const parts: string[] = [];
  for (const n of jsonLdNodes(doc)) {
    if (isProductNode(n)) parts.push(String(n.name ?? ''), String(n.category ?? ''));
    const types = ([] as unknown[]).concat(n['@type']);
    if (types.includes('BreadcrumbList')) {
      for (const it of ([] as Record<string, unknown>[]).concat((n.itemListElement as Record<string, unknown>[]) ?? [])) {
        const item = it?.item as Record<string, unknown> | undefined;
        parts.push(String(it?.name ?? item?.name ?? ''));
      }
    }
  }
  const meta = (p: string) => doc.querySelector(`meta[property="${p}"], meta[name="${p}"]`)?.getAttribute('content') ?? '';
  parts.push(meta('og:title'), meta('product:category'), doc.title ?? '');
  const text = parts.join(' ').replace(/\s+/g, ' ');
  if (!text.trim() || NON_FOOD_WORDS.test(text)) return null;
  return FOOD_WORDS.test(text) ? 'food' : null;
}

function jsonLdNodes(doc: Document): Record<string, unknown>[] {
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
  return nodes;
}

const isProductNode = (n: Record<string, unknown>) =>
  ([] as unknown[]).concat(n['@type']).some((t) => t === 'Product' || t === 'ProductGroup');

/** 페이지가 상품 상세라고 스스로 표시하는지 본다. 학습포털·블로그 등은 보통 없다. */
export function hasProductSignal(doc: Document = document): boolean {
  if (jsonLdNodes(doc).some(isProductNode)) return true;
  const ogType = doc.querySelector('meta[property="og:type"]')?.getAttribute('content') ?? '';
  if (/product/i.test(ogType)) return true;
  if (doc.querySelector('meta[property="product:price:amount"], meta[property="og:price:amount"]')) return true;
  return !!doc.querySelector('[itemtype*="schema.org/Product" i], [itemprop="price"]');
}

// 상품 표시(구조화 데이터)가 없는 국내 쇼핑몰(디바이스마트·컴퓨존·모다아울렛 등)용 보조 판단.
// 상품 상세처럼 보이는 주소 + 구매 버튼 + 가격이 모두 있을 때만 상품 페이지로 본다(목록·검색 화면 제외).
export const PRODUCT_URL_HINT = /(goods|product|item|detail|prd|view)/i;
export const PRODUCT_QUERY_HINT = /(product_?no|goods_?no|goods_?code|item_?(id|no)|prd_?no|[?&]no=\d|[?&]pno=\d)/i;
export const LIST_PATH = /(list|search|category|catalog|cart|basket|order|event|board|review)/i;
export const BUY_TEXT = /바로\s*구매|구매\s*하기|장바구니|buy\s*now|add\s*to\s*(cart|bag)/i;
export const PRICE_TEXT = /\d[\d,]{2,}\s*원|₩\s*\d|\d{1,3}(,\d{3})+/;

export function hasCommerceSignal(doc: Document = document): boolean {
  const loc = doc.location;
  if (!loc) return false;
  const urlHint = PRODUCT_URL_HINT.test(loc.pathname) || PRODUCT_QUERY_HINT.test(loc.search);
  if (!urlHint || LIST_PATH.test(loc.pathname)) return false;
  const controls = Array.from(doc.querySelectorAll('button, a, input[type="button"], input[type="submit"]')).slice(0, 400);
  const canBuy = controls.some((el) => BUY_TEXT.test((el as HTMLInputElement).value || el.textContent || ''));
  if (!canBuy) return false;
  return PRICE_TEXT.test((doc.body?.innerText ?? '').slice(0, 20000));
}

export function scanPage(doc: Document = document): PageScan {
  const signal = hasProductSignal(doc) || hasCommerceSignal(doc);
  const shop = isShopHost(doc.location?.hostname ?? '');
  return { signal, product: extractPageProduct(doc, shop || signal), domain: shop || signal ? pageDomain(doc) : null };
}

/** headingFallback: 상품명을 못 찾으면 og:title·h1·문서 제목으로 대신 채울지(쇼핑몰·상품 표시가 있을 때만) */
export function extractPageProduct(doc: Document = document, headingFallback = true): PageProduct | null {
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
  const product = jsonLdNodes(doc).find(isProductNode);
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
  if (!name && headingFallback) name = clean(meta('og:title'));
  if (!price) price = num(meta('product:price:amount') || meta('og:price:amount') || meta('price'));
  if (!currency) currency = clean(meta('product:price:currency') || meta('og:price:currency') || meta('priceCurrency'));

  // 3) 화면 요소
  if (!name && headingFallback) name = clean(doc.querySelector('h1')?.textContent) || clean(doc.title);
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
