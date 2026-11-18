import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { allergenLabel } from '../shared/allergens';
import { formatPrice } from '../shared/format';
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

export function headerLabel(a: Analysis | null): string {
  if (a?.warnings.length) return '꿀픽 · 알레르기 주의';
  if (a?.premium) return '꿀픽 PREMIUM';
  return '꿀픽 · AI 추천';
}

export function OfferRow({ card, onOpenUrl }: { card: OfferCard; onOpenUrl: (u: string) => void }) {
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
          <Text style={st.sub}>{card.subtitle}</Text>
          <Text style={st.price}>{formatPrice(card.price, card.currency)}</Text>
        </View>
        <Pressable onPress={() => onOpenUrl(card.url)} hitSlop={10} accessibilityRole="link" accessibilityLabel={`${card.name} 판매처로 이동`}>
          <IconExternal size={22} color={C.primary} />
        </Pressable>
      </View>
      <Text style={st.reason}>
        AI · {card.reason}
      </Text>
    </View>
  );
}

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
  if (!analysis || analysis.result_kind === 'empty') return <EmptyState title="이 페이지에는 추천할 상품이 없어요" body="쇼핑몰 상품 페이지를 열면 꿀픽이 비슷한 상품과 더 좋은 가격을 보여드려요." />;

  const a = analysis;
  const main = a.sections.filter((x) => x.kind !== 'used');
  const used = a.sections.find((x) => x.kind === 'used');
  const locked = main.some((x) => x.locked_count > 0);
  const f = a.applied_filter;

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
        {a.warnings.map((w) => {
          const name = allergenLabel(w.allergen);
          return (
            <View key={w.allergen} style={st.warning} accessibilityRole="alert">
              <Text style={st.warningTitle}>{name} 알레르기 주의</Text>
              <Text style={st.warningBody}>
                내 알레르기 · {name}
                {'\n'}
                {w.message}
              </Text>
              <Text style={st.warningNote}>구매 전 판매처의 원재료·알레르기 표시를 확인해 주세요.</Text>
            </View>
          );
        })}
        {(a.ingredient_status === 'not_found' || a.result_kind === 'ingredient_unknown') && (
          <View style={st.filterChip}>
            <Text style={{ color: C.sub, fontSize: 12 }}>성분 정보를 확인하지 못했어요. 안전하다는 뜻이 아니니 판매처의 원재료 표시를 확인해 주세요.</Text>
          </View>
        )}
        {main.map((sec) => (
          <View key={sec.kind}>
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
        {used && (
          <View>
            <View style={st.divider} />
            <Text style={[st.sectionTitle, { fontSize: 16 }]}>중고 추천 상품</Text>
            {used.state === 'loading' && <Text style={st.mutedCenter}>중고 상품 분석중입니다.</Text>}
            {used.state === 'failed' && <Text style={st.mutedCenter}>중고 상품을 불러오지 못했어요.</Text>}
            {used.state === 'ready' && used.items.length === 0 && <Text style={st.mutedCenter}>지금 구매할 수 있는 중고 매물이 없어요.</Text>}
            {used.items.map((c) => (
              <OfferRow key={c.offer_id} card={c} onOpenUrl={h.onOpenUrl} />
            ))}
          </View>
        )}
      </ScrollView>
      {locked && (
        <View style={{ padding: 16, paddingTop: 8 }}>
          <Button label="프리미엄으로 추천 3개 보기" onPress={h.onPremium} />
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
