import { Redirect, router } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';
import { useSession } from '../session';
import { allergenLabel } from '../shared/allergens';
import { ageGroupLabel, GENDER_LABEL } from '../shared/format';
import { Button, H1, H2, Page, SubHeader } from '../ui/components';
import { SubscriptionCard } from '../ui/SubscriptionCard';
import { C } from '../ui/theme';

// 마이페이지 (Figma U12)
export default function MyPageScreen() {
  const { me, loading } = useSession();
  if (!loading && !me) return <Redirect href="/login" />;
  if (!me) return null;
  const p = me.profile;
  return (
    <View style={{ flex: 1 }}>
      <SubHeader title="마이페이지" />
      <Page>
        <H1>{me.login_id}님, 안녕하세요!</H1>
        <View style={st.card}>
          <Text style={st.tag}>{me.premium ? '프리미엄 회원' : '일반 회원'}</Text>
          <Text style={st.id}>ID {me.login_id}</Text>
          <Text style={st.meta}>
            연령 {ageGroupLabel(p.birth_date)} · 성별 {p.gender ? GENDER_LABEL[p.gender] : '미입력'}
          </Text>
        </View>
        <H2>선택한 알레르기</H2>
        <View style={st.chipbox}>
          <Text style={{ color: C.sub, fontSize: 13 }}>{p.allergies.length ? p.allergies.map(allergenLabel).join(' · ') : '선택한 알레르기가 없어요'}</Text>
        </View>
        <Button variant="outline" label="개인정보 수정" onPress={() => router.push('/profile-edit')} style={{ marginTop: 16 }} />
        {me.premium ? <SubscriptionCard /> : <Button label="프리미엄 알아보기" onPress={() => router.push('/premium')} style={{ marginTop: 16 }} />}
      </Page>
    </View>
  );
}

const st = StyleSheet.create({
  card: { backgroundColor: C.primarySoft, borderRadius: 4, padding: 16 },
  tag: { color: C.primary, fontSize: 12, fontWeight: '700' },
  id: { fontWeight: '800', fontSize: 17, color: C.text, marginTop: 6 },
  meta: { color: C.sub, fontSize: 13, marginTop: 6 },
  chipbox: { backgroundColor: C.primarySoft, borderRadius: 10, padding: 14 },
});
