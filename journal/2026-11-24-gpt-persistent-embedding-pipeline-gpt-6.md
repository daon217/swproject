# [GPT-6 (Codex)] 개발일지 · 2026-11-24 백엔드 임베딩 작업자와 pgvector 추천 연결 (#43)

- 날짜: 2026-11-24 (회고 기록일, Asia/Seoul)
- 작업 시기: 2026-11-23
- 상태: 부분 해결 — 아래에 명시한 당시 범위 기준
- 브랜치 / 커밋: 기록은 `devlog`; 코드 근거 [`2d444b0`](https://github.com/daon217/swproject/commit/2d444b0ee4e1c181701c8491c77800b9c30f2e88)
- 관련 파일: [services/recommendation/embedding_config.py:20](https://github.com/daon217/swproject/blob/2d444b0ee4e1c181701c8491c77800b9c30f2e88/services/recommendation/embedding_config.py#L20); [services/recommendation/embedding_worker.py:15](https://github.com/daon217/swproject/blob/2d444b0ee4e1c181701c8491c77800b9c30f2e88/services/recommendation/embedding_worker.py#L15); [services/api/migrations/versions/embedding_jobs.sql:2](https://github.com/daon217/swproject/blob/2d444b0ee4e1c181701c8491c77800b9c30f2e88/services/api/migrations/versions/embedding_jobs.sql#L2); [services/recommendation/http_service.py:81](https://github.com/daon217/swproject/blob/2d444b0ee4e1c181701c8491c77800b9c30f2e88/services/recommendation/http_service.py#L81); [services/recommendation/tests/test_embedding_pipeline.py:78](https://github.com/daon217/swproject/blob/2d444b0ee4e1c181701c8491c77800b9c30f2e88/services/recommendation/tests/test_embedding_pipeline.py#L78)
- 작성 AI: GPT-6 (Codex, 회고 작성)
- 원 작업 AI: GPT/ChatGPT/Codex. 과거 세션의 상세 모델 버전은 미확인.
- 구현 주체 구분: 사용자 제공 Claude 분석을 참고했고, 본 항목의 적용 커밋은 GPT 작업 기록으로 확인했다.
> 과거 작업을 커밋·PR·대화 기록으로 복원한 일지다. 선택지 표는 회고 시점의 설계 비교이며, 모든 대안을 당시 구현·실험했다는 뜻이 아니다. 검증 수치는 해당 커밋의 기록이며 최신 코드 전체의 재검증 결과가 아니다. [기록 범위와 근거](2026-11-24-gpt-retrospective-scope-gpt-6.md)를 함께 읽는다.

## 문제점
분석 때마다 상품 목록을 내려받아 메모리 인덱스를 새로 만들었다. DB 벡터 테이블·도우미가 있어도 계약 등록, 자동 벡터 생성, 추천 HTTP의 DB 검색이 이어지지 않았다.

## 원인
수집 Observation v2는 텍스트 계약이며 벡터 입력 필드가 없었다. 이는 백엔드 작업자가 스냅샷을 처리하도록 한 명세와 맞지만 그 후속 작업자가 없었다. 기존 DB 검색 구현은 HTTP 기본 경로에서 사용되지 않았다. 사용자 제공 Claude 분석은 문제를 찾는 참고 자료로 사용했으며 이 일지는 GPT가 적용한 `2d444b0`만 기록한다.

## 해결 방안 (검토한 선택지)
| 선택지 | 장점 | 단점 | 채택 |
| --- | --- | --- | --- |
| 크롤러가 벡터를 생성해 전송 | 계산을 수집 단계로 이동 | 모든 크롤러의 모델/전처리 동기화와 무거운 의존성 필요 | 미채택 |
| 백엔드 outbox + 임베딩 작업자 + DB 검색 | 텍스트 수집 계약 유지, 모델 계약 중앙 관리 | 초기 적재·작업자 운영 필요 | 채택 |
| 요청마다 메모리 재색인 유지 | 초기 설정 적음 | 조회 상한·반복 계산·품질 한계 | 교체 |

## 해결 (적용 내용)
- `main`을 수정하지 않고 `maintest`의 `2d444b0`에 적용했다. 여기서 작업자는 백엔드 담당자인 사람이 아니라 자동 실행되는 `embedding-worker` 프로그램이다.
- 마이그레이션 `0008`과 `app.embedding_jobs`를 추가했다. 상품 원문 변경 시 버전 무효화와 공개 스냅샷 작업 등록이 같은 트랜잭션에서 이뤄진다. 롤백되면 작업도 남지 않는다.
- 기본 모델은 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, 384차원·CPU·정규화이며 revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`를 고정했다. 모델·revision·전처리·영역 계약을 등록하고 HNSW 인덱스와 기존 상품/가상 데이터 backfill을 준비했다.
- 작업자는 `SKIP LOCKED`로 5분 임대를 받고 트랜잭션 밖에서 계산한다. 저장 직전에 버전·임대 토큰을 검사해 오래된 결과를 버린다. 벡터 저장과 작업 제거는 한 트랜잭션으로 처리한다.
- 추천 HTTP는 인코더를 재사용하고 `PgVectorIndex`로 검색한다. 분석 작업자는 상품 목록 대신 검색어·영역·사용자 조건을 보낸다. URL 문맥 조회도 DB의 정확한 URL 검색으로 바꿨다.
- DB/계약 준비 실패는 503으로 표시하고 해시·메모리로 자동 대체하지 않는다. `RECO_EMBEDDER=hash`는 별도 계약의 연결 테스트용이다.
- 공통 Compose에 일회성 owner 권한 초기화, app 권한 작업자/추천 서비스를 연결했다. 모델은 이미지 빌드 시 받고 런타임에서는 오프라인으로 읽는다. 공개 상품 텍스트만 작업에 넣고 개인 OCR·검색어·프로필을 작업 테이블에 적재하지 않는다.

## 왜 그렇게 해결했는지
크롤러는 수집에 집중하고 모델과 전처리 규칙을 백엔드에서 일치시킨다. outbox는 DB 저장 성공과 작업 유실 사이의 틈을 줄이고, 버전/임대 검증은 느린 계산이 최신 상품을 덮어쓰지 못하게 한다. 의미 검색이 준비되지 않았을 때 조용히 임시 추천을 내보내면 장애를 알아채기 어려워 명시적으로 실패시킨다.

## 검증
- [Actions 실행 45095253284](https://github.com/daon217/swproject/actions/runs/45095253284): 실제 PostgreSQL/pgvector 경로의 추천·작업자 테스트 66개 통과·1개 건너뜀, 운영 도구 17개 통과, API 62개 통과·1개 건너뜀. 이 실행의 합계는 **145개 통과·2개 건너뜀**이다. 과거 다른 실행과 더하지 않는다.
- CI 명령: `EMBEDDING_INTEGRATION=1 python -m pytest -q services/recommendation/tests services/dev_runtime/test_analysis_worker.py`; `python -m unittest discover -s tools -p 'test_*.py' -q`; API는 `CATALOG_INTEGRATION=1`과 테스트용 연결 설정으로 `python -m pytest -q --ignore=tests/test_sample_mutations.py`를 실행했다.
- 1,001개 기존 상품, 변경 무효화, 롤백, 임대 회수, 동시 처리, 재시도, 판매 상태, 영역/계약 분리, HTTP 경로를 검증했다. 컨테이너 smoke 응답에서 추천 ID 6개를 확인했다.
- 별도 실제 모델 검사에서 네트워크 없는 컨테이너의 384차원 출력과 한국어 관련성 한 사례를 확인했다. “무선 헤드셋” 대비 헤드폰 약 0.6387, 채소 약 0.0086이었다. 의미 품질 전체 평가가 아니다.
- 회고 작성 시 Actions 성공 상태를 재확인했다. 운영 서버 배포·운영 DB 변경은 수행 범위 밖이었다.

이번 일지 작성에서는 코드 테스트를 재실행하지 않았다. 커밋별 파일·행 존재와 기록 근거를 대조했다.

## 남은 과제 / 주의
- 이 커밋의 작업자는 **한 번에 1건이며 재시도 횟수 상한이 없었다.** 후속 Claude 수정 #06/#07을 GPT 성과로 합산하지 않는다.
- 첫 실행에서 전체 backfill이 끝나기 전에는 결과가 비어 있거나 일부만 나올 수 있다. 기존 #24의 모델 전환 공백도 별도 과제다.
- DB 연결 풀(#22), 식품 원재료 부족(#27), 실제 상품의 검색 품질·대량 적재 시간·운영 부하 측정은 해결 완료로 표기하지 않는다. 가격만 바뀔 때는 재임베딩하지 않는다.
- 모델/전처리가 바뀌면 새 계약·이미지·재계산과 전환 계획이 필요하다. 실행 절차는 해당 커밋의 `docs/embedding-pipeline.md`를 따른다.
