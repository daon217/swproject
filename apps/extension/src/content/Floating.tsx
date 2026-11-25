import { useEffect, useState } from 'react';
import { allergyNotice, warningsForDomain } from '../shared/allergens';
import { formatPrice } from '../shared/format';
import type { PanelRoute, TabState } from '../shared/messages';
import { IconClose, IconWarning } from '../shared/ui/icons';

// 인페이지 플로팅 카드(Figma E15·E18·E23). 상품 페이지에서 작은 카드로 보이고,
// 누르면 사이드 패널(AI 추천 탭)이 열린다. ×로 닫으면 같은 페이지(page_session_id)에서는 다시 띄우지 않는다.
// 상품 페이지에서는 분석 중·실패도 작게 알린다. 상품 페이지가 아니거나 추천이 비면 띄우지 않는다. 카드는 끌어서 옮길 수 있다(drag.ts).

export interface FloatingProps {
  state: TabState | null;
  onOpenPanel: (route: PanelRoute) => void;
  onRetry: () => void;
  panelOpen?: boolean;
}

export function Floating({ state, onOpenPanel, onRetry, panelOpen = false }: FloatingProps) {
  const [closed, setClosed] = useState(false);
  const session = state?.page_session_id;

  // 새 페이지(세션)이면 다시 카드를 보여준다.
  useEffect(() => setClosed(false), [session, panelOpen]);

  if (closed || panelOpen) return null;
  const open = () => onOpenPanel('recommend');

  // 상품 페이지에서만 띄운다(분석 대상이 아니면 status가 'none'). 분석은 보통 20~40초 걸려서
  // 그동안 아무것도 안 보이면 동작하지 않는 것처럼 보이므로 '분석 중'을 작게 보여 주고,
  // 실패하면 다시 시도할 수 있게 알린다. 추천이 비었으면 띄우지 않는다.
  if (state?.status === 'analyzing') {
    return (
      <div className="fl-wrap">
        <button className="fl-compact" onClick={open} aria-label="꿀픽이 이 상품을 분석하고 있어요 - 눌러서 사이드 패널에서 보기">
          <span className="fl-state-row">
            <span className="fl-spinner" aria-hidden="true" />
            <span className="fl-compact-label">꿀픽 분석 중</span>
          </span>
          <span className="fl-compact-hint">비슷한 상품과 가격을 찾고 있어요</span>
        </button>
        <CloseButton onClick={() => setClosed(true)} />
      </div>
    );
  }
  if (state?.status === 'error') {
    return (
      <div className="fl-wrap">
        <button className="fl-compact" onClick={onRetry} aria-label="분석하지 못했어요 - 눌러서 다시 시도">
          <span className="fl-compact-label is-danger">분석하지 못했어요</span>
          <span className="fl-state-body">{state.error ?? '잠시 후 다시 시도해 주세요.'}</span>
          <span className="fl-compact-hint is-link">눌러서 다시 시도</span>
        </button>
        <CloseButton onClick={() => setClosed(true)} />
      </div>
    );
  }
  const a = state?.status === 'done' ? state.analysis : null;
  if (!a || (a.result_kind !== 'recommendation' && a.result_kind !== 'empty')) return null;
  // 국내 추천이 없으면 해외 추천이라도 보여준다(중고는 제외).
  const items = a.sections.filter((s) => s.kind !== 'used').flatMap((s) => s.items);
  // 알레르기 경고는 추천 상품이 없어도 보여준다(안전 안내). 경고도 추천도 없으면 띄우지 않는다.
  const notice = allergyNotice(warningsForDomain(a.warnings, a.selected_domain));
  if (items.length === 0 && !notice) return null;
  if (notice) {
    return (
      <div className="fl-wrap">
        <button className="fl-compact fl-compact-alert" onClick={open} aria-label={`${notice.title} - 눌러서 사이드 패널에서 ${items.length ? '대체 상품' : '자세히'} 보기`}>
          <IconWarning size={22} className="fl-alert-icon" />
          <span className="fl-alert-title">{notice.title}</span>
          <span className="fl-alert-body">
            {notice.names.length > 1 && (
              <>
                {notice.names.join(', ')}
                <br />
              </>
            )}
            {notice.lines[0]}
            <br />
            구매 전 성분표를 확인해 주세요.
          </span>
          <span className="fl-compact-hint is-link">{items.length ? '눌러서 대체 상품 보기' : '눌러서 자세히 보기'}</span>
        </button>
        <CloseButton onClick={() => setClosed(true)} />
      </div>
    );
  }

  // [임시] 페이지에서 읽은 실제 상품명·가격이 있으면 그것을 보여준다(서버 OCR 연동 전).
  const first = a.page_product ?? items[0];
  return (
    <div className="fl-wrap">
      <button className="fl-compact" onClick={open} aria-label="꿀픽 추천 - 눌러서 사이드 패널에서 보기">
        <span className="fl-compact-label">꿀픽 추천</span>
        <span className="fl-compact-name">{first.name}</span>
        {first.price && <span className="fl-compact-price">{formatPrice(first.price, first.currency)}</span>}
        <span className="fl-compact-hint">눌러서 사이드 패널에서 보기</span>
      </button>
      <CloseButton onClick={() => setClosed(true)} />
    </div>
  );
}

function CloseButton({ onClick }: { onClick: () => void }) {
  return (
    <button className="fl-close" onClick={onClick} aria-label="꿀픽 추천 닫기">
      <IconClose size={12} strokeWidth={3} />
    </button>
  );
}
