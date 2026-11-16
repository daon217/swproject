// 캡처 대상 화면 선별(명세 F-CAP-02). 상품 상세로 보이는 화면만 캡처하고 민감 화면은 제외한다.
// 최종 판단(상품 여부·상품/식품 구분)은 서버 분석 결과(result_kind)가 한다.

const SENSITIVE = /(login|signin|sign-in|auth|account|mypage|my-page|checkout|order|payment|pay\.|bank|cart|member)/i;
const SENSITIVE_HOSTS = /(bank|card|pay|gov|mail|accounts\.google)/i;
// 국내 몰(product·goods·vp/ 등) + 해외 몰: 아마존 /dp/·/gp/product/·/gp/aw/d/, 이베이 /itm/
export const PRODUCT_PATH = /(product|products|goods|item|vp\/|catalog|detail|\/dp\/|\/gp\/(product|aw\/d)\/|\/itm\/)/i;

export function shouldCapture(url: string | undefined): boolean {
  if (!url) return false;
  let u: URL;
  try {
    u = new URL(url);
  } catch {
    return false;
  }
  if (u.protocol !== 'https:' && u.protocol !== 'http:') return false;
  if (SENSITIVE_HOSTS.test(u.hostname)) return false;
  if (SENSITIVE.test(u.pathname)) return false;
  return PRODUCT_PATH.test(u.pathname);
}
