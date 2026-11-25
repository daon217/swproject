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
