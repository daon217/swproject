import { Platform } from 'react-native';
import { getAuthToken } from '../auth';
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
      // React Native FormData 파일 형식
      if (req.image) form.append('image', { uri: req.image.uri, name: 'capture.jpg', type: 'image/jpeg' } as unknown as Blob);
      form.append('page_url', req.page_url);
      form.append('selected_domain', req.selected_domain ?? 'product');
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
    listSupportMessages: (id) => request('GET', `/v2/support/conversations/${encodeURIComponent(id)}/messages?limit=50`),
    sendSupportMessage: (id, body, client_message_id) =>
      request('POST', `/v2/support/conversations/${encodeURIComponent(id)}/messages`, { body, client_message_id }),
  };
}
