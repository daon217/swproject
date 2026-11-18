import { useEffect, useState } from 'react';
import { allergenLabel } from '../allergens';
import { formatPrice } from '../format';
import type { TabState } from '../messages';
import type { Analysis, OfferCard, ResultSection } from '../types';
import { IconExternal, IconFilter, IconFood, IconPrinter, IconSearch, IconSparkle } from './icons';

// AI 추천 결과 화면(Figma E16·E17·E19~E22·E24~E27). 사이드 패널과 인페이지 플로팅이 함께 쓴다.

interface Handlers {
  onOpenUrl: (url: string) => void;
  onPremium: () => void;
  onFilter: () => void;
  onRetry: () => void;
}

export function OfferRow({ card, onOpenUrl }: { card: OfferCard; onOpenUrl: (url: string) => void }) {
  return (
    <div className="kp-offer">
      <div className="kp-offer-main">
        <div className="kp-thumb" aria-hidden="true">
          {card.image_kind === 'food' ? <IconFood size={26} /> : <IconPrinter size={28} />}
        </div>
        <div className="kp-offer-text">
          <div className="kp-offer-name">
            {card.affiliate && <span className="kp-ad-badge">제휴</span>}
            {card.name}
          </div>
          <div className="kp-offer-sub">{card.subtitle}</div>
          <div className="kp-price">{formatPrice(card.price, card.currency)}</div>
        </div>
        <button className="kp-icon-btn kp-link" onClick={() => onOpenUrl(card.url)} aria-label={`${card.name} 판매처로 이동`}>
          <IconExternal size={20} />
        </button>
      </div>
      <p className="kp-reason">
        AI · {card.reason}

      </p>
    </div>
  );
}

function LockedRow({ count }: { count: number }) {
  return (
    <div className="kp-locked">
      <div className="kp-locked-thumb" />
      <div>
        <div className="kp-locked-title">프리미엄 추천 상품</div>
        <div className="kp-locked-sub">추가 추천 {count}개를 확인해 보세요</div>
      </div>
    </div>
  );
}

function sectionTitle(s: ResultSection, premium: boolean): string {
  const shown = s.items.length;
  if (s.kind === 'alternative') return premium ? `대체 추천 후보 ${shown}개` : `대체 추천 후보 · ${shown}개 공개`;
  if (s.locked_count > 0) return `AI 추천 상품 ${shown}개 공개`;
  return `AI 추천 상품 ${shown}개`;
}

function MainSection({ s, premium, onOpenUrl }: { s: ResultSection; premium: boolean; onOpenUrl: (u: string) => void }) {
  return (
    <section>
      <h3 className="kp-section-title">{sectionTitle(s, premium)}</h3>
      {s.items.length === 0 && <p className="kp-muted-center">조건에 맞는 추천 후보를 찾지 못했어요.</p>}
      {s.items.map((c) => (
        <OfferRow key={c.offer_id} card={c} onOpenUrl={onOpenUrl} />
      ))}
      {Array.from({ length: s.locked_count }, (_, i) => (
        <LockedRow key={i} count={s.locked_count} />
      ))}
      {s.footnote && <p className="kp-footnote">{s.footnote}</p>}
    </section>
  );
}

function UsedSection({ s, onOpenUrl }: { s: ResultSection; onOpenUrl: (u: string) => void }) {
  return (
    <section className="kp-used">
      <h3 className="kp-section-title kp-section-title-lg">중고 추천 상품</h3>
      {s.state === 'loading' && <p className="kp-muted-center">중고 상품 분석중입니다.</p>}
      {s.state === 'failed' && <p className="kp-muted-center">중고 상품을 불러오지 못했어요.</p>}
      {s.state === 'ready' && s.items.length === 0 && <p className="kp-muted-center">지금 구매할 수 있는 중고 매물이 없어요.</p>}
      {s.items.map((c) => (
        <OfferRow key={c.offer_id} card={c} onOpenUrl={onOpenUrl} />
      ))}
    </section>
  );
}

const ANALYZING_STEPS = ['상품 화면을 읽고 있어요', '비슷한 상품을 찾고 있어요', '가격을 비교하고 있어요'];

