import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { sendMessage, type Message, type TabState } from '../shared/messages';
import baseCss from '../shared/ui/styles.css?inline';
import floatingCss from './floating.css?inline';
import { Floating } from './Floating';
import { scanPage } from '../shared/pageProduct';
import { dlog } from '../shared/debug';
import { useDragPosition } from './drag';

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
      if (msg.type === 'tabState' && msg.state.url === location.href) {
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
