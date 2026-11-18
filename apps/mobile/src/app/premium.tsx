import { Redirect, router } from 'expo-router';
import { useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useSession } from '../session';
import { api } from '../shared/api';
import { formatPrice } from '../shared/format';
import type { SubscriptionPlan } from '../shared/types';
import { Button, Desc, H1, Page, SubHeader } from '../ui/components';
import { C } from '../ui/theme';

// 프리미엄 안내 (Figma U29)
export default function PremiumScreen() {
  const { me, loading } = useSession();
  const [plan, setPlan] = useState<SubscriptionPlan | null>(null);
  useEffect(() => {
    api.listPlans().then((p) => setPlan(p[0] ?? null));
  }, []);
  if (!loading && !me) return <Redirect href="/login" />;

  return (
    <View style={{ flex: 1 }}>
      <SubHeader title="꿀픽 프리미엄" />
      <Page footer={<Button label="결제하기" onPress={() => router.push('/payment')} disabled={!plan} />}>
        <Text style={st.eyebrow}>PREMIUM</Text>
        <H1 style={{ fontSize: 30, lineHeight: 40 }}>{'더 많은 선택지,\n더 나다운 추천.'}</H1>
        <Desc>잠겨 있던 추천까지 한 번에 확인하세요.</Desc>
        <View style={st.benefits}>
          {(plan?.benefits ?? []).map((b, i) => (
            <Text key={b} style={st.benefit}>
              {String(i + 1).padStart(2, '0')}  {b}
            </Text>
          ))}
        </View>
        <View style={st.price}>
          <Text style={{ color: C.sub, fontSize: 13 }}>{plan?.price ? `월 ${formatPrice(plan.price, plan.currency)}` : '구독 요금 · 결제 주기는 정책 확정 후 표시'}</Text>
        </View>
        <Desc style={{ marginTop: 16 }}>결제수단을 선택한 후 결제를 진행합니다. 결제 결과에 따라 완료 또는 오류 화면을 안내합니다.</Desc>
      </Page>
    </View>
  );
}

const st = StyleSheet.create({
  eyebrow: { color: C.primary, fontWeight: '800', fontSize: 12, marginTop: 8 },
  benefits: { backgroundColor: C.primarySoft, borderRadius: 16, padding: 20, gap: 18, marginBottom: 16 },
  benefit: { fontWeight: '800', fontSize: 15, color: C.text },
  price: { backgroundColor: C.primarySoft, borderRadius: 10, padding: 14 },
});
