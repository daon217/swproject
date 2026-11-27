import { useEffect, useState, type ComponentRef, type RefObject } from 'react';
import { Platform, type View } from 'react-native';
import { captureRef } from 'react-native-view-shot';
import {
  endVisionSession,
  FRAME_INTERVAL_MS,
  getVisionStatus,
  initVisionSession,
  MAX_FRAMES,
  refreshesResult,
  SCROLL_STOP_MS,
  sendVisionFrame,
  STATUS_POLL_MS,
  STATUS_WAIT_MS,
  VisionError,
  wantsScrollFrames,
} from './shared/api/vision';
import type { PageScan } from './shared/pageProductScript';
import type { PageAnalysis } from './usePageAnalysis';

// 앱 안 브라우저에서 스크롤하는 동안 0.7초마다 보이는 화면을 캡처해 Vision AI로 바로 보낸다(확장과 같은 규칙).
// - 성분표를 아직 못 찾은 상품 페이지(식품 not_found · 화장품 등 not_applicable)에서 동작한다.
//   일반 상품이면 Vision이 init(1단계)에서 세션을 바로 끝낸다.
// - 다른 페이지로 가거나 화면을 떠나면 진행 중인 세션에 is_last_frame을 보내 마감한다.
// - 스크롤이 멈추면(250ms 동안 스크롤 신호 없음) 바로 멈추고 더 보내지 않는다.
// - 페이지마다 init 한 번, frame 최대 25장. Vision이 세션을 끝내면 그 페이지에서는 멈춘다.
// 스크롤 신호는 WebView에 주입한 스크립트(pageProductScript.ts)가 'kp-scroll'로 보낸다.

type Page = PageAnalysis & { reanalyzeWith: (base64: string) => void };

interface Context {
  url: string | null;
  page: Page;
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
  /** 마지막으로 보낸 프레임(base64). 성분표를 찾으면 이 이미지로 백엔드 분석을 다시 받는다 */
  lastImage: string | null;
  lastFrameAt: number;
  /** Vision 결과(status)를 확인하는 중인지 / 결과가 나왔는지 */
  polling: boolean;
  resolved: boolean;
}

/** 타이머·세션 상태는 렌더와 상관없이 이 안에서만 바뀐다 */
function createScrollFrames() {
  let ctx: Context | null = null;
  let tick: ReturnType<typeof setTimeout> | null = null;
  let idle: ReturnType<typeof setTimeout> | null = null;
  let stream: Stream | null = null;
  /** 스크롤 캡처가 끝난 주소 */
  let finishedUrl: string | null = null;

  const stop = () => {
    if (tick) clearTimeout(tick);
    if (idle) clearTimeout(idle);
    tick = idle = null;
  };

  const wanted = () => {
    if (Platform.OS === 'web' || !ctx?.url || !ctx.page.pageSessionId || ctx.url === finishedUrl) return false;
    if (!wantsScrollFrames(ctx.page.status, ctx.page.analysis)) return false;
    return !(stream && stream.sessionId === ctx.page.pageSessionId && (stream.ended || stream.next >= MAX_FRAMES));
  };

  /**
   * 프레임은 접수(202)만 되고 Vision 분석은 나중에 끝난다. 마지막 프레임 뒤 20초까지 1초마다 GET /status로 확인한다.
   * success + 성분이 나오면, 성분표가 찍힌 마지막 프레임으로 백엔드 분석을 다시 받아 알레르기 경고·추천을 갱신한다.
   * (백엔드 분석 요청은 성분 목록을 받지 않으므로 이미지를 다시 보내 백엔드가 같은 성분표를 읽게 한다.)
   */
  const watchResult = async (s: Stream, url: string) => {
    if (s.polling || s.resolved) return;
    s.polling = true;
    try {
      while (stream === s && !s.resolved && Date.now() - s.lastFrameAt < STATUS_WAIT_MS) {
        await new Promise((r) => setTimeout(r, STATUS_POLL_MS));
        const v = await getVisionStatus(s.sessionId).catch(() => null);
        if (!v || v.status === 'processing') continue;
        s.resolved = s.ended = true;
        finishedUrl = url;
        if (refreshesResult(v) && s.lastImage && stream === s && ctx?.url === url) ctx.page.reanalyzeWith(s.lastImage);
      }
    } finally {
      s.polling = false;
    }
  };

  const sendFrame = async () => {
    if (!ctx?.url) return;
    const { url, page, captureTarget, getPageScan } = ctx;
    if (!stream || stream.sessionId !== page.pageSessionId) {
      stream = { sessionId: page.pageSessionId, next: 0, inited: false, ended: false, busy: false, failures: 0, lastImage: null, lastFrameAt: 0, polling: false, resolved: false };
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
        s.lastImage = image;
        s.lastFrameAt = Date.now();
        void watchResult(s, url);
      }
      s.failures = 0;
    } catch (e) {
      // 세션이 만료됐으면(404) 다음 차례에 다시 시작한다. Vision이 계속 응답하지 않으면 이 페이지에서는 멈춘다.
      if (e instanceof VisionError && e.status === 404) s.inited = false;
      if (++s.failures >= 3) s.ended = true;
    } finally {
      s.busy = false;
      if (s.ended) finishedUrl = url;
    }
  };

  /** 이탈(다른 페이지로 이동 · 화면 닫기): 진행 중인 Vision 세션에 마지막 프레임(이미지 없음)을 보내 마감한다 */
  const leave = () => {
    const s = stream;
    stream = null;
    if (!s) return;
    s.resolved = true; // 결과 확인·재분석도 멈춘다
    if (!s.inited || s.ended) return;
    s.ended = true;
    void endVisionSession(s.sessionId, s.next).catch(() => undefined);
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
    /**
     * 페이지·분석 세션이 바뀌면 진행 중인 캡처를 멈추고 새로 센다.
     * 같은 주소에서 이미 끝난 스크롤 캡처(성분 찾음·25장·실패)는 다시 시작하지 않는다.
     * (모바일은 재분석마다 세션 id가 바뀌어, 그대로 두면 성분 찾기 → 재분석 → 다시 캡처가 반복될 수 있다)
     */
    reset(url: string | null) {
      stop();
      leave();
      if (url !== finishedUrl) finishedUrl = null;
    },
    /** 화면을 떠날 때 */
    dispose() {
      stop();
      leave();
    },
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
  page: Page,
  captureTarget: RefObject<ComponentRef<typeof View> | null>,
  getPageScan?: (url: string) => PageScan | undefined,
) {
  const [ctl] = useState(createScrollFrames);
  useEffect(() => {
    ctl.update({ url, page, captureTarget, getPageScan });
  });
  useEffect(() => {
    ctl.reset(url);
  }, [ctl, url, page.pageSessionId]);
  useEffect(() => () => ctl.dispose(), [ctl]);
  return { onScroll: ctl.onScroll };
}
