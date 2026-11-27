# [Claude Opus 5.5] 개발일지 · 2026-11-25 maintest 최신화(82a81db) 후 전체 재점검

- 작성 AI: Claude Opus 5.5
- 브랜치 / 커밋: `part/소병선-backend-test` d0a46f8 → `82a81db` (fast-forward, 푸시함) = `maintest`
- 상태: 최신화 완료, 새 문제 3건(#59–#61) 기록, 코드 수정 없음

## 1. 최신화
- `maintest`에 새로 들어온 커밋은 `82a81db` 하나뿐(JSLuigi, "대두 경고를 클라이언트 코드 soybean으로 반환").
- 테스트 브랜치가 maintest의 조상이어서 병합 커밋 없이 앞으로 당김(`--ff-only`). 로컬 미커밋 파일(`apps/mobile/.env.example`, `package-lock.json`)은 건드리지 않음.

## 2. 82a81db 검토
- 내용: 추천 서비스 `/internal/process`가 클라이언트의 `soybean`을 내부 코드 `soy`로 바꿔 처리하는데, 경고 응답에도 `soy`가 나가서 확장·모바일의 한글 라벨 조회가 실패("soy 알레르기 주의"). 응답 직전에 `soybean`으로 되돌림.
- 판단: **올바른 수정.** 클라이언트(확장·모바일) 코드 목록에서 내부 코드와 철자가 다른 것은 `soybean` 하나뿐이라 다른 누락은 없음. 분석 워커가 추가하는 추정 상품 경고는 클라이언트 코드를 그대로 쓰므로 영향 없음.
- 연관해서 발견: 아래 #59 (DB에 저장된 식품 알레르기 코드는 반대 방향의 같은 종류 문제).

## 3. 새로 발견한 문제

### #59 식품 `allergens_declared` 코드가 추천 안전 검사에서 누락될 수 있음 — 중요(안전)
- 문제: 추천 서비스(`adapters/postgres.py`)는 `foods.allergens_declared`(구조화된 코드 목록)를 직접 비교하지 않고, **`allergen_notice_raw`가 비어 있을 때만** 코드를 쉼표로 이어 붙여 글자 매칭(`detect`)에 넣는다.
- 재현: `detect(split_ingredients(code))`를 19개 코드 전부에 돌리면 **`shellfish`, `pine_nut`은 감지되지 않음**(동의어 목록에 코드 자체가 없음 / `pine nut`은 공백 제거 후 `pinenut`이라 `pine_nut`과 불일치).
- 영향: 수집기가 `allergens_declared=["shellfish"]`처럼 코드로 보내고 표시 원문이 없으면, 조개류 알레르기 사용자에게 그 식품이 "안전"으로 추천될 수 있다. 또 표시 원문이 있으면 `allergens_declared`는 아예 무시된다.
- 추가 원인: 백엔드 확장 API는 `allergens_declared`에 아무 문자열(≤64자)이나 허용하고, 계약 문서에 코드 체계가 정해져 있지 않다.
- 해결 방안: (A) 추천 서비스가 `allergens_declared`를 코드 집합으로 직접 판정(+`soybean`→`soy` 같은 별칭 정규화) — 권장, (B) 동의어 목록에 코드 철자 추가(임시), (C) 백엔드에서 허용 코드 검증 + 계약 문서화.

### #60 관리자 가입 신청 거절 기능 없음 — 운영
- 승인 API만 있고 거절·삭제 API가 없다. 잘못된 신청은 목록(`/v2/admin/auth/requests`, 최대 100건)에 영구히 남는다. 신청 자체는 IP당 분당 30회 제한뿐이라(프록시 뒤에서는 #17로 전체 공유) 신청이 쌓이면 실제 신청이 100건 밖으로 밀릴 수 있다.
- 해결 방안: `POST /v2/admin/auth/requests/{id}/reject`(감사 로그 포함) + 오래된 미승인 신청 정리.

### #61 `admin_cli revoke` 감사 로그의 역할 표기 오류 — 경미
- `revoke`는 `--role` 기본값 `support`를 그대로 감사 로그에 남겨, admin 계정을 회수해도 `revoke:support`로 기록된다. 실제 회수 대상 역할을 기록해야 한다.

## 4. 기존 미해결 문제 재확인 (모두 그대로)
| # | 재확인 결과 |
| --- | --- |
| 16 | `/v2/links/convert` 여전히 인증 없음(IP별 분당 10회 + 전체 60회만) |
| 17 | API Dockerfile의 uvicorn에 `--proxy-headers`/`--forwarded-allow-ips` 없음 → 프록시 뒤에서는 모든 사용자가 같은 IP |
| 18 | 분석 워커 동시성 기본 4 그대로 |
| 25 | 분석 `fail`에서 retryable이면 즉시 `queued`(대기 시간 없음) |
| 29·30 | 도매꾹 수집기 `max_attempts` 5 후 `exhausted`, 401/403/409는 출처 전체 `held` — 그대로 |
| 31·32 | 도매꾹(주기 수집) 쪽은 `listing-checks`·확장 API 미호출. 11번가 오프라인 어댑터만 `/extensions` 전송 |
| 23 | `handoffs/real_db_test_300_20261115/observations_v2_REAL_300.json`(220KB) 여전히 저장소에 있음 |
| 24·26·27·04·19·21·22·33 | 관련 코드 변경 없음 |

## 5. 점검했지만 문제 없던 것
- 앱(확장·모바일·관리자 웹)이 호출하는 API 경로 전부 백엔드에 존재(404 없음).
- 분석 상태 값(`queued/running/completed/failed/cancelled`)과 경고 `evidence` 값이 백엔드 모델과 확장 타입에서 일치.
- 관리자 역할 검사: 가입 승인·카탈로그 삭제·제휴·회원 목록은 `admin`만, 상담은 `admin/support`. 권한 회수 시 `auth_version`으로 세션 즉시 무효.
- 분석 취소·실패·만료 시 이미지 삭제(취소·실패는 즉시, 만료는 정리 작업).

## 6. 검증
- PR #15 CI(82a81db): 24개 검사 전부 통과(Playwright `browser` 포함).
- 격리 DB 통합 테스트(82a81db): CI 순서·반대 순서 모두 추천+워커 79 통과(1 skip), API 89 통과(1 skip), 샘플 변조 32 통과.
