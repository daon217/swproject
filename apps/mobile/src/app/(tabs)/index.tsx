import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { openInBrowser } from '../../browserBus';
import { useSession } from '../../session';
import { api } from '../../shared/api';
import type { AnalysisHistoryItem } from '../../shared/types';
import { Button, Desc, ErrorText, H1 } from '../../ui/components';
import { EmptyState, OfferRow } from '../../ui/ResultView';
import { C } from '../../ui/theme';

// 최근 추천 (Figma U01·U02)
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
        <View style={{ flex: 1, justifyContent: 'center', paddingBottom: 60 }}>
          <EmptyState title="로그인하면 추천 기록이 저장돼요" body="다시 보고 싶은 추천을 이 탭에서 모아볼 수 있어요." />
          <Button label="로그인" onPress={() => router.push('/login')} style={{ marginHorizontal: 80 }} />
        </View>
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

const st = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  title: { textAlign: 'center', fontWeight: '800', fontSize: 16, color: C.text, height: 60, lineHeight: 60 },
  divider: { height: 1, backgroundColor: C.border, marginBottom: 18 },
  empty: { textAlign: 'center', color: C.sub, paddingVertical: 40 },
});
