import { recordVisit } from '../../shared/accountData';
import { router } from 'expo-router';
import { useCallback, useEffect, useRef, useState, type ComponentRef } from 'react';
import { BackHandler, KeyboardAvoidingView, Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { setBrowserListener } from '../../browserBus';
import { useSession } from '../../session';
import { safeHttpUrl } from '../../shared/format';
import { uuid } from '../../shared/platform';
import { Floating } from '../../ui/Floating';
import { IconBack, IconClose, IconForward, IconHome, IconLock, IconPlus, IconReload } from '../../ui/icons';
import { ShortcutsHome } from '../../ui/Shortcuts';
import { WebPage, type WebNavState, type WebPageHandle } from '../../ui/WebPage';
import { C } from '../../ui/theme';
import { KEYBOARD_BEHAVIOR } from '../../ui/useKeyboard';
import { usePageAnalysis } from '../../usePageAnalysis';
import type { PageScan } from '../../shared/pageProductScript';

// 앱 안 브라우저(Figma U16~U25). Android 화면 캡처 보안 정책 때문에 다른 앱 위 오버레이 대신
// 앱 안에서 쇼핑몰을 열고, 지금 보이는 탭의 WebView 화면만 캡처해 분석한다.
// 여러 탭을 지원한다: 추천 상품 링크·사이트의 새 창 링크는 새 탭으로 열린다.

const MAX_TABS = 10;

interface BrowserTab {
  id: string;
  /** WebView에 처음 넘긴 주소. null이면 바로가기 홈 */
  source: string | null;
  /** 현재 보고 있는 주소 */
  url: string | null;
  /** 페이지 실제 제목. 모르면 null(도메인으로 대신 표시) */
  title: string | null;
  nav: { back: boolean; forward: boolean; loading: boolean };
}

const newTab = (source: string | null = null): BrowserTab => ({
  id: uuid(),
  source,
  url: source,
  title: null,
  nav: { back: false, forward: false, loading: !!source },
});

function toUrl(input: string): string | null {
  const t = input.trim();
  if (!t) return null;
  if (/^https?:\/\//i.test(t)) return safeHttpUrl(t);
  if (/^[\w-]+(\.[\w-]+)+(\/.*)?$/.test(t)) return safeHttpUrl(`https://${t}`);
  // 주소가 아니면 구글 검색
  return safeHttpUrl(`https://www.google.com/search?q=${encodeURIComponent(t)}`);
}

function hostOf(url: string | null): string {
  if (!url) return '';
  try {
    const u = new URL(url);
    return u.host + u.pathname.replace(/\/$/, '');
  } catch {
    return url;
  }
}

/** 탭 이름: 페이지 실제 제목, 아직 없으면 도메인 */
function tabTitle(t: BrowserTab): string {
  if (!t.url) return '바로가기 홈';
  return t.title?.trim() || hostOf(t.url).split('/')[0];
}

export default function BrowserScreen() {
  const { me, loading } = useSession();
  if (loading) return null;
  return <AccountBrowser key={me?.user_id ?? 'guest'} />;
}
function AccountBrowser() {
  const insets = useSafeAreaInsets();
  const { me } = useSession();
  const [tabs, setTabs] = useState<BrowserTab[]>(() => [newTab()]);
  const [activeId, setActiveId] = useState(() => tabs[0].id);
  const [switcher, setSwitcher] = useState(false);
  const [input, setInput] = useState('');
  const [editing, setEditing] = useState(false);
  const webRefs = useRef<Record<string, WebPageHandle | null>>({});
  const captureTarget = useRef<ComponentRef<typeof View>>(null);

  const active = tabs.find((t) => t.id === activeId) ?? tabs[0];
  // 페이지의 상품 표시 여부 + [임시] 상품명·가격(주소별 최신값)
  const pageScans = useRef(new Map<string, PageScan>());
  // 주소의 #… 과 끝 / 차이는 같은 페이지로 본다(리다이렉트·해시 이동 대비).
  const pageKey = (u: string) => u.split('#')[0].replace(/\/+$/, '');
  const getPageScan = useCallback((u: string) => pageScans.current.get(pageKey(u)), []);
  const page = usePageAnalysis(active.url, active.nav.loading, captureTarget, getPageScan);

  const patchTab = useCallback((id: string, patch: Partial<BrowserTab>) => {
    setTabs((ts) => ts.map((t) => (t.id === id ? { ...t, ...patch } : t)));
  }, []);

  /** 현재 탭에서 주소 열기(주소창·바로가기) */
  const openHere = (target: string) => {
    void recordVisit(me?.user_id, target);
    patchTab(active.id, { source: target, url: target, title: null, nav: { back: false, forward: false, loading: true } });
    setInput(target);
  };

  /** 새 탭으로 열기(추천 상품 링크·사이트 새 창). 탭이 너무 많으면 가장 오래된 탭을 닫는다. */
  const openInNewTab = useCallback((target: string) => {
    const safe = safeHttpUrl(target);
    if (!safe) return;
    void recordVisit(me?.user_id, safe);
    const tab = newTab(safe);
    setTabs((ts) => {
      const next = [...ts, tab];
      return next.length > MAX_TABS ? next.slice(next.length - MAX_TABS) : next;
    });
    setActiveId(tab.id);
    setSwitcher(false);
  }, [me?.user_id]);

  const closeTab = (id: string) => {
    setTabs((ts) => {
      const idx = ts.findIndex((t) => t.id === id);
      const rest = ts.filter((t) => t.id !== id);
      if (rest.length === 0) {
        const fresh = newTab();
        setActiveId(fresh.id);
        return [fresh];
      }
      if (id === activeId) setActiveId(rest[Math.max(0, idx - 1)].id);
      return rest;
    });
    delete webRefs.current[id];
  };

  const addBlankTab = () => {
    const tab = newTab();
    setTabs((ts) => [...ts, tab].slice(-MAX_TABS));
    setActiveId(tab.id);
    setSwitcher(false);
  };

  useEffect(() => {
    setBrowserListener(openInNewTab);
    return () => setBrowserListener(null);
  }, [openInNewTab]);


  // Android 뒤로가기: 탭 목록 닫기 → 웹 히스토리 → 바로가기 홈
  useEffect(() => {
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      if (switcher) {
        setSwitcher(false);
        return true;
      }
      if (active.nav.back) {
        webRefs.current[active.id]?.goBack();
        return true;
      }
      if (active.source) {
        patchTab(active.id, { source: null, url: null, title: null, nav: { back: false, forward: false, loading: false } });
        return true;
      }
      return false;
    });
    return () => sub.remove();
  }, [switcher, active, patchTab]);

  const onNav = (id: string) => (e: WebNavState) => {
    if (!e.loading) void recordVisit(me?.user_id, e.url);
    // 로딩 중에는 제목 자리에 주소가 오기도 해서 무시한다.
    // 제목이 아직 없으면 같은 주소일 때만 이전 제목을 유지하고, 다른 주소로 가면 지운다(도메인으로 대신 표시).
    const real = e.title.trim() && !/^(https?:\/\/|about:)/i.test(e.title) ? e.title.trim() : null;
    setTabs((ts) =>
      ts.map((t) => {
        if (t.id !== id) return t;
        const title = real ?? (t.url === e.url ? t.title : null);
        return { ...t, url: e.url, title, nav: { back: e.canGoBack, forward: e.canGoForward, loading: e.loading } };
      }),
    );
  };

  const goHome = () => patchTab(active.id, { source: null, url: null, title: null, nav: { back: false, forward: false, loading: false } });
  const webRef = webRefs.current[active.id];

  return (
    <KeyboardAvoidingView style={[st.root, { paddingTop: insets.top }]} behavior={KEYBOARD_BEHAVIOR}>
      <View style={st.content}>
        {/* 탭마다 WebView를 유지해 탭을 오가도 페이지·기록이 남는다. 보이는 탭만 캡처 대상 */}
        {tabs.map((t) =>
          t.source ? (
            <View
              key={t.id}
              ref={t.id === active.id ? captureTarget : undefined}
              collapsable={false}
              style={[StyleSheet.absoluteFill, t.id !== active.id && st.hidden]}
            >
              <WebPage
                ref={(h) => {
                  webRefs.current[t.id] = h;
                }}
                uri={t.source}
                onNavigation={onNav(t.id)}
                onPageProduct={(u, scan) => {
                  pageScans.current.set(pageKey(u), scan);
                  if (pageScans.current.size > 50) pageScans.current.delete(pageScans.current.keys().next().value!);
                }}
                onNewWindow={openInNewTab}
              />
            </View>
          ) : null,
        )}
        {!active.source && (
          <View style={StyleSheet.absoluteFill}>
            <ShortcutsHome onOpen={openHere} />
          </View>
        )}
        {active.source && (
          <Floating
            page={page}
            onOpenUrl={openInNewTab}
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
        <Pressable onPress={() => webRef?.goBack()} disabled={!active.nav.back} accessibilityLabel="뒤로" hitSlop={6}>
          <IconBack size={24} color={active.nav.back ? C.text : C.border} />
        </Pressable>
        <Pressable onPress={() => webRef?.goForward()} disabled={!active.nav.forward} accessibilityLabel="앞으로" hitSlop={6}>
          <IconForward size={24} color={active.nav.forward ? C.text : C.border} />
        </Pressable>
        <View style={st.urlBox}>
          {!editing && !!active.url && <IconLock size={14} color={C.sub} />}
          <TextInput
            style={st.urlInput}
            value={editing ? input : hostOf(active.url)}
            placeholder="쇼핑몰 주소나 상품명 입력"
            placeholderTextColor={C.muted}
            onFocus={() => {
              setEditing(true);
              setInput(active.url ?? '');
            }}
            onBlur={() => setEditing(false)}
            onChangeText={setInput}
            onSubmitEditing={() => {
              const target = toUrl(input);
              if (target) openHere(target);
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
        <Pressable onPress={() => setSwitcher(true)} accessibilityLabel={`탭 ${tabs.length}개 보기`} hitSlop={6} style={st.tabCount}>
          <Text style={st.tabCountText}>{tabs.length}</Text>
        </Pressable>
        <Pressable onPress={() => webRef?.reload()} disabled={!active.source} accessibilityLabel="새로고침" hitSlop={6}>
          <IconReload size={22} color={active.source ? C.text : C.border} />
        </Pressable>
      </View>

      <TabSwitcher
        visible={switcher}
        tabs={tabs}
        activeId={active.id}
        onSelect={(id) => {
          setActiveId(id);
          setSwitcher(false);
        }}
        onClose={closeTab}
        onAdd={addBlankTab}
        onDismiss={() => setSwitcher(false)}
      />
    </KeyboardAvoidingView>
  );
}

function TabSwitcher({
  visible,
  tabs,
  activeId,
  onSelect,
  onClose,
  onAdd,
  onDismiss,
}: {
  visible: boolean;
  tabs: BrowserTab[];
  activeId: string;
  onSelect: (id: string) => void;
  onClose: (id: string) => void;
  onAdd: () => void;
  onDismiss: () => void;
}) {
  const insets = useSafeAreaInsets();
  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onDismiss}>
      <View style={[st.switcher, { paddingTop: insets.top, paddingBottom: insets.bottom }]}>
        <View style={st.switcherHead}>
          <Text style={st.switcherTitle}>탭 {tabs.length}개</Text>
          <Pressable onPress={onDismiss} accessibilityRole="button" hitSlop={8}>
            <Text style={{ color: C.primary, fontWeight: '700', fontSize: 15 }}>완료</Text>
          </Pressable>
        </View>
        <ScrollView contentContainerStyle={{ padding: 16, gap: 10 }}>
          {tabs.map((t) => {
            const on = t.id === activeId;
            return (
              <Pressable
                key={t.id}
                style={[st.tabCard, on && st.tabCardOn]}
                onPress={() => onSelect(t.id)}
                accessibilityRole="button"
                accessibilityState={{ selected: on }}
                accessibilityLabel={t.url ? `${tabTitle(t)} 탭` : '바로가기 홈 탭'}
              >
                <View style={{ flex: 1 }}>
                  <Text style={st.tabCardTitle} numberOfLines={1}>
                    {tabTitle(t)}
                  </Text>
                  <Text style={st.tabCardSub} numberOfLines={1}>
                    {t.url ?? '쇼핑몰 바로가기'}
                  </Text>
                </View>
                <Pressable onPress={() => onClose(t.id)} hitSlop={10} accessibilityLabel="탭 닫기">
                  <IconClose size={18} color={C.sub} />
                </Pressable>
              </Pressable>
            );
          })}
        </ScrollView>
        <Pressable style={st.addTab} onPress={onAdd} accessibilityRole="button" disabled={tabs.length >= MAX_TABS}>
          <IconPlus size={20} color={tabs.length >= MAX_TABS ? C.muted : C.primary} />
          <Text style={{ color: tabs.length >= MAX_TABS ? C.muted : C.primary, fontWeight: '700', fontSize: 15 }}>
            {tabs.length >= MAX_TABS ? `탭은 최대 ${MAX_TABS}개까지 열 수 있어요` : '새 탭'}
          </Text>
        </Pressable>
      </View>
    </Modal>
  );
}

const st = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  content: { flex: 1 },
  hidden: { opacity: 0, zIndex: -1, pointerEvents: 'none' },
  bar: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 14, paddingVertical: 10, borderTopWidth: 1, borderTopColor: C.border, backgroundColor: C.surface },
  urlBox: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 6, height: 40, borderRadius: 20, backgroundColor: C.surfaceMuted, paddingHorizontal: 14 },
  urlInput: { flex: 1, fontSize: 14, color: C.text, padding: 0 },
  tabCount: { width: 24, height: 24, borderRadius: 6, borderWidth: 2, borderColor: C.text, alignItems: 'center', justifyContent: 'center' },
  tabCountText: { fontSize: 12, fontWeight: '800', color: C.text },
  switcher: { flex: 1, backgroundColor: C.surfaceMuted },
  switcherHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 20, height: 56, backgroundColor: C.surface, borderBottomWidth: 1, borderBottomColor: C.border },
  switcherTitle: { fontSize: 17, fontWeight: '800', color: C.text },
  tabCard: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: C.surface, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border },
  tabCardOn: { borderColor: C.primary, borderWidth: 2 },
  tabCardTitle: { fontSize: 15, fontWeight: '700', color: C.text },
  tabCardSub: { fontSize: 12, color: C.sub, marginTop: 2 },
  addTab: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, height: 56, backgroundColor: C.surface, borderTopWidth: 1, borderTopColor: C.border },
});
