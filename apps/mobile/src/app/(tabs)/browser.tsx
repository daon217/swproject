import { clearVisits, loadBrowserSession, loadSearchEngineIndex, loadVisits, recordVisit, removeVisits, saveBrowserSession, saveSearchEngineIndex, SEARCH_ENGINES, type Visit } from '../../shared/accountData';
import { router } from 'expo-router';
import { useCallback, useEffect, useRef, useState, type ComponentRef } from 'react';
import { BackHandler, KeyboardAvoidingView, Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { setBrowserListener } from '../../browserBus';
import { useSession } from '../../session';
import { safeHttpUrl } from '../../shared/format';
import { uuid } from '../../shared/platform';
import { loadShortcuts, saveShortcuts, type Shortcut } from '../../shared/shortcuts';
import { Floating } from '../../ui/Floating';
import { IconBack, IconCheck, IconClose, IconForward, IconHome, IconLock, IconMoreVert, IconPlus, IconReload } from '../../ui/icons';
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

function toUrl(input: string, queryUrl = SEARCH_ENGINES[0].queryUrl): string | null {
  const t = input.trim();
  if (!t) return null;
  if (/^https?:\/\//i.test(t)) return safeHttpUrl(t);
  if (/^[\w-]+(\.[\w-]+)+(\/.*)?$/.test(t)) return safeHttpUrl(`https://${t}`);
  // 주소가 아니면 현재 선택된 검색엔진(Naver / Google / Daum)으로 검색
  return safeHttpUrl(`${queryUrl}${encodeURIComponent(t)}`);
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
  const [sessionLoaded, setSessionLoaded] = useState(false);
  const [switcher, setSwitcher] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuTab, setMenuTab] = useState<'bookmarks' | 'history'>('bookmarks');
  const [engineIndex, setEngineIndex] = useState(0);
  const [input, setInput] = useState('');
  const [editing, setEditing] = useState(false);
  const webRefs = useRef<Record<string, WebPageHandle | null>>({});
  const captureTarget = useRef<ComponentRef<typeof View>>(null);

  const currentEngine = SEARCH_ENGINES[engineIndex] ?? SEARCH_ENGINES[0];

  const cycleEngine = () => {
    const nextIdx = (engineIndex + 1) % SEARCH_ENGINES.length;
    setEngineIndex(nextIdx);
    void saveSearchEngineIndex(nextIdx, me?.user_id);
  };

  // 앱을 껐다 켜도 마지막으로 보던 탭과 페이지 및 선택된 검색엔진이 이어서 뜨도록 복원
  useEffect(() => {
    let alive = true;
    void loadSearchEngineIndex(me?.user_id).then((savedIdx) => {
      if (alive) setEngineIndex(savedIdx);
    });
    void loadBrowserSession(me?.user_id).then((saved) => {
      if (!alive) return;
      if (saved && saved.tabs.length > 0) {
        const restored: BrowserTab[] = saved.tabs.map((t) => {
          const targetUrl = t.url || t.source || null;
          return {
            id: t.id || uuid(),
            source: targetUrl,
            url: targetUrl,
            title: t.title ?? null,
            nav: { back: false, forward: false, loading: !!targetUrl },
          };
        });
        setTabs(restored);
        const validActive = restored.some((t) => t.id === saved.activeId)
          ? saved.activeId
          : restored[0].id;
        setActiveId(validActive);
      }
      setSessionLoaded(true);
    });
    return () => {
      alive = false;
    };
  }, [me?.user_id]);

  // 탭 상태나 활성 탭이 바뀔 때마다 기기 스토리지에 영구 저장
  useEffect(() => {
    if (!sessionLoaded) return;
    void saveBrowserSession(
      {
        tabs: tabs.map((t) => ({
          id: t.id,
          source: t.url ?? t.source,
          url: t.url,
          title: t.title,
        })),
        activeId,
      },
      me?.user_id,
    );
  }, [tabs, activeId, sessionLoaded, me?.user_id]);

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

  // Android 뒤로가기: 메뉴 시트 닫기 → 탭 목록 닫기 → 웹 히스토리 → 바로가기 홈
  useEffect(() => {
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      if (menuOpen) {
        setMenuOpen(false);
        return true;
      }
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
  }, [menuOpen, switcher, active, patchTab]);

  const onNav = (id: string) => (e: WebNavState) => {
    const real = e.title.trim() && !/^(https?:\/\/|about:)/i.test(e.title) ? e.title.trim() : null;
    if (!e.loading) void recordVisit(me?.user_id, e.url, real);
    setTabs((ts) =>
      ts.map((t) => {
        if (t.id !== id) return t;
        const title = real ?? (t.url === e.url ? t.title : null);
        return { ...t, url: e.url, title, nav: { back: e.canGoBack, forward: e.canGoForward, loading: e.loading } };
      }),
    );
  };

  const goHome = () => {
    setSwitcher(false);
    patchTab(active.id, { source: null, url: null, title: null, nav: { back: false, forward: false, loading: false } });
  };
  const webRef = webRefs.current[active.id];
  const canGoBack = active.nav.back || !!active.source;

  return (
    <KeyboardAvoidingView style={[st.root, { paddingTop: insets.top }]} behavior={KEYBOARD_BEHAVIOR}>
      {/* 상단 크롬 모바일 스타일 컴팩트 툴바: [뒤로] [앞으로] [홈] (알약형 주소창 + 새로고침) [탭 수] [⋮ 메뉴] */}
      <View style={st.topBar}>
        <Pressable
          style={st.topIconBtn}
          onPress={() => {
            if (active.nav.back) webRef?.goBack();
            else if (active.source) goHome();
          }}
          disabled={!canGoBack}
          accessibilityLabel="뒤로"
          hitSlop={4}
        >
          <IconBack size={18} color={canGoBack ? C.sub : C.border} />
        </Pressable>

        <Pressable
          style={st.topIconBtn}
          onPress={() => webRef?.goForward()}
          disabled={!active.nav.forward}
          accessibilityLabel="앞으로"
          hitSlop={4}
        >
          <IconForward size={18} color={active.nav.forward ? C.sub : C.border} />
        </Pressable>

        <Pressable
          style={st.topIconBtn}
          onPress={goHome}
          accessibilityLabel="바로가기 홈"
          hitSlop={4}
        >
          <IconHome size={18} color={C.sub} />
        </Pressable>

        <View style={st.urlBox}>
          <Pressable
            onPress={cycleEngine}
            hitSlop={4}
            style={st.enginePill}
            accessibilityRole="button"
            accessibilityLabel={`검색엔진 변경 (현재 ${currentEngine.label})`}
          >
            <Text style={st.enginePillText}>{currentEngine.label}</Text>
          </Pressable>
          {!editing && !!active.url && <IconLock size={13} color={C.sub} />}
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
              const target = toUrl(input, currentEngine.queryUrl);
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
          {editing && input.length > 0 && (
            <Pressable onPress={() => setInput('')} hitSlop={6} accessibilityLabel="입력 지우기">
              <IconClose size={14} color={C.sub} />
            </Pressable>
          )}
          {!editing && !!active.source && (
            <Pressable onPress={() => webRef?.reload()} hitSlop={6} accessibilityLabel="새로고침">
              <IconReload size={15} color={C.sub} />
            </Pressable>
          )}
        </View>

        <Pressable
          onPress={() => setSwitcher((v) => !v)}
          accessibilityLabel={`탭 ${tabs.length}개 보기`}
          hitSlop={4}
          style={st.topIconBtn}
        >
          <View style={[st.tabCount, switcher && { borderColor: C.primary }]}>
            <Text style={[st.tabCountText, switcher && { color: C.primary }]}>{tabs.length}</Text>
          </View>
        </Pressable>

        <Pressable
          onPress={() => setMenuOpen(true)}
          accessibilityLabel="브라우저 메뉴 (북마크 및 방문 기록)"
          hitSlop={4}
          style={st.topIconBtn}
        >
          <IconMoreVert size={18} color={C.sub} />
        </Pressable>
      </View>

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
            <ShortcutsHome
              onOpen={openHere}
              engineLabel={currentEngine.label}
              onEngineToggle={cycleEngine}
              onSearchSubmit={(q) => {
                const target = toUrl(q, currentEngine.queryUrl);
                if (target) openHere(target);
              }}
            />
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

      <BrowserMenuSheet
        visible={menuOpen}
        selectedTab={menuTab}
        onSelectTab={setMenuTab}
        userId={me?.user_id}
        onNavigate={(url) => {
          setMenuOpen(false);
          setSwitcher(false);
          openHere(url);
        }}
        onDismiss={() => setMenuOpen(false)}
      />
    </KeyboardAvoidingView>
  );
}

function BrowserMenuSheet({
  visible,
  selectedTab,
  onSelectTab,
  userId,
  onNavigate,
  onDismiss,
}: {
  visible: boolean;
  selectedTab: 'bookmarks' | 'history';
  onSelectTab: (tab: 'bookmarks' | 'history') => void;
  userId?: string;
  onNavigate: (url: string) => void;
  onDismiss: () => void;
}) {
  const insets = useSafeAreaInsets();
  const [bookmarks, setBookmarks] = useState<Shortcut[]>([]);
  const [history, setHistory] = useState<Visit[]>([]);
  const [selectedUrls, setSelectedUrls] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!visible) return;
    let alive = true;
    void loadShortcuts(userId).then((bms) => {
      if (alive) setBookmarks(bms);
    });
    void loadVisits(userId).then((vis) => {
      if (alive) {
        setHistory(vis);
        setSelectedUrls(new Set());
      }
    });
    return () => {
      alive = false;
    };
  }, [visible, userId]);

  const handleRemoveBookmark = async (id: string) => {
    const next = bookmarks.filter((b) => b.id !== id);
    setBookmarks(next);
    await saveShortcuts(next, userId);
  };

  const toggleHistorySelect = (url: string) => {
    setSelectedUrls((prev) => {
      const next = new Set(prev);
      if (next.has(url)) next.delete(url);
      else next.add(url);
      return next;
    });
  };

  const allSelected = history.length > 0 && selectedUrls.size === history.length;

  const handleToggleSelectAll = () => {
    if (allSelected) {
      setSelectedUrls(new Set());
    } else {
      setSelectedUrls(new Set(history.map((h) => h.url)));
    }
  };

  const handleDeleteSelected = async () => {
    if (selectedUrls.size === 0) return;
    const next = await removeVisits(userId, Array.from(selectedUrls));
    setHistory(next);
    setSelectedUrls(new Set());
  };

  const handleDeleteSingleHistory = async (url: string) => {
    const next = await removeVisits(userId, [url]);
    setHistory(next);
    setSelectedUrls((prev) => {
      const copy = new Set(prev);
      copy.delete(url);
      return copy;
    });
  };

  const handleClearAllHistory = async () => {
    await clearVisits(userId);
    setHistory([]);
    setSelectedUrls(new Set());
  };

  const formatVisitTime = (ts: number) => {
    try {
      const d = new Date(ts);
      const hh = String(d.getHours()).padStart(2, '0');
      const mm = String(d.getMinutes()).padStart(2, '0');
      return `${hh}:${mm}`;
    } catch {
      return '';
    }
  };

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onDismiss} statusBarTranslucent navigationBarTranslucent>
      <View style={st.menuDim}>
        <Pressable style={StyleSheet.absoluteFill} onPress={onDismiss} accessibilityLabel="메뉴 닫기" />
        <View style={[st.menuSheet, { paddingBottom: Math.max(insets.bottom, 20) }]}>
          <View style={st.menuHandle} />

          {/* 탭 전환: 북마크 / 방문 기록 (데스크톱 버전 & 퀵 메모 제외) */}
          <View style={st.menuTabBar}>
            <Pressable
              style={[st.menuTabBtn, selectedTab === 'bookmarks' && st.menuTabBtnActive]}
              onPress={() => onSelectTab('bookmarks')}
              accessibilityRole="tab"
              accessibilityState={{ selected: selectedTab === 'bookmarks' }}
            >
              <Text style={[st.menuTabText, selectedTab === 'bookmarks' && st.menuTabTextActive]}>
                북마크 ({bookmarks.length})
              </Text>
            </Pressable>
            <Pressable
              style={[st.menuTabBtn, selectedTab === 'history' && st.menuTabBtnActive]}
              onPress={() => onSelectTab('history')}
              accessibilityRole="tab"
              accessibilityState={{ selected: selectedTab === 'history' }}
            >
              <Text style={[st.menuTabText, selectedTab === 'history' && st.menuTabTextActive]}>
                방문 기록 ({history.length})
              </Text>
            </Pressable>
          </View>

          {selectedTab === 'bookmarks' ? (
            <ScrollView style={st.menuList} contentContainerStyle={{ gap: 8, paddingVertical: 4 }}>
              {bookmarks.length === 0 ? (
                <View style={st.emptyBox}>
                  <Text style={st.emptyText}>저장된 북마크가 없습니다.</Text>
                </View>
              ) : (
                bookmarks.map((bm) => (
                  <Pressable
                    key={bm.id}
                    style={st.menuItemRow}
                    onPress={() => onNavigate(bm.url)}
                    accessibilityRole="button"
                  >
                    <View style={{ flex: 1 }}>
                      <Text style={st.menuItemTitle} numberOfLines={1}>
                        {bm.name}
                      </Text>
                      <Text style={st.menuItemSub} numberOfLines={1}>
                        {bm.url}
                      </Text>
                    </View>
                    <Pressable onPress={() => void handleRemoveBookmark(bm.id)} hitSlop={8} style={st.deleteBtn}>
                      <Text style={st.deleteBtnText}>삭제</Text>
                    </Pressable>
                  </Pressable>
                ))
              )}
            </ScrollView>
          ) : (
            <View style={st.menuList}>
              {history.length === 0 ? (
                <View style={st.emptyBox}>
                  <Text style={st.emptyText}>방문 기록이 없습니다.</Text>
                </View>
              ) : (
                <>
                  {/* 방문 기록 상단 컨트롤: 전체 선택 / 선택 삭제 (N) / 전체 삭제 */}
                  <View style={st.historyToolbar}>
                    <Pressable onPress={handleToggleSelectAll} hitSlop={6} style={st.historyActionBtn}>
                      <Text style={st.historyActionSecondary}>
                        {allSelected ? '선택 해제' : '전체 선택'}
                      </Text>
                    </Pressable>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
                      <Pressable
                        onPress={() => void handleDeleteSelected()}
                        disabled={selectedUrls.size === 0}
                        hitSlop={6}
                        style={st.historyActionBtn}
                      >
                        <Text
                          style={[
                            st.historyActionDelete,
                            selectedUrls.size === 0 && { color: C.muted },
                          ]}
                        >
                          {selectedUrls.size > 0 ? `선택 삭제 (${selectedUrls.size})` : '선택 삭제'}
                        </Text>
                      </Pressable>
                      <Pressable onPress={() => void handleClearAllHistory()} hitSlop={6} style={st.historyActionBtn}>
                        <Text style={st.historyActionClear}>전체 삭제</Text>
                      </Pressable>
                    </View>
                  </View>

                  <ScrollView contentContainerStyle={{ gap: 8, paddingVertical: 4 }}>
                    {history.map((item) => {
                      const checked = selectedUrls.has(item.url);
                      const timeStr = formatVisitTime(item.at);
                      return (
                        <Pressable
                          key={item.url}
                          style={[st.menuItemRow, checked && st.menuItemRowChecked]}
                          onPress={() => onNavigate(item.url)}
                          accessibilityRole="button"
                        >
                          <Pressable
                            onPress={() => toggleHistorySelect(item.url)}
                            hitSlop={8}
                            style={[st.checkbox, checked && st.checkboxChecked]}
                            accessibilityRole="checkbox"
                            accessibilityState={{ checked }}
                          >
                            {checked && <IconCheck size={14} color="#FFFFFF" strokeWidth={2.5} />}
                          </Pressable>

                          <View style={{ flex: 1 }}>
                            <Text style={st.menuItemTitle} numberOfLines={1}>
                              {item.title || hostOf(item.url)}
                            </Text>
                            <Text style={st.menuItemSub} numberOfLines={1}>
                              {timeStr ? `${timeStr} · ${item.url}` : item.url}
                            </Text>
                          </View>

                          <Pressable onPress={() => void handleDeleteSingleHistory(item.url)} hitSlop={8} style={st.deleteBtn}>
                            <Text style={st.deleteBtnText}>삭제</Text>
                          </Pressable>
                        </Pressable>
                      );
                    })}
                  </ScrollView>
                </>
              )}
            </View>
          )}
        </View>
      </View>
    </Modal>
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
          <Text style={st.switcherTitle}>열린 탭 ({tabs.length})</Text>
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
  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
    paddingHorizontal: 6,
    paddingVertical: 6,
    borderBottomWidth: 1,
    borderBottomColor: C.border,
    backgroundColor: C.surface,
  },
  topIconBtn: {
    width: 30,
    height: 30,
    borderRadius: 15,
    alignItems: 'center',
    justifyContent: 'center',
  },
  urlBox: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    height: 38,
    borderRadius: 19,
    backgroundColor: C.surfaceMuted,
    borderWidth: 1,
    borderColor: C.border,
    paddingLeft: 6,
    paddingRight: 10,
    marginHorizontal: 2,
  },
  enginePill: {
    height: 26,
    paddingHorizontal: 9,
    borderRadius: 13,
    backgroundColor: C.surface,
    borderWidth: 1,
    borderColor: C.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  enginePillText: {
    fontSize: 11.5,
    fontWeight: '800',
    color: C.primary,
  },
  urlInput: { flex: 1, fontSize: 13.5, color: C.text, padding: 0 },
  tabCount: {
    width: 19,
    height: 19,
    borderRadius: 5,
    borderWidth: 1.8,
    borderColor: C.sub,
    alignItems: 'center',
    justifyContent: 'center',
  },
  tabCountText: { fontSize: 10.5, fontWeight: '800', color: C.sub },
  switcher: { flex: 1, backgroundColor: C.surfaceMuted },
  switcherHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 20, height: 56, backgroundColor: C.surface, borderBottomWidth: 1, borderBottomColor: C.border },
  switcherTitle: { fontSize: 17, fontWeight: '800', color: C.text },
  tabCard: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: C.surface, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border },
  tabCardOn: { borderColor: C.primary, borderWidth: 2 },
  tabCardTitle: { fontSize: 15, fontWeight: '700', color: C.text },
  tabCardSub: { fontSize: 12, color: C.sub, marginTop: 2 },
  addTab: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, height: 56, backgroundColor: C.surface, borderTopWidth: 1, borderTopColor: C.border },
  menuDim: { flex: 1, backgroundColor: C.dim, justifyContent: 'flex-end' },
  menuSheet: {
    backgroundColor: C.surface,
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    paddingHorizontal: 20,
    paddingTop: 10,
  },
  menuHandle: {
    width: 40,
    height: 4,
    borderRadius: 2,
    backgroundColor: '#D5DAE3',
    alignSelf: 'center',
    marginBottom: 14,
  },
  menuTabBar: {
    flexDirection: 'row',
    backgroundColor: C.surfaceMuted,
    borderRadius: 12,
    padding: 4,
    gap: 4,
    marginBottom: 14,
  },
  menuTabBtn: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: 9,
    alignItems: 'center',
    justifyContent: 'center',
  },
  menuTabBtnActive: {
    backgroundColor: C.primary,
  },
  menuTabText: {
    fontSize: 13,
    fontWeight: '700',
    color: C.sub,
  },
  menuTabTextActive: {
    color: '#FFFFFF',
  },
  menuList: {
    height: 320,
  },
  emptyBox: {
    height: 280,
    alignItems: 'center',
    justifyContent: 'center',
  },
  emptyText: {
    fontSize: 13.5,
    color: C.muted,
  },
  menuItemRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    backgroundColor: C.surfaceMuted,
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderWidth: 1,
    borderColor: 'transparent',
  },
  menuItemRowChecked: {
    backgroundColor: C.primarySoft,
    borderColor: C.primary,
  },
  menuItemTitle: {
    fontSize: 13.5,
    fontWeight: '600',
    color: C.text,
  },
  menuItemSub: {
    fontSize: 11.5,
    color: C.sub,
    marginTop: 2,
  },
  deleteBtn: {
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  deleteBtnText: {
    fontSize: 12,
    color: C.sub,
    fontWeight: '600',
  },
  historyToolbar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingBottom: 8,
    paddingHorizontal: 4,
  },
  historyActionBtn: {
    paddingVertical: 4,
    paddingHorizontal: 4,
  },
  historyActionSecondary: {
    fontSize: 12.5,
    fontWeight: '600',
    color: C.sub,
  },
  historyActionDelete: {
    fontSize: 12.5,
    fontWeight: '700',
    color: C.danger,
  },
  historyActionClear: {
    fontSize: 12.5,
    fontWeight: '600',
    color: C.primary,
  },
  checkbox: {
    width: 22,
    height: 22,
    borderRadius: 6,
    borderWidth: 1.5,
    borderColor: '#CBD5E1',
    backgroundColor: '#FFFFFF',
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkboxChecked: {
    backgroundColor: C.primary,
    borderColor: C.primary,
  },
});
