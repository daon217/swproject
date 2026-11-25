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
