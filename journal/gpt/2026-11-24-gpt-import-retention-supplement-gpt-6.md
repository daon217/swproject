# [GPT-6 (Codex)] 개발일지 · 2026-11-24 실제 수집 파일 가져오기·정리 정책·재생성 방지 보완 (#46)

- 날짜: 2026-11-24 (누락 보완 기록일, Asia/Seoul)
- 실제 작업 시기: 2026-11-16~11-17
- 상태: 부분 해결 — 당시 작업 범위 기준, 최신 운영 완료 판정 아님
- 브랜치 / 커밋: 문서는 `devlog`; 코드 근거 [`6058d22`](https://github.com/daon217/swproject/commit/6058d22f34c30f98c771fab4381192b79d5578f0), [`0e6690b`](https://github.com/daon217/swproject/commit/0e6690bec28d440688519f8f39f3c4d0fa24af64), [`8fcacfa`](https://github.com/daon217/swproject/commit/8fcacfa345fe4f9d02c6cc776f424370cd69226d)
- 관련 파일: [tools/catalog.py:24](https://github.com/daon217/swproject/blob/6058d22f34c30f98c771fab4381192b79d5578f0/tools/catalog.py#L24); [tools/catalog.py:64](https://github.com/daon217/swproject/blob/6058d22f34c30f98c771fab4381192b79d5578f0/tools/catalog.py#L64); [docs/CATALOG_INGESTION.md:1](https://github.com/daon217/swproject/blob/6058d22f34c30f98c771fab4381192b79d5578f0/docs/CATALOG_INGESTION.md#L1); [services/api/kkulpick/maintenance.py:20](https://github.com/daon217/swproject/blob/8fcacfa345fe4f9d02c6cc776f424370cd69226d/services/api/kkulpick/maintenance.py#L20); [services/api/tests/test_retention.py:25](https://github.com/daon217/swproject/blob/8fcacfa345fe4f9d02c6cc776f424370cd69226d/services/api/tests/test_retention.py#L25); [docs/DB_OPERATIONS.md:1](https://github.com/daon217/swproject/blob/8fcacfa345fe4f9d02c6cc776f424370cd69226d/docs/DB_OPERATIONS.md#L1)
- 작성 AI: GPT-6 (Codex, 회고 작성)
- 원 작업 AI: GPT/ChatGPT/Codex. 당시 상세 모델 버전은 미확인.

> 사용자 정정에 따라 실제 코드 개발이 시작된 2026-11-04 이후만 기록한다. 그 이전 설계·ERD·발표자료 제작은 포함하지 않는다. 선택지 표는 회고 비교이며 당시 모두 실험했다는 뜻이 아니다. 기존 일지를 덮어쓰지 않고 누락을 보완한다.

## 문제점
기존 #35/#36은 API 병합·회원 기능 중심이라 실제 300건 수집 파일 적재 도구, 단계별 검증, 품절/종료 정리와 과거 관측 재생성 방지 정책이 빠지거나 짧게 언급됐다.

## 원인
관측 API는 한 건씩 받으므로 파일 전체를 한 번에 POST할 수 없다. 정리 후 오래된 관측이 도착하면 삭제된 매물이 다시 생성될 수 있고, 원문/이력을 무기한 보관하면 저장량이 계속 늘어난다. 일시 접속 실패를 품절과 같은 삭제 조건으로 사용하면 정상 상품이 사라질 수 있다.

## 해결 방안 (검토한 선택지)
| 선택지 | 장점 | 단점 | 채택 |
| --- | --- | --- | --- |
| 파일을 DB에 직접 넣고 품절 행만 삭제 | 단순해 보임 | 입력 계약 우회·재전송·과거 복원 문제 | 미채택 |
| API 기반 파일 도구 + 삭제 식별 기록·보존기간 | 계약·멱등성 유지, 정리 경계 명확 | 정책 조정과 정리 처리량 관리 필요 | 채택 |

## 해결 (적용 내용)
- `tools/catalog.py`의 inspect/configure-hosts/import를 추가했다. 허용 호스트 추가는 명시적 로컬 설정 변경이며 수집 권한을 부여하거나 외부 사이트를 호출하는 작업이 아니다.
- 파일 관측은 원래 키·관측 시각을 유지해 API로 한 건씩 전송하고 행별 실패를 집계한다. 각 요청이 트랜잭션이므로 파일 전체 원자적 적재로 설명하지 않는다.
- `0002_arrival_updates`로 도착 시 갱신, 필드별 관측 시각, 변경 이력 등을 확장했다. 당시 고정 24시간 조회 만료를 없앴지만, 이는 이후 판매 상태 기준의 정리 유예 24시간과 다른 정책이다.
- `0003_retention`과 정리 작업을 추가했다. 당시 임시 기본 정책은 품절/판매 종료 상태 관측 후 24시간, 원문 7일, 관측 메타·닫힌 이력/삭제 식별 기록 90일이었다. 매시간 항목별 최대 500건을 처리했다.
- 삭제와 수신이 동일 매물 식별자 잠금을 사용하고 최신 재입고를 보존한다. 삭제 전 시각의 관측으로 복원하지 않으며, 30일보다 오래된 새 관측은 격리한다.
- timeout/blocked는 종료로 보지 않고, not_found는 suspect로 숨기며 이 정책의 물리 삭제 대상에서는 제외했다. 회원·구독·결제도 상품 정리와 구분했다.
- 지원 통화와 같은 통화의 급격한 가격 변화에 대한 임시 이상치 규칙, dry-run/apply 명령을 추가했다. 무료/대폭 할인도 격리될 수 있어 진위 판별 알고리즘으로 주장하지 않는다.

## 왜 그렇게 해결했는지
실제 수집 파일도 API의 검증·멱등 규칙을 통과시키고, 삭제 이후 재수신이라는 경계를 함께 다뤄야 한다. 보존기간은 영구 정책이 아니라 개발 중 사용자 요청에 따른 임시 운영값으로 분리했다.

## 검증
- `6058d22`의 CATALOG_INGESTION 문서에는 **로컬 격리 PostgreSQL 17.11 + pgvector 0.8.0에서 회귀 26개 통과**, 실제 300건 신규/재전송 후 중복 없음, 실제 HTTP 파일 도구 확인, 0001→0002 기존 값 보존 확인이 기록돼 있다. Docker 설정의 pgvector 0.8.7과 로컬 검사 환경을 혼동하지 않는다.
- 기존 #35의 “원본 300건 검사는 공개 CI에서 skip”은 **로컬 실제 300건 검사도 하지 않았다는 뜻이 아니다.** 이번 보완에서 두 검증을 명확히 구분한다.
- `test_retention.py`의 4개 테스트 정의는 dry-run/삭제/과거 재전송/재입고, 원문 비운 후 동일 키·충돌 처리, 너무 오래된 관측, 정책 최소값을 다룬다. 독립 실행 통과 수로 새로 집계하지 않고 당시 API 회귀 결과의 일부로 기록한다.
- 도구 예: `python tools/catalog.py inspect --file <수집 파일>`; 정리 예상 건수는 `python tools/workspace.py maintenance --scope core`, 실제 적용은 `--apply`를 붙인다. 이 기록 작성에서 사용자 DB에 적용하지 않았다.

이번 보완에서는 과거 서비스 테스트를 재실행하지 않았다. 고정 커밋의 코드·기록·참조를 대조했으며 아래 한계를 포함한다.

## 남은 과제 / 주의
- 원본 300건을 GitHub에 재업로드하지 않는다. 사용자 PC/공용 DB에 직접 적재한 작업도 아니다.
- 외부 쇼핑몰 가격·재고의 진위 검증, 수집 스케줄러, 실제 임베딩 생성은 이 단계의 범위 밖이었다.
- 보존기간이 지난 동일 관측 키의 영구 중복 방지는 제공하지 않는다. 정리 backlog·autovacuum·실데이터 정책 조정이 필요하다.
- 이후 Claude의 정리 FK 수정(#14), check-in/신선도(#31)는 별도 작업이며 이 GPT 기록에 합산하지 않는다.
