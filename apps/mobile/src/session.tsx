import { clearPendingBrowserNavigation } from './browserBus';
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { api } from './shared/api';
import { clearAuth, getAuth, saveAuth } from './shared/auth';
import { KEYS, onItemChange } from './shared/storage';
import { ApiError, type Me } from './shared/types';

// 로그인 상태와 내 정보. 프로필·권한이 바뀌면 브라우저 탭이 현재 페이지를 다시 분석하도록 알린다.

type Listener = () => void;
const reanalyzeListeners = new Set<Listener>();
export function onReanalyze(cb: Listener) {
  reanalyzeListeners.add(cb);
  return () => {
    reanalyzeListeners.delete(cb);
  };
}
export function requestReanalyze() {
  reanalyzeListeners.forEach((cb) => cb());
}

interface Session {
  loading: boolean;
  me: Me | null;
  refresh: () => Promise<Me | null>;
  login: (id: string, pw: string) => Promise<void>;
  logout: () => Promise<void>;
  setMe: (me: Me) => void;
}

const Ctx = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [me, setMeState] = useState<Me | null>(null);

  const refreshVersion = useRef(0);
  const refresh = useCallback(async () => {
    const version = ++refreshVersion.current;
    const auth = await getAuth();
    if (!auth) {
      setMeState(null);
      setLoading(false);
      return null;
    }
    try {
      const m = await api.getMe();
      if (version !== refreshVersion.current || (await getAuth())?.token !== auth.token) return null;
      setMeState(m);
      return m;
    } catch (e) {
      if (version !== refreshVersion.current || (await getAuth())?.token !== auth.token) return null;
      if (e instanceof ApiError && e.status === 401) {
        await clearAuth();
        setMeState(null);
      }
      return null;
    } finally {
      if (version === refreshVersion.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(refresh);
    return onItemChange(KEYS.auth, () => {
      clearPendingBrowserNavigation();
      setMeState(null);
      void refresh();
      requestReanalyze();
    });
  }, [refresh]);

  const login = useCallback(async (login_id: string, password: string) => {
    const { token } = await api.login(login_id, password);
    await saveAuth({ token, login_id });
    await refresh();
  }, [refresh]);

  const logout = useCallback(async () => {
    await api.logout().catch(() => undefined);
    await clearAuth();
    setMeState(null);
  }, []);

  const setMe = useCallback((m: Me) => {
    setMeState(m);
    requestReanalyze();
  }, []);

  return <Ctx.Provider value={{ loading, me, refresh, login, logout, setMe }}>{children}</Ctx.Provider>;
}

export function useSession(): Session {
  const s = useContext(Ctx);
  if (!s) throw new Error('SessionProvider missing');
  return s;
}
