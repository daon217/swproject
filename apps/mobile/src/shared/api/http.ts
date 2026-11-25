import { Platform } from 'react-native';
import { getAuthToken, getGuestKey } from '../auth';
import { ApiError } from '../types';
import type { KkulpickApi } from './index';

// 개발 중(__DEV__)에만 Expo 콘솔에 요청 실패 원인을 남긴다. 비밀번호·토큰·요청 본문·쿼리 값은 남기지 않는다.
const LOOPBACK = /^(localhost|127\.0\.0\.1|\[::1\])$/i;

/** 기기에서 localhost/127.0.0.1로 접속하려는 흔한 실수를 알려 준다. */
function loopbackHint(url: string): string | null {
  if (Platform.OS === 'web') return null;
  let host = '';
  try {
    host = new URL(url).hostname;
  } catch {
    return null;
  }
  if (!LOOPBACK.test(host)) return null;
  return Platform.OS === 'android'
    ? '휴대폰·에뮬레이터에서 localhost/127.0.0.1은 기기 자신을 가리킵니다. 에뮬레이터는 http://10.0.2.2:8000, 실제 기기는 PC의 IP(예: http://192.168.0.10:8000)를 apps/mobile/.env의 EXPO_PUBLIC_API_BASE_URL에 넣고 Metro를 재시작하세요.'
    : '실제 기기에서 localhost/127.0.0.1은 기기 자신을 가리킵니다. PC의 IP를 apps/mobile/.env의 EXPO_PUBLIC_API_BASE_URL에 넣고 Metro를 재시작하세요.';
}

const B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';

/** base64 → 바이트. 전역 atob 유무에 기대지 않는다. */
export function base64ToBytes(b64: string): Uint8Array {
  const clean = b64.replace(/[^A-Za-z0-9+/]/g, '');
  const out = new Uint8Array(Math.floor((clean.length * 3) / 4));
  let o = 0;
  for (let i = 0; i < clean.length; i += 4) {
    const n =
      (B64.indexOf(clean[i]) << 18) |
      (B64.indexOf(clean[i + 1]) << 12) |
      ((i + 2 < clean.length ? B64.indexOf(clean[i + 2]) : 0) << 6) |
      (i + 3 < clean.length ? B64.indexOf(clean[i + 3]) : 0);
    out[o++] = (n >> 16) & 255;
    if (i + 2 < clean.length) out[o++] = (n >> 8) & 255;
    if (i + 3 < clean.length) out[o++] = n & 255;
  }
  return out.subarray(0, o);
}

/**
 * 캡처 JPEG를 FormData 파일 파트로 만든다.
 * Expo SDK 58은 전역 fetch를 expo/fetch로 바꾸는데, 이 구현은 RN 방식 { uri, name, type }을
 * "Unsupported FormDataPart implementation"으로 거부한다. 대신 bytes()를 가진 객체는 받아
 * name·type을 파일 이름·Content-Type으로 쓴다(expo/src/winter/fetch/convertFormData.ts).
 */
function jpegPart(base64: string): Blob {
  const bytes = base64ToBytes(base64);
  return { name: 'capture.jpg', type: 'image/jpeg', size: bytes.length, bytes: async () => bytes } as unknown as Blob;
}

