# [Claude Opus 5.5] 개발일지 · 2026-11-25 #59 식품 알레르기 신고 코드 판정 수정

- 작성 AI: Claude Opus 5.5
- 브랜치 / 커밋: `part/소병선-backend-test` `b51ffdc` (푸시함, maintest 반영은 아직)
- 상태: **#59 해결**

## 문제점
판매처가 구조화해서 신고한 알레르기 코드(`foods.allergens_declared`)가 추천 안전 검사에서 누락될 수 있었다.
조개류(`shellfish`)·잣(`pine_nut`)만 신고된 식품이 해당 알레르기 사용자에게 "안전"으로 추천될 수 있다.

## 원인 (파일:줄은 수정 전 82a81db 기준)
1. `services/recommendation/adapters/postgres.py` — `notice = notice_raw or ", ".join(dec)`:
   신고 코드는 **표시 원문이 비었을 때만** 글자로 이어 붙여 쓰였다. 원문이 있으면 코드는 아예 무시.
2. `services/recommendation/allergens.py` `detect()` — 코드 목록을 "성분 글자"로 매칭. 동의어 목록에 `shellfish`가 없고, `pine nut`은 공백 제거 후 `pinenut`이라 `pine_nut`과 다르다.
   재현: `[c for c in ALLERGENS if not detect(split_ingredients(c))]` → `['shellfish', 'pine_nut']`.
3. 페이지 분석 경고 경로(catalog-context → 워커 → `/internal/process`)에는 신고 코드가 전혀 전달되지 않았다.
4. 백엔드 `FoodEvidence.allergens_declared`는 아무 문자열이나 저장했고, 코드 체계가 문서에 없었다(`soy`/`soybean`/`대두`가 섞일 수 있음).

## 해결 방안 (검토한 선택지)
| 선택지 | 장점 | 단점 |
| --- | --- | --- |
| A. 신고 값을 **코드로 직접 판정**(별칭·한글 표시명 정규화) + 모르는 값만 글자 매칭 | 원인 제거, 원문 유무와 무관 | 추천·워커·백엔드 여러 곳 수정 |
| B. 동의어 목록에 코드 철자 추가 | 한 줄 | "원문이 있으면 무시" 문제는 그대로, 새 코드 추가 때 또 누락 |
| C. 백엔드에서 모르는 값 422 거절 | 계약이 엄격 | 수집기 확장 전체가 실패 → #29 영구 동결로 이어짐, 안전 정보 유실 |

→ **A 채택 + 백엔드는 정규화만(거절하지 않음).** 안전 정보는 버리지 않는 쪽이 우선이다.

## 해결 (b51ffdc)
- 추천 `allergens.py`: `normalize_code()` — 코드·별칭(`soybean`→`soy`, `pine nut`/`pine-nut`→`pine_nut`)·한글 표시명(`조개류`, `잣`)을 내부 코드로. `assess()`가 신고 코드를 **항상** 직접 반영(사유 "알레르기 신고 코드 '...'"), 코드가 아닌 값(예: "새우 함유")은 글자 매칭으로 한 번 더 확인. 신고 코드만 있어도 "성분 정보 있음"으로 인정.
- 추천 `contracts.py`: `CollectedProduct.allergens_declared` 필드(문자열 목록 검증).
- 추천 `adapters/postgres.py`: 원문과 코드를 섞지 않고 각각 전달.
- 추천 `http_service.py`: catalog-context가 `allergens_declared`를 따로 반환, `/internal/process`가 `allergens_declared` 입력으로 경고 생성(코드 → "판매처 알레르기 표시에 ...", OCR 감지와 중복 제거). 요청 알레르기 코드도 `normalize_code`로 정규화.
- 워커 `analysis_worker.py`: catalog 매칭의 신고 코드를 `/internal/process`에 전달(없으면 필드 생략 — 이전 버전과 호환).
- 백엔드 `extensions.py`: `FOOD_ALLERGENS`(클라이언트·프로필과 같은 19개 코드) + `canonical_allergen()`. 저장 시 `soy`/`대두`→`soybean`, `조개류`→`shellfish`, 중복 제거, 모르는 값은 그대로 보존.
- 문서: `services/api/README.md`에 신고 코드 목록과 규칙.

## 왜 이렇게 했는지
- 신고 코드는 "판매처가 이미 판정한 결과"라서 글자 매칭보다 신뢰도가 높다. 원문이 있다고 버리면 안 된다.
- 저장 코드는 클라이언트 철자(`soybean`)로 통일했다. 회원 프로필·확장·모바일이 이미 그 철자를 쓰고, 추천 서비스만 내부에서 `soy`로 바꾼다(82a81db와 같은 경계).
- 모르는 값을 거절하지 않은 이유: 확장 전체 실패 → 수집기 영구 동결(#29) → 성분 정보까지 유실되는 더 나쁜 결과.

## 검증
- 재현 스크립트(원인 2) — 수정 후 `normalize_code` 19개 코드 전부 통과.
- 추가 테스트: 추천 단위 2개(`test_declared_codes_*`), `/internal/process` 신고 코드 경고, 워커 전달·생략, API `canonical_allergen` 단위, 확장 저장값 통합, **DB 통합**(원문 "밀 함유 없음" + 신고 `["shellfish"]` 식품이 조개류 사용자 추천에서 빠지고, 다른 사용자에게는 추천, catalog-context가 코드를 따로 반환).
- 결과: Windows 단위 API 36, 추천+워커 44 통과. 격리 DB(CI 순서·반대 순서) 추천+워커 **81**, API **90**, 샘플 변조 32 통과.
- 미확인: 실제 수집기는 아직 확장(성분·신고 코드)을 보내지 않는다(#32). 실데이터 효과는 #32 이후 확인.

## 남은 과제
- maintest 반영(사용자 승인 후).
- 수집기(#32)가 `allergens_declared`를 보낼 때 위 코드 목록을 쓰도록 공유.
