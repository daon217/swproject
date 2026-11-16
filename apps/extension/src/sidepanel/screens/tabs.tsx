import { useEffect, useRef, useState } from 'react';
import { api } from '../../shared/api';
import { formatPrice, safeHttpUrl } from '../../shared/format';
import { DEFAULT_SHORTCUTS, loadShortcuts, saveShortcuts, type Shortcut } from '../../shared/shortcuts';
import { IconExternal, IconFood, IconPlus, IconPrinter } from '../../shared/ui/icons';
import { OfferRow, ResultView } from '../../shared/ui/ResultView';
import type { AnalysisHistoryItem, OfferCard } from '../../shared/types';
import { ConfirmDialog, Note, RowButton, Toast, Toggle } from '../components';
import { useNav } from '../nav';
import { useSession } from '../session';
import { useActiveTabState } from '../useActiveTabState';

export function openUrl(url: string) {
  const safe = safeHttpUrl(url);
  if (!safe) return;
  if (typeof chrome !== 'undefined' && chrome.tabs?.create) void chrome.tabs.create({ url: safe });
  else window.open(safe, '_blank', 'noopener');
}

// ---------- AI 추천 (E01, E16~E27) ----------
export function RecommendTab() {
  const { state, retry } = useActiveTabState();
  const nav = useNav();
  const { me } = useSession();
  return (
    <ResultView
      state={state}
      onOpenUrl={openUrl}
      onRetry={retry}
      onPremium={() => nav.push(me ? 'premium' : 'login')}
      onFilter={() => nav.push('filter')}
    />
  );
}

