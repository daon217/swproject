# [Claude Opus 5.5] 개발일지 · 2026-11-24 세션 2 — 추가 검토 후 개선 (#11 #12 #13 #15, 발견 #14)

- 작성: Claude (Opus 5.5)
- 브랜치: `part/소병선-backend-test` (로컬·미push)
- 사용자 요청: 추가로 찾은 문제 중 4(아이디 중복), 5(임베딩 브랜드·카테고리), 6(확장 선도착·옵션), 8(테스트 DB 섞임) 개선.

---

## <a id="11"></a>#11 회원·관리자 아이디 중복 — 해결 (aec0143)

**문제점** 같은 로그인 아이디가 회원(`app.members`)과 관리자(`app.admin_identities`)에 동시에 존재할 수 있다. 상담 화면의 상담원 이름 표시, 로그인 안내가 헷갈린다.

**원인** 관리자 가입은 회원 테이블을 확인하지만 회원 가입은 관리자 테이블을 확인하지 않음. 각 테이블의 unique 인덱스는 자기 테이블만 보장.

**해결 방안**
| 선택지 | 채택 |
| --- | --- |
| A. 두 가입 경로 모두 양쪽 테이블 확인 + 아이디별 advisory lock | ✅ |
| B. 공용 login_ids 테이블 신설 | 확실하지만 마이그레이션·기존 데이터 이전 부담 |
| C. 확인만 추가(락 없음) | 동시 가입 시 경합으로 뚫림 |

**해결** `members.login_id_taken()`: `pg_advisory_xact_lock(hashtextextended('login-id:'||lower(id),0))` 후 두 테이블 존재 확인. 회원 가입·관리자 가입·아이디 사용 가능 조회가 모두 사용.

**왜** 두 테이블이 같은 member DB에 있어 트랜잭션 범위 락으로 충분하고 스키마 변경이 없다.

**남은 과제** 이미 DB에 중복된 아이디가 있다면 정리하지 않는다(확인 쿼리 필요).

**검증** `test_member_and_staff_share_one_login_namespace` 통과.

---

## <a id="12"></a>#12 브랜드·카테고리 변경이 임베딩에 반영 안 됨 — 해결 (0e3da73)

**문제점** 확장 수집으로 브랜드·카테고리가 바뀌어도 검색 벡터가 갱신되지 않는다.

**원인** 트리거 `embedding_content_version`이 name/description/kind만 비교, 작업 스냅샷도 이 3개만 담음. 임베딩 텍스트 템플릿 `catalog-v1`도 3개 필드.

**해결**
- 마이그레이션 `0011_embedding_snapshot_v2`: brand·category 변경 시 content_version 증가, 스냅샷 함수 `app.embedding_snapshot()`으로 통일(작업 등록·백필 트리거 모두).
- 템플릿 `catalog-v2: name | brand | category | kind | description` → 계약 ID가 새로 생김(불변 계약 원칙).
- `bootstrap()`이 같은 도메인의 다른 serving 계약을 내리고 그 대기 작업을 삭제.

