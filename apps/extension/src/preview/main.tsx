import { StrictMode, useEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import '../shared/ui/styles.css';
import '../sidepanel/sidepanel.css';
import baseCss from '../shared/ui/styles.css?inline';
import floatingCss from '../content/floating.css?inline';
import { Floating } from '../content/Floating';
import { App } from '../sidepanel/App';
import { useActiveTabState } from '../sidepanel/useActiveTabState';
import { setItem, KEYS } from '../shared/storage';

// 개발용 미리보기(확장 설치 없이 화면 확인). 왼쪽: 쇼핑몰 페이지 + 인페이지 플로팅, 오른쪽: 사이드 패널.
// ?url= 로 분석할 페이지 주소를 바꾼다. 예) ?url=https://smartstore.naver.com/snackmarket/products/4021

function FloatingInShadow() {
  const hostRef = useRef<HTMLDivElement>(null);
  const rootRef = useRef<ReturnType<typeof createRoot> | null>(null);
  const { state } = useActiveTabState();

  useEffect(() => {
    const host = hostRef.current!;
    if (!rootRef.current) {
      const shadow = host.shadowRoot ?? host.attachShadow({ mode: 'open' });
      const style = document.createElement('style');
      style.textContent = baseCss + floatingCss.replace('position: fixed', 'position: absolute');
      const c = document.createElement('div');
      shadow.append(style, c);
      rootRef.current = createRoot(c);
    }
    rootRef.current.render(
      <div className="kp-root fl-root">
        <Floating state={state} onOpenPanel={(route) => void setItem(KEYS.pendingRoute, { route, at: Date.now() })} />
      </div>,
    );
  }, [state]);

  return <div ref={hostRef} />;
}

function Preview() {
  const url = new URLSearchParams(location.search).get('url') ?? 'https://brand.naver.com/epson/products/1120';
  return (
    <div style={{ display: 'flex', height: '100vh', fontFamily: 'system-ui', background: '#e9edf3' }}>
      <div style={{ flex: 1, position: 'relative', background: '#fff', overflow: 'hidden' }}>
        <div style={{ padding: '10px 16px', background: '#f2f4f8', fontSize: 13, color: '#555' }}>{url}</div>
        <div style={{ padding: 32, color: '#1a2233' }}>
          <h2 style={{ marginTop: 0 }}>쇼핑몰 상품 페이지 (미리보기)</h2>
          <p>주소에 ?url= 을 바꿔 상품/식품/일반 페이지를 확인하세요.</p>
          <p>
            <a href="?url=https://brand.naver.com/epson/products/1120">프린터 상품</a> ·{' '}
            <a href="?url=https://smartstore.naver.com/snackmarket/products/4021">식품(땅콩)</a> ·{' '}
            <a href="?url=https://www.naver.com">상품 아님</a>
          </p>
        </div>
        <FloatingInShadow />
      </div>
      <div style={{ width: 400, borderLeft: '1px solid #d5dae3', background: '#fff' }}>
        <App />
      </div>
    </div>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Preview />
  </StrictMode>,
);
