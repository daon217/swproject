import { accountKey } from './accountData';
import { getItem, setItem } from './storage';

// 쇼핑몰 바로가기. 서버에 저장하지 않고 이 기기(AsyncStorage)에만 저장한다.

export interface Shortcut {
  id: string;
  name: string;
  url: string;
  /** 아이콘에 표시할 글자(없으면 이름 첫 글자) */
  mark?: string;
}

export const DEFAULT_SHORTCUTS: Shortcut[] = [
  { id: 'coupang', name: '쿠팡', url: 'https://www.coupang.com' },
  { id: 'naver', name: '네이버쇼핑', url: 'https://shopping.naver.com', mark: 'N' },
  { id: '11st', name: '11번가', url: 'https://www.11st.co.kr', mark: '11' },
  { id: 'gmarket', name: 'G마켓', url: 'https://www.gmarket.co.kr', mark: 'G' },
  { id: 'ssg', name: 'SSG.COM', url: 'https://www.ssg.com', mark: 'S' },
  { id: 'musinsa', name: '무신사', url: 'https://www.musinsa.com' },
  { id: 'ohou', name: '오늘의집', url: 'https://ohou.se' },
  { id: 'kurly', name: '컬리', url: 'https://www.kurly.com' },
];

export async function loadShortcuts(userId?: string): Promise<Shortcut[]> {
  if (!userId) return DEFAULT_SHORTCUTS;
  return getItem<Shortcut[]>(accountKey(userId, 'shortcuts'), DEFAULT_SHORTCUTS);
}

export async function saveShortcuts(list: Shortcut[], userId?: string): Promise<void> {
  if (!userId) return;
  await setItem(accountKey(userId, 'shortcuts'), list);
}
