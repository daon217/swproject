import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { api } from '../shared/api';
import { clearAuth, getAuth, saveAuth } from '../shared/auth';
import { sendMessage } from '../shared/messages';
import { KEYS, onItemChange } from '../shared/storage';
import { ApiError, type Me } from '../shared/types';

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
  const [me, setMe] = useState<Me | null>(null);

  const refreshVersion = useRef(0);
  const refresh = useCallback(async () => {
    const version = ++refreshVersion.current;
    const auth = await getAuth();
    if (!auth) {
      setMe(null);
      setLoading(false);
      return null;
    }
    try {
      const m = await api.getMe();
      if (version !== refreshVersion.current || (await getAuth())?.token !== auth.token) return null;
      setMe(m);
      return m;
    } catch (e) {
      if (version !== refreshVersion.current || (await getAuth())?.token !== auth.token) return null;
      if (e instanceof ApiError && e.status === 401) {
        await clearAuth();
        setMe(null);
      }
      return null;
    } finally {
      if (version === refreshVersion.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    return onItemChange(KEYS.auth, () => { setMe(null); void refresh(); });
  }, [refresh]);

  const login = useCallback(
    async (login_id: string, password: string) => {
      const { token } = await api.login(login_id, password);
      await saveAuth({ token, login_id });
      await refresh();
    },
    [refresh],
  );

  const logout = useCallback(async () => {
    await api.logout().catch(() => undefined);
    await clearAuth();
    setMe(null);
  }, []);

  const update = useCallback((m: Me) => {
    setMe(m);
    // 프로필·권한이 바뀌면 현재 페이지 추천을 다시 받는다.
    void sendMessage({ type: 'reanalyze' });
  }, []);

  return <Ctx.Provider value={{ loading, me, refresh, login, logout, setMe: update }}>{children}</Ctx.Provider>;
}

export function useSession(): Session {
  const s = useContext(Ctx);
  if (!s) throw new Error('SessionProvider missing');
  return s;
}
