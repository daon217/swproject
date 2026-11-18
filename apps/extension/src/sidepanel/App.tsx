import { useCallback, useEffect, useMemo, useState } from 'react';
import type { PanelRoute } from '../shared/messages';
import { getItem, KEYS, onItemChange, removeItem } from '../shared/storage';
import { useRecommendEnabled } from './useRecommendEnabled';
import { Toggle } from './components';
import { NavCtx, type Nav, type Screen, type Tab } from './nav';
import { MyPageScreen, LoginScreen, PasswordScreen, ProfileEditScreen, SignupScreen, WithdrawScreen } from './screens/account';
import { FilterScreen, PaymentDoneScreen, PaymentScreen, PremiumScreen, SupportScreen } from './screens/more';
import { RecentTab, RecommendTab, SettingsTab, ShortcutsTab } from './screens/tabs';
import { SessionProvider, useSession } from './session';

const TABS: { id: Tab; label: string }[] = [
  { id: 'recommend', label: 'AI 추천' },
  { id: 'recent', label: '최근' },
  { id: 'shortcuts', label: '바로가기' },
  { id: 'settings', label: '설정' },
];

/** 로그인이 필요한 화면 */
const MEMBER_ONLY: Screen[] = ['mypage', 'profileEdit', 'password', 'support', 'filter', 'premium', 'payment', 'paymentDone', 'withdraw'];

function ScreenView({ screen }: { screen: Screen }) {
  switch (screen) {
    case 'login':
      return <LoginScreen />;
    case 'signup':
      return <SignupScreen />;
    case 'mypage':
      return <MyPageScreen />;
    case 'profileEdit':
      return <ProfileEditScreen />;
    case 'withdraw':
      return <WithdrawScreen />;
    case 'password':
      return <PasswordScreen />;
    case 'support':
      return <SupportScreen />;
    case 'filter':
      return <FilterScreen />;
    case 'premium':
      return <PremiumScreen />;
    case 'payment':
      return <PaymentScreen />;
    case 'paymentDone':
      return <PaymentDoneScreen />;
  }
}

function TabView({ tab }: { tab: Tab }) {
  switch (tab) {
    case 'recommend':
      return <RecommendTab />;
    case 'recent':
      return <RecentTab />;
    case 'shortcuts':
      return <ShortcutsTab />;
    case 'settings':
      return <SettingsTab />;
  }
}

function Shell() {
  const { me, loading } = useSession();
  const [tab, setTabState] = useState<Tab>('recommend');
  const [stack, setStack] = useState<Screen[]>([]);

  const nav: Nav = useMemo(
    () => ({
      tab,
      stack,
      setTab: (t) => {
        setTabState(t);
        setStack([]);
      },
      push: (s) => setStack((st) => [...st, s]),
      pop: () => setStack((st) => st.slice(0, -1)),
      reset: (t) => {
        setStack([]);
        if (t) setTabState(t);
      },
      replace: (s) => setStack((st) => [...st.slice(0, -1), s]),
    }),
    [tab, stack],
  );

  // 인페이지 플로팅에서 '프리미엄'·'필터'를 누르면 해당 화면으로 연다.
  const consumeRoute = useCallback(async () => {
    const pending = await getItem<{ route: PanelRoute; at: number } | null>(KEYS.pendingRoute, null);
    if (!pending || Date.now() - pending.at > 10_000) return;
    await removeItem(KEYS.pendingRoute);
    setTabState('recommend');
    setStack(pending.route === 'recommend' ? [] : [pending.route]);
  }, []);
  useEffect(() => {
    void consumeRoute();
    return onItemChange(KEYS.pendingRoute, () => void consumeRoute());
  }, [consumeRoute]);

  if (loading) return <p>로그인 상태 확인 중…</p>;
  let top = stack[stack.length - 1];
  // 로그아웃 상태에서 회원 화면이 열려 있으면 로그인 화면을 대신 보여준다.
  if (!loading && top && !me && MEMBER_ONLY.includes(top)) top = 'login';
  // 프리미엄 회원이 아니면 재료 필터 대신 프리미엄 안내
  if (top === 'filter' && me && !me.premium) top = 'premium';

  return (
    <NavCtx.Provider value={nav}>
      <div className="kp-root sp-app" key={me?.user_id ?? 'guest'}>
        {top ? (
          <div className="sp-screen" key={top}>
            <ScreenView screen={top} />
          </div>
        ) : (
          <>
            <RecommendSwitch />
            <nav className="sp-tabs" role="tablist">
              {TABS.map((t) => (
                <button key={t.id} role="tab" aria-selected={tab === t.id} className={tab === t.id ? 'is-active' : ''} onClick={() => nav.setTab(t.id)}>
                  {t.label}
                </button>
              ))}
            </nav>
            <main className="sp-main" role="tabpanel">
              <TabView tab={tab} />
            </main>
          </>
        )}
      </div>
    </NavCtx.Provider>
  );
}

/** 사이드 패널 맨 위: 상품 추천 켜기/끄기(기본 꺼짐) */
function RecommendSwitch() {
  const [on, setOn] = useRecommendEnabled();
  return (
    <div className="sp-recommend-switch">
      <div>
        <div className="sp-recommend-switch-title">상품 추천</div>
        <div className="sp-recommend-switch-desc">{on ? '상품 페이지를 열면 AI가 분석해요' : '꺼져 있어요 · 화면을 분석하지 않아요'}</div>
      </div>
      <Toggle checked={!!on} onChange={setOn} label="상품 추천" disabled={on === null} />
    </div>
  );
}

export function App() {
  return (
    <SessionProvider>
      <Shell />
    </SessionProvider>
  );
}
