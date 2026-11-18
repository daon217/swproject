import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { api } from '../shared/api';
import { formatDate } from '../shared/format';
import { ApiError, type SubscriptionStatus } from '../shared/types';
import { AlertDialog, type Alert } from './AlertDialog';
import { Button, ConfirmDialog, Toast } from './components';
import { C } from './theme';

// 마이페이지 구독 관리(프리미엄 회원만). 자동 결제 해지 = 다음 결제만 멈추고 남은 기간은 그대로(명세 11.3).
// 해지 취소(다시 자동 결제) API는 명세에 없어 넣지 않았다.
export function SubscriptionCard() {
  const [sub, setSub] = useState<SubscriptionStatus | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [alert, setAlert] = useState<Alert>(null);
  const [toast, setToast] = useState<string | null>(null);

  const load = useCallback(() => {
    api.getSubscription().then((value) => { setSub(value); setLoadError(false); }, () => setLoadError(true));
  }, []);
  useEffect(load, [load]);

  const end = sub?.entitlement_end ? formatDate(sub.entitlement_end) : null;

  const cancel = async () => {
    setAsking(false);
    setBusy(true);
    try {
      setSub(await api.cancelRenewal(sub?.version));
      setToast('자동 결제를 해지했어요');
    } catch (e) {
      if (e instanceof ApiError && e.code === 'VERSION_CONFLICT') load();
      setAlert({ title: '해지하지 못했어요', body: e instanceof Error ? e.message : '잠시 후 다시 시도해 주세요.' });
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={st.card}>
      <Text style={st.title}>구독 관리</Text>
      {!sub && !loadError && <ActivityIndicator color={C.primary} style={{ marginVertical: 12 }} />}
      {loadError && (
        <>
          <Text style={st.meta}>구독 정보를 불러오지 못했어요.</Text>
          <Button variant="outline" label="다시 시도" onPress={load} style={{ marginTop: 12 }} />
        </>
      )}
      {sub && (
        <>
          <View style={st.row}>
            <Text style={st.plan}>꿀픽 프리미엄</Text>
            <Text style={[st.badge, sub.cancel_at_period_end && st.badgeOff]}>{sub.cancel_at_period_end ? '자동 결제 해지됨' : '이용 중'}</Text>
          </View>
          {end && <Text style={st.meta}>이용 기간 · {end}까지</Text>}
          {end && <Text style={st.meta}>{sub.cancel_at_period_end ? `${end} 이후에는 일반 회원으로 바뀌어요` : `다음 결제일 · ${end}`}</Text>}
          {!sub.cancel_at_period_end && (
            <Button variant="outline" label="자동 결제 해지" onPress={() => setAsking(true)} loading={busy} style={{ marginTop: 14 }} />
          )}
        </>
      )}
      <ConfirmDialog
        visible={asking}
        title="자동 결제를 해지할까요?"
        body={`다음 결제부터 청구되지 않아요.${end ? `\n${end}까지는 프리미엄을 계속 이용할 수 있어요.` : ''}`}
        confirmLabel="해지하기"
        cancelLabel="유지하기"
        danger
        onConfirm={() => void cancel()}
        onCancel={() => setAsking(false)}
      />
      <AlertDialog alert={alert} onClose={() => setAlert(null)} />
      <Toast message={toast} onDone={() => setToast(null)} />
    </View>
  );
}

const st = StyleSheet.create({
  card: { marginTop: 20, borderWidth: 1, borderColor: C.border, borderRadius: 12, padding: 16 },
  title: { fontSize: 15, fontWeight: '800', color: C.text, marginBottom: 10 },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  plan: { fontSize: 16, fontWeight: '700', color: C.text },
  badge: { fontSize: 12, fontWeight: '700', color: C.primary, backgroundColor: C.primarySoft, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, overflow: 'hidden' },
  badgeOff: { color: C.sub, backgroundColor: C.surfaceMuted },
  meta: { fontSize: 13, color: C.sub, marginTop: 6 },
});
