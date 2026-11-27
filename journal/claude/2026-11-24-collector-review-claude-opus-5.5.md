# [Claude Opus 5.5] 개발일지 · 2026-11-24 수집기(최준서 파트) 로직 검토 — 주기적 적재 전제

- 작성 AI: Claude Opus 5.5
- 대상: `origin/part/최준서-collector` bd18140 (2026-11-24 커밋 포함), 백엔드는 `part/소병선-backend-test` b5c8caa
- 코드 변경 없음 (읽기 검토)
- 계기: 사용자 정정 — "크롤링 데이터는 미리 넣는 게 아니라 **주기적으로 DB에 들어간다**. 수집은 준서 파트."

## 수집기 구조 요약
- `unified_live/`: 승인 기반 통합 수집 계층. 도매꾹·Serper·YES24·eBay(일반/중고)·범용 URL(JSON-LD/CSS) 수집기를 묶는다. `engine.py`(사이클·작업), `fleet.py`(사이트별 설정), `changes.py`(내용 기반 중복 제거), `transport.py`(전송).
- `domeggook_live/domeggook_delivery.py`: **Outbox**. 관측을 파일(`backend_outbox.json`)에 쌓고 `/internal/v2/crawl-runs/{run_id}/observations`로 보낸다. 모든 수집기가 이 Outbox를 재사용.
- `collector_ops/`: NAS 운영 런타임, 백엔드 전송 경로(HTTPS 또는 내부 HTTP).
- 실행 주기: 대부분 **7,200초(2시간) 이상**, eBay 중고만 60초 목표. 외부 수집·백엔드 전송은 각각 `COLLECTOR_RUN_APPROVED`, `COLLECTOR_DELIVERY_APPROVED` 승인 필요.
- 백엔드로 보내는 것은 **관측(observations)뿐**. 확장 정보(판매처·이미지·GTIN·식품 성분)는 수집기 로컬 checkpoint에만 보관하고 백엔드로 보내지 않는다. URL에서 찾은 식품은 전송 보류.

## 전송 규칙 (코드로 확인)
`domeggook_delivery.py` `flush()`
| 백엔드 응답 | 수집기 처리 |
| --- | --- |
| 200/201 + state | delivered, 또는 state가 quarantine이면 **quarantine** |
| 401/403/**409**/3xx | 해당 항목 held + **Outbox 전체 hold** (사람이 풀 때까지 그 출처 전송 중단) |
| 0/408/425/429/5xx | 재시도. 대기 5→10→20→40초(최대 300초), **최대 5회 후 exhausted** |
| 그 외 4xx (422 등) | **rejected**, 본문 삭제 |

`unified_live/changes.py` `_stage()`
- 내용(observed_at·observation_key 제외)이 이전과 같으면 **보내지 않는다**(`unchanged_skipped`, 로컬 `last_checked_at`만 갱신).
- 직전 이벤트가 `quarantine / revoked / held / exhausted / rejected`이면 **`previous_event_requires_review`로 그 상품의 새 관측을 영원히 보내지 않는다.**

`unified_live/fleet.py` 범용 URL 사이트 기본값: 사이클당 신규 3개, 기존 상품 재확인 1개, 2시간 주기, 하루 요청 40회, 추적 최대 1,000개.

---

## 발견한 문제

### #29 한 번 전송에 실패한 상품은 영구히 갱신이 멈춘다 — 중요
- 원인 조합: (1) exhausted는 재시도 5회, 누적 대기 약 75초. (2) 백엔드가 quarantine으로 응답하는 경우: `PRICE_ANOMALY`(이전 가격 대비 `CATALOG_PRICE_RATIO`=10배 이상 변동), `SAME_TIME_CONFLICT`, `INCOMPLETE_FIRST_OBSERVATION`, `IDENTITY_CONFLICT`, `OBSERVATION_TOO_OLD`. (3) 422(허용 안 된 호스트·통화). → 어느 쪽이든 `changes.py`가 그 상품을 `previous_event_requires_review`로 묶어 **가격·재고가 바뀌어도 다시 보내지 않는다.**
- 실제 상황: 백엔드 배포·재시작(마이그레이션 포함)이 75초를 넘으면 그 사이 대기 중이던 상품 전부가 영구 정지. 정상적인 큰 할인(10배)도 영구 정지.
- 영향 받는 파트: 수집기(재시도·검토 정책)와 백엔드(quarantine 기준) 양쪽.
- 해결 방안 후보: 수집기 — exhausted를 시간 기반으로 되살리기(예: 백엔드 health 회복 시 재시도), quarantine은 "그 이벤트만 보류"하고 다음 변경은 새 이벤트로 허용. 백엔드 — quarantine 사유를 ACK에 명확히(이미 `error_code` 있음), 가격 이상 기준 재검토.

