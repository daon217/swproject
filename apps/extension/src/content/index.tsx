import { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { sendMessage, type Message, type TabState } from '../shared/messages';
import baseCss from '../shared/ui/styles.css?inline';
import floatingCss from './floating.css?inline';
import { Floating } from './Floating';
import { scanPage } from '../shared/pageProduct';
import { sameUrl } from '../shared/pageFilter';
import { dlog } from '../shared/debug';
import { useDragPosition } from './drag';
import { FRAME_INTERVAL_MS, SCROLL_STOP_MS, wantsScrollFrames } from '../shared/api/vision';

dlog('content', 'content script 주입됨', { url: location.href });

// 백그라운드가 캡처 전후로 이 페이지의 상품 표시 여부와 [임시] 상품명·가격을 물어본다.
chrome.runtime.onMessage.addListener((msg: Message, _sender, sendResponse) => {
  if (msg.type !== 'extractProduct') return false;
  try {
    const scan = scanPage(document);
    dlog('content', '백그라운드 요청 extractProduct → 페이지 스캔', { signal: scan?.signal, product: scan?.product });
    sendResponse(scan);
  } catch (e) {
    dlog('content', '페이지 스캔 실패', e);
    sendResponse(null);
  }
  return false;
});

// 쇼핑몰 페이지에 꿀픽 플로팅을 주입한다. 사이트 CSS와 섞이지 않도록 Shadow DOM을 쓴다.

function ContentApp() {
  const [state, setState] = useState<TabState | null>(null);

  const [panelOpen, setPanelOpen] = useState(false);
  const [openError, setOpenError] = useState(false);
  const drag = useDragPosition();

  useEffect(() => {
    void sendMessage<TabState | null>({ type: 'getTabState' }).then((s) => setState(s ?? null));
    let visibilityChanged = false;
    void sendMessage<boolean>({ type: 'getPanelVisibility' }).then(open => { if (!visibilityChanged) setPanelOpen(!!open); });
    const onMsg = (msg: Message) => {
      if (msg.type === 'panelVisibility') { visibilityChanged = true; setPanelOpen(msg.open); return; }
      // 현재 문서 URL과 다른 결과는 표시하지 않는다(이전 페이지 결과 노출 방지).
      if (msg.type === 'tabState' && sameUrl(msg.state.url, location.href)) {
        dlog('content', `플로팅 상태 갱신 → ${msg.state.status}`, { page_revision: msg.state.page_revision, error: msg.state.error });
        setState(msg.state);
      } else if (msg.type === 'tabState') {
        dlog('content', '다른 URL의 결과라 플로팅 숨김', { got: msg.state.url, here: location.href });
        setState(null);
      }
    };
    chrome.runtime.onMessage.addListener(onMsg);
    return () => chrome.runtime.onMessage.removeListener(onMsg);
  }, []);

  // 성분표를 아직 못 찾은 식품 페이지(ingredient_status === 'not_found')에서는
  // 스크롤하는 동안 0.7초마다 화면 캡처를 요청한다(백그라운드가 캡처해 Vision AI로 바로 보낸다).
  // 스크롤이 멈추면(250ms 동안 스크롤 이벤트 없음) 바로 타이머를 끄고 더 보내지 않는다.
  // 백그라운드가 '이 페이지는 끝(25장·Vision 종료)'이라고 답하면 같은 주소에서는 더 요청하지 않는다.
  const framesDone = useRef<string | null>(null);
  useEffect(() => {
    let tick: ReturnType<typeof setTimeout> | null = null;
    let idle: ReturnType<typeof setTimeout> | null = null;
    const wanted = () =>
      !!state && sameUrl(state.url, location.href) && wantsScrollFrames(state) && framesDone.current !== location.href;
    const stop = () => {
      if (tick) clearTimeout(tick);
      if (idle) clearTimeout(idle);
      tick = idle = null;
    };
    const next = () => {
      tick = setTimeout(() => {
        if (!wanted()) return stop();
        const url = location.href;
        void sendMessage<{ more: boolean }>({ type: 'scrollFrame' }).then((r) => {
          if (r && !r.more) {
            framesDone.current = url;
            dlog('content', '스크롤 캡처 종료(25장 또는 Vision 세션 끝)');
          }
        });
        next();
      }, FRAME_INTERVAL_MS);
    };
    const onScroll = () => {
      if (!wanted()) return stop();
      if (idle) clearTimeout(idle);
      idle = setTimeout(stop, SCROLL_STOP_MS); // 멈춘 순간 캡처 중단
      if (!tick) next();
    };

    window.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', onScroll);
      stop();
    };
  }, [state]);

  return (
    // 카드를 끌어서 옮길 수 있다(drag.ts). 짧게 누르면 평소처럼 사이드 패널이 열린다.
    <div className="kp-root fl-root" ref={drag.ref} style={drag.style} onPointerDown={drag.onPointerDown} onClickCapture={drag.onClickCapture}>
      {/* 사이드 패널은 사용자 클릭 직후에만 열 수 있어 클릭 핸들러에서 바로 메시지를 보낸다 */}
      <Floating
        state={state}
        panelOpen={panelOpen}
        onOpenPanel={(route) => {
          setOpenError(false);
          void sendMessage<{ ok: boolean }>({ type: 'openSidePanel', route }).then(result => {
            if (result?.ok) setPanelOpen(true);
            else setOpenError(true);
          });
        }}
        onRetry={() => void sendMessage({ type: 'retry' })}
      />
      {openError && !panelOpen && <p role="alert">사이드바를 열지 못했어요. 확장 아이콘을 눌러 주세요.</p>}
    </div>
  );
}

function mount() {
  if (window.top !== window.self) return; // iframe 안에는 띄우지 않는다
  if (document.getElementById('kkulpick-floating-host')) return;
  const host = document.createElement('div');
  host.id = 'kkulpick-floating-host';
  const shadow = host.attachShadow({ mode: 'open' });
  const style = document.createElement('style');
  style.textContent = baseCss + floatingCss;
  const container = document.createElement('div');
  shadow.append(style, container);
  document.documentElement.appendChild(host);
  createRoot(container).render(<ContentApp />);
}

mount();
