// 캡처 대상 화면 선별(명세 F-CAP-02). 상품 상세로 보이는 화면만 캡처하고 민감 화면은 제외한다.
// 최종 판단(상품 여부·상품/식품 구분)은 서버 분석 결과(result_kind)가 한다.
//
// 주소만으로는 상품 페이지를 다 알 수 없어(나이키 /kr/t/…/CW2288-111, 자라 …-p02298302.html 등) 두 단계로 거른다.
// - 알려진 쇼핑몰: 주소가 상품 상세처럼 보이면 캡처('shop')
// - 그 밖의 사이트: 민감한 주소(로그인·결제 등)만 빼고, 페이지에 상품 표시
//   (JSON-LD Product·ProductGroup, og:type=product, 가격 메타 태그 등)가 있을 때만 캡처('needs-signal').
//   학습포털·블로그처럼 상품 표시가 없는 페이지는 이 단계에서 걸러진다.

const SENSITIVE = /(login|signin|sign-in|auth|account|mypage|my-page|checkout|order|payment|pay\.|bank|cart|member)/i;
const SENSITIVE_HOSTS = /(bank|card|pay|gov|mail|accounts\.google)/i;

/** 알려진 쇼핑몰(국내·해외·중고). 하위 도메인 포함(m.smartstore.naver.com 등). */
export const SHOP_HOSTS =
  /(^|\.)((smartstore|brand|shopping)\.naver\.com|coupang\.com|11st\.co\.kr|gmarket\.co\.kr|auction\.co\.kr|ssg\.com|kurly\.com|musinsa\.com|oliveyoung\.co\.kr|lotteon\.com|lotteimall\.com|wemakeprice\.com|tmon\.co\.kr|interpark\.com|29cm\.co\.kr|wconcept\.co\.kr|a-bly\.com|zigzag\.kr|kream\.co\.kr|hmall\.com|gsshop\.com|cjonmall\.com|danawa\.com|bunjang\.co\.kr|daangn\.com|joongna\.com|amazon\.(com|co\.jp|co\.uk|de|fr|it|es|ca|com\.au|in)|ebay\.(com|co\.uk|de|fr|it|es|ca|com\.au)|aliexpress\.(com|us)|temu\.com|rakuten\.co\.jp|iherb\.com|daisomall\.co\.kr)$/i;

// 쇼핑몰 안에서 상품 상세로 보는 주소 단어. 국내 몰(product·goods·vp/ 등) + 아마존 /dp/·/gp/product/·/gp/aw/d/, 이베이 /itm/
// + 다나와 /info/, GS샵 /prd/, 티몬 /deal/, 당근 /buy-sell/·/articles/, 아이허브 /pr/, 테무 …-g-숫자.html, 다이소몰 /pd/pdr/
export const PRODUCT_PATH =
  /(product|products|goods|item|vp\/|catalog|detail|\/dp\/|\/gp\/(product|aw\/d)\/|\/itm\/|\/info\/|\/prd\/|\/deal\/|\/buy-sell\/|\/articles\/|\/pr\/|\/pdr\/|-g-\d+\.html)/i;

export type CaptureRule = 'shop' | 'needs-signal';

export function isShopHost(hostname: string): boolean {
  return SHOP_HOSTS.test(hostname);
}

/** 주소만 보고 판단한다. 'needs-signal'이면 페이지의 상품 표시를 확인한 뒤 캡처한다. */
export function captureRule(url: string | undefined): CaptureRule | null {
  if (!url) return null;
  let u: URL;
  try {
    u = new URL(url);
  } catch {
    return null;
  }
  if (u.protocol !== 'https:' && u.protocol !== 'http:') return null;
  if (SENSITIVE_HOSTS.test(u.hostname)) return null;
  if (SENSITIVE.test(u.pathname)) return null;
  // 알려진 쇼핑몰이라도 주소 형태가 낯설면(라쿠텐 /가게/상품코드/ 등) 버리지 않고 페이지의 상품 표시로 판단한다.
  // 검색·목록 화면에는 상품 표시(JSON-LD Product 등)가 없어 여기서 걸러진다.
  if (isShopHost(u.hostname)) return PRODUCT_PATH.test(u.pathname) ? 'shop' : 'needs-signal';
  // 주소 형태와 상관없이 페이지 안 상품 표시로 판단한다(브랜드몰 상품 주소는 제각각이다).
  return 'needs-signal';
}

/** 주소 기준 1차 판단(캡처 후보인지). 쇼핑몰이 아닌 사이트는 이후 상품 표시 확인이 더 필요하다. */
export function shouldCapture(url: string | undefined): boolean {
  return captureRule(url) !== null;
}
