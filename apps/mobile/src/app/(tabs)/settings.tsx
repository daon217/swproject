import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useSession } from '../../session';
import { api } from '../../shared/api';
import { Button, ConfirmDialog, Desc, RowButton, Toast, Toggle } from '../../ui/components';
import { IconForward } from '../../ui/icons';
import { C } from '../../ui/theme';

// 설정 (Figma 03): 계정 · 중고상품 포함 · 고객지원. 기록 삭제는 회원 전용.
export default function SettingsScreen() {
  const insets = useSafeAreaInsets();
  const { me, logout, setMe } = useSession();
  const [saving, setSaving] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const toggleUsed = async (on: boolean) => {
    if (!me) return router.push('/login');
    setSaving(true);
    try {
      setMe(await api.updateProfile({ expected_version: me.profile.version, include_used: on }));
    } catch (e) {
      setToast(e instanceof Error ? e.message : '저장하지 못했어요.');
    } finally {
      setSaving(false);
    }
  };

  const deleteHistory = async () => {
    setConfirm(false);
    try {
      await api.deleteAllHistory();
      setToast('추천 기록 삭제를 요청했어요.');
    } catch {
      setToast('삭제하지 못했어요. 잠시 후 다시 시도해 주세요.');
    }
  };

  return (
    <View style={[st.root, { paddingTop: insets.top }]}>
      <Text style={st.title}>설정</Text>
      <ScrollView contentContainerStyle={{ padding: 24 }}>
        <Pressable style={st.account} onPress={() => router.push(me ? '/mypage' : '/login')} accessibilityRole="button">
          <View style={{ flex: 1 }}>
            <Text style={st.accountTitle}>{me ? me.login_id : '로그인 해 주세요.'}</Text>
            <Text style={st.accountSub}>{me ? '마이페이지 보기' : '로그인하면 추천 기록을 저장할 수 있어요.'}</Text>
          </View>
          <IconForward size={22} color={C.sub} />
        </Pressable>
        <View style={st.divider} />
        <View style={st.settingRow}>
          <Text style={st.settingTitle}>중고상품 포함</Text>
          <Toggle label="중고상품 포함" value={!!me?.profile.include_used} onChange={toggleUsed} disabled={saving} />
        </View>
        <Desc style={{ marginTop: 8 }}>{me ? '켜면 관련 중고 상품을 3개까지 추천해요.' : '로그인하면 중고 상품도 함께 추천받을 수 있어요.'}</Desc>
        <View style={[st.divider, { marginTop: 0 }]} />
        <RowButton label="고객지원" onPress={() => router.push(me ? '/support' : '/login')} />
        {me && <RowButton danger label="로그아웃" onPress={() => void logout()} />}
      </ScrollView>
      {me && (
        <View style={{ padding: 24, paddingTop: 8 }}>
          <Button variant="outline" label="추천 기록 전체 삭제" onPress={() => setConfirm(true)} />
        </View>
      )}
      <ConfirmDialog
        visible={confirm}
        title="추천 기록을 모두 삭제할까요?"
        body="분석·추천 기록이 모두 삭제되고 되돌릴 수 없어요. 결제·상담 기록은 삭제되지 않아요."
        confirmLabel="삭제"
        danger
        onConfirm={() => void deleteHistory()}
        onCancel={() => setConfirm(false)}
      />
      <Toast message={toast} onDone={() => setToast(null)} />
    </View>
  );
}

const st = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  title: { textAlign: 'center', fontWeight: '800', fontSize: 16, color: C.text, height: 60, lineHeight: 60 },
  account: { flexDirection: 'row', alignItems: 'center', backgroundColor: C.primarySoft, borderRadius: 14, padding: 18 },
  accountTitle: { fontWeight: '800', fontSize: 16, color: C.text },
  accountSub: { fontSize: 12, color: C.sub, marginTop: 2 },
  divider: { height: 1, backgroundColor: C.border, marginVertical: 16 },
  settingRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  settingTitle: { fontWeight: '800', fontSize: 16, color: C.text },
});
