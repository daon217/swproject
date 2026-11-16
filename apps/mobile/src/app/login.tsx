import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { useSession } from '../session';
import { Button, Desc, ErrorText, Field, H1, Note, Page, SubHeader } from '../ui/components';
import { C } from '../ui/theme';

// 로그인 (Figma U10)
export default function LoginScreen() {
  const { login } = useSession();
  const [id, setId] = useState('');
  const [pw, setPw] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!id || !pw) return setError('아이디와 비밀번호를 입력해 주세요.');
    setBusy(true);
    setError(null);
    try {
      await login(id.trim(), pw);
      router.back();
    } catch (e) {
      setError(e instanceof Error ? e.message : '로그인하지 못했어요.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={{ flex: 1 }}>
      <SubHeader title="로그인" />
      <Page>
        <H1>반가워요!</H1>
        <Desc>로그인하고 나만의 추천을 관리하세요.</Desc>
        <Field label="ID" placeholder="아이디 입력" autoCapitalize="none" autoComplete="username" value={id} onChangeText={setId} />
        <Field label="PW" placeholder="비밀번호 입력" secureTextEntry autoComplete="current-password" value={pw} onChangeText={setPw} onSubmitEditing={() => void submit()} />
        {error && <ErrorText>{error}</ErrorText>}
        <Button label="로그인" onPress={() => void submit()} loading={busy} style={{ marginTop: 8 }} />
        <Button variant="outline" label="회원가입" onPress={() => router.replace('/signup')} style={{ marginTop: 16 }} />
        <Note>로그인하면 알레르기 설정과 나만의 추천 기록을 관리할 수 있어요.</Note>
        <Pressable onPress={() => router.back()} accessibilityRole="button">
          <Text style={{ color: C.primary, fontWeight: '600' }}>로그인 없이 둘러보기</Text>
        </Pressable>
      </Page>
    </View>
  );
}
