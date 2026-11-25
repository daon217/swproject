import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { allergyNotice, warningsForDomain } from '../shared/allergens';
import { formatPrice, offerSubtitle } from '../shared/format';
import type { Analysis, OfferCard, ResultSection } from '../shared/types';
import { Button } from './components';
import { IconExternal, IconFilter, IconFood, IconPrinter, IconSearch } from './icons';
import { C, R } from './theme';

// AI 추천 결과(Figma U17·U18·U20~U23·U25, 09 중고). 플로팅 확장 패널 안에서 쓴다. 확장의 ResultView와 같은 규칙.

export type AnalysisStatus = 'none' | 'analyzing' | 'done' | 'error';

interface Handlers {
  onOpenUrl: (url: string) => void;
  onPremium: () => void;
  onFilter: () => void;
  onRetry: () => void;
}

/** 이 페이지에 보여줄 알레르기 경고(식품 페이지만 백엔드 경고를 보여주고, 상품 페이지는 띄우지 않는다) */
export function visibleWarnings(a: Analysis | null) {
  return a ? warningsForDomain(a.warnings, a.selected_domain) : [];
}

/**
 * 최저가 추천: 공개된 추천 후보(중고 제외)를 가격 낮은 순으로. 가격을 모르는 상품은 맨 뒤.
 * 통화가 다르면 환율 없이 비교할 수 없으므로 원화 상품을 먼저, 해외 통화 상품은 통화별로 그 뒤에 둔다.
 */
export function lowestPriceItems(sections: ResultSection[]): OfferCard[] {
  const seen = new Set<string>();
  const items = sections.flatMap((x) => x.items).filter((c) => !seen.has(c.offer_id) && !!seen.add(c.offer_id));
  const value = (c: OfferCard) => {
    const n = Number(c.price);
    return c.price && Number.isFinite(n) ? n : Infinity;
  };
  const group = (c: OfferCard) => (!c.currency || c.currency === 'KRW' ? '' : c.currency);
  return items.sort((x, y) => group(x).localeCompare(group(y)) || value(x) - value(y));
}

export function headerLabel(a: Analysis | null): string {
  if (visibleWarnings(a).length) return '꿀픽 · 알레르기 주의';
  if (a?.premium) return '꿀픽 PREMIUM';
  return '꿀픽 · AI 추천';
}

