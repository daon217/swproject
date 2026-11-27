import { getItem, setItem, removeItem } from './storage';
export const accountKey = (userId: string, kind: string) => `kp.user.${encodeURIComponent(userId || 'guest')}.${kind}`;
export async function clearAccountData(userId: string) {
  const uid = userId || 'guest';
  await pending.get(uid);
  await Promise.all(['shortcuts', 'visits', 'lastPage', 'browserTabs', 'searchEngine'].map(kind => removeItem(accountKey(uid, kind))));
}

export interface SearchEngineItem {
  id: 'naver' | 'google' | 'daum';
  label: string;
  queryUrl: string;
}

export const SEARCH_ENGINES: SearchEngineItem[] = [
  { id: 'naver', label: 'Naver', queryUrl: 'https://m.search.naver.com/search.naver?query=' },
  { id: 'google', label: 'Google', queryUrl: 'https://www.google.com/search?q=' },
  { id: 'daum', label: 'Daum', queryUrl: 'https://m.search.daum.net/search?q=' },
];

export async function loadSearchEngineIndex(userId?: string): Promise<number> {
  const uid = userId || 'guest';
  const idx = await getItem<number>(accountKey(uid, 'searchEngine'), 0);
  return typeof idx === 'number' && idx >= 0 && idx < SEARCH_ENGINES.length ? idx : 0;
}

export async function saveSearchEngineIndex(index: number, userId?: string): Promise<void> {
  const uid = userId || 'guest';
  await setItem(accountKey(uid, 'searchEngine'), index);
}
export interface Visit { url: string; title?: string; at: number }
const MAX_AGE = 30 * 86400000;
export async function loadVisits(userId: string | undefined): Promise<Visit[]> {
  const uid = userId || 'guest';
  const items = await getItem<Visit[]>(accountKey(uid, 'visits'), []);
  const valid = Array.isArray(items) ? items.filter(v => typeof v?.url === 'string' && v.at > Date.now() - MAX_AGE).slice(0, 50) : [];
  if (JSON.stringify(items) !== JSON.stringify(valid)) await setItem(accountKey(uid, 'visits'), valid);
  return valid;
}
// Only deliberate in-app navigation is recorded. Never collect global browser history.
// Strip query/hash/userinfo to avoid persisting authentication codes or search text.
export function historyUrl(raw: string): string | null {
  try {
    const u = new URL(raw);
    if (!['http:', 'https:'].includes(u.protocol) || u.username || u.password) return null;
    if (/login|signin|oauth|callback|checkout|payment|password/i.test(u.pathname)) return null;
    u.search = ''; u.hash = '';
    return u.href;
  } catch { return null; }
}
const pending = new Map<string, Promise<void>>();
export function recordVisit(userId: string | undefined, raw: string, title?: string | null): Promise<void> {
  const uid = userId || 'guest';
  const url = historyUrl(raw);
  if (!url) return Promise.resolve();
  const previous = pending.get(uid) ?? Promise.resolve();
  const next = previous.catch(() => undefined).then(async () => {
    const list = await loadVisits(uid);
    const prevMatch = list.find(v => v.url === url);
    const cleanTitle = title?.trim() || prevMatch?.title || undefined;
    await setItem(accountKey(uid, 'visits'), [{ url, title: cleanTitle, at: Date.now() }, ...list.filter(v => v.url !== url)].slice(0, 50));
  });
  pending.set(uid, next);
  void next.finally(() => { if (pending.get(uid) === next) pending.delete(uid); });
  return next;
}
export async function removeVisits(userId: string | undefined, urlsToRemove: string[]): Promise<Visit[]> {
  const uid = userId || 'guest';
  await pending.get(uid);
  const removeSet = new Set(urlsToRemove);
  const list = await loadVisits(uid);
  const next = list.filter(v => !removeSet.has(v.url));
  await setItem(accountKey(uid, 'visits'), next);
  return next;
}
export async function clearVisits(userId: string | undefined) {
  const uid = userId || 'guest';
  await pending.get(uid);
  await removeItem(accountKey(uid, 'visits'));
  await removeItem(accountKey(uid, 'lastPage'));
}

export interface PersistedBrowserTab {
  id: string;
  source: string | null;
  url: string | null;
  title: string | null;
}

export interface PersistedBrowserSession {
  tabs: PersistedBrowserTab[];
  activeId: string;
}

export async function loadBrowserSession(userId?: string): Promise<PersistedBrowserSession | null> {
  const uid = userId || 'guest';
  const data = await getItem<PersistedBrowserSession | null>(accountKey(uid, 'browserTabs'), null);
  if (!data || !Array.isArray(data.tabs) || data.tabs.length === 0) return null;
  return data;
}

export async function saveBrowserSession(session: PersistedBrowserSession, userId?: string): Promise<void> {
  const uid = userId || 'guest';
  await setItem(accountKey(uid, 'browserTabs'), session);
}
