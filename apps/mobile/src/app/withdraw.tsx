import { Redirect, router } from 'expo-router';
import { useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useSession } from '../session';
import { api } from '../shared/api';
import { formatDate } from '../shared/format';
import { ApiError } from '../shared/types';
import { AlertDialog, type Alert } from '../ui/AlertDialog';
import { Button, Checkbox, ConfirmDialog, Field, H1, Page, SubHeader } from '../ui/components';
import { C } from '../ui/theme';

// 회원 탈퇴(명세 14.3). 비밀번호로 본인을 다시 확인하고 탈퇴를 접수한다.
// 접수 즉시 로그인이 끊기고 실제 삭제는 서버에서 차례로 진행된다. 결제 기록 일부는 법정 보관.
// 남은 프리미엄 기간 환불 여부는 운영 정책 미확정이라 안내하지 않는다.

const DELETED = ['계정(아이디·비밀번호)', '프로필·알레르기·필터 설정', '추천 기록', '고객지원 상담 내역'];
const KEPT = ['결제 기록: 관계 법령에 따라 정해진 기간 동안 분리 보관 후 파기'];

export default function WithdrawScreen() {
  const { me, loading, logout } = useSession();
  const [pw, setPw] = useState('');
  const [agree, setAgree] = useState(false);
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [alert, setAlert] = useState<Alert>(null);
  const [done, setDone] = useState(false);
  const [premiumEnd, setPremiumEnd] = useState<string | null>(null);

  useEffect(() => {
    if (!me?.premium) return;
    api.getSubscription().then((s) => setPremiumEnd(s.active ? s.entitlement_end : null), () => undefined);
  }, [me?.premium]);

  if (!done && !loading && !me) return <Redirect href="/login" />;

  const submit = async () => {
    setAsking(false);
    setBusy(true);
    try {
      await api.deleteAccount(pw);
      setDone(true);
      setAlert({ title: '탈퇴가 접수됐어요', body: '그동안 꿀픽을 이용해 주셔서 감사해요.\n개인 정보는 차례로 삭제돼요.' });
    } catch (e) {
      if (e instanceof ApiError && e.code === 'WRONG_PASSWORD') setAlert({ title: '비밀번호 불일치', body: '비밀번호가 맞지 않아요. 다시 입력해 주세요.' });
      else setAlert({ title: '탈퇴하지 못했어요', body: e instanceof Error ? e.message : '잠시 후 다시 시도해 주세요.' });
    } finally {
      setBusy(false);
    }
  };

  const closeAlert = async () => {
    setAlert(null);
    if (!done) return;
    await logout();
    router.dismissTo('/');
  };

  return (
    <View style={{ flex: 1 }}>
      <SubHeader title="회원 탈퇴" />
      <Page footer={<Button variant="danger" label="탈퇴하기" onPress={() => setAsking(true)} disabled={!agree || !pw || done} loading={busy} />}>
        <H1>탈퇴하기 전에 확인해 주세요</H1>
        {premiumEnd && (
          <View style={st.warn}>
            <Text style={st.warnTitle}>프리미엄 이용 기간이 남아 있어요</Text>
            <Text style={st.warnBody}>{formatDate(premiumEnd)}까지 남은 기간도 탈퇴와 함께 사라지고, 자동 결제도 멈춰요.</Text>
          </View>
        )}
        <Text style={st.h}>삭제되는 정보</Text>
        {DELETED.map((t) => (
          <Text key={t} style={st.li}>
            · {t}
          </Text>
        ))}
        <Text style={st.h}>보관되는 정보</Text>
        {KEPT.map((t) => (
          <Text key={t} style={st.li}>
            · {t}
          </Text>
        ))}
        <Text style={[st.li, { marginTop: 8 }]}>탈퇴 후에는 같은 아이디의 정보를 되살릴 수 없어요.</Text>
        <View style={{ height: 20 }} />
        <Field label="비밀번호 확인" placeholder="현재 비밀번호 입력" secureTextEntry autoComplete="current-password" value={pw} onChangeText={setPw} />
        <Checkbox checked={agree} onChange={setAgree} label="안내 사항을 모두 확인했고 탈퇴에 동의해요" />
      </Page>
      <ConfirmDialog
        visible={asking}
        title="정말 탈퇴할까요?"
        body="탈퇴하면 되돌릴 수 없어요."
        confirmLabel="탈퇴하기"
        cancelLabel="취소"
        danger
        onConfirm={() => void submit()}
        onCancel={() => setAsking(false)}
      />
      <AlertDialog alert={alert} onClose={() => void closeAlert()} />
    </View>
  );
}

const st = StyleSheet.create({
  warn: { backgroundColor: '#FFF1F1', borderRadius: 10, padding: 14, marginBottom: 8 },
  warnTitle: { color: C.danger, fontWeight: '800', fontSize: 14 },
  warnBody: { color: C.text, fontSize: 13, marginTop: 4, lineHeight: 19 },
  h: { fontSize: 15, fontWeight: '800', color: C.text, marginTop: 18, marginBottom: 6 },
  li: { fontSize: 14, color: C.sub, lineHeight: 22 },
});
