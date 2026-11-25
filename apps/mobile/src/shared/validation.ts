// 프론트·서버 계약: ID는 영문/숫자 4~16자, 비밀번호는 8~128자.
export function loginIdError(value: string): string | undefined {
  if (/\s/.test(value)) return '아이디에는 공백을 사용할 수 없습니다.';
  if (!/^[A-Za-z0-9]{4,16}$/.test(value)) return '아이디는 영문·숫자 4~16자로 입력해 주세요.';
}
export function passwordError(value: string): string | undefined {
  const length = Array.from(value).length;
  if (length < 8) return `비밀번호는 8자 이상이어야 해요. (현재 ${length}자)`;
  if (length > 128) return '비밀번호는 128자 이하여야 해요.';
}
export function signupErrors(form: {id: string; pw: string; pw2: string}) {
  return { id: loginIdError(form.id), pw: passwordError(form.pw),
    pw2: form.pw !== form.pw2 ? '비밀번호가 일치하지 않아요.' : undefined };
}

// 키·몸무게·발 사이즈(선택). 범위는 서버 Profile·DB CHECK 제약과 같다. 빈 칸이면 null.
export interface BodySizeForm {
  height: string;
  weight: string;
  foot: string;
}
const BODY_RULES = {
  height: { min: 50, max: 250, int: false, label: '키는 50~250cm 사이로 입력해 주세요.' },
  weight: { min: 10, max: 300, int: false, label: '몸무게는 10~300kg 사이로 입력해 주세요.' },
  foot: { min: 150, max: 350, int: true, label: '발 사이즈는 150~350mm 사이로 입력해 주세요(예: 260).' },
} as const;

/** 입력값을 숫자로 바꾼다. 빈 칸이면 null, 형식이 틀리면 NaN. 키·몸무게는 소수 첫째 자리까지 */
function parseBody(value: string, int: boolean): number | null {
  const v = value.trim();
  if (!v) return null;
  if (!(int ? /^\d+$/ : /^\d+(\.\d)?$/).test(v)) return NaN;
  return Number(v);
}

export function bodySizeErrors(form: BodySizeForm): Partial<Record<keyof BodySizeForm, string>> {
  const er: Partial<Record<keyof BodySizeForm, string>> = {};
  for (const k of Object.keys(BODY_RULES) as (keyof BodySizeForm)[]) {
    const r = BODY_RULES[k];
    const n = parseBody(form[k], r.int);
    if (n !== null && !(n >= r.min && n <= r.max)) er[k] = r.label;
  }
  return er;
}

/** 저장할 값. bodySizeErrors가 비어 있을 때만 부른다. */
export function bodySizes(form: BodySizeForm): { height_cm: number | null; weight_kg: number | null; foot_mm: number | null } {
  return {
    height_cm: parseBody(form.height, false),
    weight_kg: parseBody(form.weight, false),
    foot_mm: parseBody(form.foot, true),
  };
}

/** 저장된 값을 입력칸 문자열로 */
export function bodySizeForm(p: { height_cm?: number | null; weight_kg?: number | null; foot_mm?: number | null } | null | undefined): BodySizeForm {
  const s = (n: number | null | undefined) => (n === null || n === undefined ? '' : String(n));
  return { height: s(p?.height_cm), weight: s(p?.weight_kg), foot: s(p?.foot_mm) };
}
