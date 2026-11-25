import { useEffect, useState } from 'react';
import { allergenLabel } from '../shared/allergens';
import { formatPrice } from '../shared/format';
import type { PanelRoute, TabState } from '../shared/messages';
import { IconClose, IconWarning } from '../shared/ui/icons';

// 인페이지 플로팅 카드(Figma E15·E18·E23). 평소에는 작은 카드만 보이고,
// 누르면 사이드 패널(AI 추천 탭)이 열린다. ×로 닫으면 같은 페이지(page_session_id)에서는 다시 띄우지 않는다.
// 분석 중·실패·추천 없음도 작은 카드로 알려 준다(아무 표시 없이 사라지면 원인을 알 수 없어서).

export interface FloatingProps {
  state: TabState | null;
  onOpenPanel: (route: PanelRoute) => void;
  onRetry: () => void;
  panelOpen?: boolean;
}

export function Floating({ state, onOpenPanel, onRetry: _onRetry, panelOpen = false }: FloatingProps) {
  const [closed, setClosed] = useState(false);
  const session = state?.page_session_id;

  // 새 페이지(세션)이면 다시 카드를 보여준다.
  useEffect(() => setClosed(false), [session, panelOpen]);

  if (closed || panelOpen) return null;
  const open = () => onOpenPanel('recommend');

  if (!state || state.status === 'none') return (
    <div className="fl-wrap"><button className="fl-compact" onClick={open} aria-label="꿀픽 사이드바 열기">
      <span className="fl-compact-label">꿀픽</span><span className="fl-compact-hint">추천 상품 보기</span>
    </button><CloseButton onClick={() => setClosed(true)} /></div>
  );

  if (state.status === 'analyzing') {
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
  if (state.status === 'error') {
    return (
      <div className="fl-wrap">
        <button className="fl-compact" onClick={open} aria-label="분석하지 못했어요 - 사이드바에서 다시 시도">
          <span className="fl-compact-label is-danger">분석하지 못했어요</span>
          <span className="fl-state-body">{state.error ?? '잠시 후 다시 시도해 주세요.'}</span>
          <span className="fl-compact-hint is-link">사이드바에서 다시 시도</span>
        </button>
        <CloseButton onClick={() => setClosed(true)} />
      </div>
    );
  }

  const a = state.analysis;
  if (!a || a.result_kind !== 'recommendation') {
    return (
      <div className="fl-wrap">
        <button className="fl-compact" onClick={open} aria-label="추천할 상품을 찾지 못했어요 - 눌러서 사이드 패널에서 보기">
          <span className="fl-compact-label">꿀픽 추천</span>
          <span className="fl-state-body">{a?.result_kind === 'ingredient_unknown' ? '성분 정보를 확인하지 못했어요' : '추천할 상품을 찾지 못했어요'}</span>
        </button>
        <CloseButton onClick={() => setClosed(true)} />
      </div>
    );
  }

  const warning = a.warnings[0];

  if (warning) {
    const name = allergenLabel(warning.allergen);
    return (
      <div className="fl-wrap">
        <button className="fl-compact fl-compact-alert" onClick={open} aria-label={`${name} 알레르기 주의 - 눌러서 사이드 패널에서 대체 상품 보기`}>
          <IconWarning size={22} className="fl-alert-icon" />
          <span className="fl-alert-title">{name} 알레르기 주의</span>
          <span className="fl-alert-body">
            {warning.message}
            <br />
            구매 전 성분표를 확인해 주세요.
          </span>
          <span className="fl-compact-hint is-link">눌러서 대체 상품 보기</span>
        </button>
        <CloseButton onClick={() => setClosed(true)} />
      </div>
    );
  }

  // [임시] 페이지에서 읽은 실제 상품명·가격이 있으면 그것을 보여준다(서버 OCR 연동 전).
  const first = a.page_product ?? a.sections.find((s) => s.kind !== 'used')?.items[0];
  if (!first) return <div className="fl-wrap"><button className="fl-compact" onClick={open}>추천 상품 보기</button></div>;
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
