import { useImperativeHandle, useRef, type ComponentType, type Ref } from 'react';
import { WebView, type WebViewNavigation, type WebViewProps } from 'react-native-webview';

// 앱 안 브라우저 화면(네이티브). 웹 미리보기는 WebPage.web.tsx(iframe)를 쓴다.

export interface WebPageHandle {
  goBack: () => void;
  goForward: () => void;
  reload: () => void;
}

export interface WebNavState {
  url: string;
  canGoBack: boolean;
  canGoForward: boolean;
  loading: boolean;
}

// react-native-webview 클래스 타입이 React 19 타입과 맞지 않아 컴포넌트 타입만 좁혀 쓴다.
const WebViewC = WebView as unknown as ComponentType<WebViewProps & { ref?: Ref<WebView> }>;

export function WebPage({ uri, onNavigation, ref }: { uri: string; onNavigation: (s: WebNavState) => void; ref?: Ref<WebPageHandle> }) {
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
      onNavigationStateChange={(e: WebViewNavigation) => onNavigation({ url: e.url, canGoBack: e.canGoBack, canGoForward: e.canGoForward, loading: e.loading })}
      onShouldStartLoadWithRequest={(r: { url: string }) => /^(https?|about|data|blob):/i.test(r.url)}
      setSupportMultipleWindows={false}
      allowsBackForwardNavigationGestures
      style={{ flex: 1 }}
    />
  );
}
