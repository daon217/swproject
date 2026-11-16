import { createContext, useContext } from 'react';

export type Tab = 'recommend' | 'recent' | 'shortcuts' | 'settings';

export type Screen =
  | 'login'
  | 'signup'
  | 'mypage'
  | 'profileEdit'
  | 'password'
  | 'support'
  | 'filter'
  | 'premium'
  | 'payment'
  | 'paymentDone';

export interface Nav {
  tab: Tab;
  stack: Screen[];
  setTab: (t: Tab) => void;
  push: (s: Screen) => void;
  pop: () => void;
  /** 하위 화면을 모두 닫고 탭으로 돌아간다 */
  reset: (t?: Tab) => void;
  replace: (s: Screen) => void;
}

export const NavCtx = createContext<Nav | null>(null);

export function useNav(): Nav {
  const n = useContext(NavCtx);
  if (!n) throw new Error('Nav missing');
  return n;
}
