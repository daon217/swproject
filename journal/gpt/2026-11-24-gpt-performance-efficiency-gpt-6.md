# [GPT-6 (Codex)] 개발일지 · 2026-11-24 성능 측정·조회 쿼리와 인덱스 개선 (#37)

- 날짜: 2026-11-24 (회고 기록일, Asia/Seoul)
- 작업 시기: 2026-11-17
- 상태: 부분 해결 — 아래에 명시한 당시 범위 기준
- 브랜치 / 커밋: 기록은 `devlog`; 코드 근거 [`ba68281`](https://github.com/daon217/swproject/commit/ba68281e7701c2c79b4735cccdbc145652e3564b) / [`085e7f6`](https://github.com/daon217/swproject/commit/085e7f618608d7370f82fd0da62d8ca88afe24e3) / [`248d4c5`](https://github.com/daon217/swproject/commit/248d4c51fcc0fd6302a9ea423accf62855c85141)
- 관련 파일: [services/api/kkulpick/analyses.py:128](https://github.com/daon217/swproject/blob/085e7f618608d7370f82fd0da62d8ca88afe24e3/services/api/kkulpick/analyses.py#L128); [services/api/migrations/versions/0005_efficiency.py:14](https://github.com/daon217/swproject/blob/085e7f618608d7370f82fd0da62d8ca88afe24e3/services/api/migrations/versions/0005_efficiency.py#L14); [services/api/tests/test_efficiency.py:15](https://github.com/daon217/swproject/blob/085e7f618608d7370f82fd0da62d8ca88afe24e3/services/api/tests/test_efficiency.py#L15); [tools/performance.py:45](https://github.com/daon217/swproject/blob/085e7f618608d7370f82fd0da62d8ca88afe24e3/tools/performance.py#L45)
- 작성 AI: GPT-6 (Codex, 회고 작성)
- 원 작업 AI: GPT/ChatGPT/Codex. 과거 세션의 상세 모델 버전은 미확인.

> 과거 작업을 커밋·PR·대화 기록으로 복원한 일지다. 선택지 표는 회고 시점의 설계 비교이며, 모든 대안을 당시 구현·실험했다는 뜻이 아니다. 검증 수치는 해당 커밋의 기록이며 최신 코드 전체의 재검증 결과가 아니다. [기록 범위와 근거](2026-11-24-gpt-retrospective-scope-gpt-6.md)를 함께 읽는다.

## 문제점
분석 이력의 카드 조회가 건수에 따라 SQL을 반복했고, 성능이 충분한지 객관적인 측정값이 없었다.

## 원인
분석별 상품 카드 조회가 N+1 패턴을 만들었다. 이력·만료·목록 조회 조건에 맞는 인덱스와 중복 작업 억제가 필요했다. 인덱스 크기 검사에는 search_path 관련 오류도 있었다.

## 해결 방안 (검토한 선택지)
| 선택지 | 장점 | 단점 | 채택 |
| --- | --- | --- | --- |
| 캐시/서버 증설부터 적용 | 일부 지연 완화 가능 | 반복 SQL 원인이 남고 복잡성 증가 | 미채택 |
| 일괄 조회·조건별 인덱스·부하 측정 | 원인 개선과 정량 비교 가능 | 쓰기/인덱스 공간 비용 증가 | 채택 |

## 해결 (적용 내용)
- 분석 이력 카드 조회를 일괄화해 100건 이력 기준 catalog SQL을 최대 101회에서 2회로 줄였다. 인증 DB 조회는 이 수치에 포함하지 않는다.
- 마이그레이션 `0005_efficiency`에서 조회 패턴을 위한 인덱스 5개를 추가했다. 반복 폴링·만료 처리도 보완했다.
- `085e7f6`에서 인덱스 크기 검사 기준을 수정하고 성능 결과 문서를 남겼다.

## 왜 그렇게 해결했는지
서비스 규모를 늘리기 전에 요청 수에 비례해 증가하는 DB 왕복을 없애는 편이 효과를 설명하고 검증하기 쉬웠다. 인덱스는 모든 컬럼에 무조건 추가하지 않고 실제 조건 중심으로 선택했다.

## 검증
- [PR #3](https://github.com/daon217/swproject/pull/3), [Actions 실행 44050527427](https://github.com/daon217/swproject/actions/runs/44050527427): 10,000행·동시성 16에서 새 관측/갱신/재전송/조회 p95가 각각 178.24/158.29/89.98/62.46ms였고 요청 오류 0건이었다. 최종값과 페이지별 행 수도 확인한 기록이다.
- 1,000행·동시성 8 결과는 각각 69.29/89.69/37.94/29.68ms였다. 환경이 다른 실행의 수치를 하나의 보장값으로 쓰지 않는다.
- 재현 도구 예: 격리 데이터베이스에서 `python tools/performance.py --allow-write --rows 10000 --workers 16 --cleanup`. 쓰기 테스트이므로 운영 DB에서 그대로 실행하지 않는다.
- `tests/test_efficiency.py`는 이력 조회 SQL 횟수, 반복 폴링, 조회 계획 관련 검증을 포함한다.

이번 일지 작성에서는 코드 테스트를 재실행하지 않았다. 커밋별 파일·행 존재와 기록 근거를 대조했다.

## 남은 과제 / 주의
- 이 수치는 수집/조회 API 테스트 결과다. OCR·실제 임베딩·전체 추천 응답 시간이나 운영 서버 SLA가 아니다.
- 기존 미해결 #22(DB 연결 풀 미사용)는 이 최적화로 해결했다고 주장하지 않는다.
- 실데이터 분포·동시 사용자·장기 운영 부하 검증이 남는다.
