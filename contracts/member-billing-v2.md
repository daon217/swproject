# 회원·구독 API 임시 계약

프론트 참고: `part/서지웅-extension`의 `51888bcc5fcea6ffcd0b8dad8ed969fb5228ad7e`.
확장 `src/shared/types.ts`, `src/shared/api/http.ts`, 회원 화면 및 모바일 결제 화면을 대조했다.
프론트는 미완성 참고본이며 이 계약도 검토용이다. 팀원 브랜치의 코드는 수정하지 않았다.

## 응답과 인증

성공: `{ "data": ..., "request_id": "..." }`. 오류: `{ "error": { "code": "...", "message": "...", "retryable": false }, "request_id": "..." }`.
회원 API는 로그인 응답의 `token`을 `Authorization: Bearer ...`로 보낸다. 수집 토큰과 회원 토큰은 서로 대체할 수 없다.
세션은 임시 7일, 서버에는 토큰 SHA-256만 저장한다. 비밀번호는 무작위 salt + scrypt(N=16384,r=8,p=1)로 저장한다.
로그아웃은 해당 세션만 폐기한다. 비밀번호 변경은 현재 세션을 제외한 다른 세션을 폐기한다.
가입·로그인·ID 중복확인은 작업별/IP별 분당 30회 제한한다. DB에는 raw IP 대신 해시된 제한 키만 남긴다.
프록시 배포 시 실제 클라이언트 IP 설정과 별도 edge 제한을 검토해야 한다.

| 메서드·경로 | 입력 / 동작 |
|---|---|
| POST `/v2/auth/signup` | login_id, password, password_confirmation, consent_version, consent_accepted=true, gender, birth_date, allergies. user_id 반환 |
| GET `/v2/auth/login-id-availability?login_id=...` | 대소문자 무시 중복 확인, available 반환 |
| POST `/v2/auth/login` | login_id, password → token, expires_in |
| POST `/v2/auth/logout` | 현재 세션 폐기, 204 |
| GET `/v2/me` | user_id, login_id, premium, profile |
| PATCH `/v2/me/profile` | expected_version 필수. gender, birth_date, include_used, allergies, ingredient_filter 선택 |
| PATCH `/v2/me/password` | current_password, new_password, new_password_confirmation → 204 |
| GET `/v2/subscription-plans` | plan_id, name, price, currency, interval, benefits, billing_mode 목록 |
| POST `/v2/me/subscriptions` | plan_id, payment_method. `Idempotency-Key` 헤더 8~128자 필수 |
| GET `/v2/me/subscription` | active, entitlement_end, cancel_at_period_end. 추가 subscription_id, billing_mode |
| POST `/v2/me/subscription/cancel` | 기간 말 종료 예약. 남은 기간 권한 유지 |
| GET `/v2/me/payments?limit=20` | 본인 결제 이력, 최대 100개 |
| POST `/v2/me/payments/{id}/mock-refund` | 개발 모드의 모의 전액 환불. 실제 환불 아님 |

profile은 version, gender, birth_date, include_used, allergies, ingredient_filter `{avoid,prefer}`를 반환한다.
나이는 birth_date에서 표시 시 계산하며 별도 저장하지 않는다. 별명·관리자 역할 필드는 임의로 추가하지 않는다.
미제공 필드는 보존한다. birth_date/gender의 명시적 null은 삭제다. profile version 불일치는 409.
기피·선호 재료 수정은 유효한 프리미엄 권한을 요구한다. 코드는 아직 자유 문자열이며 성분 사전 확정 후 좁혀야 한다.
연령 제한·동의문 버전 목록·탈퇴·비밀번호 재설정·관리자 인증은 별도 후속 기능이다.

## 결제 범위와 임시 정책

기본 `BILLING_MODE=disabled`. 결제사·요금·정기결제 상품이 미정이므로 live 과금 어댑터는 구현하지 않았다.
`APP_ENV=development`, `BILLING_MODE=mock`일 때만 모의 결제가 가능하다. production에서 mock은 503이며 mock 권한도 유효하게 보지 않는다.
프론트의 premium-monthly와 월 단위를 사용하며 요금은 NULL(미정)이다. 모의 청구서는 금액 0으로 기록하며 실제 무료 요금제를 뜻하지 않는다.
card/bank_transfer/naverpay/kakaopay/tosspay는 모의 수단 이름이며 각 결제사와 연동되지 않았다. 카드번호·계좌 비밀번호·개인 결제 키를 받지 않는다.

- 성공: 201, 동일 재요청 200. subscription_id, invoice_id, payment_id, status, billing_mode 반환.
- 동일 사용자/동일 키/다른 요청: 409 IDEMPOTENCY_CONFLICT.
- 활성 구독에 새 결제: 409 SUBSCRIPTION_ALREADY_ACTIVE. 동시 요청은 회원 행 잠금으로 직렬화.
- 실패: 시도 이력은 저장하고 402 PAYMENT_FAILED. 같은 키를 다시 보내도 성공으로 바꾸지 않음.
- 결과 미확인: 202 pending, 권한 부여 안 함. 다른 키의 결제도 409 PAYMENT_PENDING으로 차단.
- `MOCK_PAYMENT_OUTCOME=succeeded|failed|pending`은 서버 개발 설정이며 클라이언트 입력이 아니다.
- 미확인 건 확정: `POST /internal/v2/mock-payments/{id}/resolve` + 별도 BILLING_TEST_TOKEN(32자 이상), `{outcome: succeeded|failed}`.
- 중복 확정은 기간을 연장하지 않는다. 상충하는 확정은 409. 이 경로는 실제 결제사 webhook이 아니다.
- 취소해도 결제한 기간까지 사용 가능하며 만료 시 GET에서 즉시 active=false가 된다.
- 현재 임시 구독은 월 이용권 방식: 만료 후 사용자가 새 결제를 요청한다. 자동 정기 청구/빌링키/실제 webhook/실제 환불은 결제사 확정 뒤 연결한다.
- 모의 환불은 해당 기간 권한만 취소하며 과거 결제 환불로 이후 결제 기간을 취소하지 않는다.

## 프론트 연결 시 조정할 부분

현재 http.ts 경로·요청 형태를 유지했다. CORS에 Idempotency-Key를 허용한다.
개발 화면에 테스트 결제 표시가 필요하다. 가격 미확정 표시를 실제 0원 상품으로 해석하지 않는다.
현재 payment.tsx는 active=false를 실패로 처리하므로 202 pending일 때 '확인 중' 화면과 조회 재시도가 필요하다.
실제 결제 redirect 주소·결제 동의 버전/서버 전송·결제 수단별 비동기 상태는 아직 합의되지 않았다.
모의 결제 동작 확인과 실제 결제 연동 완료를 구분한다. 분석·추천·상담 API는 이 변경에서 구현하지 않았다.
