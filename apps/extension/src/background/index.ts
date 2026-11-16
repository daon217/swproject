import { api } from '../shared/api';
import type { Message, PanelRoute, TabState } from '../shared/messages';
import { safeHttpUrl } from '../shared/format';
import { shouldCapture } from '../shared/pageFilter';
import { KEYS } from '../shared/storage';
import type { Analysis } from '../shared/types';

// 백그라운드 서비스 워커
// - 탭 URL이 바뀌면 디바운스 후 활성 화면을 캡처해 분석을 접수하고 결과를 폴링한다.
// - 결과 저장·표시 직전에 탭 URL과 page_revision이 그대로인지 확인한다(이전 탭 결과 노출 방지).
// - 서비스 워커는 언제든 내려갈 수 있어 탭 상태를 chrome.storage.session에 둔다.

const DEBOUNCE_MS = 800;
const POLL_MS = 700;
const POLL_TIMEOUT_MS = 30_000;

const tabKey = (tabId: number) => `kp.tab.${tabId}`;
const timers = new Map<number, ReturnType<typeof setTimeout>>();

chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => undefined);

async function readState(tabId: number): Promise<TabState | null> {
  const res = await chrome.storage.session.get(tabKey(tabId));
  return (res[tabKey(tabId)] as TabState | undefined) ?? null;
}

async function writeState(state: TabState) {
  await chrome.storage.session.set({ [tabKey(state.tabId)]: state });
  const msg: Message = { type: 'tabState', state };
  chrome.tabs.sendMessage(state.tabId, msg).catch(() => undefined);
  chrome.runtime.sendMessage(msg).catch(() => undefined);
}

function emptyState(tabId: number, url: string, revision: number): TabState {
  return {
    tabId,
    url,
    page_session_id: crypto.randomUUID(),
    page_revision: revision,
    status: 'none',
    analysis: null,
    error: null,
  };
}

/** 같은 탭에서 URL이 바뀌면 page_revision을 올리고 새 세션으로 시작한다. */
async function resetForUrl(tabId: number, url: string): Promise<TabState> {
  const prev = await readState(tabId);
  const state = emptyState(tabId, url, (prev?.page_revision ?? 0) + 1);
  if (prev && prev.url === url) state.page_session_id = prev.page_session_id;
  await writeState(state);
  return state;
}

function schedule(tabId: number, url: string) {
  clearTimeout(timers.get(tabId));
  timers.set(
    tabId,
    setTimeout(() => {
      timers.delete(tabId);
      void analyze(tabId, url);
    }, DEBOUNCE_MS),
  );
}

async function captureTab(tab: chrome.tabs.Tab): Promise<Blob | null> {
  // captureVisibleTab은 창의 활성 탭만 캡처한다.
  if (!tab.active || tab.windowId === undefined) return null;
  try {
    const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: 'jpeg', quality: 80 });
    return await (await fetch(dataUrl)).blob();
  } catch {
    return null;
  }
}

async function isStale(tabId: number, state: TabState): Promise<boolean> {
  const tab = await chrome.tabs.get(tabId).catch(() => null);
  const latest = await readState(tabId);
  return !tab || tab.url !== state.url || latest?.page_revision !== state.page_revision;
}

