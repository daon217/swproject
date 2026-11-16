import { router } from 'expo-router';
import { safeHttpUrl } from './shared/format';

// 다른 탭에서 '판매처로 이동'을 누르면 앱 안 브라우저 탭에서 연다.
type Listener = (url: string) => void;
let listener: Listener | null = null;
let pending: string | null = null;

export function setBrowserListener(cb: Listener | null) {
  listener = cb;
  if (cb && pending) {
    cb(pending);
    pending = null;
  }
}

export function openInBrowser(url: string) {
  const safe = safeHttpUrl(url);
  if (!safe) return;
  if (listener) listener(safe);
  else pending = safe;
  router.navigate('/');
}
