// 약관 원문 화면(/terms)에서 '동의하기'를 누르면 가입 화면 체크박스에 반영한다.
type Listener = () => void;
let listener: Listener | null = null;
export function onConsentAgreed(cb: Listener | null) {
  listener = cb;
}
export function agreeConsent() {
  listener?.();
}
