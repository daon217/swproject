import { router, useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { openInBrowser } from '../../browserBus';
import { useSession } from '../../session';
import { api } from '../../shared/api';
import type { AnalysisHistoryItem, OfferCard } from '../../shared/types';
import { Desc, ErrorText, H1 } from '../../ui/components';
import { OfferRow } from '../../ui/ResultView';
import { C } from '../../ui/theme';

// 시작 화면 · 최근 추천 (Figma U01·U02)
// 비회원은 기록이 없으므로 로그인 유도 안내 + 추천 상품(제휴 상품) 목록을 보여준다.
export default function RecentScreen() {
  const insets = useSafeAreaInsets();
  const { me } = useSession();
  const [items, setItems] = useState<AnalysisHistoryItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useFocusEffect(
    useCallback(() => {
      if (!me) return;
      api
        .listHistory()
        .then((h) => {
          setItems(h);
          setError(null);
        })
        .catch(() => setError('최근 추천을 불러오지 못했어요.'));
    }, [me]),
  );

  return (
    <View style={[st.root, { paddingTop: insets.top }]}>
      <Text style={st.title}>꿀픽</Text>
      {!me ? (
        <GuestHome />
      ) : (
        <ScrollView contentContainerStyle={{ padding: 24 }}>
          <H1>최근 추천 상품</H1>
          <Desc>다시 보고 싶은 추천을 모아뒀어요.</Desc>
          {error && <ErrorText>{error}</ErrorText>}
          {items?.length === 0 && <Text style={st.empty}>아직 추천 기록이 없어요.</Text>}
          {items?.map((h, i) => (
            <View key={h.analysis_id}>
              {i > 0 && <View style={st.divider} />}
              <OfferRow card={h.card} onOpenUrl={openInBrowser} />
            </View>
          ))}
        </ScrollView>
      )}
    </View>
  );
}

// 제휴 상품은 표시광고 규정·명세 10.3에 따라 '제휴' 표시를 반드시 남긴다.
function GuestHome() {
  const [items, setItems] = useState<OfferCard[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    api
      .listFeatured()
      .then(setItems)
      .catch(() => setError(true));
  }, []);

  return (
    <ScrollView contentContainerStyle={{ padding: 24 }}>
      <Pressable style={st.banner} onPress={() => router.push('/login')} accessibilityRole="button" accessibilityLabel="로그인하고 나만의 추천 받기">
        <View style={{ flex: 1 }}>
          <Text style={st.bannerTitle}>로그인하고 나만의 추천을 받아보세요</Text>
          <Text style={st.bannerSub}>알레르기 설정과 추천 기록 저장은 로그인 후 이용할 수 있어요.</Text>
        </View>
        <View style={st.bannerCta}>
          <Text style={{ color: '#fff', fontWeight: '700', fontSize: 13 }}>로그인</Text>
        </View>
      </Pressable>
      <H1>추천 상품</H1>
      <Desc>꿀픽이 고른 인기 상품이에요.</Desc>
      {error && <ErrorText>추천 상품을 불러오지 못했어요.</ErrorText>}
      {items?.map((c, i) => (
        <View key={c.offer_id}>
          {i > 0 && <View style={st.divider} />}
          <OfferRow card={c} onOpenUrl={openInBrowser} />
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
