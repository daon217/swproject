import { getAuthToken } from '../auth';
import { ApiError } from '../types';
import type { KkulpickApi } from './index';

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
    let res: Response;
    try {
      res = await fetch(new URL(path, baseUrl), init);
    } catch {
      throw new ApiError(0, 'NETWORK', '네트워크 연결을 확인해 주세요.', true);
    }
    const json = res.status === 204 ? null : await res.json().catch(() => null);
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
      form.append('page_session_id', req.page_session_id);
      form.append('page_revision', String(req.page_revision));
      form.append('request_key', req.request_key);
      return request('POST', '/analyses', form);
    },
    getAnalysis: (id) => request('GET', `/analyses/${encodeURIComponent(id)}`),
    cancelAnalysis: (id) => request('POST', `/analyses/${encodeURIComponent(id)}/cancel`),
    listHistory: () => request('GET', '/v2/me/analyses?limit=20'),
    listFeatured: () => request('GET', '/v2/recommendations/featured?limit=10'),
    deleteAllHistory: () => request('POST', '/v2/me/data-deletions', { scope: 'history' }),

    listPlans: () => request('GET', '/v2/subscription-plans'),
    createSubscription: (plan_id, payment_method, key) =>
      request('POST', '/v2/me/subscriptions', { plan_id, payment_method }, { 'Idempotency-Key': key }),
    getSubscription: () => request('GET', '/v2/me/subscription'),

    getSupportConversation: () => request('GET', '/v2/support/conversations?limit=1').then((list: any) => list[0]),
    listSupportMessages: (id) => request('GET', `/v2/support/conversations/${encodeURIComponent(id)}/messages?limit=50`),
    sendSupportMessage: (id, body, client_message_id) =>
      request('POST', `/v2/support/conversations/${encodeURIComponent(id)}/messages`, { body, client_message_id }),
  };
}
