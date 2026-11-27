import { useEffect, useState, type ComponentRef, type RefObject } from 'react';
import { Platform, type View } from 'react-native';
import { captureRef } from 'react-native-view-shot';
import {
  FRAME_INTERVAL_MS,
  initVisionSession,
  MAX_FRAMES,
  SCROLL_STOP_MS,
  sendVisionFrame,
  VisionError,
  wantsScrollFrames,
} from './shared/api/vision';
import type { PageScan } from './shared/pageProductScript';
import type { PageAnalysis } from './usePageAnalysis';

// 앱 안 브라우저에서 스크롤하는 동안 0.7초마다 보이는 화면을 캡처해 Vision AI로 바로 보낸다(확장과 같은 규칙).
// - 성분표를 아직 못 찾은 식품 페이지(ingredient_status === 'not_found')에서만 동작한다.
// - 스크롤이 멈추면(250ms 동안 스크롤 신호 없음) 바로 멈추고 더 보내지 않는다.
// - 페이지마다 init 한 번, frame 최대 25장. Vision이 세션을 끝내면 그 페이지에서는 멈춘다.
// 스크롤 신호는 WebView에 주입한 스크립트(pageProductScript.ts)가 'kp-scroll'로 보낸다.

interface Context {
  url: string | null;
  page: PageAnalysis;
  captureTarget: RefObject<ComponentRef<typeof View> | null>;
  getPageScan?: (url: string) => PageScan | undefined;
}

interface Stream {
  sessionId: string;
  next: number;
  inited: boolean;
  ended: boolean;
  busy: boolean;
  failures: number;
}

/** 타이머·세션 상태는 렌더와 상관없이 이 안에서만 바뀐다 */
function createScrollFrames() {
  let ctx: Context | null = null;
  let tick: ReturnType<typeof setTimeout> | null = null;
  let idle: ReturnType<typeof setTimeout> | null = null;
  let stream: Stream | null = null;

  const stop = () => {
    if (tick) clearTimeout(tick);
    if (idle) clearTimeout(idle);
    tick = idle = null;
  };

  const wanted = () => {
    if (Platform.OS === 'web' || !ctx?.url || !ctx.page.pageSessionId) return false;
    if (!wantsScrollFrames(ctx.page.status, ctx.page.analysis)) return false;
    return !(stream && stream.sessionId === ctx.page.pageSessionId && (stream.ended || stream.next >= MAX_FRAMES));
  };

  const sendFrame = async () => {
    if (!ctx?.url) return;
    const { url, page, captureTarget, getPageScan } = ctx;
    if (!stream || stream.sessionId !== page.pageSessionId) {
      stream = { sessionId: page.pageSessionId, next: 0, inited: false, ended: false, busy: false, failures: 0 };
    }
    const s = stream;
    if (s.busy || s.ended || s.next >= MAX_FRAMES) return; // 앞 프레임 전송 중이면 이번 차례는 건너뛴다
    s.busy = true;
    try {
      const image = await captureRef(captureTarget as Parameters<typeof captureRef>[0], { format: 'jpg', quality: 0.8, result: 'base64' });
      if (stream !== s) return; // 캡처하는 사이 페이지가 바뀌었다
      if (!s.inited) {
        const scan = getPageScan?.(url);
        const init = await initVisionSession({ session_id: s.sessionId, product_name: scan?.product?.name, price: scan?.product?.price, first_frame_image: image });
        s.inited = true;
        // 일반 상품처럼 Vision이 시작하자마자 세션을 끝내면 프레임을 보내지 않는다.
        if (init.status && init.status !== 'processing') s.ended = true;
      }
      if (!s.ended) {
        const frame_index = s.next++;
        const is_last_frame = frame_index === MAX_FRAMES - 1;
        const res = await sendVisionFrame({ session_id: s.sessionId, frame_index, image, is_last_frame });
        if (is_last_frame || (res.status && res.status !== 'processing')) s.ended = true;
      }
      s.failures = 0;
    } catch (e) {
      // 세션이 만료됐으면(404) 다음 차례에 다시 시작한다. Vision이 계속 응답하지 않으면 이 페이지에서는 멈춘다.
      if (e instanceof VisionError && e.status === 404) s.inited = false;
      if (++s.failures >= 3) s.ended = true;
    } finally {
      s.busy = false;
    }
  };

  const next = () => {
    tick = setTimeout(() => {
      if (!wanted()) return stop();
      void sendFrame();
      next();
    }, FRAME_INTERVAL_MS);
  };

  return {
    update(c: Context) {
      ctx = c;
    },
    /** 페이지가 바뀌면 진행 중인 캡처를 멈추고 새로 센다 */
    reset() {
      stop();
      stream = null;
    },
    stop,
    /** WebView가 보낸 스크롤 신호. 지금 보는 탭의 신호만 넘긴다 */
    onScroll() {
      if (!wanted()) return stop();
      if (idle) clearTimeout(idle);
      idle = setTimeout(stop, SCROLL_STOP_MS); // 멈춘 순간 캡처 중단
      if (!tick) next();
    },
  };
}

export function useScrollFrames(
  url: string | null,
  page: PageAnalysis,
  captureTarget: RefObject<ComponentRef<typeof View> | null>,
  getPageScan?: (url: string) => PageScan | undefined,
) {
  const [ctl] = useState(createScrollFrames);
  useEffect(() => {
    ctl.update({ url, page, captureTarget, getPageScan });
  });
  useEffect(() => {
    ctl.reset();
  }, [ctl, url, page.pageSessionId]);
  useEffect(() => () => ctl.stop(), [ctl]);
  return { onScroll: ctl.onScroll };
}
