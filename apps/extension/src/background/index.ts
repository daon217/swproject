import { panelIsOpen, panelOpened } from './panelPresence';
import { api, isMockApi } from '../shared/api';
import { getAuthToken } from '../shared/auth';
import type { Message, PanelRoute, TabState } from '../shared/messages';
import { safeHttpUrl } from '../shared/format';
import { captureRule, sameUrl, shouldCapture } from '../shared/pageFilter';
import { isAiFallbackEnabled, isRecommendEnabled } from '../shared/recommendSetting';
import { KEYS } from '../shared/storage';
import type { PageScan } from '../shared/pageProduct';
import type { Analysis } from '../shared/types';
import { debugEnabled, dlog } from '../shared/debug';
import { initVisionSession, MAX_FRAMES, sendVisionFrame, VisionError, wantsScrollFrames } from '../shared/api/vision';

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
  if (prev && sameUrl(prev.url, url)) state.page_session_id = prev.page_session_id;
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

// ── 스크롤 중 Vision AI 직접 전송 ──────────────────────────────────────────
// content script가 스크롤하는 동안 0.7초마다 'scrollFrame'을 보내면, 여기서 보이는 화면을 캡처해 Vision에 보낸다.
// Vision 세션 id는 이 페이지의 page_session_id(백엔드 분석 요청과 같은 값). 페이지마다 init 한 번, frame 최대 15장.

interface VisionStream {
  sessionId: string;
  url: string;
  next: number;
  inited: boolean;
  ended: boolean;
  busy: boolean;
  failures: number;
}
const visionStreams = new Map<number, VisionStream>();

/** 스크롤 프레임 한 장을 캡처해 보낸다. 반환값: 이 페이지에서 더 보낼지(false면 content가 멈춘다) */
async function streamFrame(tab: chrome.tabs.Tab): Promise<boolean> {
  const tabId = tab.id!;
  if (!tab.active) return true; // 활성 탭만 캡처할 수 있다. 돌아와 다시 스크롤하면 이어서 보낸다
  const state = await readState(tabId);
  if (!state || !sameUrl(state.url, tab.url) || !wantsScrollFrames(state)) return true;
  let s = visionStreams.get(tabId);
  if (!s || s.sessionId !== state.page_session_id || !sameUrl(s.url, tab.url)) {
    s = { sessionId: state.page_session_id, url: tab.url!, next: 0, inited: false, ended: false, busy: false, failures: 0 };
    visionStreams.set(tabId, s);
  }
  if (s.ended || s.next >= MAX_FRAMES) return false;
  if (s.busy) return true; // 앞 프레임을 아직 보내는 중이면 이번 차례는 건너뛴다(쌓아 두지 않는다)
  s.busy = true;
  try {
    const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: 'jpeg', quality: 80 }).catch(() => null);
    if (!dataUrl) return true;
    const image = dataUrl.slice(dataUrl.indexOf(',') + 1);
    if (!s.inited) {
      const scan = await readPageScan(tabId);
      await initVisionSession({ session_id: s.sessionId, product_name: scan?.product?.name, price: scan?.product?.price, first_frame_image: image });
      s.inited = true;
    }
    const frame_index = s.next++;
    const is_last_frame = frame_index === MAX_FRAMES - 1;
    dlog('vision', `스크롤 프레임 ${frame_index + 1}/${MAX_FRAMES} 전송`, { session: s.sessionId });
    const res = await sendVisionFrame({ session_id: s.sessionId, frame_index, image, is_last_frame });
    s.failures = 0;
    if (is_last_frame || (res.status && res.status !== 'processing')) s.ended = true;
  } catch (e) {
    // 세션이 만료됐으면(404) 다음 차례에 다시 시작한다. Vision이 계속 응답하지 않으면 이 페이지에서는 멈춘다.
    if (e instanceof VisionError && e.status === 404) s.inited = false;
    if (++s.failures >= 3) s.ended = true;
    dlog('vision', 'Vision 전송 실패', { error: String(e), failures: s.failures });
  } finally {
    s.busy = false;
  }
  return !s.ended && s.next < MAX_FRAMES;
}

/** 진행 중인 분석이 더 이상 유효하지 않은 이유. 유효하면 null */
async function staleReason(tabId: number, state: TabState): Promise<string | null> {
  const tab = await chrome.tabs.get(tabId).catch(() => null);
  const latest = await readState(tabId);
  if (!(await isRecommendEnabled())) return '상품 추천 스위치 꺼짐';
  if (owners.has(state) && owners.get(state) !== await getAuthToken()) return '로그인 계정 변경';
  if (!tab) return '탭 닫힘';
  if (!sameUrl(tab.url, state.url)) return `탭 URL 변경 → ${tab.url}`;
  if (latest?.page_revision !== state.page_revision) return `새 분석 시작됨(rev ${latest?.page_revision} ≠ ${state.page_revision})`;
  return null;
}