export function OfferRow({ card, onOpenUrl, basic = false }: { card: OfferCard; onOpenUrl: (u: string) => void; basic?: boolean }) {
  return (
    <View style={st.offer}>
      <View style={st.offerMain}>
        <View style={st.thumb}>{card.image_kind === 'food' ? <IconFood size={26} color={C.primary} /> : <IconPrinter size={28} color={C.primary} />}</View>
        <View style={{ flex: 1, minWidth: 0 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            {card.affiliate && (
              <View style={st.adBadge}>
                <Text style={st.adBadgeText}>제휴</Text>
              </View>
            )}
            <Text style={[st.name, { flexShrink: 1 }]} numberOfLines={1}>
              {card.name}
            </Text>
          </View>
          <Text style={st.sub}>{offerSubtitle(card.subtitle, card.condition)}</Text>
          <Text style={st.price}>{formatPrice(card.price, card.currency)}</Text>
        </View>
        <Pressable onPress={() => onOpenUrl(card.url)} hitSlop={10} accessibilityRole="link" accessibilityLabel={`${card.name} 판매처로 이동`}>
          <IconExternal size={22} color={C.primary} />
        </Pressable>
      </View>
      <Text style={st.reason}>
        {basic ? '' : 'AI · '}{card.reason}
      </Text>
    </View>
  );
}

/** 중고·해외 추천 구역 문구(확장 ResultView와 같다). 둘 다 AI 공개 개수와 별개로 따로 보여준다. */
const EXTRA_SECTION = {
  overseas: { title: '해외 추천 상품', loading: '해외 상품 분석중입니다.', failed: '해외 상품을 불러오지 못했어요.', empty: '이 상품과 비슷한 해외 판매처 상품이 없어요.', note: '해외 판매처 상품이에요. 배송비·관세·전압(110V/220V)을 확인해 주세요.' },
  used: { title: '중고 추천 상품', loading: '중고 상품 분석중입니다.', failed: '중고 상품을 불러오지 못했어요.', empty: '지금 구매할 수 있는 중고 매물이 없어요.', note: null },
} as const;

function LockedRow({ count }: { count: number }) {
  return (
    <View style={st.locked}>
      <View style={st.lockedThumb} />
      <View>
        <Text style={st.lockedTitle}>프리미엄 추천 상품</Text>
        <Text style={st.lockedSub}>추가 추천 {count}개를 확인해 보세요</Text>
      </View>
    </View>
  );
}

function sectionTitle(sec: ResultSection, premium: boolean) {
  const n = sec.items.length;
  if (sec.kind === 'alternative') return premium ? `대체 추천 후보 ${n}개` : `대체 추천 후보 · ${n}개 공개`;
  return sec.locked_count > 0 ? `AI 추천 상품 ${n}개 공개` : `AI 추천 상품 ${n}개`;
}

export function EmptyState({ title, body, loading }: { title: string; body: string; loading?: boolean }) {
  return (
    <View style={st.empty}>
      {loading ? (
        <ActivityIndicator color={C.primary} size="large" />
      ) : (
        <View style={st.emptyIcon}>
          <IconSearch size={26} color={C.primary} />
        </View>
      )}
      <Text style={st.emptyTitle}>{title}</Text>
      <Text style={st.emptyBody}>{body}</Text>
    </View>
  );
}

export function ResultView({ status, analysis, error, ...h }: { status: AnalysisStatus; analysis: Analysis | null; error: string | null } & Handlers) {
  if (status === 'analyzing' || (status === 'done' && !analysis)) return <EmptyState loading title="화면을 분석하고 있어요" body="비슷한 상품과 가격을 찾는 중이에요." />;
  if (status === 'error')
    return (
      <View style={st.empty}>
        <Text style={st.emptyTitle}>분석에 실패했어요</Text>
        <Text style={st.emptyBody}>{error ?? '잠시 후 다시 시도해 주세요.'}</Text>
        <Button variant="outline" label="다시 시도" onPress={h.onRetry} />
      </View>
    );
  // 분석은 됐지만(상품/식품 판별됨) 비슷한 상품이 없을 때도 알레르기 경고는 반드시 보여준다.
  if (analysis?.result_kind === 'empty' && visibleWarnings(analysis).length) return <ResultBody key={analysis.analysis_id} analysis={analysis} {...h} />;
  if (analysis?.result_kind === 'empty' && analysis.selected_domain)
    return <EmptyState title="비슷한 상품을 찾지 못했어요" body="이 상품과 비슷한 추천 상품이 아직 꿀픽에 없어요. 다른 상품 페이지에서 다시 확인해 주세요." />;
  if (!analysis || analysis.result_kind === 'empty') return <EmptyState title="이 페이지에는 추천할 상품이 없어요" body="쇼핑몰 상품 페이지를 열면 꿀픽이 비슷한 상품과 더 좋은 가격을 보여드려요." />;

  return <ResultBody key={analysis.analysis_id} analysis={analysis} {...h} />;
}

function ResultBody({ analysis: a, ...h }: { analysis: Analysis } & Handlers) {
  // AI 추천(국내) 아래에 해외 → 중고 순으로 따로 보여준다.
  const main = a.sections.filter((x) => x.kind !== 'used' && x.kind !== 'overseas');
  const extras = (['overseas', 'used'] as const).flatMap((k) => a.sections.filter((x) => x.kind === k));
  const locked = main.some((x) => x.locked_count > 0);
  const f = a.applied_filter;
  const warnings = visibleWarnings(a);
  const notice = allergyNotice(warnings);
  const unread = warnings.some((w) => w.evidence === 'unknown');
  const lowest = lowestPriceItems(main);

  return (
    <View style={{ flex: 1 }}>
      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 24 }}>
        <View style={st.head}>
          <Text style={st.brand}>{headerLabel(a)}</Text>
          {a.premium && a.selected_domain === 'food' && (
            <Pressable style={st.filterBtn} onPress={h.onFilter} accessibilityRole="button">
              <IconFilter size={15} color={C.primary} />
              <Text style={{ color: C.primary, fontWeight: '700', fontSize: 13 }}>필터</Text>
            </Pressable>
          )}
        </View>
        {f && (
          <View style={st.filterChip}>
            <Text style={{ color: C.sub, fontSize: 12 }}>
              적용 중 · {[f.avoid.length ? `기피: ${f.avoid.join(', ')}` : null, f.prefer.length ? `선호: ${f.prefer.join(', ')}` : null].filter(Boolean).join(' / ')}
            </Text>
          </View>
        )}
        {notice && (
          <View style={st.warning} accessibilityRole="alert">
            <Text style={st.warningTitle}>{notice.title}</Text>
            <Text style={st.warningBody}>
              내 알레르기 · {notice.names.join(', ')}
              {notice.lines.map((l) => `\n${l}`).join('')}
            </Text>
            <Text style={st.warningNote}>구매 전 판매처의 원재료·성분 표시를 직접 확인해 주세요.</Text>
          </View>
        )}
        {!unread && (a.ingredient_status === 'not_found' || a.result_kind === 'ingredient_unknown') && (
          <View style={st.filterChip}>
            <Text style={{ color: C.sub, fontSize: 12 }}>성분 정보를 확인하지 못했어요. 안전하다는 뜻이 아니니 판매처의 원재료 표시를 확인해 주세요.</Text>
          </View>
        )}
        {/* 탭 없이 한 화면에서 스크롤: 최저가 추천 → AI 추천 → 중고 추천 */}
        <View>
          <Text style={st.sectionTitle}>{lowest.length ? `최저가 추천 상품 ${lowest.length}개` : '최저가 추천 상품'}</Text>
          {lowest.length === 0 && <Text style={st.mutedCenter}>가격을 비교할 추천 후보를 찾지 못했어요.</Text>}
          {lowest.map((c) => (
            <OfferRow key={c.offer_id} card={c} onOpenUrl={h.onOpenUrl} />
          ))}
        </View>
        {main.map((sec) => (
          <View key={sec.kind}>
            <View style={st.divider} />
            <Text style={st.sectionTitle}>{sectionTitle(sec, a.premium)}</Text>
            {sec.items.length === 0 && <Text style={st.mutedCenter}>조건에 맞는 추천 후보를 찾지 못했어요.</Text>}
            {sec.items.map((c) => (
              <OfferRow key={c.offer_id} card={c} onOpenUrl={h.onOpenUrl} />
            ))}
            {Array.from({ length: sec.locked_count }, (_, i) => (
              <LockedRow key={i} count={sec.locked_count} />
            ))}
            {!!sec.footnote && <Text style={st.footnote}>{sec.footnote}</Text>}
          </View>
        ))}
        {extras.map((sec) => {
          const t = EXTRA_SECTION[sec.kind === 'overseas' ? 'overseas' : 'used'];
          return (
            <View key={sec.kind}>
              <View style={st.divider} />
              <Text style={[st.sectionTitle, { fontSize: 16 }]}>{t.title}</Text>
              {sec.state === 'loading' && <Text style={st.mutedCenter}>{t.loading}</Text>}
              {sec.state === 'failed' && <Text style={st.mutedCenter}>{t.failed}</Text>}
              {sec.state === 'ready' && sec.items.length === 0 && <Text style={st.mutedCenter}>{t.empty}</Text>}
              {!!t.note && sec.items.length > 0 && <Text style={[st.footnote, { marginBottom: 12 }]}>{t.note}</Text>}
              {sec.items.map((c) => (
                <OfferRow key={c.offer_id} card={c} onOpenUrl={h.onOpenUrl} />
              ))}
            </View>
          );
        })}
      </ScrollView>
      {locked && (
        <View style={{ padding: 16, paddingTop: 8 }}>
          <Button label="프리미엄으로 추천 5개 보기" onPress={h.onPremium} />
        </View>
      )}
    </View>
  );
}

