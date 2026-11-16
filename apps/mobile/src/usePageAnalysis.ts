import { useCallback, useEffect, useRef, useState, type ComponentRef, type RefObject } from 'react';
import { Platform, type View } from 'react-native';
import { captureRef } from 'react-native-view-shot';
import { onReanalyze } from './session';
import { api } from './shared/api';
import { shouldCapture } from './shared/pageFilter';
import { uuid } from './shared/platform';
import type { Analysis } from './shared/types';
import type { AnalysisStatus } from './ui/ResultView';

// 앱 안 브라우저 페이지 분석(명세 F-CAP-02·03, F-AN-01).
// URL이 바뀌고 로딩이 끝나면 디바운스 후 화면을 캡처해 분석을 접수하고 결과를 폴링한다.
// 기다리는 사이 URL·page_revision이 바뀌면 결과를 버린다(이전 페이지 결과 노출 방지).

const DEBOUNCE_MS = 800;
const POLL_MS = 700;
const TIMEOUT_MS = 30_000;

export interface PageAnalysis {
  status: AnalysisStatus;
  analysis: Analysis | null;
  error: string | null;
  pageSessionId: string;
}

export function usePageAnalysis(url: string | null, loading: boolean, captureTarget: RefObject<ComponentRef<typeof View> | null>) {
  const [state, setState] = useState<PageAnalysis>({ status: 'none', analysis: null, error: null, pageSessionId: '' });
  const revision = useRef(0);
  const current = useRef<{ url: string | null; rev: number }>({ url: null, rev: 0 });
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const run = useCallback(
    async (target: string) => {
      const rev = ++revision.current;
      const pageSessionId = uuid();
      current.current = { url: target, rev };
      const stale = () => current.current.rev !== rev || current.current.url !== target;

      if (!shouldCapture(target)) {
        setState({ status: 'none', analysis: null, error: null, pageSessionId });
        return;
      }
      setState({ status: 'analyzing', analysis: null, error: null, pageSessionId });

      let image: { uri: string } | null = null;
      // 웹 미리보기(iframe)는 캡처하지 않고 주소 기준으로만 분석한다.
      if (Platform.OS !== 'web') {
        try {
          const uri = await captureRef(captureTarget as Parameters<typeof captureRef>[0], { format: 'jpg', quality: 0.8, result: 'tmpfile' });
          image = { uri };
        } catch {
          image = null; // 캡처 실패 시에도 URL 기반 분석은 진행(서버가 판단)
        }
      }
      if (stale()) return;

      try {
        const created = await api.createAnalysis({ image, page_url: target, page_session_id: pageSessionId, page_revision: rev, request_key: `${pageSessionId}:${rev}` });
        const started = Date.now();
        while (Date.now() - started < TIMEOUT_MS) {
          if (stale()) {
            void api.cancelAnalysis(created.analysis_id).catch(() => undefined);
            return;
          }
          const a = await api.getAnalysis(created.analysis_id);
          if (stale() || a.page_session_id !== pageSessionId || a.page_revision !== rev) return;
          if (a.state === 'completed') {
            setState({ status: 'done', analysis: a, error: null, pageSessionId });
            if (!a.sections.some((x) => x.state === 'loading')) return;
          } else if (a.state === 'failed' || a.state === 'cancelled') {
            setState({ status: 'error', analysis: null, error: a.error?.message ?? '분석에 실패했어요.', pageSessionId });
            return;
          }
          await new Promise((r) => setTimeout(r, POLL_MS));
        }
        if (!stale()) setState((s) => (s.status === 'done' ? s : { status: 'error', analysis: null, error: '분석 시간이 오래 걸리고 있어요.', pageSessionId }));
      } catch (e) {
        if (!stale()) setState({ status: 'error', analysis: null, error: e instanceof Error ? e.message : '분석에 실패했어요.', pageSessionId });
      }
    },
    [captureTarget],
  );

  // URL이 바뀌면 이전 결과를 즉시 숨기고, 로딩이 끝나면 디바운스 후 분석
  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    if (current.current.url !== url) {
      revision.current++;
      current.current = { url, rev: revision.current };
      setState({ status: 'none', analysis: null, error: null, pageSessionId: '' });
    }
    if (!url || loading) return;
    timer.current = setTimeout(() => void run(url), DEBOUNCE_MS);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [url, loading, run]);

  // 로그인·프로필·결제 변경 시 현재 페이지 다시 분석
  useEffect(
    () =>
      onReanalyze(() => {
        if (url && !loading) void run(url);
      }),
    [url, loading, run],
  );

  const retry = useCallback(() => {
    if (url) void run(url);
  }, [url, run]);

  return { ...state, retry };
}