async function analyze(tabId: number, url: string) {
  const tab = await chrome.tabs.get(tabId).catch(() => null);
  if (!tab || tab.url !== url) return;
  const state = await resetForUrl(tabId, url);
  if (!shouldCapture(url)) return; // 상품 페이지가 아니면 'none' 상태(E01 빈 화면)

  if (!tab.active) return; // 비활성 탭은 활성화될 때 다시 시도
  const image = await captureTab(tab);
  if (await isStale(tabId, state)) return; // 캡처 전후 탭/URL이 바뀌면 폐기

  await writeState({ ...state, status: 'analyzing' });
  try {
    const created = await api.createAnalysis({
      image,
      page_url: url,
      page_session_id: state.page_session_id,
      page_revision: state.page_revision,
      request_key: `${state.page_session_id}:${state.page_revision}`,
    });
    const started = Date.now();
    let analysis: Analysis | null = null;
    while (Date.now() - started < POLL_TIMEOUT_MS) {
      if (await isStale(tabId, state)) {
        await api.cancelAnalysis(created.analysis_id).catch(() => undefined);
        return;
      }
      analysis = await api.getAnalysis(created.analysis_id);
      // 응답이 현재 페이지 세션·버전과 다르면 표시하지 않는다.
      if (analysis.page_session_id !== state.page_session_id || analysis.page_revision !== state.page_revision) return;
      if (analysis.state === 'completed' || analysis.state === 'failed' || analysis.state === 'cancelled') {
        // AI 추천이 먼저 끝나면 바로 보여주고, 중고 구역처럼 남은 구역은 계속 갱신한다.
        await writeState({ ...state, status: analysis.state === 'completed' ? 'done' : 'error', analysis, error: analysis.error?.message ?? null });
        if (!analysis.sections.some((s) => s.state === 'loading')) return;
      }
      await new Promise((r) => setTimeout(r, POLL_MS));
    }
    if (analysis?.state !== 'completed') {
      await writeState({ ...state, status: 'error', analysis: null, error: '분석 시간이 오래 걸리고 있어요.' });
    }
  } catch (e) {
    if (await isStale(tabId, state)) return;
    await writeState({ ...state, status: 'error', analysis: null, error: e instanceof Error ? e.message : '분석에 실패했어요.' });
  }
}

async function activeTab(): Promise<chrome.tabs.Tab | null> {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  return tab ?? null;
}

async function reanalyzeActive() {
  const tab = await activeTab();
  if (tab?.id !== undefined && tab.url) void analyze(tab.id, tab.url);
}

chrome.tabs.onUpdated.addListener((tabId, info, tab) => {
  if (info.url || (info.status === 'complete' && tab.url)) schedule(tabId, tab.url!);
});

chrome.tabs.onActivated.addListener(async ({ tabId }) => {
  const tab = await chrome.tabs.get(tabId).catch(() => null);
  if (!tab?.url) return;
  const state = await readState(tabId);
  // 활성화 시점에 결과가 없거나 다른 URL이면 다시 분석한다.
  if (!state || state.url !== tab.url || (state.status === 'none' && shouldCapture(tab.url))) schedule(tabId, tab.url);
  else chrome.runtime.sendMessage({ type: 'tabState', state } satisfies Message).catch(() => undefined);
});

chrome.tabs.onRemoved.addListener((tabId) => {
  clearTimeout(timers.get(tabId));
  void chrome.storage.session.remove(tabKey(tabId));
});

// 로그인/로그아웃 시 권한·개인화가 바뀌므로 현재 탭을 다시 분석한다.
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === 'local' && KEYS.auth in changes) void reanalyzeActive();
});

chrome.runtime.onMessage.addListener((raw: Message, sender, sendResponse) => {
  switch (raw.type) {
    case 'getTabState': {
      const tabId = sender.tab?.id;
      if (tabId === undefined) return false;
      readState(tabId).then((s) => sendResponse(s && s.url === sender.tab?.url ? s : null));
      return true;
    }
    case 'getActiveTabState': {
      activeTab().then(async (tab) => {
        if (tab?.id === undefined) return sendResponse(null);
        const s = await readState(tab.id);
        sendResponse(s && s.url === tab.url ? s : emptyState(tab.id, tab.url ?? '', 0));
      });
      return true;
    }
    case 'reanalyze':
      void reanalyzeActive();
      return false;
    case 'retry': {
      const p = raw.tabId !== undefined ? chrome.tabs.get(raw.tabId) : activeTab();
      Promise.resolve(p).then((tab) => {
        if (tab?.id !== undefined && tab.url) void analyze(tab.id, tab.url);
      });
      return false;
    }
    case 'openSidePanel': {
      // sidePanel.open은 사용자 동작 직후에만 허용되므로 await 없이 바로 호출한다.
      const tabId = sender.tab?.id;
      if (tabId !== undefined) {
        chrome.sidePanel.open({ tabId }).catch(() => undefined);
        void chrome.storage.local.set({ [KEYS.pendingRoute]: { route: raw.route satisfies PanelRoute, at: Date.now() } });
      }
      return false;
    }
    case 'openUrl': {
      const url = safeHttpUrl(raw.url);
      if (url) void chrome.tabs.create({ url });
      return false;
    }
    default:
      return false;
  }
});
