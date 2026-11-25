import { PRODUCT_PATH } from '../pageFilter';
import type { Domain, OfferCard } from '../types';

// 목업 추천 데이터. Figma 시안의 예시 상품을 그대로 사용한다. 실제 데이터가 아니다.

const now = () => new Date().toISOString();

function card(id: string, kind: Domain, name: string, subtitle: string, price: string, reason: string): OfferCard {
  return {
    offer_id: id,
    name,
    subtitle,
    price,
    currency: 'KRW',
    observed_at: now(),
    availability: 'available',
    url: `https://example.com/offers/${id}`,
    reason,
    affiliate: false,
    image_kind: kind,
  };
}

export const PRINTER_AI = [
  card('p-ink', 'product', '잉크탱크 흑백 프린터', '흑백 인쇄 · 프린터', '169000', '예상 출력량과 잉크 유지비를 비교하세요.'),
  card('p-laser', 'product', '소형 흑백 레이저 프린터', '흑백 인쇄 · 프린터', '139000', '문서 출력 속도와 토너 비용을 비교하세요.'),
  card('p-wifi', 'product', '무선 흑백 프린터', '흑백 인쇄 · 프린터', '159000', '무선 연결과 지원 기기를 확인하세요.'),
];

export const PRINTER_USED = [
  card('u-m1120', 'product', '엡손 M1120 · 중고', '중고 · 출력 상태 확인', '110000', '중고 매물이에요. 출력 상태와 잉크·토너 잔량을 확인하세요.'),
  card('u-laser', 'product', '흑백 레이저 프린터 · 중고', '중고 · 출력 상태 확인', '72000', '중고 매물이에요. 드럼 수명과 출력 매수를 확인하세요.'),
  card('u-wifi', 'product', '무선 흑백 프린터 · 중고', '중고 · 출력 상태 확인', '89000', '중고 매물이에요. 무선 연결 동작을 확인하세요.'),
];

export const SNACK_AI = [
  card('f-rice', 'food', '라이스 크리스프', '쌀과자 · 120g', '12000', '설정한 재료를 고려한 추천 후보예요.'),
  card('f-brown', 'food', '담백한 현미 스낵', '현미 · 3개입', '10200', '선호 재료인 현미를 포함한 후보예요.'),
  card('f-orig', 'food', '오리지널 쌀과자', '쌀과자 · 2개입', '9900', '담백한 맛을 찾는 분께 추천해요.'),
];

/** 비회원 시작 화면 추천 상품(목업 제휴 상품). 제휴 사실은 화면에 표시한다(명세 10.3). */
export const FEATURED = [
  card('a-ink', 'product', '잉크탱크 흑백 프린터', '흑백 인쇄 · 프린터', '169000', '이번 주 많이 찾는 프린터예요.'),
  card('a-rice', 'food', '라이스 크리스프', '쌀과자 · 120g', '12000', '담백한 간식을 찾는 분께 인기예요.'),
  card('a-laser', 'product', '소형 흑백 레이저 프린터', '흑백 인쇄 · 프린터', '139000', '문서 출력이 많은 분께 추천해요.'),
  card('a-brown', 'food', '담백한 현미 스낵', '현미 · 3개입', '10200', '현미로 만든 가벼운 간식이에요.'),
].map((c) => ({ ...c, affiliate: true }));

/** 현재 보고 있는 상품의 목업 정보 */
export interface MockPage {
  domain: Domain;
  name: string;
  /** 현재 상품에 함유된 성분 코드(목업) */
  contains: string[];
}

/** URL로 목업 페이지를 고른다. 실제로는 서버가 캡처 이미지를 분석해 결정한다. */
export function mockPageFor(url: string): MockPage | null {
  let u: URL;
  try {
    u = new URL(url);
  } catch {
    return null;
  }
  if (!/^https?:$/.test(u.protocol)) return null;
  const s = decodeURIComponent(u.href).toLowerCase();
  const isProductPage = PRODUCT_PATH.test(u.pathname);
  if (!isProductPage) return null;
  if (/(snack|food|kurly|마켓컬리|과자|식품|4021)/.test(s)) {
    return { domain: 'food', name: '정화 오징어는땅콩을좋아해 40g, 10개', contains: ['peanut', 'squid', 'wheat'] };
  }
  return { domain: 'product', name: '엡손 M1120 잉크포함 무한잉크 흑백 프린터', contains: [] };
}
