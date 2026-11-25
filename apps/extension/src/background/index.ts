import { panelIsOpen, panelOpened } from './panelPresence';
import { api, isMockApi } from '../shared/api';
import { getAuthToken } from '../shared/auth';
import type { Message, PanelRoute, TabState } from '../shared/messages';
import { safeHttpUrl } from '../shared/format';
import { captureRule, shouldCapture } from '../shared/pageFilter';
import { isRecommendEnabled } from '../shared/recommendSetting';
import { KEYS } from '../shared/storage';
import type { PageScan } from '../shared/pageProduct';
import type { Analysis } from '../shared/types';
import { debugEnabled, dlog } from '../shared/debug';

if (debugEnabled) dlog('bg', '디버그 로그 켜짐', { api: import.meta.env.VITE_API_BASE_URL, mock: isMockApi });

/** [임시] content script에 페이지 상품명·가격을 묻는다. 응답이 없으면 null */
async function readPageScan(tabId: number): Promise<PageScan | null> {
  const t0 = Date.now();
  const timeout = new Promise<null>((r) => setTimeout(() => r(null), 1500));
  const ask = chrome.tabs.sendMessage(tabId, { type: 'extractProduct' } satisfies Message).catch(() => null) as Promise<PageScan | null>;
  const scan = (await Promise.race([ask, timeout])) ?? null;
  dlog('scan', scan ? `content script 응답 (${Date.now() - t0}ms)` : `content script 응답 없음/시간초과 (${Date.now() - t0}ms) — 페이지 새로고침 전 주입 안 됨일 수 있음`,
    scan ? { signal: scan.signal, product: scan.product } : undefined);
  return scan;
}

/** 쇼핑몰이 아닌 사이트: 페이지에 상품 표시가 있는지 확인한다. 늦게 그려지는 페이지를 위해 한 번 더 본다. */
async function confirmProductSignal(tabId: number): Promise<boolean> {
  for (let i = 0; i < 2; i++) {
    dlog('filter', `상품 신호 확인 ${i + 1}/2`, { tabId });
    if ((await readPageScan(tabId))?.signal) return true;
    if (i === 0) await new Promise((r) => setTimeout(r, 1500));
  }
  return false;
}

// 백그라운드 서비스 워커
// - 탭 URL이 바뀌면 디바운스 후 활성 화면을 캡처해 분석을 접수하고 결과를 폴링한다.
// - 결과 저장·표시 직전에 탭 URL과 page_revision이 그대로인지 확인한다(이전 탭 결과 노출 방지).
// - 서비스 워커는 언제든 내려갈 수 있어 탭 상태를 chrome.storage.session에 둔다.

const DEBOUNCE_MS = 800;
const POLL_MS = 700;
const POLL_TIMEOUT_MS = 120_000;

const tabKey = (tabId: number) => `kp.tab.${tabId}`;
const owners = new WeakMap<TabState, string | null>();
const timers = new Map<number, ReturnType<typeof setTimeout>>();

chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => undefined);

async function readState(tabId: number): Promise<TabState | null> {
  const res = await chrome.storage.session.get(tabKey(tabId));
  const cached = res[tabKey(tabId)] as { state?: TabState; owner?: string } | undefined;
  const token = await getAuthToken();
  const owner = token ? Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(token)))).map(b => b.toString(16).padStart(2, '0')).join('') : '';
  return cached?.owner === owner ? cached.state ?? null : null;
}

async function writeState(state: TabState, expectedToken?: string | null) {
  const token = await getAuthToken();
  if (expectedToken !== undefined && token !== expectedToken) return;
  const owner = token ? Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(token)))).map(b => b.toString(16).padStart(2, '0')).join('') : '';
  await chrome.storage.session.set({ [tabKey(state.tabId)]: { state, owner } });
  dlog('state', `탭 ${state.tabId} rev ${state.page_revision} → ${state.status}`,
    { url: state.url, analysis_id: state.analysis?.analysis_id ?? null, result_kind: (state.analysis as { result_kind?: string } | null)?.result_kind ?? null, error: state.error });
  if ((await getAuthToken()) !== token) return;
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

