import { getAuthToken } from '../auth';
import { ApiError } from '../types';
import type { KkulpickApi } from './index';
import { dlog } from '../debug';

// 실제 백엔드 연결용 구현. 응답 래퍼({data, request_id})와 오류({code,message,retryable})는 명세 17.1 기준.
export function createHttpApi(baseUrl: string): KkulpickApi {
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
    const t0 = Date.now();
    dlog('http', `→ ${method} ${url}`, body);
    let res: Response;
    try {
      res = await fetch(url, init);
    } catch (e) {
      dlog('http', `✕ ${method} ${url} 네트워크 실패 (${Date.now() - t0}ms) — 서버 꺼짐/주소 오류/CORS`, String(e));
      throw new ApiError(0, 'NETWORK', '네트워크 연결을 확인해 주세요.', true);
    }
    const json = res.status === 204 ? null : await res.json().catch(() => null);
    dlog('http', `← ${res.status} ${method} ${path} (${Date.now() - t0}ms)`, json);
    if (!res.ok) {
      const err = json?.error ?? json ?? {};
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
      if (req.image) form.append('image', req.image, 'capture.jpg');
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
