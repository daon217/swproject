// 캡처 대상 화면 선별(명세 F-CAP-02). 상품 상세로 보이는 화면만 캡처하고 민감 화면은 제외한다.
// 최종 판단(상품 여부·상품/식품 구분)은 서버 분석 결과(result_kind)가 한다.
//
// 주소만으로는 쇼핑몰이 아닌 사이트(학습포털 /modules/items/… 등)가 걸릴 수 있어 두 단계로 거른다.
// - 알려진 쇼핑몰: 주소가 상품 상세처럼 보이면 캡처('shop')
// - 그 밖의 사이트: 경로 한 칸이 정확히 product·goods·item 등이고, 페이지에 상품 표시
//   (JSON-LD Product, og:type=product, 가격 메타 태그 등)가 있을 때만 캡처('needs-signal')

const SENSITIVE = /(login|signin|sign-in|auth|account|mypage|my-page|checkout|order|payment|pay\.|bank|cart|member)/i;
const SENSITIVE_HOSTS = /(bank|card|pay|gov|mail|accounts\.google)/i;

/** 알려진 쇼핑몰(국내·해외·중고). 하위 도메인 포함(m.smartstore.naver.com 등). */
export const SHOP_HOSTS =
  /(^|\.)((smartstore|brand|shopping)\.naver\.com|coupang\.com|11st\.co\.kr|gmarket\.co\.kr|auction\.co\.kr|ssg\.com|kurly\.com|musinsa\.com|oliveyoung\.co\.kr|lotteon\.com|lotteimall\.com|wemakeprice\.com|tmon\.co\.kr|interpark\.com|29cm\.co\.kr|wconcept\.co\.kr|a-bly\.com|zigzag\.kr|kream\.co\.kr|hmall\.com|gsshop\.com|cjonmall\.com|danawa\.com|bunjang\.co\.kr|daangn\.com|joongna\.com|amazon\.(com|co\.jp|co\.uk|de|fr|it|es|ca|com\.au|in)|ebay\.(com|co\.uk|de|fr|it|es|ca|com\.au)|aliexpress\.(com|us)|temu\.com|rakuten\.co\.jp|iherb\.com)$/i;

// 쇼핑몰 안에서 상품 상세로 보는 주소 단어. 국내 몰(product·goods·vp/ 등) + 아마존 /dp/·/gp/product/·/gp/aw/d/, 이베이 /itm/
export const PRODUCT_PATH = /(product|products|goods|item|vp\/|catalog|detail|\/dp\/|\/gp\/(product|aw\/d)\/|\/itm\/)/i;
/** 쇼핑몰이 아닌 사이트용: 경로 한 칸이 정확히 이 단어여야 한다(items·itemview 등은 제외). */
const STRICT_PRODUCT_PATH = /(^|\/)(products?|goods|item|itm|dp|vp|catalog)(\/|$)/i;

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
  if (isShopHost(u.hostname)) return PRODUCT_PATH.test(u.pathname) ? 'shop' : null;
  return STRICT_PRODUCT_PATH.test(u.pathname) ? 'needs-signal' : null;
}

/** 주소 기준 1차 판단(캡처 후보인지). 쇼핑몰이 아닌 사이트는 이후 상품 표시 확인이 더 필요하다. */
export function shouldCapture(url: string | undefined): boolean {
  return captureRule(url) !== null;
}
