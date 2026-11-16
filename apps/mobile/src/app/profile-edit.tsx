import { Redirect, router, usePreventRemove } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { Text, View } from 'react-native';
import { useSession } from '../session';
import { api } from '../shared/api';
import { todaySeoul } from '../shared/format';
import { ApiError, type Gender } from '../shared/types';
import { AllergyPicker, BirthDateField, Button, ConfirmDialog, ErrorText, GenderSelect, H2, Note, Page, SubHeader, Toast } from '../ui/components';
import { C } from '../ui/theme';

// 개인정보 수정 (Figma U13) — 저장 성공 응답 후에만 완료 표시, 미저장 이탈 시 버리기/계속 편집 선택(명세 F-PROF-02)
export default function ProfileEditScreen() {
  const { me, loading, setMe, refresh } = useSession();
  const [birth, setBirth] = useState(me?.profile.birth_date ?? '');
  const [gender, setGender] = useState<string>(me?.profile.gender ?? '');
  const [allergies, setAllergies] = useState<string[]>(me?.profile.allergies ?? []);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const [discarded, setDiscarded] = useState(false);
  const repeatRef = useRef<(() => void) | null>(null);

  const dirty =
    !!me &&
    (birth !== (me.profile.birth_date ?? '') || gender !== (me.profile.gender ?? '') || [...allergies].sort().join() !== [...me.profile.allergies].sort().join());

  usePreventRemove(dirty && !discarded, ({ repeat }) => {
    repeatRef.current = repeat;
    setAsking(true);
  });
  // 버리기를 고르면 보호를 끈 뒤 막혔던 뒤로가기를 다시 실행한다.
  useEffect(() => {
    if (discarded) repeatRef.current?.();
  }, [discarded]);

  if (!loading && !me) return <Redirect href="/login" />;
  if (!me) return null;

  const save = async () => {
    if (birth && birth > todaySeoul()) return setError('미래 날짜는 입력할 수 없어요.');
    setBusy(true);
    setError(null);
    try {
      setMe(await api.updateProfile({ expected_version: me.profile.version, birth_date: birth || null, gender: (gender || null) as Gender | null, allergies }));
      setToast('변경사항을 저장했어요.');
    } catch (e) {
      setError(e instanceof Error ? e.message : '저장하지 못했어요.');
      if (e instanceof ApiError && e.status === 409) void refresh();
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={{ flex: 1 }}>
      <SubHeader title="개인정보 수정" />
      <Page footer={<Button label="변경사항 저장" onPress={() => void save()} loading={busy} disabled={!dirty} />}>
        <Text style={{ fontSize: 20, fontWeight: '800', color: C.text, marginBottom: 16 }}>내 추천 정보를 관리해요</Text>
        <Button variant="outline" label="비밀번호 변경" onPress={() => router.push('/password')} style={{ marginBottom: 16 }} />
        <BirthDateField value={birth} onChange={setBirth} />
        <GenderSelect value={gender} onChange={setGender} />
        <H2>알레르기 설정</H2>
        <AllergyPicker value={allergies} onChange={setAllergies} />
        <Note>알레르기 선택 항목은 회원가입과 동일해요. 저장한 내용은 다음 추천부터 반영돼요.</Note>
        {error && <ErrorText>{error}</ErrorText>}
      </Page>
      <ConfirmDialog
        visible={asking}
        title="저장하지 않고 나갈까요?"
        body="변경한 내용이 저장되지 않았어요."
        confirmLabel="버리고 나가기"
        cancelLabel="계속 편집"
        onConfirm={() => {
          setAsking(false);
          setDiscarded(true);
        }}
        onCancel={() => setAsking(false)}
      />
      <Toast message={toast} onDone={() => setToast(null)} />
    </View>
  );
}