/** AI 분석 중 화면: 가운데 로딩 + 단계 안내(1.6초마다 바뀜) */
function AnalyzingView() {
  const [step, setStep] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setStep((s) => (s + 1) % ANALYZING_STEPS.length), 1600);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="kp-empty kp-analyzing" role="status" aria-live="polite">
      <div className="kp-ai-loader" aria-hidden="true">
        <span className="kp-ai-ring" />
        <IconSparkle size={28} />
      </div>
      <div className="kp-empty-title">AI가 상품을 분석하고 있어요</div>
      <p className="kp-empty-body kp-analyzing-step">{ANALYZING_STEPS[step]}</p>
      <ol className="kp-analyzing-dots" aria-hidden="true">
        {ANALYZING_STEPS.map((s, i) => (
          <li key={s} className={i === step ? 'is-on' : ''} />
        ))}
      </ol>
      <p className="kp-analyzing-note">잠시만 기다려 주세요. 보통 몇 초 걸려요.</p>
    </div>
  );
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="kp-empty">
      <div className="kp-empty-icon">
        <IconSearch size={26} />
      </div>
      <div className="kp-empty-title">{title}</div>
      <p className="kp-empty-body">{body}</p>
    </div>
  );
}

export function headerLabel(a: Analysis | null): { text: string; danger: boolean } {
  if (a?.warnings.length) return { text: '꿀픽 · 알레르기 주의', danger: false };
  if (a?.premium) return { text: '꿀픽 PREMIUM', danger: false };
  return { text: '꿀픽 · AI 추천', danger: false };
}

/** 분석 상태(로딩·완료·빈 결과·미확인·실패)를 구분해 그린다(명세 F-UI-01). */
export function ResultView({ state, ...h }: { state: TabState | null } & Handlers) {
  if (!state || state.status === 'none') {
    return <EmptyState title="이 페이지에는 추천할 상품이 없어요" body="쇼핑몰 상품 페이지를 열면 꿀픽이 비슷한 상품과 더 좋은 가격을 이 패널에 보여드려요." />;
  }
  if (state.status === 'analyzing' || (state.status === 'done' && !state.analysis)) {
    return <AnalyzingView />;
  }
  if (state.status === 'error') {
    return (
      <div className="kp-empty">
        <div className="kp-empty-title">분석에 실패했어요</div>
        <p className="kp-empty-body">{state.error ?? '잠시 후 다시 시도해 주세요.'}</p>
        <button className="kp-btn kp-btn-outline kp-btn-sm" onClick={h.onRetry}>
          다시 시도
        </button>
      </div>
    );
  }
  const a = state.analysis!;
  if (a.result_kind === 'empty') {
    return <EmptyState title="이 페이지에는 추천할 상품이 없어요" body="상품 정보를 찾지 못했어요. 상품 상세 페이지에서 다시 확인해 주세요." />;
  }
  return <ResultBody analysis={a} {...h} />;
}

function ResultBody({ analysis: a, onOpenUrl, onPremium, onFilter }: { analysis: Analysis } & Handlers) {
  const label = headerLabel(a);
  const main = a.sections.filter((s) => s.kind !== 'used');
  const used = a.sections.find((s) => s.kind === 'used');
  const locked = main.some((s) => s.locked_count > 0);
  const canFilter = a.premium && a.selected_domain === 'food';
  const f = a.applied_filter;

  return (
    <div className="kp-result">
      <div className="kp-result-scroll">
        <div className="kp-result-head">
          <span className="kp-brand">{label.text}</span>
          {canFilter && (
            <button className="kp-btn kp-btn-outline kp-btn-chip" onClick={onFilter}>
              <IconFilter size={16} /> 필터
            </button>
          )}
        </div>

        {f && (
          <div className="kp-filter-chip">
            적용 중 · {[f.avoid.length ? `기피: ${f.avoid.join(', ')}` : null, f.prefer.length ? `선호: ${f.prefer.join(', ')}` : null].filter(Boolean).join(' / ')}
          </div>
        )}

        {a.warnings.map((w) => {
          const name = allergenLabel(w.allergen);
          return (
            <div key={w.allergen} className="kp-warning" role="alert">
              <div className="kp-warning-title">{name} 알레르기 주의</div>
              <div className="kp-warning-body">
                내 알레르기 · {name}
                <br />
                {w.message}
              </div>
              <div className="kp-warning-note">구매 전 판매처의 원재료·알레르기 표시를 확인해 주세요.</div>
            </div>
          );
        })}

        {a.ingredient_status === 'not_found' || a.result_kind === 'ingredient_unknown' ? (
          <div className="kp-info">성분 정보를 확인하지 못했어요. 안전하다는 뜻이 아니니 판매처의 원재료 표시를 확인해 주세요.</div>
        ) : null}

        {main.map((s) => (
          <MainSection key={s.kind} s={s} premium={a.premium} onOpenUrl={onOpenUrl} />
        ))}

        {used && (
          <>
            <hr className="kp-divider" />
            <UsedSection s={used} onOpenUrl={onOpenUrl} />
          </>
        )}
      </div>
      {locked && (
        <div className="kp-result-cta">
          <button className="kp-btn kp-btn-primary kp-btn-block" onClick={onPremium}>
            프리미엄으로 추천 3개 보기
          </button>
        </div>
      )}
    </div>
  );
}