const st = StyleSheet.create({
  head: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', minHeight: 36, marginBottom: 6, paddingRight: 36 },
  brand: { color: C.primary, fontWeight: '800', fontSize: 16 },
  filterBtn: { flexDirection: 'row', alignItems: 'center', gap: 4, borderWidth: 1, borderColor: C.primary, borderRadius: 8, paddingHorizontal: 14, height: 32 },
  filterChip: { backgroundColor: C.primarySoft, borderRadius: 8, padding: 10, marginBottom: 12 },
  sectionTitle: { fontWeight: '700', fontSize: 14, color: C.text, marginTop: 8, marginBottom: 12 },
  offer: { marginBottom: 18 },
  offerMain: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  thumb: { width: 62, height: 70, borderRadius: 10, backgroundColor: C.primarySoft, alignItems: 'center', justifyContent: 'center' },
  name: { fontWeight: '700', fontSize: 15, color: C.text },
  adBadge: { borderWidth: 1, borderColor: C.border, borderRadius: 4, paddingHorizontal: 5, paddingVertical: 1 },
  adBadgeText: { fontSize: 10, fontWeight: '700', color: C.sub },
  sub: { fontSize: 12, color: C.sub, marginVertical: 2 },
  price: { color: C.price, fontWeight: '800', fontSize: 17 },
  reason: { fontSize: 12, color: C.sub, marginTop: 8 },
  locked: { flexDirection: 'row', alignItems: 'center', gap: 14, padding: 14, marginBottom: 12, borderRadius: R, backgroundColor: C.surfaceMuted },
  lockedThumb: { width: 42, height: 42, borderRadius: 8, backgroundColor: '#E2E6EE' },
  lockedTitle: { fontWeight: '700', color: '#4A5465', fontSize: 13 },
  lockedSub: { fontSize: 11, color: C.sub },
  footnote: { fontSize: 11, color: C.sub },
  divider: { height: 1, backgroundColor: C.border, marginVertical: 16 },
  mutedCenter: { textAlign: 'center', color: C.sub, paddingVertical: 24 },
  warning: { borderWidth: 1, borderColor: C.danger, borderRadius: 8, padding: 12, marginBottom: 16 },
  warningTitle: { color: C.danger, fontWeight: '800', fontSize: 16, marginBottom: 6 },
  warningBody: { fontSize: 13, color: C.text, lineHeight: 19 },
  warningNote: { fontSize: 11, color: C.sub, marginTop: 6 },
  empty: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32, gap: 8, minHeight: 260 },
  emptyIcon: { width: 64, height: 64, borderRadius: 16, backgroundColor: C.primarySoft, alignItems: 'center', justifyContent: 'center' },
  emptyTitle: { fontWeight: '800', fontSize: 18, color: C.text, textAlign: 'center' },
  emptyBody: { color: C.sub, fontSize: 13, textAlign: 'center', marginBottom: 8 },
});
