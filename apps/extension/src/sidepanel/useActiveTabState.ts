import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../shared/api';
import { sendMessage, type Message, type TabState } from '../shared/messages';
import { shouldCapture } from '../shared/pageFilter';
import { getAuth } from '../shared/auth';
import { KEYS, onItemChange } from '../shared/storage';

const inExtension = typeof chrome !== 'undefined' && !!chrome.runtime?.id;

/** 현재 활성 탭의 분석 상태. 확장 밖 미리보기에서는 ?url= 값으로 목업 분석을 직접 돌린다. */
export function useActiveTabState(): { state: TabState | null; retry: () => void } {
  const [state, setState] = useState<TabState | null>(null);
  const counter = useRef({ run: 0 });

  const load = useCallback(async () => {
    if (inExtension) {
      setState((await sendMessage<TabState | null>({ type: 'getActiveTabState' })) ?? null);
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
      return () => {
        off();
        window.removeEventListener('kp-reanalyze', reload);
      };
    }

    const onMsg = (msg: Message) => {
      if (msg.type !== 'tabState') return;
      chrome.tabs.query({ active: true, lastFocusedWindow: true }).then(([tab]) => {
        if (tab?.id === msg.state.tabId && tab.url === msg.state.url) setState(msg.state);
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
  if (!shouldCapture(url)) return set(base);
  set({ ...base, status: 'analyzing' });
  await getAuth();
  const created = await api.createAnalysis({ image: null, page_url: url, page_session_id: base.page_session_id, page_revision: run, request_key: String(run) });
  for (let i = 0; i < 40 && run === previewRun(); i++) {
    const a = await api.getAnalysis(created.analysis_id);
    if (a.state === 'completed') {
      set({ ...base, status: 'done', analysis: a });
      if (!a.sections.some((s) => s.state === 'loading')) return;
    }
    await new Promise((r) => setTimeout(r, 600));
  }
}
