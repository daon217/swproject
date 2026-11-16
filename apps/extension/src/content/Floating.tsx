import { useEffect, useState } from 'react';
import { allergenLabel } from '../shared/allergens';
import { formatPrice } from '../shared/format';
import type { PanelRoute, TabState } from '../shared/messages';
import { IconClose, IconWarning } from '../shared/ui/icons';

// 인페이지 플로팅 카드(Figma E15·E18·E23). 평소에는 작은 카드만 보이고,
// 누르면 사이드 패널(AI 추천 탭)이 열린다. ×로 닫으면 같은 페이지(page_session_id)에서는 다시 띄우지 않는다.

export interface FloatingProps {
  state: TabState | null;
  onOpenPanel: (route: PanelRoute) => void;
}

export function Floating({ state, onOpenPanel }: FloatingProps) {
  const [closed, setClosed] = useState(false);
  const session = state?.page_session_id;

  // 새 페이지(세션)이면 다시 카드를 보여준다.
  useEffect(() => setClosed(false), [session]);

  const a = state?.status === 'done' ? state.analysis : null;
  if (closed || !a || a.result_kind !== 'recommendation') return null;

  const open = () => onOpenPanel('recommend');
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

  const first = a.sections.find((s) => s.kind !== 'used')?.items[0];
  if (!first) return null;
  return (
    <div className="fl-wrap">
      <button className="fl-compact" onClick={open} aria-label="꿀픽 추천 - 눌러서 사이드 패널에서 보기">
        <span className="fl-compact-label">꿀픽 추천</span>
        <span className="fl-compact-name">{first.name}</span>
        <span className="fl-compact-price">{formatPrice(first.price, first.currency)}</span>
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
