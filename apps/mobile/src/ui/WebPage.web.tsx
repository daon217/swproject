import { useEffect, useImperativeHandle, useRef, useState } from 'react';
import { Text, View } from 'react-native';
import { C } from './theme';
import type { WebPageProps } from './WebPage';

export type { WebNavState, WebPageHandle } from './WebPage';

// 웹 미리보기 전용(개발 확인용). 네이티브 WebView 대신 iframe으로 띄운다.
// 다른 출처 페이지 안의 이동은 알 수 없어서, 주소창·바로가기로 연 주소만 기록·분석한다.
// 많은 쇼핑몰이 iframe 표시를 막으므로 화면이 비어 보일 수 있다(분석은 주소 기준 목업으로 동작).

// iframe 안 다른 출처 페이지의 새 창 링크는 가로챌 수 없어 onNewWindow는 웹에서 쓰지 않는다.
export function WebPage({ uri, onNavigation, ref }: WebPageProps) {
  const [nav, setNav] = useState({ history: [uri], index: 0 });
  const { history, index } = nav;
  const [loading, setLoading] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);
  const cb = useRef(onNavigation);
  cb.current = onNavigation;

  // 새 주소가 열리면 기록에 추가
  useEffect(() => {
    setNav((n) => (n.history[n.index] === uri ? n : { history: [...n.history.slice(0, n.index + 1), uri], index: n.index + 1 }));
    setLoading(true);
  }, [uri]);

  const current = history[index] ?? uri;

  // iframe이 막혀 load 이벤트가 늦거나 안 오면 3초 뒤 로딩 끝으로 본다.
  useEffect(() => {
    const t = setTimeout(() => setLoading(false), 3000);
    return () => clearTimeout(t);
  }, [current, reloadKey]);

  useEffect(() => {
    cb.current({ url: current, title: '', canGoBack: index > 0, canGoForward: index < history.length - 1, loading });
  }, [current, index, history.length, loading]);

  useImperativeHandle(ref, () => ({
    goBack: () => {
      if (index > 0) {
        setNav({ history, index: index - 1 });
        setLoading(true);
      }
    },
    goForward: () => {
      if (index < history.length - 1) {
        setNav({ history, index: index + 1 });
        setLoading(true);
      }
    },
    reload: () => {
      setReloadKey((k) => k + 1);
      setLoading(true);
    },
  }));

  return (
    <View style={{ flex: 1 }}>
      <View style={{ backgroundColor: C.primarySoft, paddingVertical: 6, paddingHorizontal: 12 }}>
        <Text style={{ fontSize: 11, color: C.sub }}>웹 미리보기 · 쇼핑몰이 iframe 표시를 막으면 빈 화면일 수 있어요</Text>
      </View>
      <iframe
        key={`${current}#${reloadKey}`}
        src={current}
        title="쇼핑몰 페이지"
        onLoad={() => setLoading(false)}
        style={{ flex: 1, border: 0, width: '100%', height: '100%', background: '#fff' }}
        sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
      />
    </View>
  );
}