async function isStale(tabId: number, state: TabState): Promise<boolean> {
  const reason = await staleReason(tabId, state);
  if (reason) dlog('analyze', `중단: ${reason}`, { tabId, page_revision: state.page_revision });
  return !!reason;
}

/** 탭별로 지금 분석 중인 URL. 같은 페이지 분석이 겹쳐 서로 취소하지 않게 한다. */
const inflight = new Map<number, string>();

/** 추천 상품 카드를 클릭해 열린 탭: 해당 상품 페이지가 열리는 동안에는 자동으로 새 분석을 돌리지 않는다. */
const recommendedTabs = new Map<number, { initialUrl: string; settledUrl: string | null; openedAt: number }>();

function isSameRecommendedNavigation(entry: { initialUrl: string; settledUrl: string | null; openedAt: number }, url: string): boolean {
  if (sameUrl(url, entry.initialUrl) || sameUrl(url, entry.settledUrl)) return true;
  // 클릭 직후(8초 이내) 리다이렉트·정규화 쿼리 파라미터가 붙는 경우는 같은 추천 상품 이동으로 본다.
  if (Date.now() - entry.openedAt < 8000) {
    entry.settledUrl = url;
    return true;
  }
  return false;
}

/**
 * 같은 페이지는 한 번만 분석한다. 쇼핑몰은 로드 중 URL 변경·로드 완료 이벤트가 여러 번 와서,
 * 그대로 두면 분석을 여러 번 접수하고 앞의 것을 취소한다. 취소된 분석도 Vision 처리는 계속돼
 * 실제 분석이 밀리고 시간 초과(OCR_FAILED)로 실패한다.
 * force: 다시 시도·로그인/설정 변경처럼 결과를 새로 받아야 할 때.
 */
async function analyze(tabId: number, url: string, force = false) {
  if (force) {
    recommendedTabs.delete(tabId);
  } else {
    const recEntry = recommendedTabs.get(tabId);
    if (recEntry) {
      if (isSameRecommendedNavigation(recEntry, url)) {
        const prev = await readState(tabId);
        if (prev && !sameUrl(prev.url, url)) await writeState({ ...prev, url });
        return dlog('analyze', '건너뜀: 추천 상품 클릭으로 이동한 페이지라 자동 재분석 안 함', { tabId, url });
      }
      recommendedTabs.delete(tabId);
    }
    if (sameUrl(inflight.get(tabId), url)) return dlog('analyze', '건너뜀: 같은 페이지 분석 진행 중', { tabId, url });
    const prev = await readState(tabId);
    // 진행 중 여부는 메모리(inflight)로만 본다. 서비스 워커가 내려가 'analyzing'이 남아도 다시 분석할 수 있게.
    if (sameUrl(prev?.url, url) && prev?.status === 'done') {
      return dlog('analyze', '건너뜀: 같은 페이지 결과 재사용', { tabId, url });
    }
  }
  inflight.set(tabId, url);
  try {
    await runAnalyze(tabId, url);
  } finally {
    if (sameUrl(inflight.get(tabId), url)) inflight.delete(tabId);
  }
}

