import { useCallback, useEffect, useRef, useState } from 'react';
import { api, isMockApi } from '../shared/api';
import { sendMessage, type Message, type TabState } from '../shared/messages';
import { sameUrl, shouldCapture } from '../shared/pageFilter';
import { getAuth } from '../shared/auth';
import { KEYS, onItemChange } from '../shared/storage';
import { isRecommendEnabled } from '../shared/recommendSetting';
import { dlog } from '../shared/debug';

const inExtension = typeof chrome !== 'undefined' && !!chrome.runtime?.id;

/** 현재 활성 탭의 분석 상태. 확장 밖 미리보기에서는 ?url= 값으로 목업 분석을 직접 돌린다. */
export function useActiveTabState(): { state: TabState | null; retry: () => void } {
  const [state, setState] = useState<TabState | null>(null);
  const counter = useRef({ run: 0 });

  const load = useCallback(async () => {
    if (inExtension) {
      const s = (await sendMessage<TabState | null>({ type: 'getActiveTabState' })) ?? null;
      dlog('panel', `활성 탭 상태 불러옴 → ${s?.status ?? '없음'}`, s ? { tabId: s.tabId, url: s.url, page_revision: s.page_revision } : undefined);
      setState(s);
    } else {
      await runPreview(setState, counter.current);
    }
  }, []);

  useEffect(() => {
    void load();
    if (!inExtension) {
      const reload = () => void load();
      window.addEventListener('kp-reanalyze', reload);
      const off = onItemChange(KEYS.auth, reload);
      const offRecommend = onItemChange(KEYS.recommendEnabled, reload);
      return () => {
        off();
        offRecommend();
        window.removeEventListener('kp-reanalyze', reload);
      };
    }

    const onMsg = (msg: Message) => {
      if (msg.type !== 'tabState') return;
      chrome.tabs.query({ active: true, lastFocusedWindow: true }).then(([tab]) => {
        if (tab?.id === msg.state.tabId && sameUrl(tab.url, msg.state.url)) {
          dlog('panel', `사이드패널 화면 갱신 → ${msg.state.status}`, { tabId: msg.state.tabId, page_revision: msg.state.page_revision, error: msg.state.error });
          setState(msg.state);
        }
      });
    };
    const onActivated = () => void load();
    chrome.runtime.onMessage.addListener(onMsg);
    chrome.tabs.onActivated.addListener(onActivated);
    return () => {
      chrome.runtime.onMessage.removeListener(onMsg);
      chrome.tabs.onActivated.removeListener(onActivated);
    };
  }, [load]);

  const retry = useCallback(() => {
    if (inExtension) void sendMessage({ type: 'retry' });
    else void load();
  }, [load]);

  return { state, retry };
}

async function runPreview(set: (s: TabState) => void, counter: { run: number }) {
  const run = ++counter.run;
  const previewRun = () => counter.run;
  const url = new URLSearchParams(location.search).get('url') ?? 'https://brand.naver.com/epson/products/1120';
  const base: TabState = {
    tabId: 0,
    url,
    page_session_id: crypto.randomUUID(),
    page_revision: run,
    status: 'none',
    analysis: null,
    error: null,
  };
  if (!(await isRecommendEnabled()) || !isMockApi || !shouldCapture(url)) return set(base); // 실제 분석은 확장에서 캡처하거나 별도 업로드로 테스트
  set({ ...base, status: 'analyzing' });
  await getAuth();
  const created = await api.createAnalysis({ image: null, page_url: url, page_session_id: base.page_session_id, page_revision: run, request_key: `${base.page_session_id}:${run}` });
  for (let i = 0; i < 40 && run === previewRun(); i++) {
    const a = await api.getAnalysis(created.analysis_id);
    if (a.state === 'completed') {
      set({ ...base, status: 'done', analysis: a });
      if (!a.sections.some((s) => s.state === 'loading')) return;
    }
    await new Promise((r) => setTimeout(r, 600));
  }
}
