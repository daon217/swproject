import { getItem, KEYS, removeItem, setItem } from './storage';

export interface AuthState {
  token: string;
  login_id: string;
}

export async function getAuth(): Promise<AuthState | null> {
  return getItem<AuthState | null>(KEYS.auth, null);
}

export async function getAuthToken(): Promise<string | null> {
  return (await getAuth())?.token ?? null;
}

export async function saveAuth(state: AuthState): Promise<void> {
  await setItem(KEYS.auth, state);
}

export async function clearAuth(): Promise<void> {
  await removeItem(KEYS.auth);
}

/** 비회원 분석용 기기 키. 처음 쓸 때 만들고 이 기기에만 저장한다(무작위 64자, 개인정보 아님). */
export async function getGuestKey(): Promise<string> {
  const saved = await getItem<string | null>(KEYS.guestKey, null);
  if (saved && /^[A-Za-z0-9_-]{32,128}$/.test(saved)) return saved;
  const key = (crypto.randomUUID() + crypto.randomUUID()).replace(/-/g, '');
  await setItem(KEYS.guestKey, key);
  return key;
}
