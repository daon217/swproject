import type { Analysis } from './types';

/** 탭 단위 분석 상태. 탭·URL·페이지 버전이 바뀌면 이전 결과는 폐기된다(명세 F-CAP-03). */
export interface TabState {
  tabId: number;
  url: string;
  page_session_id: string;
  page_revision: number;
  status: 'none' | 'analyzing' | 'done' | 'error';
  analysis: Analysis | null;
  error: string | null;
}

/** 사이드 패널에서 바로 열 화면 */
export type PanelRoute = 'premium' | 'filter' | 'login' | 'recommend';

export type Message =
  | { type: 'getPanelVisibility' }
  | { type: 'panelVisibility'; open: boolean }
  | { type: 'getTabState' } // content → bg (sender 탭)
  | { type: 'getActiveTabState' } // sidepanel → bg
  | { type: 'reanalyze' } // sidepanel → bg (로그인·설정·결제 변경 후)
  | { type: 'retry'; tabId?: number }
  | { type: 'openSidePanel'; route: PanelRoute } // content → bg (사용자 클릭)
  | { type: 'openUrl'; url: string }
  | { type: 'openRecommendedUrl'; url: string } // 추천 상품 클릭 시 새 탭에서 자동 재분석하지 않고 열기
  | { type: 'tabState'; state: TabState } // bg → content / sidepanel
  | { type: 'extractProduct' } // bg → content: 상품 표시 여부 + [임시] 페이지 상품명·가격 읽기(PageScan)
  | { type: 'scrollFrame' }; // content → bg: 스크롤 중 화면 한 장을 캡처해 Vision AI로 보내기. 응답 { more }

export function sendMessage<T = unknown>(msg: Message): Promise<T | undefined> {
  if (typeof chrome === 'undefined' || !chrome.runtime?.id) {
    // 확장 밖 미리보기: 재분석 요청만 페이지 이벤트로 전달한다.
    if (msg.type === 'reanalyze' && typeof window !== 'undefined') window.dispatchEvent(new Event('kp-reanalyze'));
    return Promise.resolve(undefined);
  }
  return chrome.runtime.sendMessage(msg).catch(() => undefined) as Promise<T | undefined>;
}