// 실제 백엔드 연결용 구현. 응답 래퍼({data, request_id})와 오류({code,message,retryable})는 명세 17.1 기준.
export function createHttpApi(baseUrl: string): KkulpickApi {
  if (__DEV__) {
    console.log(`[kkulpick api] 서버 주소: ${baseUrl}`);
    const hint = loopbackHint(baseUrl);
    if (hint) console.warn(`[kkulpick api] ${hint}`);
  }

  async function request<T>(method: string, path: string, body?: unknown, headers: Record<string, string> = {}): Promise<T> {
    const token = await getAuthToken();
    const init: RequestInit = { method, headers: { ...headers } };
    if (token) (init.headers as Record<string, string>).Authorization = `Bearer ${token}`;
    // 비회원도 화면 분석을 받을 수 있게 분석 요청에는 기기 키를 보낸다(로그인하면 토큰만 보낸다).
    else if (path.startsWith('/analyses')) (init.headers as Record<string, string>)['X-Guest-Key'] = await getGuestKey();
    if (body instanceof FormData) init.body = body;
    else if (body !== undefined) {
      (init.headers as Record<string, string>)['Content-Type'] = 'application/json';
      init.body = JSON.stringify(body);
    }
    const url = `${baseUrl.replace(/\/$/, '')}${path}`;
    const logUrl = url.split('?')[0]; // 쿼리 값(아이디 등)은 콘솔에 남기지 않는다.
    let res: Response;
    try {
      res = await fetch(url, init);
    } catch (e) {
      if (__DEV__) {
        const reason = e instanceof Error ? `${e.name}: ${e.message}` : String(e);
        const hint = loopbackHint(url);
        console.warn(
          [
            `[kkulpick api] 네트워크 오류 ${method} ${logUrl}`,
            `  원인: ${reason}`,
            hint ? `  힌트: ${hint}` : null,
            '  그 밖에 확인할 것: API 서버 실행 여부, PC 방화벽(8000 포트), 휴대폰과 PC가 같은 Wi-Fi인지, http 주소 차단(Android cleartext), 웹 미리보기면 CORS',
          ]
            .filter(Boolean)
            .join('\n'),
        );
      }
      throw new ApiError(0, 'NETWORK', '네트워크 연결을 확인해 주세요.', true);
    }
    const json = res.status === 204 ? null : await res.json().catch(() => null);
    if (!res.ok) {
      const err = json?.error ?? json ?? {};
      if (__DEV__) {
        console.warn(`[kkulpick api] ${res.status} ${method} ${logUrl} → ${err.code ?? 'UNKNOWN'}${json?.request_id ? ` (request_id ${json.request_id})` : ''}`);
      }
      throw new ApiError(res.status, err.code ?? 'UNKNOWN', err.message ?? '요청을 처리하지 못했어요.', !!err.retryable);
    }
    return (json?.data ?? json) as T;
  }

  return {
    signup: (req) => request('POST', '/v2/auth/signup', req),
    checkLoginId: (login_id) => request('GET', `/v2/auth/login-id-availability?login_id=${encodeURIComponent(login_id)}`),
    login: (login_id, password) => request('POST', '/v2/auth/login', { login_id, password }),
    logout: async () => {
      await request('POST', '/v2/auth/logout').catch(() => undefined);
    },
    getMe: () => request('GET', '/v2/me'),
    updateProfile: (patch) => request('PATCH', '/v2/me/profile', patch),
    changePassword: (current_password, new_password, new_password_confirmation) =>
      request('PATCH', '/v2/me/password', { current_password, new_password, new_password_confirmation }),

    createAnalysis: (req) => {
      const form = new FormData();
      if (req.image) form.append('image', jpegPart(req.image.base64));
      form.append('page_url', req.page_url);
      if (req.selected_domain) form.append('selected_domain', req.selected_domain); // 기본은 미전송(서버 자동 판단)
      form.append('page_session_id', req.page_session_id);
      form.append('page_revision', String(req.page_revision));
      form.append('request_key', req.request_key);
      // 페이지에서 읽은 임시 정보는 서버의 검증된 상품 정보로 취급하지 않는다.
      return request('POST', '/analyses', form);
    },
    getAnalysis: (id) => request('GET', `/analyses/${encodeURIComponent(id)}`),
    cancelAnalysis: (id) => request('POST', `/analyses/${encodeURIComponent(id)}/cancel`),
    listHistory: () => request('GET', '/v2/me/analyses?limit=20'),
    listBasic: (domain = 'product') => request('GET', `/v2/recommendations/basic?limit=10&selected_domain=${domain}`),
    listFeatured: () => request('GET', '/v2/recommendations/featured?limit=10'),
    deleteAllHistory: () => request('POST', '/v2/me/data-deletions', { scope: 'history' }),
    deleteAccount: (current_password) => request('POST', '/v2/me/withdrawal', { current_password }),

    listPlans: () => request('GET', '/v2/subscription-plans'),
    createSubscription: (plan_id, payment_method, key) =>
      request('POST', '/v2/me/subscriptions', { plan_id, payment_method }, { 'Idempotency-Key': key }),
    getSubscription: () => request('GET', '/v2/me/subscription'),
    cancelRenewal: () => request('POST', '/v2/me/subscription/cancel'),

    getSupportConversation: () => request('POST', '/v2/support/conversations'),
    listSupportConversations: () => request('GET', '/v2/support/conversations?limit=5'),
    listSupportMessages: (id) => request('GET', `/v2/support/conversations/${encodeURIComponent(id)}/messages?limit=50`),
    sendSupportMessage: (id, body, client_message_id) =>
      request('POST', `/v2/support/conversations/${encodeURIComponent(id)}/messages`, { body, client_message_id }),
  };
}
