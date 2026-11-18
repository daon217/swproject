import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { sendMessage, type Message, type TabState } from '../shared/messages';
import baseCss from '../shared/ui/styles.css?inline';
import floatingCss from './floating.css?inline';
import { Floating } from './Floating';
import { scanPage } from '../shared/pageProduct';

// 백그라운드가 캡처 전후로 이 페이지의 상품 표시 여부와 [임시] 상품명·가격을 물어본다.
chrome.runtime.onMessage.addListener((msg: Message, _sender, sendResponse) => {
  if (msg.type !== 'extractProduct') return false;
  try {
    sendResponse(scanPage(document));
  } catch {
    sendResponse(null);
  }
  return false;
});

// 쇼핑몰 페이지에 꿀픽 플로팅을 주입한다. 사이트 CSS와 섞이지 않도록 Shadow DOM을 쓴다.

function ContentApp() {
  const [state, setState] = useState<TabState | null>(null);

  useEffect(() => {
    void sendMessage<TabState | null>({ type: 'getTabState' }).then((s) => setState(s ?? null));
    const onMsg = (msg: Message) => {
      // 현재 문서 URL과 다른 결과는 표시하지 않는다(이전 페이지 결과 노출 방지).
      if (msg.type === 'tabState' && msg.state.url === location.href) setState(msg.state);
      else if (msg.type === 'tabState') setState(null);
    };
    chrome.runtime.onMessage.addListener(onMsg);
    return () => chrome.runtime.onMessage.removeListener(onMsg);
  }, []);

  return (
    <div className="kp-root fl-root">
      {/* 사이드 패널은 사용자 클릭 직후에만 열 수 있어 클릭 핸들러에서 바로 메시지를 보낸다 */}
      <Floating state={state} onOpenPanel={(route) => void sendMessage({ type: 'openSidePanel', route })} />
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