function schedule(tabId: number, url: string, why = '') {
  dlog('schedule', `${timers.has(tabId) ? '디바운스 재설정' : '분석 예약'} ${DEBOUNCE_MS}ms ${why}`, { tabId, url });
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
    const t0 = Date.now();
    const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: 'jpeg', quality: 80 });
    const blob = await (await fetch(dataUrl)).blob();
    dlog('capture', `captureVisibleTab 완료 (${Date.now() - t0}ms)`, blob);
    return blob;
  } catch (e) {
    dlog('capture', 'captureVisibleTab 실패 — 권한/chrome:// 페이지/창 비활성', e);
    return null;
  }
}

/** 진행 중인 분석이 더 이상 유효하지 않은 이유. 유효하면 null */
async function staleReason(tabId: number, state: TabState): Promise<string | null> {
  const tab = await chrome.tabs.get(tabId).catch(() => null);
  const latest = await readState(tabId);
  if (!(await isRecommendEnabled())) return '상품 추천 스위치 꺼짐';
  if (owners.has(state) && owners.get(state) !== await getAuthToken()) return '로그인 계정 변경';
  if (!tab) return '탭 닫힘';
  if (tab.url !== state.url) return `탭 URL 변경 → ${tab.url}`;
  if (latest?.page_revision !== state.page_revision) return `새 분석 시작됨(rev ${latest?.page_revision} ≠ ${state.page_revision})`;
  return null;
}

async function isStale(tabId: number, state: TabState): Promise<boolean> {
  const reason = await staleReason(tabId, state);
  if (reason) dlog('analyze', `중단: ${reason}`, { tabId, page_revision: state.page_revision });
  return !!reason;
}

