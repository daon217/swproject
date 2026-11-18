import { loginIdError, passwordError, signupErrors } from '../shared/validation';
import { router } from 'expo-router';
import { useEffect, useRef, useState, type ComponentRef } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { onConsentAgreed } from '../consent';
import { useSession } from '../session';
import { api } from '../shared/api';
import { todaySeoul } from '../shared/format';
import { CONSENT_VERSION, PRIVACY_CONSENT_TITLE } from '../shared/terms';
import { ApiError, type Gender } from '../shared/types';
import { AlertDialog, type Alert } from '../ui/AlertDialog';
import { AllergyPicker, BirthDateField, Button, Checkbox, ErrorText, GenderSelect, H2, Page, s as cs, SubHeader, Field } from '../ui/components';
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
  const [alert, setAlert] = useState<Alert>(null);
  /** 중복확인을 통과한 아이디. 아이디를 바꾸면 다시 확인해야 한다. */
  const [checkedId, setCheckedId] = useState<string | null>(null);
  const set = (k: keyof typeof form) => (v: string) => {
    const value = v;
    const nextForm = { ...form, [k]: value };
    setForm(nextForm);
    if (k === 'id') setCheckedId(null);
    const live = signupErrors(nextForm);
    setErrors(previous => ({ ...previous, id: nextForm.id ? live.id ?? '' : '',
      pw: nextForm.pw ? live.pw ?? '' : '', pw2: nextForm.pw2 ? live.pw2 ?? '' : '' }));
  };
  const idChecked = !!form.id && checkedId === form.id;

  const checkId = async () => {
    if (!LOGIN_ID_RE.test(form.id)) return setAlert({ title: '아이디 확인', body: '아이디는 영문·숫자 4~16자로 입력해 주세요.' });
    try {
      const { available } = await api.checkLoginId(form.id);
      if (available) {
        setCheckedId(form.id);
        setAlert({ title: '사용 가능한 아이디', body: `'${form.id}'는 사용할 수 있는 아이디예요.` });
      } else {
        setCheckedId(null);
        setAlert({ title: '아이디 중복', body: '이미 사용 중인 아이디예요. 다른 아이디를 입력해 주세요.' });
      }
    } catch (e) {
      setAlert({ title: '중복확인 실패', body: e instanceof Error ? e.message : '잠시 후 다시 시도해 주세요.' });
    }
  };

  useEffect(() => {
    onConsentAgreed(() => setConsent(true));
    return () => onConsentAgreed(null);
  }, []);

  // 필수 동의 누락: 중앙 팝업 → 확인 시 동의 항목으로 스크롤하고 강조한다.
  const scrollRef = useRef<ComponentRef<typeof ScrollView>>(null);
  const consentY = useRef(0);
  const [goToConsent, setGoToConsent] = useState(false);
  const [consentAttention, setConsentAttention] = useState(false);
  const closeAlert = () => {
    setAlert(null);
    if (goToConsent) {
      setGoToConsent(false);
      scrollRef.current?.scrollTo({ y: Math.max(0, consentY.current - 160), animated: true });
      setConsentAttention(true);
    }
  };

  const submit = async () => {
    const er: Record<string, string> = {};
    if (loginIdError(form.id)) er.id = loginIdError(form.id)!;
    if (passwordError(form.pw)) er.pw = passwordError(form.pw)!;
    if (form.pw2 !== form.pw) er.pw2 = '비밀번호가 일치하지 않아요.';
    // 비밀번호 불일치·중복확인 누락은 팝업으로 안내
    if (form.pw && form.pw2 !== form.pw) {
      setErrors(er);
      return setAlert({ title: '비밀번호 불일치', body: '비밀번호와 비밀번호 확인이 일치하지 않아요. 다시 입력해 주세요.' });
    }
    if (form.birth && form.birth > todaySeoul()) er.birth = '미래 날짜는 입력할 수 없어요.';
    if (!consent) er.consent = '개인정보 수집 및 이용에 동의해 주세요.';
    setErrors(er);
    if (Object.keys(er).some((k) => k !== 'consent')) return; // 형식 오류는 입력칸 아래 안내
    if (er.consent) {
      setGoToConsent(true);
      return setAlert({
        title: '개인정보 수집 및 이용 동의 필요',
        body: '회원가입을 하려면 [필수] 개인정보 수집 및 이용에 동의해 주세요.',
      });
    }
    if (!idChecked) return setAlert({ title: '아이디 중복확인', body: '아이디 중복확인을 먼저 해 주세요.' });

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
      if (e instanceof ApiError && e.code === 'LOGIN_ID_TAKEN') {
        setCheckedId(null);
        setAlert({ title: '아이디 중복', body: '이미 사용 중인 아이디예요. 다른 아이디를 입력해 주세요.' });
      }
      else setErrors({ form: e instanceof Error ? e.message : '가입하지 못했어요.' });
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={{ flex: 1 }}>
      <SubHeader title="회원가입" />
      <Page scrollRef={scrollRef} footer={<Button label="동의하고 가입하기" onPress={() => void submit()} loading={busy} disabled={!!loginIdError(form.id) || !!passwordError(form.pw) || form.pw !== form.pw2} />}>
        <Text style={st.heading}>나에게 맞는 추천의 시작</Text>
        <View style={cs.field}>
          <Text style={cs.label}>ID</Text>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <TextInput
              style={[cs.input, { flex: 1 }, !!errors.id && { borderColor: C.danger }]}
              placeholder="아이디 입력"
              placeholderTextColor={C.muted}
              autoCapitalize="none"
              autoComplete="username"
              value={form.id}
              onChangeText={set('id')}
              accessibilityLabel="ID"
            />
            <Pressable
              onPress={() => void checkId()}
              style={[st.checkBtn, idChecked && { borderColor: C.success }]}
              accessibilityRole="button"
            >
              <Text style={{ color: idChecked ? C.success : C.primary, fontWeight: '700', fontSize: 14 }}>{idChecked ? '확인 완료' : '중복확인'}</Text>
            </Pressable>
          </View>
          {!!errors.id && <ErrorText>{errors.id}</ErrorText>}
        </View>
        <Field label="비밀번호" placeholder="비밀번호 입력" secureTextEntry autoComplete="new-password" value={form.pw} onChangeText={set('pw')} error={errors.pw} />
        <Field label="비밀번호 확인" placeholder="비밀번호를 다시 입력하세요" secureTextEntry autoComplete="new-password" value={form.pw2} onChangeText={set('pw2')} error={errors.pw2} />
        <BirthDateField value={form.birth} onChange={set('birth')} error={errors.birth} />
        <GenderSelect value={form.gender} onChange={set('gender')} />
        <H2>알레르기 설정</H2>
        <AllergyPicker value={allergies} onChange={setAllergies} />
        <View style={[st.consent, consentAttention && !consent && st.consentAttention]} onLayout={(e) => (consentY.current = e.nativeEvent.layout.y)}>
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
      <AlertDialog alert={alert} onClose={closeAlert} />
    </View>
  );
}

const st = StyleSheet.create({
  heading: { fontSize: 20, fontWeight: '800', color: C.text, marginBottom: 16 },
  consent: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 20, borderWidth: 2, borderColor: 'transparent', borderRadius: 10, paddingHorizontal: 8 },
  consentAttention: { borderColor: C.danger, backgroundColor: '#FFF1F1' },
  link: { color: C.primary, fontWeight: '600', fontSize: 13, textDecorationLine: 'underline' },
  checkBtn: { height: 48, paddingHorizontal: 14, borderRadius: 10, borderWidth: 1, borderColor: C.border, alignItems: 'center', justifyContent: 'center' },
});
