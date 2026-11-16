import { router } from 'expo-router';
import { useEffect, useRef, useState, type ComponentRef } from 'react';
import { BackHandler, Pressable, StyleSheet, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { setBrowserListener } from '../../browserBus';
import { useSession } from '../../session';
import { safeHttpUrl } from '../../shared/format';
import { Floating } from '../../ui/Floating';
import { IconBack, IconForward, IconHome, IconLock, IconReload } from '../../ui/icons';
import { ShortcutsHome } from '../../ui/Shortcuts';
import { WebPage, type WebNavState, type WebPageHandle } from '../../ui/WebPage';
import { C } from '../../ui/theme';
import { usePageAnalysis } from '../../usePageAnalysis';

// 앱 안 브라우저(Figma U16~U25). Android 화면 캡처 보안 정책 때문에 다른 앱 위 오버레이 대신
// 앱 안에서 쇼핑몰을 열고, 이 WebView 화면만 캡처해 분석한다.

function toUrl(input: string): string | null {
  const t = input.trim();
  if (!t) return null;
  if (/^https?:\/\//i.test(t)) return safeHttpUrl(t);
  if (/^[\w-]+(\.[\w-]+)+(\/.*)?$/.test(t)) return safeHttpUrl(`https://${t}`);
  return safeHttpUrl(`https://search.shopping.naver.com/search/all?query=${encodeURIComponent(t)}`);
}

export default function BrowserScreen() {
  const insets = useSafeAreaInsets();
  const { me } = useSession();
  const webRef = useRef<WebPageHandle>(null);
  const captureTarget = useRef<ComponentRef<typeof View>>(null);
  const [url, setUrl] = useState<string | null>(null); // null이면 바로가기 홈
  const [source, setSource] = useState<string | null>(null);
  const [input, setInput] = useState('');
  const [editing, setEditing] = useState(false);
  const [nav, setNav] = useState({ back: false, forward: false, loading: false });

  const page = usePageAnalysis(url, nav.loading, captureTarget);

  const open = (target: string) => {
    setSource(target);
    setUrl(target);
    setInput(target);
  };

  useEffect(() => {
    setBrowserListener(open);
    return () => setBrowserListener(null);
  }, []);

  // Android 뒤로가기: 웹 히스토리 → 바로가기 홈
  useEffect(() => {
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      if (nav.back) {
        webRef.current?.goBack();
        return true;
      }
      if (url) {
        setUrl(null);
        setSource(null);
        return true;
      }
      return false;
    });
    return () => sub.remove();
  }, [nav.back, url]);

  const onNav = (e: WebNavState) => {
    setNav({ back: e.canGoBack, forward: e.canGoForward, loading: e.loading });
    if (e.url !== url) {
      setUrl(e.url);
      if (!editing) setInput(e.url);
    }
  };

  const goHome = () => {
    setUrl(null);
    setSource(null);
    setInput('');
  };

  const display = (() => {
    if (editing) return input;
    try {
      return url ? new URL(url).host + new URL(url).pathname.replace(/\/$/, '') : '';
    } catch {
      return url ?? '';
    }
  })();

  return (
    <View style={[st.root, { paddingTop: insets.top }]}>
      <View style={st.content}>
        {source ? (
          <View ref={captureTarget} collapsable={false} style={{ flex: 1 }}>
            <WebPage ref={webRef} uri={source} onNavigation={onNav} />
          </View>
        ) : (
          <ShortcutsHome onOpen={open} />
        )}
        {source && (
          <Floating
            page={page}
            onOpenUrl={open}
            onRetry={page.retry}
            onPremium={() => router.push(me ? '/premium' : '/login')}
            onFilter={() => router.push('/filter')}
          />
        )}
      </View>

      <View style={st.bar}>
        <Pressable onPress={goHome} accessibilityLabel="바로가기 홈" hitSlop={6}>
          <IconHome size={24} color={C.text} />
        </Pressable>
        <Pressable onPress={() => webRef.current?.goBack()} disabled={!nav.back} accessibilityLabel="뒤로" hitSlop={6}>
          <IconBack size={24} color={nav.back ? C.text : C.border} />
        </Pressable>
        <Pressable onPress={() => webRef.current?.goForward()} disabled={!nav.forward} accessibilityLabel="앞으로" hitSlop={6}>
          <IconForward size={24} color={nav.forward ? C.text : C.border} />
        </Pressable>
        <View style={st.urlBox}>
          {!editing && !!url && <IconLock size={14} color={C.sub} />}
          <TextInput
            style={st.urlInput}
            value={display}
            placeholder="쇼핑몰 주소나 상품명 입력"
            placeholderTextColor={C.muted}
            onFocus={() => {
              setEditing(true);
              setInput(url ?? '');
            }}
            onBlur={() => setEditing(false)}
            onChangeText={setInput}
            onSubmitEditing={() => {
              const target = toUrl(input);
              if (target) open(target);
              setEditing(false);
            }}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
            returnKeyType="go"
            selectTextOnFocus
            accessibilityLabel="주소"
            numberOfLines={1}
          />
        </View>
        <Pressable onPress={() => (source ? webRef.current?.reload() : undefined)} accessibilityLabel="새로고침" hitSlop={6}>
          <IconReload size={22} color={source ? C.text : C.border} />
        </Pressable>
      </View>
    </View>
  );
}

const st = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  content: { flex: 1 },
  bar: { flexDirection: 'row', alignItems: 'center', gap: 14, paddingHorizontal: 14, paddingVertical: 10, borderTopWidth: 1, borderTopColor: C.border, backgroundColor: C.surface },
  urlBox: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 6, height: 40, borderRadius: 20, backgroundColor: C.surfaceMuted, paddingHorizontal: 14 },
  urlInput: { flex: 1, fontSize: 14, color: C.text, padding: 0 },
});