async function analyze(tabId: number, url: string) {
  const tab = await chrome.tabs.get(tabId).catch(() => null);
  if (!tab || tab.url !== url) return;
  const token = await getAuthToken();
  const state = await resetForUrl(tabId, url);
  owners.set(state, token);
  const skip = (reason: string) => dlog('analyze', `건너뜀: ${reason}`, { tabId, url });
  dlog('analyze', `① 분석 시작 판단 (탭 ${tabId}, rev ${state.page_revision})`, { url, page_session_id: state.page_session_id, logged_in: !!token, mock: isMockApi });
  if (!(await isRecommendEnabled())) return skip('상품 추천 스위치 꺼짐'); // 상품 추천이 꺼져 있으면 캡처·분석하지 않는다
  const rule = captureRule(url);
  dlog('filter', `② 페이지 규칙: ${rule ?? '대상 아님'}`, { url, rule });
  if (!rule) return skip('상품 페이지 아님(pageFilter)'); // 상품 페이지가 아니면 'none' 상태(E01 빈 화면)

  if (!isMockApi && !(await getAuthToken())) return skip('로그인 안 됨'); // 로그인 전에 화면을 업로드하지 않음
  if (!tab.active) return skip('비활성 탭'); // 비활성 탭은 활성화될 때 다시 시도
  // 쇼핑몰이 아닌 사이트는 페이지에 상품 표시가 있을 때만 캡처한다(학습포털 등 제외).
  if (rule === 'needs-signal' && !(await confirmProductSignal(tabId))) return skip('상품 신호 없음');
  if (await isStale(tabId, state)) return skip('탭/URL 변경됨');
  const image = await captureTab(tab);
  dlog('analyze', image ? '③ 화면 캡처 완료' : '③ 화면 캡처 실패 — URL을 보내지 않으므로 분석 중단', image);
  if (!image) {
    if (!(await isStale(tabId, state))) await writeState({ ...state, status: 'error', error: '화면을 캡처하지 못했어요. 다시 시도해 주세요.' }, token);
    return;
  }
  if (await isStale(tabId, state)) return skip('캡처 중 탭/URL 변경됨'); // 캡처 전후 탭/URL이 바뀌면 폐기

  await writeState({ ...state, status: 'analyzing' }, token);
  const page_product = (await readPageScan(tabId))?.product ?? null;
  dlog('analyze', '④ 페이지에서 읽은 상품 정보', page_product);
  if (await isStale(tabId, state)) return skip('탭/URL 변경됨');
  try {
    // 분석 종류(상품/식품)는 보내지 않는다. 서버가 캡처 내용으로 판단한다.
    dlog('analyze', '⑤ 분석 접수 요청 POST /analyses (캡처만 전송, page_url·분석 종류 미전송)', { image, page_revision: state.page_revision });
    const created = await api.createAnalysis({
      image,
      page_product,
      page_url: url,
      page_session_id: state.page_session_id,
      page_revision: state.page_revision,
      request_key: `${state.page_session_id}:${state.page_revision}`,
    });
    dlog('analyze', `⑥ 접수됨 analysis_id=${created.analysis_id} → ${POLL_MS}ms 간격 폴링 시작(최대 ${POLL_TIMEOUT_MS / 1000}s)`, created);
    const started = Date.now();
    let analysis: Analysis | null = null;
    let lastState = '';
    while (Date.now() - started < POLL_TIMEOUT_MS) {
      if (await isStale(tabId, state)) {
        await api.cancelAnalysis(created.analysis_id).catch(() => undefined);
        return;
      }
      analysis = await api.getAnalysis(created.analysis_id);
      const sec = analysis.sections?.map((s) => `${s.kind}:${s.state}(${s.items.length})`);
      if (analysis.state !== lastState) {
        dlog('poll', `⑦ 상태 변경 ${lastState || '시작'} → ${analysis.state} (${((Date.now() - started) / 1000).toFixed(1)}s)`,
          { sections: sec, result_kind: (analysis as { result_kind?: string }).result_kind, error: analysis.error ?? null });
        lastState = analysis.state;
      } else {
        dlog('poll', `${((Date.now() - started) / 1000).toFixed(1)}s state=${analysis.state}`, { sections: sec });
      }
      if (await isStale(tabId, state)) return;
      // 응답이 현재 페이지 세션·버전과 다르면 표시하지 않는다.
      if (analysis.page_session_id !== state.page_session_id || analysis.page_revision !== state.page_revision) {
        dlog('poll', '응답의 page_session/revision이 현재 페이지와 달라 표시 안 함', { got: [analysis.page_session_id, analysis.page_revision], want: [state.page_session_id, state.page_revision] });
        return;
      }
      if (analysis.state === 'completed' || analysis.state === 'failed' || analysis.state === 'cancelled') {
        // AI 추천이 먼저 끝나면 바로 보여주고, 중고 구역처럼 남은 구역은 계속 갱신한다.
        dlog('result', `⑧ 결과 표시: ${analysis.state}`, {
          result_kind: (analysis as { result_kind?: string }).result_kind,
          source_summary: (analysis as { source_summary?: unknown }).source_summary,
          cards: analysis.sections.flatMap((s) => s.items.map((i) => `${s.kind}: ${i.name} ${i.price ?? ''}${i.currency ?? ''}`)),
          warnings: (analysis as { warnings?: unknown }).warnings, error: analysis.error ?? null });
        await writeState({ ...state, status: analysis.state === 'completed' ? 'done' : 'error', analysis, error: analysis.error?.message ?? null }, token);
        if (!analysis.sections.some((s) => s.state === 'loading')) return;
        dlog('poll', '일부 구역이 아직 loading — 계속 폴링');
      }
      await new Promise((r) => setTimeout(r, POLL_MS));
    }
    if (await isStale(tabId, state)) return;
    if (analysis?.state !== 'completed') {
      dlog('analyze', `시간 초과(${POLL_TIMEOUT_MS / 1000}s) — 서버에 분석 워커가 없거나 처리 중`, { analysis_id: created.analysis_id, last_state: analysis?.state });
      await api.cancelAnalysis(created.analysis_id).catch(() => undefined);
      await writeState({ ...state, status: 'error', analysis: null, error: '분석 시간이 오래 걸리고 있어요.' }, token);
    }
  } catch (e) {
    dlog('analyze', '분석 오류', e);
    if (await isStale(tabId, state)) return;
    await writeState({ ...state, status: 'error', analysis: null, error: e instanceof Error ? e.message : '분석에 실패했어요.' }, token);
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
  if (info.url || (info.status === 'complete' && tab.url)) {
    dlog('event', `tabs.onUpdated ${info.url ? 'URL 변경' : '로드 완료'}`, { tabId, url: tab.url });
    schedule(tabId, tab.url!, info.url ? '(URL 변경)' : '(로드 완료)');
  }
});

