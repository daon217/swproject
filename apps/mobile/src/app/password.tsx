import { passwordError } from '../shared/validation';
import { router } from 'expo-router';
import { useState } from 'react';
import { Text, View } from 'react-native';
import { api } from '../shared/api';
import { ApiError } from '../shared/types';
import { AlertDialog, type Alert } from '../ui/AlertDialog';
import { Button, ConfirmDialog, ErrorText, Field, Note, Page, SubHeader } from '../ui/components';
import { C } from '../ui/theme';

// 비밀번호 변경 (Figma U14)
export default function PasswordScreen() {
  const [cur, setCur] = useState('');
  const [next, setNext] = useState('');
  const [next2, setNext2] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [alert, setAlert] = useState<Alert>(null);

  const submit = async () => {
    if (passwordError(next)) return setError(passwordError(next)!);
    if (next !== next2) return setAlert({ title: '새 비밀번호 불일치', body: '새 비밀번호와 새 비밀번호 확인이 일치하지 않아요. 다시 입력해 주세요.' });
    setBusy(true);
    setError(null);
    try {
      await api.changePassword(cur, next, next2);
      setDone(true);
    } catch (e) {
      if (e instanceof ApiError && e.code === 'WRONG_PASSWORD') setAlert({ title: '현재 비밀번호 불일치', body: '현재 비밀번호가 일치하지 않아요. 다시 확인해 주세요.' });
      else if (e instanceof ApiError && e.code === 'PASSWORD_MISMATCH') setAlert({ title: '새 비밀번호 불일치', body: '새 비밀번호와 새 비밀번호 확인이 일치하지 않아요. 다시 입력해 주세요.' });
      else setError(e instanceof Error ? e.message : '변경하지 못했어요.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={{ flex: 1 }}>
      <SubHeader title="비밀번호 변경" />
      <Page footer={<Button label="비밀번호 변경" onPress={() => void submit()} loading={busy} disabled={!cur || !!passwordError(next) || next !== next2} />}>
        <Text style={{ fontSize: 20, fontWeight: '800', color: C.text, marginBottom: 16 }}>새 비밀번호를 설정하세요</Text>
        <Field label="현재 비밀번호" placeholder="현재 비밀번호 입력" secureTextEntry autoComplete="current-password" value={cur} onChangeText={setCur} />
        <Field label="새 비밀번호" placeholder="새 비밀번호 입력" secureTextEntry autoComplete="new-password" error={next ? passwordError(next) : undefined} value={next} onChangeText={setNext} />
        <Field label="새 비밀번호 확인" placeholder="새 비밀번호 다시 입력" secureTextEntry autoComplete="new-password" error={next2 && next !== next2 ? '비밀번호가 일치하지 않아요.' : undefined} value={next2} onChangeText={setNext2} />
        <Note>새 비밀번호와 확인 값이 같아야 변경할 수 있어요.</Note>
        {error && <ErrorText>{error}</ErrorText>}
      </Page>
      <AlertDialog alert={alert} onClose={() => setAlert(null)} />
      <ConfirmDialog visible={done} title="비밀번호를 변경했어요" body="다음 로그인부터 새 비밀번호를 사용해 주세요." confirmLabel="확인" cancelLabel={null} onConfirm={() => router.back()} />
    </View>
  );
}
