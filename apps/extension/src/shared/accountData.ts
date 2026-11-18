import { getItem, setItem, removeItem } from './storage';
export const accountKey = (userId: string, kind: string) => `kp.user.${encodeURIComponent(userId)}.${kind}`;
export async function clearAccountData(userId: string) {
  await pending.get(userId);
  await Promise.all(['shortcuts', 'visits', 'lastPage'].map(kind => removeItem(accountKey(userId, kind))));
}
export interface Visit { url: string; at: number }
const MAX_AGE = 30 * 86400000;
export async function loadVisits(userId: string | undefined): Promise<Visit[]> {
  if (!userId) return [];
  const items = await getItem<Visit[]>(accountKey(userId, 'visits'), []);
  const valid = Array.isArray(items) ? items.filter(v => typeof v?.url === 'string' && v.at > Date.now() - MAX_AGE).slice(0, 50) : [];
  if (JSON.stringify(items) !== JSON.stringify(valid)) await setItem(accountKey(userId, 'visits'), valid);
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
export function recordVisit(userId: string | undefined, raw: string): Promise<void> {
  const url = historyUrl(raw);
  if (!userId || !url) return Promise.resolve();
  const previous = pending.get(userId) ?? Promise.resolve();
  const next = previous.catch(() => undefined).then(async () => {
    const list = await loadVisits(userId);
    await setItem(accountKey(userId, 'visits'), [{ url, at: Date.now() }, ...list.filter(v => v.url !== url)].slice(0, 50));
  });
  pending.set(userId, next);
  void next.finally(() => { if (pending.get(userId) === next) pending.delete(userId); });
  return next;
}
export async function clearVisits(userId: string | undefined) {
  if (!userId) return;
  await pending.get(userId);
  await removeItem(accountKey(userId, 'visits'));
  await removeItem(accountKey(userId, 'lastPage'));
}
