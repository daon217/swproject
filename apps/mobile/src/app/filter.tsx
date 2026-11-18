import { Redirect, router } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';
import { useSession } from '../session';
import { allergenLabel } from '../shared/allergens';
import { api } from '../shared/api';
import { Button, Desc, ErrorText, Field, H1, H2, Note, Page, SubHeader } from '../ui/components';

const splitList = (s: string) =>
  s
    .split(',')
    .map((x) => x.trim())
    .filter(Boolean)
    .slice(0, 10);

// 재료 필터 (Figma U22) — 프리미엄 식품 추천 전용
export default function FilterScreen() {
  const { me, loading, setMe } = useSession();
  const [avoid, setAvoid] = useState(me?.profile.ingredient_filter.avoid.join(', ') ?? '');
  const [prefer, setPrefer] = useState(me?.profile.ingredient_filter.prefer.join(', ') ?? '');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!loading && !me) return <Redirect href="/login" />;
  if (me && !me.premium) return <Redirect href="/premium" />;
  if (!me) return null;

  const apply = async () => {
    setBusy(true);
    setError(null);
    try {
      setMe(await api.updateProfile({ expected_version: me.profile.version, ingredient_filter: { avoid: splitList(avoid), prefer: splitList(prefer) } }));
      router.back();
    } catch (e) {
      setError(e instanceof Error ? e.message : '필터를 적용하지 못했어요.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={{ flex: 1 }}>
      <SubHeader title="재료 필터" />
      <Page footer={<Button label="필터 적용" onPress={() => void apply()} loading={busy} />}>
        <H1>입맛에 맞게 골라보세요</H1>
        <Desc>프리미엄 식품 추천에만 적용돼요.</Desc>
        <Field label="기피 재료" placeholder="예) 고수" value={avoid} onChangeText={setAvoid} />
        <Note>추천에서 피하고 싶은 재료를 입력해 주세요.</Note>
        <Field label="선호 재료" placeholder="예) 현미" value={prefer} onChangeText={setPrefer} />
        <Note>더 자주 추천받고 싶은 재료를 입력해 주세요.</Note>
        <Desc>여러 재료는 쉼표로 구분해 주세요.</Desc>
        <H2>선택한 알레르기 · {me.profile.allergies.length ? me.profile.allergies.map(allergenLabel).join(', ') : '없음'}</H2>
        <Note>재료 필터를 바꿔도 알레르기 설정은 유지돼요.</Note>
        {error && <ErrorText>{error}</ErrorText>}
      </Page>
    </View>
  );
}