**왜** 계약은 불변이라 템플릿을 바꾸면 새 계약으로 전체 재임베딩하는 것이 맞다. 옛 계약을 serving으로 남겨두면 상품이 바뀔 때마다 아무도 처리하지 않는 작업이 쌓인다(#15의 원인과 같은 구조).

**운영 영향** 배포 후 `embedding-init`(bootstrap)이 v2 계약을 등록하고 전체 상품을 다시 임베딩한다. 그동안 새 계약 벡터가 없는 상품은 검색 결과에 늦게 나타날 수 있다.

**검증** `test_brand_and_category_changes_reembed_and_enter_text`, `test_bootstrap_retires_superseded_contracts` 통과. 가격만 바뀌면 재임베딩하지 않는 것도 확인.

---

## <a id="13"></a>#13 확장 정보 선도착 유실, 옵션 삭제 불가 — 해결 (b5c8caa)

**문제점**
1. 수집기가 상세(확장) 정보를 상품 첫 관측보다 먼저 보내면 404로 버려진다(보관하지 않음).
2. `matching_profile.options`는 합치기만 해서 한 번 들어간 옵션을 지울 수 없다.

**원인** `accept_extension`이 offer가 없으면 `HTTPException(404)` → 트랜잭션 롤백. options는 `dict.update`.

**해결 방안**
| 선택지 | 채택 |
| --- | --- |
| A. pending으로 저장 → 첫 관측 트랜잭션에서 적용 | ✅ |
| B. 수집기에 순서 보장 요구 | 큐가 분리돼 있어 보장 어려움 |
| C. 별도 재처리 워커 | 구성 요소 추가, 지연 발생 |

**해결**
- offer가 없으면 `state='pending'`, `error_code='OFFER_NOT_YET_OBSERVED'`, HTTP 202로 저장.
- 관측 수신 시 offer가 새로 생기면(`change_kind='created'`) 같은 트랜잭션·같은 식별자 락 안에서 pending 확장을 순서대로 적용. 건마다 savepoint를 써서 검증 실패한 건은 `INVALID_PENDING_EXTENSION`으로 격리하고 관측은 정상 처리.
- 같은 확장을 다시 보내면 pending일 때는 재처리, 적용 후에는 기존처럼 멱등 응답.
- 7일 넘게 pending이면 정리 작업이 `OFFER_NEVER_OBSERVED`로 격리.
- 마이그레이션 `0012_pending_extensions`: `source_listing_id`, `variant_key` 컬럼과 pending 부분 인덱스.
- options 값에 `null`을 보내면 해당 옵션 삭제.

**왜** 같은 트랜잭션에서 적용하면 "관측은 됐는데 상세는 아직" 상태가 외부에 보이지 않고, 별도 워커가 필요 없다.

**검증** `test_extension_before_first_observation_is_held_then_applied` 통과(보관 → 재전송 → 첫 관측 적용 → 멱등 재전송 → 옵션 삭제).

---

## <a id="14"></a>#14 정리 작업 crawl_runs FK 오류 — 해결 (b5c8caa)

**문제점** 정리 작업(maintenance)이 관측이 없는 오래된 `crawl_runs`를 지우는데, `listing_extensions.run_id`가 이를 참조(ON DELETE 없음)하면 FK 오류로 **정리 작업 전체**가 실패.

**원인** maintest에서 listing_extensions가 추가될 때 maintenance 쿼리가 갱신되지 않음. (#13 작업 중 발견)

**해결** 삭제 조건에 `NOT EXISTS (listing_extensions)` 추가.

---

## <a id="15"></a>#15 테스트 DB 상태 섞임 — 해결 (0e3da73)

**문제점** API 테스트 뒤에 임베딩 테스트를 돌리면 8개 실패. API 테스트를 같은 DB에서 두 번 돌리면 유사 상품 테스트 실패. CI는 순서가 반대라 드러나지 않음.

**원인**
- `test_database.py`가 테스트용 임베딩 모델 2개를 serving으로 켜고 끄지 않음 → 활성화 트리거가 모든 상품에 작업을 만들어(약 480개) 남김.
- `test_arrival_updates.py`가 만든 상품을 지우지 않음. 유사 상품 검색은 출처(source)를 가리지 않아 이전 실행의 같은 GTIN·브랜드가 잡힘.

**해결** 테스트용 모델을 테스트 종료 시 내리고 작업 삭제(finalizer). arrival 테스트 fixture가 자기 source의 데이터를 정리. #12의 bootstrap 정리도 같은 문제를 막는다.

**검증** 새 DB에서 (임베딩→API), (API→임베딩) 두 순서와 같은 DB 재실행 모두 통과: 추천+워커 79, API 87, 샘플 변조 32.