async function runAnalyze(tabId: number, url: string) {
  const tab = await chrome.tabs.get(tabId).catch(() => null);
  if (!tab || !sameUrl(tab.url, url)) return;
  const token = await getAuthToken();
  const state = await resetForUrl(tabId, url);
  owners.set(state, token);
  const skip = (reason: string) => dlog('analyze', `건너뜀: ${reason}`, { tabId, url });
  dlog('analyze', `① 분석 시작 판단 (탭 ${tabId}, rev ${state.page_revision})`, { url, page_session_id: state.page_session_id, logged_in: !!token, mock: isMockApi });
  if (!(await isRecommendEnabled())) return skip('상품 추천 스위치 꺼짐'); // 상품 추천이 꺼져 있으면 캡처·분석하지 않는다
  const rule = captureRule(url);
  dlog('filter', `② 페이지 규칙: ${rule ?? '대상 아님'}`, { url, rule });
  if (!rule) return skip('상품 페이지 아님(pageFilter)'); // 상품 페이지가 아니면 'none' 상태(E01 빈 화면)

  // 로그인하지 않아도 분석한다(서버가 기기별 비회원 키로 기본 설정 추천). 회원 전용은 개인 설정·기록뿐이다.
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
  const scan = await readPageScan(tabId);
  const page_product = scan?.product ?? null;
  // 페이지에 적힌 상품명·카테고리로 식품이 확실하면 알려 준다(OCR이 리뷰 문장을 상품명으로 읽어 일반 상품으로 판단하는 문제 방지).
  // 페이지 주소·상품명은 보내지 않고 '식품'이라는 구분만 보낸다. 확실하지 않으면 서버가 캡처로 판단한다.
  const selected_domain = scan?.domain ?? undefined;
  dlog('analyze', '④-1 페이지로 본 상품 종류', selected_domain ?? '(서버 판단)');
  dlog('analyze', '④ 페이지에서 읽은 상품 정보', page_product);
  if (await isStale(tabId, state)) return skip('탭/URL 변경됨');
  try {
    // 분석 종류는 페이지로 식품이 확실할 때만 보낸다. 그 밖에는 서버가 캡처 내용으로 판단한다.
    const ai_fallback = await isAiFallbackEnabled();
    dlog('analyze', '⑤ 분석 접수 요청 POST /analyses', { image, page_revision: state.page_revision, ai_fallback });
    const created = await api.createAnalysis({
      image,
      page_product,
      selected_domain,
      page_url: url,
      page_session_id: state.page_session_id,
      page_revision: state.page_revision,
      request_key: `${state.page_session_id}:${state.page_revision}`,
      ai_fallback,
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
  if (tab?.id !== undefined && tab.url) void analyze(tab.id, tab.url, true);
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
  if (!state || !sameUrl(state.url, tab.url) || (state.status === 'none' && shouldCapture(tab.url))) {
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
  recommendedTabs.delete(tabId);
  visionStreams.delete(tabId);
  void chrome.storage.session.remove(tabKey(tabId));
});

// 로그인/로그아웃 시 권한·개인화가 바뀌므로 현재 탭을 다시 분석한다.
chrome.storage.onChanged.addListener((changes, area) => {
  // 로그인 계정이 바뀌거나 상품 추천·AI 실시간 추천을 켜고 끄면 모든 탭 결과를 지우고 현재 탭을 다시 판단한다.
  if (area === 'local' && (KEYS.auth in changes || KEYS.recommendEnabled in changes || KEYS.aiFallbackEnabled in changes)) {
    dlog('event', '설정 변경 → 모든 탭 결과 초기화 후 현재 탭 재분석', {
      changed: Object.keys(changes).filter((k) => ([KEYS.auth, KEYS.recommendEnabled, KEYS.aiFallbackEnabled] as string[]).includes(k)),
      recommendEnabled: KEYS.recommendEnabled in changes ? changes[KEYS.recommendEnabled].newValue : undefined,
      aiFallbackEnabled: KEYS.aiFallbackEnabled in changes ? changes[KEYS.aiFallbackEnabled].newValue : undefined,
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
      readState(tabId).then((s) => sendResponse(s && sameUrl(s.url, sender.tab?.url) ? s : null));
      return true;
    }
    case 'getActiveTabState': {
      activeTab().then(async (tab) => {
        if (tab?.id === undefined) return sendResponse(null);
        const s = await readState(tab.id);
        sendResponse(s && sameUrl(s.url, tab.url) ? s : emptyState(tab.id, tab.url ?? '', 0));
      });
      return true;
    }
    case 'reanalyze':
      void reanalyzeActive();
      return false;
    case 'scrollFrame': {
      const tab = sender.tab;
      if (tab?.id === undefined || !tab.url) return false;
      void streamFrame(tab).then((more) => sendResponse({ more }));
      return true;
    }
    case 'retry': {
      const p = raw.tabId !== undefined ? chrome.tabs.get(raw.tabId) : activeTab();
      Promise.resolve(p).then((tab) => {
        if (tab?.id !== undefined && tab.url) void analyze(tab.id, tab.url, true);
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
    case 'openRecommendedUrl': {
      const url = safeHttpUrl(raw.url);
      if (url) {
        void (async () => {
          const cur = await activeTab();
          const prev = cur?.id !== undefined ? await readState(cur.id) : null;
          const created = await chrome.tabs.create({ url });
          if (created.id !== undefined) {
            recommendedTabs.set(created.id, { initialUrl: url, settledUrl: null, openedAt: Date.now() });
            if (prev && prev.status === 'done' && prev.analysis) {
              await writeState({ ...prev, tabId: created.id, url });
            }
          }
        })();
      }
      return false;
    }
    default:
      return false;
  }
});
