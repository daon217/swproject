# [GPT-6 (Codex)] 개발일지 · 2026-11-24 팀 코드 통합·OCR 분석 작업자·관리 화면 연결 (#42)

- 날짜: 2026-11-24 (회고 기록일, Asia/Seoul)
- 작업 시기: 2026-11-19 (한국 시간; 일부 Git 기록은 UTC 11-18)
- 상태: 부분 해결 — 아래에 명시한 당시 범위 기준
- 브랜치 / 커밋: 기록은 `devlog`; 코드 근거 [`a9da43b`](https://github.com/daon217/swproject/commit/a9da43b7727c515344c94e552eacd27969396b5d) / [`4969fa3`](https://github.com/daon217/swproject/commit/4969fa38ee17ff306c92f8eaa4e9a61f652d009a) / [`46b781a`](https://github.com/daon217/swproject/commit/46b781aaf789e12ef544e9b00dee339768189e21) / [`a19c431`](https://github.com/daon217/swproject/commit/a19c4312b0e18b78c6b9260cbac299d223558eba)
- 관련 파일: [services/dev_runtime/analysis_worker.py:19](https://github.com/daon217/swproject/blob/a19c4312b0e18b78c6b9260cbac299d223558eba/services/dev_runtime/analysis_worker.py#L19); [services/recommendation/http_service.py:51](https://github.com/daon217/swproject/blob/a19c4312b0e18b78c6b9260cbac299d223558eba/services/recommendation/http_service.py#L51); [infra/integration/compose.yaml:1](https://github.com/daon217/swproject/blob/a19c4312b0e18b78c6b9260cbac299d223558eba/infra/integration/compose.yaml#L1); [tools/integration_smoke.py:14](https://github.com/daon217/swproject/blob/a19c4312b0e18b78c6b9260cbac299d223558eba/tools/integration_smoke.py#L14)
- 작성 AI: GPT-6 (Codex, 회고 작성)
- 원 작업 AI: GPT/ChatGPT/Codex. 과거 세션의 상세 모델 버전은 미확인.

> 과거 작업을 커밋·PR·대화 기록으로 복원한 일지다. 선택지 표는 회고 시점의 설계 비교이며, 모든 대안을 당시 구현·실험했다는 뜻이 아니다. 검증 수치는 해당 커밋의 기록이며 최신 코드 전체의 재검증 결과가 아니다. [기록 범위와 근거](2026-11-24-gpt-retrospective-scope-gpt-6.md)를 함께 읽는다.

## 문제점
팀별 OCR·추천·수집·화면 구현이 있어도 분석 요청이 실제 처리되어 DB와 화면으로 돌아오는 실행 흐름이 연결되지 않았다.

## 원인
작업 임대/완료 API, Vision 서버, 추천 HTTP 어댑터와 화면의 데이터 계약을 맞춰야 했다. 수집 코드의 import 경로와 CI 실행 환경도 달랐다.

## 해결 방안 (검토한 선택지)
| 선택지 | 장점 | 단점 | 채택 |
| --- | --- | --- | --- |
| 기존 대기 상태/고정 응답 유지 | 통합 비용 적음 | 실제 처리 완료 검증 불가 | 임시 단계 종료 |
| 팀 엔진을 HTTP/작업자 어댑터로 통합 | 기존 파트 코드를 활용해 끝까지 실행 | 임시 추천 구현의 품질 한계 유지 | 당시 채택 |

## 해결 (적용 내용)
- Vision 8100, 분석 작업 임대, OCR 호출, 추천 호출, 완료 결과 DB 저장을 연결했다. 팀이 작성한 엔진 자체를 GPT 신규 구현으로 기록하지 않는다.
- 관리자 화면의 실제 CRUD와 수집 Observation 어댑터, 사이드바/플로팅·비회원 카탈로그 흐름을 통합했다. 로그 민감값 노출을 줄이는 처리도 포함했다.
- 후속 커밋에서 수집기 최신 변경과 import/CI 경로를 정리했다.
- 당시 추천 HTTP는 `HashEmbedder`/규칙 랭커와 요청별 메모리 인덱스를 사용하고 영역별 상품 조회 상한이 있었다. 이 통합은 실제 pgvector 의미 검색 완성을 뜻하지 않는다.

## 왜 그렇게 해결했는지
먼저 각 팀 파트 사이의 실행 계약을 연결해 실제 요청을 끝까지 처리할 수 있게 했다. 다만 임시 해시/메모리 추천은 지속 가능한 검색 구조가 아니어서 #43에서 교체했다.

## 검증
- [PR #13](https://github.com/daon217/swproject/pull/13): 6개 CI 워크플로 성공, 실제 PostgreSQL·한국어 PaddleOCR·브라우저 관리 CRUD 확인 기록. 로컬 Docker 권한 제한으로 CI에서 검증한 항목을 로컬 실행으로 표기하지 않는다.
- 수집 테스트는 당시 총 108개(11번가 오프라인 사례 62개 포함) 기록. 이 수치를 전체 사이트 실시간 수집 성공으로 해석하지 않는다.
- 실행 구성: `python tools/workspace.py up --scope integrated`; 통합 검증 진입점은 `tools/integration_smoke.py`이며 당시 환경 설정이 필요하다.
- 로컬 Codex `9343be3`/`9a8b6e0`와 원격 `a9da43b`/`a19c431`의 tree 일치를 확인했다.

이번 일지 작성에서는 코드 테스트를 재실행하지 않았다. 커밋별 파일·행 존재와 기록 근거를 대조했다.

## 남은 과제 / 주의
- 임시 상품 1,000개 조회·메모리 재색인·해시 벡터는 성능과 추천 품질에 한계가 있었다. 이 문제를 이 단계에서 해결했다고 쓰지 않는다.
- 11번가 실수집 어댑터·운영 수집 성공률은 당시 검증 범위 밖이다.
- NAS 및 이후 다른 AI의 기능 변경을 이 GPT 통합 작업에 합산하지 않는다.