chrome.tabs.onActivated.addListener(async ({ tabId }) => {
  const tab = await chrome.tabs.get(tabId).catch(() => null);
  if (!tab?.url) return;
  const state = await readState(tabId);
  // 활성화 시점에 결과가 없거나 다른 URL이면 다시 분석한다.
  if (!state || state.url !== tab.url || (state.status === 'none' && shouldCapture(tab.url))) {
    dlog('event', 'tabs.onActivated → 결과 없음/다른 URL이라 재분석', { tabId, url: tab.url, prev: state?.status ?? null });
    schedule(tabId, tab.url, '(탭 전환)');
  } else {
    dlog('event', `tabs.onActivated → 저장된 결과(${state.status}) 재사용`, { tabId });
    chrome.runtime.sendMessage({ type: 'tabState', state } satisfies Message).catch(() => undefined);
  }
});

chrome.tabs.onRemoved.addListener((tabId) => {
  dlog('event', 'tabs.onRemoved → 탭 상태 삭제', { tabId });
  clearTimeout(timers.get(tabId));
  void chrome.storage.session.remove(tabKey(tabId));
});

// 로그인/로그아웃 시 권한·개인화가 바뀌므로 현재 탭을 다시 분석한다.
chrome.storage.onChanged.addListener((changes, area) => {
  // 로그인 계정이 바뀌거나 상품 추천을 켜고 끄면 모든 탭 결과를 지우고 현재 탭을 다시 판단한다.
  if (area === 'local' && (KEYS.auth in changes || KEYS.recommendEnabled in changes)) {
    dlog('event', '설정 변경 → 모든 탭 결과 초기화 후 현재 탭 재분석', {
      changed: Object.keys(changes).filter((k) => ([KEYS.auth, KEYS.recommendEnabled] as string[]).includes(k)),
      recommendEnabled: KEYS.recommendEnabled in changes ? changes[KEYS.recommendEnabled].newValue : undefined,
      logged_in: KEYS.auth in changes ? !!changes[KEYS.auth].newValue : undefined });
    for (const timer of timers.values()) clearTimeout(timer);
    timers.clear();
    void chrome.tabs.query({}).then(async tabs => {
      for (const tab of tabs) if (tab.id !== undefined) await resetForUrl(tab.id, tab.url ?? '');
      await reanalyzeActive();
    });
  }
});

chrome.runtime.onMessage.addListener((raw: Message, sender, sendResponse) => {
  dlog('msg', `메시지 수신: ${raw.type} (${sender.tab ? `탭 ${sender.tab.id} content` : '사이드패널'})`, raw.type === 'openSidePanel' || raw.type === 'retry' ? raw : undefined);
  switch (raw.type) {
    case 'getPanelVisibility':
      sendResponse(sender.tab ? panelIsOpen(sender.tab.windowId) : false);
      return false;
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
        chrome.sidePanel.open({ tabId }).then(() => {
          panelOpened(sender.tab!.windowId);
          sendResponse({ ok: true });
        }).catch(() => sendResponse({ ok: false }));
        void chrome.storage.local.set({ [KEYS.pendingRoute]: { route: raw.route satisfies PanelRoute, at: Date.now() } });
        return true;
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
