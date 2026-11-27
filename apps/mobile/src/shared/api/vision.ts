// 스크롤 중 캡처한 화면을 Vision AI(성분표 OCR)로 바로 보낸다. 백엔드를 거치지 않는다.
// 흐름: 페이지마다 init(세션 시작) 한 번 → 스크롤하는 동안 0.7초마다 frame(0, 1, 2 …), 최대 15장.
// Vision이 세션을 끝냈다고 답하면(success · analysis_unavailable) 그 페이지에서는 더 보내지 않는다.
// 같은 내용이 apps/extension/src/shared/api/vision.ts에도 있다. 고치면 같이 고친다.

import type { Analysis } from '../types';

/** 스크롤 중 캡처 간격 */
export const FRAME_INTERVAL_MS = 700;
/** 마지막 스크롤 이벤트 뒤 이만큼 조용하면 멈춘 것으로 본다 */
export const SCROLL_STOP_MS = 250;
/** 페이지(Vision 세션)당 최대 프레임 수. Vision의 15프레임 상한과 같다 */
export const MAX_FRAMES = 15;

/** EXPO_PUBLIC_VISION_BASE_URL이 없으면 API 주소의 호스트에 8100 포트를 쓴다(실기기는 PC IP를 그대로 따라간다). */
function visionBase(): string {
  const explicit = process.env.EXPO_PUBLIC_VISION_BASE_URL?.trim();
  if (explicit) return explicit.replace(/\/$/, '');
  const api = process.env.EXPO_PUBLIC_API_BASE_URL?.trim() || process.env.EXPO_PUBLIC_API_URL?.trim() || 'http://127.0.0.1:8000';
  try {
    const u = new URL(api);
    return `${u.protocol}//${u.hostname}:8100`;
  } catch {
    return 'http://127.0.0.1:8100';
  }
}

const BASE = visionBase() + '/api/v1/vision';
// 로컬 개발용. 앱에 들어간 값은 누구나 볼 수 있으므로 운영 토큰을 넣지 않는다.
const TOKEN = process.env.EXPO_PUBLIC_VISION_TOKEN?.trim() || '';

/** 스크롤 캡처가 필요한 페이지: 분석이 끝났고 식품인데 성분표를 아직 못 찾은 경우(ingredient_status === 'not_found') */
export function wantsScrollFrames(status: string, analysis: Analysis | null): boolean {
  return status === 'done' && analysis?.ingredient_status === 'not_found';
}

export type VisionSessionStatus = 'processing' | 'success' | 'analysis_unavailable';

export class VisionError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function post(path: string, body: Record<string, unknown>): Promise<{ status?: VisionSessionStatus }> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (TOKEN) headers.Authorization = `Bearer ${TOKEN}`;
  let res: Response;
  try {
    res = await fetch(BASE + path, { method: 'POST', headers, body: JSON.stringify(body) });
  } catch {
    if (__DEV__) console.warn(`[kkulpick vision] POST ${path} 네트워크 실패 — Vision 주소(${BASE}) 확인`);
    throw new VisionError(0, 'NETWORK');
  }
  const json = await res.json().catch(() => null);
  if (!res.ok) {
    if (__DEV__) console.warn(`[kkulpick vision] POST ${path} → ${res.status}`, json?.detail ?? '');
    throw new VisionError(res.status, json?.detail ?? 'VISION_ERROR');
  }
  return json ?? {};
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
