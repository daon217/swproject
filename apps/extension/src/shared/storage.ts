// chrome.storage.local 래퍼. 확장 밖(개발용 미리보기)에서는 localStorage로 대체한다.

const hasChromeStorage = typeof chrome !== 'undefined' && !!chrome.storage?.local;

export async function getItem<T>(key: string, fallback: T): Promise<T> {
  try {
    if (hasChromeStorage) {
      const res = await chrome.storage.local.get(key);
      return (res[key] as T | undefined) ?? fallback;
    }
    const raw = localStorage.getItem(key);
    return raw == null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

export async function setItem<T>(key: string, value: T): Promise<void> {
  try {
    if (hasChromeStorage) {
      await chrome.storage.local.set({ [key]: value });
      return;
    }
    localStorage.setItem(key, JSON.stringify(value));
    window.dispatchEvent(new CustomEvent('kp-storage', { detail: { key } }));
  } catch {
    /* 저장 실패는 화면 동작을 막지 않는다 */
  }
}

export async function removeItem(key: string): Promise<void> {
  try {
    if (hasChromeStorage) await chrome.storage.local.remove(key);
    else {
      localStorage.removeItem(key);
      window.dispatchEvent(new CustomEvent('kp-storage', { detail: { key } }));
    }
  } catch {
    /* noop */
  }
}

/** 특정 키가 바뀔 때 호출된다. 반환값으로 구독을 해제한다. */
export function onItemChange(key: string, cb: () => void): () => void {
  if (hasChromeStorage) {
    const listener = (changes: Record<string, chrome.storage.StorageChange>, area: string) => {
      if (area === 'local' && key in changes) cb();
    };
    chrome.storage.onChanged.addListener(listener);
    return () => chrome.storage.onChanged.removeListener(listener);
  }
  const listener = (e: Event) => {
    if ((e as CustomEvent).detail?.key === key) cb();
  };
  const crossTab = (e: StorageEvent) => { if (e.key === key || e.key === null) cb(); };
  window.addEventListener('kp-storage', listener);
  window.addEventListener('storage', crossTab);
  return () => { window.removeEventListener('kp-storage', listener); window.removeEventListener('storage', crossTab); };
}

export const KEYS = {
  auth: 'kp.auth',
  shortcuts: 'kp.shortcuts',
  mockDb: 'kp.mock.db',
  /** 비회원 분석용 기기 키(무작위). 서버가 이 키로 비회원 분석의 주인을 구분한다. 로그아웃해도 유지 */
  guestKey: 'kp.guestKey',
  pendingRoute: 'kp.pendingRoute',
  /** 상품 추천 켜기/끄기(기본 꺼짐) */
  recommendEnabled: 'kp.recommendEnabled',
} as const;
