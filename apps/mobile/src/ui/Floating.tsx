import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { allergenLabel } from '../shared/allergens';
import { formatPrice } from '../shared/format';
import type { PageAnalysis } from '../usePageAnalysis';
import { IconClose, IconWarning } from './icons';
import { ResultView } from './ResultView';
import { C } from './theme';

// 플로팅 결과(Figma U16~U25): 축소 카드 → 눌러서 확장 → X로 축소, 축소 카드의 ×로 닫기(명세 REQ-UI-009~011).

type Mode = 'compact' | 'expanded' | 'closed';

export function Floating({
  page,
  onOpenUrl,
  onPremium,
  onFilter,
  onRetry,
}: {
  page: PageAnalysis;
  onOpenUrl: (url: string) => void;
  onPremium: () => void;
  onFilter: () => void;
  onRetry: () => void;
}) {
  const [mode, setMode] = useState<Mode>('compact');
  useEffect(() => setMode('compact'), [page.pageSessionId]);

  const a = page.status === 'done' ? page.analysis : null;
  if (mode === 'closed' || !a || a.result_kind !== 'recommendation') return null;

  if (mode === 'expanded') {
    return (
      <View style={st.panel} accessibilityViewIsModal>
        <Pressable style={st.panelClose} onPress={() => setMode('compact')} accessibilityLabel="축소" hitSlop={10}>
          <IconClose size={22} color={C.sub} />
        </Pressable>
        <ResultView status={page.status} analysis={a} error={page.error} onOpenUrl={onOpenUrl} onPremium={onPremium} onFilter={onFilter} onRetry={onRetry} />
      </View>
    );
  }

  const warning = a.warnings[0];
  const first = a.sections.find((x) => x.kind !== 'used')?.items[0];
  if (!warning && !first) return null;

  return (
    <View style={st.compactWrap}>
      <Pressable
        style={[st.compact, warning && st.compactAlert]}
        onPress={() => setMode('expanded')}
        accessibilityRole="button"
        accessibilityLabel={warning ? `${allergenLabel(warning.allergen)} 알레르기 주의. 눌러서 대체 상품 보기` : '꿀픽 추천. 눌러서 추천 더 보기'}
      >
        {warning ? (
          <>
            <IconWarning size={22} color={C.danger} />
            <Text style={st.alertTitle}>{allergenLabel(warning.allergen)} 알레르기 주의</Text>
            <Text style={st.alertBody}>{warning.message}{'\n'}구매 전 성분표를 확인해 주세요.</Text>
            <Text style={[st.hint, { color: C.primary }]}>눌러서 대체 상품 보기</Text>
          </>
        ) : (
          first && (
            <>
              <Text style={st.label}>꿀픽 추천</Text>
              <Text style={st.name} numberOfLines={1}>
                {first.name}
              </Text>
              <Text style={st.price}>{formatPrice(first.price, first.currency)}</Text>
              <Text style={st.hint}>눌러서 추천 더 보기</Text>
            </>
          )
        )}
      </Pressable>
      <Pressable style={st.close} onPress={() => setMode('closed')} accessibilityLabel="꿀픽 추천 닫기" hitSlop={8}>
        <IconClose size={12} color={C.sub} strokeWidth={3} />
      </Pressable>
    </View>
  );
}

const shadow = { shadowColor: '#1A2233', shadowOpacity: 0.16, shadowRadius: 16, shadowOffset: { width: 0, height: 6 }, elevation: 8 };

const st = StyleSheet.create({
  compactWrap: { position: 'absolute', top: 96, right: 12 },
  compact: { width: 206, padding: 14, borderRadius: 14, backgroundColor: C.surface, borderWidth: 1, borderColor: C.border, ...shadow },
  compactAlert: { width: 238, backgroundColor: C.primarySoft, borderColor: '#D7DEEF' },
  label: { color: C.primary, fontWeight: '800', fontSize: 13, marginBottom: 8 },
  name: { fontWeight: '800', fontSize: 15, color: C.text },
  price: { color: C.price, fontWeight: '800', fontSize: 18, marginTop: 4 },
  hint: { fontSize: 12, color: C.sub, marginTop: 8 },
  alertTitle: { color: C.danger, fontWeight: '800', fontSize: 14, marginTop: 6 },
  alertBody: { fontSize: 12, color: C.text, marginTop: 4, lineHeight: 17 },
  close: { position: 'absolute', top: -8, right: -8, width: 24, height: 24, borderRadius: 12, backgroundColor: C.surface, borderWidth: 1, borderColor: C.border, alignItems: 'center', justifyContent: 'center', ...shadow },
  panel: { position: 'absolute', top: 96, left: 12, right: 12, bottom: 12, maxHeight: 560, backgroundColor: C.surface, borderRadius: 18, borderWidth: 1, borderColor: C.border, overflow: 'hidden', ...shadow },
  panelClose: { position: 'absolute', top: 16, right: 14, zIndex: 1 },
});
