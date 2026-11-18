import { getItem, KEYS, setItem } from './storage';

// 상품 추천 켜기/끄기(사이드 패널 맨 위 스위치). 기본은 꺼짐.
// 꺼져 있으면 화면 캡처·분석을 하지 않고 플로팅도 띄우지 않는다. 브라우저(chrome.storage.local)에 저장한다.

export function isRecommendEnabled(): Promise<boolean> {
  return getItem<boolean>(KEYS.recommendEnabled, false);
}

export function setRecommendEnabled(on: boolean): Promise<void> {
  return setItem(KEYS.recommendEnabled, on);
}