// ---------- 최근 (E02) ----------
export function RecentTab() {
  const { me } = useSession();
  const nav = useNav();
  const [items, setItems] = useState<AnalysisHistoryItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!me) return;
    api
      .listHistory()
      .then(setItems)
      .catch(() => setError('최근 추천을 불러오지 못했어요.'));
  }, [me]);

  if (!me) return <GuestRecent onLogin={() => nav.push('login')} />;
  return (
    <div className="sp-scroll sp-pad">
      <h1 className="sp-title">최근 추천 상품</h1>
      <p className="sp-desc">다시 보고 싶은 추천을 모아뒀어요.</p>
      {error && <p className="sp-error">{error}</p>}
      {items && items.length === 0 && <p className="kp-muted-center">아직 추천 기록이 없어요.</p>}
      {items?.map((h, i) => (
        <div key={h.analysis_id}>
          {i > 0 && <hr className="kp-divider" />}
          <div className="kp-offer">
            <div className="kp-offer-main">
              <div className="kp-thumb">{h.card.image_kind === 'food' ? <IconFood size={26} /> : <IconPrinter size={28} />}</div>
              <div className="kp-offer-text">
                <div className="kp-offer-name">{h.card.name}</div>
                <div className="kp-offer-sub">{h.card.subtitle}</div>
                <div className="kp-price">{formatPrice(h.card.price, h.card.currency)}</div>
              </div>
              <button className="kp-icon-btn kp-link" onClick={() => openUrl(h.card.url)} aria-label={`${h.card.name} 판매처로 이동`}>
                <IconExternal size={20} />
              </button>
            </div>
            <p className="kp-reason">AI · {h.card.reason}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

// 비회원 시작 화면: 기록이 없으니 로그인 유도 + 추천 상품(제휴 상품) 목록.
// 제휴 상품은 표시광고 규정·명세 10.3에 따라 '제휴' 표시를 반드시 남긴다.
function GuestRecent({ onLogin }: { onLogin: () => void }) {
  const [items, setItems] = useState<OfferCard[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    api
      .listFeatured()
      .then(setItems)
      .catch(() => setError(true));
  }, []);

  return (
    <div className="sp-scroll sp-pad">
      <button className="sp-login-banner" onClick={onLogin}>
        <span>
          <strong>로그인하고 나만의 추천을 받아보세요</strong>
          <small>알레르기 설정과 추천 기록 저장은 로그인 후 이용할 수 있어요.</small>
        </span>
        <span className="sp-login-banner-cta">로그인</span>
      </button>
      <h1 className="sp-title">추천 상품</h1>
      <p className="sp-desc">꿀픽이 고른 인기 상품이에요.</p>
      {error && <p className="sp-error">추천 상품을 불러오지 못했어요.</p>}
      {items?.map((c, i) => (
        <div key={c.offer_id}>
          {i > 0 && <hr className="kp-divider" />}
          <OfferRow card={c} onOpenUrl={openUrl} />
        </div>
      ))}
      {items?.some((c) => c.affiliate) && <p className="kp-footnote">제휴 링크가 포함된 상품이에요. 구매 시 꿀픽이 판매처로부터 수수료를 받을 수 있어요.</p>}
    </div>
  );
}

// ---------- 바로가기 (E03~E06) : 이 기기(chrome.storage.local)에만 저장 ----------
export function ShortcutsTab() {
  const [list, setList] = useState<Shortcut[]>(DEFAULT_SHORTCUTS);
  const [editing, setEditing] = useState(false);
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const dragFrom = useRef<number | null>(null);

  useEffect(() => {
    void loadShortcuts().then(setList);
  }, []);

  const update = (next: Shortcut[]) => {
    setList(next);
    void saveShortcuts(next);
  };

  const remove = (id: string) => update(list.filter((s) => s.id !== id));
  const move = (from: number, to: number) => {
    if (from === to) return;
    const next = [...list];
    const [it] = next.splice(from, 1);
    next.splice(to, 0, it);
    update(next);
  };

  return (
    <div className="sp-scroll sp-pad">
      <div className="sp-title-row">
        <h1 className="sp-title">{editing ? '바로가기 편집' : '쇼핑몰 바로가기'}</h1>
        <button className={`kp-btn kp-btn-pill ${editing ? 'is-solid' : ''}`} onClick={() => setEditing(!editing)}>
          {editing ? '완료' : '편집'}
        </button>
      </div>
      <p className="sp-desc">{editing ? '−를 눌러 삭제하고, 끌어서 순서를 바꿔요.' : '자주 가는 쇼핑몰을 직접 추가하고 정리할 수 있어요.'}</p>

      <ul className="sp-shortcuts">
        {list.map((s, i) => (
          <li
            key={s.id}
            draggable={editing}
            onDragStart={() => (dragFrom.current = i)}
            onDragOver={(e) => editing && e.preventDefault()}
            onDrop={() => {
              if (dragFrom.current != null) move(dragFrom.current, i);
              dragFrom.current = null;
            }}
          >
            <button
              className={`sp-shortcut ${editing ? 'is-editing' : ''}`}
              onClick={() => !editing && openUrl(s.url)}
              aria-label={editing ? `${s.name} (끌어서 이동)` : `${s.name} 새 탭에서 열기`}
            >
              <span className="sp-shortcut-icon">{s.mark ?? s.name.trim().charAt(0)}</span>
              <span className="sp-shortcut-name">{s.name}</span>
            </button>
            {editing && (
              <button className="sp-shortcut-remove" onClick={() => remove(s.id)} aria-label={`${s.name} 삭제`}>
                <span />
              </button>
            )}
          </li>
        ))}
        <li>
          <button className="sp-shortcut" onClick={() => setAdding(true)} aria-label="바로가기 추가">
            <span className="sp-shortcut-icon is-add">
              <IconPlus size={22} />
            </span>
            <span className="sp-shortcut-name is-muted">추가</span>
          </button>
        </li>
      </ul>

      <Note>{editing ? '변경한 바로가기는 이 기기에 저장돼요.' : '바로가기를 누르면 새 탭에서 열리고, 상품 페이지에서 AI 추천이 화면에 표시돼요.'}</Note>

      {adding && (
        <AddShortcutSheet
          onCancel={() => setAdding(false)}
          onAdd={(s) => {
            update([...list, s]);
            setAdding(false);
            setNotice(`'${s.name}' 바로가기를 추가했어요.`);
          }}
        />
      )}
      {notice && <Toast message={notice} onDone={() => setNotice(null)} />}
    </div>
  );
}

function AddShortcutSheet({ onAdd, onCancel }: { onAdd: (s: Shortcut) => void; onCancel: () => void }) {
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [error, setError] = useState<string | null>(null);

  const submit = () => {
    const trimmed = name.trim();
    if (!trimmed) return setError('쇼핑몰 이름을 입력해 주세요.');
    const withScheme = /^https?:\/\//i.test(url.trim()) ? url.trim() : `https://${url.trim()}`;
    const safe = safeHttpUrl(withScheme);
    if (!url.trim() || !safe || !new URL(safe).hostname.includes('.')) return setError('올바른 주소를 입력해 주세요.');
    onAdd({ id: crypto.randomUUID(), name: trimmed.slice(0, 20), url: safe });
  };

  return (
    <div className="sp-dim" onClick={onCancel}>
      <div className="sp-sheet" role="dialog" aria-modal="true" aria-label="바로가기 추가" onClick={(e) => e.stopPropagation()}>
        <div className="sp-sheet-handle" />
        <h2>바로가기 추가</h2>
        <p className="sp-desc">쇼핑몰 이름과 주소를 입력해 주세요.</p>
        <div className="sp-field">
          <label htmlFor="sc-name">이름</label>
          <input id="sc-name" className="sp-input" placeholder="예) 오아시스마켓" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
        </div>
        <div className="sp-field">
          <label htmlFor="sc-url">주소 (URL)</label>
          <input
            id="sc-url"
            className="sp-input"
            placeholder="https://www.oasis.co.kr"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submit()}
            inputMode="url"
          />
        </div>
        {error && <p className="sp-error">{error}</p>}
        <div className="sp-dialog-actions">
          <button className="kp-btn kp-btn-outline" onClick={onCancel}>
            취소
          </button>
          <button className="kp-btn kp-btn-primary" onClick={submit}>
            추가
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------- 설정 (E07, E08) ----------
export function SettingsTab() {
  const { me, logout, setMe } = useSession();
  const nav = useNav();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const toggleUsed = async (on: boolean) => {
    if (!me) return nav.push('login');
    setSaving(true);
    try {
      setMe(await api.updateProfile({ expected_version: me.profile.version, include_used: on }));
    } catch (e) {
      setNotice(e instanceof Error ? e.message : '저장하지 못했어요.');
    } finally {
      setSaving(false);
    }
  };

  const deleteHistory = async () => {
    setConfirmDelete(false);
    try {
      await api.deleteAllHistory();
      setNotice('추천 기록 삭제를 요청했어요.');
    } catch {
      setNotice('삭제하지 못했어요. 잠시 후 다시 시도해 주세요.');
    }
  };

  return (
    <div className="sp-page">
      <div className="sp-page-body sp-pad">
        <button className="sp-account" onClick={() => nav.push(me ? 'mypage' : 'login')}>
          <span>
            <strong>{me ? me.login_id : '로그인 해 주세요.'}</strong>
            <small>{me ? '마이페이지 보기' : '로그인하면 추천 기록을 저장할 수 있어요.'}</small>
          </span>
          <span aria-hidden="true">›</span>
        </button>
        <hr className="kp-divider" />
        <div className="sp-setting">
          <span className="sp-setting-title">중고상품 포함</span>
          <Toggle label="중고상품 포함" checked={!!me?.profile.include_used} onChange={toggleUsed} disabled={saving} />
        </div>
        <p className="sp-desc sp-mt8">{me ? '켜면 관련 중고 상품을 3개까지 추천해요.' : '로그인하면 중고 상품도 함께 추천받을 수 있어요.'}</p>
        <hr className="kp-divider" />
        <RowButton onClick={() => nav.push(me ? 'support' : 'login')}>고객지원</RowButton>
        {me && (
          <RowButton danger onClick={() => void logout()}>
            로그아웃
          </RowButton>
        )}
      </div>
      {/* 기록 삭제는 회원 전용(POST /v2/me/data-deletions) */}
      {me && (
        <div className="sp-page-footer">
          <button className="kp-btn kp-btn-outline kp-btn-block sp-btn-plain" onClick={() => setConfirmDelete(true)}>
            추천 기록 전체 삭제
          </button>
        </div>
      )}
      {confirmDelete && (
        <ConfirmDialog
          title="추천 기록을 모두 삭제할까요?"
          body="분석·추천 기록이 모두 삭제되고 되돌릴 수 없어요. 결제·상담 기록은 삭제되지 않아요."
          confirmLabel="삭제"
          danger
          onConfirm={() => void deleteHistory()}
          onCancel={() => setConfirmDelete(false)}
        />
      )}
      {notice && <Toast message={notice} onDone={() => setNotice(null)} />}
    </div>
  );
}
