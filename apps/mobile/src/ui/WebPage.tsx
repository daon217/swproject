import { useImperativeHandle, useRef, type ComponentType, type Ref } from 'react';
import { WebView, type WebViewMessageEvent, type WebViewNavigation, type WebViewProps } from 'react-native-webview';
import { PAGE_PRODUCT_SCRIPT, type PageProductMessage, type PageScan } from '../shared/pageProductScript';

// 앱 안 브라우저 화면(네이티브). 웹 미리보기는 WebPage.web.tsx(iframe)를 쓴다.

export interface WebPageHandle {
  goBack: () => void;
  goForward: () => void;
  reload: () => void;
}

export interface WebNavState {
  url: string;
  /** 페이지의 실제 제목(<title>). 아직 모르면 빈 문자열 */
  title: string;
  canGoBack: boolean;
  canGoForward: boolean;
  loading: boolean;
}

// react-native-webview 클래스 타입이 React 19 타입과 맞지 않아 컴포넌트 타입만 좁혀 쓴다.
const WebViewC = WebView as unknown as ComponentType<WebViewProps & { ref?: Ref<WebView> }>;

export interface WebPageProps {
  uri: string;
  onNavigation: (s: WebNavState) => void;
  /** 사이트가 새 창(target=_blank, window.open)으로 여는 링크 → 앱 안 새 탭 */
  onNewWindow?: (url: string) => void;
  /** 페이지의 상품 표시 여부 + [임시] 상품명·가격(주입 스크립트가 보냄) */
  onPageProduct?: (url: string, scan: PageScan) => void;
  ref?: Ref<WebPageHandle>;
}

export function WebPage({ uri, onNavigation, onNewWindow, onPageProduct, ref }: WebPageProps) {
  const web = useRef<WebView>(null);
  useImperativeHandle(ref, () => ({
    goBack: () => web.current?.goBack(),
    goForward: () => web.current?.goForward(),
    reload: () => web.current?.reload(),
  }));
  return (
    <WebViewC
      ref={web}
      source={{ uri }}
      onNavigationStateChange={(e: WebViewNavigation) => onNavigation({ url: e.url, title: e.title ?? '', canGoBack: e.canGoBack, canGoForward: e.canGoForward, loading: e.loading })}
      onShouldStartLoadWithRequest={(r: { url: string }) => /^(https?|about|data|blob):/i.test(r.url)}
      setSupportMultipleWindows={!!onNewWindow}
      onOpenWindow={(e: { nativeEvent: { targetUrl: string } }) => onNewWindow?.(e.nativeEvent.targetUrl)}
      injectedJavaScript={PAGE_PRODUCT_SCRIPT}
      onMessage={(e: WebViewMessageEvent) => {
        try {
          const msg = JSON.parse(e.nativeEvent.data) as PageProductMessage;
          if (msg?.type === 'kp-product') onPageProduct?.(msg.url, { signal: !!msg.signal, product: msg.product ?? null, domain: msg.domain === 'food' ? 'food' : null });
        } catch {
          /* 페이지가 보낸 다른 메시지는 무시 */
        }
      }}
      allowsBackForwardNavigationGestures
      style={{ flex: 1 }}
    />
  );
}
