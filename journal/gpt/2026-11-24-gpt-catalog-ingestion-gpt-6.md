# [GPT-6 (Codex)] 개발일지 · 2026-11-24 수집 API·상품 갱신·필드별 검증 (#35)

- 날짜: 2026-11-24 (회고 기록일, Asia/Seoul)
- 작업 시기: 2026-11-05~11-16
- 상태: 부분 해결 — 아래에 명시한 당시 범위 기준
- 브랜치 / 커밋: 기록은 `devlog`; 코드 근거 [`cd72f41`](https://github.com/daon217/swproject/commit/cd72f4113d7a3064b1de243d6d94ce0f997e5e8c) / [`22fa5bf`](https://github.com/daon217/swproject/commit/22fa5bfc84b255315c7be08c87b5342b2a8a9f0e) / [`6058d22`](https://github.com/daon217/swproject/commit/6058d22f34c30f98c771fab4381192b79d5578f0) / [`0e6690b`](https://github.com/daon217/swproject/commit/0e6690bec28d440688519f8f39f3c4d0fa24af64)
- 관련 파일: [services/api/kkulpick/ingest.py:21](https://github.com/daon217/swproject/blob/0e6690bec28d440688519f8f39f3c4d0fa24af64/services/api/kkulpick/ingest.py#L21); [services/api/kkulpick/models.py:11](https://github.com/daon217/swproject/blob/0e6690bec28d440688519f8f39f3c4d0fa24af64/services/api/kkulpick/models.py#L11); [services/api/tests/test_sample_mutations.py:26](https://github.com/daon217/swproject/blob/0e6690bec28d440688519f8f39f3c4d0fa24af64/services/api/tests/test_sample_mutations.py#L26)
- 작성 AI: GPT-6 (Codex, 회고 작성)
- 원 작업 AI: GPT/ChatGPT/Codex. 과거 세션의 상세 모델 버전은 미확인.

> 과거 작업을 커밋·PR·대화 기록으로 복원한 일지다. 선택지 표는 회고 시점의 설계 비교이며, 모든 대안을 당시 구현·실험했다는 뜻이 아니다. 검증 수치는 해당 커밋의 기록이며 최신 코드 전체의 재검증 결과가 아니다. [기록 범위와 근거](2026-11-24-gpt-retrospective-scope-gpt-6.md)를 함께 읽는다.

## 문제점
반복 수집, 늦게 도착한 가격, 품절·판매 종료·수집 오류가 섞이면 최신 상품 상태를 잘못 덮어쓸 수 있었다. 입력 필드별 실제 처리 확인도 필요했다.

## 원인
수집 시도와 상품의 현재 상태를 구분해야 하며 재전송 식별자·관측 시각·명시적 필드 존재 여부가 필요했다. `Observation` 입력 검증과 `accept` 저장 처리가 이 경계다.

## 해결 방안 (검토한 선택지)
| 선택지 | 장점 | 단점 | 채택 |
| --- | --- | --- | --- |
| 수집 원문을 그대로 덮어쓰기 | 단순함 | 과거 관측·누락 필드로 현재 데이터 훼손 가능 | 미채택 |
| Observation 검증 + 상태별 병합/격리 | 중복·오래된 데이터·불명확한 식별자 구분 | 분기와 테스트 증가 | 채택 |

## 해결 (적용 내용)
- 상품/식품 분리 및 최초 식별자 결합, 관측 재전송, 가격·URL·판매 상태 변경, 실패 이력 처리 경로를 구현·보완했다.
- 알 수 없는 입력 필드는 거절하고, 누락 필드와 명시적 null을 구분했다. 과거 관측·같은 시각의 충돌·식별자 불명확 사례는 각각 별도 처리했다.
- 실제 수집 형태를 본뜬 비식별 가상 표본에 32개 단일 필드 변형 테스트를 추가했다. 원본 300개 데이터는 저장소에 넣지 않았다.
- 벡터 저장/검색 도우미는 존재했지만, 이 단계에서는 실제 임베딩 모델·자동 계산 작업자·HTTP DB 검색 경로까지 연결하지 않았다.

## 왜 그렇게 해결했는지
쇼핑몰 접속 실패를 판매 종료와 동일하게 처리하지 않고, 잘못된 관측 한 번으로 정상 상품이 삭제·덮어쓰기 되는 일을 줄이기 위해서다. 초기의 단순 URL·제목·쇼핑몰 중복 개념보다 실제 구현은 출처 식별자·옵션·관측 키를 함께 다룬다.

## 검증
- [PR #3](https://github.com/daon217/swproject/pull/3)에 필드별 결과와 최종 API 검증 기록이 있다. `tests/test_sample_mutations.py`의 32개 사례는 가격/URL/품절/판매 종료/과거값/충돌/오류/필드 누락 등을 각각 바꾼다.
- 격리·마이그레이션된 DB에서 재현하는 명령 형태: `CATALOG_INTEGRATION=1 python -m pytest -q tests/test_sample_mutations.py` (`services/api`에서 실행, DB 연결 설정 필요).
- 최종 PR 검증은 일반 59개 + 변형 32개 = 91개 통과, 원본 데이터 의존 검사 1개 건너뜀. [Actions 실행 44050527427](https://github.com/daon217/swproject/actions/runs/44050527427) 성공 상태를 다시 확인했다.

이번 일지 작성에서는 코드 테스트를 재실행하지 않았다. 커밋별 파일·행 존재와 기록 근거를 대조했다.

## 남은 과제 / 주의
- 32개 검사는 저장/병합 정책 검증이며 쇼핑몰의 실제 가격·재고가 참이라는 검증이 아니다.
- 수집기 전체 사이트 지원과 실제 운영 수집 성공률은 별도다. 자동 임베딩 연결은 #43의 후속 작업에서 다룬다.
- 현재 수집기 연계의 미해결 사항은 기존 OPEN_ISSUES.md를 따른다.
