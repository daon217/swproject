import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { onConsentAgreed } from '../consent';
import { useSession } from '../session';
import { api } from '../shared/api';
import { todaySeoul } from '../shared/format';
import { CONSENT_VERSION, PRIVACY_CONSENT_TITLE } from '../shared/terms';
import { ApiError, type Gender } from '../shared/types';
import { AllergyPicker, BirthDateField, Button, Checkbox, ErrorText, Field, GenderSelect, H2, Page, SubHeader } from '../ui/components';
import { C } from '../ui/theme';

const LOGIN_ID_RE = /^[A-Za-z0-9]{4,16}$/;

// 회원가입 (Figma U11) — 연령 → 생년월일, 개인정보 수집·이용 동의 + 원문보기
export default function SignupScreen() {
  const { login } = useSession();
  const [form, setForm] = useState({ id: '', pw: '', pw2: '', birth: '', gender: '' });
  const [allergies, setAllergies] = useState<string[]>([]);
  const [consent, setConsent] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof form) => (v: string) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    onConsentAgreed(() => setConsent(true));
    return () => onConsentAgreed(null);
  }, []);

  const submit = async () => {
    const er: Record<string, string> = {};
    if (!LOGIN_ID_RE.test(form.id)) er.id = '영문·숫자 4~16자로 입력해 주세요.';
    if (form.pw.length < 8) er.pw = '비밀번호는 8자 이상이어야 해요.';
    if (form.pw2 !== form.pw) er.pw2 = '비밀번호가 일치하지 않아요.';
    if (form.birth && form.birth > todaySeoul()) er.birth = '미래 날짜는 입력할 수 없어요.';
    if (!consent) er.consent = '개인정보 수집 및 이용에 동의해 주세요.';
    setErrors(er);
    if (Object.keys(er).length) return;

    setBusy(true);
    try {
      await api.signup({
        login_id: form.id,
        password: form.pw,
        password_confirmation: form.pw2,
        consent_version: CONSENT_VERSION,
        consent_accepted: consent,
        allergies,
        gender: (form.gender || null) as Gender | null,
        birth_date: form.birth || null,
      });
      await login(form.id, form.pw);
      router.dismissTo('/settings');
    } catch (e) {
      if (e instanceof ApiError && e.code === 'LOGIN_ID_TAKEN') setErrors({ id: e.message });
      else setErrors({ form: e instanceof Error ? e.message : '가입하지 못했어요.' });
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={{ flex: 1 }}>
      <SubHeader title="회원가입" />
      <Page footer={<Button label="동의하고 가입하기" onPress={() => void submit()} loading={busy} />}>
        <Text style={st.heading}>나에게 맞는 추천의 시작</Text>
        <Field label="ID" placeholder="아이디 입력" autoCapitalize="none" autoComplete="username" value={form.id} onChangeText={set('id')} error={errors.id} />
        <Field label="비밀번호" placeholder="비밀번호 입력" secureTextEntry autoComplete="new-password" value={form.pw} onChangeText={set('pw')} error={errors.pw} />
        <Field label="비밀번호 확인" placeholder="비밀번호를 다시 입력하세요" secureTextEntry autoComplete="new-password" value={form.pw2} onChangeText={set('pw2')} error={errors.pw2} />
        <BirthDateField value={form.birth} onChange={set('birth')} error={errors.birth} />
        <GenderSelect value={form.gender} onChange={set('gender')} />
        <H2>알레르기 설정</H2>
        <AllergyPicker value={allergies} onChange={setAllergies} />
        <View style={st.consent}>
          <View style={{ flex: 1 }}>
            <Checkbox checked={consent} onChange={setConsent} label={`[필수] ${PRIVACY_CONSENT_TITLE}`} />
          </View>
          <Pressable onPress={() => router.push('/terms')} accessibilityRole="link" hitSlop={8}>
            <Text style={st.link}>원문보기 &gt;</Text>
          </Pressable>
        </View>
        {errors.consent && <ErrorText>{errors.consent}</ErrorText>}
        {errors.form && <ErrorText>{errors.form}</ErrorText>}
      </Page>
    </View>
  );
}

const st = StyleSheet.create({
  heading: { fontSize: 20, fontWeight: '800', color: C.text, marginBottom: 16 },
  consent: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 20 },
  link: { color: C.primary, fontWeight: '600', fontSize: 13, textDecorationLine: 'underline' },
});
