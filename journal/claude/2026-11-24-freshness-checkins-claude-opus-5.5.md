# [Claude Opus 5.5] 개발일지 · 2026-11-24 #31 판매 확인(heartbeat) API와 신선도 표시

- 작성 AI: Claude Opus 5.5
- 브랜치 / 커밋: `part/소병선-backend-test` / `4f26501`
- 상태: **부분 해결** — 백엔드 완료. 수집기(최준서 파트)가 이 API를 호출해야 완전히 해결.

## 문제점
수집기는 내용이 바뀐 상품만 관측으로 보낸다. 그래서 백엔드의 `last_seen_at`이 마지막 "변경" 시각에 멈추고, 아직 판매 중인 상품과 쇼핑몰에서 사라진 상품을 구분할 수 없다. 사라진 상품도 '판매 중'으로 추천되고, 화면의 확인 시각도 오래된다. (발견: [수집기 검토](2026-11-24-collector-review-claude-opus-5.5.md#31))

## 원인
- 수집기: `unified_live/changes.py` — 내용이 같으면 `unchanged_skipped`(로컬 `last_checked_at`만 갱신).
- 백엔드: 내용 변경 없이 "확인했다"만 받는 API가 없었다. 관측을 같은 내용으로 다시 받으면 되지만, 수집기는 같은 본문을 반복 전송하지 않도록 설계되어 있고(멱등 키·Outbox 정책), 상품당 요청 1건이라 비효율.

## 해결 방안 (검토한 선택지)
| 선택지 | 장점 | 단점 | 채택 |
| --- | --- | --- | --- |
| A. 별도 check-in API(묶음 전송), 카탈로그와 값이 같을 때만 신선도 갱신 | 요청 수 적음, 오래된 값을 신선하게 보이게 만들 위험 없음 | 수집기 쪽 작업 필요 | ✅ |
| B. 수집기가 같은 관측을 주기적으로 재전송 | 백엔드 변경 없음 | 상품당 요청, 관측 기록·이력 테이블 증가, 수집기 멱등 정책과 충돌 | |
| C. 백엔드가 일정 시간 지나면 자동으로 '판매 종료' 처리 | 수집기 변경 없음 | 수집 주기가 길어(재확인이 사이클당 1개) 멀쩡한 상품을 대량으로 내림 | |

## 해결 (적용 내용)
1. `POST /internal/v2/listing-checks` (`services/api/kkulpick/freshness.py`, 수집 토큰)
   - 본문 `{source, items:[{source_listing_id, variant_key, observed_at, price, currency, availability}]}`, 최대 500개.
   - 카탈로그의 price·currency·availability가 **같을 때만** `last_seen_at`/`last_checked_at`을 `greatest()`로 앞으로 옮김. 가격·상태 값과 필드별 관측 시각(`price_observed_at` 등), `last_changed_at`은 바꾸지 않음.
   - 응답 `{confirmed, mismatch[], unknown[], rejected[]}`. mismatch(값이 다름)·unknown(없음/삭제됨)은 수집기가 전체 관측을 다시 보내라는 신호. observed_at이 미래 5분 초과 또는 30일 초과면 rejected.
   - 한 번의 SQL(`UPDATE ... FROM unnest(...)`)로 처리.
2. 상품 카드(기본 추천 `/v2/recommendations/basic`, 제휴 `/featured`, 분석 결과)에 `seen_at`(마지막 판매 확인 시각), `stale`(기준 `CATALOG_STALE_HOURS`, 기본 72시간) 추가. 기본 추천 정렬을 `last_seen_at` 최신순으로.
3. 추천 서비스 선택 옵션 `RECO_MAX_STALENESS_HOURS`(기본 0=끔): 켜면 그 시간 안에 판매 확인이 안 된 매물을 후보에서 제외 (`vectors.candidates`, `PgVectorIndex.search`).
4. 문서: `services/api/README.md`, `.env.example`.

## 왜 그렇게 해결했는지
- **값이 같을 때만 갱신**: 수집기가 "변경 없음"이라고 믿어도, 그 전 전송이 실패했으면(#29) 백엔드 값은 옛 값이다. 이때 신선도만 올리면 틀린 가격이 '방금 확인됨'으로 보인다. 비교해서 다르면 mismatch로 돌려줘 재전송을 유도한다. → #29의 피해도 일부 줄인다(수집기가 mismatch를 받아 다시 보내면 멈춘 상품이 풀림).
- **필드 관측 시각은 건드리지 않음**: ingest는 필드별 관측 시각으로 순서를 판단한다. check-in이 이를 바꾸면 늦게 도착한 진짜 관측과의 순서 판단이 달라질 수 있어 신선도 칼럼만 갱신했다.
- **자동 판매 종료(C안) 대신 표시만**: 수집기의 재확인 주기가 매우 길어서 시간 기준 자동 종료는 멀쩡한 상품을 대량으로 내린다. 기본은 표시(`stale`)만 하고, 추천 제외는 운영자가 켜는 옵션으로 뒀다.
- 응답을 다른 수집 엔드포인트처럼 감싸지 않은 본문(`{...}`)으로 맞췄다.

## 검증
- 격리 DB(새 볼륨)에서 CI 순서·반대 순서 모두: 추천+워커 80 passed, API 89 passed, 샘플 변조 32 passed. Windows 단위: API 35, 워커·추천 63 passed.
- 새 테스트: `test_listing_checks_refresh_freshness_only_when_catalog_matches`(일치·불일치·미존재·미래·과거 check-in), `test_cards_flag_stale_listings`, `test_optional_staleness_window_drops_unconfirmed_offers`.
- 검증하지 못한 것: 실제 수집기 연동(수집기가 아직 호출하지 않음).

## 남은 과제
- **수집기(최준서)**: `unchanged_skipped`가 된 매물을 모아 `/internal/v2/listing-checks`로 보내고, mismatch·unknown은 전체 관측으로 다시 보내기. 이때 #29의 "영구 보류" 상태인 매물도 mismatch를 계기로 풀어주는 것이 좋다.
- 사라진 상품(404/410)은 여전히 백엔드로 오지 않는다 → check-in이 끊기므로 `stale`로 드러난다.
- 수집기의 재확인 빈도(사이클당 1개)가 낮으면 check-in도 드물다. 수집 설정 조정은 수집기 담당.
