import { Redirect, router } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { requestReanalyze, useSession } from '../session';
import { api } from '../shared/api';
import { formatPrice } from '../shared/format';
import { uuid } from '../shared/platform';
import type { PaymentMethod, SubscriptionPlan } from '../shared/types';
import { Button, Checkbox, ConfirmDialog, Desc, H2, Page, SubHeader } from '../ui/components';
import { C } from '../ui/theme';

// 결제수단 선택 (Figma U30) · 결제 오류 (U32)
// 실제 VAN/PG는 연결하지 않고 흐름 형식만 구현. 완료 여부는 구독(권한) 조회로 확정한다.
const METHODS: { id: PaymentMethod; label: string }[] = [
  { id: 'card', label: '신용카드 결제' },
  { id: 'bank_transfer', label: '무통장 입금' },
];
const EASY: { id: PaymentMethod; label: string; mark: string; bg: string; fg: string }[] = [
  { id: 'naverpay', label: '네이버페이', mark: 'N pay', bg: '#03C75A', fg: '#fff' },
  { id: 'kakaopay', label: '카카오페이', mark: 'pay', bg: '#FEE500', fg: '#191919' },
  { id: 'tosspay', label: '토스페이', mark: 'toss pay', bg: 'transparent', fg: '#0064FF' },
];

export default function PaymentScreen() {
  const { me, loading, refresh } = useSession();
  const [plan, setPlan] = useState<SubscriptionPlan | null>(null);
  const [method, setMethod] = useState<PaymentMethod | null>(null);
  const [agree, setAgree] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [paymentMessage, setPaymentMessage] = useState('');
  const idemKey = useRef(uuid()); // 같은 결제 시도의 재요청이 중복 결제가 되지 않게

  useEffect(() => {
    api.listPlans().then((p) => setPlan(p[0] ?? null)).catch(() => setPlan(null));
  }, []);
  if (!loading && !me) return <Redirect href="/login" />;

  const pay = async () => {
    if (!plan || !method || !agree) return;
    setBusy(true);
    try {
      const payment = await api.createSubscription(plan.plan_id, method, idemKey.current);
      if (payment.status === 'pending') {
        setPaymentMessage('결제 결과를 확인 중입니다. 같은 요청으로 다시 확인해 주세요.');
        return;
      }
      const sub = await api.getSubscription(); // 리다이렉트 성공만으로 프리미엄을 켜지 않는다
      if (!sub.active) throw new Error('not active');
      await refresh();
      requestReanalyze();
      router.replace('/payment-done');
    } catch (error) {
      setPaymentMessage(error instanceof Error ? error.message : '결제 결과를 확인하지 못했어요.');
      setFailed(true);
      // 연결 오류 시에도 같은 멱등 키로 결과를 확인한다.
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={{ flex: 1 }}>
      <SubHeader title="결제하기" />
      <Page footer={<Button label={busy ? '결제 진행 중…' : '결제하기'} onPress={() => void pay()} disabled={!plan || plan.billing_mode === 'disabled' || !method || !agree || busy} loading={busy} />}>
        <View style={st.summary}>
          <Text style={{ color: C.sub, fontSize: 13 }}>상품명</Text>
          <Text style={st.planName}>{plan?.name ?? '꿀픽 프리미엄'}</Text>
          <View style={st.priceRow}>
            <Text style={{ color: C.text }}>월 요금</Text>
            <Text style={{ fontSize: 18, fontWeight: '800', color: C.text }}>{plan?.price ? formatPrice(plan.price, plan.currency) : '확정 예정'}</Text>
          </View>
        </View>
        <Desc>{plan?.billing_mode === 'disabled' ? '결제 서비스가 아직 연결되지 않았습니다.' : plan?.billing_mode === 'mock' ? '개발용 테스트 결제입니다. 실제 청구는 발생하지 않습니다.' : ''}</Desc>
        {paymentMessage ? <Desc>{paymentMessage}</Desc> : null}
        <H2>결제수단</H2>
        <View style={{ gap: 10 }} accessibilityRole="radiogroup">
          {METHODS.map((m) => (
            <Pressable key={m.id} style={[st.method, method === m.id && st.methodOn]} onPress={() => setMethod(m.id)} accessibilityRole="radio" accessibilityState={{ checked: method === m.id }} aria-checked={method === m.id}>
              <Text style={{ color: C.primary, fontWeight: '700', fontSize: 15 }}>{m.label}</Text>
            </Pressable>
          ))}
          <View style={{ flexDirection: 'row', gap: 10 }}>
            {EASY.map((m) => (
              <Pressable key={m.id} style={[st.method, st.easy, method === m.id && st.methodOn]} onPress={() => setMethod(m.id)} accessibilityRole="radio" accessibilityLabel={m.label} accessibilityState={{ checked: method === m.id }} aria-checked={method === m.id}>
                <View style={[st.mark, { backgroundColor: m.bg }]}>
                  <Text style={{ color: m.fg, fontWeight: '900', fontSize: 14 }}>{m.mark}</Text>
                </View>
                <Text style={{ fontSize: 12, color: C.text }}>{m.label}</Text>
              </Pressable>
            ))}
          </View>
        </View>
        <View style={{ marginTop: 16 }}>
          <Checkbox checked={agree} onChange={setAgree} label="[필수] 결제 내용을 확인하고 동의합니다." />
        </View>
        <Desc>선택한 결제수단으로 결제를 진행합니다.</Desc>
      </Page>
      <ConfirmDialog
        visible={failed}
        title="결제 오류"
        body={
          <View>
            <Text style={{ fontWeight: '700', fontSize: 15, color: C.text }}>결제가 정상적으로 처리되지 않았습니다.</Text>
            <Desc>{paymentMessage}</Desc>
          </View>
        }
        confirmLabel="확인"
        cancelLabel={null}
        onConfirm={() => setFailed(false)}
      />
    </View>
  );
}

const st = StyleSheet.create({
  summary: { backgroundColor: C.primarySoft, borderRadius: 16, padding: 20 },
  planName: { fontWeight: '800', fontSize: 20, color: C.text, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: '#D7DEEF' },
  priceRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 12 },
  method: { height: 50, borderWidth: 1, borderColor: C.border, borderRadius: 12, alignItems: 'center', justifyContent: 'center', backgroundColor: C.surface },
  methodOn: { borderWidth: 2, borderColor: C.primary, backgroundColor: C.primarySoft },
  easy: { flex: 1, height: 84, gap: 8 },
  mark: { minWidth: 76, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 8 },
});
