import { useState } from 'react';
import { allergenLabel } from '../../shared/allergens';
import { api } from '../../shared/api';
import { ageGroupLabel, GENDER_LABEL, todaySeoul } from '../../shared/format';
import { CONSENT_VERSION, PRIVACY_CONSENT_SECTIONS, PRIVACY_CONSENT_TITLE } from '../../shared/terms';
import { ApiError, type Gender } from '../../shared/types';
import { AllergyPicker, Checkbox, ConfirmDialog, Field, GenderSelect, Note, Page, SubHeader, Toast } from '../components';
import { useNav } from '../nav';
import { useSession } from '../session';

const LOGIN_ID_RE = /^[A-Za-z0-9]{4,16}$/;
/** 안내 팝업(제목·본문). null이면 닫힘 */
type Alert = { title: string; body: string } | null;

function AlertDialog({ alert, onClose }: { alert: Alert; onClose: () => void }) {
  if (!alert) return null;
  return <ConfirmDialog title={alert.title} body={alert.body} confirmLabel="확인" cancelLabel={null} onConfirm={onClose} />;
}

const errMsg = (e: unknown) => (e instanceof ApiError || e instanceof Error ? e.message : '요청을 처리하지 못했어요.');

// ---------- 로그인 (E09) ----------
export function LoginScreen() {
  const nav = useNav();
  const { login } = useSession();
  const [id, setId] = useState('');
  const [pw, setPw] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [alert, setAlert] = useState<Alert>(null);

  const submit = async () => {
    if (!id || !pw) return setError('아이디와 비밀번호를 입력해 주세요.');
    setBusy(true);
    setError(null);
    try {
      await login(id.trim(), pw);
      // 회원 화면 대신 로그인이 떠 있던 경우에는 그 화면이 그대로 이어서 보인다.
      if (nav.stack[nav.stack.length - 1] === 'login') nav.pop();
    } catch (e) {
      // 로그인 실패 안내 팝업
      if (e instanceof ApiError && e.status === 401) setAlert({ title: '로그인 실패', body: '아이디 또는 비밀번호가 일치하지 않아요. 다시 확인해 주세요.' });
      else setAlert({ title: '로그인 실패', body: errMsg(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <AlertDialog alert={alert} onClose={() => setAlert(null)} />
      <SubHeader title="로그인" />
      <Page>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <h1 className="sp-hero">반가워요!</h1>
          <p className="sp-desc">로그인하고 나만의 추천을 관리하세요.</p>
          <Field label="ID" placeholder="아이디 입력" autoComplete="username" value={id} onChange={(e) => setId(e.target.value)} />
          <Field label="PW" type="password" placeholder="비밀번호 입력" autoComplete="current-password" value={pw} onChange={(e) => setPw(e.target.value)} />
          {error && <p className="sp-error">{error}</p>}
          <button className="kp-btn kp-btn-primary kp-btn-block sp-mt8" disabled={busy}>
            로그인
          </button>
        </form>
        <button className="kp-btn kp-btn-outline kp-btn-block sp-mt16" onClick={() => nav.replace('signup')}>
          회원가입
        </button>
        <Note>로그인하면 알레르기 설정과 나만의 추천 기록을 관리할 수 있어요.</Note>
        <button className="kp-text-btn sp-mt8" onClick={() => nav.reset('recommend')}>
          로그인 없이 둘러보기
        </button>
      </Page>
    </>
  );
}

// ---------- 회원가입 (E10) : 연령 → 생년월일, 개인정보 동의 + 원문보기 ----------
export function SignupScreen() {
  const nav = useNav();
  const { login } = useSession();
  const [form, setForm] = useState({ id: '', pw: '', pw2: '', birth: '', gender: '' });
  const [allergies, setAllergies] = useState<string[]>([]);
  const [consent, setConsent] = useState(false);
  const [showTerms, setShowTerms] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [alert, setAlert] = useState<Alert>(null);
  /** 중복확인을 통과한 아이디. 아이디를 바꾸면 다시 확인해야 한다. */
  const [checkedId, setCheckedId] = useState<string | null>(null);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });

  const checkId = async () => {
    if (!LOGIN_ID_RE.test(form.id)) return setAlert({ title: '아이디 확인', body: '아이디는 영문·숫자 4~16자로 입력해 주세요.' });
    try {
      const { available } = await api.checkLoginId(form.id);
      if (available) {
        setCheckedId(form.id);
        setErrors(({ id: _id, ...rest }) => rest);
        setAlert({ title: '사용 가능한 아이디', body: `'${form.id}'는 사용할 수 있는 아이디예요.` });
      } else {
        setCheckedId(null);
        setAlert({ title: '아이디 중복', body: '이미 사용 중인 아이디예요. 다른 아이디를 입력해 주세요.' });
      }
    } catch (e) {
      setAlert({ title: '중복확인 실패', body: errMsg(e) });
    }
  };

  const validate = () => {
    const er: Record<string, string> = {};
    if (!LOGIN_ID_RE.test(form.id)) er.id = '영문·숫자 4~16자로 입력해 주세요.';
    if (form.pw.length < 8) er.pw = '비밀번호는 8자 이상이어야 해요.';
    if (form.pw2 !== form.pw) er.pw2 = '비밀번호가 일치하지 않아요.';
    if (form.birth && form.birth > todaySeoul()) er.birth = '미래 날짜는 입력할 수 없어요.';
    if (!consent) er.consent = '개인정보 수집 및 이용에 동의해 주세요.';
    setErrors(er);
    return Object.keys(er).length === 0;
  };

  const submit = async () => {
    const ok = validate();
    // 비밀번호 불일치·중복확인 누락은 팝업으로 안내
    if (form.pw && form.pw2 !== form.pw) return setAlert({ title: '비밀번호 불일치', body: '비밀번호와 비밀번호 확인이 일치하지 않아요. 다시 입력해 주세요.' });
    if (!ok) return;
    if (checkedId !== form.id) return setAlert({ title: '아이디 중복확인', body: '아이디 중복확인을 먼저 해 주세요.' });
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
      nav.reset('settings');
    } catch (e) {
      if (e instanceof ApiError && e.code === 'LOGIN_ID_TAKEN') {
        setCheckedId(null);
        setAlert({ title: '아이디 중복', body: '이미 사용 중인 아이디예요. 다른 아이디를 입력해 주세요.' });
      }
      else setErrors({ form: errMsg(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <AlertDialog alert={alert} onClose={() => setAlert(null)} />
      <SubHeader title="회원가입" />
      <Page
        footer={
          <button className="kp-btn kp-btn-primary kp-btn-block" onClick={() => void submit()} disabled={busy}>
            동의하고 가입하기
          </button>
        }
      >
        <h1 className="sp-heading">나에게 맞는 추천의 시작</h1>
        <div className="sp-field">
          <label htmlFor="signup-id">ID</label>
          <div className="sp-inline">
            <input
              id="signup-id"
              className={`sp-input ${errors.id ? 'is-error' : ''}`}
              placeholder="아이디 입력"
              autoComplete="username"
              value={form.id}
              onChange={set('id')}
              aria-invalid={!!errors.id}
            />
            <button className={`kp-btn kp-btn-outline sp-inline-btn ${checkedId === form.id && form.id ? 'is-done' : ''}`} onClick={() => void checkId()}>
              {checkedId === form.id && form.id ? '확인 완료' : '중복확인'}
            </button>
          </div>
          {errors.id && <p className="sp-error">{errors.id}</p>}
        </div>
        <Field label="비밀번호" type="password" placeholder="비밀번호 입력" autoComplete="new-password" value={form.pw} onChange={set('pw')} error={errors.pw} />
        <Field
          label="비밀번호 확인"
          type="password"
          placeholder="비밀번호를 다시 입력하세요"
          autoComplete="new-password"
          value={form.pw2}
          onChange={set('pw2')}
          error={errors.pw2}
        />
        <div className="sp-grid2">
          <Field label="생년월일" type="date" max={todaySeoul()} value={form.birth} onChange={set('birth')} error={errors.birth} />
          <GenderSelect value={form.gender} onChange={(v) => setForm({ ...form, gender: v })} />
        </div>
        <h2 className="sp-subtitle">알레르기 설정</h2>
        <AllergyPicker value={allergies} onChange={setAllergies} />

        <div className="sp-consent">
          <Checkbox checked={consent} onChange={setConsent}>
            [필수] {PRIVACY_CONSENT_TITLE}
          </Checkbox>
          <button className="kp-text-btn sp-consent-link" onClick={() => setShowTerms(true)}>
            원문보기 &gt;
          </button>
        </div>
        {errors.consent && <p className="sp-error">{errors.consent}</p>}
        {errors.form && <p className="sp-error">{errors.form}</p>}
      </Page>
      {showTerms && (
        <TermsOverlay
          onClose={() => setShowTerms(false)}
          onAgree={() => {
            setConsent(true);
            setShowTerms(false);
          }}
        />
      )}
    </>
  );
}

function TermsOverlay({ onClose, onAgree }: { onClose: () => void; onAgree: () => void }) {
  return (
    <div className="sp-overlay" role="dialog" aria-modal="true" aria-label={PRIVACY_CONSENT_TITLE}>
      <SubHeader title={PRIVACY_CONSENT_TITLE} onBack={onClose} />
      <Page
        footer={
          <button className="kp-btn kp-btn-primary kp-btn-block" onClick={onAgree}>
            동의하기
          </button>
        }
      >
        {PRIVACY_CONSENT_SECTIONS.map((s) => (
          <section key={s.heading} className="sp-terms">
            <h3>{s.heading}</h3>
            <p>{s.body}</p>
          </section>
        ))}
        <p className="sp-desc">문서 버전 {CONSENT_VERSION}</p>
      </Page>
    </div>
  );
}

// ---------- 마이페이지 (E11) ----------
export function MyPageScreen() {
  const nav = useNav();
  const { me } = useSession();
  if (!me) return null;
  const p = me.profile;
  return (
    <>
      <SubHeader title="마이페이지" />
      <Page>
        <h1 className="sp-hero">{me.login_id}님, 안녕하세요!</h1>
        <div className="sp-card">
          <div className="sp-card-tag">{me.premium ? '프리미엄 회원' : '일반 회원'}</div>
          <div className="sp-card-title">ID {me.login_id}</div>
          <div className="sp-desc">
            연령 {ageGroupLabel(p.birth_date)} · 성별 {p.gender ? GENDER_LABEL[p.gender] : '미입력'}
          </div>
        </div>
        <h2 className="sp-subtitle">선택한 알레르기</h2>
        <div className="sp-chipbox">{p.allergies.length ? p.allergies.map(allergenLabel).join(' · ') : '선택한 알레르기가 없어요'}</div>
        <button className="kp-btn kp-btn-outline kp-btn-block sp-mt16" onClick={() => nav.push('profileEdit')}>
          개인정보 수정
        </button>
        {!me.premium && (
          <button className="kp-btn kp-btn-primary kp-btn-block sp-mt16" onClick={() => nav.push('premium')}>
            프리미엄 알아보기
          </button>
        )}
      </Page>
    </>
  );
}

// ---------- 개인정보 수정 (E12) ----------
export function ProfileEditScreen() {
  const nav = useNav();
  const { me, setMe, refresh } = useSession();
  const [birth, setBirth] = useState(me?.profile.birth_date ?? '');
  const [gender, setGender] = useState<string>(me?.profile.gender ?? '');
  const [allergies, setAllergies] = useState<string[]>(me?.profile.allergies ?? []);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [saved, setSaved] = useState(false);
  if (!me) return null;

  const dirty =
    birth !== (me.profile.birth_date ?? '') ||
    gender !== (me.profile.gender ?? '') ||
    [...allergies].sort().join() !== [...me.profile.allergies].sort().join();

  const save = async () => {
    if (birth && birth > todaySeoul()) return setError('미래 날짜는 입력할 수 없어요.');
    setBusy(true);
    setError(null);
    try {
      // 저장 성공 응답을 받은 뒤에만 완료로 표시한다(명세 F-PROF-02).
      setMe(
        await api.updateProfile({
          expected_version: me.profile.version,
          birth_date: birth || null, // 비우면 명시적 null로 삭제
          gender: (gender || null) as Gender | null,
          allergies,
        }),
      );
      setSaved(true);
    } catch (e) {
      setError(errMsg(e));
      if (e instanceof ApiError && e.status === 409) void refresh();
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <SubHeader title="개인정보 수정" onBack={() => (dirty && !saved ? setLeaving(true) : nav.pop())} />
      <Page
        footer={
          <button className="kp-btn kp-btn-primary kp-btn-block" onClick={() => void save()} disabled={busy || !dirty}>
            변경사항 저장
          </button>
        }
      >
        <h1 className="sp-heading">내 추천 정보를 관리해요</h1>
        <button className="kp-btn kp-btn-outline kp-btn-block sp-mb16" onClick={() => nav.push('password')}>
          비밀번호 변경
        </button>
        <Field label="생년월일" type="date" max={todaySeoul()} value={birth} onChange={(e) => setBirth(e.target.value)} />
        <GenderSelect value={gender} onChange={setGender} />
        <h2 className="sp-subtitle">알레르기 설정</h2>
        <AllergyPicker value={allergies} onChange={setAllergies} />
        <Note>알레르기 선택 항목은 회원가입과 동일해요. 저장한 내용은 다음 추천부터 반영돼요.</Note>
        {error && <p className="sp-error">{error}</p>}
      </Page>
      {leaving && (
        <ConfirmDialog
          title="저장하지 않고 나갈까요?"
          body="변경한 내용이 저장되지 않았어요."
          confirmLabel="버리고 나가기"
          cancelLabel="계속 편집"
          onConfirm={nav.pop}
          onCancel={() => setLeaving(false)}
        />
      )}
      {saved && <Toast message="변경사항을 저장했어요." onDone={() => setSaved(false)} />}
    </>
  );
}

// ---------- 비밀번호 변경 (E13) ----------
export function PasswordScreen() {
  const nav = useNav();
  const [cur, setCur] = useState('');
  const [next, setNext] = useState('');
  const [next2, setNext2] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [alert, setAlert] = useState<Alert>(null);

  const submit = async () => {
    if (next.length < 8) return setError('새 비밀번호는 8자 이상이어야 해요.');
    if (next !== next2) return setAlert({ title: '새 비밀번호 불일치', body: '새 비밀번호와 새 비밀번호 확인이 일치하지 않아요. 다시 입력해 주세요.' });
    setBusy(true);
    setError(null);
    try {
      await api.changePassword(cur, next, next2);
      setDone(true);
    } catch (e) {
      if (e instanceof ApiError && e.code === 'WRONG_PASSWORD') setAlert({ title: '현재 비밀번호 불일치', body: '현재 비밀번호가 일치하지 않아요. 다시 확인해 주세요.' });
      else if (e instanceof ApiError && e.code === 'PASSWORD_MISMATCH') setAlert({ title: '새 비밀번호 불일치', body: '새 비밀번호와 새 비밀번호 확인이 일치하지 않아요. 다시 입력해 주세요.' });
      else setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <AlertDialog alert={alert} onClose={() => setAlert(null)} />
      <SubHeader title="비밀번호 변경" />
      <Page
        footer={
          <button className="kp-btn kp-btn-primary kp-btn-block" onClick={() => void submit()} disabled={busy || !cur || !next || !next2}>
            비밀번호 변경
          </button>
        }
      >
        <h1 className="sp-heading">새 비밀번호를 설정하세요</h1>
        <Field label="현재 비밀번호" type="password" placeholder="현재 비밀번호 입력" autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} />
        <Field label="새 비밀번호" type="password" placeholder="새 비밀번호 입력" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />
        <Field label="새 비밀번호 확인" type="password" placeholder="새 비밀번호 다시 입력" autoComplete="new-password" value={next2} onChange={(e) => setNext2(e.target.value)} />
        <Note>새 비밀번호와 확인 값이 같아야 변경할 수 있어요.</Note>
        {error && <p className="sp-error">{error}</p>}
      </Page>
      {done && <ConfirmDialog title="비밀번호를 변경했어요" body="다음 로그인부터 새 비밀번호를 사용해 주세요." confirmLabel="확인" cancelLabel={null} onConfirm={nav.pop} />}
    </>
  );
}
