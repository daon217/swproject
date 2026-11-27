import { dlog } from '../debug';
import type { TabState } from '../messages';

// 스크롤 중 캡처한 화면을 Vision AI(성분표 OCR)로 바로 보낸다. 백엔드를 거치지 않는다.
// 흐름: 페이지마다 init(세션 시작) 한 번 → 스크롤하는 동안 0.7초마다 frame(0, 1, 2 …), 최대 25장.
// Vision이 세션을 끝냈다고 답하면(success · analysis_unavailable) 그 페이지에서는 더 보내지 않는다.
// 같은 내용이 apps/mobile/src/shared/api/vision.ts에도 있다. 고치면 같이 고친다.

/** 스크롤 중 캡처 간격 */
export const FRAME_INTERVAL_MS = 700;
/** 마지막 스크롤 이벤트 뒤 이만큼 조용하면 멈춘 것으로 본다 */
export const SCROLL_STOP_MS = 250;
/** 페이지(Vision 세션)당 최대 프레임 수. Vision의 MAX_FRAME_LIMIT과 맞춰야 한다 */
export const MAX_FRAMES = 25;

const BASE = (import.meta.env.VITE_VISION_BASE_URL || 'http://127.0.0.1:8100').replace(/\/$/, '') + '/api/v1/vision';
// 로컬 개발용. 확장에 넣은 값은 누구나 볼 수 있으므로 운영 토큰을 넣지 않는다.
const TOKEN = import.meta.env.VITE_VISION_TOKEN || '';

/** 스크롤 캡처가 필요한 페이지: 분석이 끝났고 식품인데 성분표를 아직 못 찾은 경우(ingredient_status === 'not_found') */
export function wantsScrollFrames(state: TabState | null | undefined): boolean {
  return !!state && state.status === 'done' && state.analysis?.ingredient_status === 'not_found';
}

export type VisionSessionStatus = 'processing' | 'success' | 'analysis_unavailable';

export class VisionError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

/** 마지막 프레임을 보낸 뒤 이 시간 동안 Vision 결과(status)를 1초마다 확인한다 */
export const STATUS_POLL_MS = 1000;
export const STATUS_WAIT_MS = 20_000;

/** GET /status 응답. success + ingredients가 있으면 성분표를 찾은 것이다 */
export interface VisionResult {
  status: VisionSessionStatus;
  product_category?: string | null;
  ingredients?: string[];
}

async function request<T>(method: 'GET' | 'POST', path: string, body?: Record<string, unknown>): Promise<T> {
  const headers: Record<string, string> = {};
  if (body) headers['Content-Type'] = 'application/json';
  if (TOKEN) headers.Authorization = `Bearer ${TOKEN}`;
  const t0 = Date.now();
  let res: Response;
  try {
    res = await fetch(BASE + path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  } catch (e) {
    dlog('vision', `✕ ${method} ${path} 네트워크 실패 (${Date.now() - t0}ms) — Vision 꺼짐/주소 오류`, String(e));
    throw new VisionError(0, 'NETWORK');
  }
  const json = await res.json().catch(() => null);
  dlog('vision', `← ${res.status} ${method} ${path} (${Date.now() - t0}ms)`, json);
  if (!res.ok) throw new VisionError(res.status, json?.detail ?? 'VISION_ERROR');
  return (json ?? {}) as T;
}

const post = (path: string, body: Record<string, unknown>) => request<{ status?: VisionSessionStatus }>('POST', path, body);

/** 세션 결과 조회. 프레임은 접수(202)만 되고 실제 분석은 나중에 끝나므로 이걸로 끝났는지 본다 */
export function getVisionStatus(session_id: string) {
  return request<VisionResult>('GET', `/status/${encodeURIComponent(session_id)}`);
}

/** 스크롤 중 성분표를 찾았는지(일반 상품 조기 종료는 success지만 성분이 비어 있다) */
export function foundIngredients(v: VisionResult): boolean {
  return v.status === 'success' && (v.ingredients?.length ?? 0) > 0;
}

/** 세션 시작. 상품명이 없으면 첫 화면으로 Vision이 상품명을 찾는다 */
export function initVisionSession(req: { session_id: string; product_name?: string | null; price?: string | null; first_frame_image?: string }) {
  const price = req.price && /^\d+$/.test(req.price) ? Number(req.price) : undefined;
  return post('/init', {
    session_id: req.session_id,
    product_name: req.product_name || undefined,
    price,
    first_frame_image: req.product_name ? undefined : req.first_frame_image,
  });
}

/** 프레임 한 장. 응답 status가 processing이 아니면 세션이 끝난 것이다 */
export function sendVisionFrame(req: { session_id: string; frame_index: number; image: string; is_last_frame: boolean }) {
  return post('/frame', req);
}
