import { useEffect, useRef, useState } from 'react';
import { api, isMockApi } from '../shared/api';
import type { Analysis } from '../shared/types';

/** 개발용 미리보기에서 실제 업로드 계약을 확인한다. 확장 번들에는 포함되지 않는다. */
export function AnalysisCheck() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<Analysis | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const active = useRef<string | null>(null);
  const url = 'https://store.example.test/product/preview';
  useEffect(() => () => {
    if (active.current) void api.cancelAnalysis(active.current).catch(() => undefined);
  }, []);
  useEffect(() => {
    if (!result || !['queued', 'running'].includes(result.state)) return;
    let alive = true;
    const timer = setInterval(() => {
      void api.getAnalysis(result.analysis_id).then((r) => { if (alive) setResult(r); })
        .catch((e: Error) => { if (alive) setError(e.message); });
    }, 2000);
    return () => { alive = false; clearInterval(timer); };
  }, [result?.analysis_id, result?.state]);
  const submit = async () => {
    setError(''); setBusy(true);
    try {
      if (!file) throw new Error('테스트할 PNG·JPEG·WebP 이미지를 선택해 주세요.');
      if (file.size > 2 * 1024 * 1024) throw new Error('이미지는 2MiB 이하만 가능합니다.');
      const id = crypto.randomUUID();
      const created = await api.createAnalysis({ image: file, page_url: url, page_session_id: id, page_revision: 1, request_key: id });
      active.current = created.analysis_id;
      setResult(await api.getAnalysis(created.analysis_id));
    } catch (e) { setError(e instanceof Error ? e.message : '접수 실패'); }
    finally { setBusy(false); }
  };
  const cancel = async () => {
    if (!result) return;
    try {
      await api.cancelAnalysis(result.analysis_id);
      setResult(await api.getAnalysis(result.analysis_id)); active.current = null;
    } catch (e) { setError(e instanceof Error ? e.message : '취소 실패'); }
  };
  const pending = !!result && ['queued', 'running'].includes(result.state);
  return <section aria-label="개발용 API 확인">
    <h2>실제 API 연결 확인</h2>
    <p>{isMockApi ? '화면 목업 모드 — DB에 저장되지 않습니다.' : '실제 API 모드 — 회원·설정·상담 내용이 로컬 DB에 저장됩니다.'}</p>
    <p>오른쪽에서 회원가입·로그인한 후 테스트 이미지를 올리세요. OCR·추천 작업자 연결 전에는 대기 상태로 남습니다.</p>
    <label>분석 테스트 이미지 <input type="file" accept="image/png,image/jpeg,image/webp" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></label>
    <p><button onClick={() => void submit()} disabled={busy || pending}>분석 접수 테스트</button>{' '}
      <button onClick={() => void cancel()} disabled={!pending}>분석 취소</button></p>
    <p role="status">분석 상태: {result?.state ?? '미접수'}</p>
    {error && <p role="alert">{error}</p>}
  </section>;
}
