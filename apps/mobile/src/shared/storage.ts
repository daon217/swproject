import AsyncStorage from '@react-native-async-storage/async-storage';

// AsyncStorage 래퍼(확장의 chrome.storage 래퍼와 같은 모양). 같은 앱 안의 변경을 구독할 수 있다.

const listeners = new Map<string, Set<() => void>>();
const emit = (key: string) => listeners.get(key)?.forEach((cb) => cb());

export async function getItem<T>(key: string, fallback: T): Promise<T> {
  try {
    const raw = await AsyncStorage.getItem(key);
    return raw == null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

export async function setItem<T>(key: string, value: T): Promise<void> {
  try {
    await AsyncStorage.setItem(key, JSON.stringify(value));
    emit(key);
  } catch {
    /* 저장 실패는 화면 동작을 막지 않는다 */
  }
}

export async function removeItem(key: string): Promise<void> {
  try {
    await AsyncStorage.removeItem(key);
    emit(key);
  } catch {
    /* noop */
  }
}

export function onItemChange(key: string, cb: () => void): () => void {
  if (!listeners.has(key)) listeners.set(key, new Set());
  listeners.get(key)!.add(cb);
  const crossTab = (event: StorageEvent) => { if (event.key === key || event.key === null) cb(); };
  const web = typeof window !== 'undefined' && typeof window.addEventListener === 'function';
  if (web) window.addEventListener('storage', crossTab);
  return () => {
    listeners.get(key)?.delete(cb);
    if (web) window.removeEventListener('storage', crossTab);
  };
}

export const KEYS = {
  auth: 'kp.auth',
  shortcuts: 'kp.shortcuts',
  mockDb: 'kp.mock.db',
  /** 비회원 분석용 기기 키(무작위). 서버가 이 키로 비회원 분석의 주인을 구분한다. 로그아웃해도 유지 */
  guestKey: 'kp.guestKey',
} as const;
