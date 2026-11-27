# [Claude Opus 5.5] 개발일지 · 2026-11-25 condition=unknown 지원(#68) · 웹 브랜치 반영

- 작성 AI: Claude Opus 5.5
- 브랜치 / 커밋: `part/소병선-backend-test` → **maintest `e6c7a3e`** (fast-forward)
  - `7404d25` 김호진 웹(maintest 병합 + README) fast-forward
  - `c670202` 웹 README 주소 설명 정정
  - `e6c7a3e` condition=unknown
- 상태: #68 해결. 새 미해결 #69·#70·#71 기록

## 1. 김호진 웹 브랜치 반영
- `origin/part/김호진-web`(7404d25)은 maintest(426a5da)를 병합한 뒤 `apps/web/README.md`만 바꾼 상태 → 코드는 maintest와 동일(404 수정 #55, 토큰 위임 제거 #20 그대로). 병합 커밋 없이 앞으로 당김.
- README 정정(c670202): "API 기본값이 NAS 주소 `http://<NAS 공인 IP>:8000`"이라고 적혀 있었으나 실제 `index.html`은 `api-base="/backend"`(Next 프록시 → `INTERNAL_API_URL`). 저장소가 **공개**라 서버 공인 IP·포트를 문서에서 뺌.

## 2. #68 condition=unknown (수집기 최준서 요청)
### 문제
- 수집기 측 확인: 백엔드 `Observation.condition`은 `new`/`used`만, 생략하면 `new`. 일반 쇼핑몰은 신품·중고를 표시하지 않는 경우가 있어 `unknown`이 필요.
- 받기만 하면 깨지는 곳(확인한 사실):
  1. 모델 Literal, DB `offers_condition_check`(`IN ('new','used')`) → 422/DB 오류.
  2. 추천 서비스 `CollectedProduct.from_dict`가 `new|used` 외는 ContractError → 후보 중 `unknown` 하나만 있어도 **추천 요청 전체 422**.
  3. 기본 추천(`/v2/recommendations/basic`)·유사 상품이 `condition='new'`로 걸러 `unknown` 상품이 조용히 빠짐.

### 선택지와 결정
| 쟁점 | 선택 | 이유 |
| --- | --- | --- |
| 생략 시 기본값 | **`new` 유지** | 기존 수집기·재전송 호환(v1 재전송 멱등 비교가 기본값에 의존). 표시가 없으면 수집기가 `unknown`을 명시 |
| 나중 관측이 `unknown`일 때 | **기존 `new`/`used`를 덮어쓰지 않음** | `unknown`은 "판매처가 말하지 않음"이지 상태 변경이 아님 |
| 추천·유사 상품 | **`used`가 아닌 것(`new`+`unknown`) 표시** | 일반 쇼핑몰 상품 대부분이 `unknown`이 될 수 있어 빼면 추천 대상이 크게 줄어듦. 중고 마켓은 `used`를 표시 |
| `/v2/offers` 기본 필터 | `new` 그대로, `unknown`·`all` 추가 | 기존 동작 유지. 관리자 웹은 이미 `all` 사용 |
| 식품 | `unknown` 허용, `used`는 계속 거절 | 별도 제약 `condition <> 'used' OR kind='product'` 유지 |

### 적용 (e6c7a3e)
- 마이그레이션 `0013_offer_condition_unknown`: 정의로 제약을 찾아 교체 → `CHECK (condition IN ('new','used','unknown'))`. downgrade는 `unknown` 행이 있으면 거부(추측해서 바꾸지 않음).
- `models.py` Literal 확장, `ingest.py` 덮어쓰기 금지 규칙, `api.py` 필터, `affiliates.py`·`extensions.py` `condition<>'used'`, 추천 `contracts.py` 허용(`is_used`는 `used`만).
- 계약 문서 `contracts/catalog-v2.md`에 규칙.

### 검증
- 새 테스트: 적재·목록 필터(unknown/new/all)·기본 추천 포함·`new`로 채워짐·이후 `unknown`이 `new`/`used`를 안 지움·식품 unknown 허용·used 식품 거절·잘못된 값 422 / 샘플 변조 `unknown_keeps_known_condition`(→ unchanged) / 추천 계약.
- 격리 DB(마이그레이션 0013 적용, 제약 확인): 추천+워커 **84**, API **91**, 샘플 변조 **33** — 두 순서 모두 통과.
- 미확인: downgrade 실행, NAS 실데이터 적재(수집기 수정 후 최준서가 검증 예정).

### 수집기 측 다른 항목 (백엔드 확인 결과)
- seller: 관측(Observation)에는 없음. 판매자는 리스팅 확장 `matching_profile.seller_id/seller_name`으로 보냄 → 수집기 보류 조건에서 분리하는 판단이 맞음.
- availability: 모델은 선택이지만 **첫 관측에는 name·price·currency·availability·url 필수**(없으면 `INCOMPLETE_FIRST_OBSERVATION` 격리).
- 다중 옵션: 백엔드는 옵션마다 `variant_key`를 달리해 **옵션별 별도 리스팅**으로 받음(가격·재고도 옵션별). 옵션 속성은 확장 `matching_profile.options`(최대 16개). 크롤러가 옵션별 가격을 뽑아 variant마다 관측을 보내면 됨.

## 3. 새로 발견한 문제
- **#69 관리자 웹 제휴 링크 우회 저장 — 중요(데이터·보안)**: `apps/web/pages/affiliate/index.js` 804~818줄. 서버가 허용 목록(`AFFILIATE_URL_HOSTS`) 밖 주소를 422로 거부하면 웹이 `https://store.example.test/redirect?url=<원래 주소>`로 감싸 다시 저장. 서버 검증 우회이고, 실제 사용자에게 나가는 제휴 링크가 존재하지 않는 테스트 도메인이 됨. 409 경로도 같은 처리. 2026-11-25 웹 병합(d0a46f8) 때 놓침. 해결: 우회 제거 + 오류 표시, 운영 서버에 실제 제휴 호스트를 `AFFILIATE_URL_HOSTS`로 등록.
- **#70 공개 저장소에 NAS 공인 IP — 확인 필요(보안)**: `services/collector/domeggook_live/live_http_test.py:22`에 `BASE='http://<NAS 공인 IP>:8000'`. 저장소가 PUBLIC. 해결: 환경변수로 바꾸고, 노출된 포트의 방화벽·인증 확인.
- **#71 임베딩 작업이 강제 종료로 시도 상한에 닿으면 조용히 멈춤 — 경미(운영)**: `claim_many`가 가져갈 때 `attempts`를 올리므로, 같은 묶음에서 워커가 8번 죽으면 `attempts>=8`이지만 `last_error`가 없어 다시 가져가지도, `--requeue-failed`로 살아나지도 않음. 해결: lease 만료 + 상한 도달 작업을 `exhausted:WorkerLost`로 표시.
