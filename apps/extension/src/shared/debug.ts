// 분석 흐름 디버그 로그. .env에 VITE_DEBUG_LOG=true일 때만 출력한다(기본 꺼짐).
// 보는 곳: 백그라운드 = chrome://extensions → 꿀픽 → "서비스 워커" 검사, 사이드패널 = 패널에서 우클릭 → 검사.
// 비밀번호·토큰은 가리고, 이미지는 크기·형식만 출력한다.
export const debugEnabled = import.meta.env.VITE_DEBUG_LOG === 'true';

const SECRET = /password|token|authorization|secret/i;

export function redact(value: unknown, depth = 0): unknown {
  if (value == null || depth > 6) return value;
  if (value instanceof Blob) return `[${value.type || 'blob'} ${(value.size / 1024).toFixed(1)}KB]`;
  if (typeof value === 'string') return value.startsWith('data:') ? `[dataURL ${(value.length / 1024).toFixed(1)}KB]` : value;
  if (value instanceof FormData) {
    const out: Record<string, unknown> = {};
    value.forEach((v, k) => { out[k] = SECRET.test(k) ? '***' : redact(v, depth + 1); });
    return out;
  }
  if (value instanceof Error) return { name: value.name, message: value.message, ...(redact({ ...value }, depth + 1) as object) };
  if (Array.isArray(value)) return value.map((v) => redact(v, depth + 1));
  if (typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) out[k] = SECRET.test(k) ? '***' : redact(v, depth + 1);
    return out;
  }
  return value;
}

export function dlog(scope: string, message: string, data?: unknown) {
  if (!debugEnabled) return;
  const time = new Date().toISOString().slice(11, 23);
  if (data === undefined) console.log(`%c[꿀픽:${scope}]%c ${time} ${message}`, 'color:#e0a400;font-weight:bold', '');
  else console.log(`%c[꿀픽:${scope}]%c ${time} ${message}`, 'color:#e0a400;font-weight:bold', '', redact(data));
}
