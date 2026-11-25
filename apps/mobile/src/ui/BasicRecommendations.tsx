import { useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { api } from '../shared/api';
import type { OfferCard } from '../shared/types';
import { Button, Desc, ErrorText, H1 } from './components';
import { OfferRow } from './ResultView';
import { C } from './theme';

// 제휴 상품은 표시광고 규정·명세 10.3에 따라 '제휴' 표시를 반드시 남긴다.
// 비회원 추천 상품은 상품/식품 선택 없이 상품 목록을 보여준다.
const GUEST_DOMAIN = 'product';

export function BasicRecommendations({ onOpenUrl, onLogin }: { onOpenUrl: (url: string) => void; onLogin: () => void }) {
  const [items, setItems] = useState<OfferCard[] | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let alive = true;
    api.listBasic(GUEST_DOMAIN).then(rows => { if (alive) setItems(rows); })
      .catch(() => { if (alive) setError(true); });
    return () => { alive = false; };
  }, [attempt]);

  return (
    <ScrollView contentContainerStyle={{ padding: 24 }}>
      <Pressable style={st.banner} onPress={onLogin} accessibilityRole="button" accessibilityLabel="로그인하고 나만의 추천 받기">
        <View style={{ flex: 1 }}>
          <Text style={st.bannerTitle}>로그인하고 나만의 추천을 받아보세요</Text>
          <Text style={st.bannerSub}>알레르기 설정과 추천 기록 저장은 로그인 후 이용할 수 있어요.</Text>
        </View>
        <View style={st.bannerCta}>
          <Text style={{ color: '#fff', fontWeight: '700', fontSize: 13 }}>로그인</Text>
        </View>
      </Pressable>
      <H1>추천 상품</H1>
      <Desc>로그인 없이 상품을 둘러보세요. 개인 맞춤 AI 분석 결과는 아니에요.</Desc>
      {!items && !error && <Text>상품을 불러오는 중이에요.</Text>}
      {error && <><ErrorText>추천 상품을 불러오지 못했어요.</ErrorText><Button label="다시 시도" onPress={() => { setItems(null); setError(false); setAttempt(v => v + 1); }} /></>}
      {items?.length === 0 && <Text>현재 표시할 상품이 없어요. 나중에 다시 확인해 주세요.</Text>}
      {items?.map((c, i) => (
        <View key={c.offer_id}>
          {i > 0 && <View style={st.divider} />}
          <OfferRow card={c} onOpenUrl={onOpenUrl} basic />
        </View>
      ))}
      {items?.some((c) => c.affiliate) && <Text style={st.footnote}>제휴 링크가 포함된 상품이에요. 구매 시 꿀픽이 판매처로부터 수수료를 받을 수 있어요.</Text>}
    </ScrollView>
  );
}

const st = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  title: { textAlign: 'center', fontWeight: '800', fontSize: 16, color: C.text, height: 60, lineHeight: 60 },
  divider: { height: 1, backgroundColor: C.border, marginBottom: 18 },
  empty: { textAlign: 'center', color: C.sub, paddingVertical: 40 },
  banner: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: C.primarySoft, borderRadius: 14, padding: 16, marginBottom: 20 },
  bannerTitle: { fontWeight: '800', fontSize: 15, color: C.text },
  bannerSub: { fontSize: 12, color: C.sub, marginTop: 4, lineHeight: 17 },
  bannerCta: { backgroundColor: C.primary, borderRadius: 999, paddingHorizontal: 14, paddingVertical: 8 },
  footnote: { fontSize: 11, color: C.sub, lineHeight: 16 },
});
