// 표시용 포맷 도우미

export function formatPrice(price: string, currency = 'KRW'): string {
  // 금액은 문자열로 받으며 부동소수 계산 없이 천 단위로 끊는다. 원화는 정수부만, 외화는 소수 2자리까지.
  const [int, dec] = price.split('.');
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  if (currency === 'KRW') return `${grouped}원`;
  const cents = dec ? `.${dec.padEnd(2, '0').slice(0, 2)}` : '';
  const symbol: Record<string, string> = { USD: '$', EUR: '€', GBP: '£', JPY: '¥' };
  return symbol[currency] ? `${symbol[currency]}${grouped}${cents}` : `${grouped}${cents} ${currency}`;
}

/** 받침 여부로 이/가, 을/를 등 조사를 고른다. */
export function josa(word: string, withBatchim: string, without: string): string {
  const last = word.charCodeAt(word.length - 1);
  if (last < 0xac00 || last > 0xd7a3) return word + without;
  return word + ((last - 0xac00) % 28 > 0 ? withBatchim : without);
}

/** Asia/Seoul 기준 오늘 날짜(YYYY-MM-DD) */
export function todaySeoul(): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' }).format(new Date());
}

/** birth_date와 Asia/Seoul 기준일로 만 나이를 계산한다(명세 F-PROF-01). 2/29생은 비윤년에 3/1 기준. */
export function ageFromBirthDate(birth: string): number | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(birth);
  if (!m) return null;
  const [ty, tm, td] = todaySeoul().split('-').map(Number);
  const by = Number(m[1]);
  const bm = Number(m[2]);
  const bd = Number(m[3]);
  let age = ty - by;
  if (tm < bm || (tm === bm && td < bd)) age -= 1;
  return age >= 0 ? age : null;
}

export function ageGroupLabel(birth: string | null): string {
  if (!birth) return '미입력';
  const age = ageFromBirthDate(birth);
  if (age == null) return '미입력';
  return age < 10 ? '10세 미만' : `${Math.floor(age / 10) * 10}대`;
}

export const GENDER_LABEL: Record<string, string> = {
  male: '남성',
  female: '여성',
  prefer_not_to_say: '응답 안 함',
};

export function formatTime(iso: string): string {
  return new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', hour: 'numeric', minute: '2-digit' }).format(new Date(iso));
}

export function formatDate(iso: string): string {
  return new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', dateStyle: 'long' }).format(new Date(iso));
}

/** 외부 이동 링크는 http(s)만 허용한다. */
export function safeHttpUrl(url: string): string | null {
  try {
    const u = new URL(url);
    return !u.username && !u.password && (u.protocol === 'https:' || u.protocol === 'http:') ? u.href : null;
  } catch {
    return null;
  }
}

/** 카드 보조 문구 + 상품 상태. unknown은 새 상품으로 보이지 않게 '상태 미확인'으로 표시한다(new는 표시 생략). */
export function offerSubtitle(subtitle: string, condition?: string | null): string {
  const label = condition === 'used' ? '중고' : condition === 'unknown' ? '상태 미확인' : '';
  return [subtitle, label].filter(Boolean).join(' · ');
}

/** 마이페이지 신체 정보 한 줄. 예: '키 170cm · 몸무게 60kg · 발 260mm' */
export function bodySizeLabel(p: { height_cm?: number | null; weight_kg?: number | null; foot_mm?: number | null }): string {
  const v = (n: number | null | undefined, unit: string) => (n === null || n === undefined ? '미입력' : `${n}${unit}`);
  return `키 ${v(p.height_cm, 'cm')} · 몸무게 ${v(p.weight_kg, 'kg')} · 발 ${v(p.foot_mm, 'mm')}`;
}