### #30 백엔드 409 하나로 그 출처 전체 전송이 멈춘다 — 중요
- 원인: 409를 인증 문제(401/403)와 같은 "사람 검토 필요"로 묶어 Outbox 전체를 hold.
- 백엔드가 409를 주는 경우: 같은 observation_key에 다른 본문, `RUN_SOURCE_CONFLICT`(run_id 하나에 다른 출처), 처리 중 무결성 충돌(`DATA_CONFLICT`).
- 해결 방안 후보: 409는 해당 항목만 held, 원인 코드별 처리. 백엔드는 409 사유 코드를 계약에 명시.

### #31 "아직 판매 중"이라는 신호가 백엔드에 가지 않는다 (신선도) — 중요
- 원인: 내용이 같으면 보내지 않음 + 404/410·검색 누락은 판매 종료로 보내지 않음(`verification_required`) + 기존 상품 재확인이 사이클당 1개(1,000개 추적 시 개별 상품 재확인 간격이 수십 일).
- 결과: 백엔드의 `last_seen_at / price_observed_at`이 계속 오래된 값. 쇼핑몰에서 사라진 상품도 '판매 중'으로 남아 추천될 수 있다. 화면의 가격 기준 시각도 오래됨.
- 수집기 문서도 "전송 생략 시 freshness를 갱신할 별도 batch heartbeat 필요"라고 적어 둠(미구현). 백엔드에도 그런 API 없음.
- 해결 방안 후보: 백엔드에 "확인만 함(heartbeat)" API(가격·상태 변경 없이 `last_checked_at`만 갱신) 추가 + 수집기가 unchanged에서 묶어 전송. 백엔드는 오래 확인 안 된 상품을 추천에서 낮추거나 "가격 확인 필요" 표시.

### #32 백엔드 확장 API가 생겼지만 수집기는 쓰지 않는다 — 중요
- 백엔드(maintest~): `/internal/v2/crawl-runs/{run}/extensions` (`listing-matching-extension-v1`, `food-evidence-v1`) — 판매처·이미지·GTIN·모델번호·옵션·성분.
- 수집기: 같은 정보를 로컬 checkpoint(`listing-extension-v1`)에만 저장. `collector_ops/backend_transport.py`의 허용 경로도 observations뿐(도매꾹 쪽 `domeggook_backend.py`만 extensions 허용).
- 결과: 유사 상품(matches), 확장 선도착 처리(#13), 브랜드·카테고리 임베딩(#12), 식품 성분 기반 알레르기 판정(#27)이 **운영 데이터 없이** 동작. → #27의 직접 원인.
- 해결 방안: 두 파트 계약 맞추기(스키마 이름·필드 매핑), 수집기 Outbox에 extensions 경로 추가.

### #33 새 사이트를 추가할 때 백엔드 허용 목록을 같이 바꿔야 한다 — 운영
- 백엔드는 `CATALOG_URL_HOSTS`, `CATALOG_CURRENCIES`에 없는 관측을 422로 거절 → 수집기는 rejected → #29로 그 상품 영구 정지.
- 해결 방안: 사이트 등록 절차에 백엔드 설정 변경 포함, 또는 수집기가 전송 전에 백엔드 허용 목록을 확인(preflight).

## 기존 이슈 재평가 (사전 적재 → 주기적 적재)
| # | 변경 |
| --- | --- |
| 28 | "오래된 데이터 적재 거부"는 대부분 해당 없음(관측은 보낼 때 신선). 단 Outbox에 30일 넘게 머문 항목은 OBSERVATION_TOO_OLD → #29로 정지. **#31(신선도)로 대체** |
| 24 | 계속 해당. DB가 운영 중 계속 갱신되므로 업그레이드 시 공백 발생. 재임베딩 중에도 새 상품이 계속 들어옴 |
| 27 | 원인이 확정됨: 수집기가 성분을 백엔드로 보내지 않음(#32) |
| 16 | 그대로(offer_id 기반 권장). 주기 적재라도 상품은 DB에 있음 |
| 23 | 그대로(저장소에서 제거) |
| 14 | 주기 적재에서 더 중요: 도매꾹 Outbox는 run_id 하나를 계속 써서 crawl_run이 오래 유지됨 → 정리 작업 FK 문제는 이미 해결(#14) |
| 13 | 수집기가 extensions를 보내기 시작하면 유효(#32) |

## 확인하지 못한 것
- NAS에서 실제로 어떤 수집기가 승인·가동 중인지, 실제 전송 성공률.
- 수집기 테스트 실행(이번엔 코드 읽기만).
